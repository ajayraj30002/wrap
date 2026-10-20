"""Deterministic replay state machine tests."""

import pytest
from datetime import datetime, timezone, timedelta

from src.analytics.enums import TaskStatus, WorkflowEventType, WorkflowStatus
from src.analytics.state_machine import (
    InvalidStateTransitionError,
    WorkflowReplayMachine,
)


def test_deterministic_replay_success():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    machine = WorkflowReplayMachine(workflow_run_id="wf-101")

    events = [
        {"logical_sequence": 1, "event_type": "WORKFLOW_CREATED", "timestamp": t0, "payload": {}},
        {"logical_sequence": 2, "event_type": "WORKFLOW_STARTED", "timestamp": t0 + timedelta(milliseconds=10), "payload": {}},
        {"logical_sequence": 3, "event_type": "TASK_READY", "task_id": "step1", "timestamp": t0 + timedelta(milliseconds=15), "payload": {}},
        {
            "logical_sequence": 4,
            "event_type": "TASK_STARTED",
            "task_id": "step1",
            "attempt": 1,
            "timestamp": t0 + timedelta(milliseconds=20),
            "payload": {"worker_id": "w-groq-1", "provider": "groq", "model": "qwen3.8-27b"},
        },
        {
            "logical_sequence": 5,
            "event_type": "TASK_SUCCEEDED",
            "task_id": "step1",
            "attempt": 1,
            "timestamp": t0 + timedelta(milliseconds=150),
            "payload": {"duration_ms": 130, "output_hash": "hash_abc"},
        },
        {"logical_sequence": 6, "event_type": "WORKFLOW_COMPLETED", "timestamp": t0 + timedelta(milliseconds=160), "payload": {}},
    ]

    for ev in events:
        machine.apply_event(ev)

    state = machine.state
    assert state.status == WorkflowStatus.COMPLETED
    assert state.applied_events == 6
    assert state.wall_clock_duration_ms == 150  # 160 - 10
    assert "step1" in state.tasks
    t1 = state.tasks["step1"]
    assert t1.status == TaskStatus.SUCCEEDED
    assert t1.worker_id == "w-groq-1"
    assert t1.provider == "groq"
    assert t1.model == "qwen3.8-27b"
    assert t1.duration_ms == 130
    assert len(t1.attempts) == 1
    assert t1.attempts[0].status == "SUCCEEDED"


def test_deterministic_replay_with_retries():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    machine = WorkflowReplayMachine(workflow_run_id="wf-retry-1")

    events = [
        {"logical_sequence": 1, "event_type": "WORKFLOW_CREATED", "timestamp": t0},
        {"logical_sequence": 2, "event_type": "WORKFLOW_STARTED", "timestamp": t0 + timedelta(milliseconds=5)},
        {"logical_sequence": 3, "event_type": "TASK_READY", "task_id": "call-1", "timestamp": t0 + timedelta(milliseconds=10)},
        {
            "logical_sequence": 4,
            "event_type": "TASK_STARTED",
            "task_id": "call-1",
            "attempt": 1,
            "timestamp": t0 + timedelta(milliseconds=15),
            "payload": {"worker_id": "w1", "provider": "groq", "model": "m1"},
        },
        {
            "logical_sequence": 5,
            "event_type": "TASK_RETRYING",
            "task_id": "call-1",
            "attempt": 1,
            "timestamp": t0 + timedelta(milliseconds=60),
            "payload": {"duration_ms": 45, "error_type": "RateLimitError"},
        },
        {
            "logical_sequence": 6,
            "event_type": "TASK_STARTED",
            "task_id": "call-1",
            "attempt": 2,
            "timestamp": t0 + timedelta(milliseconds=100),
            "payload": {"worker_id": "w2", "provider": "cerebras", "model": "m2"},
        },
        {
            "logical_sequence": 7,
            "event_type": "TASK_SUCCEEDED",
            "task_id": "call-1",
            "attempt": 2,
            "timestamp": t0 + timedelta(milliseconds=180),
            "payload": {"duration_ms": 80},
        },
        {"logical_sequence": 8, "event_type": "WORKFLOW_COMPLETED", "timestamp": t0 + timedelta(milliseconds=190)},
    ]

    for ev in events:
        machine.apply_event(ev)

    task = machine.state.tasks["call-1"]
    assert task.status == TaskStatus.SUCCEEDED
    assert task.current_attempt == 2
    assert len(task.attempts) == 2
    assert task.attempts[0].status == "RETRYING"
    assert task.attempts[0].provider == "groq"
    assert task.attempts[1].status == "SUCCEEDED"
    assert task.attempts[1].provider == "cerebras"


def test_deterministic_replay_out_of_order_error():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    machine = WorkflowReplayMachine(workflow_run_id="wf-order")

    machine.apply_event({"logical_sequence": 2, "event_type": "WORKFLOW_CREATED", "timestamp": t0})
    # sequence 1 arriving after sequence 2 must raise ValueError
    with pytest.raises(ValueError, match="Out of order event"):
        machine.apply_event({"logical_sequence": 1, "event_type": "WORKFLOW_STARTED", "timestamp": t0})


def test_deterministic_replay_invalid_transition_error():
    t0 = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)
    machine = WorkflowReplayMachine(workflow_run_id="wf-invalid")

    machine.apply_event({"logical_sequence": 1, "event_type": "WORKFLOW_CREATED", "timestamp": t0})
    machine.apply_event({"logical_sequence": 2, "event_type": "WORKFLOW_STARTED", "timestamp": t0})
    machine.apply_event({"logical_sequence": 3, "event_type": "WORKFLOW_COMPLETED", "timestamp": t0})

    # Cannot transition from COMPLETED to RUNNING via WORKFLOW_STARTED
    with pytest.raises(InvalidStateTransitionError):
        machine.apply_event({"logical_sequence": 4, "event_type": "WORKFLOW_STARTED", "timestamp": t0})
