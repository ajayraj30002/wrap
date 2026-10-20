"""RoutingExplanation — builds human-readable explanation for routing decisions.

Generates the decision_reasons list and ensures no sensitive data
(provider API keys, encrypted secrets, authorization headers) is exposed.
"""

from __future__ import annotations

from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.models.scoring import RejectedCandidate, ScoredCandidate
from src.intelligence.resources.worker_state import WorkerState


class RoutingExplanation:
    """Generates structured explanations for routing decisions."""

    def build_reasons(
        self,
        profile: RequestProfile,
        selected: ScoredCandidate | None,
        all_scored: list[ScoredCandidate],
        rejected: list[RejectedCandidate],
        policy: str,
    ) -> list[str]:
        """Build a list of human-readable reason strings.

        Never includes provider credentials or sensitive information.
        """
        reasons: list[str] = []

        if selected is None:
            reasons.append("no eligible worker found")
            if rejected:
                reasons.append(f"{len(rejected)} workers rejected by constraints")
                # Summarize rejection reasons
                reason_counts: dict[str, int] = {}
                for r in rejected:
                    reason_counts[r.reason] = reason_counts.get(r.reason, 0) + 1
                for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                    reasons.append(f"  {count}x {reason}")
            return reasons

        # Selected worker info
        reasons.append(
            f"selected worker for model={selected.model} via provider={selected.provider}"
        )

        # Model routing mode
        if profile.is_auto_model:
            reasons.append("model=auto: intelligent routing active")
        else:
            reasons.append(f"model={profile.model_requested}: explicit model, intelligent worker selection")

        # Policy
        reasons.append(f"policy={policy}")

        # Why this worker won
        scores = selected.scores
        if scores.latency >= 0.8:
            reasons.append("lowest predicted latency among eligible workers")
        elif scores.latency >= 0.6:
            reasons.append("competitive predicted latency")

        if scores.reliability >= 0.9:
            reasons.append("strong recent reliability")
        elif scores.reliability >= 0.7:
            reasons.append("acceptable reliability")

        if scores.capability >= 0.8:
            reasons.append("strong capability match")

        if scores.quota >= 0.8:
            reasons.append("sufficient known quota")
        elif scores.quota >= 0.5:
            reasons.append("adequate quota availability")

        if scores.load >= 0.8:
            reasons.append("worker currently idle/lightly loaded")

        # Confidence note
        if selected.performance_confidence < 0.3:
            reasons.append("low performance confidence (limited historical data)")

        # Candidate/rejection summary
        if len(all_scored) > 1:
            reasons.append(f"{len(all_scored)} eligible workers evaluated")
        if rejected:
            reasons.append(f"{len(rejected)} workers rejected by constraints")

        return reasons
