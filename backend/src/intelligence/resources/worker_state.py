"""WorkerState — runtime snapshot of a single worker's current state.

This dataclass is the in-memory view that the routing engine uses for
every decision. It combines static configuration (model, capabilities)
with dynamic telemetry (latency, TPS, quota, load) and health status.

PostgreSQL remains the historical persistence layer; WorkerState is
rebuilt from DB data on startup and updated via application events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WorkerState:
    """Fast runtime view of a single worker resource."""

    worker_id: uuid.UUID
    provider: str
    credential_id: uuid.UUID
    model: str
    worker_type: str = "cloud"

    # Configuration state
    enabled: bool = True
    healthy: bool = True
    health_status: str = "unknown"
    consecutive_failures: int = 0

    # Capabilities (from Worker.capabilities JSON)
    capabilities: dict[str, Any] = field(default_factory=dict)

    # Current load
    active_requests: int = 0

    # Performance metrics (from RequestMetric aggregation)
    ttft_p50_ms: float | None = None
    ttft_p95_ms: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    tps_p50: float | None = None
    error_rate: float = 0.0
    success_rate: float = 1.0
    sample_count: int = 0

    # Quota (from QuotaSnapshot)
    quota_requests_remaining: int | None = None
    quota_requests_limit: int | None = None
    quota_tokens_remaining: int | None = None
    quota_tokens_limit: int | None = None
    quota_reset_at: datetime | None = None
    quota_source: str = "unknown"  # provider_reported | response_header | estimated | unknown

    # Timestamps
    last_used_at: datetime | None = None
    last_health_check_at: datetime | None = None

    @property
    def is_eligible(self) -> bool:
        """Quick check: enabled and not known-unhealthy."""
        return self.enabled and self.health_status in ("healthy", "unknown", "degraded")

    @property
    def has_known_quota(self) -> bool:
        return self.quota_source in ("provider_reported", "response_header")

    @property
    def performance_confidence(self) -> float:
        """Confidence in performance metrics based on sample size.

        Returns a value in [0, 1]. Uses a simple sigmoid-like ramp:
        - 0 samples → 0.0
        - 10 samples → ~0.5
        - 50+ samples → ~0.95
        - 200+ samples → ~1.0

        This prevents workers with tiny sample sizes from dominating
        those with thousands of observations due to noise.
        """
        if self.sample_count <= 0:
            return 0.0
        # Simple logistic curve: confidence = 1 - 1/(1 + count/20)
        return 1.0 - 1.0 / (1.0 + self.sample_count / 20.0)
