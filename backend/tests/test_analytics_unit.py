"""Unit tests for the analytics subsystem: enums, state machine, critical path, metrics, and redaction."""

import pytest
from datetime import datetime, timezone, timedelta

from src.analytics.enums import TaskStatus, WorkflowEventType, WorkflowStatus
from src.analytics.critical_path import calculate_critical_path, CriticalPathResult
from src.analytics.calculator import (
    compute_all_metrics,
    compute_concurrency_metrics,
    compute_retry_metrics,
)
from src.analytics.redaction import sanitize_payload
from src.analytics.state_machine import (
    InvalidStateTransitionError,
    validate_task_transition,
    validate_workflow_transition,
)


def test_enums_and_values():
    assert WorkflowEventType.WORKFLOW_CREATED.value == "WORKFLOW_CREATED"
    assert WorkflowEventType.WORKFLOW_STARTED.value == "WORKFLOW_STARTED"
    assert WorkflowEventType.WORKFLOW_COMPLETED.value == "WORKFLOW_COMPLETED"
    assert WorkflowEventType.WORKFLOW_FAILED.value == "WORKFLOW_FAILED"
    assert WorkflowEventType.WORKFLOW_CANCELLED.value == "WORKFLOW_CANCELLED"

    assert WorkflowEventType.TASK_READY.value == "TASK_READY"
    assert WorkflowEventType.TASK_STARTED.value == "TASK_STARTED"
    assert WorkflowEventType.TASK_RETRYING.value == "TASK_RETRYING"
    assert WorkflowEventType.TASK_SUCCEEDED.value == "TASK_SUCCEEDED"
    assert WorkflowEventType.TASK_FAILED.value == "TASK_FAILED"
    assert WorkflowEventType.TASK_CANCELLED.value == "TASK_CANCELLED"


def test_workflow_state_transitions_valid():
    # PENDING -> RUNNING
    s1 = validate_workflow_transition(WorkflowStatus.PENDING, WorkflowEventType.WORKFLOW_STARTED, "wf-1")
    assert s1 == WorkflowStatus.RUNNING

    # RUNNING -> COMPLETED
    s2 = validate_workflow_transition(WorkflowStatus.RUNNING, WorkflowEventType.WORKFLOW_COMPLETED, "wf-1")
    assert s2 == WorkflowStatus.COMPLETED

    # RUNNING -> FAILED
    s3 = validate_workflow_transition(WorkflowStatus.RUNNING, WorkflowEventType.WORKFLOW_FAILED, "wf-1")
    assert s3 == WorkflowStatus.FAILED

    # RUNNING -> CANCELLED
    s4 = validate_workflow_transition(WorkflowStatus.RUNNING, WorkflowEventType.WORKFLOW_CANCELLED, "wf-1")
    assert s4 == WorkflowStatus.CANCELLED


def test_workflow_state_transitions_invalid():
    # COMPLETED is terminal
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition(WorkflowStatus.COMPLETED, WorkflowEventType.WORKFLOW_STARTED, "wf-1")

    # FAILED is terminal
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition(WorkflowStatus.FAILED, WorkflowEventType.WORKFLOW_COMPLETED, "wf-1")

    # PENDING cannot transition straight to COMPLETED without starting
    with pytest.raises(InvalidStateTransitionError):
        validate_workflow_transition(WorkflowStatus.PENDING, WorkflowEventType.WORKFLOW_COMPLETED, "wf-1")


def test_task_state_transitions():
    # PENDING -> READY
    t1 = validate_task_transition(TaskStatus.PENDING, WorkflowEventType.TASK_READY, "task-1")
    assert t1 == TaskStatus.READY

    # READY -> RUNNING
    t2 = validate_task_transition(TaskStatus.READY, WorkflowEventType.TASK_STARTED, "task-1")
    assert t2 == TaskStatus.RUNNING

    # RUNNING -> RETRYING
    t3 = validate_task_transition(TaskStatus.RUNNING, WorkflowEventType.TASK_RETRYING, "task-1")
    assert t3 == TaskStatus.RETRYING

    # RETRYING -> RUNNING
    t4 = validate_task_transition(TaskStatus.RETRYING, WorkflowEventType.TASK_STARTED, "task-1")
    assert t4 == TaskStatus.RUNNING

    # RUNNING -> SUCCEEDED
    t5 = validate_task_transition(TaskStatus.RUNNING, WorkflowEventType.TASK_SUCCEEDED, "task-1")
    assert t5 == TaskStatus.SUCCEEDED

    # Invalid: SUCCEEDED -> RUNNING
    with pytest.raises(InvalidStateTransitionError):
        validate_task_transition(TaskStatus.SUCCEEDED, WorkflowEventType.TASK_STARTED, "task-1")

    # Invalid: CANCELLED -> SUCCEEDED
    with pytest.raises(InvalidStateTransitionError):
        validate_task_transition(TaskStatus.CANCELLED, WorkflowEventType.TASK_SUCCEEDED, "task-1")


