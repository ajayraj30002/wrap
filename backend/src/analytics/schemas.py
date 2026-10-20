"""Pydantic schemas for analytics API responses."""

import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict


class WorkflowMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_run_id: uuid.UUID
    status: str
    is_partial: bool = False
    wall_clock_duration_ms: int | None = None
    total_task_execution_time_ms: int | None = None
    critical_path_duration_ms: int | None = None
    successful_critical_path_duration_ms: int | None = None
    queue_wait_time_ms: int | None = None
    workflow_queue_wait_ms: int | None = None
    task_queue_wait_ms: int | None = None
    scheduler_overhead_ms: int | None = None
    orchestration_gap_ms: int | None = None
    synthesis_overhead_ms: int | None = None
    telemetry_overhead_ms: int | None = None
    retry_overhead_ms: int | None = None
    max_concurrent_tasks: int | None = None
    parallelism_factor: float | None = None
    observed_speedup_ratio: float | None = None
    total_attempts: int = 0
    total_retries: int = 0
    max_retries_per_task: int = 0
    failed_attempts: int = 0
    successful_after_retry_count: int = 0
    metrics_metadata: dict[str, Any] = {}


class TimelineEventItem(BaseModel):
    event_id: str
    logical_sequence: int
    event_type: str
    task_id: str | None = None
    attempt: int = 1
    timestamp: str | None = None
    elapsed_ms: int = 0
    payload: dict[str, Any] = {}


class WorkflowTimelineResponse(BaseModel):
    workflow_run_id: str
    status: str
    requested_model: str
    executed_model: str | None = None
    provider: str | None = None
    execution_mode: str
    events_count: int
    events: list[TimelineEventItem]


class WorkflowReplayResponse(BaseModel):
    workflow_run_id: str
    replay_valid: bool
    reconstructed_status: str
    current_status: str
    applied_events_count: int
    reconstructed_wall_clock_ms: int | None = None
    tasks: dict[str, Any]
    comparison: dict[str, Any]


class AnalyticsSummaryResponse(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    cancelled_runs: int
    success_rate_percent: float
    avg_wall_clock_duration_ms: float
    avg_critical_path_duration_ms: float
    avg_parallelism_factor: float
    total_retries: int
    peak_concurrency: int
    total_workflows: int = 0
    completed_workflows: int = 0
    failed_workflows: int = 0
    average_wall_clock_ms: float = 0.0
    average_critical_path_ms: float = 0.0
    average_parallelism_factor: float = 1.0
    total_attempts: int = 0
    retry_rate: float = 0.0
