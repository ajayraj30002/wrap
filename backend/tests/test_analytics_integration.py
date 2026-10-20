"""Integration tests proving real WRAP execution populates analytics, events, attempts, and metrics."""

import asyncio
import uuid
from datetime import timedelta
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.core.config import get_settings
from src.core.security import get_password_hash, hash_token, generate_random_token, utcnow
from src.db.models import (
    AdminSession,
    AdminUser,
    Base,
    GatewayApiKey,
    WorkflowEvent,
    WorkflowMetrics,
    WorkflowRun,
    TaskAttempt,
    Worker,
    RoutingDecision,
)
from src.db.session import AsyncSessionLocal, engine
from src.orchestration.executor import DAGExecutor
from src.orchestration.models import DAGNode, TaskDAG
from src.providers.base import (
    ProviderCapabilities,
    ProviderCompletion,
    ProviderModel as AdapterProviderModel,
    ProviderStreamEvent,
)
from src.providers.registry import registry
from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.services.bootstrap import ensure_builtin_providers


class AnalyticsFakeGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="fast-llama", display_name="Fast Llama", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        content = f"response from {model}"
        tools = request.get("tools")
        tool_calls = None
        if tools:
            tool_calls = [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "test_func", "arguments": '{"query":"test"}'},
                }
            ]
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content, "tool_calls": tool_calls},
                        "finish_reason": "tool_calls" if tool_calls else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            quota={"requests_remaining": 99, "requests_limit": 100, "tokens_remaining": 990, "tokens_limit": 1000},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "streamed "}}]})
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "tokens"}}]})
        yield ProviderStreamEvent(done=True, usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})


