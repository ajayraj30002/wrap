import asyncio
import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.analytics.critical_path import calculate_critical_path
from src.analytics.enums import WorkflowEventType
from src.analytics.event_logger import EventLogger
from src.analytics.models import WorkflowRun
from src.analytics.service import AnalyticsService
from src.core.config import Settings
from src.db.models import ExecutionNode, ExecutionRun, GatewayApiKey, Provider, RoutingDecision, Worker
from src.db.session import AsyncSessionLocal
from src.orchestration.models import DAGNode, TaskDAG
from src.orchestration.validator import DAGValidator
from src.providers.base import InvalidRequestError, ModelNotFoundError, ProviderError, ProviderUnavailableError, RateLimitError
from src.providers.registry import registry
from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.scheduler import NoWorkerAvailable, Scheduler
from src.services.credentials import get_credential_secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DAGExecutionError(Exception):
    pass


class DAGExecutor:
    def __init__(self, *, settings: Settings, router) -> None:
        self.settings = settings
        self.router = router
        self.validator = DAGValidator(
            max_nodes=settings.DAG_MAX_NODES,
            max_depth=settings.DAG_MAX_DEPTH,
            max_parallel_nodes=settings.DAG_MAX_PARALLEL_NODES,
            max_total_execution_time=settings.DAG_MAX_TOTAL_EXECUTION_SECONDS,
        )
        self._routing_lock = asyncio.Lock()

    async def execute(
        self,
        request: ChatCompletionRequest,
        dag: TaskDAG,
        *,
        request_id: str,
        policy: str = "balanced",
        gateway_key: GatewayApiKey | None = None,
        decision: Any = None,
        planning_ms: int = 0,
    ) -> dict[str, Any]:
        self.validator.validate(dag)
        started = _now()
        initial_metadata: dict[str, Any] = {"task_id": dag.task_id, "planning_ms": planning_ms}
        if decision is not None:
            initial_metadata["decomposition_reason"] = getattr(decision, "reason", "DAG orchestration selected")
            initial_metadata["decomposition_version"] = getattr(decision, "decomposition_version", "phase2b-v2")
            initial_metadata["confidence"] = getattr(decision, "confidence", 1.0)
            initial_metadata["workstreams"] = getattr(decision, "workstreams", [])

        async with AsyncSessionLocal() as session:
            run = ExecutionRun(
                request_id=request_id,
                execution_mode="DAG",
                status="running",
                node_count=len(dag.nodes),
                max_parallelism=self.settings.DAG_MAX_PARALLEL_NODES,
                run_metadata=initial_metadata,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id

            # Create matching WorkflowRun for historical analytics
            wf_run = WorkflowRun(
                id=run_id,
                workflow_definition_id=dag.task_id,
                execution_run_id=run_id,
                request_id=request_id,
                status="RUNNING",
                execution_mode="DAG",
                routing_policy=policy,
                requested_model=request.model,
                started_at=started,
                run_metadata=initial_metadata,
            )
            session.add(wf_run)
            await session.commit()

        event_logger = EventLogger(run_id)

        # Emit initial workflow events
        async with AsyncSessionLocal() as session:
            await event_logger.log_event(
                session,
                WorkflowEventType.WORKFLOW_CREATED,
                payload={"requested_model": request.model, "nodes_count": len(dag.nodes)},
            )
            await event_logger.log_event(
                session,
                WorkflowEventType.WORKFLOW_STARTED,
                payload={"routing_policy": policy, "execution_mode": "DAG"},
            )
            # Emit TASK_READY for initial source nodes
            for node in dag.nodes:
                if not node.depends_on:
                    await event_logger.log_event(
                        session,
                        WorkflowEventType.TASK_READY,
                        task_id=node.id,
                        payload={"node_type": node.type, "description": node.description},
                    )
            await session.commit()

        outputs: dict[str, dict[str, Any]] = {}
        pending = {node.id for node in dag.nodes}
        running: set[str] = set()
        running_workers: set[uuid.UUID] = set()
        running_providers: set[str] = set()
        running_credentials: set[uuid.UUID] = set()
        failed: set[str] = set()
        semaphore = asyncio.Semaphore(self.settings.DAG_MAX_PARALLEL_NODES)
        deadline = time.monotonic() + self.settings.DAG_MAX_TOTAL_EXECUTION_SECONDS
        node_map = dag.node_map()

        try:
            while pending:
                if time.monotonic() > deadline:
                    raise asyncio.TimeoutError("DAG exceeded total execution timeout")
                runnable = []
                blocked_by_failures = []
                for node_id in sorted(pending):
                    node = node_map[node_id]
                    if node_id in running:
                        continue

                    if not node.depends_on:
                        runnable.append(node)
                        continue

                    if not node.allow_partial_input:
                        if any(dep in failed for dep in node.depends_on):
                            blocked_by_failures.append(node)
                        elif all(dep in outputs for dep in node.depends_on):
                            runnable.append(node)
                    else:
                        # For partial-input enabled nodes:
                        # If all dependencies have settled and all of them failed, the node cannot run
                        if all(dep in failed for dep in node.depends_on):
                            blocked_by_failures.append(node)
                        # If all dependencies have resolved (settled in either outputs or failed)
                        # and at least one dependency succeeded (is in outputs), it is runnable!
                        elif all(dep in outputs or dep in failed for dep in node.depends_on) and any(dep in outputs for dep in node.depends_on):
                            runnable.append(node)

                for node in blocked_by_failures:
                    pending.remove(node.id)
                    failed.add(node.id)
                    await self._persist_skipped_node(run_id, node, "dependency_failed", event_logger=event_logger)
                if not runnable:
                    if blocked_by_failures:
                        continue
                    raise DAGExecutionError("No runnable DAG nodes remain")

                # Emit TASK_READY for any runnable nodes with dependencies that just became ready
                async with AsyncSessionLocal() as session:
                    for node in runnable:
                        if node.depends_on:
                            await event_logger.log_event(
                                session,
                                WorkflowEventType.TASK_READY,
                                task_id=node.id,
                                payload={"node_type": node.type, "description": node.description},
                            )
                    await session.commit()

                tasks = []
                current_batch = runnable[: self.settings.DAG_MAX_PARALLEL_NODES]
                for node in current_batch:
                    pending.remove(node.id)
                    running.add(node.id)
                    tasks.append(
                        asyncio.create_task(
                            self._execute_node(
                                request,
                                node,
                                outputs,
                                run_id=run_id,
                                request_id=request_id,
                                policy=policy,
                                gateway_key=gateway_key,
                                semaphore=semaphore,
                                event_logger=event_logger,
                                running_workers=running_workers,
                                running_providers=running_providers,
                                running_credentials=running_credentials,
                            )
                        )
                    )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for node, result in zip(current_batch, results):
                    running.discard(node.id)
                    if isinstance(result, Exception):
                        logger.error("DAG node %s failed with exception: %r", node.id, result, exc_info=result)
                        failed.add(node.id)
                    else:
                        outputs[node.id] = result

            final_node = next((node for node in reversed(dag.nodes) if node.type == "synthesis"), dag.nodes[-1])
            if final_node.id not in outputs:
                if outputs:
                    # Construct unified synthesis consolidating all completed deliverables
                    deliverable_sections = []
                    total_in_tokens = 0
                    total_out_tokens = 0
                    for nid, out in outputs.items():
                        desc = node_map.get(nid, DAGNode(id=nid, type="", description="")).description or nid
                        txt = out.get("content", "").strip()
                        if txt:
                            deliverable_sections.append(f"## Subtask Deliverable: {nid} ({desc})\n\n{txt}")
                        usage = out.get("usage")
                        if isinstance(usage, dict):
                            total_in_tokens += usage.get("input_tokens", 0) or 0
                            total_out_tokens += usage.get("output_tokens", 0) or 0

                    merged_content = (
                        "# Unified System Deliverables (Partial Execution Synthesis)\n\n"
                        + "\n\n---\n\n".join(deliverable_sections)
                    )
                    recovered_output = {
                        "node_id": "partial_recovery_synthesis",
                        "type": "synthesis",
                        "content": merged_content,
                        "tool_calls": None,
                        "usage": {"input_tokens": total_in_tokens, "output_tokens": total_out_tokens},
                        "_metrics": {"is_synthesis": True, "partial_recovery": True},
                    }
                    await self._complete_run(run_id, started, "partial_success", len(outputs), len(failed), planning_ms=planning_ms, event_logger=event_logger, outputs=outputs)
                    return recovered_output
                await self._complete_run(run_id, started, "failed", len(outputs), max(1, len(failed)), planning_ms=planning_ms, event_logger=event_logger, outputs=outputs)
                raise DAGExecutionError(f"DAG execution failed: no completed node outputs (failed nodes: {len(failed)})")

            await self._complete_run(run_id, started, "success", len(outputs), len(failed), planning_ms=planning_ms, event_logger=event_logger, outputs=outputs)
            return outputs[final_node.id]
        except asyncio.CancelledError:
            await self._complete_run(run_id, started, "cancelled", len(outputs), len(failed), planning_ms=planning_ms, event_logger=event_logger, outputs=outputs)
            raise
        except Exception:
            await self._complete_run(run_id, started, "failed", len(outputs), max(1, len(failed)), planning_ms=planning_ms, event_logger=event_logger, outputs=outputs)
            raise

    async def _execute_node(
        self,
        request: ChatCompletionRequest,
        node: DAGNode,
        outputs: dict[str, dict[str, Any]],
        *,
        run_id,
        request_id: str,
        policy: str,
        gateway_key: GatewayApiKey | None,
        semaphore: asyncio.Semaphore,
        event_logger: EventLogger,
        running_workers: set[uuid.UUID] | None = None,
        running_providers: set[str] | None = None,
        running_credentials: set[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        async with semaphore:
            attempts = 0
            failed_worker_ids: set[uuid.UUID] = set()
            while True:
                attempts += 1
                try:
                    return await asyncio.wait_for(
                        self._invoke_node(
                            request,
                            node,
                            outputs,
                            run_id=run_id,
                            request_id=request_id,
                            policy=policy,
                            gateway_key=gateway_key,
                            retry_count=attempts - 1,
                            event_logger=event_logger,
                            failed_worker_ids=failed_worker_ids,
                            running_workers=running_workers,
                            running_providers=running_providers,
                            running_credentials=running_credentials,
                        ),
                        timeout=node.timeout_seconds,
                    )
                except InvalidRequestError as exc:
                    await self._persist_failed_node(run_id, node, "invalid_request_error", "invalid request", attempts - 1)
                    async with AsyncSessionLocal() as session:
                        await event_logger.finish_attempt(
                            session,
                            task_id=node.id,
                            attempt_number=attempts,
                            status="FAILED",
                            error_type="InvalidRequestError",
                            error_message="invalid request",
                        )
                        await session.commit()
                    raise
                except Exception as exc:
                    is_rate_limit = isinstance(exc, (RateLimitError, ProviderUnavailableError)) or "429" in str(exc) or "rate limit" in str(exc).lower()
                    if hasattr(exc, "last_worker_id") and getattr(exc, "last_worker_id"):
                        failed_worker_ids.add(getattr(exc, "last_worker_id"))

                    is_final_failure = attempts > self.settings.DAG_MAX_RETRIES_PER_NODE
                    async with AsyncSessionLocal() as session:
                        await event_logger.finish_attempt(
                            session,
                            task_id=node.id,
                            attempt_number=attempts,
                            status="FAILED" if is_final_failure else "RETRYING",
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:200],
                        )
                        await session.commit()

                    if is_final_failure:
                        await self._persist_failed_node(run_id, node, type(exc).__name__, str(exc)[:200], attempts - 1)
                        raise

                    # Fast 0ms failover on rate limit or provider hiccups so alternative workers pick up immediately
                    if not is_rate_limit:
                        await asyncio.sleep(min(0.25 * (2 ** (attempts - 1)), 1.5))

    async def _invoke_node(
        self,
        request: ChatCompletionRequest,
        node: DAGNode,
        outputs: dict[str, dict[str, Any]],
        *,
        run_id,
        request_id: str,
        policy: str,
        gateway_key: GatewayApiKey | None,
        retry_count: int,
        event_logger: EventLogger,
        failed_worker_ids: set[uuid.UUID] | None = None,
        running_workers: set[uuid.UUID] | None = None,
        running_providers: set[str] | None = None,
        running_credentials: set[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        started = _now()
        prompt = self._build_node_prompt(request, node, outputs)
        node_request = ChatCompletionRequest(
            model=request.model,
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            max_completion_tokens=request.max_completion_tokens,
            top_p=request.top_p,
            tools=request.tools if node.type == "synthesis" else None,
            tool_choice=request.tool_choice if node.type == "synthesis" else None,
            stream=False,
        )
        t_route_0 = time.perf_counter()
        async with self._routing_lock:
            async with AsyncSessionLocal() as session:
                worker, decision = await self._route_node(
                    node_request,
                    session=session,
                    request_id=request_id,
                    policy=policy,
                    gateway_key=gateway_key,
                    execution_run_id=run_id,
                    execution_node_id=node.id,
                    failed_worker_ids=failed_worker_ids,
                    node=node,
                    running_workers=running_workers,
                    running_providers=running_providers,
                    running_credentials=running_credentials,
                )
                route_ms = max(0, int((time.perf_counter() - t_route_0) * 1000))

                routing_snapshot = None
                if hasattr(decision, "to_explanation"):
                    routing_snapshot = decision.to_explanation()
                elif isinstance(decision, dict):
                    routing_snapshot = decision
                elif hasattr(decision, "candidate_workers"):
                    routing_snapshot = {
                        "selected_worker": str(getattr(decision, "selected_worker", worker.id)),
                        "candidate_workers": getattr(decision, "candidate_workers", []),
                        "decision_reason": getattr(decision, "decision_reason", ""),
                        "policy": getattr(decision, "policy", policy),
                    }

                t_tel_0 = time.perf_counter()
                # Record task attempt start and emit TASK_STARTED
                await event_logger.start_attempt(
                    session,
                    task_id=node.id,
                    attempt_number=retry_count + 1,
                    worker_id=worker.id,
                    provider=worker.provider.name,
                    model=worker.model,
                    metadata={
                        "description": node.description,
                        "routing_snapshot": routing_snapshot,
                        "route_duration_ms": route_ms,
                    },
                )
                await session.commit()
                tel_ms = max(0, int((time.perf_counter() - t_tel_0) * 1000))

            if running_workers is not None:
                running_workers.add(worker.id)
            if running_providers is not None and worker.provider:
                running_providers.add((worker.provider.name or "").lower())
            if running_credentials is not None and worker.credential_id:
                running_credentials.add(worker.credential_id)

        from src.services.rate_limiter import upstream_quota_limiter
        node_cred_id = str(worker.credential_id or worker.id)
        node_pname = worker.provider.name if worker.provider else None
        await upstream_quota_limiter.acquire_slot(node_cred_id, node_pname)
        try:
            adapter = registry.get(worker.provider.name)
            try:
                completion = await adapter.create_completion(
                    node_request.model_dump(exclude_none=True),
                    api_key=await get_credential_secret(worker.credential),
                    model=worker.model,
                    request_id=request_id,
                    timeout=self.settings.REQUEST_TIMEOUT_SECONDS,
                )
            except ModelNotFoundError:
                async with AsyncSessionLocal() as session:
                    from src.services.catalog import mark_catalog_stale
                    await mark_catalog_stale(session, worker.provider_id, worker.model)
                    await session.commit()
                raise
            except Exception as exc:
                setattr(exc, "last_worker_id", worker.id)
                raise
            finally:
                upstream_quota_limiter.release_slot(node_cred_id)

            content = self._completion_text(completion.response)
            tool_calls = None
            choices = completion.response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                tool_calls = msg.get("tool_calls")
            completed = _now()
            latency_ms = int((completed - started).total_seconds() * 1000)

            async with AsyncSessionLocal() as session:
                session.add(
                    ExecutionNode(
                        execution_run_id=run_id,
                        node_id=node.id,
                        node_type=node.type,
                        depends_on=node.depends_on,
                        status="success",
                        worker_id=worker.id,
                        provider=worker.provider.name,
                        model=worker.model,
                        started_at=started,
                        first_token_at=None,
                        completed_at=completed,
                        latency_ms=latency_ms,
                        ttft_ms=None,
                        input_tokens=completion.usage.get("input_tokens"),
                        output_tokens=completion.usage.get("output_tokens"),
                        retry_count=retry_count,
                        node_metadata={"description": node.description, "output_ref": node.output_ref},
                    )
                )
                # Auto-recover worker health if it was previously marked degraded/unhealthy
                db_worker = await session.get(Worker, worker.id)
                if db_worker:
                    if db_worker.health_status != "healthy":
                        db_worker.health_status = "healthy"
                    db_worker.last_used_at = completed

                # Record task attempt completion and emit TASK_SUCCEEDED
                output_hash = f"hash_{len(content)}"
                t_tel_1 = time.perf_counter()
                await event_logger.finish_attempt(
                    session,
                    task_id=node.id,
                    attempt_number=retry_count + 1,
                    status="SUCCEEDED",
                    duration_ms=latency_ms,
                    output_hash=output_hash,
                )
                await session.commit()
                tel_ms += max(0, int((time.perf_counter() - t_tel_1) * 1000))

            return {
                "node_id": node.id,
                "type": node.type,
                "content": content,
                "tool_calls": tool_calls,
                "usage": completion.usage,
                "_metrics": {
                    "route_ms": route_ms,
                    "tel_ms": tel_ms,
                    "is_synthesis": (node.type == "synthesis"),
                    "duration_ms": latency_ms,
                },
            }
        finally:
            if running_workers is not None and "worker" in locals():
                running_workers.discard(worker.id)
            if running_providers is not None and "worker" in locals() and worker.provider:
                running_providers.discard((worker.provider.name or "").lower())
            if running_credentials is not None and "worker" in locals() and worker.credential_id:
                running_credentials.discard(worker.credential_id)

    async def _route_node(
        self,
        request: ChatCompletionRequest,
        *,
        session,
        request_id: str,
        policy: str,
        gateway_key: GatewayApiKey | None,
        execution_run_id,
        execution_node_id: str,
        failed_worker_ids: set[uuid.UUID] | None = None,
        node: DAGNode | None = None,
        running_workers: set[uuid.UUID] | None = None,
        running_providers: set[str] | None = None,
        running_credentials: set[uuid.UUID] | None = None,
    ) -> tuple[Worker, Any]:
        if gateway_key and gateway_key.worker_selection_mode == "SPECIFIC_WORKER":
            if not gateway_key.specific_worker_id:
                raise NoWorkerAvailable("API key specific worker is not configured")
            result = await session.execute(
                select(Worker)
                .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
                .where(Worker.id == gateway_key.specific_worker_id)
                .where(Worker.enabled.is_(True))
            )
            worker = result.scalar_one_or_none()
            if worker is None:
                raise NoWorkerAvailable("API key specific worker is unavailable")
            decision = RoutingDecision(
                request_id=request_id,
                candidate_workers=[str(worker.id)],
                selected_worker=str(worker.id),
                decision_reason="DAG node routed by API key specific worker scope",
                routing_version="phase2b-api-key-scope-v1",
                policy=policy,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
            session.add(decision)
            return worker, decision

        if gateway_key and gateway_key.worker_selection_mode == "WORKER_POOL":
            allowed = {__import__("uuid").UUID(item) for item in (gateway_key.allowed_worker_ids or [])}
            worker = await Scheduler().select_worker(
                session,
                request_id=request_id,
                model=request.model,
                allowed_worker_ids=allowed,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
            from src.intelligence.models.routing_decision import RoutingDecisionData
            decision = RoutingDecisionData(
                request_id=request_id,
                selected_worker_id=worker.id,
                selected_provider=worker.provider.name,
                selected_model=worker.model,
                policy=policy,
                routing_version="phase2b-worker-pool-v1",
                decision_reasons=["DAG node routed by API key worker pool scope"],
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
                routing_duration_ms=1.0,
            )
            return worker, decision

        # ── Workload Affinity & Load-Balanced Selection ──────────────
        node_desc = (node.description if node else "").lower()
        node_type = (node.type if node else "").lower()
        node_id = (node.id if node else "").lower()

        is_deep_reasoning = (
            node_type in ("aggregation", "synthesis")
            or any(kw in node_id or kw in node_desc for kw in (
                "database", "schema", "model", "data model", "integration",
                "synthesis", "aggregate", "architect", "auth", "security", "jwt"
            ))
        )
        is_fast_procedural = (
            node_type == "subtask"
            and any(kw in node_id or kw in node_desc for kw in (
                "api", "endpoint", "route", "frontend", "ui", "view", "component",
                "test", "tests", "verification", "doc", "docs", "documentation", "readme", "analytics"
            ))
        )

        node_text = (getattr(node, "description", "") or "") + " " + " ".join([m.content for m in getattr(request, "messages", []) if isinstance(getattr(m, "content", None), str)])
        node_token_mass = max(1, len(node_text) // 4)

        preferred_provider = "gemini" if is_deep_reasoning else ("groq" if is_fast_procedural else None)

        stmt = (
            select(Worker)
            .join(Provider, Worker.provider_id == Provider.id)
            .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
            .where(Provider.enabled.is_(True))
            .where(Worker.enabled.is_(True))
            .where(Worker.health_status != "unhealthy")
        )
        # In DAG orchestration, subtask nodes leverage the entire healthy worker pool.
        # Affinity scoring (_score_worker) assigns each subtask (deep reasoning vs fast procedural)
        # to the optimal provider while enforcing cross-provider fan-out.
        excluded_ids = set(failed_worker_ids or ())
        if excluded_ids:
            stmt = stmt.where(Worker.id.notin_(excluded_ids))

        candidates = list((await session.execute(stmt)).scalars().all())

        # If strict exclusion removed all candidates and failures were temporary, fall back to any enabled worker
        if not candidates and excluded_ids:
            fallback_stmt = (
                select(Worker)
                .join(Provider, Worker.provider_id == Provider.id)
                .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
                .where(Provider.enabled.is_(True))
                .where(Worker.enabled.is_(True))
                .where(Worker.health_status != "unhealthy")
            )
            candidates = list((await session.execute(fallback_stmt)).scalars().all())

        if not candidates:
            raise NoWorkerAvailable("No active healthy worker available in worker pool")

        # Affinity & concurrency scoring function
        def _score_worker(w: Worker) -> float:
            score = 100.0
            pname = (w.provider.name or "").lower()
            mname = (w.model or "").lower()

            # 1. Cross-Provider Fan-Out (Provider Diversity):
            # If a sibling node in this wave is already running on this provider,
            # apply a strong penalty so concurrent nodes stripe across different free providers
            if running_providers and pname in running_providers:
                score -= 350.0

            # 2. Multi-Credential Key Rotation:
            # If the provider must be reused, strongly prefer a different credential key
            if running_credentials and w.credential_id in running_credentials:
                score -= 250.0

            # 2b. Preemptive Upstream Quota Saturation Penalty:
            from src.services.rate_limiter import upstream_quota_limiter
            c_key = str(w.credential_id or w.id)
            util = upstream_quota_limiter.get_utilization(c_key, pname)
            if util.get("is_saturated"):
                score -= 400.0 * (1.0 + util.get("rpm_percent", 0.0))

            # 3. Exact Worker Concurrency Penalty:
            if running_workers and w.id in running_workers:
                score -= 400.0

            # 4. Workload Affinity & Tiered Model Sizing:
            if is_deep_reasoning:
                # Deep reasoning / aggregation / synthesis prefers capable frontier models
                if "gemini" in pname or "claude" in pname or "gpt-4" in mname or "70b" in mname or "pro" in mname:
                    score += 300.0
                elif "flash" in mname:
                    score += 200.0
            elif is_fast_procedural:
                # Fast procedural subtasks prefer ultra-low latency LPU / fast inference
                # BUT only if the token mass is small enough for Groq's TPM limit.
                # DAG node prompts include the full original user message, so they're often large.
                if node_token_mass < 1500:
                    if "cerebras" in pname:
                        score += 350.0  # Ultra-fast 2000 tok/s free tier
                    elif "groq" in pname or "sambanova" in pname:
                        score += 300.0
                    elif "flash" in mname or "mini" in mname:
                        score += 200.0
                else:
                    # Large token mass: prefer high-TPM providers even for procedural tasks
                    if "gemini" in pname or "google" in pname or "flash" in mname:
                        score += 200.0
                    elif "cerebras" in pname:
                        score += 150.0  # 60k TPM, still fine

                # Token-efficient micro-models bonus for subtasks (save tokens & quota)
                if any(tag in mname for tag in ("8b", "mini", "flash-lite", "instant", "small")):
                    score += 150.0

            # 4b. Dynamic Token-Mass Bouncer:
            if node_token_mass >= 1500:
                if "gemini" in pname or "google" in pname or "flash" in mname:
                    score += 350.0  # Steer heavy prompt to 1M TPM context pool
                if "groq" in pname:
                    score -= 300.0  # Protect tight 6,000 TPM limit
            elif 0 < node_token_mass < 1000:
                if "cerebras" in pname or "groq" in pname:
                    score += 250.0  # Ultra-fast procedural output

            # 5. Low-latency & Health bonus
            if "flash" in mname or "instant" in mname:
                score += 50.0
            if w.health_status == "healthy":
                score += 50.0

            # 6. LRU / Load Balancing tie-breaker
            try:
                last_used = w.last_used_at or w.created_at
                if last_used:
                    age_seconds = max(0.0, (time.time() - last_used.timestamp()))
                    score += min(30.0, age_seconds / 2.0)
            except Exception:
                pass

            return score

        selected = max(candidates, key=_score_worker)
        selected.last_used_at = _now()

        from src.intelligence.models.routing_decision import RoutingDecisionData
        reason_affinity = "reasoning" if is_deep_reasoning else ("throughput" if is_fast_procedural else "balanced")
        reason = f"Workload affinity: routed {node_type} '{execution_node_id}' to {selected.provider.name}/{selected.model} (affinity: {reason_affinity})"

        decision = RoutingDecisionData(
            request_id=request_id,
            selected_worker_id=selected.id,
            selected_provider=selected.provider.name,
            selected_model=selected.model,
            policy=policy,
            routing_version="phase2b-affinity-v1",
            decision_reasons=[reason],
            execution_run_id=execution_run_id,
            execution_node_id=execution_node_id,
            routing_duration_ms=1.0,
        )
        session.add(
            RoutingDecision(
                request_id=request_id,
                candidate_workers=[str(w.id) for w in candidates],
                selected_worker=str(selected.id),
                decision_reason=reason,
                routing_version="phase2b-affinity-v1",
                policy=policy,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
        )
        return selected, decision

    async def _persist_skipped_node(self, run_id, node: DAGNode, reason: str, event_logger: EventLogger | None = None) -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                ExecutionNode(
                    execution_run_id=run_id,
                    node_id=node.id,
                    node_type=node.type,
                    depends_on=node.depends_on,
                    status="skipped",
                    error_type=reason,
                    error_message=reason,
                    node_metadata={"description": node.description},
                )
            )
            if event_logger:
                await event_logger.log_event(
                    session,
                    WorkflowEventType.TASK_CANCELLED,
                    task_id=node.id,
                    payload={"reason": reason},
                )
            await session.commit()

    async def _persist_failed_node(self, run_id, node: DAGNode, error_type: str, message: str, retry_count: int) -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                ExecutionNode(
                    execution_run_id=run_id,
                    node_id=node.id,
                    node_type=node.type,
                    depends_on=node.depends_on,
                    status="failed",
                    completed_at=_now(),
                    retry_count=retry_count,
                    error_type=error_type,
                    error_message=message,
                    node_metadata={"description": node.description},
                )
            )
            await session.commit()

    async def _complete_run(
        self,
        run_id,
        started: datetime,
        status: str,
        completed_nodes: int,
        failed_nodes: int,
        planning_ms: int = 0,
        event_logger: EventLogger | None = None,
        outputs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(ExecutionRun, run_id)
            if run:
                run.status = status
                run.completed_at = _now()
                run.completed_nodes = completed_nodes
                run.failed_nodes = failed_nodes
                total_execution_ms = int((run.completed_at - started).total_seconds() * 1000)
                run.total_execution_ms = total_execution_ms

                # Load execution nodes to compute detailed efficiency metrics
                result = await session.execute(
                    select(ExecutionNode).where(ExecutionNode.execution_run_id == run_id)
                )
                nodes = list(result.scalars().all())
                sum_latency = sum(n.latency_ms or 0 for n in nodes)
                worker_ids = {str(n.worker_id) for n in nodes if n.worker_id}
                providers = {n.provider for n in nodes if n.provider}
                in_tokens = sum(n.input_tokens or 0 for n in nodes)
                out_tokens = sum(n.output_tokens or 0 for n in nodes)
                retries = sum(n.retry_count or 0 for n in nodes)

                speedup = round(sum_latency / max(1, total_execution_ms), 2)

                crit_path_res = calculate_critical_path(
                    [{"id": n.node_id, "depends_on": n.depends_on, "latency_ms": n.latency_ms, "status": n.status} for n in nodes]
                )
                crit_path = crit_path_res.critical_path_duration_ms

                run.run_metadata = {
                    **(run.run_metadata or {}),
                    "planning_ms": planning_ms,
                    "total_execution_ms": total_execution_ms,
                    "sum_node_latency_ms": sum_latency,
                    "critical_path_ms": crit_path,
                    "critical_path_nodes": crit_path_res.critical_path_nodes,
                    "parallel_speedup": speedup,
                    "worker_count": len(worker_ids),
                    "provider_count": len(providers),
                    "total_input_tokens": in_tokens,
                    "total_output_tokens": out_tokens,
                    "retry_overhead": retries,
                }

                # Update WorkflowRun historical facts
                wf_run = await session.get(WorkflowRun, run_id)
                if wf_run:
                    wf_status = "COMPLETED" if status == "success" else ("FAILED" if status == "failed" else status.upper())
                    wf_run.status = wf_status
                    wf_run.finished_at = run.completed_at
                    if nodes:
                        final_node = next((n for n in reversed(nodes) if n.node_type == "synthesis"), nodes[-1])
                        wf_run.executed_model = final_node.model
                        wf_run.provider = final_node.provider
                        wf_run.worker_id = final_node.worker_id

                if event_logger:
                    if status in ("success", "partial_success"):
                        await event_logger.log_event(
                            session,
                            WorkflowEventType.WORKFLOW_COMPLETED,
                            payload={"status": status, "completed_nodes": completed_nodes, "failed_nodes": failed_nodes, "total_execution_ms": total_execution_ms},
                        )
                    elif status == "cancelled":
                        await event_logger.log_event(
                            session,
                            WorkflowEventType.WORKFLOW_CANCELLED,
                            payload={"completed_nodes": completed_nodes, "failed_nodes": failed_nodes, "total_execution_ms": total_execution_ms},
                        )
                    else:
                        await event_logger.log_event(
                            session,
                            WorkflowEventType.WORKFLOW_FAILED,
                            payload={"completed_nodes": completed_nodes, "failed_nodes": failed_nodes, "total_execution_ms": total_execution_ms},
                        )

                await session.commit()

                # Calculate measured overheads from node execution metrics
                sched_overhead = 0
                synth_overhead = 0
                tel_overhead = 0
                if outputs:
                    for out in outputs.values():
                        if isinstance(out, dict) and "_metrics" in out:
                            m = out["_metrics"]
                            sched_overhead += int(m.get("route_ms") or 0)
                            tel_overhead += int(m.get("tel_ms") or 0)
                            if m.get("is_synthesis"):
                                synth_overhead += int(m.get("duration_ms") or 0)

                # Calculate and persist WorkflowMetrics with separated metrics
                await AnalyticsService.get_or_calculate_workflow_metrics(
                    session,
                    workflow_run_id=run_id,
                    planning_ms=planning_ms,
                    scheduler_overhead_ms=sched_overhead,
                    synthesis_overhead_ms=synth_overhead,
                    telemetry_overhead_ms=tel_overhead,
                )

    def _build_node_prompt(self, request: ChatCompletionRequest, node: DAGNode, outputs: dict[str, dict[str, Any]]) -> str:
        inputs = [{"node_id": dep, "result": outputs[dep].get("content", "")} for dep in node.depends_on if dep in outputs]
        original = "\n".join(str(message.content) for message in request.messages if message.role == "user")
        if node.type == "subtask":
            return (
                f"### ROLE: Specialized Engineering Worker [{node.id}]\n"
                f"### SCOPE: {node.description}\n\n"
                f"### SYSTEM OBJECTIVE:\n{original}\n\n"
                f"### OUTPUT SPECIFICATION:\n"
                f"- Return ONLY strict, concrete code, schema definitions, typed signatures, and implementation details for '{node.id}'.\n"
                f"- Omit pleasantries, conversational fluff, and generic introductory/concluding explanations.\n"
                f"- Do not implement scopes outside '{node.id}'. Focus purely on high-density production code."
            )
        elif node.type == "aggregation":
            formatted_inputs = []
            for item in inputs:
                content = item["result"].strip()
                formatted_inputs.append(f"#### Upstream Contract [{item['node_id']}]:\n{content}")
            inputs_str = "\n\n".join(formatted_inputs)
            return (
                f"### ROLE: Systems Integration Engineer\n"
                f"### OBJECTIVE: Reconcile subtask deliverables into a unified system specification.\n\n"
                f"### COMPONENT DELIVERABLES:\n{inputs_str}\n\n"
                f"### OUTPUT SPECIFICATION:\n"
                f"- Validate schema compatibility, endpoint routes, and cross-module interfaces.\n"
                f"- Provide a dense, cohesive architecture mapping resolving any dependency conflicts."
            )
        else:
            formatted_inputs = []
            for item in inputs:
                content = item["result"].strip()
                formatted_inputs.append(f"#### Module [{item['node_id']}]:\n{content}")
            inputs_str = "\n\n".join(formatted_inputs)
            return (
                f"### USER OBJECTIVE:\n{original}\n\n"
                f"### VALIDATED MODULE DELIVERABLES:\n{inputs_str}\n\n"
                f"### SYNTHESIS INSTRUCTIONS:\n"
                f"1. Assemble the comprehensive, production-ready solution satisfying the user's objective.\n"
                f"2. Provide explicit file paths, full implementation code for every required file, and terminal commands to run the project.\n"
                f"3. Eliminate redundancies across modules and ensure 100% cohesion."
            )

    def _completion_text(self, response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""
