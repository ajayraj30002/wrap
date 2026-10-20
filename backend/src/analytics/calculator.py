"""Calculation engine for concurrency, retry, parallelism, and workflow performance metrics."""

from datetime import datetime, timezone
from typing import Any

from src.analytics.critical_path import calculate_critical_path


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_concurrency_metrics(
    attempts: list[dict[str, Any]],
    workflow_finished_at: datetime | None = None,
) -> int:
    """Calculate the maximum concurrent tasks observed from task attempt lifecycles.
    
    Each attempt should contain started_at and finished_at (datetime or float/int timestamp).
    Attempts that finished or failed are capped by their terminal timestamp.
    Unfinished attempts are capped at workflow_finished_at to ensure terminal workflows
    do not retain indefinitely active attempts.
    """
    if not attempts:
        return 0

    points: list[tuple[float, int]] = []
    wf_end_ts = _to_utc(workflow_finished_at).timestamp() if workflow_finished_at else None

    for a in attempts:
        started = a.get("started_at")
        finished = a.get("finished_at")

        if not started:
            continue

        if isinstance(started, datetime):
            start_ts = _to_utc(started).timestamp()
        else:
            start_ts = float(started)
        # Point: (timestamp, +1 for start)
        points.append((start_ts, 1))

        if finished:
            if isinstance(finished, datetime):
                finish_ts = _to_utc(finished).timestamp()
            else:
                finish_ts = float(finished)
            # Point: (timestamp, -1 for end)
            points.append((finish_ts, -1))
        elif wf_end_ts and wf_end_ts >= start_ts:
            points.append((wf_end_ts, -1))

    if not points:
        return 0

    # Sort primarily by timestamp. When timestamps are identical, ends (-1) come before starts (+1)
    # (half-open interval semantics [start, end)) so completed attempts and sequential retries
    # do not falsely register as overlapping concurrency.
    points.sort(key=lambda p: (p[0], p[1]))

    max_active = 0
    current_active = 0

    for _, delta in points:
        current_active += delta
        if current_active > max_active:
            max_active = current_active

    return max(0, max_active)


def compute_retry_metrics(attempts: list[dict[str, Any]]) -> dict[str, int]:
    """Calculate attempt and retry metrics explicitly from attempt records."""
    if not attempts:
        return {
            "total_attempts": 0,
            "total_retries": 0,
            "max_retries_per_task": 0,
            "retry_overhead_ms": 0,
            "failed_attempts": 0,
            "successful_after_retry_count": 0,
        }

    task_attempts: dict[str, list[dict[str, Any]]] = {}
    failed_attempts_count = 0
    retry_overhead_ms = 0

    for a in attempts:
        tid = str(a.get("task_id", ""))
        if tid not in task_attempts:
            task_attempts[tid] = []
        task_attempts[tid].append(a)

        status = str(a.get("status", "")).upper()
        if status in ("FAILED", "RETRYING"):
            failed_attempts_count += 1
            duration = a.get("duration_ms") or 0
            retry_overhead_ms += int(duration)

    total_attempts = len(attempts)
    total_retries = 0
    max_retries = 0
    successful_after_retry = 0

    for tid, t_atts in task_attempts.items():
        att_count = len(t_atts)
        retries = max(0, att_count - 1)
        total_retries += retries
        if retries > max_retries:
            max_retries = retries

        # Check if task succeeded after having > 1 attempt
        has_success = any(str(x.get("status", "")).upper() in ("SUCCEEDED", "SUCCESS") for x in t_atts)
        if has_success and att_count > 1:
            successful_after_retry += 1

    return {
        "total_attempts": total_attempts,
        "total_retries": total_retries,
        "max_retries_per_task": max_retries,
        "retry_overhead_ms": retry_overhead_ms,
        "failed_attempts": failed_attempts_count,
        "successful_after_retry_count": successful_after_retry,
    }


