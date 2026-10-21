"""Virtual Model Groups, Aliasing, and Fallback Cascades for WRAP AI Gateway.

Enables clients to route requests using virtual aliases (e.g. 'fast-tier', 'economy-tier',
'reasoning-tier', 'coding-tier') across heterogeneous physical workers with transparent failover.
Provides autonomous capability classification compatible with all major LLM providers.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelGroup:
    id: str
    name: str
    description: str
    default_policy: str
    models: list[str]


# Universal baseline templates for virtual model groups
BUILTIN_MODEL_GROUPS: dict[str, ModelGroup] = {
    "fast-tier": ModelGroup(
        id="fast-tier",
        name="Fast LPU & Flash Tier",
        description="Ultra-low TTFT and high-throughput streaming inference across Groq, Cerebras, and Gemini Flash.",
        default_policy="latency_optimized",
        models=[
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "gemini-2.0-flash",
            "qwen/qwen3.8-27b",
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
            "groq/llama-3.1-8b-instant",
            "allam-2-7b",
            "openai/gpt-oss-20b",
        ],
    ),
    "reasoning-tier": ModelGroup(
        id="reasoning-tier",
        name="Frontier Reasoning Tier",
        description="Deep reasoning, complex logic, and high benchmark capability.",
        default_policy="quality_first",
        models=[
            "openai/gpt-oss-120b",
            "gemini-2.5-pro",
            "gemini-pro-latest",
            "gemini-3.1-pro-preview",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "deep-research-preview-04-2026",
            "qwen/qwen3.8-27b",
            "cerebras/llama-3.3-70b",
            "openai/o1",
            "openai/o3-mini",
        ],
    ),
    "economy-tier": ModelGroup(
        id="economy-tier",
        name="Economy & Free Tier",
        description="Maximum quota headroom, lightweight token-efficient models.",
        default_policy="balanced",
        models=[
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash-lite",
            "groq/llama-3.1-8b-instant",
            "openai/gpt-oss-20b",
            "allam-2-7b",
            "qwen/qwen3.8-27b",
            "gemini-2.0-flash",
            "gemini-3.5-flash",
        ],
    ),
    "coding-tier": ModelGroup(
        id="coding-tier",
        name="Code & Synthesis Tier",
        description="Syntax, code-completion, and multi-step tool execution optimized models.",
        default_policy="quality_first",
        models=[
            "qwen/qwen3.8-27b",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-2.5-pro",
            "gemini-3.1-pro-preview",
            "gemini-3.6-flash",
            "groq/llama-3.3-70b-versatile",
            "gemini-flash-lite-latest",
        ],
    ),
    "ensemble-consensus": ModelGroup(
        id="ensemble-consensus",
        name="Dual-Model Ensemble Consensus Tier",
        description="High-speed primary generation verified concurrently by deep reasoning model for frontier accuracy at $0 cost.",
        default_policy="quality_first",
        models=[
            "gemini-flash-lite-latest",
            "openai/gpt-oss-120b",
            "gemini-2.5-pro",
            "qwen/qwen3.8-27b",
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-2.0-flash",
        ],
    ),
}

# Aliases mapping to groups
ALIAS_MAP: dict[str, str] = {
    "fast": "fast-tier",
    "ultra-fast": "fast-tier",
    "lpu": "fast-tier",
    "reasoning": "reasoning-tier",
    "frontier": "reasoning-tier",
    "economy": "economy-tier",
    "free": "economy-tier",
    "cheap": "economy-tier",
    "coding": "coding-tier",
    "code": "coding-tier",
    "consensus": "ensemble-consensus",
    "ensemble": "ensemble-consensus",
    "dual-model": "ensemble-consensus",
    "frontier-consensus": "ensemble-consensus",
}


def classify_model_into_tiers(model_name: str, provider_name: str | None = None, capabilities: dict | None = None) -> set[str]:
    """Autonomously classify any model from any provider into matching virtual model tiers.

    Compatible across all 14 providers (Gemini, Groq, Cerebras, OpenAI, Anthropic, DeepSeek,
    Mistral, SambaNova, Together, Fireworks, Ollama/Local, OpenRouter, Perplexity, Cohere, XAI).
    """
    tiers: set[str] = set()
    m = (model_name or "").lower().strip()
    p = (provider_name or "").lower().strip()
    caps = capabilities or {}

    is_lpu_fast_provider = p in ("groq", "cerebras", "sambanova")
    is_reasoning_capability = bool(caps.get("reasoning"))
    is_coding_capability = "coder" in m or "code" in m
    is_audio_only = any(k in m for k in ("orpheus", "whisper", "tts", "audio"))
    is_massive_weights = any(k in m for k in ("120b", "405b"))

    if is_audio_only:
        return tiers

    # 1. FAST TIER (Latency Optimized)
    # Fast flash/lite models or low-latency LPU models (<70B)
    if not is_massive_weights and (
        (is_lpu_fast_provider and not any(k in m for k in ("safeguard",)))
        or any(k in m for k in ("flash", "lite", "mini", "haiku", "turbo", "nemo", "speed", "8b", "7b", "20b", "27b", "instant", "small"))
    ):
        tiers.add("fast-tier")

    # 2. FRONTIER REASONING TIER (Quality First)
    if (
        is_reasoning_capability
        or any(k in m for k in (
            "reason", "thinking", "pro", "o1", "o3", "o4", "r1", "opus", "sonnet",
            "120b", "70b", "72b", "405b", "large", "deep-research", "gpt-4o", "gpt-4",
            "3.7-flash", "3.8-flash", "3.6-flash"
        ))
    ):
        tiers.add("reasoning-tier")

    # 3. ECONOMY & FREE TIER (Balanced)
    if not is_massive_weights and (
        any(k in m for k in ("lite", "flash", "mini", "haiku", "nano", "banana", "8b", "7b", "20b", "small", "free", "open-mistral"))
        or (is_lpu_fast_provider and any(k in m for k in ("8b", "7b", "20b", "27b", "instant")))
    ):
        tiers.add("economy-tier")

    # 4. CODE & SYNTHESIS TIER (Quality First)
    if (
        is_coding_capability
        or any(k in m for k in ("coder", "code", "codestral", "qwen", "sonnet", "3.7-flash", "3.8-flash", "pro", "gpt-4o", "o3", "r1"))
    ):
        tiers.add("coding-tier")

    # 5. ENSEMBLE CONSENSUS TIER
    if "fast-tier" in tiers or "reasoning-tier" in tiers:
        tiers.add("ensemble-consensus")

    return tiers


def get_tier_model_priority(model: str, tier_id: str, provider: str | None = None) -> int:
    """Determine ranking priority for models within a specific tier cascade."""
    m = model.lower()
    p = (provider or "").lower()

    if tier_id == "fast-tier":
        if p in ("cerebras", "groq"):
            return 5
        if "flash-lite" in m or "flash_lite" in m:
            return 10
        if "flash" in m:
            return 20
        if "mini" in m or "haiku" in m:
            return 25
        if "20b" in m or "27b" in m or "7b" in m:
            return 30
        return 40

    if tier_id == "reasoning-tier":
        if "120b" in m or "o1" in m or "o3" in m:
            return 5
        if "2.5-pro" in m or "pro-latest" in m:
            return 10
        if "3.1-pro" in m or "pro" in m:
            return 15
        if "deep-research" in m or "reasoner" in m or "r1" in m:
            return 20
        if "3.8-flash" in m or "3.7-flash" in m:
            return 25
        return 35

    if tier_id == "coding-tier":
        if "coder" in m or "codestral" in m:
            return 5
        if "qwen" in m:
            return 10
        if "3.7-flash" in m or "3.8-flash" in m:
            return 15
        if "pro" in m or "sonnet" in m:
            return 20
        return 30

    if tier_id == "economy-tier":
        if "flash-lite" in m:
            return 5
        if "flash" in m:
            return 10
        if "20b" in m or "7b" in m or "8b" in m or "mini" in m:
            return 15
        return 25

    return 20


def is_worker_matching_tier(worker_or_model: Any, tier_id: str, provider: str | None = None) -> bool:
    """Check if a Worker instance or model name string matches the specified virtual tier."""
    if isinstance(worker_or_model, str):
        return tier_id in classify_model_into_tiers(worker_or_model, provider)

    if not getattr(worker_or_model, "enabled", True):
        return False
    m = getattr(worker_or_model, "model", "")
    p = None
    if "provider" in getattr(worker_or_model, "__dict__", {}):
        prov_obj = worker_or_model.__dict__.get("provider")
        p = getattr(prov_obj, "name", None) if prov_obj else None
    elif "/" in m:
        p = m.split("/")[0]

    caps = getattr(worker_or_model, "capabilities", None)
    return tier_id in classify_model_into_tiers(m, p, caps)


def build_dynamic_group_models(group_id: str, active_workers: list[Any] | None) -> list[str]:
    """Dynamically build the fallback model cascade for a virtual tier using active connected workers.

    Guarantees that connected models are listed at the top, and unconfigured providers
    (e.g. Cerebras with zero keys) never pollute the cascade with phantom 'Not connected' items.
    """
    if not active_workers:
        base_group = BUILTIN_MODEL_GROUPS.get(group_id)
        return list(base_group.models) if base_group else []

    # Identify all active workers matching this tier
    tier_workers = [w for w in active_workers if is_worker_matching_tier(w, group_id)]

    if tier_workers:
        # Group by model identifier
        model_counts: dict[str, int] = {}
        model_providers: dict[str, str] = {}
        for w in tier_workers:
            m = w.model
            model_counts[m] = model_counts.get(m, 0) + 1
            if getattr(w, "provider", None):
                model_providers[m] = w.provider.name

        # Sort models by tier priority first, then worker count, then name
        sorted_models = sorted(
            model_counts.keys(),
            key=lambda m: (
                get_tier_model_priority(m, group_id, model_providers.get(m)),
                -model_counts[m],
                m,
            ),
        )
        return sorted_models[:10]

    # Fallback to base models if no active workers match this tier
    base_group = BUILTIN_MODEL_GROUPS.get(group_id)
    return list(base_group.models) if base_group else []


def normalize_group_id(name: str) -> str | None:
    """Normalize model string to a known virtual model group ID if applicable."""
    cleaned = (name or "").strip().lower()
    if cleaned in BUILTIN_MODEL_GROUPS:
        return cleaned
    return ALIAS_MAP.get(cleaned)


def is_virtual_group(name: str) -> bool:
    """Check if the requested model name is a virtual model group or alias."""
    return normalize_group_id(name) is not None


def get_group(name: str, active_workers: list[Any] | None = None) -> ModelGroup | None:
    """Retrieve virtual model group definition by name or alias, dynamically populated if workers are provided."""
    norm = normalize_group_id(name)
    if not norm:
        return None
    base = BUILTIN_MODEL_GROUPS.get(norm)
    if not base:
        return None

    if active_workers:
        dynamic_models = build_dynamic_group_models(norm, active_workers)
        return ModelGroup(
            id=base.id,
            name=base.name,
            description=base.description,
            default_policy=base.default_policy,
            models=dynamic_models,
        )
    return base


def list_virtual_groups(active_workers: list[Any] | None = None) -> list[dict[str, Any]]:
    """Return all virtual model groups with dynamically resolved member models and active worker counts."""
    res = []
    for g in BUILTIN_MODEL_GROUPS.values():
        dynamic_models = build_dynamic_group_models(g.id, active_workers)
        active_count = 0
        if active_workers:
            active_count = sum(
                1 for w in active_workers
                if getattr(w, "enabled", True) and (
                    model_matches_group(getattr(w, "model", ""), dynamic_models)
                    or is_worker_matching_tier(w, g.id)
                )
            )
        res.append({
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "default_policy": g.default_policy,
            "models": dynamic_models,
            "active_workers_count": active_count,
        })
    return res


def expand_group_models(models: list[str]) -> list[str]:
    """Expand list of models to include both provider-prefixed and bare model identifiers."""
    expanded: list[str] = []
    seen: set[str] = set()
    for m in models:
        clean = (m or "").strip().lower()
        if clean and clean not in seen:
            expanded.append(clean)
            seen.add(clean)
        if "/" in clean:
            bare = clean.split("/", 1)[1]
            if bare not in seen:
                expanded.append(bare)
                seen.add(bare)
    return expanded


def model_matches_group(worker_model: str, group_models: list[str], provider_name: str | None = None, group_id: str | None = None) -> bool:
    """Check if worker model matches any model in group, handling prefixes, provider names, and autonomous tier classification."""
    clean_w = (worker_model or "").strip().lower()
    variants = {clean_w}
    if "/" in clean_w:
        variants.add(clean_w.split("/", 1)[1])
    if provider_name:
        p = provider_name.strip().lower()
        variants.add(f"{p}/{clean_w}")
        if "/" in clean_w:
            variants.add(f"{p}/{clean_w.split('/', 1)[1]}")

    expanded_targets = set(expand_group_models(group_models))
    if not variants.isdisjoint(expanded_targets):
        return True

    if group_id:
        norm_gid = normalize_group_id(group_id)
        if norm_gid and norm_gid in classify_model_into_tiers(worker_model, provider_name):
            return True

    return False
