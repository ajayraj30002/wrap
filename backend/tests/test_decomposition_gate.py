from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.security import generate_random_token, get_password_hash, hash_token, utcnow
from src.db.models import AdminSession, AdminUser, Base, ExecutionNode, ExecutionRun, GatewayApiKey, RoutingDecision
from src.db.session import AsyncSessionLocal, engine
from src.main import app
from src.orchestration.analyzer import TaskAnalyzer
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderStreamEvent
from src.providers.registry import registry
from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.services.bootstrap import ensure_builtin_providers


class MockAgentProviderAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ("fake-agent-model",)
    capabilities = ProviderCapabilities(
        streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True
    )

    def normalize_request(self, request, model):
        return request

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": "chatcmpl_mock_done",
                "object": "chat.completion",
                "created": 1234567890,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Component completed successfully.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
            usage={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            quota=None,
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout):
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def setup_test_environment():
    registry.register(MockAgentProviderAdapter())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def auth_context():
    async with AsyncSessionLocal() as session:
        user = AdminUser(password_hash=get_password_hash("testpwd"))
        session.add(user)
        token = generate_random_token(64)
        session_obj = AdminSession(
            session_token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=1),
        )
        session.add(session_obj)

        raw_key = generate_random_token(32)
        wrap_key = f"wrap_{raw_key}"
        key_obj = GatewayApiKey(
            name="test-key",
            prefix=wrap_key[:8],
            key_hash=hash_token(wrap_key),
        )
        session.add(key_obj)
        await session.commit()
    return {"cookies": {"session_id": token}, "wrap_key": wrap_key}


def test_simple_queries_remain_single():
    analyzer = TaskAnalyzer()

    # Informational / conceptual queries
    req1 = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="What is RRF?")])
    assert analyzer.should_decompose(req1) is False
    dec1 = analyzer.assess(req1)
    assert dec1.execution_mode == "SINGLE"

    req2 = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="Explain this function.")])
    assert analyzer.should_decompose(req2) is False

    req3 = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="What is the capital of Japan?")])
    assert analyzer.should_decompose(req3) is False


def test_simple_code_edits_remain_single():
    analyzer = TaskAnalyzer()

    req1 = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="Fix this typo in line 42.")])
    assert analyzer.should_decompose(req1) is False
    assert analyzer.assess(req1).execution_mode == "SINGLE"

    req2 = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="Write a two-line Python function to reverse a string.")])
    assert analyzer.should_decompose(req2) is False


def test_explicit_model_remains_single():
    analyzer = TaskAnalyzer()

    complex_prompt = (
        "Build a production-quality FastAPI analytics application with:\n"
        "- database\n"
        "- REST API\n"
        "- analytics\n"
        "- frontend\n"
        "- tests\n"
        "- documentation"
    )
    # When explicit single execution is requested (e.g. :single suffix or execution_mode="single"), remains SINGLE
    req1 = ChatCompletionRequest(model="llama-3.3-70b:single", messages=[ChatMessage(role="user", content=complex_prompt)])
    dec1 = analyzer.assess(req1)
    assert dec1.should_decompose is False
    assert dec1.execution_mode == "SINGLE"
    assert "Explicit single execution requested" in dec1.reason

    # For simple queries, any model remains SINGLE
    simple_req = ChatCompletionRequest(model="llama-3.3-70b", messages=[ChatMessage(role="user", content="What is the capital of France?")])
    dec_simple = analyzer.assess(simple_req)
    assert dec_simple.should_decompose is False
    assert dec_simple.execution_mode == "SINGLE"

    # But when situation demands DAG, any model (including llama-3.3-70b, deepseek, etc.) decomposes!
    dec2 = analyzer.assess(ChatCompletionRequest(model="llama-3.3-70b", messages=[ChatMessage(role="user", content=complex_prompt)]))
    assert dec2.should_decompose is True
    assert dec2.execution_mode == "DAG"


def test_software_engineering_workload_decomposes_to_dag():
    analyzer = TaskAnalyzer()

    complex_prompt = (
        "Build a production-quality FastAPI analytics application with:\n"
        "- database\n"
        "- REST API\n"
        "- analytics\n"
        "- frontend\n"
        "- tests\n"
        "- documentation\n"
        "Independently plan the major areas first, then implement them, integrate them, run tests, and fix failures."
    )
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content=complex_prompt)])
    decision = analyzer.assess(req)
    assert decision.should_decompose is True
    assert decision.execution_mode == "DAG"
    assert decision.detected_pattern == "software_engineering"
    assert len(decision.workstreams) >= 4
    assert "database" in decision.workstreams
    assert "api" in decision.workstreams

    # Build DAG and inspect structure
    dag = analyzer.build_dag(req, task_id="task_swe_1")
    assert len(dag.nodes) >= 6

    node_types = {n.type for n in dag.nodes}
    assert "subtask" in node_types
    assert "aggregation" in node_types
    assert "synthesis" in node_types

    # Subtasks should be independent (no dependencies)
    subtasks = [n for n in dag.nodes if n.type == "subtask"]
    assert all(len(n.depends_on) == 0 for n in subtasks)

    # Integration node depends on core subtasks
    integration_node = next(n for n in dag.nodes if n.type == "aggregation")
    assert len(integration_node.depends_on) >= 3

    # Synthesis node depends on integration
    synthesis_node = next(n for n in dag.nodes if n.type == "synthesis")
    assert integration_node.id in synthesis_node.depends_on
    assert synthesis_node.priority == 10


def test_comparative_research_decomposes_to_dag():
    analyzer = TaskAnalyzer()

    prompt = "Compare Redis, Memcached, and Dragonfly for high-throughput caching and provide a recommendation."
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content=prompt)])
    decision = analyzer.assess(req)
    assert decision.should_decompose is True
    assert decision.execution_mode == "DAG"
    assert decision.detected_pattern == "comparative_research"
    assert len(decision.workstreams) >= 2


