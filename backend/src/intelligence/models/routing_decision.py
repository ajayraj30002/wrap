"""RoutingDecisionData — the complete routing decision produced by Phase 2A.

This is the internal representation. It maps to the existing
RoutingDecision DB model (extended with new columns) for persistence,
and to the structured explanation JSON for diagnostics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from src.intelligence.models.scoring import (
    CandidateScores,
    PerformancePrediction,
    RejectedCandidate,
    ScoredCandidate,
)


ROUTING_VERSION = "phase2a-v1"


@dataclass
class RoutingDecisionData:
    """Complete routing decision with explanation data."""

    request_id: str
    selected_worker_id: uuid.UUID | None = None
    selected_provider: str | None = None
    selected_model: str | None = None

    # Candidate tracking
    all_candidates: list[uuid.UUID] = field(default_factory=list)
    eligible_candidates: list[ScoredCandidate] = field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = field(default_factory=list)

    # Policy
    policy: str = "balanced"
    routing_version: str = ROUTING_VERSION

    # Prediction (for the selected worker)
    predicted_ttft_ms: float | None = None
    predicted_latency_ms: float | None = None
    prediction_confidence: float | None = None

    # Scores (for the selected worker)
    scores: CandidateScores | None = None

    # Human-readable reasons
    decision_reasons: list[str] = field(default_factory=list)

    # Timing
    routing_duration_ms: float | None = None
    execution_run_id: uuid.UUID | None = None
    execution_node_id: str | None = None

    def to_explanation(self) -> dict[str, Any]:
        """Generate the structured explanation JSON for diagnostics.

        Never includes provider API keys, encrypted secrets, or
        authorization headers.
        """
        candidates_info = []
        for sc in self.eligible_candidates:
            candidates_info.append({
                "worker_id": str(sc.worker_id),
                "provider": sc.provider,
                "model": sc.model,
                "eligible": True,
                "scores": sc.scores.as_dict(),
                "prediction": sc.prediction.as_dict(),
            })
        for rc in self.rejected_candidates:
            candidates_info.append({
                "worker_id": str(rc.worker_id),
                "provider": rc.provider,
                "model": rc.model,
                "eligible": False,
                "rejection_reason": rc.reason,
            })

        return {
            "request_id": self.request_id,
            "policy": self.policy,
            "routing_version": self.routing_version,
            "selected_worker": {
                "worker_id": str(self.selected_worker_id) if self.selected_worker_id else None,
                "provider": self.selected_provider,
                "model": self.selected_model,
            } if self.selected_worker_id else None,
            "prediction": {
                "ttft_ms": round(self.predicted_ttft_ms) if self.predicted_ttft_ms is not None else None,
                "latency_ms": round(self.predicted_latency_ms) if self.predicted_latency_ms is not None else None,
                "confidence": round(self.prediction_confidence, 4) if self.prediction_confidence is not None else None,
            },
            "scores": self.scores.as_dict() if self.scores else None,
            "candidates": candidates_info,
            "decision_reasons": self.decision_reasons,
            "routing_duration_ms": round(self.routing_duration_ms, 2) if self.routing_duration_ms is not None else None,
        }

    def to_db_fields(self) -> dict[str, Any]:
        """Fields for persisting to the RoutingDecision DB model."""
        return {
            "request_id": self.request_id,
            "candidate_workers": [str(wid) for wid in self.all_candidates],
            "selected_worker": str(self.selected_worker_id) if self.selected_worker_id else None,
            "decision_reason": "; ".join(self.decision_reasons[:3]) if self.decision_reasons else "no reason",
            "routing_version": self.routing_version,
            "policy": self.policy,
            "predicted_latency_ms": int(self.predicted_latency_ms) if self.predicted_latency_ms is not None else None,
            "predicted_ttft_ms": int(self.predicted_ttft_ms) if self.predicted_ttft_ms is not None else None,
            "prediction_confidence": round(self.prediction_confidence, 4) if self.prediction_confidence is not None else None,
            "decision_metadata": self.to_explanation(),
            "execution_run_id": self.execution_run_id,
            "execution_node_id": self.execution_node_id,
        }