def compute_all_metrics(
    *,
    workflow_status: str,
    created_at: datetime | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    nodes: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
    sequential_baseline_ms: int | None = None,
    planning_ms: int = 0,
    scheduler_overhead_ms: int | None = None,
    synthesis_overhead_ms: int | None = None,
    telemetry_overhead_ms: int | None = None,
) -> dict[str, Any]:
    """Compute complete workflow execution metrics with strict semantic separation."""
    c_at = _to_utc(created_at)
    s_at = _to_utc(started_at)
    f_at = _to_utc(finished_at)

    # 1. Wall-clock duration
    wall_clock_duration_ms: int | None = None
    if s_at and f_at:
        wall_clock_duration_ms = max(0, int((f_at - s_at).total_seconds() * 1000))
    elif s_at:
        wall_clock_duration_ms = max(0, int((datetime.now(timezone.utc) - s_at).total_seconds() * 1000))

    # 2. Queue wait times:
    # 2a. Workflow queue wait (created_at -> started_at)
    workflow_queue_wait_ms: int = 0
    if c_at and s_at:
        workflow_queue_wait_ms = max(0, int((s_at - c_at).total_seconds() * 1000))

    # 2b. Task queue wait (TASK_READY -> TASK_STARTED per task)
    task_queue_wait_ms: int = 0
    if events:
        ready_times: dict[str, datetime] = {}
        start_times: dict[str, datetime] = {}
        for ev in events:
            etype = ev.get("event_type")
            tid = ev.get("task_id")
            ts = ev.get("timestamp")
            if not tid or not ts:
                continue
            dt_ts = _to_utc(ts) if isinstance(ts, datetime) else None
            if dt_ts is None and isinstance(ts, str):
                try:
                    dt_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    pass
            if not dt_ts:
                continue
            if etype == "TASK_READY" and tid not in ready_times:
                ready_times[tid] = dt_ts
            elif etype == "TASK_STARTED" and tid not in start_times:
                start_times[tid] = dt_ts

        waits = []
        for tid, r_time in ready_times.items():
            if tid in start_times:
                s_time = start_times[tid]
                wait = max(0, int((s_time - r_time).total_seconds() * 1000))
                waits.append(wait)
        if waits:
            task_queue_wait_ms = sum(waits)

    # Legacy queue_wait_time_ms compatibility
    queue_wait_time_ms = task_queue_wait_ms if task_queue_wait_ms > 0 else workflow_queue_wait_ms

    # 3. Task execution duration
    total_task_execution_time_ms = sum(
        int(a.get("duration_ms") or 0) for a in attempts
    )
    if not total_task_execution_time_ms and nodes:
        total_task_execution_time_ms = sum(
            int(n.get("duration_ms") or n.get("latency_ms") or 0) for n in nodes
        )

    # 4. Critical path
    crit_all = calculate_critical_path(nodes, only_successful=False)
    crit_succ = calculate_critical_path(nodes, only_successful=True)
    observed_crit_ms = crit_all.critical_path_duration_ms
    successful_crit_ms = crit_succ.critical_path_duration_ms

    # 5. Orchestration gap: wall clock duration minus observed critical path
    # (Observed residual gap; not pure scheduler CPU time)
    orchestration_gap_ms: int = 0
    if wall_clock_duration_ms is not None and observed_crit_ms is not None:
        orchestration_gap_ms = max(0, wall_clock_duration_ms - observed_crit_ms)

    # 5b. Instrumented scheduler overhead (real measured scheduler/router time)
    real_scheduler_overhead_ms = max(0, int(scheduler_overhead_ms or 0))

    # 5c. Synthesis overhead (real measured synthesis node latency)
    real_synthesis_overhead_ms = max(0, int(synthesis_overhead_ms or 0))
    if real_synthesis_overhead_ms == 0 and nodes:
        for n in nodes:
            if n.get("type") == "synthesis" or n.get("node_type") == "synthesis" or n.get("id") == "synthesis":
                real_synthesis_overhead_ms += int(n.get("duration_ms") or n.get("latency_ms") or 0)

    # 5d. Telemetry overhead (real measured logging and metrics computation time)
    real_telemetry_overhead_ms = max(0, int(telemetry_overhead_ms or 0))

    # 6. Concurrency
    max_concurrent = compute_concurrency_metrics(attempts, workflow_finished_at=finished_at)
    if max_concurrent == 0 and len(nodes) == 1:
        max_concurrent = 1

    # 7. Retry metrics
    retry_metrics = compute_retry_metrics(attempts)

    # 8. Parallelism factor
    parallelism_factor: float | None = None
    if wall_clock_duration_ms and wall_clock_duration_ms > 0:
        parallelism_factor = round(total_task_execution_time_ms / wall_clock_duration_ms, 2)
    elif total_task_execution_time_ms > 0:
        parallelism_factor = 1.0

    # 9. True speedup ratio (ONLY when an actual sequential baseline is provided; strictly null otherwise)
    observed_speedup_ratio: float | None = None
    if sequential_baseline_ms is not None and wall_clock_duration_ms and wall_clock_duration_ms > 0:
        observed_speedup_ratio = round(sequential_baseline_ms / wall_clock_duration_ms, 2)

    is_partial = workflow_status in ("PENDING", "RUNNING")

    return {
        "status": workflow_status,
        "is_partial": is_partial,
        "wall_clock_duration_ms": wall_clock_duration_ms,
        "total_task_execution_time_ms": total_task_execution_time_ms,
        "critical_path_duration_ms": observed_crit_ms,
        "successful_critical_path_duration_ms": successful_crit_ms,
        "critical_path_nodes": crit_all.critical_path_nodes,
        "successful_critical_path_nodes": crit_succ.critical_path_nodes,
        "queue_wait_time_ms": queue_wait_time_ms,
        "workflow_queue_wait_ms": workflow_queue_wait_ms,
        "task_queue_wait_ms": task_queue_wait_ms,
        "scheduler_overhead_ms": real_scheduler_overhead_ms,
        "orchestration_gap_ms": orchestration_gap_ms,
        "synthesis_overhead_ms": real_synthesis_overhead_ms,
        "telemetry_overhead_ms": real_telemetry_overhead_ms,
        "retry_overhead_ms": retry_metrics["retry_overhead_ms"],
        "max_concurrent_tasks": max_concurrent,
        "parallelism_factor": parallelism_factor,
        "observed_speedup_ratio": observed_speedup_ratio,
        "total_attempts": retry_metrics["total_attempts"],
        "total_retries": retry_metrics["total_retries"],
        "max_retries_per_task": retry_metrics["max_retries_per_task"],
        "failed_attempts": retry_metrics["failed_attempts"],
        "successful_after_retry_count": retry_metrics["successful_after_retry_count"],
        "planning_ms": planning_ms,
    }
