"""Virtual Model Groups, Aliasing, and Fallback Cascades for WRAP AI Gateway.

Enables clients to route requests using virtual aliases (e.g. 'fast-tier', 'economy-tier',
'reasoning-tier', 'coding-tier') across heterogeneous physical workers with transparent failover.
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


BUILTIN_MODEL_GROUPS: dict[str, ModelGroup] = {
    "fast-tier": ModelGroup(
        id="fast-tier",
        name="Fast LPU & Flash Tier",
        description="Ultra-low TTFT and high-throughput streaming inference across Groq and Gemini Flash.",
        default_policy="latency_optimized",
        models=[
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "qwen/qwen3.8-27b",
            "cerebras/llama-3.3-70b",
            "groq/llama-3.3-70b-versatile",
            "groq/llama-3.1-8b-instant",
            "gemini-2.0-flash",
        ],
    ),
    "reasoning-tier": ModelGroup(
        id="reasoning-tier",
        name="Frontier Reasoning Tier",
        description="Deep reasoning, complex logic, and high benchmark capability.",
        default_policy="quality_first",
        models=[
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-2.5-pro",
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "gemini-2.0-flash-thinking-exp-01-21",
            "gemini-1.5-pro",
            "qwen/qwen-2.5-coder-32b-instruct",
            "gemini-2.0-flash",
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
            "gemini-3.5-flash",
            "qwen/qwen3.8-27b",
            "groq/llama-3.1-8b-instant",
            "gemini-1.5-flash-8b",
            "gemini-1.5-flash",
        ],
    ),
    "coding-tier": ModelGroup(
        id="coding-tier",
        name="Code & Synthesis Tier",
        description="Syntax, code-completion, and multi-step tool execution optimized models.",
        default_policy="quality_first",
        models=[
            "gemini-3.7-flash",
            "qwen/qwen3.8-27b",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-flash-lite-latest",
            "qwen/qwen-2.5-coder-32b-instruct",
            "groq/llama-3.3-70b-versatile",
            "gemini-2.0-flash",
        ],
    ),
    "ensemble-consensus": ModelGroup(
        id="ensemble-consensus",
        name="Dual-Model Ensemble Consensus Tier",
        description="High-speed primary generation verified concurrently by deep reasoning model for frontier accuracy at $0 cost.",
        default_policy="quality_first",
        models=[
            "gemini-3.7-flash",
            "qwen/qwen3.8-27b",
            "gemini-3.6-flash",
            "gemini-flash-lite-latest",
            "groq/llama-3.3-70b-versatile",
            "gemini-2.0-flash",
            "cerebras/llama-3.3-70b",
            "qwen/qwen-2.5-coder-32b-instruct",
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


def normalize_group_id(name: str) -> str | None:
    """Normalize model string to a known virtual model group ID if applicable."""
    cleaned = (name or "").strip().lower()
    if cleaned in BUILTIN_MODEL_GROUPS:
        return cleaned
    return ALIAS_MAP.get(cleaned)


def is_virtual_group(name: str) -> bool:
    """Check if the requested model name is a virtual model group or alias."""
    return normalize_group_id(name) is not None


def get_group(name: str) -> ModelGroup | None:
    """Retrieve virtual model group definition by name or alias."""
    norm = normalize_group_id(name)
    if not norm:
        return None
    return BUILTIN_MODEL_GROUPS.get(norm)


def list_virtual_groups() -> list[dict[str, Any]]:
    """Return all configured virtual model groups."""
    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "default_policy": g.default_policy,
            "models": list(g.models),
        }
        for g in BUILTIN_MODEL_GROUPS.values()
    ]


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


def model_matches_group(worker_model: str, group_models: list[str], provider_name: str | None = None) -> bool:
    """Check if worker model matches any model in group, handling prefixes and provider names."""
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
    return not variants.isdisjoint(expanded_targets)
