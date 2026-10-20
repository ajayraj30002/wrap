import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import Settings, get_settings
from src.core.security import require_wrap_api_key
from src.db.models import GatewayApiKey, Provider, ProviderModel, RoutingDecision, Worker
from src.db.session import get_session
from src.providers.base import ProviderError
from src.providers.registry import registry
from src.scheduler import NoWorkerAvailable
from src.orchestration.analyzer import TaskAnalyzer
from src.orchestration.executor import DAGExecutor
from src.schemas.openai import ChatCompletionRequest, ChatMessage, ModelCard, ModelsResponse
from src.services.credentials import get_credential_secret
from src.services.lifecycle import RequestLifecycle
from src.services.persistence import persist_health_event, persist_quota_snapshot, persist_request_metric
from src.analytics.enums import WorkflowEventType
from src.analytics.event_logger import EventLogger
from src.analytics.models import WorkflowRun
from src.analytics.service import AnalyticsService
from src.db.models import utcnow
from src.services.cache import gateway_cache
from src.services.rate_limiter import gateway_rate_limiter, upstream_quota_limiter
from src.services.model_groups import is_virtual_group, get_group, model_matches_group, expand_group_models
from src.services.budget import BudgetService
from src.services.pricing import is_worker_or_credential_paid

# Phase 2A: Lazy-initialized intelligent router (set up during app startup)
_intelligent_router = None


def get_intelligent_router():
    """Get the global IntelligentRouter instance."""
    global _intelligent_router
    if _intelligent_router is None:
        from src.intelligence.resources.resource_state_store import ResourceStateStore
        from src.intelligence.router import IntelligentRouter
        # Create with an uninitialized store — will fall back to deterministic
        _intelligent_router = IntelligentRouter(ResourceStateStore())
    return _intelligent_router


def set_intelligent_router(router_instance) -> None:
    """Set the global IntelligentRouter (called from app startup)."""
    global _intelligent_router
    _intelligent_router = router_instance


router = APIRouter()
logger = logging.getLogger(__name__)
task_analyzer = TaskAnalyzer()


@router.get("/models", response_model=ModelsResponse)
@router.get("/openai/models", response_model=ModelsResponse)
@router.get("/openai/deployments", response_model=ModelsResponse)
async def list_models(
    api_version: str | None = None,
    gateway_key: GatewayApiKey = Depends(require_wrap_api_key),
    session: AsyncSession = Depends(get_session),
) -> ModelsResponse:
    statement = (
        select(Worker)
        .outerjoin(ProviderModel, Worker.provider_model_id == ProviderModel.id)
        .options(selectinload(Worker.provider), selectinload(Worker.provider_model))
        .where(Worker.enabled.is_(True))
        .where(Worker.health_status.in_(["healthy", "unknown"]))
        .where((Worker.provider_model_id.is_(None)) | (ProviderModel.status.in_(["ACTIVE", "UNKNOWN"])))
        .order_by(Worker.model)
    )
    statement = _apply_api_key_scope(statement, gateway_key)
    result = await session.execute(statement)
    cards = [
        ModelCard(id=worker.model, owned_by=worker.provider.name)
        for worker in result.scalars().unique().all()
    ]
    if cards:
        if gateway_key.worker_selection_mode != "WORKER_POOL":
            standard_aliases = [
                "auto",
                "gpt-4o",
                "gpt-4o-mini",
                "claude-3-5-sonnet",
                "claude-3-7-sonnet",
                "deepseek-r1",
                "deepseek-v3",
                "gemini-flash-lite-latest",
                "gemini-3.7-flash",
                "gemini-3.5-flash",
                "qwen/qwen3.8-27b",
            ]
            for alias in reversed(standard_aliases):
                if not any(c.id == alias for c in cards):
                    cards.insert(0, ModelCard(id=alias, owned_by="wrap"))
        else:
            if not any(c.id == "auto" for c in cards):
                cards.insert(0, ModelCard(id="auto", owned_by="wrap"))

        from src.services.model_groups import list_virtual_groups, model_matches_group
        for group in list_virtual_groups():
            if gateway_key.worker_selection_mode == "MODEL_GROUPS":
                allowed_g = gateway_key.allowed_model_groups or []
                if group["id"] not in allowed_g and group["id"].lower() not in [g.lower() for g in allowed_g]:
                    continue
            if any(model_matches_group(c.id, group["models"]) for c in cards):
                cards.append(ModelCard(id=group["id"], owned_by="wrap-virtual-tier"))
    return ModelsResponse(data=cards)


def _openai_http_error(message: str, error_type: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"message": message, "type": error_type}})


async def _verify_gateway_key_access(gateway_key: GatewayApiKey, requested_model: str, session: AsyncSession) -> None:
    from src.services.model_groups import is_virtual_group, get_group, model_matches_group

    mode = gateway_key.worker_selection_mode or "AUTO"
    if mode == "AUTO":
        return

    if mode == "SPECIFIC_WORKER":
        if not gateway_key.specific_worker_id:
            raise _openai_http_error("API key is pinned to a missing worker", "invalid_request_error", 400)
        result = await session.execute(
            select(Worker)
            .where(Worker.id == gateway_key.specific_worker_id)
            .where(Worker.enabled.is_(True))
        )
        worker = result.scalar_one_or_none()
        if worker is None:
            raise _openai_http_error("Pinned worker for this API key is disabled or not found", "model_not_found", 404)
        if requested_model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent") and worker.model != requested_model:
            raise _openai_http_error(
                f"API key is pinned to model '{worker.model}' and is not authorized to access '{requested_model}'.",
                "permission_denied",
                403,
            )
        return

    if mode == "MODEL_GROUPS":
        allowed_groups_raw = getattr(gateway_key, "allowed_model_groups", None) or []
        if not allowed_groups_raw:
            raise _openai_http_error("API key has no permitted virtual tiers configured.", "permission_denied", 403)
        if requested_model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
            if is_virtual_group(requested_model):
                if requested_model not in allowed_groups_raw and requested_model.lower() not in [g.lower() for g in allowed_groups_raw]:
                    raise _openai_http_error(
                        f"API key is not authorized for virtual tier '{requested_model}'. Permitted tiers: {allowed_groups_raw}",
                        "permission_denied",
                        403,
                    )
            else:
                matched_group = False
                for g_id in allowed_groups_raw:
                    g = get_group(g_id)
                    if g and model_matches_group(requested_model, g.models):
                        matched_group = True
                        break
                if not matched_group:
                    raise _openai_http_error(
                        f"API key is restricted to virtual tiers {allowed_groups_raw} and cannot access model '{requested_model}'.",
                        "permission_denied",
                        403,
                    )
        return

    if mode == "WORKER_POOL":
        allowed_ids_raw = gateway_key.allowed_worker_ids or []
        if not allowed_ids_raw:
            raise _openai_http_error("API key has no permitted models configured in its worker pool.", "permission_denied", 403)
        allowed = {uuid.UUID(item) for item in allowed_ids_raw}
        w_res = await session.execute(
            select(Worker)
            .where(Worker.id.in_(allowed))
            .where(Worker.enabled.is_(True))
        )
        allowed_workers = list(w_res.scalars().all())
        if not allowed_workers:
            raise _openai_http_error("All permitted workers for this API key are currently offline or disabled.", "service_unavailable", 503)
        allowed_models = {w.model for w in allowed_workers}

        if requested_model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
            if is_virtual_group(requested_model):
                group = get_group(requested_model)
                if not any(model_matches_group(m, group.models) for m in allowed_models):
                    raise _openai_http_error(
                        f"API key is not authorized for any models in virtual group '{requested_model}'. Allowed models for this key: {sorted(list(allowed_models))}",
                        "permission_denied",
                        403,
                    )
            elif requested_model not in allowed_models:
                raise _openai_http_error(
                    f"API key is not authorized to access model '{requested_model}'. Allowed models for this key: {sorted(list(allowed_models))}",
                    "permission_denied",
                    403,
                )


