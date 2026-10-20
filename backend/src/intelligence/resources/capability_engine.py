"""CapabilityEngine — evaluates how well a worker's capabilities match request needs.

Separates static capabilities (context window, streaming, tool calling)
from empirical performance (latency, TPS, error rate). This module
handles ONLY static capability matching.

Returns a capability_score ∈ [0, 1] where 1.0 = perfect match.
"""

from __future__ import annotations

from src.intelligence.analysis.request_profile import RequestProfile
from src.intelligence.resources.worker_state import WorkerState


# Known model quality tiers — static metadata, not fake benchmarks.
# Source: model_metadata / provider documentation.
# Used when model="auto" to prefer higher-quality models for complex requests.
_MODEL_QUALITY_TIERS: dict[str, float] = {
    # Tier 1: Large flagship models
    "gemini-3.8-flash": 0.92,
    "gemini-3.7-flash": 0.90,
    "gemini-3.6-flash": 0.88,
    "gemini-3.5-flash": 0.88,
    "gemini-flash-latest": 0.88,
    "gemini-2.5-pro": 0.95,
    "gemini-1.5-pro": 0.9,
    "gemini-2.5-flash": 0.88,
    "gemini-2.0-flash": 0.88,
    "gemini-flash-lite-latest": 0.85,
    "qwen/qwen3.8-27b": 0.86,
    "qwen-2.5-32b": 0.86,
    "llama-3.3-70b-versatile": 0.85,
    "llama-3.3-70b": 0.85,
    "llama3.3-70b": 0.85,
    "llama3.1-70b": 0.85,
    "llama-4-scout-17b-16e-instruct": 0.8,
    # Tier 2: Smaller/faster models
    "gemini-1.5-flash": 0.7,
    "llama-3.1-8b-instant": 0.6,
    "llama3.1-8b": 0.6,
}

# Fallback quality for models not covered by dynamic signals
_DEFAULT_QUALITY = 0.75
_DEFAULT_CONTEXT_WINDOW = 131_072

_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Large context flagship models
    "gemini-3.8-flash": 1_048_576,
    "gemini-3.7-flash": 1_048_576,
    "gemini-3.6-flash": 1_048_576,
    "gemini-3.5-flash": 1_048_576,
    "gemini-flash-latest": 1_048_576,
    "gemini-2.5-pro": 2_097_152,
    "gemini-1.5-pro": 2_097_152,
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-1.5-flash": 1_048_576,
    "gemini-flash-lite-latest": 1_048_576,
    # Llama series
    "llama-3.3-70b-versatile": 131_072,
    "llama-3.3-70b": 131_072,
    "llama3.3-70b": 131_072,
    "llama-3.1-70b-versatile": 131_072,
    "llama-3.1-70b": 131_072,
    "llama3.1-70b": 131_072,
    "llama-3.1-8b-instant": 131_072,
    "llama-3.1-8b": 131_072,
    "llama3.1-8b": 131_072,
    "llama-4-scout-17b-16e-instruct": 131_072,
    # Other models
    "mixtral-8x7b-32768": 32_768,
    "gemma2-9b-it": 8_192,
    "qwen/qwen3.8-27b": 131_072,
    "qwen-2.5-32b": 32_768,
    "qwen-2.5-72b": 32_768,
    "deepseek-r1-distill-llama-70b": 131_072,
}


