"""API routes for Workflow Analytics, Timeline, Deterministic Replay, and Metrics."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.schemas import (
    AnalyticsSummaryResponse,
    WorkflowMetricsResponse,
    WorkflowReplayResponse,
    WorkflowTimelineResponse,
)
from src.analytics.service import AnalyticsService
from src.db.session import get_session

router = APIRouter(tags=["Analytics"])


@router.get("/workflows/{workflow_run_id}/metrics", response_model=WorkflowMetricsResponse)
async def get_workflow_metrics(
    workflow_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> WorkflowMetricsResponse:
    """Fetch calculated performance and execution metrics for a specific workflow run."""
    metrics = await AnalyticsService.get_or_calculate_workflow_metrics(session, workflow_run_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Workflow run or metrics not found")

    return WorkflowMetricsResponse(
        workflow_run_id=metrics.workflow_run_id,
        status=metrics.status,
        is_partial=metrics.is_partial,
        wall_clock_duration_ms=metrics.wall_clock_duration_ms,
        total_task_execution_time_ms=metrics.total_task_execution_time_ms,
        critical_path_duration_ms=metrics.critical_path_duration_ms,
        successful_critical_path_duration_ms=metrics.successful_critical_path_duration_ms,
        queue_wait_time_ms=metrics.queue_wait_time_ms,
        scheduler_overhead_ms=metrics.scheduler_overhead_ms,
        retry_overhead_ms=metrics.retry_overhead_ms,
        max_concurrent_tasks=metrics.max_concurrent_tasks,
        parallelism_factor=metrics.parallelism_factor,
        observed_speedup_ratio=metrics.observed_speedup_ratio,
        total_attempts=metrics.total_attempts,
        total_retries=metrics.total_retries,
        max_retries_per_task=metrics.max_retries_per_task,
        failed_attempts=metrics.failed_attempts,
        successful_after_retry_count=metrics.successful_after_retry_count,
        metrics_metadata=metrics.metrics_metadata or {},
    )


@router.get("/workflows/{workflow_run_id}/timeline", response_model=WorkflowTimelineResponse)
async def get_workflow_timeline(
    workflow_run_id: str,
    session: AsyncSession = Depends(get_session),
) -> WorkflowTimelineResponse:
    """Return chronological event timeline for audit and execution tracing."""
    timeline = await AnalyticsService.get_timeline(session, workflow_run_id)
    if not timeline.get("events") and "status" not in timeline:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return WorkflowTimelineResponse(**timeline)


@router.get("/workflows/{workflow_run_id}/replay", response_model=WorkflowReplayResponse)
async def replay_workflow(
    workflow_run_id: str,
    strict: bool = Query(True),
    session: AsyncSession = Depends(get_session),
) -> WorkflowReplayResponse:
    """Execute deterministic state machine replay from persisted events to verify integrity."""
    result = await AnalyticsService.replay_workflow(session, workflow_run_id, strict=strict)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return WorkflowReplayResponse(**result)


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryResponse:
    """Return aggregate performance and throughput metrics across all historical workflows."""
    summary = await AnalyticsService.get_global_summary(session)
    return AnalyticsSummaryResponse(**summary)


@router.get("/stream/telemetry")
async def stream_telemetry(request: Request):
    """Live Server-Sent Events (SSE) telemetry stream for real-time mission control."""
    import asyncio
    import json
    from datetime import datetime, timezone
    from fastapi.responses import StreamingResponse
    from src.db.session import AsyncSessionLocal
    from src.services.cache import gateway_cache
    from src.api.routes.management import metrics_topbar

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                async with AsyncSessionLocal() as session:
                    topbar = await metrics_topbar(session)
                    c_stats = gateway_cache.stats()
                    payload = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "topbar": topbar,
                        "cache": c_stats,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(2.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
