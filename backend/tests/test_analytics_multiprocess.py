"""Multi-process concurrency test for database-authoritative event sequence allocation."""

import asyncio
import multiprocessing
import os
import uuid
import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.analytics.enums import WorkflowEventType
from src.analytics.event_logger import EventLogger
from src.analytics.models import WorkflowEvent, WorkflowRun
from src.analytics.state_machine import WorkflowReplayMachine


def _process_worker_emit_events(run_id_str: str, process_idx: int, count: int, db_url: str):
    """Executed in an independent OS process: connects to DB, instantiates EventLogger, logs events."""
    async def _async_emit():
        run_id = uuid.UUID(run_id_str)
        engine = create_async_engine(db_url, pool_pre_ping=True)
        logger = EventLogger(run_id)

        for i in range(count):
            task_idx = i // 2
            is_start = (i % 2 == 0)
            event_type = WorkflowEventType.TASK_STARTED if is_start else WorkflowEventType.TASK_SUCCEEDED
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    await logger.log_event(
                        session,
                        event_type,
                        task_id=f"proc-{process_idx}-t{task_idx}",
                        attempt=1,
                        payload={"process_idx": process_idx, "item_idx": i},
                    )
            # Micro-yield to allow OS context switches across processes
            await asyncio.sleep(0.01)

        await engine.dispose()

    asyncio.run(_async_emit())


@pytest.mark.asyncio
async def test_multiprocess_event_sequencing_postgresql():
    """Verify that multiple independent OS processes emitting events for the same workflow_run_id

    achieve strictly monotonic, gap-free, duplicate-free sequence allocation using database-level
    row locking on PostgreSQL.
    """
    pg_url = os.environ.get("POSTGRES_TEST_URL", "postgresql+asyncpg://wrap:wrap@localhost:5433/wrap")
    is_pg_reachable = False
    try:
        conn = await asyncpg.connect("postgresql://wrap:wrap@localhost:5433/wrap", timeout=2)
        await conn.close()
        is_pg_reachable = True
    except Exception:
        pass

    if not is_pg_reachable:
        pytest.skip("PostgreSQL (port 5433) is not reachable, skipping multi-process DB test")

    engine = create_async_engine(pg_url, pool_pre_ping=True)
    run_id = uuid.uuid4()

    # 1. Initialize WorkflowRun record in PostgreSQL
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            run = WorkflowRun(
                id=run_id,
                request_id="multiprocess-test",
                status="RUNNING",
                execution_mode="DAG",
                requested_model="auto",
                event_sequence_counter=0,
            )
            session.add(run)

    # 2. Launch 3 separate OS processes to log events concurrently
    num_processes = 3
    events_per_process = 10
    total_expected = num_processes * events_per_process

    ctx = multiprocessing.get_context("spawn")
    processes = []
    for p_idx in range(num_processes):
        p = ctx.Process(
            target=_process_worker_emit_events,
            args=(str(run_id), p_idx, events_per_process, pg_url),
        )
        processes.append(p)

    for p in processes:
        p.start()

    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0, f"Process {p} failed with exit code {p.exitcode}"

    # 3. Verify sequence allocation in PostgreSQL
    async with AsyncSession(engine, expire_on_commit=False) as session:
        stmt = (
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_run_id == run_id)
            .order_by(WorkflowEvent.logical_sequence.asc())
        )
        events = (await session.execute(stmt)).scalars().all()

        # Check total count
        assert len(events) == total_expected, f"Expected {total_expected} events, got {len(events)}"

        # Verify sequences are strictly 1, 2, ..., total_expected
        sequences = [e.logical_sequence for e in events]
        assert sequences == list(range(1, total_expected + 1)), f"Sequences were not strictly monotonic: {sequences}"

        # Verify no duplicate sequence numbers
        assert len(set(sequences)) == total_expected, "Found duplicate sequence numbers across processes"

        # Verify WorkflowRun.event_sequence_counter matches exactly
        run_row = (await session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))).scalar_one()
        assert run_row.event_sequence_counter == total_expected

        # 4. Verify deterministic replay ordering
        machine = WorkflowReplayMachine(workflow_run_id=str(run_id), strict=False)
        for ev in events:
            machine.apply_event(ev)

        assert machine.state.applied_events == total_expected
        assert len(machine.state.tasks) == total_expected // 2

        # Cleanup
        await session.delete(run_row)
        await session.commit()

    await engine.dispose()
