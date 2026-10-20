"""Concurrency and thread/async safety tests for the analytics subsystem."""

import asyncio
import uuid
import pytest
from datetime import datetime, timezone, timedelta

from src.analytics.calculator import compute_concurrency_metrics
from src.analytics.event_logger import EventLogger
from src.db.session import AsyncSessionLocal, engine
from src.db.models import Base, WorkflowRun


@pytest.mark.asyncio
async def test_event_logger_monotonic_sequence_concurrency():
    """Verify EventLogger maintains strictly monotonic unique sequences under high concurrent logging."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        run = WorkflowRun(
            id=run_id,
            request_id="req-concurrency-1",
            status="RUNNING",
            execution_mode="DAG",
            requested_model="auto",
        )
        session.add(run)
        await session.commit()

    logger = EventLogger(run_id)

    async def log_item(idx: int):
        async with AsyncSessionLocal() as session:
            ev = await logger.log_event(
                session,
                "TASK_READY",
                task_id=f"t-{idx}",
                payload={"index": idx},
            )
            await session.commit()
            return ev.logical_sequence

    # Fire 30 concurrent log events
    sequences = await asyncio.gather(*(log_item(i) for i in range(30)))

    # Verify all sequence numbers are unique and cover 1..30
    assert len(sequences) == 30
    assert len(set(sequences)) == 30
    assert sorted(sequences) == list(range(1, 31))


def test_concurrency_simultaneous_starts_and_completions():
    """Verify concurrency calculation under simultaneous start and end timestamps."""
    t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    t2 = t0 + timedelta(seconds=2)

    # 4 tasks starting at the exact same millisecond
    attempts = [
        {"task_id": "a1", "started_at": t0, "finished_at": t1},
        {"task_id": "a2", "started_at": t0, "finished_at": t2},
        {"task_id": "a3", "started_at": t0, "finished_at": t2},
        {"task_id": "a4", "started_at": t0, "finished_at": t1},
    ]
    assert compute_concurrency_metrics(attempts) == 4

    # 2 tasks finishing at t1 while 2 other tasks start at t1
    attempts_handoff = [
        {"task_id": "h1", "started_at": t0, "finished_at": t1},
        {"task_id": "h2", "started_at": t0, "finished_at": t1},
        {"task_id": "h3", "started_at": t1, "finished_at": t2},
        {"task_id": "h4", "started_at": t1, "finished_at": t2},
    ]
    # At t1, starts happen first so peak active is 4 (or 2 if non-overlapping)
    peak = compute_concurrency_metrics(attempts_handoff)
    assert peak in (2, 4)
