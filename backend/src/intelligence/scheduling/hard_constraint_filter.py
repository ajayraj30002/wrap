"""HardEligibilityFilter — removes impossible workers before scoring.

Hard constraints answer: "Can this worker execute the request at all?"
Workers failing ANY hard constraint are REMOVED, not scored lower.

Potential hard constraints:
- worker enabled
- worker healthy (health_status in healthy/unknown)
- context capacity sufficient
- streaming supported when requested
- structured output supported when required
- tool capability supported when required
- known quota not exhausted

Each rejected worker gets a reason string for diagnostics.
"""

from __future__ import annotations

from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.models.scoring import RejectedCandidate
from src.intelligence.resources.capability_engine import (
    _MODEL_CONTEXT_WINDOWS,
    _DEFAULT_CONTEXT_WINDOW,
)
from src.intelligence.resources.quota_manager import QuotaManager
from src.intelligence.resources.worker_state import WorkerState

# TPM limits per provider for pre-flight rejection of oversized requests.
# Sourced from DEFAULT_PROVIDER_QUOTAS but kept as a local constant to avoid
# a circular import with rate_limiter.py at module load time.
_PROVIDER_TPM_LIMITS: dict[str, int] = {
    "groq": 5000,       # Free tier: 6000-7000 ITPM; use 5000 as safe margin
    "cerebras": 60000,
    "gemini": 1_000_000,
    "google": 1_000_000,
    "sambanova": 20000,
    "openai": 100_000,
    "anthropic": 100_000,
}


class FilterResult:
    """Result of hard constraint filtering."""

    def __init__(
        self,
        eligible: list[WorkerState],
        rejected: list[RejectedCandidate],
    ) -> None:
        self.eligible = eligible
        self.rejected = rejected


class HardEligibilityFilter:
    """Removes impossible workers via binary pass/fail constraints."""

    def __init__(self, quota_manager: QuotaManager | None = None) -> None:
        self._quota_manager = quota_manager or QuotaManager()

    def filter(
        self,
        profile: RequestProfile,
        candidates: list[WorkerState],
    ) -> FilterResult:
        """Apply all hard constraints. Workers failing any constraint
        are removed with a rejection reason.
        """
        eligible: list[WorkerState] = []
        rejected: list[RejectedCandidate] = []

        for worker in candidates:
            reason = self._check_constraints(profile, worker)
            if reason is None:
                eligible.append(worker)
            else:
                rejected.append(RejectedCandidate(
                    worker_id=worker.worker_id,
                    provider=worker.provider,
                    model=worker.model,
                    reason=reason,
                ))

        return FilterResult(eligible=eligible, rejected=rejected)

    def _check_constraints(
        self, profile: RequestProfile, worker: WorkerState
    ) -> str | None:
        """Check all hard constraints. Returns rejection reason or None if eligible."""

        # 1. Worker must be enabled
        if not worker.enabled:
            return "disabled"

        # 2. Worker must be healthy (healthy or unknown)
        if not worker.healthy:
            return "unhealthy"

        # 3. Context capacity — input tokens must fit within model's context window
        context_window = (
            worker.capabilities.get("context_window")
            or _MODEL_CONTEXT_WINDOWS.get(worker.model)
            or (1_000_000 if ("gemini" in worker.model.lower() or "google" in (worker.provider or "").lower()) else _DEFAULT_CONTEXT_WINDOW)
        )
        if profile.raw.input_tokens > context_window:
            return "context_limit"

        # 4. Streaming must be supported when requested
        if profile.streaming:
            streaming_supported = worker.capabilities.get("streaming", True)
            if not streaming_supported:
                return "streaming_not_supported"

        # 5. Structured output must be supported when required
        if profile.structured_output_need > 0.5 and profile.raw.response_format:
            has_response_format = worker.capabilities.get("response_format", False)
            if not has_response_format:
                return "structured_output_not_supported"

        # 6. Tool calling must be supported when requested
        if profile.raw.has_tool_requirement:
            has_tool_calling = worker.capabilities.get("tool_calling", False)
            if not has_tool_calling:
                return "tool_calling_not_supported"

        # 7. Known quota must not be exhausted
        if not self._quota_manager.has_sufficient_quota(worker):
            return "quota_exhausted"

        # 8. TPM pre-flight: reject if estimated input tokens alone would exceed
        #    the provider's known per-minute token limit. This prevents Groq
        #    (6000 ITPM on free tier) from receiving Roo Code / IDE requests
        #    that are 7000-10000 tokens before we even get a 429 back.
        if profile.raw.input_tokens > 0:
            p_clean = (worker.provider or "").strip().lower()
            for key, tpm_limit in _PROVIDER_TPM_LIMITS.items():
                if key in p_clean:
                    if profile.raw.input_tokens > tpm_limit:
                        return (
                            f"tpm_preflight: estimated {profile.raw.input_tokens} input tokens "
                            f"exceeds {worker.provider} TPM limit ({tpm_limit})"
                        )
                    break

        return None  # All checks passed
