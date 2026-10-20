"""Benchmark measuring telemetry overhead: baseline vs instrumented execution."""

import asyncio
import os
import time
import tracemalloc
import uuid
import asyncpg
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.analytics.enums import WorkflowEventType
from src.analytics.event_logger import EventLogger
from src.analytics.models import TaskAttempt, WorkflowEvent, WorkflowMetrics, WorkflowRun
from src.analytics.service import AnalyticsService
from src.db.models import utcnow


async def run_baseline_workflow(iterations: int = 5) -> dict[str, float]:
    """Execute baseline workload without event logging or metrics calculation."""
    tracemalloc.start()
    t0 = time.perf_counter()

    task_durations = []
    for it in range(iterations):
        # Simulate 4 tasks per iteration
        for t in range(4):
            task_t0 = time.perf_counter()
            # Synthetic task work
            await asyncio.sleep(0.005)
            task_durations.append((time.perf_counter() - task_t0) * 1000)

    wall_clock_ms = (time.perf_counter() - t0) * 1000
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "wall_clock_ms": round(wall_clock_ms, 2),
        "avg_task_latency_ms": round(sum(task_durations) / len(task_durations), 2),
        "db_writes": 0,
        "analytics_persistence_ms": 0.0,
        "peak_memory_kb": round(peak_mem / 1024, 2),
    }


async def run_instrumented_workflow(engine, iterations: int = 5) -> dict[str, float]:
    """Execute identical workload with full event history, attempt tracking, and metrics persistence."""
    tracemalloc.start()
    t0 = time.perf_counter()

    task_durations = []
    total_persistence_ms = 0.0
    total_db_writes = 0

    for it in range(iterations):
        run_id = uuid.uuid4()
        # 1. Create WorkflowRun
        t_p0 = time.perf_counter()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                run = WorkflowRun(
                    id=run_id,
                    request_id=f"bench-req-{it}",
                    status="RUNNING",
                    execution_mode="DAG",
                    requested_model="auto",
                    started_at=utcnow(),
                )
                session.add(run)
        total_persistence_ms += (time.perf_counter() - t_p0) * 1000
        total_db_writes += 1

        logger = EventLogger(run_id)

        # Log workflow start
        t_p = time.perf_counter()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                await logger.log_event(session, WorkflowEventType.WORKFLOW_CREATED)
                await logger.log_event(session, WorkflowEventType.WORKFLOW_STARTED)
        total_persistence_ms += (time.perf_counter() - t_p) * 1000
        total_db_writes += 2

        # 4 tasks per iteration
        for t in range(4):
            task_id = f"task-{t}"
            t_p = time.perf_counter()
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    await logger.log_event(session, WorkflowEventType.TASK_READY, task_id=task_id)
                    await logger.start_attempt(session, task_id=task_id, attempt_number=1)
            total_persistence_ms += (time.perf_counter() - t_p) * 1000
            total_db_writes += 2  # 1 event + 1 attempt

            task_t0 = time.perf_counter()
            await asyncio.sleep(0.005)
            duration_ms = int((time.perf_counter() - task_t0) * 1000)
            task_durations.append(duration_ms)

            t_p = time.perf_counter()
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    await logger.finish_attempt(
                        session,
                        task_id=task_id,
                        attempt_number=1,
                        status="SUCCEEDED",
                        duration_ms=duration_ms,
                    )
            total_persistence_ms += (time.perf_counter() - t_p) * 1000
            total_db_writes += 1  # 1 event (update attempt + insert event)

        # Complete workflow & persist metrics
        t_p = time.perf_counter()
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                run_row = (await session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))).scalar_one()
                run_row.status = "COMPLETED"
                run_row.finished_at = utcnow()
                await logger.log_event(session, WorkflowEventType.WORKFLOW_COMPLETED)
            total_db_writes += 1

            # Compute and persist WorkflowMetrics
            await AnalyticsService.get_or_calculate_workflow_metrics(
                session,
                workflow_run_id=run_id,
                scheduler_overhead_ms=5,
            )
            total_db_writes += 1
        total_persistence_ms += (time.perf_counter() - t_p) * 1000

        # Cleanup bench run to keep DB clean
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                r = (await session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))).scalar_one()
                await session.delete(r)

    wall_clock_ms = (time.perf_counter() - t0) * 1000
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "wall_clock_ms": round(wall_clock_ms, 2),
        "avg_task_latency_ms": round(sum(task_durations) / len(task_durations), 2),
        "db_writes": total_db_writes,
        "analytics_persistence_ms": round(total_persistence_ms, 2),
        "peak_memory_kb": round(peak_mem / 1024, 2),
    }


