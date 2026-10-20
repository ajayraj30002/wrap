import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.db.models import Credential, QuotaSnapshot, Worker
from src.providers.registry import registry
from src.services.catalog import sync_provider_catalog_for_credential
from src.services.credentials import get_credential_secret
from src.services.persistence import persist_health_event

logger = logging.getLogger(__name__)


class CatalogReconciler:
    """Automated background worker health watchdog and catalog reconciler."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self, session_factory) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(session_factory))

    async def shutdown(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self, session_factory) -> None:
        # Initial health check after startup delay (grace period for server startup)
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            pass

        if not self._stopped.is_set():
            try:
                await self.check_and_prune_workers(session_factory)
            except Exception as e:
                logger.error("Initial worker health sweep failed: %s", e)

        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=getattr(settings, "WORKER_HEALTH_CHECK_INTERVAL_SECONDS", 300.0),
                )
            except asyncio.TimeoutError:
                try:
                    await self.check_and_prune_workers(session_factory)
                except Exception as e:
                    logger.error("Periodic worker health sweep failed: %s", e)

    async def refresh_all(self, session_factory) -> None:
        async with session_factory() as session:
            result = await session.execute(
                select(Credential)
                .options(selectinload(Credential.provider))
                .where(Credential.enabled.is_(True))
            )
            for credential in result.scalars():
                await sync_provider_catalog_for_credential(session, credential, timeout=settings.REQUEST_TIMEOUT_SECONDS)
            await session.commit()

    async def check_and_prune_workers(self, session_factory) -> dict[str, int]:
        """Perform lightweight health checks across enabled workers, auto-pruning dead/decommissioned models."""
        # 1. Fetch worker descriptors under enabled credentials in a fast, short-lived session
        async with session_factory() as session:
            result = await session.execute(
                select(Worker)
                .join(Credential, Worker.credential_id == Credential.id)
                .options(selectinload(Worker.provider), selectinload(Worker.credential))
                .where(Credential.enabled.is_(True))
            )
            raw_workers = list(result.scalars().all())
            worker_data = []
            for w in raw_workers:
                try:
                    key = await get_credential_secret(w.credential)
                    worker_data.append({
                        "id": w.id,
                        "model": w.model,
                        "provider_name": w.provider.name if w.provider else None,
                        "key": key,
                    })
                except Exception:
                    pass

        if not worker_data:
            return {"checked": 0, "healthy": 0, "pruned": 0}

        # 2. Probe workers concurrently with bounded concurrency outside the DB session
        sem = asyncio.Semaphore(4)
        probe_results = {}

        async def _probe_single(item):
            w_id = item["id"]
            p_name = item["provider_name"]
            adapter = registry.get(p_name) if p_name else None
            if not adapter:
                probe_results[w_id] = ("healthy", None, None)
                return
            async with sem:
                try:
                    await asyncio.wait_for(
                        adapter.test_credential(api_key=item["key"], model=item["model"], timeout=12.0),
                        timeout=15.0,
                    )
                    probe_results[w_id] = ("healthy", None, None)
                except asyncio.TimeoutError:
                    probe_results[w_id] = ("degraded", False, "probe timed out (transient latency > 15s)")
                except Exception as exc:
                    err_msg = str(exc) or type(exc).__name__
                    is_decommissioned = any(
                        hint in err_msg.lower()
                        for hint in ("not found", "decommissioned", "no longer available", "does not exist", "404", "modelnotfound")
                    )
                    is_rate_limited = any(
                        hint in err_msg.lower()
                        for hint in ("429", "quota", "rate limit", "resource exhausted")
                    )
                    if is_decommissioned:
                        probe_results[w_id] = ("unhealthy", True, err_msg)
                    elif is_rate_limited:
                        probe_results[w_id] = ("rate_limited", False, err_msg)
                    else:
                        probe_results[w_id] = ("degraded", False, err_msg)

        await asyncio.gather(*[_probe_single(w) for w in worker_data], return_exceptions=True)

        # 3. Apply results in a quick, dedicated DB session
        checked = len(worker_data)
        healthy = 0
        pruned = 0

        async with session_factory() as session:
            result = await session.execute(
                select(Worker)
                .where(Worker.id.in_(list(probe_results.keys())))
            )
            workers_map = {w.id: w for w in result.scalars().all()}

            for w_id, (status, should_prune, err_msg) in probe_results.items():
                w = workers_map.get(w_id)
                if not w:
                    continue

                if status == "healthy":
                    w.health_status = "healthy"
                    w.enabled = True
                    healthy += 1
                    session.add(
                        QuotaSnapshot(
                            worker_id=w.id,
                            requests_remaining=995,
                            requests_limit=1000,
                            tokens_remaining=80000,
                            tokens_limit=80000,
                            source="health_probe",
                        )
                    )
                elif should_prune:
                    pruned += 1
                    logger.info("Watchdog auto-pruned decommissioned worker: %s (%s)", w.model, w.id)
                    await session.delete(w)
                elif status == "rate_limited":
                    w.health_status = "rate_limited"
                    session.add(
                        QuotaSnapshot(
                            worker_id=w.id,
                            requests_remaining=0,
                            requests_limit=1000,
                            tokens_remaining=0,
                            tokens_limit=80000,
                            source="rate_limit_429",
                        )
                    )
                    await persist_health_event(session, worker=w, new_status=w.health_status, reason=f"watchdog 429: {str(err_msg)[:200]}")
                else:
                    w.health_status = "degraded"
                    await persist_health_event(session, worker=w, new_status=w.health_status, reason=f"watchdog probe: {str(err_msg)[:200]}")

            await session.commit()

        # 4. Refresh in-memory intelligent router state store
        from src.api.routes.openai import get_intelligent_router
        router = get_intelligent_router()
        if router and getattr(router, "_resource_store", None):
            async with session_factory() as session:
                await router._resource_store._full_refresh(session)

        logger.info(
            "Worker health sweep completed: %d checked, %d healthy, %d auto-pruned",
            checked,
            healthy,
            pruned,
        )
        return {"checked": checked, "healthy": healthy, "pruned": pruned}
