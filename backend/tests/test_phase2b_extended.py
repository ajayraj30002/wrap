import asyncio
import uuid
import time
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
    Credential
)
from src.db.session import AsyncSessionLocal, engine
from src.orchestration.analyzer import TaskAnalyzer
from src.orchestration.models import DAGNode, TaskDAG
from src.orchestration.validator import DAGValidator, InvalidDAGError
from src.orchestration.executor import DAGExecutor
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderModel as AdapterProviderModel, ProviderStreamEvent, ModelNotFoundError
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers
from src.core.config import get_settings


class ExtendedFakeGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)
    
    def __init__(self):
        self.call_count = 0
        self.delay = 0
        self.fail_models = set()
        self.model_not_found_models = set()
        self.test_cred_fail = False
        self.list_models_fail = False

    async def list_models(self, *, api_key: str, timeout: float):
        if self.list_models_fail:
            raise Exception("Catalog API failure")
        return [
            AdapterProviderModel(external_model_id="fake-fast", display_name="Fake Fast", streaming=True),
            AdapterProviderModel(external_model_id="fake-quality", display_name="Fake Quality", streaming=True),
            AdapterProviderModel(external_model_id="fake-deprecated", display_name="Fake Deprecated", status="DEPRECATED", streaming=True),
            # duplicate to test handling
            AdapterProviderModel(external_model_id="fake-fast", display_name="Fake Fast 2", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        self.call_count += 1
        import time
        t_start = time.monotonic()
        print(f"create_completion START {request_id} at {t_start:.3f}")
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        print(f"create_completion END {request_id} at {time.monotonic():.3f} (duration: {time.monotonic()-t_start:.3f})")
        if model in self.model_not_found_models:
            raise ModelNotFoundError("Model not found")
        if model in self.fail_models:
            raise Exception("Provider failure")
            
        content = f"{model}: ok"
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
        if self.test_cred_fail:
            raise Exception("Auth failed")
        return None

fake_adapter = ExtendedFakeGroqAdapter()

@pytest.fixture(autouse=True)
async def clean_database():
    fake_adapter.call_count = 0
    fake_adapter.delay = 0
    fake_adapter.fail_models = set()
    fake_adapter.model_not_found_models = set()
    fake_adapter.test_cred_fail = False
    fake_adapter.list_models_fail = False
    registry.register(fake_adapter)
    
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

async def create_credential_api(client: AsyncClient, cookies: dict):
    response = await client.post(
        "/api/credentials",
        cookies=cookies,
        json={"provider": "groq", "name": "key", "api_key": "gsk_test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# DAG Execution Tests
@pytest.mark.asyncio
async def test_dag_executor_runs_independent_nodes_in_parallel():
    # Setup DAG with 2 independent nodes and 1 dependent node
    dag = TaskDAG(
        task_id="t1",
        nodes=[
            DAGNode(id="n1", type="subtask", description="desc1", timeout_seconds=5),
            DAGNode(id="n2", type="subtask", description="desc2", timeout_seconds=5),
            DAGNode(id="n3", type="synthesis", description="desc3", depends_on=["n1", "n2"], timeout_seconds=5),
        ]
    )
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    
    # Needs a credential and worker first
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        
    req = ChatCompletionRequest(model="fake-fast", messages=[ChatMessage(role="user", content="test")])
    executor = DAGExecutor(settings=get_settings(), router=get_intelligent_router())
    
    fake_adapter.delay = 1.0 # Add delay to prove parallel execution
    
    start_time = time.monotonic()
    result = await executor.execute(req, dag, request_id="req1")
    duration = time.monotonic() - start_time
    
    # If sequential, it would take > 3.0s (1.0s * 3)
    # If parallel, it should take ~ 2.0s (1.0s for n1 and n2 concurrently, then 1.0s for n3)
    assert duration < 3.2
    assert result["type"] == "synthesis"

@pytest.mark.asyncio
async def test_dag_executor_respects_concurrency_limits():
    settings = get_settings()
    settings.DAG_MAX_PARALLEL_NODES = 2
    
    dag = TaskDAG(
        task_id="t1",
        nodes=[
            DAGNode(id="n1", type="subtask", description="desc1", timeout_seconds=5),
            DAGNode(id="n2", type="subtask", description="desc2", timeout_seconds=5),
            DAGNode(id="n3", type="subtask", description="desc3", timeout_seconds=5),
            DAGNode(id="n4", type="synthesis", description="desc4", depends_on=["n1", "n2", "n3"], timeout_seconds=5),
        ]
    )
    
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    
    req = ChatCompletionRequest(model="fake-fast", messages=[ChatMessage(role="user", content="test")])
    executor = DAGExecutor(settings=settings, router=get_intelligent_router())
    
    fake_adapter.delay = 1.0
    start_time = time.monotonic()
    result = await executor.execute(req, dag, request_id="req2")
    duration = time.monotonic() - start_time
    
    # 2 nodes parallel (1.0s) -> 1 node (1.0s) -> synthesis (1.0s) => total ~3.0s
    # If it was fully parallel, it would be 2.0s.
    assert duration >= 2.8
    
@pytest.mark.asyncio
async def test_dag_executor_node_timeout():
    dag = TaskDAG(
        task_id="t1",
        nodes=[
            DAGNode(id="n1", type="subtask", description="desc1", timeout_seconds=1),
        ]
    )
    
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    req = ChatCompletionRequest(model="fake-fast", messages=[ChatMessage(role="user", content="test")])
    executor = DAGExecutor(settings=get_settings(), router=get_intelligent_router())
    
    fake_adapter.delay = 2.0 # > timeout
    
    with pytest.raises(Exception):
        await executor.execute(req, dag, request_id="req3")
        
    async with AsyncSessionLocal() as session:
        node_status = (await session.execute(select(ExecutionNode).where(ExecutionNode.node_id == "n1"))).scalar_one().status
        assert node_status == "failed"

@pytest.mark.asyncio
async def test_dag_executor_retries_on_failure():
    settings = get_settings()
    settings.DAG_MAX_RETRIES_PER_NODE = 2
    
    dag = TaskDAG(
        task_id="t1",
        nodes=[
            DAGNode(id="n1", type="subtask", description="desc1"),
        ]
    )
    
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    req = ChatCompletionRequest(model="fake-fast", messages=[ChatMessage(role="user", content="test")])
    executor = DAGExecutor(settings=settings, router=get_intelligent_router())
    
    fake_adapter.fail_models.add("fake-fast")
    fake_adapter.fail_models.add("fake-quality")
    
    with pytest.raises(Exception):
        await executor.execute(req, dag, request_id="req4")
        
    async with AsyncSessionLocal() as session:
        node = (await session.execute(select(ExecutionNode).where(ExecutionNode.node_id == "n1"))).scalar_one()
        assert node.retry_count == 2
        assert node.status == "failed"
        
@pytest.mark.asyncio
async def test_dag_executor_dependency_failure_propagation():
    dag = TaskDAG(
        task_id="t1",
        nodes=[
            DAGNode(id="n1", type="subtask", description="desc1"),
            DAGNode(id="n2", type="synthesis", description="desc2", depends_on=["n1"]),
        ]
    )
    
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    req = ChatCompletionRequest(model="fake-fast", messages=[ChatMessage(role="user", content="test")])
    executor = DAGExecutor(settings=get_settings(), router=get_intelligent_router())
    
    fake_adapter.fail_models.add("fake-fast")
    fake_adapter.fail_models.add("fake-quality")
    
    with pytest.raises(Exception):
        await executor.execute(req, dag, request_id="req5")
        
    async with AsyncSessionLocal() as session:
        n2_status = (await session.execute(select(ExecutionNode).where(ExecutionNode.node_id == "n2"))).scalar_one().status
        assert n2_status == "skipped"

@pytest.mark.asyncio
async def test_routing_excludes_unavailable_worker():
    # Phase 2A/B router should exclude unhealthy/disabled workers
    async with AsyncSessionLocal() as session:
        from src.services.credentials import create_credential
        cred = await create_credential(session, provider_name="groq", name="test", api_key="test", model=None, metadata={})
        workers = (await session.execute(select(Worker))).scalars().all()
        for w in workers:
            w.health_status = "unhealthy"
        await session.commit()
        
    from src.schemas.openai import ChatCompletionRequest, ChatMessage
    from src.api.routes.openai import get_intelligent_router
    req = ChatCompletionRequest(model="auto", messages=[ChatMessage(role="user", content="test")])
    
    from src.scheduler import NoWorkerAvailable
    
    async with AsyncSessionLocal() as session:
        with pytest.raises(NoWorkerAvailable):
            await get_intelligent_router().route(req, session=session, request_id="req_exclude")
            
# Catalog Tests
@pytest.mark.asyncio
async def test_catalog_upsert_handles_duplicates(admin_session_cookie):
    from src.main import app
    # Our fake adapter returns "fake-fast" twice.
    async with AsyncClient(app=app, base_url="http://test") as client:
        credential = await create_credential_api(client, admin_session_cookie)
        catalog = await client.get("/api/provider-models?provider=groq", cookies=admin_session_cookie)
        assert catalog.status_code == 200
        models = catalog.json()
        
        # It should handle duplicates gracefully and we should see distinct external_model_ids
        external_ids = [m["external_model_id"] for m in models]
        assert len(external_ids) == len(set(external_ids))

@pytest.mark.asyncio
async def test_catalog_marks_deprecated_models(admin_session_cookie):
    from src.main import app
    async with AsyncClient(app=app, base_url="http://test") as client:
        await create_credential_api(client, admin_session_cookie)
        catalog = await client.get("/api/provider-models?provider=groq", cookies=admin_session_cookie)
        
        deprecated_model = next((m for m in catalog.json() if m["external_model_id"] == "fake-deprecated"), None)
        assert deprecated_model is not None
        assert deprecated_model["status"] == "DEPRECATED"

@pytest.mark.asyncio
async def test_model_not_found_triggers_catalog_refresh(admin_session_cookie):
    from src.main import app
    key = await create_gateway_key()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        await create_credential_api(client, admin_session_cookie)
        
    fake_adapter.model_not_found_models.add("fake-fast")
    fake_adapter.model_not_found_models.add("fake-quality")
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "fake-fast", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert response.status_code == 404
        
    async with AsyncSessionLocal() as session:
        pm = (await session.execute(select(ProviderModel).where(ProviderModel.external_model_id == "fake-fast"))).scalar_one()
        assert pm.status == "STALE"

@pytest.mark.asyncio
async def test_catalog_sync_failure_preserves_state(admin_session_cookie):
    from src.main import app
    async with AsyncClient(app=app, base_url="http://test") as client:
        cred = await create_credential_api(client, admin_session_cookie)
        
        # Now fail the catalog api
        fake_adapter.list_models_fail = True
        
        resp = await client.post(f"/api/credentials/{cred['id']}/catalog/sync", cookies=admin_session_cookie)
        # Even if it fails (returns 0 models or throws), existing models should remain in DB but maybe marked STALE
        assert resp.status_code == 200
        
        catalog = await client.get("/api/provider-models?provider=groq", cookies=admin_session_cookie)
        models = catalog.json()
        assert len(models) > 0 # Models preserved
        assert all(m["status"] in ("STALE", "DEPRECATED") for m in models) # Marked stale or left deprecated

@pytest.mark.asyncio
async def test_default_worker_creation(admin_session_cookie):
    from src.main import app
    async with AsyncClient(app=app, base_url="http://test") as client:
        await create_credential_api(client, admin_session_cookie)
        
        workers = await client.get("/api/workers", cookies=admin_session_cookie)
        assert len(workers.json()) == 1 # 1 default worker created