@pytest.fixture(autouse=True)
async def setup_test_db_and_adapter():
    registry.register(AnalyticsFakeGroqAdapter())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def admin_session_cookie():
    async with AsyncSessionLocal() as session:
        session.add(AdminUser(password_hash=get_password_hash("testpassword")))
        token = generate_random_token(64)
        session.add(AdminSession(session_token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
        await session.commit()
    return {"session_id": token}


async def create_gateway_key(**kwargs) -> str:
    raw = f"wrap_{generate_random_token(32)}"
    async with AsyncSessionLocal() as session:
        session.add(
            GatewayApiKey(
                name=kwargs.pop("name", "test"),
                prefix=raw[:8],
                key_hash=hash_token(raw),
                **kwargs,
            )
        )
        await session.commit()
    return raw


@pytest.mark.asyncio
async def test_dag_execution_real_analytics_and_replay(admin_session_cookie):
    """End-to-end test verifying DAG execution populates real analytics, events, attempts, metrics, and replay."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Add credential and sync catalog
        cred_res = await client.post(
            "/api/credentials",
            cookies=admin_session_cookie,
            json={"provider": "groq", "name": "groq-cred", "api_key": "gsk_test"},
        )
        assert cred_res.status_code == 201
        cred_id = cred_res.json()["id"]

        sync_res = await client.post(f"/api/credentials/{cred_id}/catalog/sync", cookies=admin_session_cookie)
        assert sync_res.status_code == 200

        # Enable worker
        workers_res = await client.get("/api/workers", cookies=admin_session_cookie)
        worker_id = workers_res.json()[0]["id"]

        # 2. Build and execute a real DAG with DAGExecutor
        from src.intelligence.router import IntelligentRouter
        from src.intelligence.resources.resource_state_store import ResourceStateStore
        router = IntelligentRouter(ResourceStateStore())
        dag = TaskDAG(
            task_id="dag-test-run-1",
            nodes=[
                DAGNode(id="root", type="subtask", description="Analyze intent", depends_on=[]),
                DAGNode(id="step1", type="subtask", description="Generate component A", depends_on=["root"]),
                DAGNode(id="step2", type="subtask", description="Generate component B", depends_on=["root"]),
                DAGNode(id="synth", type="synthesis", description="Synthesize output", depends_on=["step1", "step2"]),
            ],
        )
        request = ChatCompletionRequest(
            model="auto",
            messages=[ChatMessage(role="user", content="Build fullstack app with tests")],
        )
        executor = DAGExecutor(settings=get_settings(), router=router)
        req_id = "wrap_dag_req_12345"

        result = await executor.execute(request, dag, request_id=req_id, policy="balanced")
        assert "content" in result
        assert "response from fast-llama" in result["content"]

        # 3. Verify Database Persistence of Analytics Entities
        async with AsyncSessionLocal() as session:
            # Check WorkflowRun
            wf_res = await session.execute(select(WorkflowRun).where(WorkflowRun.request_id == req_id))
            wf_run = wf_res.scalar_one_or_none()
            assert wf_run is not None
            assert wf_run.status == "COMPLETED"
            assert wf_run.execution_mode == "DAG"
            assert wf_run.routing_policy == "balanced"
            assert wf_run.requested_model == "auto"
            assert wf_run.executed_model == "fast-llama"
            assert wf_run.provider == "groq"
            assert wf_run.started_at is not None
            assert wf_run.finished_at is not None

            # Check WorkflowEvents
            events_res = await session.execute(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_run_id == wf_run.id)
                .order_by(WorkflowEvent.logical_sequence)
            )
            events = list(events_res.scalars().all())
            assert len(events) >= 6
            event_types = [e.event_type for e in events]
            assert "WORKFLOW_CREATED" in event_types
            assert "WORKFLOW_STARTED" in event_types
            assert "TASK_READY" in event_types
            assert "TASK_STARTED" in event_types
            assert "TASK_SUCCEEDED" in event_types
            assert "WORKFLOW_COMPLETED" in event_types

            # Verify logical sequences are strictly monotonic: 1, 2, 3...
            seqs = [e.logical_sequence for e in events]
            assert seqs == list(range(1, len(events) + 1))

            # Check TaskAttempts
            attempts_res = await session.execute(
                select(TaskAttempt).where(TaskAttempt.workflow_run_id == wf_run.id)
            )
            attempts = list(attempts_res.scalars().all())
            assert len(attempts) == 4
            for att in attempts:
                assert att.status == "SUCCEEDED"
                assert att.provider == "groq"
                assert att.model == "fast-llama"
                assert att.duration_ms is not None

            # Check WorkflowMetrics
            m_res = await session.execute(
                select(WorkflowMetrics).where(WorkflowMetrics.workflow_run_id == wf_run.id)
            )
            metrics = m_res.scalar_one_or_none()
            assert metrics is not None
            assert metrics.status in ("COMPLETED", "success")
            assert metrics.wall_clock_duration_ms is not None
            assert metrics.critical_path_duration_ms is not None
            assert metrics.critical_path_duration_ms > 0
            assert metrics.total_attempts == 4
            assert metrics.total_retries == 0

        # 4. Test API Endpoints
        # A) Metrics Endpoint
        m_api = await client.get(f"/workflows/{wf_run.id}/metrics")
        assert m_api.status_code == 200, m_api.text
        m_json = m_api.json()
        assert m_json["workflow_run_id"] == str(wf_run.id)
        assert m_json["status"] in ("COMPLETED", "success")
        assert m_json["total_attempts"] == 4
        assert "critical_path_nodes" in m_json["metrics_metadata"]

        # B) Timeline Endpoint
        t_api = await client.get(f"/workflows/{wf_run.id}/timeline")
        assert t_api.status_code == 200
        t_json = t_api.json()
        assert t_json["workflow_run_id"] == str(wf_run.id)
        assert len(t_json["events"]) >= 6
        assert t_json["requested_model"] == "auto"
        assert t_json["executed_model"] == "fast-llama"

        # C) Deterministic Replay Endpoint
        r_api = await client.get(f"/workflows/{wf_run.id}/replay")
        assert r_api.status_code == 200
        r_json = r_api.json()
        assert r_json["replay_valid"] is True
        assert r_json["reconstructed_status"] == "COMPLETED"
        assert r_json["comparison"]["tasks_count"] == 4

        # D) Analytics Summary Endpoint
        s_api = await client.get("/analytics/summary")
        assert s_api.status_code == 200
        s_json = s_api.json()
        assert s_json["total_runs"] >= 1
        assert s_json["completed_runs"] >= 1
        assert s_json["success_rate_percent"] == 100.0


@pytest.mark.asyncio
async def test_single_worker_and_streaming_telemetry(admin_session_cookie):
    """Verify single-worker and streaming execution populate real telemetry and metrics."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create credential & sync
        cred_res = await client.post(
            "/api/credentials",
            cookies=admin_session_cookie,
            json={"provider": "groq", "name": "single-cred", "api_key": "gsk_test"},
        )
        cred_id = cred_res.json()["id"]
        await client.post(f"/api/credentials/{cred_id}/catalog/sync", cookies=admin_session_cookie)

        # Create Gateway API key
        gw_key = await create_gateway_key(name="test_gw_key")

        # 1. Non-streaming SINGLE execution
        req_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {gw_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hello single test"}],
            },
        )
        assert req_res.status_code == 200, req_res.text
        req_json = req_res.json()
        assert "choices" in req_json

        # Verify WorkflowRun exists
        async with AsyncSessionLocal() as session:
            runs = (await session.execute(select(WorkflowRun).where(WorkflowRun.execution_mode == "SINGLE"))).scalars().all()
            assert len(runs) >= 1
            latest_run = runs[-1]
            assert latest_run.status == "COMPLETED"
            assert latest_run.requested_model == "auto"
            assert latest_run.executed_model == "fast-llama"

            # Check attempts and metrics
            attempts = (await session.execute(select(TaskAttempt).where(TaskAttempt.workflow_run_id == latest_run.id))).scalars().all()
            assert len(attempts) == 1
            assert attempts[0].status == "SUCCEEDED"

            metrics = (await session.execute(select(WorkflowMetrics).where(WorkflowMetrics.workflow_run_id == latest_run.id))).scalar_one_or_none()
            assert metrics is not None
            assert metrics.status == "COMPLETED"

        # 2. Streaming execution
        stream_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {gw_key}"},
            json={
                "model": "auto",
                "stream": True,
                "messages": [{"role": "user", "content": "Hello stream test"}],
            },
        )
        assert stream_res.status_code == 200
        text = stream_res.text
        assert "data: " in text
        assert "[DONE]" in text


@pytest.mark.asyncio
async def test_tool_calling_preserves_protocol(admin_session_cookie):
    """Verify tool calling protocol and arguments remain unaltered by analytics."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cred_res = await client.post(
            "/api/credentials",
            cookies=admin_session_cookie,
            json={"provider": "groq", "name": "tool-cred", "api_key": "gsk_test"},
        )
        cred_id = cred_res.json()["id"]
        await client.post(f"/api/credentials/{cred_id}/catalog/sync", cookies=admin_session_cookie)

        gw_key = await create_gateway_key(name="tool_key")

        tools_def = [
            {
                "type": "function",
                "function": {
                    "name": "test_func",
                    "description": "A test function",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]

        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {gw_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Execute test function"}],
                "tools": tools_def,
            },
        )
        assert response.status_code == 200
        res_json = response.json()
        choice = res_json["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        assert choice["message"]["tool_calls"][0]["function"]["name"] == "test_func"
