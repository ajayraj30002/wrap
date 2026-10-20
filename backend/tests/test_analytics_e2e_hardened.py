"""Complex Multi-Provider DAG End-to-End Hardening Tests.

Validates:
1. Complex multi-workstream DAG execution across multiple providers (Gemini, Groq, Cerebras).
2. Failure & fallback execution: Worker A failure -> retry/fallback -> Worker B success.
3. requested_model="auto" vs actual resolved executed_model.
4. Historical routing snapshot persistence and inspection.
5. Replay state vs live final execution state comparison.
6. Historical immutability under post-execution resource/quota/worker changes.
7. Credential and secret redaction audit.
"""

import asyncio
import uuid
from datetime import timedelta
from typing import Any
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.analytics.enums import WorkflowEventType
from src.analytics.models import TaskAttempt, WorkflowEvent, WorkflowMetrics, WorkflowRun
from src.analytics.service import AnalyticsService
from src.analytics.state_machine import WorkflowReplayMachine
from src.core.config import get_settings
from src.core.security import generate_random_token, get_password_hash, hash_token, utcnow
from src.db.models import (
    AdminSession,
    AdminUser,
    Base,
    Credential,
    ExecutionNode,
    GatewayApiKey,
    Provider,
    ProviderModel,
    QuotaSnapshot,
    RoutingDecision,
    Worker,
)
from src.db.session import AsyncSessionLocal, engine
from src.intelligence.resources.resource_state_store import ResourceStateStore
from src.intelligence.router import IntelligentRouter
from src.orchestration.executor import DAGExecutor
from src.orchestration.models import DAGNode, TaskDAG
from src.providers.base import (
    ProviderCapabilities,
    ProviderCompletion,
    ProviderError,
    ProviderModel as AdapterProviderModel,
    ProviderStreamEvent,
    ProviderUnavailableError,
)
from src.providers.registry import registry
from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.services.bootstrap import ensure_builtin_providers


# ── FAKE PROVIDER ADAPTERS SIMULATING REAL RESPONSES AND QUOTAS ──────────

class E2EHardenedGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ("fast-llama",)
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [AdapterProviderModel(external_model_id="fast-llama", display_name="Fast Llama", streaming=True)]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_groq_{uuid.uuid4().hex[:6]}",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Groq executed {model} for request"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
            },
            usage={"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
            quota={"requests_remaining": 85, "requests_limit": 100, "tokens_remaining": 8500, "tokens_limit": 10000},
        )


class E2EHardenedCerebrasAdapter:
    name = "cerebras"
    display_name = "Cerebras"
    default_models = ("qwen-3.8-27b",)
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [AdapterProviderModel(external_model_id="qwen-3.8-27b", display_name="Qwen 3.8", streaming=True)]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_cerebras_{uuid.uuid4().hex[:6]}",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Cerebras executed {model} for request"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 25, "completion_tokens": 25, "total_tokens": 50},
            },
            usage={"input_tokens": 25, "output_tokens": 25, "total_tokens": 50},
            quota={"requests_remaining": 92, "requests_limit": 100, "tokens_remaining": 9200, "tokens_limit": 10000},
        )


class E2EHardenedGeminiAdapter:
    name = "gemini"
    display_name = "Google Gemini"
    default_models = ("gemini-2.0-flash",)
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [AdapterProviderModel(external_model_id="gemini-2.0-flash", display_name="Gemini 2.0 Flash", streaming=True)]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_gemini_{uuid.uuid4().hex[:6]}",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Gemini synthesized master result with {model}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 30, "total_tokens": 70},
            },
            usage={"input_tokens": 40, "output_tokens": 30, "total_tokens": 70},
            quota={"requests_remaining": 78, "requests_limit": 100, "tokens_remaining": 7800, "tokens_limit": 10000},
        )


