"""Deterministic replay state machine and state-transition validation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.analytics.enums import TaskStatus, WorkflowEventType, WorkflowStatus


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition occurs during execution or replay."""

    def __init__(self, entity_type: str, entity_id: str, from_state: str, to_state: str, event_type: str) -> None:
        super().__init__(
            f"Invalid {entity_type} state transition for '{entity_id}': cannot transition from {from_state} to {to_state} via {event_type}"
        )
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.from_state = from_state
        self.to_state = to_state
        self.event_type = event_type


# Valid workflow transitions: current_state -> {allowed_events: next_state}
WORKFLOW_TRANSITIONS: dict[WorkflowStatus, dict[WorkflowEventType, WorkflowStatus]] = {
    WorkflowStatus.PENDING: {
        WorkflowEventType.WORKFLOW_STARTED: WorkflowStatus.RUNNING,
        WorkflowEventType.WORKFLOW_CANCELLED: WorkflowStatus.CANCELLED,
        WorkflowEventType.WORKFLOW_FAILED: WorkflowStatus.FAILED,
    },
    WorkflowStatus.RUNNING: {
        WorkflowEventType.WORKFLOW_COMPLETED: WorkflowStatus.COMPLETED,
        WorkflowEventType.WORKFLOW_FAILED: WorkflowStatus.FAILED,
        WorkflowEventType.WORKFLOW_CANCELLED: WorkflowStatus.CANCELLED,
    },
    WorkflowStatus.COMPLETED: {},
    WorkflowStatus.FAILED: {},
    WorkflowStatus.CANCELLED: {},
    WorkflowStatus.PARTIAL_SUCCESS: {},
}

# Valid task transitions: current_state -> {allowed_events: next_state}
TASK_TRANSITIONS: dict[TaskStatus, dict[WorkflowEventType, TaskStatus]] = {
    TaskStatus.PENDING: {
        WorkflowEventType.TASK_READY: TaskStatus.READY,
        WorkflowEventType.TASK_CANCELLED: TaskStatus.CANCELLED,
        WorkflowEventType.TASK_STARTED: TaskStatus.RUNNING,  # For single or direct starts
    },
    TaskStatus.READY: {
        WorkflowEventType.TASK_STARTED: TaskStatus.RUNNING,
        WorkflowEventType.TASK_CANCELLED: TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        WorkflowEventType.TASK_SUCCEEDED: TaskStatus.SUCCEEDED,
        WorkflowEventType.TASK_FAILED: TaskStatus.FAILED,
        WorkflowEventType.TASK_RETRYING: TaskStatus.RETRYING,
        WorkflowEventType.TASK_CANCELLED: TaskStatus.CANCELLED,
    },
    TaskStatus.RETRYING: {
        WorkflowEventType.TASK_STARTED: TaskStatus.RUNNING,
        WorkflowEventType.TASK_CANCELLED: TaskStatus.CANCELLED,
        WorkflowEventType.TASK_FAILED: TaskStatus.FAILED,
    },
    TaskStatus.SUCCEEDED: {},  # Terminal
    TaskStatus.FAILED: {},     # Terminal unless transitioned through RETRYING
    TaskStatus.CANCELLED: {},  # Terminal
    TaskStatus.SKIPPED: {},    # Terminal
}


def validate_workflow_transition(current: WorkflowStatus, event_type: WorkflowEventType, workflow_id: str) -> WorkflowStatus:
    allowed = WORKFLOW_TRANSITIONS.get(current, {})
    if event_type not in allowed:
        raise InvalidStateTransitionError("Workflow", workflow_id, current.value, event_type.value, event_type.value)
    return allowed[event_type]


def validate_task_transition(current: TaskStatus, event_type: WorkflowEventType, task_id: str) -> TaskStatus:
    allowed = TASK_TRANSITIONS.get(current, {})
    if event_type not in allowed:
        raise InvalidStateTransitionError("Task", task_id, current.value, event_type.value, event_type.value)
    return allowed[event_type]


@dataclass
class TaskAttemptReplay:
    attempt_number: int
    worker_id: str | None = None
    provider: str | None = None
    model: str | None = None
    status: str = "RUNNING"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class TaskReplayState:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    current_attempt: int = 1
    worker_id: str | None = None
    provider: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    output_hash: str | None = None
    error: str | None = None
    attempts: list[TaskAttemptReplay] = field(default_factory=list)


@dataclass
class WorkflowReplayState:
    workflow_run_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    wall_clock_duration_ms: int | None = None
    tasks: dict[str, TaskReplayState] = field(default_factory=dict)
    applied_events: int = 0
    routing_decisions: list[dict[str, Any]] = field(default_factory=list)


