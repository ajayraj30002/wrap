import json
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.db.models import Base, Credential, RequestMetric, RoutingDecision, Worker, AdminUser, AdminSession, GatewayApiKey
from src.db.session import AsyncSessionLocal, engine
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderStreamEvent
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers
from src.core.security import get_password_hash, hash_token


class FakeGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ("fake-model",)

    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": "chatcmpl_fake",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            quota={"requests_remaining": 99, "requests_limit": 100, "tokens_remaining": None, "tokens_limit": None, "reset_at": None, "source": "response_header"},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(
            payload={
                "id": "chatcmpl_fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": "hel"}, "finish_reason": None}],
            },
            usage={"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
        )
        yield ProviderStreamEvent(
            payload={
                "id": "chatcmpl_fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}],
            },
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        )
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def clean_database():
    registry.register(FakeGroqAdapter())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def admin_session_cookie():
    from src.core.security import generate_random_token, utcnow
    from datetime import timedelta
    async with AsyncSessionLocal() as session:
        user = AdminUser(password_hash=get_password_hash("testpassword"))
        session.add(user)
        
        token = generate_random_token(64)
        session_obj = AdminSession(
            session_token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=1)
        )
        session.add(session_obj)
        await session.commit()
    return {"session_id": token}


@pytest.fixture
async def gateway_api_key():
    from src.core.security import generate_random_token
    async with AsyncSessionLocal() as session:
        raw = generate_random_token(32)
        full_key = f"wrap_{raw}"
        key_obj = GatewayApiKey(
            name="test",
            prefix=full_key[:8],
            key_hash=hash_token(full_key)
        )
        session.add(key_obj)
        await session.commit()
    return full_key


async def add_fake_credential(client: AsyncClient, cookies: dict) -> dict:
    response = await client.post(
        "/api/credentials",
        cookies=cookies,
        json={"provider": "groq", "name": "test key", "api_key": "gsk_test_secret_value", "model": "fake-model"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_credential_is_masked_and_worker_is_created(admin_session_cookie):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        credential = await add_fake_credential(client, admin_session_cookie)
        assert credential["masked_identifier"] != "gsk_test_secret_value"
        assert "secret_value" not in json.dumps(credential)
        credentials = await client.get("/api/credentials", cookies=admin_session_cookie)
        workers = await client.get("/api/workers", cookies=admin_session_cookie)

    assert credentials.status_code == 200
    assert workers.status_code == 200
    assert workers.json()[0]["model"] == "fake-model"


@pytest.mark.asyncio
async def test_chat_completion_persists_metrics_and_routing(admin_session_cookie, gateway_api_key):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        await add_fake_credential(client, admin_session_cookie)
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {gateway_api_key}"},
            json={"model": "fake-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "hello"
    async with AsyncSessionLocal() as session:
        metrics = (await session.execute(select(RequestMetric))).scalars().all()
        decisions = (await session.execute(select(RoutingDecision))).scalars().all()
        workers = (await session.execute(select(Worker))).scalars().all()
    assert len(metrics) == 1
    assert metrics[0].status == "success"
    assert metrics[0].total_tokens == 5
    assert len(decisions) == 1
    assert decisions[0].selected_worker == str(workers[0].id)


@pytest.mark.asyncio
async def test_streaming_completion_uses_openai_sse_and_persists_metrics(admin_session_cookie, gateway_api_key):
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        await add_fake_credential(client, admin_session_cookie)
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {gateway_api_key}"},
            json={"model": "fake-model", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as response:
            text = await response.aread()

    decoded = text.decode("utf-8")
    assert response.status_code == 200
    assert "data: " in decoded
    assert "data: [DONE]" in decoded
    async with AsyncSessionLocal() as session:
        metric = (await session.execute(select(RequestMetric))).scalar_one()
    assert metric.streamed is True
    assert metric.status == "success"


@pytest.mark.asyncio
async def test_authentication_required():
    from src.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/models")
    assert response.status_code == 401
