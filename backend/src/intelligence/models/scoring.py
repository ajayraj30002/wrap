"""Scoring models — intermediate data structures for the routing pipeline.

These dataclasses carry per-worker score information through the pipeline
stages without coupling any stage to another.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CandidateScores:
    """Named score dimensions for a single worker candidate.

    All scores are normalized to [0, 1] where 1.0 = best.
    """

    capability: float = 0.0
    latency: float = 0.0
    reliability: float = 0.0
    quota: float = 0.0
    load: float = 0.0

    # Weighted composite (set by AllocationOptimizer)
    composite: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "capability": round(self.capability, 4),
            "latency": round(self.latency, 4),
            "reliability": round(self.reliability, 4),
            "quota": round(self.quota, 4),
            "load": round(self.load, 4),
            "composite": round(self.composite, 4),
        }


@dataclass
class PerformancePrediction:
    """Predicted performance for a specific worker + request combination."""

    predicted_ttft_ms: float | None = None
    predicted_latency_ms: float | None = None
    predicted_tps: float | None = None
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "predicted_ttft_ms": round(self.predicted_ttft_ms) if self.predicted_ttft_ms is not None else None,
            "predicted_latency_ms": round(self.predicted_latency_ms) if self.predicted_latency_ms is not None else None,
            "predicted_tps": round(self.predicted_tps, 1) if self.predicted_tps is not None else None,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ScoredCandidate:
    """A worker that has passed hard constraints and been scored."""

    worker_id: uuid.UUID
    provider: str
    model: str
    credential_id: uuid.UUID

    scores: CandidateScores = field(default_factory=CandidateScores)
    prediction: PerformancePrediction = field(default_factory=PerformancePrediction)

    # For tie-breaking and diagnostics
    sample_count: int = 0
    performance_confidence: float = 0.0


@dataclass
class RejectedCandidate:
    """A worker that was removed by hard constraint filtering."""

    worker_id: uuid.UUID
    provider: str
    model: str
    reason: str  # e.g. "unhealthy", "model_not_available", "context_limit"