def test_critical_path_section_32_specification():
    """Verify Section 32 known DAG:
    A = 100ms
    B = 400ms
    C depends on A = 200ms
    D depends on A,B = 100ms
    E depends on C,D = 300ms
    A -> C -> E = 600ms
    B -> D -> E = 800ms
    Therefore critical_path = 800ms
    """
    nodes = {
        "A": {"id": "A", "depends_on": [], "duration_ms": 100, "status": "success"},
        "B": {"id": "B", "depends_on": [], "duration_ms": 400, "status": "success"},
        "C": {"id": "C", "depends_on": ["A"], "duration_ms": 200, "status": "success"},
        "D": {"id": "D", "depends_on": ["A", "B"], "duration_ms": 100, "status": "success"},
        "E": {"id": "E", "depends_on": ["C", "D"], "duration_ms": 300, "status": "success"},
    }
    result = calculate_critical_path(nodes)
    assert result.critical_path_duration_ms == 800
    assert result.critical_path_nodes == ["B", "D", "E"]
    assert result.node_earliest_starts["A"] == 0
    assert result.node_finish_times["A"] == 100
    assert result.node_earliest_starts["B"] == 0
    assert result.node_finish_times["B"] == 400
    assert result.node_earliest_starts["C"] == 100
    assert result.node_finish_times["C"] == 300
    assert result.node_earliest_starts["D"] == 400
    assert result.node_finish_times["D"] == 500
    assert result.node_earliest_starts["E"] == 500
    assert result.node_finish_times["E"] == 800


def test_critical_path_edge_cases():
    # 1. Zero nodes
    res_zero = calculate_critical_path([])
    assert res_zero.critical_path_duration_ms == 0
    assert res_zero.critical_path_nodes == []

    # 2. Single node
    res_single = calculate_critical_path([{"id": "single", "depends_on": [], "duration_ms": 150}])
    assert res_single.critical_path_duration_ms == 150
    assert res_single.critical_path_nodes == ["single"]

    # 3. Linear chain
    res_linear = calculate_critical_path([
        {"id": "1", "depends_on": [], "duration_ms": 50},
        {"id": "2", "depends_on": ["1"], "duration_ms": 70},
        {"id": "3", "depends_on": ["2"], "duration_ms": 30},
    ])
    assert res_linear.critical_path_duration_ms == 150
    assert res_linear.critical_path_nodes == ["1", "2", "3"]

    # 4. Diamond DAG
    res_diamond = calculate_critical_path([
        {"id": "start", "depends_on": [], "duration_ms": 100},
        {"id": "left", "depends_on": ["start"], "duration_ms": 200},
        {"id": "right", "depends_on": ["start"], "duration_ms": 400},
        {"id": "end", "depends_on": ["left", "right"], "duration_ms": 100},
    ])
    assert res_diamond.critical_path_duration_ms == 600
    assert res_diamond.critical_path_nodes == ["start", "right", "end"]

    # 5. Missing duration data
    res_missing = calculate_critical_path([
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": ["a"], "duration_ms": None},
    ])
    assert res_missing.critical_path_duration_ms == 0

    # 6. Cycle detection
    with pytest.raises(ValueError, match="Cycle detected"):
        calculate_critical_path([
            {"id": "cycle1", "depends_on": ["cycle2"], "duration_ms": 10},
            {"id": "cycle2", "depends_on": ["cycle1"], "duration_ms": 10},
        ])


def test_critical_path_successful_vs_observed():
    nodes = [
        {"id": "A", "depends_on": [], "duration_ms": 100, "status": "success"},
        {"id": "B_failed", "depends_on": [], "duration_ms": 500, "status": "failed"},
        {"id": "C", "depends_on": ["A"], "duration_ms": 200, "status": "success"},
    ]
    observed = calculate_critical_path(nodes, only_successful=False)
    successful = calculate_critical_path(nodes, only_successful=True)

    assert observed.critical_path_duration_ms == 500
    assert observed.critical_path_nodes == ["B_failed"]

    assert successful.critical_path_duration_ms == 300
    assert successful.critical_path_nodes == ["A", "C"]


