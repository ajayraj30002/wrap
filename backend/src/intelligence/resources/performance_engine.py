"""PerformanceEngine — predicts latency and assesses reliability from telemetry.

Uses Phase 1 telemetry data (TTFT, latency, TPS, error rate) aggregated
per worker in the ResourceStateStore. Produces a PerformancePrediction
and a latency_score / reliability_score for the allocation optimizer.

Latency prediction formula (first-order deterministic estimator):
    predicted_latency ≈ predicted_ttft
                      + estimated_output_tokens / predicted_tps
                      + load_penalty
                      + overhead

Confidence is based on sample count using WorkerState.performance_confidence.
"""

from __future__ import annotations

from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.models.scoring import PerformancePrediction
from src.intelligence.resources.worker_state import WorkerState


# Default values when no telemetry is available
_DEFAULT_TTFT_MS = 500.0
_DEFAULT_LATENCY_MS = 3000.0
_DEFAULT_TPS = 50.0

# Load penalty per active request (ms)
_LOAD_PENALTY_PER_REQUEST_MS = 200.0

# Maximum latency for normalization (10s)
_MAX_LATENCY_MS = 10_000.0

# Overhead estimate for routing + serialization (ms)
_ROUTING_OVERHEAD_MS = 5.0


class PerformanceEngine:
    """Predicts per-worker performance for a given request profile."""

    def predict(self, profile: RequestProfile, worker: WorkerState) -> PerformancePrediction:
        """Produce a latency/throughput prediction for this worker.

        Returns PerformancePrediction with estimated values and confidence.
        """
        confidence = worker.performance_confidence

        # TTFT prediction
        if worker.ttft_p50_ms is not None:
            predicted_ttft = worker.ttft_p50_ms
        else:
            predicted_ttft = _DEFAULT_TTFT_MS

        # TPS prediction
        if worker.tps_p50 is not None and worker.tps_p50 > 0:
            predicted_tps = worker.tps_p50
        else:
            predicted_tps = _DEFAULT_TPS

        # Output token estimation
        est_output = profile.raw.estimated_output_tokens or 200

        # Generation time = output_tokens / tps (in ms)
        generation_ms = (est_output / predicted_tps) * 1000.0

        # Load penalty: each active request adds latency
        load_penalty = worker.active_requests * _LOAD_PENALTY_PER_REQUEST_MS

        # Total predicted latency
        predicted_latency = predicted_ttft + generation_ms + load_penalty + _ROUTING_OVERHEAD_MS

        return PerformancePrediction(
            predicted_ttft_ms=predicted_ttft,
            predicted_latency_ms=predicted_latency,
            predicted_tps=predicted_tps,
            confidence=confidence,
        )

    def latency_score(self, prediction: PerformancePrediction) -> float:
        """Convert predicted latency into a [0, 1] score where 1.0 = fastest.

        Uses bounded inverse: score = 1 - (latency / max_latency)
        Avoids unstable min/max normalization on tiny candidate sets.
        """
        if prediction.predicted_latency_ms is None:
            return 0.5  # Unknown → neutral

        lat = max(0.0, prediction.predicted_latency_ms)
        score = 1.0 - min(1.0, lat / _MAX_LATENCY_MS)
        return max(0.0, score)

    def reliability_score(self, worker: WorkerState) -> float:
        """Score based on historical success rate, weighted by confidence.

        Low-sample workers get pulled toward 0.5 (neutral) rather than
        trusting potentially noisy success rates.
        """
        if worker.sample_count == 0:
            return 0.5  # No data → neutral

        raw_reliability = worker.success_rate
        confidence = worker.performance_confidence

        # Blend toward neutral (0.7) for low confidence
        neutral = 0.7
        blended = neutral * (1.0 - confidence) + raw_reliability * confidence
        return max(0.0, min(1.0, blended))

    def load_score(self, worker: WorkerState) -> float:
        """Score based on current worker load where 1.0 = idle.

        Simple bounded inverse: more active requests → lower score.
        """
        if worker.active_requests <= 0:
            return 1.0
        # 5 active requests → 0.5, 10 → 0.33, etc.
        return 1.0 / (1.0 + worker.active_requests * 0.2)
