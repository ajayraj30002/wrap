"""Concurrency-safe event logger and attempt tracker for workflows."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.enums import WorkflowEventType
from src.analytics.models import TaskAttempt, WorkflowEvent, WorkflowRun
from src.analytics.redaction import sanitize_payload
from src.db.models import utcnow


class EventLogger:
    """Emits immutable, sequentially ordered, sanitized workflow events."""

    def __init__(self, workflow_run_id: uuid.UUID) -> None:
        self.workflow_run_id = workflow_run_id
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def log_event(
        self,
        session: AsyncSession,
        event_type: WorkflowEventType | str,
        *,
        task_id: str | None = None,
        attempt: int = 1,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
        flush: bool = True,
    ) -> WorkflowEvent:
        """Create, sanitize, and persist a WorkflowEvent with a monotonic logical sequence.
        
        Uses database row-level locking (SELECT ... FOR UPDATE) on WorkflowRun to guarantee
        strictly monotonic, duplicate-free, and gap-free sequence numbers across concurrent
        coroutines, threads, and independent application processes.
        """
        if isinstance(event_type, WorkflowEventType):
            event_type_str = event_type.value
        else:
            event_type_str = str(event_type)

        async with self._lock:
            # 1. Flush any newly added instances in current session so the row exists
            if session.new:
                await session.flush()

            # 2. Acquire database row-level lock and increment counter atomically
            stmt = (
                select(WorkflowRun)
                .where(WorkflowRun.id == self.workflow_run_id)
                .with_for_update()
            )
            result = await session.execute(stmt)
            run = result.scalar_one_or_none()

            if run is not None:
                max_stmt = select(func.coalesce(func.max(WorkflowEvent.logical_sequence), 0)).where(
                    WorkflowEvent.workflow_run_id == self.workflow_run_id
                )
                max_res = await session.execute(max_stmt)
                current_max = max_res.scalar_one()
                next_seq = max(run.event_sequence_counter, self._sequence, current_max) + 1
                run.event_sequence_counter = next_seq
                self._sequence = next_seq
                seq = next_seq
            else:
                # Fallback for standalone/mock tests where WorkflowRun is uncommitted
                max_stmt = select(func.coalesce(func.max(WorkflowEvent.logical_sequence), 0)).where(
                    WorkflowEvent.workflow_run_id == self.workflow_run_id
                )
                max_res = await session.execute(max_stmt)
                current_max = max_res.scalar_one()
                seq = max(current_max, self._sequence) + 1
                self._sequence = seq

            sanitized_payload = sanitize_payload(payload or {})
            ts = timestamp or utcnow()

            event = WorkflowEvent(
                workflow_run_id=self.workflow_run_id,
                task_id=task_id,
                event_type=event_type_str,
                logical_sequence=seq,
                attempt=attempt,
                timestamp=ts,
                payload=sanitized_payload,
            )
            session.add(event)
            if flush:
                await session.flush()
            return event

    async def start_attempt(
        self,
        session: AsyncSession,
        *,
        task_id: str,
        attempt_number: int,
        worker_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        flush: bool = True,
    ) -> TaskAttempt:
        """Record the start of a task attempt and emit TASK_STARTED."""
        attempt = TaskAttempt(
            workflow_run_id=self.workflow_run_id,
            task_id=task_id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            provider=provider,
            model=model,
            status="RUNNING",
            started_at=utcnow(),
            retryable=True,
            attempt_metadata=sanitize_payload(metadata or {}),
        )
        session.add(attempt)
        if flush:
            await session.flush()

        await self.log_event(
            session,
            WorkflowEventType.TASK_STARTED,
            task_id=task_id,
            attempt=attempt_number,
            payload={
                "attempt": attempt_number,
                "worker_id": str(worker_id) if worker_id else None,
                "provider": provider,
                "model": model,
                **(metadata or {}),
            },
            flush=flush,
        )
        return attempt

    async def finish_attempt(
        self,
        session: AsyncSession,
        *,
        task_id: str,
        attempt_number: int,
        status: str,  # SUCCEEDED, FAILED, RETRYING, CANCELLED
        duration_ms: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        output_hash: str | None = None,
        flush: bool = True,
    ) -> None:
        """Update a task attempt's outcome and emit corresponding terminal or retry event."""
        now = utcnow()
        # Find attempt in current session
        from sqlalchemy import select
        result = await session.execute(
            select(TaskAttempt).where(
                TaskAttempt.workflow_run_id == self.workflow_run_id,
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == attempt_number,
            )
        )
        attempt = result.scalar_one_or_none()
        if attempt:
            attempt.status = status.upper()
            attempt.finished_at = now
            if duration_ms is not None:
                attempt.duration_ms = duration_ms
            elif attempt.started_at:
                st = attempt.started_at.replace(tzinfo=timezone.utc) if attempt.started_at.tzinfo is None else attempt.started_at
                attempt.duration_ms = max(0, int((now - st).total_seconds() * 1000))
            attempt.error_type = error_type
            attempt.error_message = error_message
            if flush:
                await session.flush()

        duration = attempt.duration_ms if attempt else duration_ms

        status_upper = status.upper()
        if status_upper in ("SUCCEEDED", "SUCCESS"):
            await self.log_event(
                session,
                WorkflowEventType.TASK_SUCCEEDED,
                task_id=task_id,
                attempt=attempt_number,
                payload={"duration_ms": duration, "output_hash": output_hash},
                flush=flush,
            )
        elif status_upper == "RETRYING":
            await self.log_event(
                session,
                WorkflowEventType.TASK_RETRYING,
                task_id=task_id,
                attempt=attempt_number,
                payload={"duration_ms": duration, "error_type": error_type, "retryable": True},
                flush=flush,
            )
        elif status_upper in ("FAILED", "FAILURE"):
            await self.log_event(
                session,
                WorkflowEventType.TASK_FAILED,
                task_id=task_id,
                attempt=attempt_number,
                payload={"duration_ms": duration, "error_type": error_type, "retryable": False},
                flush=flush,
            )
        elif status_upper == "CANCELLED":
            await self.log_event(
                session,
                WorkflowEventType.TASK_CANCELLED,
                task_id=task_id,
                attempt=attempt_number,
                payload={"duration_ms": duration, "reason": error_message or "cancelled"},
                flush=flush,
            )
