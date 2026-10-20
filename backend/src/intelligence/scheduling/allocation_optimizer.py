"""AllocationOptimizer — multi-objective scoring and worker selection.

Combines scores from CapabilityEngine, PerformanceEngine, QuotaManager
using weights from PolicyEngine, then selects the best worker.

Scoring is deterministic and explainable:
1. Each dimension produces a normalized [0,1] score.
2. Dimensions are weighted by the active routing policy.
3. Weighted sum produces a composite score.
4. Tie-breaking is deterministic (see _tie_break_key).
5. The selected worker's scores and reasons are recorded.

Score dimensions:
- capability ∈ [0,1]: static capability match
- latency ∈ [0,1]: predicted latency (1.0 = fastest)
- reliability ∈ [0,1]: historical success rate
- quota ∈ [0,1]: available quota (1.0 = abundant)
- load ∈ [0,1]: current worker load (1.0 = idle)
"""

from __future__ import annotations

import uuid
from typing import Any

from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.models.scoring import (
    CandidateScores,
    PerformancePrediction,
    ScoredCandidate,
)
from src.intelligence.resources.capability_engine import CapabilityEngine
from src.intelligence.resources.performance_engine import PerformanceEngine
from src.intelligence.resources.quota_manager import QuotaManager
from src.intelligence.resources.worker_state import WorkerState
from src.intelligence.scheduling.policy_engine import PolicyEngine, PolicyWeights


class AllocationOptimizer:
    """Combines all scoring dimensions and selects the optimal worker."""

    def __init__(
        self,
        capability_engine: CapabilityEngine | None = None,
        performance_engine: PerformanceEngine | None = None,
        quota_manager: QuotaManager | None = None,
    ) -> None:
        self._capability = capability_engine or CapabilityEngine()
        self._performance = performance_engine or PerformanceEngine()
        self._quota = quota_manager or QuotaManager()

    def score_and_select(
        self,
        profile: RequestProfile,
        eligible: list[WorkerState],
        weights: PolicyWeights,
    ) -> tuple[ScoredCandidate | None, list[ScoredCandidate]]:
        """Score all eligible workers and select the best one.

        Returns (selected, all_scored). selected is None if no eligible workers.
        """
        if not eligible:
            return None, []

        scored: list[ScoredCandidate] = []

        for worker in eligible:
            # Score each dimension
            cap_score = self._capability.score(profile, worker)
            prediction = self._performance.predict(profile, worker)
            lat_score = self._performance.latency_score(prediction)
            rel_score = self._performance.reliability_score(worker)
            quota_score = self._quota.score(worker)
            load_score = self._performance.load_score(worker)

            # Compute weighted composite
            total_weight = weights.total
            if total_weight > 0:
                composite = (
                    cap_score * weights.capability
                    + lat_score * weights.latency
                    + rel_score * weights.reliability
                    + quota_score * weights.quota
                    + load_score * weights.load
                ) / total_weight
            else:
                composite = (cap_score + lat_score + rel_score + quota_score + load_score) / 5.0

            scores = CandidateScores(
                capability=cap_score,
                latency=lat_score,
                reliability=rel_score,
                quota=quota_score,
                load=load_score,
                composite=composite,
            )

            scored.append(ScoredCandidate(
                worker_id=worker.worker_id,
                provider=worker.provider,
                model=worker.model,
                credential_id=worker.credential_id,
                scores=scores,
                prediction=prediction,
                sample_count=worker.sample_count,
                performance_confidence=worker.performance_confidence,
            ))

        # Sort by composite score descending, then deterministic tie-breaking
        scored.sort(key=lambda sc: self._sort_key(sc), reverse=True)

        return scored[0], scored

    def _sort_key(self, sc: ScoredCandidate) -> tuple[float, float, float, float, str]:
        """Deterministic sort key for tie-breaking.

        Order:
        1. Higher composite score
        2. Higher performance confidence (prefer well-known workers)
        3. Higher reliability score
        4. Lower predicted latency (higher latency score)
        5. Worker ID string (absolute deterministic tie-break)
        """
        return (
            sc.scores.composite,
            sc.performance_confidence,
            sc.scores.reliability,
            sc.scores.latency,
            str(sc.worker_id),
        )
