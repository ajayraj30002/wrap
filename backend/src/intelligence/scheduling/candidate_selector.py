"""CandidateSelector — generates initial candidate workers from resource state.

Candidates come from the ResourceStateStore (worker resources), NOT from
the ProviderRegistry. The ProviderRegistry answers "which adapters exist?"
while the resource layer answers "which worker resources are available?"

Includes Tier-Aware Alias Mapping and Pre-Flight Context Guardrails to ensure
coding agents requesting frontier models (e.g. gpt-4o, claude-3-5-sonnet) get
appropriate high-reasoning workers, and requests exceeding small context windows
never route to constrained LPUs.
"""

from __future__ import annotations

import logging
from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.resources.worker_state import WorkerState

logger = logging.getLogger("wrap.candidate_selector")

# Models representing Frontier / Deep Reasoning tier
FRONTIER_ALIASES = {
    "gpt-4o",
    "gpt-4",
    "gpt-4-turbo",
    "claude-3-7-sonnet",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet",
    "claude-3-5-sonnet-latest",
    "claude-3-opus",
    "claude-3-opus-latest",
    "o1",
    "o3-mini",
    "deepseek-reasoner",
    "deepseek-chat",
    "gemini-pro",
    "gemini-1.5-pro",
    "gemini-2.5-pro",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
}

# Preferred frontier worker models available in Wrap pool
FRONTIER_WORKER_PREFERENCES = (
    "gemini-3.1-pro-preview",
    "gemini-pro-latest",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-2.0-flash",
    "openai/gpt-oss-120b",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "gpt-4o",
    "deepseek-chat",
)

# Models representing Fast / Economy tier
ECONOMY_ALIASES = {
    "gpt-4o-mini",
    "claude-3-haiku",
    "claude-3-5-haiku",
    "claude-3-5-haiku-latest",
    "gemini-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash-lite",
    "fast",
    "compound-mini",
    "llama-3.1-8b-instant",
    "llama3.1-8b",
}

ECONOMY_WORKER_PREFERENCES = (
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant",
)


class CandidateSelector:
    """Generates the initial candidate set from resource state."""

    def select(
        self,
        profile: RequestProfile,
        workers: list[WorkerState],
    ) -> list[WorkerState]:
        """Select candidate workers based on model requirement.

        For explicit model: check exact match first, then tier mapping.
        For auto: all workers (filtered by subsequent stages).
        """
        if profile.is_auto_model:
            candidates = list(workers)
        else:
            requested = (profile.model_requested or "").strip().lower()

            # 1. Exact worker match first
            matched = [w for w in workers if w.model.lower() == requested]
            if matched:
                candidates = matched
            else:
                # 2. Tier-Aware Alias Mapping:
                # Check Economy/Speed tier first so 'mini' / 'haiku' aren't mistakenly caught by 'gpt-4' or 'claude'
                if requested in ECONOMY_ALIASES or any(k in requested for k in ["mini", "haiku", "lite", "fast", "8b", "flash-lite"]):
                    # Prioritize fast/economy workers
                    economy_cands = [
                        w for w in workers
                        if any(pref in w.model.lower() for pref in ECONOMY_WORKER_PREFERENCES)
                    ]
                    if economy_cands:
                        logger.info("Tier-Aware Routing: Mapped economy alias '%s' to %d fast workers", requested, len(economy_cands))
                        candidates = economy_cands
                    else:
                        candidates = list(workers)

                elif requested in FRONTIER_ALIASES or any(k in requested for k in ["gpt-4", "sonnet", "opus", "o1", "o3", "pro"]):
                    # Prioritize high-reasoning frontier workers
                    frontier_cands = [
                        w for w in workers
                        if any(pref in w.model.lower() for pref in FRONTIER_WORKER_PREFERENCES)
                    ]
                    if frontier_cands:
                        logger.info("Tier-Aware Routing: Mapped frontier alias '%s' to %d high-reasoning workers", requested, len(frontier_cands))
                        candidates = frontier_cands
                    else:
                        candidates = list(workers)
                else:
                    candidates = list(workers)


        # 3. Pre-Flight Context Guardrail:
        # If the request context is large (>28,000 tokens), eliminate workers from providers with
        # low context windows or strict TPM caps (like Groq free tier) to prevent crashes.
        input_tokens = getattr(profile.raw, "input_tokens", 0) or 0
        if input_tokens > 28000:
            long_context_cands = [
                w for w in candidates
                if ("gemini" in w.model.lower() or "google" in (w.provider or "").lower() or w.capabilities.get("context_window", 0) >= 64000)
            ]
            if long_context_cands:
                logger.info("Context Guardrail: Large request (%d tokens) restricted to %d long-context workers", input_tokens, len(long_context_cands))
                candidates = long_context_cands

        return candidates
