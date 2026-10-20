import asyncio
import json
import uuid
from typing import AsyncIterator
import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.core.security import hash_token, generate_random_token, encrypt_secret
from src.db.session import AsyncSessionLocal, engine
from src.db.models import Base, Provider, Worker, Credential, GatewayApiKey
from src.providers.base import (
    ProviderCapabilities,
    ProviderCompletion,
    ProviderModel as AdapterProviderModel,
    ProviderStreamEvent,
)
from src.providers.registry import registry
from src.services.rate_limiter import upstream_quota_limiter


class MockSlowWorkerAdapter:
    """Simulates a slow worker with 800ms cold-start / queue delay."""
    name = "slow-provider"
    display_name = "Slow Provider"
    capabilities = ProviderCapabilities(streaming=True)
    default_models = []

    async def list_models(self, *, api_key: str, timeout: float):
        return []

    def normalize_request(self, request, model):
        return request

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        await asyncio.sleep(0.4)
        return ProviderCompletion(
            response={
                "id": "slow_resp",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "slow response"}, "finish_reason": "stop"}],
            },
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        # Delay 600ms before first token
        await asyncio.sleep(0.6)
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "from-slow"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


class MockFastWorkerAdapter:
    """Simulates an ultra-fast LPU worker."""
    name = "fast-provider"
    display_name = "Fast LPU Provider"
    capabilities = ProviderCapabilities(streaming=True)
    default_models = []

    async def list_models(self, *, api_key: str, timeout: float):
        return []

    def normalize_request(self, request, model):
        return request

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        return ProviderCompletion(
            response={
                "id": "fast_resp",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "fast response"}, "finish_reason": "stop"}],
            },
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        # Responds in 20ms
        await asyncio.sleep(0.02)
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "from-fast-lpu"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


class MockVerifierAdapter:
    """Simulates Gemini 2.0 Flash reasoning verifier."""
    name = "verifier-provider"
    display_name = "Verifier Provider"
    capabilities = ProviderCapabilities(streaming=True)
    default_models = []

    async def list_models(self, *, api_key: str, timeout: float):
        return []

    def normalize_request(self, request, model):
        return request

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        # Inspect messages for prompt
        messages = request.get("messages", [])
        last_text = messages[-1].get("content", "") if messages else ""
        if "deliberate_bug" in last_text:
            content = "STATUS: REVISED\nfunction perfectedSolution() { return 42; }"
        else:
            content = "STATUS: VERIFIED"
        return ProviderCompletion(
            response={
                "id": "ver_resp",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            },
            usage={"input_tokens": 15, "output_tokens": 8, "total_tokens": 23},
        )

    async def stream_completion(self, request, *, api_key, model, request_id, timeout) -> AsyncIterator[ProviderStreamEvent]:
        yield ProviderStreamEvent(payload={"choices": [{"delta": {"content": "verified"}}]})
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def setup_test_environment():
    registry.register(MockSlowWorkerAdapter())
    registry.register(MockFastWorkerAdapter())
    registry.register(MockVerifierAdapter())
    upstream_quota_limiter.reset_all()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    registry.unregister("slow-provider")
    registry.unregister("fast-provider")
    registry.unregister("verifier-provider")
    upstream_quota_limiter.reset_all()


async def create_api_key() -> str:
    raw = f"wrap_{generate_random_token(32)}"
    async with AsyncSessionLocal() as session:
        session.add(
            GatewayApiKey(
                name="test-key",
                prefix=raw[:8],
                key_hash=hash_token(raw),
            )
        )
        await session.commit()
    return raw


async def create_worker_with_cred(session, provider: Provider, model_name: str) -> Worker:
    cred = Credential(
        provider_id=provider.id,
        name=f"{provider.name}_{model_name}_cred",
        encrypted_secret=encrypt_secret("mock_secret_key"),
        masked_identifier="mock_1234",
    )
    session.add(cred)
    await session.flush()
    worker = Worker(
        provider_id=provider.id,
        credential_id=cred.id,
        model=model_name,
        enabled=True,
        health_status="healthy",
    )
    session.add(worker)
    await session.flush()
    return worker


