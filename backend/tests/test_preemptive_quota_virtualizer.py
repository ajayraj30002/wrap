import asyncio
import time
import pytest
from uuid import uuid4
from unittest.mock import MagicMock

from src.services.rate_limiter import (
    ProviderCredentialRateLimiter,
    ProviderQuotaProfile,
    upstream_quota_limiter,
)
from src.scheduler import Scheduler
from src.db.models import Provider, Worker


@pytest.mark.asyncio
async def test_provider_quota_profiles():
    limiter = ProviderCredentialRateLimiter(window_seconds=60.0)
    
    groq_prof = limiter.get_profile(provider_name="groq")
    assert groq_prof.rpm_limit in (20, 30)
    assert groq_prof.concurrency_limit == 2

    gemini_prof = limiter.get_profile(provider_name="gemini")
    assert gemini_prof.rpm_limit == 15
    assert gemini_prof.tpm_limit == 1000000

    cerebras_prof = limiter.get_profile(provider_name="cerebras")
    assert cerebras_prof.rpm_limit == 30

    custom_prof = ProviderQuotaProfile(rpm_limit=10, tpm_limit=5000, concurrency_limit=1)
    limiter.set_custom_limit("custom-key-1", custom_prof)
    assert limiter.get_profile(credential_id="custom-key-1").rpm_limit == 10


@pytest.mark.asyncio
async def test_preemptive_saturation_detection():
    limiter = ProviderCredentialRateLimiter(window_seconds=60.0)
    key_id = "test-groq-key-1"
    prof = ProviderQuotaProfile(rpm_limit=10, tpm_limit=5000, concurrency_limit=2)
    limiter.set_custom_limit(key_id, prof)

    # 1. Initially available
    assert limiter.is_available(key_id) is True
    util = limiter.get_utilization(key_id)
    assert util["rpm_used"] == 0
    assert util["is_saturated"] is False

    # 2. Consume 8 requests (80% of limit - still under 85%)
    for _ in range(8):
        await limiter.acquire_slot(key_id, max_wait_seconds=0.1)
        limiter.release_slot(key_id)

    util = limiter.get_utilization(key_id)
    assert util["rpm_used"] == 8
    assert util["rpm_percent"] == 0.8
    assert util["is_saturated"] is False

    # 3. Consume 9th request (90% >= 85% threshold -> PREEMPTIVELY SATURATED!)
    await limiter.acquire_slot(key_id, max_wait_seconds=0.1)
    limiter.release_slot(key_id)

    util = limiter.get_utilization(key_id)
    assert util["rpm_used"] == 9
    assert util["is_saturated"] is True
    assert limiter.is_available(key_id) is False


@pytest.mark.asyncio
async def test_micro_queuing_buffer():
    limiter = ProviderCredentialRateLimiter(window_seconds=0.2)  # fast 200ms window for test
    key_id = "test-micro-key"
    prof = ProviderQuotaProfile(rpm_limit=2, tpm_limit=1000, concurrency_limit=1)
    limiter.set_custom_limit(key_id, prof)

    # Acquire 2 slots (filling limit)
    await limiter.acquire_slot(key_id)
    limiter.release_slot(key_id)
    await limiter.acquire_slot(key_id)
    limiter.release_slot(key_id)

    assert limiter.get_utilization(key_id)["is_saturated"] is True

    # 3rd slot should wait in micro-queue until sliding window purges expired slots
    t0 = time.monotonic()
    wait_ms = await limiter.acquire_slot(key_id, max_wait_seconds=1.0)
    limiter.release_slot(key_id)
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.15  # Waited in micro-queue
    assert wait_ms >= 100.0


from src.db.session import AsyncSessionLocal, engine
from src.db.models import Base


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_scheduler_preemptive_credential_sharding():
    """Verify scheduler preempts saturated credential in favor of alternative healthy key."""
    upstream_quota_limiter.reset_all()

    async with AsyncSessionLocal() as async_session:
        # Create provider
        provider = Provider(name="groq", display_name="Groq", enabled=True)
        async_session.add(provider)
        await async_session.flush()

        cred_1_id = uuid4()
        cred_2_id = uuid4()

        w1 = Worker(
            provider_id=provider.id,
            credential_id=cred_1_id,
            model="groq/llama-3.3-70b-versatile",
            enabled=True,
            health_status="healthy",
        )
        w2 = Worker(
            provider_id=provider.id,
            credential_id=cred_2_id,
            model="groq/llama-3.3-70b-versatile",
            enabled=True,
            health_status="healthy",
        )
        async_session.add_all([w1, w2])
        await async_session.commit()

        # Saturate credential 1
        prof = ProviderQuotaProfile(rpm_limit=10, tpm_limit=5000, concurrency_limit=2)
        upstream_quota_limiter.set_custom_limit(str(cred_1_id), prof)
        for _ in range(9):
            await upstream_quota_limiter.acquire_slot(str(cred_1_id))
            upstream_quota_limiter.release_slot(str(cred_1_id))

        assert upstream_quota_limiter.is_available(str(cred_1_id)) is False

        # Credential 2 is fresh (0 used)
        upstream_quota_limiter.set_custom_limit(str(cred_2_id), prof)
        assert upstream_quota_limiter.is_available(str(cred_2_id)) is True

        scheduler = Scheduler()
        selected = await scheduler.select_worker(
            async_session,
            request_id="req-test-sharding",
            model="groq/llama-3.3-70b-versatile",
        )

        # Scheduler MUST preemptively pick w2 because w1's key is saturated!
        assert selected.id == w2.id
        assert selected.credential_id == cred_2_id

    upstream_quota_limiter.reset_all()

