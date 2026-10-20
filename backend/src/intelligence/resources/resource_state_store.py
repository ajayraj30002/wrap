"""ResourceStateStore — in-memory runtime snapshot of all worker resources.

Update strategy:
1. Bootstrap: Full load from PostgreSQL on startup.
2. Event-driven: Application hooks push changes on health, quota,
   request completion, and worker configuration changes.
3. Periodic reconciliation: Full refresh every 60s to recover from
   missed events, process restarts, or unexpected state drift.

PostgreSQL remains the authoritative historical persistence layer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import HealthEvent, ProviderModel, QuotaSnapshot, RequestMetric, Worker
from src.intelligence.resources.worker_state import WorkerState

logger = logging.getLogger(__name__)

# Reconciliation interval in seconds
_RECONCILIATION_INTERVAL = 60.0

# Rolling window for performance aggregation (number of recent requests)
_PERF_WINDOW_SIZE = 100


class ResourceStateStore:
    """Thread-safe in-memory store of worker runtime state.

    Designed for concurrent access from the async request pipeline.
    State is eventually consistent with PostgreSQL.
    """

    def __init__(self) -> None:
        self._workers: dict[uuid.UUID, WorkerState] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._reconciliation_task: asyncio.Task[None] | None = None

    @property
    def initialized(self) -> bool:
        return self._initialized

    def snapshot(self) -> list[WorkerState]:
        """Return a snapshot of all current worker states.

        This is called on every routing decision. It returns a shallow
        copy of the list (not deep copies of WorkerState) for speed.
        The routing pipeline should treat these as read-only.
        """
        return list(self._workers.values())

    def get_worker(self, worker_id: uuid.UUID) -> WorkerState | None:
        return self._workers.get(worker_id)

    # ── Bootstrap ──────────────────────────────────────────────────

    async def initialize(self, session: AsyncSession) -> None:
        """Full load from PostgreSQL. Called once at startup."""
        async with self._lock:
            await self._full_refresh(session)
            self._initialized = True
        logger.info("ResourceStateStore initialized", extra={"worker_count": len(self._workers)})

    async def _full_refresh(self, session: AsyncSession) -> None:
        """Rebuild the entire in-memory state from PostgreSQL."""
        # Load all workers with relationships
        result = await session.execute(
            select(Worker)
            .outerjoin(ProviderModel, Worker.provider_model_id == ProviderModel.id)
            .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
            .where((Worker.provider_model_id.is_(None)) | (ProviderModel.status.in_(["ACTIVE", "UNKNOWN"])))
        )
        workers = list(result.scalars().all())

        new_states: dict[uuid.UUID, WorkerState] = {}
        for w in workers:
            caps = dict(w.capabilities or {})
            if w.provider_model:
                caps.setdefault("tool_calling", w.provider_model.tool_calling)
                caps.setdefault("streaming", w.provider_model.streaming)
                caps.setdefault("structured_output", w.provider_model.structured_output)
                caps.setdefault("reasoning", w.provider_model.reasoning)
                if w.provider_model.context_window is not None:
                    caps.setdefault("context_window", w.provider_model.context_window)
                if w.provider_model.max_output_tokens is not None:
                    caps.setdefault("max_output_tokens", w.provider_model.max_output_tokens)
            state = WorkerState(
                worker_id=w.id,
                provider=w.provider.name,
                credential_id=w.credential_id,
                model=w.model,
                worker_type=w.worker_type,
                enabled=w.enabled,
                healthy=w.health_status in ("healthy", "unknown", "degraded"),
                health_status=w.health_status,
                capabilities=caps,
                last_used_at=w.last_used_at,
            )
            # Preserve active_requests from existing state if available
            existing = self._workers.get(w.id)
            if existing:
                state.active_requests = existing.active_requests
            new_states[w.id] = state

        # Load performance metrics per worker
        await self._load_performance(session, new_states)

        # Load latest quota per worker
        await self._load_quota(session, new_states)

        self._workers = new_states

    async def _load_performance(
        self, session: AsyncSession, states: dict[uuid.UUID, WorkerState]
    ) -> None:
        """Aggregate recent request metrics per worker."""
        for worker_id, state in states.items():
            # Get recent successful requests for this worker
            result = await session.execute(
                select(
                    func.count(RequestMetric.id).label("total"),
                    func.avg(RequestMetric.total_latency_ms).label("avg_latency"),
                    func.avg(RequestMetric.ttft_ms).label("avg_ttft"),
                    func.avg(RequestMetric.output_tokens_per_second).label("avg_tps"),
                    func.sum(case((RequestMetric.status == "success", 1), else_=0)).label("successes"),
                ).where(RequestMetric.worker_id == worker_id)
            )
            row = result.one()

            state.sample_count = row.total or 0
            if state.sample_count > 0:
                state.latency_p50_ms = float(row.avg_latency) if row.avg_latency else None
                state.ttft_p50_ms = float(row.avg_ttft) if row.avg_ttft else None
                state.tps_p50 = float(row.avg_tps) if row.avg_tps else None
                state.success_rate = (row.successes / state.sample_count) if state.sample_count > 0 else 1.0
                state.error_rate = 1.0 - state.success_rate

            # Get p95 latency if sufficient samples
            if state.sample_count >= 5:
                try:
                    p95_result = await session.execute(
                        select(
                            func.percentile_cont(0.95).within_group(RequestMetric.total_latency_ms).label("p95_lat"),
                            func.percentile_cont(0.95).within_group(RequestMetric.ttft_ms).label("p95_ttft"),
                        ).where(
                            RequestMetric.worker_id == worker_id,
                            RequestMetric.status == "success",
                        )
                    )
                    p95_row = p95_result.one()
                    state.latency_p95_ms = float(p95_row.p95_lat) if p95_row.p95_lat else None
                    state.ttft_p95_ms = float(p95_row.p95_ttft) if p95_row.p95_ttft else None
                except Exception:
                    # percentile_cont may not be available in SQLite test env
                    pass

    async def _load_quota(
        self, session: AsyncSession, states: dict[uuid.UUID, WorkerState]
    ) -> None:
        """Load the latest quota snapshot per worker."""
        for worker_id, state in states.items():
            result = await session.execute(
                select(QuotaSnapshot)
                .where(QuotaSnapshot.worker_id == worker_id)
                .order_by(desc(QuotaSnapshot.timestamp))
                .limit(1)
            )
            quota = result.scalar_one_or_none()
            if quota:
                state.quota_requests_remaining = quota.requests_remaining
                state.quota_requests_limit = quota.requests_limit
                state.quota_tokens_remaining = quota.tokens_remaining
                state.quota_tokens_limit = quota.tokens_limit
                state.quota_reset_at = quota.reset_at
                state.quota_source = quota.source

    # ── Event-driven updates ───────────────────────────────────────

    def on_request_start(self, worker_id: uuid.UUID) -> None:
        """Increment active request count when a request starts."""
        state = self._workers.get(worker_id)
        if state:
            state.active_requests += 1

    def on_request_complete(
        self,
        worker_id: uuid.UUID,
        *,
        latency_ms: int | None = None,
        ttft_ms: int | None = None,
        tps: int | None = None,
        success: bool = True,
        quota: dict[str, Any] | None = None,
    ) -> None:
        """Update worker state after a request completes.

        This is an event-driven update — no database query needed.
        Uses exponentially-weighted moving average (EWMA) for metrics
        to smoothly incorporate new observations.
        """
        state = self._workers.get(worker_id)
        if not state:
            return

        state.active_requests = max(0, state.active_requests - 1)
        state.last_used_at = datetime.now(timezone.utc)
        state.sample_count += 1

        # EWMA smoothing factor — recent observations weighted more
        alpha = min(0.3, 2.0 / (state.sample_count + 1))

        if latency_ms is not None:
            if state.latency_p50_ms is not None:
                state.latency_p50_ms = state.latency_p50_ms * (1 - alpha) + latency_ms * alpha
            else:
                state.latency_p50_ms = float(latency_ms)

        if ttft_ms is not None:
            if state.ttft_p50_ms is not None:
                state.ttft_p50_ms = state.ttft_p50_ms * (1 - alpha) + ttft_ms * alpha
            else:
                state.ttft_p50_ms = float(ttft_ms)

        if tps is not None:
            if state.tps_p50 is not None:
                state.tps_p50 = state.tps_p50 * (1 - alpha) + tps * alpha
            else:
                state.tps_p50 = float(tps)

        # Update success/error rates with EWMA
        outcome = 1.0 if success else 0.0
        state.success_rate = state.success_rate * (1 - alpha) + outcome * alpha
        state.error_rate = 1.0 - state.success_rate

        # Update consecutive failures and automated health transitions
        health_transition: tuple[str, str] | None = None
        if success:
            state.consecutive_failures = 0
            if state.health_status in ("degraded", "unhealthy"):
                prev = state.health_status
                self.on_health_change(worker_id, new_status="healthy")
                health_transition = (prev, "healthy")
        else:
            state.consecutive_failures += 1
            if state.consecutive_failures >= 3 and state.health_status not in ("degraded", "unhealthy"):
                prev = state.health_status
                self.on_health_change(worker_id, new_status="degraded")
                health_transition = (prev, "degraded")

        # Update quota if provided
        if quota:
            state.quota_requests_remaining = quota.get("requests_remaining")
            state.quota_requests_limit = quota.get("requests_limit")
            state.quota_tokens_remaining = quota.get("tokens_remaining")
            state.quota_tokens_limit = quota.get("tokens_limit")
            state.quota_reset_at = quota.get("reset_at")
            source = quota.get("source", "unknown")
            if source and source != "unknown":
                state.quota_source = source

        return health_transition

    def on_health_change(self, worker_id: uuid.UUID, *, new_status: str) -> None:
        """Update worker health status."""
        state = self._workers.get(worker_id)
        if state:
            state.health_status = new_status
            state.healthy = new_status in ("healthy", "unknown")
            state.last_health_check_at = datetime.now(timezone.utc)

    def on_worker_config_change(
        self,
        worker_id: uuid.UUID,
        *,
        enabled: bool | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> None:
        """Update worker configuration (enable/disable, capabilities)."""
        state = self._workers.get(worker_id)
        if state:
            if enabled is not None:
                state.enabled = enabled
            if capabilities is not None:
                state.capabilities = capabilities

    # ── Periodic reconciliation ────────────────────────────────────

    def start_reconciliation(self, session_factory: Any) -> None:
        """Start the background reconciliation loop."""
        if self._reconciliation_task is None or self._reconciliation_task.done():
            self._reconciliation_task = asyncio.create_task(
                self._reconciliation_loop(session_factory)
            )

    async def _reconciliation_loop(self, session_factory: Any) -> None:
        """Periodic full refresh to recover from missed events."""
        while True:
            await asyncio.sleep(_RECONCILIATION_INTERVAL)
            try:
                async with session_factory() as session:
                    async with self._lock:
                        await self._full_refresh(session)
                logger.debug("ResourceStateStore reconciliation complete", extra={"worker_count": len(self._workers)})
            except Exception:
                logger.exception("ResourceStateStore reconciliation failed")

    async def shutdown(self) -> None:
        """Cancel the reconciliation task."""
        if self._reconciliation_task and not self._reconciliation_task.done():
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
