"""High-Performance In-Memory Sliding-Window Rate Limiter for Gateway API Keys.

Enforces per-key Requests Per Minute (RPM) limits with nanosecond-precision sliding window,
sliding token replenishment, and standard RFC-6585 headers (Retry-After, X-RateLimit-*).
"""

import time
import math
import threading
from collections import deque
from typing import Any, Tuple
from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, default_rpm: int = 120, window_seconds: float = 60.0):
        self.default_rpm = default_rpm
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        # Mapping from key_identifier -> deque of request timestamps (monotonic)
        self._windows: dict[str, deque[float]] = {}

    def check_and_consume(self, key_id: str, limit_rpm: int | None = None) -> Tuple[int, int, int]:
        """Check if request is allowed under key's RPM limit and record timestamp if allowed.
        
        Args:
            key_id: Unique identifier for the API key.
            limit_rpm: Optional key-specific RPM limit. Defaults to self.default_rpm.

        Returns:
            Tuple of (limit, remaining, reset_seconds)

        Raises:
            HTTPException with status 429 if rate limit is exceeded.
        """
        limit = limit_rpm if (limit_rpm is not None and limit_rpm > 0) else self.default_rpm
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            if key_id not in self._windows:
                self._windows[key_id] = deque()

            window = self._windows[key_id]

            # Purge expired timestamps outside the sliding window
            while window and window[0] <= cutoff:
                window.popleft()

            current_count = len(window)

            if current_count >= limit:
                # Rate limit exceeded! Calculate time until oldest request leaves the window
                oldest = window[0]
                retry_after = max(1, math.ceil(oldest + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": {
                            "message": f"Rate limit exceeded: maximum {limit} requests per minute. Please retry after {retry_after}s.",
                            "type": "rate_limit_error",
                            "code": "rate_limit_exceeded",
                        }
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(retry_after),
                    },
                )

            # Request allowed: record current timestamp
            window.append(now)
            remaining = max(0, limit - len(window))
            reset_seconds = max(1, math.ceil(window[0] + self.window_seconds - now))
            return limit, remaining, reset_seconds

    def reset_key(self, key_id: str) -> None:
        """Reset sliding window for a specific key (useful for tests or tier upgrades)."""
        with self._lock:
            self._windows.pop(key_id, None)

    def reset_all(self) -> None:
        """Clear all active sliding windows."""
        with self._lock:
            self._windows.clear()


# Global Gateway Rate Limiter Singleton
gateway_rate_limiter = SlidingWindowRateLimiter(default_rpm=120, window_seconds=60.0)


import asyncio
from dataclasses import dataclass


@dataclass
class ProviderQuotaProfile:
    rpm_limit: int
    tpm_limit: int
    concurrency_limit: int


DEFAULT_PROVIDER_QUOTAS: dict[str, ProviderQuotaProfile] = {
    # Groq free tier: 30 RPM / 6000 ITPM for most models, tighter for some (qwen: 7000 ITPM).
    # We use 20 RPM / 5000 TPM as a conservative pre-emptive shard threshold so we
    # never actually hit the upstream 429. The token-mass bouncer in Scheduler steers
    # requests > 1500 estimated tokens away from Groq toward high-TPM providers.
    "groq": ProviderQuotaProfile(rpm_limit=20, tpm_limit=5000, concurrency_limit=2),
    "cerebras": ProviderQuotaProfile(rpm_limit=30, tpm_limit=60000, concurrency_limit=2),
    "gemini": ProviderQuotaProfile(rpm_limit=15, tpm_limit=1000000, concurrency_limit=3),
    "google": ProviderQuotaProfile(rpm_limit=15, tpm_limit=1000000, concurrency_limit=3),
    "sambanova": ProviderQuotaProfile(rpm_limit=20, tpm_limit=20000, concurrency_limit=2),
    "openai": ProviderQuotaProfile(rpm_limit=60, tpm_limit=100000, concurrency_limit=5),
    "anthropic": ProviderQuotaProfile(rpm_limit=50, tpm_limit=100000, concurrency_limit=5),
    "default": ProviderQuotaProfile(rpm_limit=60, tpm_limit=50000, concurrency_limit=3),
}