@pytest.mark.asyncio
async def test_live_software_engineering_dag_execution(auth_context):
    """Real live execution of complex software engineering request via /v1/chat/completions."""
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create worker
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-test",
                "api_key": "gsk_test_123",
                "model": "fake-agent-model",
            },
        )

        prompt = (
            "Build a small production-quality Python service from scratch.\n"
            "The service must include:\n"
            "- database layer\n"
            "- REST API\n"
            "- analytics layer\n"
            "- frontend dashboard\n"
            "- tests\n"
            "- documentation\n"
            "Plan the major areas, implement them, integrate them, and verify."
        )

        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["finish_reason"] == "stop"

        # Verify DB execution run and efficiency telemetry
        async with AsyncSessionLocal() as session:
            run_result = await session.execute(
                select(ExecutionRun).order_by(ExecutionRun.started_at.desc())
            )
            run = run_result.scalars().first()
            assert run is not None
            assert run.execution_mode == "DAG"
            assert run.status == "success"
            assert run.node_count >= 6
            assert run.completed_nodes == run.node_count

            # Verify efficiency telemetry recorded in run_metadata
            meta = run.run_metadata
            assert "planning_ms" in meta
            assert "sum_node_latency_ms" in meta
            assert "critical_path_ms" in meta
            assert "parallel_speedup" in meta
            assert "worker_count" in meta
            assert "provider_count" in meta
            assert "decomposition_reason" in meta
            assert "software engineering" in meta["decomposition_reason"].lower()

            # Verify execution nodes in DB
            node_result = await session.execute(
                select(ExecutionNode).where(ExecutionNode.execution_run_id == run.id)
            )
            nodes = list(node_result.scalars().all())
            assert len(nodes) == run.node_count
            assert all(n.status == "success" for n in nodes)

            # Verify routing decisions were recorded for each node
            dec_result = await session.execute(
                select(RoutingDecision).where(RoutingDecision.execution_run_id == run.id)
            )
            decisions = list(dec_result.scalars().all())
            assert len(decisions) == len(nodes)


def test_frontier_alias_gpt4o_decomposes_on_multi_workstream():
    """Frontier aliases like gpt-4o decompose into DAG for multi-workstream tasks, but remain SINGLE for simple queries."""
    analyzer = TaskAnalyzer()

    # 1. Complex multi-workstream prompt with gpt-4o MUST decompose to DAG
    complex_prompt = (
        "Build a production-quality FastAPI analytics application with:\n"
        "- database schema and migrations\n"
        "- REST API endpoints\n"
        "- analytics processing\n"
        "- frontend React dashboard\n"
        "- automated tests\n"
        "- system documentation"
    )
    req_gpt4o = ChatCompletionRequest(model="gpt-4o", messages=[ChatMessage(role="user", content=complex_prompt)])
    dec_gpt4o = analyzer.assess(req_gpt4o)
    assert dec_gpt4o.should_decompose is True
    assert dec_gpt4o.execution_mode == "DAG"
    assert dec_gpt4o.detected_pattern == "software_engineering"
    assert len(dec_gpt4o.workstreams) >= 4

    # 2. claude-3-5-sonnet and o1 also decompose on multi-workstream tasks
    req_claude = ChatCompletionRequest(model="claude-3-5-sonnet", messages=[ChatMessage(role="user", content=complex_prompt)])
    assert analyzer.assess(req_claude).execution_mode == "DAG"

    req_o1 = ChatCompletionRequest(model="o1", messages=[ChatMessage(role="user", content=complex_prompt)])
    assert analyzer.assess(req_o1).execution_mode == "DAG"

    # 3. Simple query with gpt-4o MUST remain SINGLE
    simple_query = ChatCompletionRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="What is RRF?")])
    dec_simple = analyzer.assess(simple_query)
    assert dec_simple.should_decompose is False
    assert dec_simple.execution_mode == "SINGLE"

    # 4. Simple bug fix / code edit with gpt-4o MUST remain SINGLE
    simple_edit = ChatCompletionRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Fix this typo in line 42.")])
    dec_edit = analyzer.assess(simple_edit)
    assert dec_edit.should_decompose is False
    assert dec_edit.execution_mode == "SINGLE"

    # 5. Tool / Function calling with gpt-4o MUST remain SINGLE for tool dispatch
    req_tools = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content=complex_prompt)],
        tools=[{"type": "function", "function": {"name": "query_db"}}],
    )
    dec_tools = analyzer.assess(req_tools)
    assert dec_tools.should_decompose is False
    assert dec_tools.execution_mode == "SINGLE"


@pytest.mark.asyncio
async def test_live_gpt4o_frontier_dag_execution(auth_context):
    """Real live execution of complex request requesting model='gpt-4o' executes as DAG."""
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create worker
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-test-gpt4o",
                "api_key": "gsk_test_456",
                "model": "fake-agent-model",
            },
        )

        prompt = (
            "Build a production-quality Python service from scratch.\n"
            "The service must include:\n"
            "- database layer\n"
            "- REST API\n"
            "- analytics layer\n"
            "- frontend dashboard\n"
            "- tests\n"
            "- documentation\n"
            "Plan each component and implement them."
        )

        # Send request explicitly specifying model="gpt-4o"
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1

        # Verify DB execution run recorded execution_mode="DAG"
        async with AsyncSessionLocal() as session:
            run_result = await session.execute(
                select(ExecutionRun).order_by(ExecutionRun.started_at.desc())
            )
            run = run_result.scalars().first()
            assert run is not None
            assert run.execution_mode == "DAG"
            assert run.status == "success"
            assert run.node_count >= 6

