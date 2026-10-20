"""Test suite for Production Features:
1. Kubernetes Liveness & Readiness Probes (/healthz, /ready)
2. Prometheus Exposition (/metrics)
3. Real-time Telemetry SSE Stream (/api/stream/telemetry)
4. Deterministic In-Memory Response Cache (fast-path, LRU, TTL, token savings)
5. Management Cache Operations (/api/cache/stats, /api/cache/clear)
6. Sliding-Window Rate Limiter (RFC-6585 headers & 429 limit threshold)
"""

import pytest
import time
from httpx import AsyncClient, ASGITransport
from fastapi import HTTPException

from src.main import app
from src.services.cache import ResponseCache, gateway_cache
from src.services.rate_limiter import SlidingWindowRateLimiter
from src.db.models import Base
from src.db.session import engine


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_kubernetes_liveness_probe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        assert "uptime_seconds" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_kubernetes_readiness_probe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "database" in data
        assert "router_initialized" in data


@pytest.mark.asyncio
async def test_prometheus_metrics_exposition():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        text = resp.text
        assert "wrap_cache_hits_total" in text
        assert "wrap_cache_misses_total" in text
        assert "wrap_cache_entries" in text
        assert "wrap_requests_total" in text


@pytest.mark.asyncio
async def test_response_cache_unit():
    cache = ResponseCache(max_entries=3, default_ttl_seconds=10)
    req1 = {"model": "test-model", "messages": [{"role": "user", "content": "hello"}]}
    resp1 = {
        "id": "chatcmpl-1",
        "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }

    # 1. Miss initially
    assert cache.get(req1) is None

    # 2. Set and retrieve
    cache.set(req1, resp1)
    hit_res = cache.get(req1)
    assert hit_res is not None
    cached_obj, hits = hit_res
    assert hits == 1
    assert cached_obj["choices"][0]["message"]["content"] == "hi"

    # 3. Hit rate stats
    stats = cache.stats()
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1
    assert stats["hit_rate_pct"] == 50.0
    assert stats["total_tokens_saved"] == 10

    # 4. Eviction when capacity exceeded
    for i in range(5):
        cache.set({"model": "test", "messages": [{"role": "user", "content": f"msg {i}"}]}, resp1)
    assert cache.stats()["entries_count"] <= 3

    # 5. Clear
    cache.clear()
    assert cache.stats()["entries_count"] == 0


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window():
    limiter = SlidingWindowRateLimiter(default_rpm=2, window_seconds=60.0)
    key = "test_key_limit_unit"

    # First 2 requests within limit
    limit1, rem1, _ = limiter.check_and_consume(key, limit_rpm=2)
    assert rem1 == 1

    limit2, rem2, _ = limiter.check_and_consume(key, limit_rpm=2)
    assert rem2 == 0

    # Third request must raise 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_and_consume(key, limit_rpm=2)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers.get("X-RateLimit-Remaining") == "0"
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_management_cache_endpoints():
    from src.db.session import AsyncSessionLocal
    from src.db.models import AdminSession
    from src.core.security import generate_random_token, hash_token, utcnow
    from datetime import timedelta

    # Create admin auth session for management router
    token = generate_random_token(32)
    async with AsyncSessionLocal() as session:
        session.add(AdminSession(session_token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"session_id": token}) as client:
        # Cache stats
        resp_stats = await client.get("/api/cache/stats")
        assert resp_stats.status_code == 200
        stats = resp_stats.json()
        assert "entries_count" in stats
        assert "hit_rate_pct" in stats

        # Cache clear
        resp_clear = await client.post("/api/cache/clear")
        assert resp_clear.status_code == 200
        data_clear = resp_clear.json()
        assert data_clear.get("status") == "cleared"

        # System diagnostics
        resp_diag = await client.get("/api/system/diagnostics")
        assert resp_diag.status_code == 200
        diag = resp_diag.json()
        assert diag.get("status") == "operational"
        assert "database" in diag
        assert "probes" in diag
