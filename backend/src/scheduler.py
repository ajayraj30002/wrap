from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uuid import UUID

from src.db.models import Provider, ProviderModel, RoutingDecision, Worker, utcnow


class NoWorkerAvailable(Exception):
    pass


class Scheduler:
    routing_version = "phase1-deterministic-v1"

    async def select_worker(
        self,
        session: AsyncSession,
        *,
        request_id: str,
        model: str,
        allowed_worker_ids: set[UUID] | None = None,
        execution_run_id: UUID | None = None,
        execution_node_id: str | None = None,
        estimated_tokens: int = 0,
    ) -> Worker:
        from src.services.model_groups import is_virtual_group, get_group, expand_group_models

        from src.services.rate_limiter import upstream_quota_limiter

        def _worker_saturation_key(w: Worker) -> tuple[int, float]:
            c_id = str(w.credential_id or w.id)
            p_name = w.provider.name if getattr(w, "provider", None) else None
            u = upstream_quota_limiter.get_utilization(c_id, p_name)
            return (1 if u["is_saturated"] else 0, round(u["rpm_percent"], 2))

        def _token_mass_priority(w: Worker) -> int:
            if estimated_tokens <= 0:
                return 0
            pname = (w.provider.name or "").lower() if getattr(w, "provider", None) else ""
            mname = (w.model or "").lower()
            # Heavy prompt (>1500 tokens): steer to 1M TPM models (Gemini Flash), protect tight 6k TPM (Groq)
            if estimated_tokens >= 1500:
                if "gemini" in pname or "google" in pname or "flash" in mname:
                    return -10
                if "groq" in pname:
                    return 10
            # Low tokens (<1000 tokens): prefer fast LPUs
            elif estimated_tokens < 1000:
                if "cerebras" in pname or "groq" in pname:
                    return -5
            return 0

        statement = self._base_query()
        if is_virtual_group(model):
            group = get_group(model)
            expanded_models = expand_group_models(group.models)
            group_stmt = statement.where(Worker.model.in_(expanded_models))
            if allowed_worker_ids is not None:
                group_stmt = group_stmt.where(Worker.id.in_(allowed_worker_ids))
            result = await session.execute(group_stmt)
            candidates = list(result.scalars().all())
            if candidates:
                # Prioritize by non-saturated quota, token mass affinity, then group model order, then LRU
                model_priority = {m: i for i, m in enumerate(expanded_models)}
                candidates.sort(key=lambda w: (
                    _worker_saturation_key(w)[0],
                    _token_mass_priority(w),
                    model_priority.get(w.model, 999),
                    _worker_saturation_key(w)[1],
                    w.last_used_at or w.created_at,
                ))
                selected = candidates[0]
                selected.last_used_at = utcnow()
                sat_flag = _worker_saturation_key(selected)[0]
                desc_reason = f"virtual model group '{group.id}' worker ({selected.model})"
                if sat_flag == 0 and len(candidates) > 1:
                    desc_reason += " [preemptive quota sharding optimal]"
                if estimated_tokens >= 1500:
                    desc_reason += f" [token-mass-bouncer: {estimated_tokens} tokens routed to high-TPM context tier]"
                elif 0 < estimated_tokens < 1000:
                    desc_reason += f" [token-mass-bouncer: {estimated_tokens} tokens routed to low-latency LPU throughput]"
                await self._record_decision(
                    session,
                    request_id,
                    [str(w.id) for w in candidates],
                    str(selected.id),
                    desc_reason,
                    execution_run_id,
                    execution_node_id,
                )
                await session.flush()
                return selected
        elif model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
            m_stmt = statement.where(Worker.model == model)
            if allowed_worker_ids is not None:
                m_stmt = m_stmt.where(Worker.id.in_(allowed_worker_ids))
            result = await session.execute(m_stmt)
            candidates = list(result.scalars().all())
            if not candidates and allowed_worker_ids is None:
                # Fallback to general pool for standard tool aliases (e.g. gpt-4o, claude-3-5-sonnet) when unrestricted
                result = await session.execute(statement)
                candidates = list(result.scalars().all())
        else:
            if allowed_worker_ids is not None:
                statement = statement.where(Worker.id.in_(allowed_worker_ids))
            result = await session.execute(statement)
            candidates = list(result.scalars().all())

        if not candidates:
            await self._record_decision(session, request_id, [], None, f"no enabled healthy worker for model {model}", execution_run_id, execution_node_id)
            raise NoWorkerAvailable(f"No enabled healthy worker available for model {model}")

        # Choose worker with non-saturated quota, token mass affinity, then least-recently-used
        candidates.sort(key=lambda w: (
            _worker_saturation_key(w)[0],
            _token_mass_priority(w),
            _worker_saturation_key(w)[1],
            w.last_used_at or w.created_at,
        ))
        selected = candidates[0]
        selected.last_used_at = utcnow()
        reason = "least-recently-used healthy worker"
        if _worker_saturation_key(selected)[0] == 0 and len(candidates) > 1:
            reason += " (preemptive quota sharding active)"
        if estimated_tokens >= 1500:
            reason += f" (token-mass-bouncer: {estimated_tokens} tokens to high-TPM context tier)"
        elif 0 < estimated_tokens < 1000:
            reason += f" (token-mass-bouncer: {estimated_tokens} tokens to low-latency LPU throughput)"
        await self._record_decision(
            session,
            request_id,
            [str(worker.id) for worker in candidates],
            str(selected.id),
            reason,
            execution_run_id,
            execution_node_id,
        )
        await session.flush()
        return selected

    def _base_query(self) -> Select[tuple[Worker]]:
        return (
            select(Worker)
            .join(Provider, Worker.provider_id == Provider.id)
            .outerjoin(ProviderModel, Worker.provider_model_id == ProviderModel.id)
            .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
            .where(Provider.enabled.is_(True))
            .where(Worker.enabled.is_(True))
            .where(Worker.health_status.in_(["healthy", "unknown"]))
            .where((Worker.provider_model_id.is_(None)) | (ProviderModel.status.in_(["ACTIVE", "UNKNOWN"])))
            .order_by(Worker.last_used_at.asc().nullsfirst(), Worker.created_at.asc())
        )

    async def _record_decision(
        self,
        session: AsyncSession,
        request_id: str,
        candidates: list[str],
        selected: str | None,
        reason: str,
        execution_run_id: UUID | None = None,
        execution_node_id: str | None = None,
    ) -> None:
        session.add(
            RoutingDecision(
                request_id=request_id,
                candidate_workers=candidates,
                selected_worker=selected,
                decision_reason=reason,
                routing_version=self.routing_version,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
        )