@pytest.mark.asyncio
async def test_telemetry_overhead_benchmark():
    """Benchmark comparing uninstrumented baseline vs fully instrumented execution."""
    pg_url = os.environ.get("POSTGRES_TEST_URL", "postgresql+asyncpg://wrap:wrap@localhost:5433/wrap")
    is_pg_reachable = False
    try:
        conn = await asyncpg.connect("postgresql://wrap:wrap@localhost:5433/wrap", timeout=2)
        await conn.close()
        is_pg_reachable = True
    except Exception:
        pass

    db_url = pg_url if is_pg_reachable else "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(db_url, pool_pre_ping=True)

    if "sqlite" in db_url:
        from src.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # 1. Run baseline
    baseline = await run_baseline_workflow(iterations=3)

    # 2. Run instrumented
    instrumented = await run_instrumented_workflow(engine, iterations=3)

    await engine.dispose()

    # Calculate overhead
    wall_clock_overhead_ms = instrumented["wall_clock_ms"] - baseline["wall_clock_ms"]
    task_latency_delta_ms = instrumented["avg_task_latency_ms"] - baseline["avg_task_latency_ms"]

    print("\n" + "=" * 60)
    print("TELEMETRY OVERHEAD BENCHMARK REPORT")
    print("=" * 60)
    print(f"Target Database: {'PostgreSQL 5433' if is_pg_reachable else 'SQLite In-Memory'}")
    print(f"Iterations: 3 workflows (12 tasks total)")
    print("-" * 60)
    print(f"BASELINE (No Telemetry):")
    print(f"  Wall-Clock Duration:      {baseline['wall_clock_ms']} ms")
    print(f"  Avg Task Latency:         {baseline['avg_task_latency_ms']} ms")
    print(f"  Database Writes:          {baseline['db_writes']}")
    print(f"  Analytics Persistence:    {baseline['analytics_persistence_ms']} ms")
    print(f"  Peak Memory:              {baseline['peak_memory_kb']} KB")
    print("-" * 60)
    print(f"INSTRUMENTED (Full Events + Attempts + Metrics):")
    print(f"  Wall-Clock Duration:      {instrumented['wall_clock_ms']} ms")
    print(f"  Avg Task Latency:         {instrumented['avg_task_latency_ms']} ms")
    print(f"  Database Writes:          {instrumented['db_writes']}")
    print(f"  Analytics Persistence:    {instrumented['analytics_persistence_ms']} ms")
    print(f"  Peak Memory:              {instrumented['peak_memory_kb']} KB")
    print("-" * 60)
    print(f"OVERHEAD DELTA:")
    print(f"  Wall-Clock Delta:         +{wall_clock_overhead_ms:.2f} ms")
    print(f"  Task Latency Delta:       {task_latency_delta_ms:+.2f} ms")
    print(f"  Persistence Cost / Write: {instrumented['analytics_persistence_ms'] / max(1, instrumented['db_writes']):.2f} ms")
    print(f"  Memory Delta:             +{instrumented['peak_memory_kb'] - baseline['peak_memory_kb']:.2f} KB")
    print("=" * 60)

    assert instrumented["db_writes"] > 0
    assert instrumented["analytics_persistence_ms"] > 0