@pytest.mark.asyncio
async def test_speculative_hedged_streaming_erases_tail_latency():
    """Verify when primary worker is slow, hedge worker wins the race and streams first."""
    api_key = await create_api_key()

    async with AsyncSessionLocal() as session:
        p_slow = Provider(name="slow-provider", display_name="Slow Provider", enabled=True)
        p_fast = Provider(name="fast-provider", display_name="Fast Provider", enabled=True)
        session.add_all([p_slow, p_fast])
        await session.flush()

        await create_worker_with_cred(session, p_slow, "llama-3.3-70b")
        await create_worker_with_cred(session, p_fast, "llama-3.3-70b")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request with 100ms speculative hedge deadline
        # Primary worker takes 600ms; Fast worker takes 20ms
        resp = await client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Speculative-Hedge-Ms": "100",
            },
            json={
                "model": "llama-3.3-70b",
                "stream": True,
                "messages": [{"role": "user", "content": "hello world"}],
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Wrap-Speculative-Hedge") == "active"
        
        # Read the streamed response
        body_text = resp.text
        assert "data: [DONE]" in body_text
        # The fast hedge worker should have won the race!
        assert "from-fast-lpu" in body_text


@pytest.mark.asyncio
async def test_dynamic_token_mass_bouncer():
    """Verify heavy prompts (>2000 tokens) route to Gemini Flash while light prompts route to Groq."""
    from src.scheduler import Scheduler

    async with AsyncSessionLocal() as session:
        p_groq = Provider(name="groq", display_name="Groq LPU", enabled=True)
        p_gemini = Provider(name="gemini", display_name="Google Gemini", enabled=True)
        session.add_all([p_groq, p_gemini])
        await session.flush()

        w_groq = await create_worker_with_cred(session, p_groq, "groq/llama-3.3-70b-versatile")
        w_gemini = await create_worker_with_cred(session, p_gemini, "gemini-2.0-flash")
        await session.commit()

        scheduler = Scheduler()

        # 1. Light prompt (50 tokens) -> Should route to fast-tier LPU (groq)
        selected_light = await scheduler.select_worker(
            session,
            request_id="req-light",
            model="fast-tier",
            estimated_tokens=50,
        )
        assert selected_light.id == w_groq.id

        # 2. Heavy prompt (3,500 tokens) -> Must divert to high-TPM Gemini Flash to protect Groq TPM!
        selected_heavy = await scheduler.select_worker(
            session,
            request_id="req-heavy",
            model="fast-tier",
            estimated_tokens=3500,
        )
        assert selected_heavy.id == w_gemini.id


@pytest.mark.asyncio
async def test_dual_model_ensemble_consensus_verified():
    """Verify Ensemble Consensus returns primary output with VERIFIED status when sound."""
    api_key = await create_api_key()

    async with AsyncSessionLocal() as session:
        p_groq = Provider(name="fast-provider", display_name="Groq LPU", enabled=True)
        p_ver = Provider(name="verifier-provider", display_name="Gemini Verifier", enabled=True)
        session.add_all([p_groq, p_ver])
        await session.flush()

        await create_worker_with_cred(session, p_groq, "groq/llama-3.3-70b-versatile")
        await create_worker_with_cred(session, p_ver, "gemini-2.0-flash")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request using virtual group "ensemble-consensus"
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "ensemble-consensus",
                "messages": [{"role": "user", "content": "Write clean python fibonacci"}],
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Wrap-Consensus") == "VERIFIED"
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["content"] == "fast response"


@pytest.mark.asyncio
async def test_dual_model_ensemble_consensus_revised():
    """Verify Ensemble Consensus substitutes perfected output with REVISED status when flaws found."""
    api_key = await create_api_key()

    async with AsyncSessionLocal() as session:
        p_groq = Provider(name="fast-provider", display_name="Groq LPU", enabled=True)
        p_ver = Provider(name="verifier-provider", display_name="Gemini Verifier", enabled=True)
        session.add_all([p_groq, p_ver])
        await session.flush()

        await create_worker_with_cred(session, p_groq, "groq/llama-3.3-70b-versatile")
        await create_worker_with_cred(session, p_ver, "gemini-2.0-flash")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User prompt contains "deliberate_bug" which triggers MockVerifier to revise!
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "ensemble-consensus",
                "messages": [{"role": "user", "content": "deliberate_bug in memory allocation"}],
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Wrap-Consensus") == "REVISED"
        data = resp.json()
        assert "function perfectedSolution() { return 42; }" in data["choices"][0]["message"]["content"]
