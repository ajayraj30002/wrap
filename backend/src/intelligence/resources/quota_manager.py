"""QuotaManager — evaluates quota fitness without reservation.

Phase 2A performs quota *evaluation* only, not reservation. Complex
distributed quota reservation semantics belong to Phase 2C when
concurrent multi-task execution is introduced.

Quota sources and their confidence:
- provider_reported → highest confidence (provider confirmed)
- response_header   → high confidence (from last API response)
- estimated         → low confidence (WRAP estimate)
- unknown           → no data (neutral score)

Never converts an estimate into authoritative quota.
Never attempts to bypass provider limits.
"""

from __future__ import annotations

from src.intelligence.resources.worker_state import WorkerState


# Minimum requests remaining to be considered "sufficient"
_MIN_REQUESTS_THRESHOLD = 5

# Source confidence weights
_SOURCE_CONFIDENCE: dict[str, float] = {
    "provider_reported": 1.0,
    "response_header": 0.9,
    "estimated": 0.4,
    "unknown": 0.0,
}


class QuotaManager:
    """Evaluates quota fitness for routing decisions."""

    def score(self, worker: WorkerState) -> float:
        """Compute quota_score ∈ [0, 1] where 1.0 = abundant quota.

        Scoring logic:
        1. Unknown quota source → 0.5 (neutral, don't penalize)
        2. Provider-confirmed with plenty remaining → 1.0
        3. Running low → proportionally lower
        4. At or near zero → 0.0

        A worker with unknown quota is NOT automatically treated as
        equivalent to a worker with provider-confirmed quota.
        """
        source_confidence = _SOURCE_CONFIDENCE.get(worker.quota_source, 0.0)

        # No quota data at all → neutral score
        if source_confidence == 0.0:
            return 0.5

        # Evaluate requests remaining
        req_score = self._evaluate_remaining(
            remaining=worker.quota_requests_remaining,
            limit=worker.quota_requests_limit,
        )

        # Evaluate tokens remaining
        tok_score = self._evaluate_remaining(
            remaining=worker.quota_tokens_remaining,
            limit=worker.quota_tokens_limit,
        )

        # Use the worse of the two (request or token quota)
        raw_score = min(req_score, tok_score)

        # Blend with source confidence: low-confidence sources are
        # pulled toward neutral (0.5) rather than treated as gospel
        blended = 0.5 * (1.0 - source_confidence) + raw_score * source_confidence
        return max(0.0, min(1.0, blended))

    def has_sufficient_quota(self, worker: WorkerState) -> bool:
        """Check if worker has enough known quota for at least one request.

        Used by hard constraint filter. Returns True if:
        - Quota is unknown (benefit of the doubt)
        - Quota source is low-confidence (estimated)
        - Known remaining > threshold
        """
        # Unknown or low-confidence → don't reject
        if worker.quota_source in ("unknown", "estimated"):
            return True

        # High-confidence source: predictive throttle if remaining <= 2 to prevent concurrent 429 bursts
        if worker.quota_requests_remaining is not None:
            if worker.quota_requests_remaining <= 2:
                return False

        if worker.quota_tokens_remaining is not None:
            if worker.quota_tokens_remaining <= 500:
                return False

        return True

    def _evaluate_remaining(
        self,
        remaining: int | None,
        limit: int | None,
    ) -> float:
        """Score remaining capacity as a fraction of limit.

        Returns 1.0 if unknown or abundant, 0.0 if exhausted.
        """
        if remaining is None:
            return 1.0  # Unknown → optimistic

        if remaining <= 0:
            return 0.0

        if limit is not None and limit > 0:
            ratio = remaining / limit
            # Scale: 100% remaining → 1.0, 10% → 0.5, 1% → 0.1
            return max(0.0, min(1.0, ratio * 1.2))
        else:
            # Have remaining count but no limit — use absolute threshold
            if remaining > 100:
                return 1.0
            elif remaining > _MIN_REQUESTS_THRESHOLD:
                return 0.7
            else:
                return 0.3
