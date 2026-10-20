"""IntelligentRouter — orchestrates the Phase 2A routing pipeline.

This is the single entry point that replaces the Phase 1 Scheduler.
It coordinates: RequestAnalyzer → ResourceStateStore → CandidateSelector
→ HardEligibilityFilter → AllocationOptimizer → RoutingDecision.

The router NEVER makes provider API calls. After producing a
RoutingDecision, execution is handed to the existing ProviderAdapter
by the calling code in openai.py.

Fallback: If intelligent routing fails for any reason (missing state,
exception, no candidates), the router falls back to Phase 1 LRU
deterministic selection using the existing Scheduler.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import RoutingDecision, Worker
from src.intelligence.analysis.request_analyzer import RequestAnalyzer
from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.models.routing_decision import ROUTING_VERSION, RoutingDecisionData
from src.intelligence.models.scoring import RejectedCandidate, ScoredCandidate
from src.intelligence.resources.capability_engine import CapabilityEngine
from src.intelligence.resources.performance_engine import PerformanceEngine
from src.intelligence.resources.quota_manager import QuotaManager
from src.intelligence.resources.resource_state_store import ResourceStateStore
from src.intelligence.resources.worker_state import WorkerState
from src.intelligence.scheduling.allocation_optimizer import AllocationOptimizer
from src.intelligence.scheduling.candidate_selector import CandidateSelector
from src.intelligence.scheduling.hard_constraint_filter import HardEligibilityFilter
from src.intelligence.scheduling.policy_engine import DEFAULT_POLICY, PolicyEngine
from src.intelligence.scheduling.routing_explanation import RoutingExplanation
from src.scheduler import NoWorkerAvailable, Scheduler
from src.schemas.openai import ChatCompletionRequest

logger = logging.getLogger(__name__)


class IntelligentRouter:
    """Phase 2A intelligent routing pipeline orchestrator.

    Replaces Scheduler.select_worker() in the /v1/chat/completions path.
    """

    def __init__(self, resource_store: ResourceStateStore) -> None:
        self._resource_store = resource_store
        self._analyzer = RequestAnalyzer()
        self._selector = CandidateSelector()
        self._quota_manager = QuotaManager()
        self._filter = HardEligibilityFilter(quota_manager=self._quota_manager)
        self._capability = CapabilityEngine()
        self._performance = PerformanceEngine()
        self._policy_engine = PolicyEngine()
        self._optimizer = AllocationOptimizer(
            capability_engine=self._capability,
            performance_engine=self._performance,
            quota_manager=self._quota_manager,
        )
        self._explanation = RoutingExplanation()
        self._fallback_scheduler = Scheduler()

    async def route(
        self,
        request: ChatCompletionRequest,
        *,
        session: AsyncSession,
        request_id: str,
        policy: str | None = None,
        execution_run_id: uuid.UUID | None = None,
        execution_node_id: str | None = None,
    ) -> tuple[Worker, RoutingDecisionData]:
        """Execute the intelligent routing pipeline.

        Returns (selected Worker ORM object, RoutingDecisionData).
        Raises NoWorkerAvailable if no worker can serve the request.

        The returned Worker has its provider and credential eagerly
        loaded so the caller can immediately use ProviderAdapter.
        """
        start_time = time.monotonic()
        policy_name = self._policy_engine.get_policy_name(policy)

        # ── Fallback if resource store is not initialized ──────────
        if not self._resource_store.initialized:
            logger.warning("ResourceStateStore not initialized, falling back to deterministic routing")
            return await self._deterministic_fallback(
                session,
                request_id=request_id,
                model=request.model,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )

        try:
            return await self._intelligent_route(
                request,
                session=session,
                request_id=request_id,
                policy=policy_name,
                start_time=start_time,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
        except NoWorkerAvailable:
            raise
        except Exception:
            logger.exception("Intelligent routing failed, falling back to deterministic", extra={"request_id": request_id})
            return await self._deterministic_fallback(
                session,
                request_id=request_id,
                model=request.model,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )

    async def _intelligent_route(
        self,
        request: ChatCompletionRequest,
        *,
        session: AsyncSession,
        request_id: str,
        policy: str,
        start_time: float,
        execution_run_id: uuid.UUID | None = None,
        execution_node_id: str | None = None,
    ) -> tuple[Worker, RoutingDecisionData]:
        """The core Phase 2A pipeline."""

        # 1. Analyze request → RequestProfile
        profile = self._analyzer.analyze(request, request_id=request_id)

        # 2. Get runtime worker state snapshot
        workers = self._resource_store.snapshot()
        if not workers:
            async with self._resource_store._lock:
                await self._resource_store._full_refresh(session)
            workers = self._resource_store.snapshot()

        # 3. Generate candidates
        candidates = self._selector.select(profile, workers)

        # 4. Hard eligibility filtering
        filter_result = self._filter.filter(profile, candidates)

        # 5. Check if any eligible workers remain (refresh once if empty to avoid stale snapshot)
        if not filter_result.eligible:
            async with self._resource_store._lock:
                await self._resource_store._full_refresh(session)
            workers = self._resource_store.snapshot()
            candidates = self._selector.select(profile, workers)
            filter_result = self._filter.filter(profile, candidates)

        if not filter_result.eligible:
            decision = self._build_empty_decision(
                request_id=request_id,
                policy=policy,
                candidates=candidates,
                rejected=filter_result.rejected,
                start_time=start_time,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
            await self._persist_decision(session, decision)
            raise NoWorkerAvailable(
                f"No eligible worker for model={profile.model_requested} "
                f"({len(filter_result.rejected)} rejected by constraints)"
            )


        # 6. Score and select via multi-objective allocation
        weights = self._policy_engine.get_weights(policy)
        selected, all_scored = self._optimizer.score_and_select(
            profile, filter_result.eligible, weights
        )

        if selected is None:
            decision = self._build_empty_decision(
                request_id=request_id,
                policy=policy,
                candidates=candidates,
                rejected=filter_result.rejected,
                start_time=start_time,
                execution_run_id=execution_run_id,
                execution_node_id=execution_node_id,
            )
            await self._persist_decision(session, decision)
            raise NoWorkerAvailable("AllocationOptimizer returned no selection")

        # 7. Build explanation
        reasons = self._explanation.build_reasons(
            profile, selected, all_scored, filter_result.rejected, policy
        )

        # 8. Build routing decision
        routing_duration = (time.monotonic() - start_time) * 1000.0  # ms

        decision = RoutingDecisionData(
            request_id=request_id,
            selected_worker_id=selected.worker_id,
            selected_provider=selected.provider,
            selected_model=selected.model,
            all_candidates=[w.worker_id for w in candidates],
            eligible_candidates=all_scored,
            rejected_candidates=filter_result.rejected,
            policy=policy,
            routing_version=ROUTING_VERSION,
            predicted_ttft_ms=selected.prediction.predicted_ttft_ms,
            predicted_latency_ms=selected.prediction.predicted_latency_ms,
            prediction_confidence=selected.prediction.confidence,
            scores=selected.scores,
            decision_reasons=reasons,
            routing_duration_ms=routing_duration,
            execution_run_id=execution_run_id,
            execution_node_id=execution_node_id,
        )

        # 9. Persist routing decision
        await self._persist_decision(session, decision)

        # 10. Load the actual Worker ORM object with relationships
        from sqlalchemy import select as sa_select
        result = await session.execute(
            sa_select(Worker)
            .options(selectinload(Worker.provider), selectinload(Worker.credential))
            .where(Worker.id == selected.worker_id)
        )
        worker = result.scalar_one_or_none()
        if worker is None:
            raise NoWorkerAvailable(f"Selected worker {selected.worker_id} not found in database")

        # Update last_used_at
        from src.db.models import utcnow
        worker.last_used_at = utcnow()
        await session.flush()

        # Track active request in resource store
        self._resource_store.on_request_start(selected.worker_id)

        logger.info(
            "intelligent routing decision",
            extra={
                "request_id": request_id,
                "routing_version": ROUTING_VERSION,
                "routing_policy": policy,
                "candidate_count": len(candidates),
                "eligible_count": len(filter_result.eligible),
                "rejected_count": len(filter_result.rejected),
                "selected_worker_id": str(selected.worker_id),
                "predicted_latency_ms": int(selected.prediction.predicted_latency_ms or 0),
                "routing_duration_ms": round(routing_duration, 2),
            },
        )

        return worker, decision

    async def _deterministic_fallback(
        self,
        session: AsyncSession,
        *,
        request_id: str,
        model: str,
        execution_run_id: uuid.UUID | None = None,
        execution_node_id: str | None = None,
    ) -> tuple[Worker, RoutingDecisionData]:
        """Fall back to Phase 1 LRU deterministic routing."""
        worker = await self._fallback_scheduler.select_worker(
            session,
            request_id=request_id,
            model=model,
            execution_run_id=execution_run_id,
            execution_node_id=execution_node_id,
        )

        decision = RoutingDecisionData(
            request_id=request_id,
            selected_worker_id=worker.id,
            selected_provider=worker.provider.name,
            selected_model=worker.model,
            policy="fallback",
            routing_version="phase1-deterministic-v1",
            decision_reasons=["fallback to deterministic LRU routing"],
            execution_run_id=execution_run_id,
            execution_node_id=execution_node_id,
        )

        return worker, decision

    def _build_empty_decision(
        self,
        *,
        request_id: str,
        policy: str,
        candidates: list[WorkerState],
        rejected: list[RejectedCandidate],
        start_time: float,
        execution_run_id: uuid.UUID | None = None,
        execution_node_id: str | None = None,
    ) -> RoutingDecisionData:
        routing_duration = (time.monotonic() - start_time) * 1000.0
        return RoutingDecisionData(
            request_id=request_id,
            all_candidates=[w.worker_id for w in candidates],
            rejected_candidates=rejected,
            policy=policy,
            routing_version=ROUTING_VERSION,
            decision_reasons=[
                f"no eligible worker ({len(rejected)} rejected by constraints)",
                *[f"  {r.provider}/{r.model}: {r.reason}" for r in rejected[:5]],
            ],
            routing_duration_ms=routing_duration,
            execution_run_id=execution_run_id,
            execution_node_id=execution_node_id,
        )

    async def _persist_decision(
        self, session: AsyncSession, decision: RoutingDecisionData
    ) -> None:
        """Persist the routing decision to the database."""
        try:
            db_fields = decision.to_db_fields()
            session.add(RoutingDecision(**db_fields))
            await session.flush()
        except Exception:
            logger.exception(
                "Failed to persist routing decision",
                extra={"request_id": decision.request_id},
            )
