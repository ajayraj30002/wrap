"""Unit tests for hardened metric semantics, retry accounting, and concurrency intervals."""

from datetime import datetime, timezone, timedelta
import pytest

from src.analytics.calculator import (
    compute_all_metrics,
    compute_concurrency_metrics,
    compute_retry_metrics,
)


def test_retry_accounting_attempt1_failure_attempt2_success():
    """Verify Section 10: Attempt 1 failure -> retry -> Attempt 2 success:

    total_attempts = 2, total_retries = 1, successful_after_retry = 1.
    """
    t0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    attempts = [
        {
            "task_id": "step-1",
            "attempt_number": 1,
            "status": "FAILED",
            "duration_ms": 120,
            "started_at": t0,
            "finished_at": t0 + timedelta(milliseconds=120),
        },
        {
            "task_id": "step-1",
            "attempt_number": 2,
            "status": "SUCCEEDED",
            "duration_ms": 150,
            "started_at": t0 + timedelta(milliseconds=150),
            "finished_at": t0 + timedelta(milliseconds=300),
        },
    ]

    metrics = compute_retry_metrics(attempts)
    assert metrics["total_attempts"] == 2
    assert metrics["total_retries"] == 1
    assert metrics["max_retries_per_task"] == 1
    assert metrics["failed_attempts"] == 1
    assert metrics["successful_after_retry_count"] == 1
    assert metrics["retry_overhead_ms"] == 120


def test_retry_accounting_three_attempts_all_failed():
    """Verify Section 10: Attempt 1 fail -> Attempt 2 fail -> Attempt 3 fail:

    total_attempts = 3, total_retries = 2, successful_after_retry = 0.
    """
    t0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    attempts = [
        {
            "task_id": "node-A",
            "attempt_number": 1,
            "status": "FAILED",
            "duration_ms": 100,
            "started_at": t0,
            "finished_at": t0 + timedelta(milliseconds=100),
        },
        {
            "task_id": "node-A",
            "attempt_number": 2,
            "status": "FAILED",
            "duration_ms": 110,
            "started_at": t0 + timedelta(milliseconds=120),
            "finished_at": t0 + timedelta(milliseconds=230),
        },
        {
            "task_id": "node-A",
            "attempt_number": 3,
            "status": "FAILED",
            "duration_ms": 130,
            "started_at": t0 + timedelta(milliseconds=250),
            "finished_at": t0 + timedelta(milliseconds=380),
        },
    ]

    metrics = compute_retry_metrics(attempts)
    assert metrics["total_attempts"] == 3
    assert metrics["total_retries"] == 2
    assert metrics["max_retries_per_task"] == 2
    assert metrics["failed_attempts"] == 3
    assert metrics["successful_after_retry_count"] == 0
    assert metrics["retry_overhead_ms"] == 340


def test_separated_queue_wait_and_orchestration_semantics():
    """Verify Section 5, 6, 7: Distinct semantics for workflow queue wait, task queue wait,

    scheduler overhead, orchestration gap, and speedup ratio.
    """
    t_created = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    t_wf_start = t_created + timedelta(milliseconds=45)  # Workflow queue wait = 45ms
    t_ready = t_wf_start + timedelta(milliseconds=10)
    t_task_start = t_ready + timedelta(milliseconds=30)  # Task queue wait = 30ms
    t_task_finish = t_task_start + timedelta(milliseconds=200)
    t_wf_finish = t_task_finish + timedelta(milliseconds=50)  # Wall clock = 290ms

    events = [
        {"event_type": "TASK_READY", "task_id": "n1", "timestamp": t_ready},
        {"event_type": "TASK_STARTED", "task_id": "n1", "timestamp": t_task_start},
    ]
    nodes = [{"id": "n1", "depends_on": [], "duration_ms": 200, "status": "success"}]
    attempts = [{
        "task_id": "n1",
        "attempt_number": 1,
        "status": "SUCCEEDED",
        "started_at": t_task_start,
        "finished_at": t_task_finish,
        "duration_ms": 200,
    }]

    # Case A: No sequential baseline -> observed_speedup_ratio MUST be None
    res = compute_all_metrics(
        workflow_status="COMPLETED",
        created_at=t_created,
        started_at=t_wf_start,
        finished_at=t_wf_finish,
        nodes=nodes,
        attempts=attempts,
        events=events,
        sequential_baseline_ms=None,
        scheduler_overhead_ms=12,  # Actual measured router latency
    )

    assert res["workflow_queue_wait_ms"] == 45
    assert res["task_queue_wait_ms"] == 30
    assert res["wall_clock_duration_ms"] == 290
    assert res["critical_path_duration_ms"] == 200
    # Orchestration gap = wall_clock (290) - critical_path (200) = 90ms
    assert res["orchestration_gap_ms"] == 90
    # Real scheduler overhead = 12ms (not gap!)
    assert res["scheduler_overhead_ms"] == 12
    # Speedup ratio must be strictly None when no baseline exists
    assert res["observed_speedup_ratio"] is None
    # Parallelism factor = 200 / 290 = 0.69
    assert res["parallelism_factor"] == 0.69

    # Case B: With measured sequential baseline of 400ms -> observed_speedup_ratio = 400 / 290 = 1.38
    res_b = compute_all_metrics(
        workflow_status="COMPLETED",
        created_at=t_created,
        started_at=t_wf_start,
        finished_at=t_wf_finish,
        nodes=nodes,
        attempts=attempts,
        events=events,
        sequential_baseline_ms=400,
        scheduler_overhead_ms=12,
    )
    assert res_b["observed_speedup_ratio"] == 1.38


def test_adversarial_concurrency_intervals():
    """Verify Section 11: Adversarial concurrency edge cases:

    - Simultaneous starts
    - Simultaneous finishes
    - Unfinished/cancelled attempts capped by workflow finished timestamp
    - Sequential retries that do not falsely increase peak concurrency
    """
    t0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(milliseconds=100)
    t2 = t0 + timedelta(milliseconds=200)
    t3 = t0 + timedelta(milliseconds=300)

    # 3 tasks start at the EXACT same millisecond t0, 2 finish at t1, 1 finishes at t2
    # Peak concurrency must be 3
    simultaneous_attempts = [
        {"task_id": "t1", "started_at": t0, "finished_at": t1},
        {"task_id": "t2", "started_at": t0, "finished_at": t1},
        {"task_id": "t3", "started_at": t0, "finished_at": t2},
    ]
    assert compute_concurrency_metrics(simultaneous_attempts) == 3

    # Retried task: attempt 1 runs t0..t1, attempt 2 runs t1..t2
    # They should NOT overlap, peak concurrency = 1
    retry_attempts = [
        {"task_id": "retried", "attempt_number": 1, "started_at": t0, "finished_at": t1},
        {"task_id": "retried", "attempt_number": 2, "started_at": t1, "finished_at": t2},
    ]
    assert compute_concurrency_metrics(retry_attempts) == 1

    # Unfinished task in a cancelled/terminal workflow: capped at workflow_finished_at
    unfinished_attempts = [
        {"task_id": "hung_task", "started_at": t0, "finished_at": None},
        {"task_id": "normal_task", "started_at": t1, "finished_at": t2},
    ]
    # Capped at t3
    peak = compute_concurrency_metrics(unfinished_attempts, workflow_finished_at=t3)
    assert peak == 2
