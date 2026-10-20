import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import HealthEvent, Provider, QuotaSnapshot, RequestMetric, Worker
from src.services.lifecycle import RequestLifecycle

logger = logging.getLogger(__name__)


async def persist_request_metric(
    session: AsyncSession,
    lifecycle: RequestLifecycle,
    *,
    worker: Worker | None,
    requested_model: str | None = None,
    gateway_key: Any | None = None,
    is_cache_hit: bool = False,
    value_saved_override: float | None = None,
) -> None:
    try:
        from src.services.pricing import calculate_request_economics, is_worker_or_credential_paid
        from src.services.budget import BudgetService

        provider_name = None
        if worker:
            if hasattr(worker, "__dict__") and "provider" in worker.__dict__ and worker.__dict__["provider"]:
                provider_name = getattr(worker.__dict__["provider"], "name", None)
            elif getattr(worker, "provider_id", None):
                prov = await session.get(Provider, worker.provider_id)
                provider_name = prov.name if prov else None
        effective_model = (worker.model if worker else None) or requested_model or "auto"
        is_paid = is_worker_or_credential_paid(worker, provider_name) if not is_cache_hit else False

        econ = calculate_request_economics(
            input_tokens=lifecycle.input_tokens,
            output_tokens=lifecycle.output_tokens,
            total_tokens=lifecycle.total_tokens,
            provider=provider_name,
            model=effective_model,
            is_paid=is_paid,
            is_cache_hit=is_cache_hit,
        )

        cost_usd = econ.get("actual_cost_usd", 0.0) if not is_cache_hit else 0.0
        val_saved = value_saved_override if value_saved_override is not None else econ.get("saved_usd", 0.0)

        snapshot = lifecycle.snapshot()
        session.add(
            RequestMetric(
                request_id=lifecycle.request_id,
                worker_id=worker.id if worker else None,
                provider=provider_name,
                model=effective_model,
                cost_usd=cost_usd,
                value_saved_usd=val_saved,
                is_cache_hit=is_cache_hit,
                is_paid_key=is_paid,
                gateway_key_id=gateway_key.id if gateway_key and hasattr(gateway_key, "id") else None,
                **snapshot,
            )
        )
        await session.commit()

        # Update key spend & saved counters
        if gateway_key and hasattr(gateway_key, "id"):
            await BudgetService.record_key_spend(
                session, gateway_key.id, actual_cost_usd=cost_usd, value_saved_usd=val_saved
            )
    except Exception:
        await session.rollback()
        logger.exception("metrics persistence failed", extra={"request_id": lifecycle.request_id})


async def persist_quota_snapshot(session: AsyncSession, *, worker_id: UUID, quota: dict[str, Any] | None) -> None:
    if not quota:
        return
    try:
        session.add(QuotaSnapshot(worker_id=worker_id, **quota))
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("quota persistence failed", extra={"worker_id": str(worker_id)})


async def persist_health_event(
    session: AsyncSession,
    *,
    worker: Worker,
    new_status: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    previous = worker.health_status
    worker.health_status = new_status
    session.add(
        HealthEvent(
            worker_id=worker.id,
            previous_status=previous,
            new_status=new_status,
            reason=reason,
            event_metadata=metadata or {},
        )
    )
    await session.commit()
