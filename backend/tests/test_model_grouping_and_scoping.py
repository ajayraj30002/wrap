import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from src.core.security import get_password_hash, hash_token
from src.db.models import (
    AdminSession,
    AdminUser,
    Base,
    GatewayApiKey,
    Provider,
    ProviderModel,
    RoutingDecision,
    Worker,
)
from src.db.session import AsyncSessionLocal, engine
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderModel as AdapterProviderModel, ProviderStreamEvent
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers


class MockTierGroqAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="groq/llama-3.1-8b-instant", display_name="Llama 3.1 8B Instant", streaming=True),
            AdapterProviderModel(external_model_id="groq/llama-3.3-70b-versatile", display_name="Llama 3.3 70B", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        content = f"response-from-groq:{model}"
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 1000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "streamed"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


class MockTierCerebrasAdapter:
    name = "cerebras"
    display_name = "Cerebras"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="cerebras/llama-3.3-70b", display_name="Cerebras Llama 70B", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        content = f"response-from-cerebras:{model}"
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 1000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            },
            usage={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "streamed"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def clean_database():
    registry.register(MockTierGroqAdapter())
    registry.register(MockTierCerebrasAdapter())
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
                name=kwargs.pop("name", "test-key"),
                prefix=raw[:8],
                key_hash=hash_token(raw),
                **kwargs,
            )
        )
        await session.commit()
    return raw


async def setup_two_workers(client: AsyncClient, cookies: dict) -> tuple[dict, dict]:
    # 1. Add Cerebras credential & worker
    c_resp = await client.post(
        "/api/credentials",
        cookies=cookies,
        json={"provider": "cerebras", "name": "c-key", "api_key": "csk_test_secret_cerebras"},
    )
    assert c_resp.status_code == 201, c_resp.text
    c_cred = c_resp.json()

    # 2. Add Groq credential & worker
    g_resp = await client.post(
        "/api/credentials",
        cookies=cookies,
        json={"provider": "groq", "name": "g-key", "api_key": "gsk_test_secret_groq"},
    )
    assert g_resp.status_code == 201, g_resp.text
    g_cred = g_resp.json()

    workers_resp = await client.get("/api/workers", cookies=cookies)
    assert workers_resp.status_code == 200
    workers = workers_resp.json()
    assert len(workers) == 2

    cerebras_worker = next(w for w in workers if w["provider"] == "cerebras")
    groq_worker = next(w for w in workers if w["provider"] == "groq")
    return cerebras_worker, groq_worker


@pytest.mark.asyncio
async def test_get_model_groups_endpoint(admin_session_cookie):
    """Verify GET /api/model-groups returns all built-in virtual tiers with active counts."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        groups_res = await client.get("/api/model-groups", cookies=admin_session_cookie)
        assert groups_res.status_code == 200
        groups = groups_res.json()

        group_ids = [g["id"] for g in groups]
        assert "fast-tier" in group_ids
        assert "reasoning-tier" in group_ids
        assert "economy-tier" in group_ids
        assert "coding-tier" in group_ids

        fast_tier = next(g for g in groups if g["id"] == "fast-tier")
        assert fast_tier["default_policy"] == "latency_optimized"
        assert "cerebras/llama-3.3-70b" in fast_tier["models"]
        # Both Cerebras worker and Groq worker are members of fast-tier
        assert fast_tier["active_workers_count"] >= 2


@pytest.mark.asyncio
async def test_models_endpoint_scope_and_virtual_cards(admin_session_cookie):
    """Verify /v1/models includes virtual tier cards and enforces worker scope per API key."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        # 1. Unrestricted AUTO key sees both physical models + virtual cards
        auto_key = await create_gateway_key(worker_selection_mode="AUTO")
        res_auto = await client.get("/v1/models", headers={"Authorization": f"Bearer {auto_key}"})
        assert res_auto.status_code == 200
        model_ids_auto = [m["id"] for m in res_auto.json()["data"]]
        assert "cerebras/llama-3.3-70b" in model_ids_auto
        assert "groq/llama-3.1-8b-instant" in model_ids_auto
        assert "fast-tier" in model_ids_auto

        # 2. Key with WORKER_POOL scoped ONLY to Cerebras worker
        pool_key = await create_gateway_key(
            worker_selection_mode="WORKER_POOL",
            allowed_worker_ids=[w_cerebras["id"]],
        )
        res_pool = await client.get("/v1/models", headers={"Authorization": f"Bearer {pool_key}"})
        assert res_pool.status_code == 200
        model_ids_pool = [m["id"] for m in res_pool.json()["data"]]
        assert "cerebras/llama-3.3-70b" in model_ids_pool
        assert "groq/llama-3.1-8b-instant" not in model_ids_pool
        assert "fast-tier" in model_ids_pool

        # 3. Key with SPECIFIC_WORKER pinned to Groq worker
        pinned_key = await create_gateway_key(
            worker_selection_mode="SPECIFIC_WORKER",
            specific_worker_id=uuid.UUID(w_groq["id"]),
        )
        res_pinned = await client.get("/v1/models", headers={"Authorization": f"Bearer {pinned_key}"})
        assert res_pinned.status_code == 200
        model_ids_pinned = [m["id"] for m in res_pinned.json()["data"]]
        assert "groq/llama-3.1-8b-instant" in model_ids_pinned
        assert "cerebras/llama-3.3-70b" not in model_ids_pinned