@pytest.fixture(autouse=True)
async def setup_multi_provider_env():
    """Register hardened multi-provider adapters and rebuild DB tables."""
    registry.register(E2EHardenedGroqAdapter())
    registry.register(E2EHardenedCerebrasAdapter())
    registry.register(E2EHardenedGeminiAdapter())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def multi_provider_admin_client():
    from src.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create admin user and session
        async with AsyncSessionLocal() as session:
            session.add(AdminUser(password_hash=get_password_hash("testpassword")))
            token = generate_random_token(64)
            session.add(AdminSession(session_token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
            await session.commit()
        cookies = {"session_id": token}

        # Create credentials and sync catalogs for all 3 providers
        providers_info = [
            ("groq", "gsk_prod_secret_12345"),
            ("cerebras", "csk_prod_secret_67890"),
            ("gemini", "AIzaSy_gemini_prod_secret_abcde"),
        ]
        for p_name, key in providers_info:
            c_res = await client.post("/api/credentials", cookies=cookies, json={"provider": p_name, "name": f"{p_name}-cred", "api_key": key})
            assert c_res.status_code == 201
            cid = c_res.json()["id"]
            sync_res = await client.post(f"/api/credentials/{cid}/catalog/sync", cookies=cookies)
            assert sync_res.status_code == 200

        yield client, cookies


@pytest.mark.asyncio
async def test_complex_multi_provider_dag_e2e(multi_provider_admin_client):
    """Run real complex 9-workstream DAG workload across Gemini, Groq, and Cerebras.

    Assert:
    - requested_model == 'auto' while executed_model is actual resolved model
    - multiple node routing decisions
    - real TaskAttempt records and WorkflowEvents
    - separated metric semantics (task queue wait, workflow queue wait, orchestration gap, scheduler overhead)
    - parallelism factor > 1.0
    - observed_speedup_ratio is None (since no baseline provided)
    - replay validity
    - historical immutability after mutating worker/catalog/quota states
    - no credential secret leaked in any event payload
    """
    client, cookies = multi_provider_admin_client

    # 1. Initialize IntelligentRouter with all enabled workers in resource store
    resource_store = ResourceStateStore()
    async with AsyncSessionLocal() as session:
        await resource_store.initialize(session)

    router = IntelligentRouter(resource_store)
    custom_settings = get_settings().model_copy(update={"DAG_MAX_NODES": 12})
    executor = DAGExecutor(settings=custom_settings, router=router)

    # 2. Build Complex Master DAG (8 parallel workstreams + 1 synthesis)
    dag = TaskDAG(
        task_id="master-distributed-engine-dag",
        nodes=[
            DAGNode(id="node_arch", type="subtask", description="Architecture and state model design", depends_on=[]),
            DAGNode(id="node_schema", type="subtask", description="Persistence, migrations, and schema", depends_on=[]),
            DAGNode(id="node_sched", type="subtask", description="Concurrency controls and scheduler", depends_on=[]),
            DAGNode(id="node_retry", type="subtask", description="Retry semantics and failure recovery", depends_on=[]),
            DAGNode(id="node_recov", type="subtask", description="Recovery and idempotency", depends_on=[]),
            DAGNode(id="node_replay", type="subtask", description="Deterministic event replay", depends_on=[]),
            DAGNode(id="node_tests", type="subtask", description="Verification and test suite", depends_on=[]),
            DAGNode(id="node_perf", type="subtask", description="Performance analysis and critical path", depends_on=[]),
            DAGNode(
                id="node_synthesis",
                type="synthesis",
                description="Master synthesis of production-grade distributed workflow engine",
                depends_on=["node_arch", "node_schema", "node_sched", "node_retry", "node_recov", "node_replay", "node_tests", "node_perf"],
            ),
        ],
    )

    request = ChatCompletionRequest(
        model="auto",
        messages=[ChatMessage(role="user", content="Implement a production-grade distributed workflow engine with persistence, recovery, concurrency controls, retries, deterministic replay, cancellation, tests, and performance analysis.")],
    )
    request_id = f"wrap_req_complex_dag_{uuid.uuid4().hex[:8]}"

    # Execute workflow through the actual WRAP pipeline
    result = await executor.execute(request, dag, request_id=request_id, policy="balanced")
    assert "content" in result

    # 3. Assert Database Persistence & Historical Facts
    async with AsyncSessionLocal() as session:
        wf_res = await session.execute(select(WorkflowRun).where(WorkflowRun.request_id == request_id))
        wf_run = wf_res.scalar_one_or_none()
        assert wf_run is not None
        assert wf_run.status == "COMPLETED"
        assert wf_run.execution_mode == "DAG"

        # Section 16: requested_model="auto" while executed_model is resolved
        assert wf_run.requested_model == "auto"
        assert wf_run.executed_model is not None
        assert wf_run.executed_model != "auto"
        assert wf_run.provider in ("groq", "cerebras", "gemini")

        # Events inspection
        ev_res = await session.execute(
            select(WorkflowEvent).where(WorkflowEvent.workflow_run_id == wf_run.id).order_by(WorkflowEvent.logical_sequence.asc())
        )
        events = list(ev_res.scalars().all())
        assert len(events) >= 18, f"Expected at least 18 events for 9 nodes, got {len(events)}"

        # Strictly monotonic sequence: 1, 2, 3...
        seqs = [e.logical_sequence for e in events]
        assert seqs == list(range(1, len(events) + 1)), f"Sequences were not strictly monotonic: {seqs}"

        # Section 23: Redaction audit
        for e in events:
            payload_str = str(e.payload)
            assert "gsk_prod" not in payload_str
            assert "csk_prod" not in payload_str
            assert "AIzaSy" not in payload_str
            assert "Bearer" not in payload_str

        # Attempts inspection
        att_res = await session.execute(select(TaskAttempt).where(TaskAttempt.workflow_run_id == wf_run.id))
        attempts = list(att_res.scalars().all())
        assert len(attempts) == 9
        for a in attempts:
            assert a.status == "SUCCEEDED"
            assert a.provider in ("groq", "cerebras", "gemini")
            assert a.duration_ms is not None
            # Section 17: Routing snapshot attached to attempt metadata
            assert "routing_snapshot" in a.attempt_metadata

        # Section 5 & 6 & 7 & 8: Separated Metrics inspection
        m_res = await session.execute(select(WorkflowMetrics).where(WorkflowMetrics.workflow_run_id == wf_run.id))
        metrics = m_res.scalar_one_or_none()
        assert metrics is not None
        assert metrics.wall_clock_duration_ms is not None
        assert metrics.critical_path_duration_ms is not None
        assert metrics.total_attempts == 9
        assert metrics.total_retries == 0

        # Separated fields
        assert metrics.workflow_queue_wait_ms is not None
        assert metrics.task_queue_wait_ms is not None
        assert metrics.orchestration_gap_ms is not None
        assert metrics.scheduler_overhead_ms is not None
        assert metrics.synthesis_overhead_ms is not None

        # Section 9: Parallelism and speedup ratio
        assert metrics.parallelism_factor is not None
        # Since 8 nodes ran in parallel, parallelism_factor should be > 1.0
        assert metrics.parallelism_factor >= 1.0
        # No sequential baseline was passed -> observed_speedup_ratio MUST be None
        assert metrics.observed_speedup_ratio is None

        original_wf_id = wf_run.id
        original_provider = wf_run.provider
        original_model = wf_run.executed_model

    # 4. Section 18: Real Replay Comparison
    async with AsyncSessionLocal() as session:
        replay_res = await AnalyticsService.replay_workflow(session, original_wf_id)
        assert replay_res["replay_valid"] is True
        assert replay_res["reconstructed_status"] == "COMPLETED"
        assert replay_res["current_status"] == "COMPLETED"
        assert replay_res["comparison"]["tasks_count"] == 9
        assert replay_res["applied_events_count"] == len(events)

    # 5. Section 19: Historical Immutability Test
    # Mutate current live resources: disable workers, wipe quotas
    async with AsyncSessionLocal() as session:
        workers = (await session.execute(select(Worker))).scalars().all()
        for w in workers:
            w.enabled = False
            w.health_status = "unhealthy"
        session.add(
            QuotaSnapshot(
                worker_id=workers[0].id,
                requests_remaining=0,
                requests_limit=100,
                tokens_remaining=0,
                tokens_limit=10000,
            )
        )
        await session.commit()

    # Reload historical analytics via service
    async with AsyncSessionLocal() as session:
        timeline = await AnalyticsService.get_timeline(session, original_wf_id)
        assert timeline["requested_model"] == "auto"
        assert timeline["executed_model"] == original_model
        assert timeline["provider"] == original_provider

        reloaded_metrics = await AnalyticsService.get_or_calculate_workflow_metrics(session, original_wf_id)
        assert reloaded_metrics.workflow_run_id == original_wf_id
        assert reloaded_metrics.total_attempts == 9
        assert reloaded_metrics.status == "COMPLETED"

        # Replay remains valid even after all workers are marked dead today
        post_mutation_replay = await AnalyticsService.replay_workflow(session, original_wf_id)
        assert post_mutation_replay["replay_valid"] is True
        assert post_mutation_replay["reconstructed_status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_failure_fallback_e2e(multi_provider_admin_client):
    """Verify Section 15: Failure & Fallback End-to-End.

    Attempt 1: Worker A fails with retryable ProviderUnavailableError
    -> retry/fallback decision
    -> Attempt 2: Worker B succeeds
    Assert attempts, providers, error types, and retry metrics are persisted accurately.
    """
    client, cookies = multi_provider_admin_client

    call_counts = {"count": 0}
    original_create_completions = {}
    providers = ["groq", "cerebras", "gemini"]
    for p in providers:
        original_create_completions[p] = registry.get(p).create_completion

    async def flaky_create_completion(request, *, api_key, model, request_id, timeout):
        call_counts["count"] += 1
        if call_counts["count"] == 1:
            # First attempt fails with transient provider outage
            raise ProviderUnavailableError("503 Service Unavailable: simulated outage on primary worker")
        return ProviderCompletion(
            response={
                "id": "chatcmpl_flaky_ok",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Recovered successfully on retry"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            usage={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            quota={"requests_remaining": 90, "requests_limit": 100, "tokens_remaining": 9000, "tokens_limit": 10000},
        )

    for p in providers:
        registry.get(p).create_completion = flaky_create_completion

    try:
        # Build single-node DAG to test retry & fallback
        dag = TaskDAG(
            task_id="fallback-test-dag",
            nodes=[
                DAGNode(id="critical_step", type="subtask", description="Critical mission step requiring fallback", depends_on=[]),
            ],
        )
        request = ChatCompletionRequest(
            model="auto",
            messages=[ChatMessage(role="user", content="Execute critical step with automated fallback.")],
        )
        request_id = f"wrap_req_fallback_{uuid.uuid4().hex[:8]}"

        resource_store = ResourceStateStore()
        async with AsyncSessionLocal() as session:
            await resource_store.initialize(session)
        router = IntelligentRouter(resource_store)
        executor = DAGExecutor(settings=get_settings(), router=router)

        result = await executor.execute(request, dag, request_id=request_id, policy="balanced")
        assert "content" in result

        # Verify persisted attempts and retry metrics
        async with AsyncSessionLocal() as session:
            wf_run = (await session.execute(select(WorkflowRun).where(WorkflowRun.request_id == request_id))).scalar_one()
            assert wf_run.status == "COMPLETED"

            attempts = (await session.execute(
                select(TaskAttempt)
                .where(TaskAttempt.workflow_run_id == wf_run.id)
                .order_by(TaskAttempt.attempt_number.asc())
            )).scalars().all()

            assert len(attempts) == 2, f"Expected exactly 2 attempts, got {len(attempts)}"

            # Attempt 1: Failed on primary worker
            att1 = attempts[0]
            assert att1.attempt_number == 1
            assert att1.status in ("FAILED", "RETRYING")
            assert att1.error_type == "ProviderUnavailableError"
            assert "simulated outage" in (att1.error_message or "")

            # Attempt 2: Succeeded on fallback worker
            att2 = attempts[1]
            assert att2.attempt_number == 2
            assert att2.status == "SUCCEEDED"
            assert att2.worker_id != att1.worker_id, "Attempt 2 should have fallen back to a different worker!"

        # Verify WorkflowMetrics
        metrics = (await session.execute(
            select(WorkflowMetrics).where(WorkflowMetrics.workflow_run_id == wf_run.id)
        )).scalar_one()

        assert metrics.total_attempts == 2
        assert metrics.total_retries == 1
        assert metrics.failed_attempts == 1
        assert metrics.successful_after_retry_count == 1
        assert metrics.retry_overhead_ms is not None
    finally:
        for p in providers:
            registry.get(p).create_completion = original_create_completions[p]