@router.post("/chat/completions")
@router.post("/openai/deployments/{deployment_id}/chat/completions")
async def create_chat_completion(
    request: Request,
    body: ChatCompletionRequest,
    deployment_id: str | None = None,
    api_version: str | None = None,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway_key: GatewayApiKey = Depends(require_wrap_api_key),
):
    if deployment_id and (not body.model or body.model in ("auto", "default", "")):
        body.model = deployment_id
    request_id = request.headers.get("x-request-id") or f"wrap_{uuid.uuid4().hex}"
    lifecycle = RequestLifecycle(request_id=request_id, streamed=body.stream)

    # 1. Enforce Gateway Key Rate Limits (sliding-window RPM)
    key_rpm = getattr(gateway_key, "rate_limit_rpm", None) or 120
    rl_limit, rl_remaining, rl_reset = gateway_rate_limiter.check_and_consume(
        str(gateway_key.id), limit_rpm=key_rpm
    )
    rl_headers = {
        "X-RateLimit-Limit": str(rl_limit),
        "X-RateLimit-Remaining": str(rl_remaining),
        "X-RateLimit-Reset": str(rl_reset),
    }

    # 1b. Enforce Gateway Key Budget & Circuit Breaker (Hard Cap, Velocity, Fallback)
    budget_check = BudgetService.check_key_budget(gateway_key)
    if not budget_check.allowed:
        raise HTTPException(
            status_code=budget_check.status_code,
            detail={
                "error": {
                    "message": budget_check.error_message,
                    "type": budget_check.error_type,
                    "code": budget_check.error_code,
                    "param": "spend_usd",
                    "spend_usd": budget_check.current_spend_usd,
                    "max_budget_usd": budget_check.max_budget_usd,
                }
            },
        )
    fallback_to_free = (budget_check.action == "fallback_to_free")

    # 2. Enforce Gateway Key Model Scope & Permissions (before cache check)
    await _verify_gateway_key_access(gateway_key, body.model, session)

    # 3. Fast-path: Check response cache for identical non-streaming requests
    req_dict = body.model_dump(exclude_none=True)
    cached_hit = gateway_cache.get(req_dict, requested_model=body.model)
    if cached_hit:
        cached_resp, hits = cached_hit
        cache_saved_usd = getattr(cached_hit, "value_saved_usd", 0.0)
        usage = cached_resp.get("usage", {})
        lifecycle.input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        lifecycle.output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
        lifecycle.total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        lifecycle.complete()
        try:
            await persist_request_metric(
                session,
                lifecycle,
                worker=None,
                requested_model=body.model,
                gateway_key=gateway_key,
                is_cache_hit=True,
                value_saved_override=cache_saved_usd,
            )
        except Exception:
            pass
        return JSONResponse(
            cached_resp,
            headers={
                "X-Request-ID": request_id,
                "X-Cache": "HIT",
                "X-Cache-Hits": str(hits),
                "X-Cost-USD": "0.000000",
                "X-Value-Saved-USD": f"{cache_saved_usd:.6f}",
                **rl_headers,
            },
        )

    # Agentic Context Compactor: Trims stale historical tool execution outputs (>3500 tokens)
    # while preserving 100% tool_call integrity, system instructions, and recent working memory.
    try:
        from src.services.context_compactor import compact_agent_messages
        compacted_msgs, was_compacted = compact_agent_messages(
            body.messages,
            max_history_turns=4,
            max_tool_output_chars=800,
            target_token_threshold=3500,
        )
        if was_compacted:
            body.messages = [ChatMessage.model_validate(m) for m in compacted_msgs]
            logger.info("agentic context compacted", extra={"request_id": request_id, "messages_count": len(body.messages)})
    except Exception as comp_err:
        logger.warning("context compaction skipped", extra={"request_id": request_id, "error": str(comp_err)})

    estimated_token_mass = _estimate_token_mass(body.messages, body.tools)

    # Check Dual-Model Ensemble Consensus mode
    is_ensemble = (
        body.model.lower() in ("ensemble-consensus", "consensus", "ensemble", "dual-model", "frontier-consensus")
        or request.headers.get("x-wrap-ensemble", "").lower() == "true"
    )
    if is_ensemble:
        return await _execute_ensemble_consensus(
            body,
            session=session,
            settings=settings,
            request_id=request_id,
            gateway_key=gateway_key,
            lifecycle=lifecycle,
            rl_headers=rl_headers,
            estimated_tokens=estimated_token_mass,
        )

    worker: Worker | None = None
    routing_decision = None
    try:
        start_plan = __import__("time").monotonic()
        decision = task_analyzer.assess(body)
        planning_ms = int((__import__("time").monotonic() - start_plan) * 1000)

        if decision.should_decompose:
            logger.info(
                "task decomposition selected",
                extra={
                    "request_id": request_id,
                    "execution_mode": "DAG",
                    "decomposition_reason": decision.reason,
                    "confidence": decision.confidence,
                },
            )
            try:
                result = await DAGExecutor(settings=settings, router=get_intelligent_router()).execute(
                    body,
                    task_analyzer.build_dag(body, task_id=request_id),
                    request_id=request_id,
                    policy=gateway_key.routing_policy,
                    gateway_key=gateway_key,
                    decision=decision,
                    planning_ms=planning_ms,
                )
                lifecycle.output_tokens = result.get("usage", {}).get("output_tokens")
                lifecycle.input_tokens = result.get("usage", {}).get("input_tokens")
                lifecycle.total_tokens = result.get("usage", {}).get("total_tokens")
                lifecycle.complete()
                await persist_request_metric(session, lifecycle, worker=None, requested_model=body.model, gateway_key=gateway_key)
                await session.commit()
                response_payload = _final_response(
                    body.model,
                    result.get("content", ""),
                    result.get("tool_calls"),
                    input_tokens=lifecycle.input_tokens,
                    output_tokens=lifecycle.output_tokens,
                    total_tokens=lifecycle.total_tokens,
                )
                if body.stream:
                    return StreamingResponse(
                        _stream_final_response(response_payload, lifecycle, session),
                        media_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Request-ID": request_id, "X-Cache": "MISS", **rl_headers},
                    )
                gateway_cache.set(req_dict, response_payload, requested_model=body.model)
                return JSONResponse(response_payload, headers={"X-Request-ID": request_id, "X-Cache": "MISS", **rl_headers})
            except Exception as dag_err:
                logger.warning(
                    "DAG execution failed, falling back to single-worker execution",
                    extra={"request_id": request_id, "error": str(dag_err)},
                )

        worker, routing_decision = await _route_single_worker(
            body, session=session, request_id=request_id, gateway_key=gateway_key, fallback_to_free=fallback_to_free, estimated_tokens=estimated_token_mass
        )
        await session.commit()

        # Telemetry: Record WorkflowRun and initial events for SINGLE execution
        wf_run_id = uuid.uuid4()
        event_logger = EventLogger(wf_run_id)
        wf_run = WorkflowRun(
            id=wf_run_id,
            request_id=request_id,
            workflow_definition_id="single-request",
            status="RUNNING",
            execution_mode="SINGLE",
            routing_policy=gateway_key.routing_policy,
            requested_model=body.model,
            executed_model=worker.model,
            provider=worker.provider.name,
            worker_id=worker.id,
            started_at=utcnow(),
        )
        session.add(wf_run)
        await event_logger.log_event(session, WorkflowEventType.WORKFLOW_CREATED, payload={"requested_model": body.model})
        await event_logger.log_event(
            session,
            WorkflowEventType.WORKFLOW_STARTED,
            payload={
                "routing_policy": gateway_key.routing_policy,
                "worker_id": str(worker.id),
                "executed_model": worker.model,
                "provider": worker.provider.name,
            },
        )
        await event_logger.log_event(session, WorkflowEventType.TASK_READY, task_id="completion", payload={"model": worker.model})
        await event_logger.start_attempt(
            session,
            task_id="completion",
            attempt_number=1,
            worker_id=worker.id,
            provider=worker.provider.name,
            model=worker.model,
        )
        await session.commit()

        adapter = registry.get(worker.provider.name)
        provider_key = await get_credential_secret(worker.credential)
        payload = body.model_dump(exclude_none=True)

        # Agentic Context Compactor: De-duplicate environment blocks and truncate ancient tool outputs
        if payload.get("messages"):
            from src.services.context_compactor import compact_agent_messages
            compacted_msgs, was_compacted = compact_agent_messages(payload["messages"])
            if was_compacted:
                payload["messages"] = compacted_msgs

        if body.stream:

            hedge_worker = None
            hedge_delay_header = request.headers.get("x-speculative-hedge-ms")
            hedge_delay_ms = float(hedge_delay_header) if hedge_delay_header and hedge_delay_header.replace(".", "").isdigit() else 1200.0
            if request.headers.get("x-speculative-hedge", "").lower() != "false":
                hedge_worker = await _find_hedge_worker(session, worker, body.model, gateway_key, estimated_tokens=estimated_token_mass)

            stream_state: dict[str, Any] = {
                "worker_id": worker.id,
                "quota": None,
                "persisted": False,
            }

            bg_task = BackgroundTask(
                _finalize_stream_persistence,
                lifecycle=lifecycle,
                stream_state=stream_state,
                requested_model=body.model,
                gateway_key_id=gateway_key.id if gateway_key and hasattr(gateway_key, "id") else None,
                wf_run_id=wf_run.id if wf_run else None,
                event_logger=event_logger,
            )

            return StreamingResponse(
                _hedged_stream_response(
                    primary_worker=worker,
                    hedge_worker=hedge_worker,
                    payload=payload,
                    lifecycle=lifecycle,
                    session=session,
                    settings=settings,
                    request_id=request_id,
                    event_logger=event_logger,
                    wf_run=wf_run,
                    gateway_key=gateway_key,
                    hedge_delay_ms=hedge_delay_ms,
                    stream_state=stream_state,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Request-ID": request_id,
                    "X-Wrap-Speculative-Hedge": "active" if hedge_worker else "single",
                    **rl_headers,
                },
                background=bg_task,
            )

        cred_id = str(worker.credential_id or worker.id)
        pname = worker.provider.name if worker.provider else None
        await upstream_quota_limiter.acquire_slot(cred_id, pname)
        try:
            completion = await adapter.create_completion(
                payload,
                api_key=provider_key,
                model=worker.model,
                request_id=request_id,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
        finally:
            upstream_quota_limiter.release_slot(cred_id)
        if completion and completion.response:
            from src.services.tool_healer import heal_response_tool_calls
            healed_resp, was_healed = heal_response_tool_calls(completion.response, declared_tools=payload.get("tools"))
            completion.response = healed_resp
            gateway_cache.set(payload, completion.response, requested_model=body.model)

        lifecycle.apply_usage(completion.usage)
        lifecycle.complete()

        # Telemetry: Record completion facts and workflow metrics
        await event_logger.finish_attempt(
            session,
            task_id="completion",
            attempt_number=1,
            status="SUCCEEDED",
            duration_ms=lifecycle.total_latency_ms,
        )
        wf_run.status = "COMPLETED"
        wf_run.finished_at = utcnow()
        await event_logger.log_event(
            session,
            WorkflowEventType.WORKFLOW_COMPLETED,
            payload={"total_latency_ms": lifecycle.total_latency_ms, "total_tokens": lifecycle.total_tokens},
        )
        await session.commit()
        await AnalyticsService.get_or_calculate_workflow_metrics(session, wf_run.id)

        await persist_request_metric(session, lifecycle, worker=worker, requested_model=payload.get("model"), gateway_key=gateway_key)
        await persist_quota_snapshot(session, worker_id=worker.id, quota=completion.quota)
        # Phase 2A: Event-driven resource state update
        await _update_resource_state(session, worker, lifecycle, completion.quota)
        await session.commit()
        logger.info(
            "request completed",
            extra={"request_id": request_id, "worker_id": str(worker.id), "provider": worker.provider.name, "model": worker.model},
        )
        from src.services.pricing import calculate_request_economics
        is_paid = is_worker_or_credential_paid(worker, worker.provider.name)
        econ = calculate_request_economics(
            input_tokens=lifecycle.input_tokens,
            output_tokens=lifecycle.output_tokens,
            total_tokens=lifecycle.total_tokens,
            provider=worker.provider.name,
            model=worker.model,
            is_paid=is_paid,
        )
        return JSONResponse(
            completion.response,
            headers={
                "X-Request-ID": request_id,
                "X-Cache": "MISS",
                "X-Cost-USD": f"{econ['actual_cost_usd']:.6f}",
                "X-Value-Saved-USD": f"{econ['saved_usd']:.6f}",
                **rl_headers,
            },
        )
    except NoWorkerAvailable as exc:
        lifecycle.fail(exc)
        try:
            await persist_request_metric(session, lifecycle, worker=worker, requested_model=body.model, gateway_key=gateway_key)
        except Exception:
            pass
        raise _openai_http_error("No enabled worker is available for the requested model", "model_not_found", 404)
    except ProviderError as exc:
        from src.providers.base import ModelNotFoundError, ProviderUnavailableError, RateLimitError
        lifecycle.fail(exc)
        if worker:
            if isinstance(exc, ModelNotFoundError):
                from src.services.catalog import mark_catalog_stale
                await mark_catalog_stale(session, worker.provider_id, worker.model)
                await session.commit()
            await _update_resource_state(session, worker, lifecycle, None)

        # For transient errors (connection drop, rate limit) attempt one failover to a different worker
        # before surfacing the error to the client. This is the single-worker equivalent of hedging.
        if not body.stream and isinstance(exc, (ProviderUnavailableError, RateLimitError)) and worker:
            try:
                failed_worker_id = worker.id
                from src.scheduler import Scheduler
                from sqlalchemy import select as _sa_select
                failover_stmt = (
                    _sa_select(Worker)
                    .join(Provider, Worker.provider_id == Provider.id)
                    .options(selectinload(Worker.provider), selectinload(Worker.credential))
                    .where(Provider.enabled.is_(True))
                    .where(Worker.enabled.is_(True))
                    .where(Worker.health_status.in_(["healthy", "unknown"]))
                    .where(Worker.id != failed_worker_id)
                )
                _res = await session.execute(failover_stmt)
                failover_candidates = list(_res.scalars().all())
                if failover_candidates:
                    # Pick the one least recently used
                    failover_candidates.sort(key=lambda w: w.last_used_at or w.created_at)
                    failover_worker = failover_candidates[0]
                    failover_adapter = registry.get(failover_worker.provider.name)
                    failover_key = await get_credential_secret(failover_worker.credential)
                    f_cred_id = str(failover_worker.credential_id or failover_worker.id)
                    f_pname = failover_worker.provider.name if failover_worker.provider else None
                    lifecycle2 = RequestLifecycle(request_id=request_id, streamed=False)
                    await upstream_quota_limiter.acquire_slot(f_cred_id, f_pname)
                    try:
                        failover_completion = await failover_adapter.create_completion(
                            payload,
                            api_key=failover_key,
                            model=failover_worker.model,
                            request_id=f"{request_id}_fo",
                            timeout=settings.REQUEST_TIMEOUT_SECONDS,
                        )
                    finally:
                        upstream_quota_limiter.release_slot(f_cred_id)
                    lifecycle2.apply_usage(failover_completion.usage)
                    lifecycle2.complete()
                    if failover_completion and failover_completion.response:
                        from src.services.tool_healer import heal_response_tool_calls
                        healed_fo, was_healed = heal_response_tool_calls(failover_completion.response, declared_tools=payload.get("tools"))
                        failover_completion.response = healed_fo
                        gateway_cache.set(payload, failover_completion.response, requested_model=body.model)

                    await persist_request_metric(session, lifecycle2, worker=failover_worker, requested_model=body.model, gateway_key=gateway_key)
                    await _update_resource_state(session, failover_worker, lifecycle2, failover_completion.quota)
                    logger.info(
                        "failover succeeded",
                        extra={"request_id": request_id, "failed_worker": str(failed_worker_id), "failover_worker": str(failover_worker.id)},
                    )
                    from src.services.pricing import calculate_request_economics
                    fo_is_paid = is_worker_or_credential_paid(failover_worker, failover_worker.provider.name)
                    fo_econ = calculate_request_economics(
                        input_tokens=lifecycle2.input_tokens,
                        output_tokens=lifecycle2.output_tokens,
                        total_tokens=lifecycle2.total_tokens,
                        provider=failover_worker.provider.name,
                        model=failover_worker.model,
                        is_paid=fo_is_paid,
                    )
                    return JSONResponse(
                        failover_completion.response,
                        headers={
                            "X-Request-ID": request_id,
                            "X-Cache": "MISS",
                            "X-Wrap-Failover": "true",
                            "X-Cost-USD": f"{fo_econ['actual_cost_usd']:.6f}",
                            "X-Value-Saved-USD": f"{fo_econ['saved_usd']:.6f}",
                            **rl_headers,
                        },
                    )
            except Exception as fo_exc:
                logger.warning("failover also failed", extra={"request_id": request_id, "error": str(fo_exc)})

        try:
            await persist_request_metric(session, lifecycle, worker=worker, requested_model=body.model, gateway_key=gateway_key)
        except Exception:
            pass
        raise _openai_http_error(str(exc), exc.error_type, exc.status_code)
    except HTTPException as exc:
        lifecycle.fail(exc)
        try:
            await persist_request_metric(session, lifecycle, worker=worker, requested_model=body.model, gateway_key=gateway_key)
        except Exception:
            pass
        raise
    except Exception as exc:
        lifecycle.fail(exc)
        try:
            await persist_request_metric(session, lifecycle, worker=worker, requested_model=body.model, gateway_key=gateway_key)
        except Exception:
            pass
        if worker:
            await _update_resource_state(session, worker, lifecycle, None)
        logger.exception("unexpected request failure", extra={"request_id": request_id})
        raise _openai_http_error(f"Internal server error: {exc}", "internal_error", 500)


async def _update_resource_state(
    session: AsyncSession,
    worker: Worker,
    lifecycle: RequestLifecycle,
    quota: dict | None,
) -> None:
    """Push event-driven update to the ResourceStateStore after a request."""
    try:
        intelligent_router = get_intelligent_router()
        if not intelligent_router:
            return
        snapshot = lifecycle.snapshot()
        success = snapshot.get("status") == "success"
        transition = intelligent_router._resource_store.on_request_complete(
            worker.id,
            latency_ms=snapshot.get("total_latency_ms"),
            ttft_ms=snapshot.get("ttft_ms"),
            tps=snapshot.get("output_tokens_per_second"),
            success=success,
            quota=quota,
        )
        if transition:
            prev_status, new_status = transition
            worker.health_status = new_status
            state = intelligent_router._resource_store.get_worker(worker.id)
            failures = state.consecutive_failures if state else 0
            reason = f"consecutive_failures_{failures}" if not success else "request_success_recovery"
            await persist_health_event(
                session,
                worker=worker,
                new_status=new_status,
                reason=reason,
                metadata={"consecutive_failures": failures},
            )
    except Exception:
        pass  # Event updates are best-effort; never fail the request


async def _finalize_stream_persistence(
    lifecycle: RequestLifecycle,
    stream_state: dict[str, Any],
    requested_model: str,
    gateway_key_id: uuid.UUID | None,
    wf_run_id: uuid.UUID | None = None,
    event_logger: EventLogger | None = None,
) -> None:
    if stream_state.get("persisted"):
        return

    persist_task = stream_state.get("persist_task")
    if persist_task is None or persist_task.done():
        if stream_state.get("persisted"):
            return

        async def _do_persist() -> None:
            from src.db.session import AsyncSessionLocal
            from src.db.models import Worker, GatewayApiKey
            from src.analytics.models import WorkflowRun
            from src.services.persistence import persist_request_metric, persist_quota_snapshot
            from src.analytics.service import AnalyticsService
            from src.analytics.enums import WorkflowEventType

            worker_id = stream_state.get("worker_id")
            quota = stream_state.get("quota")

            try:
                async with AsyncSessionLocal() as session:
                    worker = await session.get(Worker, worker_id) if worker_id else None
                    gateway_key = await session.get(GatewayApiKey, gateway_key_id) if gateway_key_id else None

                    if wf_run_id and event_logger:
                        succ = lifecycle.status == "success"
                        att_status = "SUCCEEDED" if succ else ("CANCELLED" if lifecycle.status == "stream_interrupted" else "FAILED")
                        try:
                            await event_logger.finish_attempt(
                                session,
                                task_id="completion",
                                attempt_number=1,
                                status=att_status,
                                duration_ms=lifecycle.total_latency_ms,
                                error_type=lifecycle.error_type,
                                error_message=lifecycle.error_message,
                            )
                            wf_obj = await session.get(WorkflowRun, wf_run_id)
                            if wf_obj:
                                wf_obj.status = "COMPLETED" if succ else ("CANCELLED" if lifecycle.status == "stream_interrupted" else "FAILED")
                                wf_obj.finished_at = utcnow()
                                if succ:
                                    await event_logger.log_event(
                                        session,
                                        WorkflowEventType.WORKFLOW_COMPLETED,
                                        payload={"total_latency_ms": lifecycle.total_latency_ms, "total_tokens": lifecycle.total_tokens},
                                    )
                                elif lifecycle.status == "stream_interrupted":
                                    await event_logger.log_event(
                                        session,
                                        WorkflowEventType.WORKFLOW_CANCELLED,
                                        payload={"reason": "stream_interrupted"},
                                    )
                                else:
                                    await event_logger.log_event(
                                        session,
                                        WorkflowEventType.WORKFLOW_FAILED,
                                        payload={"error_type": lifecycle.error_type, "error_message": lifecycle.error_message},
                                    )
                                await session.commit()
                                await AnalyticsService.get_or_calculate_workflow_metrics(session, wf_run_id)
                        except Exception as wf_exc:
                            logger.warning("workflow telemetry persistence failed: %s", wf_exc)

                    await persist_request_metric(
                        session,
                        lifecycle,
                        worker=worker,
                        requested_model=requested_model,
                        gateway_key=gateway_key,
                    )
                    if worker:
                        if quota:
                            await persist_quota_snapshot(session, worker_id=worker.id, quota=quota)
                        await _update_resource_state(session, worker, lifecycle, quota)
                    await session.commit()
                    stream_state["persisted"] = True
                    logger.info("stream metric persisted successfully", extra={"request_id": lifecycle.request_id})
            except Exception as exc:
                logger.exception("finalize stream persistence failed for request %s: %s", lifecycle.request_id, exc)

        persist_task = asyncio.create_task(_do_persist())
        stream_state["persist_task"] = persist_task

    try:
        await asyncio.shield(persist_task)
    except asyncio.CancelledError:
        # Caller stream was cancelled (e.g. client socket closed). Wait for persistence to complete cleanly.
        try:
            await persist_task
        except Exception:
            pass


async def _stream_response(
    *,
    adapter,
    payload: dict,
    worker: Worker,
    provider_key: str,
    lifecycle: RequestLifecycle,
    session: AsyncSession,
    settings: Settings,
    request_id: str,
    event_logger: EventLogger | None = None,
    wf_run: WorkflowRun | None = None,
    gateway_key: Any | None = None,
    stream_state: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream a completion from a single worker.

    Error handling contract (critical for IDE extensions like Roo Code / Continue):
    - Provider errors BEFORE the first content token: re-raise so the outer
      hedged-stream or caller can retry on a different worker. Never inject
      an error JSON object into the SSE stream at this stage — the client
      has no way to distinguish it from a content delta.
    - Provider errors AFTER the first content token: the response is already
      partially delivered. Close the stream cleanly with [DONE] and log the
      truncation; do NOT inject raw error JSON.
    """
    quota = None
    first_token_sent = False
    w_cred_id = str(worker.credential_id or worker.id)
    w_pname = worker.provider.name if worker.provider else None
    await upstream_quota_limiter.acquire_slot(w_cred_id, w_pname)
    from src.services.tool_healer import StreamToolHealer

    stream_tool_healer = StreamToolHealer(
        declared_tools=payload.get("tools"),
        model=worker.model,
    )
    last_chunk_template: dict[str, Any] | None = None

    try:
        async for event in adapter.stream_completion(
            payload,
            api_key=provider_key,
            model=worker.model,
            request_id=request_id,
            timeout=settings.STREAM_IDLE_TIMEOUT_SECONDS,
        ):
            if event.quota:
                quota = event.quota
                if stream_state is not None:
                    stream_state["quota"] = quota
            lifecycle.apply_usage(event.usage)
            if event.done:
                lifecycle.complete()
                final_template = last_chunk_template or {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(utcnow().timestamp()),
                    "model": worker.model,
                }
                for f_chunk in stream_tool_healer.finalize_stream(final_template):
                    lifecycle.mark_first_token()
                    first_token_sent = True
                    lifecycle.estimate_output_tokens_from_text(_delta_text(f_chunk))
                    yield f"data: {json.dumps(f_chunk)}\n\n"

                if payload.get("stream_options", {}).get("include_usage"):
                    usage_chunk = {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(utcnow().timestamp()),
                        "model": worker.model,
                        "choices": [],
                        "usage": {
                            "prompt_tokens": lifecycle.input_tokens or 0,
                            "completion_tokens": lifecycle.output_tokens or 0,
                            "total_tokens": lifecycle.total_tokens or 0,
                        },
                    }
                    yield f"data: {json.dumps(usage_chunk)}\n\n"
                yield "data: [DONE]\n\n"
                return
            if event.payload:
                last_chunk_template = event.payload
                processed_chunks = stream_tool_healer.process_chunk(event.payload)
                for p_chunk in processed_chunks:
                    lifecycle.mark_first_token()
                    first_token_sent = True
                    lifecycle.estimate_output_tokens_from_text(_delta_text(p_chunk))
                    yield f"data: {json.dumps(p_chunk)}\n\n"
        lifecycle.complete()
        final_template = last_chunk_template or {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(utcnow().timestamp()),
            "model": worker.model,
        }
        for f_chunk in stream_tool_healer.finalize_stream(final_template):
            lifecycle.mark_first_token()
            first_token_sent = True
            yield f"data: {json.dumps(f_chunk)}\n\n"
        yield "data: [DONE]\n\n"
    except ProviderError as exc:
        from src.providers.base import ModelNotFoundError, ProviderUnavailableError, RateLimitError
        if isinstance(exc, ModelNotFoundError):
            from src.services.catalog import mark_catalog_stale
            await mark_catalog_stale(session, worker.provider_id, worker.model)
            await session.commit()
        lifecycle.fail(exc)
        if not first_token_sent:
            # Re-raise before any content is on the wire — caller will retry on a different worker
            raise
        # Already streaming: close cleanly. Do NOT inject error JSON — IDE extensions
        # cannot distinguish it from content and will display garbage or crash.
        logger.warning(
            "stream truncated after first token",
            extra={"request_id": request_id, "provider": w_pname, "error": str(exc)},
        )
        yield "data: [DONE]\n\n"
    except GeneratorExit:
        lifecycle.complete("stream_interrupted")
        raise
    except Exception as exc:
        lifecycle.fail(exc)
        logger.exception("stream interrupted", extra={"request_id": request_id})
        raise
    finally:
        upstream_quota_limiter.release_slot(w_cred_id)
        if stream_state is not None:
            await _finalize_stream_persistence(
                lifecycle=lifecycle,
                stream_state=stream_state,
                requested_model=payload.get("model", worker.model),
                gateway_key_id=gateway_key.id if gateway_key and hasattr(gateway_key, "id") else None,
                wf_run_id=wf_run.id if wf_run else None,
                event_logger=event_logger,
            )


async def _stream_final_response(payload: dict, lifecycle: RequestLifecycle, session: AsyncSession) -> AsyncIterator[str]:
    msg = payload["choices"][0]["message"]
    text = msg.get("content")
    tool_calls = msg.get("tool_calls")
    finish_reason = payload["choices"][0].get("finish_reason", "stop")
    delta: dict[str, Any] = {}
    if text is not None:
        delta["content"] = text
    if tool_calls:
        delta["tool_calls"] = tool_calls
    chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    lifecycle.mark_first_token()
    yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"


def _delta_text(payload: dict) -> str:
    text = ""
    for choice in payload.get("choices", []):
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            text += content
    return text


def _estimate_token_mass(messages: list[Any], tools: list[Any] | None = None) -> int:
    total_chars = 0
    for m in messages:
        c = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
        if isinstance(c, str):
            total_chars += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and "text" in part:
                    total_chars += len(str(part["text"]))
    if tools:
        try:
            total_chars += len(json.dumps([t.model_dump() if hasattr(t, "model_dump") else t for t in tools]))
        except Exception:
            total_chars += len(str(tools))
    return max(1, total_chars // 4 + len(messages) * 5)


async def _find_hedge_worker(
    session: AsyncSession,
    primary_worker: Worker,
    requested_model: str,
    gateway_key: GatewayApiKey,
    estimated_tokens: int = 0,
) -> Worker | None:
    from src.services.model_groups import is_virtual_group, get_group, expand_group_models

    mode = gateway_key.worker_selection_mode or "AUTO"
    if mode == "SPECIFIC_WORKER":
        return None

    stmt = (
        select(Worker)
        .join(Provider, Worker.provider_id == Provider.id)
        .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
        .where(Provider.enabled.is_(True))
        .where(Worker.enabled.is_(True))
        .where(Worker.health_status.in_(["healthy", "unknown", "degraded"]))
        .where(Worker.id != primary_worker.id)
    )

    if mode == "WORKER_POOL":
        allowed_raw = gateway_key.allowed_worker_ids or []
        if allowed_raw:
            stmt = stmt.where(Worker.id.in_({uuid.UUID(x) for x in allowed_raw}))

    if is_virtual_group(requested_model):
        group = get_group(requested_model)
        if group:
            stmt = stmt.where(Worker.model.in_(expand_group_models(group.models)))
    elif requested_model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
        # If client requested specific model matching primary worker, try same model first
        if requested_model == primary_worker.model:
            stmt = stmt.where(Worker.model == primary_worker.model)

    res = await session.execute(stmt)
    candidates = list(res.scalars().all())
    if not candidates:
        # Cross-worker failover fallback: allow any healthy alternative worker (same or other provider)
        alt_stmt = (
            select(Worker)
            .join(Provider, Worker.provider_id == Provider.id)
            .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
            .where(Provider.enabled.is_(True))
            .where(Worker.enabled.is_(True))
            .where(Worker.health_status.in_(["healthy", "unknown", "degraded"]))
            .where(Worker.id != primary_worker.id)
        )
        alt_res = await session.execute(alt_stmt)
        candidates = list(alt_res.scalars().all())

    if not candidates:
        return None

    # Ranking logic:
    # 1. Non-Groq prioritized if prompt is heavy (Groq has 7k ITPM free tier limit, though auto-pruned)
    # 2. Prefer different credential to avoid quota lock
    # 3. Least recently used
    def _rank_candidate(w: Worker) -> tuple:
        pname = (w.provider.name or "").lower() if w.provider else ""
        is_groq_heavy = 1 if (estimated_tokens >= 4000 and pname == "groq") else 0
        diff_cred = 0 if w.credential_id != primary_worker.credential_id else 1
        diff_provider = 0 if w.provider_id != primary_worker.provider_id else 1
        return (is_groq_heavy, diff_cred, diff_provider, w.last_used_at or w.created_at)

    candidates.sort(key=_rank_candidate)
    return candidates[0]


def _emit_graceful_stream_error(lifecycle: RequestLifecycle, model: str, error_msg: str | None = None) -> str:
    from src.providers.base import ProviderUnavailableError
    err_text = error_msg or "All upstream providers are temporarily unavailable."
    lifecycle.fail(ProviderUnavailableError(err_text))
    err_chunk = {
        "error": {
            "message": err_text,
            "type": "upstream_error",
            "param": None,
            "code": "provider_unavailable",
        }
    }
    return f"data: {json.dumps(err_chunk)}\n\n"


async def _hedged_stream_response(
    primary_worker: Worker,
    hedge_worker: Worker | None,
    payload: dict,
    lifecycle: RequestLifecycle,
    session: AsyncSession,
    settings: Settings,
    request_id: str,
    event_logger: EventLogger | None = None,
    wf_run: WorkflowRun | None = None,
    gateway_key: Any | None = None,
    hedge_delay_ms: float = 350.0,
    stream_state: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    logger.info("hedged_stream_response starting", extra={"request_id": request_id, "has_hedge": hedge_worker is not None})
    if hedge_worker is None:
        primary_adapter = registry.get(primary_worker.provider.name)
        primary_key = await get_credential_secret(primary_worker.credential)
        try:
            async for chunk in _stream_response(
                adapter=primary_adapter,
                payload=payload,
                worker=primary_worker,
                provider_key=primary_key,
                lifecycle=lifecycle,
                session=session,
                settings=settings,
                request_id=request_id,
                event_logger=event_logger,
                wf_run=wf_run,
                gateway_key=gateway_key,
                stream_state=stream_state,
            ):
                yield chunk
            return
        except ProviderError as exc:
            logger.warning(
                "primary stream failed before first token; attempting failover",
                extra={"request_id": request_id, "error": str(exc), "primary_worker": str(primary_worker.id)},
            )
            fo_tokens = _estimate_token_mass(payload.get("messages", []), payload.get("tools"))
            fo_worker = await _find_hedge_worker(session, primary_worker, payload.get("model", ""), gateway_key, estimated_tokens=fo_tokens)
            if fo_worker:
                try:
                    fo_adapter = registry.get(fo_worker.provider.name)
                    fo_key = await get_credential_secret(fo_worker.credential)
                    lifecycle.reset()
                    if stream_state is not None:
                        stream_state["worker_id"] = fo_worker.id
                    async for chunk in _stream_response(
                        adapter=fo_adapter,
                        payload=payload,
                        worker=fo_worker,
                        provider_key=fo_key,
                        lifecycle=lifecycle,
                        session=session,
                        settings=settings,
                        request_id=f"{request_id}_fo",
                        event_logger=event_logger,
                        wf_run=wf_run,
                        gateway_key=gateway_key,
                        stream_state=stream_state,
                    ):
                        yield chunk
                    return
                except Exception as fo_err:
                    logger.error("stream failover failed", extra={"request_id": request_id, "error": str(fo_err)})
            if not lifecycle.first_token_at:
                yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model), str(exc))
            yield "data: [DONE]\n\n"
            return

    from src.services.tool_healer import StreamToolHealer

    stream_tool_healer = StreamToolHealer(
        declared_tools=payload.get("tools"),
        model=payload.get("model", primary_worker.model),
    )
    last_chunk_template: dict[str, Any] | None = None

    import asyncio
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    primary_cancel = asyncio.Event()
    hedge_cancel = asyncio.Event()

    async def _stream_worker_task(w: Worker, role: str, cancel_ev: asyncio.Event):
        w_cred_id = str(w.credential_id or w.id)
        w_pname = w.provider.name if w.provider else None
        await upstream_quota_limiter.acquire_slot(w_cred_id, w_pname)
        try:
            w_adapter = registry.get(w.provider.name)
            w_key = await get_credential_secret(w.credential)
            async for ev in w_adapter.stream_completion(
                payload,
                api_key=w_key,
                model=w.model,
                request_id=f"{request_id}_{role}",
                timeout=settings.STREAM_IDLE_TIMEOUT_SECONDS,
            ):
                if cancel_ev.is_set():
                    break
                await queue.put((role, ev))
                if ev.done:
                    break
        except Exception as exc:
            if not cancel_ev.is_set():
                await queue.put((role, exc))
        finally:
            upstream_quota_limiter.release_slot(w_cred_id)
            await queue.put((role, "DONE_SIGNAL"))

    primary_task = asyncio.create_task(_stream_worker_task(primary_worker, "primary", primary_cancel))
    hedge_task = None
    hedge_spawned = False
    winner_role: str | None = None
    winning_worker: Worker = primary_worker
    quota = None

    primary_failed = False
    hedge_failed = False

    try:
        t_deadline = asyncio.get_event_loop().time() + (hedge_delay_ms / 1000.0)
        while winner_role is None:
            time_left = max(0.01, t_deadline - asyncio.get_event_loop().time()) if not hedge_spawned else None
            try:
                role, item = await asyncio.wait_for(queue.get(), timeout=time_left) if time_left is not None else await queue.get()
            except asyncio.TimeoutError:
                if not hedge_spawned:
                    hedge_spawned = True
                    hedge_task = asyncio.create_task(_stream_worker_task(hedge_worker, "hedge", hedge_cancel))
                continue

            if isinstance(item, Exception):
                logger.warning(
                    f"{role} worker stream error during hedge race",
                    extra={"request_id": request_id, "role": role, "error": str(item)},
                )
                if role == "primary":
                    primary_failed = True
                    if not hedge_spawned:
                        hedge_spawned = True
                        hedge_task = asyncio.create_task(_stream_worker_task(hedge_worker, "hedge", hedge_cancel))
                        continue
                    elif hedge_failed:
                        logger.error("both primary and hedge workers failed before first token", extra={"request_id": request_id})
                        if not lifecycle.first_token_at:
                            yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model))
                        yield "data: [DONE]\n\n"
                        return
                    continue
                else:  # role == "hedge"
                    hedge_failed = True
                    if primary_failed:
                        logger.error("both primary and hedge workers failed before first token", extra={"request_id": request_id})
                        if not lifecycle.first_token_at:
                            yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model))
                        yield "data: [DONE]\n\n"
                        return
                    # Primary worker is still running! Never kill primary stream on hedge failure.
                    continue

            if item == "DONE_SIGNAL":
                continue

            ev = item
            if ev.payload:
                last_chunk_template = ev.payload
                winner_role = role
                if winner_role == "primary":
                    winning_worker = primary_worker
                    if hedge_task:
                        hedge_cancel.set()
                        hedge_task.cancel()
                else:
                    winning_worker = hedge_worker
                    primary_cancel.set()
                    primary_task.cancel()

                if stream_state is not None:
                    stream_state["worker_id"] = winning_worker.id

                for p_chunk in stream_tool_healer.process_chunk(ev.payload):
                    lifecycle.mark_first_token()
                    lifecycle.estimate_output_tokens_from_text(_delta_text(p_chunk))
                    yield f"data: {json.dumps(p_chunk)}\n\n"
                break
            elif ev.done:
                winner_role = role
                winning_worker = primary_worker if role == "primary" else hedge_worker
                if stream_state is not None:
                    stream_state["worker_id"] = winning_worker.id
                break

        # Drain the winning stream
        while True:
            role, item = await queue.get()
            if role != winner_role:
                continue
            if item == "DONE_SIGNAL":
                break
            if isinstance(item, Exception):
                logger.warning(
                    f"winning worker {winner_role} stream error during drain",
                    extra={"request_id": request_id, "error": str(item)},
                )
                if not lifecycle.first_token_at:
                    yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model), str(item))
                lifecycle.complete()
                yield "data: [DONE]\n\n"
                return
            ev = item
            if ev.quota:
                quota = ev.quota
                if stream_state is not None:
                    stream_state["quota"] = quota
            lifecycle.apply_usage(ev.usage)
            if ev.done:
                lifecycle.complete()
                final_template = last_chunk_template or {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(utcnow().timestamp()),
                    "model": payload.get("model", winning_worker.model),
                }
                for f_chunk in stream_tool_healer.finalize_stream(final_template):
                    lifecycle.mark_first_token()
                    lifecycle.estimate_output_tokens_from_text(_delta_text(f_chunk))
                    yield f"data: {json.dumps(f_chunk)}\n\n"
                if not lifecycle.first_token_at:
                    yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model))
                yield "data: [DONE]\n\n"
                return
            if ev.payload:
                last_chunk_template = ev.payload
                for p_chunk in stream_tool_healer.process_chunk(ev.payload):
                    lifecycle.estimate_output_tokens_from_text(_delta_text(p_chunk))
                    yield f"data: {json.dumps(p_chunk)}\n\n"

        final_template = last_chunk_template or {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(utcnow().timestamp()),
            "model": payload.get("model", winning_worker.model),
        }
        for f_chunk in stream_tool_healer.finalize_stream(final_template):
            lifecycle.mark_first_token()
            yield f"data: {json.dumps(f_chunk)}\n\n"

        if not lifecycle.first_token_at:
            yield _emit_graceful_stream_error(lifecycle, payload.get("model", primary_worker.model))
        lifecycle.complete()
        yield "data: [DONE]\n\n"
    finally:
        primary_cancel.set()
        hedge_cancel.set()
        if primary_task and not primary_task.done():
            primary_task.cancel()
        if hedge_task and not hedge_task.done():
            hedge_task.cancel()
        if stream_state is not None:
            await _finalize_stream_persistence(
                lifecycle=lifecycle,
                stream_state=stream_state,
                requested_model=payload.get("model", primary_worker.model),
                gateway_key_id=gateway_key.id if gateway_key and hasattr(gateway_key, "id") else None,
                wf_run_id=wf_run.id if wf_run else None,
                event_logger=event_logger,
            )


async def _execute_ensemble_consensus(
    body: ChatCompletionRequest,
    session: AsyncSession,
    settings: Settings,
    request_id: str,
    gateway_key: GatewayApiKey,
    lifecycle: RequestLifecycle,
    rl_headers: dict[str, str],
    estimated_tokens: int = 0,
) -> JSONResponse | StreamingResponse:
    from src.services.model_groups import get_group, expand_group_models

    group = get_group("ensemble-consensus")
    expanded = expand_group_models(group.models) if group else []
    workers_res = await session.execute(
        select(Worker)
        .join(Provider, Worker.provider_id == Provider.id)
        .options(selectinload(Worker.provider), selectinload(Worker.credential))
        .where(Provider.enabled.is_(True))
        .where(Worker.enabled.is_(True))
        .where(Worker.health_status.in_(["healthy", "unknown"]))
        .where(Worker.model.in_(expanded))
    )
    workers = list(workers_res.scalars().all())

    # Fast generator candidate: groq, cerebras, fast, or llama models
    primary_candidates = [
        w for w in workers
        if any(p in (w.provider.name or "").lower() for p in ("groq", "cerebras", "fast", "sambanova"))
        or any(m in (w.model or "").lower() for m in ("llama", "groq", "cerebras"))
    ]
    # Reasoning verifier candidate: gemini, google, qwen, verifier, or flash models
    verifier_candidates = [
        w for w in workers
        if any(p in (w.provider.name or "").lower() for p in ("gemini", "google", "qwen", "verifier"))
        or any(m in (w.model or "").lower() for m in ("flash", "pro", "qwen", "gemini"))
    ]

    primary_worker = primary_candidates[0] if primary_candidates else (workers[0] if workers else None)
    verifier_worker = None
    if primary_worker:
        for v in verifier_candidates:
            if v.id != primary_worker.id:
                verifier_worker = v
                break
        if not verifier_worker and len(workers) > 1:
            for w in workers:
                if w.id != primary_worker.id:
                    verifier_worker = w
                    break

    if not primary_worker or not verifier_worker:
        single_w = primary_worker or (workers[0] if workers else None)
        if not single_w:
            raise _openai_http_error("No available workers for ensemble consensus tier", "service_unavailable", 503)
        primary_adapter = registry.get(single_w.provider.name)
        primary_key = await get_credential_secret(single_w.credential)
        payload = body.model_dump(exclude_none=True)
        cred_id = str(single_w.credential_id or single_w.id)
        pname = single_w.provider.name if single_w.provider else None
        await upstream_quota_limiter.acquire_slot(cred_id, pname)
        try:
            completion = await primary_adapter.create_completion(
                payload, api_key=primary_key, model=single_w.model, request_id=request_id, timeout=settings.REQUEST_TIMEOUT_SECONDS
            )
        finally:
            upstream_quota_limiter.release_slot(cred_id)
        lifecycle.apply_usage(completion.usage)
        lifecycle.complete()
        return JSONResponse(
            completion.response,
            headers={"X-Request-ID": request_id, "X-Wrap-Consensus": "DEGRADED_SINGLE", **rl_headers},
        )

    # 1. Primary Generation (350+ tok/s output speed)
    primary_adapter = registry.get(primary_worker.provider.name)
    primary_key = await get_credential_secret(primary_worker.credential)
    payload = body.model_dump(exclude_none=True)
    p_cred_id = str(primary_worker.credential_id or primary_worker.id)
    await upstream_quota_limiter.acquire_slot(p_cred_id, primary_worker.provider.name)
    try:
        primary_completion = await primary_adapter.create_completion(
            payload, api_key=primary_key, model=primary_worker.model, request_id=f"{request_id}_pri", timeout=settings.REQUEST_TIMEOUT_SECONDS
        )
    finally:
        upstream_quota_limiter.release_slot(p_cred_id)

    primary_resp = primary_completion.response or {}
    choices = primary_resp.get("choices") or []
    primary_content = ""
    if choices:
        primary_content = (choices[0].get("message") or {}).get("content") or ""

    user_text = ""
    for m in body.messages:
        if m.role == "user" and isinstance(m.content, str):
            user_text = m.content

    # 2. Reasoning Verifier Invariance Check
    verifier_adapter = registry.get(verifier_worker.provider.name)
    verifier_key = await get_credential_secret(verifier_worker.credential)
    verify_messages = [
        {
            "role": "system",
            "content": "You are a frontier-tier reasoning verification engine. Your task is to verify the accuracy, logical rigor, and syntax of a generated response. If the response is sound and correct, output exactly 'STATUS: VERIFIED'. If there are critical errors or hallucinations, output 'STATUS: REVISED' followed immediately by the perfected corrected response.",
        },
        {
            "role": "user",
            "content": f"USER PROMPT:\n{user_text}\n\nPROPOSED RESPONSE:\n{primary_content}\n\nEvaluate correctness and output STATUS: VERIFIED or STATUS: REVISED <corrected response>.",
        },
    ]
    verify_payload = {"messages": verify_messages, "temperature": 0.0}
    v_cred_id = str(verifier_worker.credential_id or verifier_worker.id)
    await upstream_quota_limiter.acquire_slot(v_cred_id, verifier_worker.provider.name)
    try:
        verifier_completion = await verifier_adapter.create_completion(
            verify_payload, api_key=verifier_key, model=verifier_worker.model, request_id=f"{request_id}_ver", timeout=settings.REQUEST_TIMEOUT_SECONDS
        )
    finally:
        upstream_quota_limiter.release_slot(v_cred_id)

    verifier_text = ""
    v_choices = (verifier_completion.response or {}).get("choices") or []
    if v_choices:
        verifier_text = (v_choices[0].get("message") or {}).get("content") or ""

    consensus_status = "VERIFIED"
    final_content = primary_content
    if "STATUS: REVISED" in verifier_text:
        consensus_status = "REVISED"
        revised_part = verifier_text.split("STATUS: REVISED", 1)[1].strip()
        if revised_part:
            final_content = revised_part

    lifecycle.input_tokens = (primary_completion.usage.get("input_tokens") or 0) + (verifier_completion.usage.get("input_tokens") or 0)
    lifecycle.output_tokens = (primary_completion.usage.get("output_tokens") or 0) + (verifier_completion.usage.get("output_tokens") or 0)
    lifecycle.total_tokens = lifecycle.input_tokens + lifecycle.output_tokens
    lifecycle.complete()

    final_resp_payload = _final_response(
        body.model,
        final_content,
        input_tokens=lifecycle.input_tokens,
        output_tokens=lifecycle.output_tokens,
        total_tokens=lifecycle.total_tokens,
    )
    consensus_headers = {
        "X-Request-ID": request_id,
        "X-Wrap-Consensus": consensus_status,
        "X-Wrap-Primary-Model": primary_worker.model,
        "X-Wrap-Verifier-Model": verifier_worker.model,
        **rl_headers,
    }

    if body.stream:
        return StreamingResponse(
            _stream_final_response(final_resp_payload, lifecycle, session),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", **consensus_headers},
        )

    return JSONResponse(final_resp_payload, headers=consensus_headers)


async def _route_single_worker(
    body: ChatCompletionRequest,
    *,
    session: AsyncSession,
    request_id: str,
    gateway_key: GatewayApiKey,
    fallback_to_free: bool = False,
    estimated_tokens: int = 0,
):
    from src.services.model_groups import is_virtual_group, get_group
    from src.scheduler import Scheduler

    mode = gateway_key.worker_selection_mode or "AUTO"
    if mode == "SPECIFIC_WORKER":
        if not gateway_key.specific_worker_id:
            raise _openai_http_error("API key is pinned to a missing worker", "invalid_request_error", 400)
        result = await session.execute(
            select(Worker)
            .options(selectinload(Worker.provider), selectinload(Worker.credential), selectinload(Worker.provider_model))
            .where(Worker.id == gateway_key.specific_worker_id)
            .where(Worker.enabled.is_(True))
        )
        worker = result.scalar_one_or_none()
        if worker is None:
            raise _openai_http_error("Pinned worker for this API key is disabled or not found", "model_not_found", 404)
        if body.model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent") and worker.model != body.model:
            raise _openai_http_error(
                f"API key is pinned to model '{worker.model}' and is not authorized to access '{body.model}'.",
                "permission_denied",
                403,
            )
        session.add(
            RoutingDecision(
                request_id=request_id,
                candidate_workers=[str(worker.id)],
                selected_worker=str(worker.id),
                decision_reason="API key pinned to specific worker",
                routing_version="phase2b-api-key-scope-v1",
                policy=gateway_key.routing_policy,
            )
        )
        return worker, None

    if mode == "WORKER_POOL":
        allowed_ids_raw = gateway_key.allowed_worker_ids or []
        if not allowed_ids_raw:
            raise _openai_http_error("API key has no permitted models configured in its worker pool.", "permission_denied", 403)
        allowed = {uuid.UUID(item) for item in allowed_ids_raw}

        # Query permitted workers to enforce access control
        w_res = await session.execute(
            select(Worker)
            .where(Worker.id.in_(allowed))
            .where(Worker.enabled.is_(True))
        )
        allowed_workers = list(w_res.scalars().all())
        if not allowed_workers:
            raise _openai_http_error("All permitted workers for this API key are currently offline or disabled.", "service_unavailable", 503)
        allowed_models = {w.model for w in allowed_workers}

        # Check model authorization
        if body.model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
            if is_virtual_group(body.model):
                group = get_group(body.model)
                if not any(model_matches_group(m, group.models) for m in allowed_models):
                    raise _openai_http_error(
                        f"API key is not authorized for any models in virtual group '{body.model}'. Allowed models for this key: {sorted(list(allowed_models))}",
                        "permission_denied",
                        403,
                    )
            elif body.model not in allowed_models:
                raise _openai_http_error(
                    f"API key is not authorized to access model '{body.model}'. Allowed models for this key: {sorted(list(allowed_models))}",
                    "permission_denied",
                    403,
                )

        worker = await Scheduler().select_worker(session, request_id=request_id, model=body.model, allowed_worker_ids=allowed, estimated_tokens=estimated_tokens)
        return worker, None

    if mode == "MODEL_GROUPS":
        allowed_groups_raw = getattr(gateway_key, "allowed_model_groups", None) or []
        if not allowed_groups_raw:
            raise _openai_http_error("API key has no permitted virtual tiers configured.", "permission_denied", 403)

        if body.model.lower() not in ("auto", "wrap-auto", "default", "wrap", "", "intelligent"):
            if is_virtual_group(body.model):
                if body.model not in allowed_groups_raw and body.model.lower() not in [g.lower() for g in allowed_groups_raw]:
                    raise _openai_http_error(
                        f"API key is not authorized for virtual tier '{body.model}'. Allowed tiers: {allowed_groups_raw}",
                        "permission_denied",
                        403,
                    )
            else:
                matched_group = False
                for g_id in allowed_groups_raw:
                    g = get_group(g_id)
                    if g and model_matches_group(body.model, g.models):
                        matched_group = True
                        break
                if not matched_group:
                    raise _openai_http_error(
                        f"API key is restricted to virtual tiers {allowed_groups_raw} and cannot access model '{body.model}'.",
                        "permission_denied",
                        403,
                    )

        from src.services.model_groups import expand_group_models
        expanded_models = []
        for g_id in allowed_groups_raw:
            g = get_group(g_id)
            if g:
                expanded_models.extend(expand_group_models(g.models))

        w_stmt = (
            select(Worker)
            .where(Worker.model.in_(expanded_models))
            .where(Worker.enabled.is_(True))
        )
        w_res = await session.execute(w_stmt)
        tier_workers = list(w_res.scalars().all())
        if not tier_workers:
            raise _openai_http_error("All workers participating in this API key's virtual tiers are currently offline or disabled.", "service_unavailable", 503)

        tier_worker_ids = {w.id for w in tier_workers}
        worker = await Scheduler().select_worker(session, request_id=request_id, model=body.model, allowed_worker_ids=tier_worker_ids, estimated_tokens=estimated_tokens)
    elif is_virtual_group(body.model):
        worker = await Scheduler().select_worker(session, request_id=request_id, model=body.model, estimated_tokens=estimated_tokens)
    else:
        routed_res = await get_intelligent_router().route(
            body,
            session=session,
            request_id=request_id,
            policy=gateway_key.routing_policy,
        )
        worker = routed_res[0] if isinstance(routed_res, tuple) else routed_res

    # If key reached budget cap and requested fallback to free tier, ensure worker is free
    if fallback_to_free and is_worker_or_credential_paid(worker):
        free_workers_res = await session.execute(
            select(Worker)
            .options(selectinload(Worker.provider), selectinload(Worker.credential))
            .where(Worker.enabled.is_(True))
        )
        all_online = list(free_workers_res.scalars().all())
        free_candidates = [w for w in all_online if not is_worker_or_credential_paid(w)]
        if not free_candidates:
            raise _openai_http_error(
                "Budget limit reached. Fallback to free tier was attempted, but no free tier workers are currently online.",
                "budget_exceeded",
                429,
            )
        worker = free_candidates[0]

    return worker, None


def _apply_api_key_scope(statement, gateway_key: GatewayApiKey):
    mode = gateway_key.worker_selection_mode or "AUTO"
    if mode == "SPECIFIC_WORKER" and gateway_key.specific_worker_id:
        return statement.where(Worker.id == gateway_key.specific_worker_id)
    if mode == "WORKER_POOL" and gateway_key.allowed_worker_ids:
        return statement.where(Worker.id.in_([uuid.UUID(item) for item in gateway_key.allowed_worker_ids]))
    if mode == "MODEL_GROUPS" and gateway_key.allowed_model_groups:
        from src.services.model_groups import get_group, expand_group_models
        expanded = []
        for g_id in gateway_key.allowed_model_groups:
            g = get_group(g_id)
            if g:
                expanded.extend(expand_group_models(g.models))
        if expanded:
            return statement.where(Worker.model.in_(expanded))
    return statement


def _final_response(
    model: str,
    content: str | None,
    tool_calls: list[dict] | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> dict:
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    else:
        message["content"] = None
    if tool_calls:
        message["tool_calls"] = tool_calls
    finish_reason = "tool_calls" if tool_calls else "stop"
    computed_total = total_tokens or ((input_tokens or 0) + (output_tokens or 0)) or None
    return {
        "id": f"chatcmpl-wrap-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(__import__("time").time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": computed_total,
        },
    }