@pytest.mark.asyncio
async def test_virtual_group_priority_routing(admin_session_cookie):
    """Verify that calling virtual alias 'fast-tier' routes to the highest priority member."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        auto_key = await create_gateway_key(worker_selection_mode="AUTO")
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {auto_key}"},
            json={"model": "fast-tier", "messages": [{"role": "user", "content": "hello fast tier"}]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # cerebras/llama-3.3-70b is first in fast-tier.models, so it is selected over groq
        assert "response-from-cerebras" in data["choices"][0]["message"]["content"]

        # Verify recorded routing decision
        async with AsyncSessionLocal() as session:
            decisions = (await session.execute(select(RoutingDecision))).scalars().all()
            assert any("fast-tier" in (d.decision_reason or "") for d in decisions)


@pytest.mark.asyncio
async def test_worker_pool_whitelist_enforcement(admin_session_cookie):
    """Verify WORKER_POOL API key can ONLY call permitted models, returning 403 on unpermitted."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        # Scoped to only Cerebras
        pool_key = await create_gateway_key(
            name="cerebras-only",
            worker_selection_mode="WORKER_POOL",
            allowed_worker_ids=[w_cerebras["id"]],
        )

        # 1. Permitted model succeeds
        ok_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {pool_key}"},
            json={"model": "cerebras/llama-3.3-70b", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert ok_res.status_code == 200, ok_res.text
        assert "response-from-cerebras" in ok_res.json()["choices"][0]["message"]["content"]

        # 2. Unpermitted model returns 403 Forbidden
        forbidden_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {pool_key}"},
            json={"model": "groq/llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert forbidden_res.status_code == 403
        data = forbidden_res.json()
        err = data.get("error") or data.get("detail", {}).get("error", {})
        assert err.get("type") == "permission_denied"
        assert "not authorized to access model" in err.get("message", "")


@pytest.mark.asyncio
async def test_specific_worker_pinned_enforcement(admin_session_cookie):
    """Verify SPECIFIC_WORKER API key enforces strict single worker pinning and rejects other models."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        pinned_key = await create_gateway_key(
            name="groq-pinned",
            worker_selection_mode="SPECIFIC_WORKER",
            specific_worker_id=uuid.UUID(w_groq["id"]),
        )

        # 1. Explicitly requesting pinned model succeeds
        ok_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {pinned_key}"},
            json={"model": "groq/llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert ok_res.status_code == 200, ok_res.text
        assert "response-from-groq" in ok_res.json()["choices"][0]["message"]["content"]

        # 2. Requesting generic "auto" succeeds and resolves to pinned worker
        auto_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {pinned_key}"},
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert auto_res.status_code == 200, auto_res.text
        assert "response-from-groq" in auto_res.json()["choices"][0]["message"]["content"]

        # 3. Requesting different model returns 403 Forbidden
        diff_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {pinned_key}"},
            json={"model": "cerebras/llama-3.3-70b", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert diff_res.status_code == 403
        data = diff_res.json()
        err = data.get("error") or data.get("detail", {}).get("error", {})
        assert err.get("type") == "permission_denied"


@pytest.mark.asyncio
async def test_worker_pool_virtual_group_filtering(admin_session_cookie):
    """Verify WORKER_POOL key routes virtual group within its permitted subset or 403s if disallowed."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        # Key scoped only to Groq (which has groq/llama-3.1-8b-instant)
        groq_pool_key = await create_gateway_key(
            name="groq-only-pool",
            worker_selection_mode="WORKER_POOL",
            allowed_worker_ids=[w_groq["id"]],
        )

        # 1. Calling 'fast-tier': even though Cerebras is priority #1, it's not permitted for this key,
        # so WRAP routes to Groq (which is also in fast-tier and allowed)!
        fast_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_pool_key}"},
            json={"model": "fast-tier", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert fast_res.status_code == 200, fast_res.text
        assert "response-from-groq" in fast_res.json()["choices"][0]["message"]["content"]

        # 2. Calling 'reasoning-tier': neither of this key's allowed workers is in reasoning-tier,
        # so WRAP must reject with 403 Forbidden!
        reason_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_pool_key}"},
            json={"model": "reasoning-tier", "messages": [{"role": "user", "content": "think"}]},
        )
        assert reason_res.status_code == 403
        data = reason_res.json()
        err = data.get("error") or data.get("detail", {}).get("error", {})
        assert err.get("type") == "permission_denied"
        assert "not authorized for any models in virtual group 'reasoning-tier'" in err.get("message", "")