def get_model_quality(worker: WorkerState) -> float:
    """Dynamically determine model quality tier based on capabilities, architecture, and telemetry."""
    if "quality_tier" in worker.capabilities:
        try:
            return float(worker.capabilities["quality_tier"])
        except (ValueError, TypeError):
            pass

    mid = worker.model.lower()

    # 1. Native reasoning flag from provider
    if worker.capabilities.get("reasoning") is True:
        return 0.95

    # 2. Flagship frontier indicators
    if any(k in mid for k in ["opus", "sonnet", "ultra", "120b", "pro", "deep-research", "argon"]):
        return 0.93

    # 3. High capacity models (70B, 32B, 31B, 27B, Flash)
    if any(k in mid for k in ["70b", "32b", "31b", "27b", "flash"]):
        if any(k in mid for k in ["lite", "flash-lite", "mini"]):
            return 0.82
        return 0.88

    # 4. Lightweight / Economy models
    if any(k in mid for k in ["8b", "7b", "3b", "20b", "haiku", "instant", "nano"]):
        return 0.72

    # Fallback to legacy dictionary or sensible default
    return _MODEL_QUALITY_TIERS.get(worker.model, _DEFAULT_QUALITY)


def get_context_window(worker: WorkerState) -> int:
    """Retrieve context window from worker capabilities or architectural tier."""
    cw = worker.capabilities.get("context_window")
    if cw and isinstance(cw, (int, float)) and cw > 0:
        return int(cw)
    if worker.model in _MODEL_CONTEXT_WINDOWS:
        return _MODEL_CONTEXT_WINDOWS[worker.model]
    return _DEFAULT_CONTEXT_WINDOW


class CapabilityEngine:
    """Evaluates static capability match between request and worker."""

    def score(self, profile: RequestProfile, worker: WorkerState) -> float:
        """Compute capability_score ∈ [0, 1].

        Components:
        1. Quality tier match (for auto model)
        2. Context window fitness
        3. Streaming capability
        4. Tool capability
        5. Structured output capability
        """
        components: list[tuple[float, float]] = []  # (score, weight)

        # 1. Quality tier (relevant mainly for auto model)
        if profile.is_auto_model:
            quality = get_model_quality(worker)
            # Weight quality by the request's quality requirement
            components.append((quality, 0.3 + 0.2 * profile.quality_requirement))
        else:
            # Explicit model — quality tier is irrelevant since user chose the model
            components.append((1.0, 0.1))

        # 2. Context fitness — how well does the model's context window fit?
        context_window = get_context_window(worker)
        if profile.raw.input_tokens > 0:
            utilization = profile.raw.input_tokens / context_window
            if utilization > 1.0:
                # Should have been caught by hard constraint, but score 0
                context_score = 0.0
            elif utilization > 0.8:
                # Getting close to limit — slightly penalize
                context_score = 0.7
            elif utilization < 0.1:
                # Oversized context window for a small request — slight waste
                context_score = 0.9
            else:
                context_score = 1.0
        else:
            context_score = 1.0
        components.append((context_score, 0.2))

        # 3. Coding capability match
        if profile.coding_demand > 0.3:
            # Prefer models known for code
            code_quality = get_model_quality(worker)
            components.append((code_quality, 0.15 * profile.coding_demand))

        # 4. Streaming match
        streaming_supported = worker.capabilities.get("streaming", True)
        if profile.streaming and not streaming_supported:
            components.append((0.0, 0.3))  # Hard miss but scored (filter should catch)
        else:
            components.append((1.0, 0.05))

        # 5. Tool capability match
        if profile.tool_requirement > 0:
            has_tools = worker.capabilities.get("tool_calling", False)
            has_structured = worker.capabilities.get("response_format", False)
            if has_tools:
                tool_score = 1.0
            elif has_structured:
                tool_score = 0.7
            else:
                tool_score = 0.2
            components.append((tool_score, 0.2))

        # 6. Structured output match
        if profile.structured_output_need > 0.3:
            has_response_format = worker.capabilities.get("response_format", False)
            struct_score = 1.0 if has_response_format else 0.3
            components.append((struct_score, 0.15 * profile.structured_output_need))

        # Weighted average
        if not components:
            return 0.5

        total_weight = sum(w for _, w in components)
        if total_weight <= 0:
            return 0.5

        weighted_sum = sum(s * w for s, w in components)
        return max(0.0, min(1.0, weighted_sum / total_weight))
