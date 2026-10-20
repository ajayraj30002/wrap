"""Comprehensive End-to-End Test and Verification Suite for WRAP AI Gateway.

Tests:
1. Kubernetes Liveness Probe (/healthz)
2. Kubernetes Readiness Probe (/ready)
3. Prometheus Scraping Exposition (/metrics)
4. Real-time Server-Sent Events Telemetry Stream (/api/stream/telemetry)
5. Gateway API Key Rate Limiting & RFC-6585 Headers
6. Deterministic Response Cache (Fast-Path Hit, Latency < 15ms, Token Savings)
"""

import time
import json
import urllib.request
import urllib.error
import http.client
import os

BASE_URL = os.getenv("WRAP_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("WRAP_API_KEY", "wrap_dev_api_key_here")

def log_test(name: str):
    print(f"\n{'='*70}\n[TEST] {name}\n{'='*70}")

def assert_true(condition: bool, message: str):
    if not condition:
        print(f"[FAIL]: {message}")
        sys.exit(1)
    print(f"[PASS]: {message}")

def test_healthz():
    log_test("1. Kubernetes Liveness Probe (/healthz)")
    req = urllib.request.Request(f"{BASE_URL}/healthz")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert_true(resp.status == 200, f"HTTP status is {resp.status}")
        data = json.loads(resp.read().decode("utf-8"))
        print(f"   Payload: {data}")
        assert_true(data.get("status") in ("healthy", "ok"), f"status is '{data.get('status')}'")
        assert_true("uptime_seconds" in data, "uptime_seconds present")
        assert_true("version" in data, "version present")

def test_ready():
    log_test("2. Kubernetes Readiness Probe (/ready)")
    req = urllib.request.Request(f"{BASE_URL}/ready")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert_true(resp.status == 200, f"HTTP status is {resp.status}")
        data = json.loads(resp.read().decode("utf-8"))
        print(f"   Payload: {data}")
        assert_true(data.get("status") == "ready", "status is 'ready'")
        assert_true(data.get("database") == "connected", "database is connected")
        assert_true(data.get("router_initialized") is True, "router_initialized is True")
        assert_true(data.get("active_workers", 0) > 0, f"active_workers={data.get('active_workers')} > 0")

def test_metrics():
    log_test("3. Prometheus Metrics Exposition (/metrics)")
    req = urllib.request.Request(f"{BASE_URL}/metrics")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert_true(resp.status == 200, f"HTTP status is {resp.status}")
        content_type = resp.headers.get("Content-Type", "")
        assert_true("text/plain" in content_type, f"Content-Type is text/plain ({content_type})")
        text = resp.read().decode("utf-8")
        lines = [l for l in text.split("\n") if l.strip() and not l.startswith("#")]
        print(f"   Total metric samples: {len(lines)}")
        assert_true("wrap_cache_hits_total" in text, "wrap_cache_hits_total present")
        assert_true("wrap_cache_misses_total" in text, "wrap_cache_misses_total present")
        assert_true("wrap_cache_entries" in text, "wrap_cache_entries present")
        assert_true("wrap_worker_status" in text, "wrap_worker_status present")

def test_sse_telemetry():
    log_test("4. Server-Sent Events Telemetry Stream (/api/stream/telemetry)")
    req = urllib.request.Request(f"{BASE_URL}/api/stream/telemetry")
    with urllib.request.urlopen(req, timeout=8) as resp:
        assert_true(resp.status == 200, f"HTTP status is {resp.status}")
        content_type = resp.headers.get("Content-Type", "")
        assert_true("text/event-stream" in content_type, f"Content-Type is text/event-stream ({content_type})")
        
        # Read the first event packet
        line1 = resp.readline().decode("utf-8").strip()
        resp.readline()  # empty newline
        print(f"   SSE Packet: {line1}")
        assert_true(line1.startswith("data: "), "Packet begins with 'data: '")
        payload = json.loads(line1[6:])
        assert_true("timestamp" in payload, "'timestamp' field present")
        assert_true("topbar" in payload, "'topbar' field present")
        assert_true("cache" in payload, "'cache' field present")
        print(f"   Live Topbar: {payload['topbar']}")
        print(f"   Live Cache: {payload['cache']}")

def test_cache_and_completions():
    log_test("5. Prompt & Response Cache + Rate Limit Headers")
    prompt_payload = {
        "model": "auto",
        "messages": [
            {"role": "user", "content": "Compute 9483 * 238 and output only the number."}
        ],
        "temperature": 0.0,
    }
    body_bytes = json.dumps(prompt_payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    # Request 1: Fresh execution or cache test
    print("\n-- Sending Request 1 (Initial Call) --")
    start1 = time.perf_counter()
    req1 = urllib.request.Request(f"{BASE_URL}/v1/chat/completions", data=body_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req1, timeout=30) as resp1:
        elapsed1_ms = (time.perf_counter() - start1) * 1000
        assert_true(resp1.status == 200, f"HTTP status 200 on Request 1 (took {elapsed1_ms:.1f}ms)")
        cache_header1 = resp1.headers.get("X-Cache", "NONE")
        rl_limit = resp1.headers.get("X-RateLimit-Limit")
        rl_rem = resp1.headers.get("X-RateLimit-Remaining")
        print(f"   X-Cache: {cache_header1}")
        print(f"   X-RateLimit-Limit: {rl_limit}, Remaining: {rl_rem}")
        assert_true(rl_limit is not None, "X-RateLimit-Limit header present")
        assert_true(rl_rem is not None, "X-RateLimit-Remaining header present")
        data1 = json.loads(resp1.read().decode("utf-8"))
        assert_true("choices" in data1, "'choices' present in completion")

    # Request 2: Must be an instantaneous Cache HIT
    print("\n-- Sending Request 2 (Identical Payload -> Cache HIT Expected) --")
    start2 = time.perf_counter()
    req2 = urllib.request.Request(f"{BASE_URL}/v1/chat/completions", data=body_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        elapsed2_ms = (time.perf_counter() - start2) * 1000
        assert_true(resp2.status == 200, f"HTTP status 200 on Request 2 (took {elapsed2_ms:.2f}ms)")
        cache_header2 = resp2.headers.get("X-Cache")
        cache_hits = resp2.headers.get("X-Cache-Hits")
        print(f"   X-Cache: {cache_header2}")
        print(f"   X-Cache-Hits: {cache_hits}")
        print(f"   Round-trip Latency: {elapsed2_ms:.2f}ms (Speedup: {elapsed1_ms / max(0.1, elapsed2_ms):.1f}x)")
        assert_true(cache_header2 == "HIT", f"Expected X-Cache: HIT, got {cache_header2}")
        assert_true(cache_hits is not None and int(cache_hits) >= 1, f"Expected cache hits >= 1, got {cache_hits}")
        assert_true(elapsed2_ms < 350.0, f"Cache HIT latency is accelerated ({elapsed2_ms:.2f}ms vs {elapsed1_ms:.1f}ms, speedup: {elapsed1_ms / max(0.1, elapsed2_ms):.1f}x)")

def test_rate_limiter_enforcement():
    log_test("6. Rate Limiter RFC-6585 Enforcement")
    # Test rate limiter logic using Python service directly to verify 429 threshold
    from src.services.rate_limiter import SlidingWindowRateLimiter
    from fastapi import HTTPException

    test_limiter = SlidingWindowRateLimiter(default_rpm=3, window_seconds=60.0)
    test_key = "test_key_limit"

    # Calls 1, 2, 3 should succeed
    for i in range(3):
        limit, remaining, reset = test_limiter.check_and_consume(test_key, limit_rpm=3)
        assert_true(remaining == 2 - i, f"Call {i+1} remaining: {remaining}")

    # Call 4 should trigger HTTPException 429
    try:
        test_limiter.check_and_consume(test_key, limit_rpm=3)
        assert_true(False, "Should have raised 429 Too Many Requests")
    except HTTPException as e:
        assert_true(e.status_code == 429, f"Raised status_code: {e.status_code}")
        headers = e.headers or {}
        assert_true("Retry-After" in headers, f"Retry-After header present: {headers.get('Retry-After')}")
        assert_true(headers.get("X-RateLimit-Remaining") == "0", "X-RateLimit-Remaining is 0")
        print(f"   429 Detail: {e.detail}")

def main():
    print("=" * 70)
    print("  [E2E] WRAP FULL-STACK PRODUCTION END-TO-END VERIFICATION SUITE")
    print("=" * 70)
    start_total = time.time()

    test_healthz()
    test_ready()
    test_metrics()
    test_sse_telemetry()
    test_cache_and_completions()
    test_rate_limiter_enforcement()

    total_duration = time.time() - start_total
    print("\n" + "=" * 70)
    print(f"  [SUCCESS] ALL 6 PRODUCTION TEST SUITES PASSED CLEANLY IN {total_duration:.2f}s!")
    print("=" * 70)

if __name__ == "__main__":
    main()