@pytest.mark.asyncio
async def test_configure_key_and_model_groups_scoping(clean_database: None, admin_session_cookie: str) -> None:
    from src.main import app
    registry.register(MockTierGroqAdapter())
    registry.register(MockTierCerebrasAdapter())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        w_cerebras, w_groq = await setup_two_workers(client, admin_session_cookie)

        # 1. Create a key initially with AUTO mode
        create_res = await client.post(
            "/api/apikeys",
            cookies=admin_session_cookie,
            json={
                "name": "initial-auto-key",
                "worker_selection_mode": "AUTO",
                "routing_policy": "balanced",
            },
        )
        assert create_res.status_code == 200, create_res.text
        key_data = create_res.json()
        raw_key = key_data["key"]
        key_id = key_data["id"]

        # 2. Configure / Update the key: change policy, change name, set MODEL_GROUPS mode with fast-tier
        patch_res = await client.patch(
            f"/api/apikeys/{key_id}",
            cookies=admin_session_cookie,
            json={
                "name": "configured-fast-tier-key",
                "routing_policy": "lowest_latency",
                "worker_selection_mode": "MODEL_GROUPS",
                "allowed_model_groups": ["fast-tier"],
                "rate_limit_rpm": 300,
            },
        )
        assert patch_res.status_code == 200, patch_res.text
        updated_key = patch_res.json()["key"]
        assert updated_key["name"] == "configured-fast-tier-key"
        assert updated_key["routing_policy"] == "lowest_latency"
        assert updated_key["worker_selection_mode"] == "MODEL_GROUPS"
        assert updated_key["allowed_model_groups"] == ["fast-tier"]
        assert updated_key["rate_limit_rpm"] == 300

        # 3. List keys and verify persistence
        list_res = await client.get("/api/apikeys", cookies=admin_session_cookie)
        assert list_res.status_code == 200
        found = next(k for k in list_res.json() if k["id"] == key_id)
        assert found["name"] == "configured-fast-tier-key"
        assert found["allowed_model_groups"] == ["fast-tier"]

        # 4. Calling 'fast-tier' with the configured key succeeds
        fast_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "fast-tier", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert fast_res.status_code == 200, fast_res.text

        # 5. Calling 'reasoning-tier' with the configured key is forbidden
        reason_res = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "reasoning-tier", "messages": [{"role": "user", "content": "think"}]},
        )
        assert reason_res.status_code == 403