def test_concurrency_metrics():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    # Three tasks overlapping in time
    attempts = [
        {"task_id": "t1", "started_at": t0, "finished_at": t0 + timedelta(seconds=10)},
        {"task_id": "t2", "started_at": t0 + timedelta(seconds=2), "finished_at": t0 + timedelta(seconds=8)},
        {"task_id": "t3", "started_at": t0 + timedelta(seconds=4), "finished_at": t0 + timedelta(seconds=6)},
    ]
    max_c = compute_concurrency_metrics(attempts)
    assert max_c == 3

    # Simultaneous start and end
    simul = [
        {"task_id": "s1", "started_at": t0, "finished_at": t0 + timedelta(seconds=5)},
        {"task_id": "s2", "started_at": t0, "finished_at": t0 + timedelta(seconds=5)},
    ]
    assert compute_concurrency_metrics(simul) == 2


def test_retry_metrics():
    attempts = [
        {"task_id": "t1", "attempt_number": 1, "status": "FAILED", "duration_ms": 120},
        {"task_id": "t1", "attempt_number": 2, "status": "RETRYING", "duration_ms": 150},
        {"task_id": "t1", "attempt_number": 3, "status": "SUCCEEDED", "duration_ms": 100},
        {"task_id": "t2", "attempt_number": 1, "status": "SUCCEEDED", "duration_ms": 200},
    ]
    retries = compute_retry_metrics(attempts)
    assert retries["total_attempts"] == 4
    assert retries["total_retries"] == 2
    assert retries["max_retries_per_task"] == 2
    assert retries["retry_overhead_ms"] == 270
    assert retries["failed_attempts"] == 2
    assert retries["successful_after_retry_count"] == 1


def test_parallelism_vs_true_speedup():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(milliseconds=500)

    nodes = [
        {"id": "n1", "depends_on": [], "duration_ms": 500, "status": "success"},
        {"id": "n2", "depends_on": [], "duration_ms": 500, "status": "success"},
    ]
    attempts = [
        {"task_id": "n1", "attempt_number": 1, "started_at": t0, "finished_at": t_end, "duration_ms": 500, "status": "SUCCEEDED"},
        {"task_id": "n2", "attempt_number": 1, "started_at": t0, "finished_at": t_end, "duration_ms": 500, "status": "SUCCEEDED"},
    ]

    # Without baseline: observed_speedup_ratio MUST be None (do NOT invent one!)
    m_no_base = compute_all_metrics(
        workflow_status="COMPLETED",
        created_at=t0,
        started_at=t0,
        finished_at=t_end,
        nodes=nodes,
        attempts=attempts,
        sequential_baseline_ms=None,
    )
    assert m_no_base["parallelism_factor"] == 2.0
    assert m_no_base["observed_speedup_ratio"] is None

    # With measured baseline
    m_base = compute_all_metrics(
        workflow_status="COMPLETED",
        created_at=t0,
        started_at=t0,
        finished_at=t_end,
        nodes=nodes,
        attempts=attempts,
        sequential_baseline_ms=1000,
    )
    assert m_base["parallelism_factor"] == 2.0
    assert m_base["observed_speedup_ratio"] == 2.0


def test_security_redaction_secrets():
    """Verify secrets are redacted before persistence."""
    dirty_payload = {
        "api_key": "gsk_secret_1234567890abcdef",
        "authorization": "Bearer wrap_longsecretkeyhere987654321",
        "worker_id": "worker-1",
        "nested": {
            "password": "my_password",
            "provider_credential": "raw_secret_value",
            "safe_field": "public_model_id",
        },
        "headers": ["Authorization: Bearer sk-antigravity-9999", "Content-Type: application/json"],
    }
    clean = sanitize_payload(dirty_payload)

    assert clean["api_key"] == "[REDACTED]"
    assert clean["authorization"] == "[REDACTED]"
    assert clean["worker_id"] == "worker-1"
    assert clean["nested"]["password"] == "[REDACTED]"
    assert clean["nested"]["provider_credential"] == "[REDACTED]"
    assert clean["nested"]["safe_field"] == "public_model_id"
    assert "Bearer [REDACTED]" in clean["headers"][0]
    assert clean["headers"][1] == "Content-Type: application/json"