class WorkflowReplayMachine:
    """Deterministic state machine that reconstructs workflow state from events."""

    def __init__(self, workflow_run_id: str, strict: bool = True) -> None:
        self.state = WorkflowReplayState(workflow_run_id=workflow_run_id)
        self.strict = strict
        self._last_logical_sequence = -1

    def apply_event(self, event: Any) -> None:
        """Apply an event in logical sequence order.
        
        event can be an ORM WorkflowEvent or a dict with equivalent fields.
        """
        seq = getattr(event, "logical_sequence", None)
        if seq is None and isinstance(event, dict):
            seq = event.get("logical_sequence")

        if seq is not None:
            if seq <= self._last_logical_sequence:
                raise ValueError(
                    f"Out of order event in replay: expected sequence > {self._last_logical_sequence}, got {seq}"
                )
            self._last_logical_sequence = seq

        event_type_str = getattr(event, "event_type", None)
        if event_type_str is None and isinstance(event, dict):
            event_type_str = event.get("event_type")

        try:
            event_type = WorkflowEventType(event_type_str)
        except ValueError:
            raise ValueError(f"Unknown event type in replay: {event_type_str}")

        timestamp = getattr(event, "timestamp", None)
        if timestamp is None and isinstance(event, dict):
            timestamp = event.get("timestamp")

        task_id = getattr(event, "task_id", None)
        if task_id is None and isinstance(event, dict):
            task_id = event.get("task_id")

        payload = getattr(event, "payload", {}) or {}
        if isinstance(event, dict) and not payload:
            payload = event.get("payload", {}) or {}

        attempt_num = getattr(event, "attempt", 1) or 1
        if isinstance(event, dict) and "attempt" in event:
            attempt_num = event.get("attempt") or 1

        self._process(event_type, task_id, attempt_num, timestamp, payload)
        self.state.applied_events += 1

    def _process(
        self,
        event_type: WorkflowEventType,
        task_id: str | None,
        attempt: int,
        timestamp: datetime | None,
        payload: dict[str, Any],
    ) -> None:
        # Workflow-level events
        if event_type == WorkflowEventType.WORKFLOW_CREATED:
            self.state.created_at = timestamp
            self.state.status = WorkflowStatus.PENDING
            return

        if event_type == WorkflowEventType.WORKFLOW_STARTED:
            self.state.status = validate_workflow_transition(self.state.status, event_type, self.state.workflow_run_id)
            self.state.started_at = timestamp
            return

        if event_type == WorkflowEventType.WORKFLOW_COMPLETED:
            self.state.status = validate_workflow_transition(self.state.status, event_type, self.state.workflow_run_id)
            self.state.finished_at = timestamp
            if self.state.started_at and self.state.finished_at:
                self.state.wall_clock_duration_ms = int(
                    (self.state.finished_at - self.state.started_at).total_seconds() * 1000
                )
            return

        if event_type == WorkflowEventType.WORKFLOW_FAILED:
            self.state.status = validate_workflow_transition(self.state.status, event_type, self.state.workflow_run_id)
            self.state.finished_at = timestamp
            if self.state.started_at and self.state.finished_at:
                self.state.wall_clock_duration_ms = int(
                    (self.state.finished_at - self.state.started_at).total_seconds() * 1000
                )
            return

        if event_type == WorkflowEventType.WORKFLOW_CANCELLED:
            self.state.status = validate_workflow_transition(self.state.status, event_type, self.state.workflow_run_id)
            self.state.finished_at = timestamp
            if self.state.started_at and self.state.finished_at:
                self.state.wall_clock_duration_ms = int(
                    (self.state.finished_at - self.state.started_at).total_seconds() * 1000
                )
            return

        # Task-level events
        if not task_id:
            return

        if task_id not in self.state.tasks:
            self.state.tasks[task_id] = TaskReplayState(task_id=task_id)

        task = self.state.tasks[task_id]

        if event_type == WorkflowEventType.TASK_READY:
            task.status = validate_task_transition(task.status, event_type, task_id)
            return

        if event_type == WorkflowEventType.TASK_STARTED:
            task.status = validate_task_transition(task.status, event_type, task_id)
            task.current_attempt = attempt
            worker_id = payload.get("worker_id")
            provider = payload.get("provider")
            model = payload.get("model")
            task.worker_id = worker_id
            task.provider = provider
            task.model = model
            if task.started_at is None:
                task.started_at = timestamp

            task.attempts.append(
                TaskAttemptReplay(
                    attempt_number=attempt,
                    worker_id=worker_id,
                    provider=provider,
                    model=model,
                    status="RUNNING",
                    started_at=timestamp,
                )
            )
            return

        if event_type == WorkflowEventType.TASK_RETRYING:
            task.status = validate_task_transition(task.status, event_type, task_id)
            error = payload.get("error_type") or payload.get("error")
            duration_ms = payload.get("duration_ms")
            if task.attempts:
                cur = task.attempts[-1]
                cur.status = "RETRYING"
                cur.finished_at = timestamp
                cur.duration_ms = duration_ms
                cur.error = error
            return

        if event_type == WorkflowEventType.TASK_SUCCEEDED:
            task.status = validate_task_transition(task.status, event_type, task_id)
            task.finished_at = timestamp
            duration_ms = payload.get("duration_ms")
            task.duration_ms = duration_ms
            task.output_hash = payload.get("output_hash")
            if task.attempts:
                cur = task.attempts[-1]
                cur.status = "SUCCEEDED"
                cur.finished_at = timestamp
                cur.duration_ms = duration_ms
            return

        if event_type == WorkflowEventType.TASK_FAILED:
            task.status = validate_task_transition(task.status, event_type, task_id)
            task.finished_at = timestamp
            duration_ms = payload.get("duration_ms")
            error = payload.get("error_type") or payload.get("error")
            task.duration_ms = duration_ms
            task.error = error
            if task.attempts:
                cur = task.attempts[-1]
                cur.status = "FAILED"
                cur.finished_at = timestamp
                cur.duration_ms = duration_ms
                cur.error = error
            return

        if event_type == WorkflowEventType.TASK_CANCELLED:
            task.status = validate_task_transition(task.status, event_type, task_id)
            task.finished_at = timestamp
            if task.attempts:
                cur = task.attempts[-1]
                cur.status = "CANCELLED"
                cur.finished_at = timestamp
            return
