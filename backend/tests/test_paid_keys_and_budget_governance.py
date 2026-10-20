import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from src.core.security import encrypt_secret, get_password_hash, hash_token
from src.db.models import (
    AdminSession,
    AdminUser,
    Base,
    Credential,
    GatewayApiKey,
    Provider,
    RequestMetric,
    Worker,
)
from src.db.session import AsyncSessionLocal, engine
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderModel as AdapterProviderModel, ProviderStreamEvent
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers
from src.services.budget import BudgetService, spend_velocity_tracker
from src.services.cache import gateway_cache
from src.services.pricing import calculate_request_economics, is_worker_or_credential_paid


class MockGroqFreeAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="groq/llama-3.1-8b-instant", display_name="Llama 3.1 8B Instant", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 1000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "free-tier-response"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "free"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


class MockOpenAIPaidAdapter:
    name = "openai"
    display_name = "OpenAI"
    default_models = ()
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True)

    async def list_models(self, *, api_key: str, timeout: float):
        return [
            AdapterProviderModel(external_model_id="gpt-4o", display_name="GPT-4o", streaming=True),
        ]

    def normalize_request(self, request, model):
        return {"model": model, "messages": request["messages"]}

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": f"chatcmpl_{model}",
                "object": "chat.completion",
                "created": 1000,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "paid-tier-response"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
            },
            usage={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "paid"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
def setup_mock_adapters(monkeypatch):
    registry.register(MockGroqFreeAdapter())
    registry.register(MockOpenAIPaidAdapter())
    gateway_cache.clear()


@pytest.fixture
async def clean_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def admin_session_cookie(clean_database):
    from datetime import timedelta
    from src.core.security import generate_random_token, utcnow

    async with AsyncSessionLocal() as session:
        session.add(AdminUser(password_hash=get_password_hash("testpassword")))
        token = generate_random_token(64)
        session.add(AdminSession(session_token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
        await session.commit()
    return {"session_id": token}


@pytest.mark.asyncio
async def test_unit_pricing_economics_free_vs_paid():
    # 1. Free tier calculation: actual cost $0, full commercial value saved
    free_econ = calculate_request_economics(
        input_tokens=1000, output_tokens=500, total_tokens=1500,
        provider="groq", model="llama-3.1-8b-instant", is_paid=False,
    )
    assert free_econ["actual_cost_usd"] == 0.0
    assert free_econ["saved_usd"] > 0.0
    assert free_econ["is_free_tier"] is True

    # 2. Paid tier calculation: actual cost billed, saved is 0
    paid_econ = calculate_request_economics(
        input_tokens=1000, output_tokens=500, total_tokens=1500,
        provider="openai", model="gpt-4o", is_paid=True,
    )
    assert paid_econ["actual_cost_usd"] > 0.0
    assert paid_econ["is_free_tier"] is False
    assert paid_econ["is_paid"] is True

    # 3. Cache hit calculation: $0.00 actual cost, full request value saved
    cache_econ = calculate_request_economics(
        input_tokens=1000, output_tokens=500, total_tokens=1500,
        provider="openai", model="gpt-4o", is_cache_hit=True,
    )
    assert cache_econ["actual_cost_usd"] == 0.0
    assert cache_econ["saved_usd"] > 0.0
    assert cache_econ["is_cache_hit"] is True


@pytest.mark.asyncio
async def test_budget_governance_hard_cap_rejection(clean_database):
    from src.main import app

    # Setup Gateway API key with hard cap exhausted
    raw_key = "wrap_hard_cap_test_secret_123456789"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        key_obj = GatewayApiKey(
            name="budget_exhausted_key",
            prefix="wrap_har",
            key_hash=hash_token(raw_key),
            max_budget_usd=5.00,
            spend_usd=5.00,  # Cap reached!
            budget_exceeded_action="hard_cap",
        )
        session.add(key_obj)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request should immediately fail pre-flight with HTTP 429
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "budget_cap_exceeded"
        assert "Hard budget cap exceeded" in data["error"]["message"]


@pytest.mark.asyncio
async def test_budget_spend_velocity_circuit_breaker(clean_database):
    from src.main import app

    raw_key = "wrap_velocity_circuit_breaker_test_key"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        key_obj = GatewayApiKey(
            name="velocity_key",
            prefix="wrap_vel",
            key_hash=hash_token(raw_key),
            max_budget_usd=100.00,
            spend_usd=0.00,
            spend_velocity_limit_usd=2.00,
            spend_velocity_window_sec=60,
        )
        session.add(key_obj)
        await session.commit()
        key_id = str(key_obj.id)

    # Simulate rapid spend in rolling window
    spend_velocity_tracker.record_spend(key_id, cost_usd=2.50)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"]["code"] == "spend_velocity_exceeded"
        assert "Circuit breaker tripped" in data["error"]["message"]


@pytest.mark.asyncio
async def test_budget_governance_fallback_to_free_tier(clean_database):
    from src.main import app

    raw_key = "wrap_fallback_to_free_test_key"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        # Create a free worker
        prov_res = await session.execute(select(Provider).where(Provider.name == "groq"))
        groq_prov = prov_res.scalar_one()

        cred = Credential(
            provider_id=groq_prov.id,
            name="groq_free_cred",
            encrypted_secret=encrypt_secret("gsk_mock_secret"),
            masked_identifier="gsk_1234",
            credential_metadata={"is_paid": False},
        )
        session.add(cred)
        await session.flush()

        w_free = Worker(
            provider_id=groq_prov.id,
            credential_id=cred.id,
            model="llama-3.1-8b-instant",
            enabled=True,
            health_status="healthy",
        )
        session.add(w_free)

        # Create key with budget cap reached but fallback_to_free enabled
        key_obj = GatewayApiKey(
            name="fallback_key",
            prefix="wrap_fal",
            key_hash=hash_token(raw_key),
            max_budget_usd=10.00,
            spend_usd=10.00,  # Cap reached
            budget_exceeded_action="fallback_to_free",
        )
        session.add(key_obj)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hello free"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        # Should succeed by falling back to free tier!
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "free-tier-response"


@pytest.mark.asyncio
async def test_cache_hit_zero_cost_and_value_saved(clean_database):
    from src.main import app

    raw_key = "wrap_cache_value_saved_test_key"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        prov_res = await session.execute(select(Provider).where(Provider.name == "groq"))
        groq_prov = prov_res.scalar_one()
        cred = Credential(
            provider_id=groq_prov.id,
            name="groq_cred",
            encrypted_secret=encrypt_secret("gsk_mock_secret"),
            masked_identifier="gsk_1234",
        )
        session.add(cred)
        await session.flush()
        w = Worker(
            provider_id=groq_prov.id,
            credential_id=cred.id,
            model="llama-3.1-8b-instant",
            enabled=True,
            health_status="healthy",
        )
        session.add(w)

        key_obj = GatewayApiKey(
            name="cache_test_key",
            prefix="wrap_cac",
            key_hash=hash_token(raw_key),
            max_budget_usd=100.00,
            spend_usd=0.00,
            value_saved_usd=0.00,
        )
        session.add(key_obj)
        await session.commit()
        key_id = key_obj.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request 1: Cache Miss
        r1 = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "cache me"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert r1.status_code == 200
        assert r1.headers.get("X-Cache") == "MISS"

        # Request 2: Cache Hit!
        r2 = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "cache me"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT"
        assert r2.headers.get("X-Cost-USD") == "0.000000"
        val_saved_header = float(r2.headers.get("X-Value-Saved-USD", 0.0))
        assert val_saved_header > 0.0

    # Verify key value_saved_usd was incremented
    async with AsyncSessionLocal() as session:
        k = await session.get(GatewayApiKey, key_id)
        assert k.value_saved_usd > 0.0
        assert k.spend_usd == 0.0


@pytest.mark.asyncio
async def test_paid_key_actual_money_tracking(clean_database):
    from src.main import app

    raw_key = "wrap_paid_key_tracking_secret"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        prov_res = await session.execute(select(Provider).where(Provider.name == "openai"))
        openai_prov = prov_res.scalar_one()
        cred = Credential(
            provider_id=openai_prov.id,
            name="openai_paid_cred",
            encrypted_secret=encrypt_secret("sk-test-paid-key"),
            masked_identifier="sk-paid-1234",
            credential_metadata={"is_paid": True},
        )
        session.add(cred)
        await session.flush()
        w = Worker(
            provider_id=openai_prov.id,
            credential_id=cred.id,
            model="gpt-4o",
            enabled=True,
            health_status="healthy",
        )
        session.add(w)

        key_obj = GatewayApiKey(
            name="paid_test_key",
            prefix="wrap_pai",
            key_hash=hash_token(raw_key),
            max_budget_usd=50.00,
            spend_usd=0.00,
            value_saved_usd=0.00,
        )
        session.add(key_obj)
        await session.commit()
        key_id = key_obj.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "paid prompt"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert r.status_code == 200
        cost_hdr = float(r.headers.get("X-Cost-USD", 0.0))
        assert cost_hdr > 0.0

    # Check database tracking
    async with AsyncSessionLocal() as session:
        k = await session.get(GatewayApiKey, key_id)
        assert k.spend_usd > 0.0


@pytest.mark.asyncio
async def test_reset_key_spend_endpoint(admin_session_cookie):
    from src.main import app

    async with AsyncSessionLocal() as session:
        key_obj = GatewayApiKey(
            name="reset_key_test",
            prefix="wrap_rst",
            key_hash=hash_token("wrap_reset_secret"),
            max_budget_usd=20.00,
            spend_usd=18.50,
        )
        session.add(key_obj)
        await session.commit()
        key_id = str(key_obj.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies=admin_session_cookie) as client:
        resp = await client.post(f"/api/apikeys/{key_id}/reset-spend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["spend_usd"] == 0.0

    # Verify in DB
    async with AsyncSessionLocal() as session:
        stmt = select(GatewayApiKey).where(GatewayApiKey.id == uuid.UUID(key_id))
        res = await session.execute(stmt)
        updated_key = res.scalar_one()
        assert updated_key.spend_usd == 0.0


@pytest.mark.asyncio
async def test_budget_fallback_to_free_when_no_free_workers_available(clean_database):
    """When budget is exceeded and fallback_to_free is set, but no free workers exist, should 429."""
    from src.main import app

    raw_key = "wrap_fallback_no_free_worker_key"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        # Create ONLY paid worker
        prov_res = await session.execute(select(Provider).where(Provider.name == "openai"))
        openai_prov = prov_res.scalar_one()

        cred = Credential(
            provider_id=openai_prov.id,
            name="openai_paid_cred",
            encrypted_secret=encrypt_secret("sk-mock-paid"),
            masked_identifier="sk-...paid",
            credential_metadata={"is_paid": True},
        )
        session.add(cred)
        await session.flush()

        w_paid = Worker(
            provider_id=openai_prov.id,
            credential_id=cred.id,
            model="gpt-4o",
            enabled=True,
        )
        session.add(w_paid)

        # Key with max_budget $5, spend $5, fallback_to_free
        key_obj = GatewayApiKey(
            name="fallback_no_free_key",
            prefix="wrap_fbnf",
            key_hash=hash_token(raw_key),
            max_budget_usd=5.00,
            spend_usd=5.00,
            budget_exceeded_action="fallback_to_free",
        )
        session.add(key_obj)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert "no free tier workers are currently online" in data["error"]["message"]


@pytest.mark.asyncio
async def test_zero_budget_hard_cap(clean_database):
    """A key created with 0.00 max budget should be immediately blocked."""
    from src.main import app

    raw_key = "wrap_zero_budget_key"
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
        key_obj = GatewayApiKey(
            name="zero_budget_key",
            prefix="wrap_zero",
            key_hash=hash_token(raw_key),
            max_budget_usd=0.00,
            spend_usd=0.00,
            budget_exceeded_action="block",
        )
        session.add(key_obj)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "budget_cap_exceeded"

