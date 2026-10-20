import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.security import get_password_hash, hash_token
from src.db.models import (
    AdminSession,
    AdminUser,
    Base,
    ExecutionNode,
    ExecutionRun,
    GatewayApiKey,
    ProviderModel,
    RoutingDecision,
    Worker,
)
from src.db.session import AsyncSessionLocal, engine
from src.orchestration.analyzer import TaskAnalyzer
from src.orchestration.models import DAGNode, TaskDAG
from src.orchestration.validator import DAGValidator, InvalidDAGError
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderModel as AdapterProviderModel, ProviderStreamEvent
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers


class Phase2BFakeGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="fake-fast", display_name="Fake Fast", streaming=True),
            AdapterProviderModel(external_model_id="fake-quality", display_name="Fake Quality", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        content = f"{model}: " + request["messages"][-1]["content"][:32]
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
            usage={"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "ok"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def clean_database():
    registry.register(Phase2BFakeGroqAdapter())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def admin_session_cookie():
    from datetime import timedelta
    from src.core.security import generate_random_token, utcnow

    async with AsyncSessionLocal() as session:
        session.add(AdminUser(password_hash=get_password_hash("testpassword")))
        token = generate_random_token(64)
        session.add(AdminSession(session_token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
        await session.commit()
    return {"session_id": token}


async def create_gateway_key(**kwargs) -> str:
    from src.core.security import generate_random_token

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


async def create_credential(client: AsyncClient, cookies: dict):
    response = await client.post(
        "/api/credentials",
        cookies=cookies,
        json={"provider": "groq", "name": "key", "api_key": "gsk_test_secret_value"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_catalog_sync_and_multiple_workers_per_credential(admin_session_cookie):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        credential = await create_credential(client, admin_session_cookie)
        catalog = await client.get("/api/provider-models?provider=groq", cookies=admin_session_cookie)
        assert catalog.status_code == 200
        models = catalog.json()
        assert {item["external_model_id"] for item in models} == {"fake-fast", "fake-quality"}

        worker_response = await client.post(
            "/api/workers",
            cookies=admin_session_cookie,
            json={"credential_id": credential["id"], "provider_model_id": models[1]["id"]},
        )
        assert worker_response.status_code == 201, worker_response.text
        workers = await client.get("/api/workers", cookies=admin_session_cookie)

    assert len(workers.json()) == 2
    assert len({worker["credential_id"] for worker in workers.json()}) == 1


def test_task_analyzer_keeps_simple_requests_single_worker():
    from src.schemas.openai import ChatCompletionRequest, ChatMessage

    request = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="What is the capital of Japan?")])
    assert TaskAnalyzer().should_decompose(request) is False


def test_dag_validator_rejects_cycles_and_missing_dependencies():
    validator = DAGValidator(max_nodes=8, max_depth=4, max_parallel_nodes=3, max_total_execution_time=120)
    with pytest.raises(InvalidDAGError):
        validator.validate(TaskDAG(task_id="t", nodes=[DAGNode(id="a", type="subtask", description="a", depends_on=["b"])]))
    with pytest.raises(InvalidDAGError):
        validator.validate(
            TaskDAG(
                task_id="t",
                nodes=[
                    DAGNode(id="a", type="subtask", description="a", depends_on=["b"]),
                    DAGNode(id="b", type="subtask", description="b", depends_on=["a"]),
                ],
            )
        )


@pytest.mark.asyncio
async def test_dag_route_executes_nodes_and_persists_node_routing(admin_session_cookie):
    from src.main import app

    key = await create_gateway_key()
    async with AsyncClient(app=app, base_url="http://test") as client:
        await create_credential(client, admin_session_cookie)
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Compare Alpha, Beta, and Gamma for a production RAG system and provide a recommendation."}],
            },
        )
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as session:
        run = (await session.execute(select(ExecutionRun))).scalar_one()
        nodes = (await session.execute(select(ExecutionNode))).scalars().all()
        decisions = (await session.execute(select(RoutingDecision).where(RoutingDecision.execution_run_id == run.id))).scalars().all()
    assert run.execution_mode == "DAG"
    assert run.status == "success"
    assert len(nodes) >= 4
    assert {node.status for node in nodes} == {"success"}
    assert len(decisions) == len(nodes)
    assert all(decision.execution_node_id for decision in decisions)


@pytest.mark.asyncio
async def test_api_key_worker_pool_limits_models_and_routing(admin_session_cookie):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        credential = await create_credential(client, admin_session_cookie)
        catalog = (await client.get("/api/provider-models?provider=groq", cookies=admin_session_cookie)).json()
        await client.post("/api/workers", cookies=admin_session_cookie, json={"credential_id": credential["id"], "provider_model_id": catalog[1]["id"]})
        workers = (await client.get("/api/workers", cookies=admin_session_cookie)).json()

    chosen = next(worker for worker in workers if worker["model"] == "fake-quality")
    key = await create_gateway_key(worker_selection_mode="WORKER_POOL", allowed_worker_ids=[chosen["id"]])
    async with AsyncClient(app=app, base_url="http://test") as client:
        models = await client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "auto", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert models.status_code == 200
    assert [item["id"] for item in models.json()["data"]] == ["auto", "fake-quality"]
    assert response.status_code == 200
    async with AsyncSessionLocal() as session:
        decision = (await session.execute(select(RoutingDecision).order_by(RoutingDecision.timestamp.desc()))).scalars().first()
    assert decision.selected_worker == chosen["id"]


@pytest.mark.asyncio
async def test_stale_catalog_worker_excluded_from_v1_models(admin_session_cookie):
    from src.main import app

    key = await create_gateway_key()
    async with AsyncClient(app=app, base_url="http://test") as client:
        await create_credential(client, admin_session_cookie)
    async with AsyncSessionLocal() as session:
        worker = (await session.execute(select(Worker))).scalars().first()
        provider_model = await session.get(ProviderModel, worker.provider_model_id)
        provider_model.status = "STALE"
        await session.commit()
    async with AsyncClient(app=app, base_url="http://test") as client:
        models = await client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    assert models.status_code == 200
    assert models.json()["data"] == []