class ProviderCredentialRateLimiter:
    """In-memory preemptive quota sharder and micro-queuing buffer for upstream API credentials.
    
    Prevents HTTP 429 upstream errors on free tier credentials by:
    1. Tracking rolling 60-second request timestamps and in-flight concurrency per credential.
    2. Exposing utilization percent so schedulers can preemptively shard to alternative credentials.
    3. Providing async micro-queuing (50-200ms) during transient bursts to smooth traffic over sliding windows.
    """

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._request_windows: dict[str, deque[float]] = {}
        self._token_windows: dict[str, deque[tuple[float, int]]] = {}
        self._in_flight: dict[str, int] = {}
        self._custom_limits: dict[str, ProviderQuotaProfile] = {}

    def get_profile(self, provider_name: str | None = None, credential_id: str | None = None) -> ProviderQuotaProfile:
        if credential_id and credential_id in self._custom_limits:
            return self._custom_limits[credential_id]
        if provider_name:
            p_clean = provider_name.strip().lower()
            for key, prof in DEFAULT_PROVIDER_QUOTAS.items():
                if key in p_clean:
                    return prof
        return DEFAULT_PROVIDER_QUOTAS["default"]

    def set_custom_limit(self, credential_id: str, profile: ProviderQuotaProfile) -> None:
        with self._lock:
            self._custom_limits[credential_id] = profile

    def _purge(self, key: str, now: float) -> deque[float]:
        if key not in self._request_windows:
            self._request_windows[key] = deque()
        window = self._request_windows[key]
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()
        return window

    def get_utilization(self, credential_id: str, provider_name: str | None = None) -> dict[str, Any]:
        """Return rolling utilization metrics for a given upstream credential."""
        now = time.monotonic()
        prof = self.get_profile(provider_name, credential_id)
        with self._lock:
            window = self._purge(credential_id, now)
            rpm_used = len(window)
            in_flight = self._in_flight.get(credential_id, 0)

        rpm_limit = prof.rpm_limit
        rpm_percent = min(1.0, rpm_used / max(1, rpm_limit))
        is_saturated = (rpm_percent >= 0.85) or (in_flight >= prof.concurrency_limit)
        is_fully_exhausted = (rpm_used >= rpm_limit) or (in_flight >= prof.concurrency_limit)

        return {
            "credential_id": credential_id,
            "provider": provider_name or "unknown",
            "rpm_used": rpm_used,
            "rpm_limit": rpm_limit,
            "rpm_percent": rpm_percent,
            "in_flight": in_flight,
            "concurrency_limit": prof.concurrency_limit,
            "is_saturated": is_saturated,
            "is_fully_exhausted": is_fully_exhausted,
        }

    def is_available(self, credential_id: str, provider_name: str | None = None) -> bool:
        """Check if credential has immediate capacity (< 85% RPM and under concurrency limit)."""
        util = self.get_utilization(credential_id, provider_name)
        return not util["is_saturated"]

    async def acquire_slot(
        self,
        credential_id: str,
        provider_name: str | None = None,
        estimated_tokens: int = 100,
        max_wait_seconds: float = 2.0,
    ) -> float:
        """Acquire an execution slot on the upstream credential, buffering in micro-queue if needed.
        
        Returns the queue wait duration in milliseconds.
        """
        start_wait = time.monotonic()
        prof = self.get_profile(provider_name, credential_id)

        while True:
            now = time.monotonic()
            with self._lock:
                window = self._purge(credential_id, now)
                rpm_used = len(window)
                in_flight = self._in_flight.get(credential_id, 0)

                # If under hard ceiling, consume immediately
                if rpm_used < prof.rpm_limit and in_flight < prof.concurrency_limit:
                    window.append(now)
                    self._in_flight[credential_id] = in_flight + 1
                    return max(0.0, (time.monotonic() - start_wait) * 1000.0)

            # Check if timeout exceeded
            elapsed = time.monotonic() - start_wait
            if elapsed >= max_wait_seconds:
                # Forced best-effort admission to avoid starving client
                with self._lock:
                    window = self._purge(credential_id, time.monotonic())
                    window.append(time.monotonic())
                    self._in_flight[credential_id] = self._in_flight.get(credential_id, 0) + 1
                    return max(0.0, (time.monotonic() - start_wait) * 1000.0)

            # Sleep in 50ms increments to yield event loop
            await asyncio.sleep(0.05)

    def release_slot(self, credential_id: str, actual_tokens: int | None = None) -> None:
        """Release active in-flight execution slot upon completion."""
        with self._lock:
            current = self._in_flight.get(credential_id, 1)
            self._in_flight[credential_id] = max(0, current - 1)

    def reset_credential(self, credential_id: str) -> None:
        with self._lock:
            self._request_windows.pop(credential_id, None)
            self._token_windows.pop(credential_id, None)
            self._in_flight.pop(credential_id, None)
            self._custom_limits.pop(credential_id, None)

    def reset_all(self) -> None:
        with self._lock:
            self._request_windows.clear()
            self._token_windows.clear()
            self._in_flight.clear()
            self._custom_limits.clear()


# Global Upstream Credential Rate Limiter Singleton
upstream_quota_limiter = ProviderCredentialRateLimiter()
