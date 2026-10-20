"""
Model Pricing, Commercial Economics, and Autonomous Routing Cost Analytics Engine.

Provides exact token pricing per model, provider-level cost calculations,
commercial market equivalent benchmarking (Industry-Standard Pricing Index),
and autonomous free-routing savings computations.
"""

from dataclasses import dataclass
from typing import Any

# Standard benchmark baselines
FRONTIER_BENCHMARK_INPUT_PER_M = 2.50    # $2.50 / 1M prompt tokens (GPT-4o baseline)
FRONTIER_BENCHMARK_OUTPUT_PER_M = 10.00  # $10.00 / 1M completion tokens (GPT-4o baseline)

FAST_BENCHMARK_INPUT_PER_M = 0.15        # $0.15 / 1M prompt tokens (GPT-4o-mini baseline)
FAST_BENCHMARK_OUTPUT_PER_M = 0.60       # $0.60 / 1M completion tokens (GPT-4o-mini baseline)

REASONING_BENCHMARK_INPUT_PER_M = 15.00  # $15.00 / 1M prompt tokens (o1 baseline)
REASONING_BENCHMARK_OUTPUT_PER_M = 60.00 # $60.00 / 1M completion tokens (o1 baseline)


@dataclass(frozen=True)
class ModelPriceSpec:
    input_cost_per_m: float       # Direct provider list price in USD per 1M input tokens
    output_cost_per_m: float      # Direct provider list price in USD per 1M output tokens
    provider: str
    is_free_tier: bool            # True if accessible via developer free tier in WRAP
    benchmark_model: str          # Commercial market equivalent model (e.g. "GPT-4o")
    benchmark_input_per_m: float  # Equivalent commercial input rate per 1M tokens
    benchmark_output_per_m: float # Equivalent commercial output rate per 1M tokens


# Comprehensive curated model pricing database (Industry Market Standard)
MODEL_PRICING_CATALOG: dict[str, ModelPriceSpec] = {
    # -------------------------------------------------------------
    # OpenAI Models
    # -------------------------------------------------------------
    "gpt-4o": ModelPriceSpec(2.50, 10.00, "openai", False, "GPT-4o", 2.50, 10.00),
    "gpt-4o-2024-08-06": ModelPriceSpec(2.50, 10.00, "openai", False, "GPT-4o", 2.50, 10.00),
    "gpt-4o-2024-05-13": ModelPriceSpec(5.00, 15.00, "openai", False, "GPT-4o (Legacy)", 5.00, 15.00),
    "gpt-4o-mini": ModelPriceSpec(0.15, 0.60, "openai", False, "GPT-4o-mini", 0.15, 0.60),
    "gpt-4o-mini-2024-07-18": ModelPriceSpec(0.15, 0.60, "openai", False, "GPT-4o-mini", 0.15, 0.60),
    "o1": ModelPriceSpec(15.00, 60.00, "openai", False, "OpenAI o1", 15.00, 60.00),
    "o1-2024-12-17": ModelPriceSpec(15.00, 60.00, "openai", False, "OpenAI o1", 15.00, 60.00),
    "o1-mini": ModelPriceSpec(3.00, 12.00, "openai", False, "OpenAI o1-mini", 3.00, 12.00),
    "o1-mini-2024-09-12": ModelPriceSpec(3.00, 12.00, "openai", False, "OpenAI o1-mini", 3.00, 12.00),
    "o1-preview": ModelPriceSpec(15.00, 60.00, "openai", False, "OpenAI o1-preview", 15.00, 60.00),
    "o3-mini": ModelPriceSpec(1.10, 4.40, "openai", False, "OpenAI o3-mini", 1.10, 4.40),
    "gpt-4-turbo": ModelPriceSpec(10.00, 30.00, "openai", False, "GPT-4 Turbo", 10.00, 30.00),
    "gpt-4-turbo-2024-04-09": ModelPriceSpec(10.00, 30.00, "openai", False, "GPT-4 Turbo", 10.00, 30.00),
    "gpt-3.5-turbo": ModelPriceSpec(0.50, 1.50, "openai", False, "GPT-3.5 Turbo", 0.50, 1.50),

    # -------------------------------------------------------------
    # Anthropic Models
    # -------------------------------------------------------------
    "claude-3-5-sonnet": ModelPriceSpec(3.00, 15.00, "anthropic", False, "Claude 3.5 Sonnet", 3.00, 15.00),
    "claude-3-5-sonnet-20241022": ModelPriceSpec(3.00, 15.00, "anthropic", False, "Claude 3.5 Sonnet", 3.00, 15.00),
    "claude-3-5-sonnet-latest": ModelPriceSpec(3.00, 15.00, "anthropic", False, "Claude 3.5 Sonnet", 3.00, 15.00),
    "claude-3-5-haiku": ModelPriceSpec(0.80, 4.00, "anthropic", False, "Claude 3.5 Haiku", 0.80, 4.00),
    "claude-3-5-haiku-20241022": ModelPriceSpec(0.80, 4.00, "anthropic", False, "Claude 3.5 Haiku", 0.80, 4.00),
    "claude-3-5-haiku-latest": ModelPriceSpec(0.80, 4.00, "anthropic", False, "Claude 3.5 Haiku", 0.80, 4.00),
    "claude-3-opus": ModelPriceSpec(15.00, 75.00, "anthropic", False, "Claude 3 Opus", 15.00, 75.00),
    "claude-3-opus-20240229": ModelPriceSpec(15.00, 75.00, "anthropic", False, "Claude 3 Opus", 15.00, 75.00),
    "claude-3-opus-latest": ModelPriceSpec(15.00, 75.00, "anthropic", False, "Claude 3 Opus", 15.00, 75.00),
    "claude-3-haiku": ModelPriceSpec(0.25, 1.25, "anthropic", False, "Claude 3 Haiku", 0.25, 1.25),

    # -------------------------------------------------------------
    # Google Gemini Models
    # -------------------------------------------------------------
    "gemini-2.5-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-2.0-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-2.5-pro": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o", 2.50, 10.00),
    "gemini-2.0-pro": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o", 2.50, 10.00),
    "gemini-1.5-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-1.5-flash-latest": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-1.5-pro": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o", 2.50, 10.00),
    "gemini-1.5-pro-latest": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o", 2.50, 10.00),
    "gemini-flash-lite-latest": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-2.0-flash-lite": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-3.5-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-3.6-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-3.7-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-3.8-flash": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),
    "gemini-flash-latest": ModelPriceSpec(0.00, 0.00, "gemini", True, "GPT-4o-mini", 0.15, 0.60),

    # -------------------------------------------------------------
    # Groq Models
    # -------------------------------------------------------------
    "llama-3.3-70b-versatile": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o", 2.50, 10.00),
    "llama-3.1-70b-versatile": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o", 2.50, 10.00),
    "llama-3.1-8b-instant": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o-mini", 0.15, 0.60),
    "qwen/qwen3.8-27b": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o", 2.50, 10.00),
    "qwen3.8-27b": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o", 2.50, 10.00),
    "qwen/qwen-2.5-32b": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o", 2.50, 10.00),
    "compound-mini": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o-mini", 0.15, 0.60),
    "groq/compound-mini": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o-mini", 0.15, 0.60),
    "mixtral-8x7b-32768": ModelPriceSpec(0.00, 0.00, "groq", True, "Mixtral 8x7B", 0.24, 0.24),
    "gemma2-9b-it": ModelPriceSpec(0.00, 0.00, "groq", True, "Gemma 2 9B", 0.20, 0.20),
    "fast-model": ModelPriceSpec(0.00, 0.00, "groq", True, "GPT-4o-mini", 0.15, 0.60),

    # -------------------------------------------------------------
    # DeepSeek Models
    # -------------------------------------------------------------
    "deepseek-chat": ModelPriceSpec(0.14, 0.28, "deepseek", False, "DeepSeek-V3", 0.14, 0.28),
    "deepseek-v3": ModelPriceSpec(0.14, 0.28, "deepseek", False, "DeepSeek-V3", 0.14, 0.28),
    "deepseek-reasoner": ModelPriceSpec(0.55, 2.19, "deepseek", False, "DeepSeek-R1", 0.55, 2.19),
    "deepseek-r1": ModelPriceSpec(0.55, 2.19, "deepseek", False, "DeepSeek-R1", 0.55, 2.19),

    # -------------------------------------------------------------
    # Mistral AI Models
    # -------------------------------------------------------------
    "mistral-large-latest": ModelPriceSpec(2.00, 6.00, "mistral", False, "Mistral Large", 2.00, 6.00),
    "mistral-large": ModelPriceSpec(2.00, 6.00, "mistral", False, "Mistral Large", 2.00, 6.00),
    "mistral-small-latest": ModelPriceSpec(0.20, 0.60, "mistral", False, "Mistral Small", 0.20, 0.60),
    "codestral-latest": ModelPriceSpec(0.30, 0.90, "mistral", False, "Codestral", 0.30, 0.90),
    "ministral-8b-latest": ModelPriceSpec(0.10, 0.10, "mistral", False, "Ministral 8B", 0.10, 0.10),

    # -------------------------------------------------------------
    # Cerebras Models
    # -------------------------------------------------------------
    "llama3.1-8b": ModelPriceSpec(0.00, 0.00, "cerebras", True, "GPT-4o-mini", 0.15, 0.60),
    "llama3.1-70b": ModelPriceSpec(0.00, 0.00, "cerebras", True, "GPT-4o", 2.50, 10.00),

    # -------------------------------------------------------------
    # xAI Models
    # -------------------------------------------------------------
    "grok-2-latest": ModelPriceSpec(2.00, 10.00, "xai", False, "Grok 2", 2.00, 10.00),
    "grok-2": ModelPriceSpec(2.00, 10.00, "xai", False, "Grok 2", 2.00, 10.00),
    "grok-beta": ModelPriceSpec(5.00, 15.00, "xai", False, "Grok Beta", 5.00, 15.00),

    # -------------------------------------------------------------
    # Perplexity Models
    # -------------------------------------------------------------
    "sonar-pro": ModelPriceSpec(3.00, 15.00, "perplexity", False, "Sonar Pro", 3.00, 15.00),
    "sonar": ModelPriceSpec(1.00, 1.00, "perplexity", False, "Sonar", 1.00, 1.00),

    # -------------------------------------------------------------
    # Cohere Models
    # -------------------------------------------------------------
    "command-r-plus": ModelPriceSpec(0.00, 0.00, "cohere", True, "Command R+", 2.50, 10.00),
    "command-r": ModelPriceSpec(0.00, 0.00, "cohere", True, "Command R", 0.15, 0.60),

    # -------------------------------------------------------------
    # SambaNova Models
    # -------------------------------------------------------------
    "sambanova/llama-3.1-70b": ModelPriceSpec(0.00, 0.00, "sambanova", True, "GPT-4o", 2.50, 10.00),
    "sambanova/llama-3.1-405b": ModelPriceSpec(0.00, 0.00, "sambanova", True, "GPT-4o", 5.00, 10.00),
}

# Providers whose developer API keys are operated under free quotas in WRAP
FREE_TIER_PROVIDERS = {"groq", "gemini", "cerebras", "sambanova", "cohere"}


def normalize_model_key(model: str | None) -> str:
    """Normalize model identifier for consistent catalog lookups."""
    if not model:
        return "auto"
    m = model.strip().lower()
    # Strip common provider prefixes
    for prefix in ["openai/", "anthropic/", "google/", "groq/", "cerebras/", "deepseek/", "mistral/", "xai/"]:
        if m.startswith(prefix):
            m = m[len(prefix):]
            break
    return m


def is_free_tier(provider: str | None, model: str | None = None) -> bool:
    """Check if the provider/model is routed through a free developer tier."""
    if not provider:
        return True
    p = provider.strip().lower()
    if p in FREE_TIER_PROVIDERS:
        return True
    norm_m = normalize_model_key(model)
    spec = MODEL_PRICING_CATALOG.get(norm_m)
    if spec and spec.is_free_tier:
        return True
    return False


def is_worker_or_credential_paid(worker: Any | None, provider: str | None = None) -> bool:
    """Determine if a worker/credential is operating as a paid commercial key vs free tier."""
    if worker:
        cred = worker.__dict__.get("credential") if hasattr(worker, "__dict__") else None
        if cred:
            meta = getattr(cred, "credential_metadata", None) or {}
            if "is_paid" in meta:
                return bool(meta["is_paid"])
        prov = worker.__dict__.get("provider") if hasattr(worker, "__dict__") else None
        if prov and getattr(prov, "name", None):
            provider = prov.name

    p = (provider or "").strip().lower()
    if p in {"openai", "anthropic", "mistral", "xai", "deepseek"}:
        return True
    if p in FREE_TIER_PROVIDERS:
        return False
    return False


def get_model_price_spec(
    model: str | None,
    provider: str | None = None,
    is_paid: bool | None = None,
) -> ModelPriceSpec:
    """Look up exact model pricing spec from catalog or derive using intelligent heuristics."""
    norm_m = normalize_model_key(model)
    prov = (provider or "groq").strip().lower()

    # Determine free vs paid
    if is_paid is not None:
        effective_is_free = not is_paid
    else:
        effective_is_free = prov in FREE_TIER_PROVIDERS

    # 1. Exact catalog match
    if norm_m in MODEL_PRICING_CATALOG:
        spec = MODEL_PRICING_CATALOG[norm_m]
        if effective_is_free:
            return ModelPriceSpec(
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                provider=prov,
                is_free_tier=True,
                benchmark_model=spec.benchmark_model,
                benchmark_input_per_m=spec.benchmark_input_per_m,
                benchmark_output_per_m=spec.benchmark_output_per_m,
            )
        elif spec.input_cost_per_m == 0.0 and is_paid:
            # Paid key on a model cataloged as free (e.g. Gemini Paid): use commercial benchmark rates
            return ModelPriceSpec(
                input_cost_per_m=spec.benchmark_input_per_m,
                output_cost_per_m=spec.benchmark_output_per_m,
                provider=prov,
                is_free_tier=False,
                benchmark_model=spec.benchmark_model,
                benchmark_input_per_m=spec.benchmark_input_per_m,
                benchmark_output_per_m=spec.benchmark_output_per_m,
            )
        return spec

    # 2. Check compound/full name (e.g. "qwen/qwen3.8-27b")
    if model and model.lower() in MODEL_PRICING_CATALOG:
        spec = MODEL_PRICING_CATALOG[model.lower()]
        if effective_is_free:
            return ModelPriceSpec(
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                provider=prov,
                is_free_tier=True,
                benchmark_model=spec.benchmark_model,
                benchmark_input_per_m=spec.benchmark_input_per_m,
                benchmark_output_per_m=spec.benchmark_output_per_m,
            )
        return spec

    # 3. Intelligent heuristic inference based on model characteristics
    if any(k in norm_m for k in ["r1", "reasoner", "o1", "o3"]):
        # Reasoning class
        return ModelPriceSpec(
            input_cost_per_m=0.0 if effective_is_free else REASONING_BENCHMARK_INPUT_PER_M,
            output_cost_per_m=0.0 if effective_is_free else REASONING_BENCHMARK_OUTPUT_PER_M,
            provider=prov,
            is_free_tier=effective_is_free,
            benchmark_model="OpenAI o1 / DeepSeek-R1",
            benchmark_input_per_m=REASONING_BENCHMARK_INPUT_PER_M,
            benchmark_output_per_m=REASONING_BENCHMARK_OUTPUT_PER_M,
        )
    elif any(k in norm_m for k in ["mini", "haiku", "8b", "lite", "small", "flash", "fast"]):
        # Fast / Lightweight class
        return ModelPriceSpec(
            input_cost_per_m=0.0 if effective_is_free else FAST_BENCHMARK_INPUT_PER_M,
            output_cost_per_m=0.0 if effective_is_free else FAST_BENCHMARK_OUTPUT_PER_M,
            provider=prov,
            is_free_tier=effective_is_free,
            benchmark_model="GPT-4o-mini",
            benchmark_input_per_m=FAST_BENCHMARK_INPUT_PER_M,
            benchmark_output_per_m=FAST_BENCHMARK_OUTPUT_PER_M,
        )
    else:
        # Standard Frontier class
        return ModelPriceSpec(
            input_cost_per_m=0.0 if effective_is_free else FRONTIER_BENCHMARK_INPUT_PER_M,
            output_cost_per_m=0.0 if effective_is_free else FRONTIER_BENCHMARK_OUTPUT_PER_M,
            provider=prov,
            is_free_tier=effective_is_free,
            benchmark_model="GPT-4o / Claude 3.5 Sonnet",
            benchmark_input_per_m=FRONTIER_BENCHMARK_INPUT_PER_M,
            benchmark_output_per_m=FRONTIER_BENCHMARK_OUTPUT_PER_M,
        )


def calculate_request_economics(
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    provider: str | None = None,
    model: str | None = None,
    is_paid: bool | None = None,
    is_cache_hit: bool = False,
) -> dict[str, Any]:
    """
    Calculate precise token economics for a request:
    - actual_cost_usd: Out-of-pocket billed cost ($0.00 for free tier keys, or exact provider rate)
    - commercial_equivalent_usd: Commercial benchmark price (GPT-4o / Claude 3.5 Sonnet / etc.)
    - saved_usd: Net savings delivered by WRAP
    - is_free_tier: Whether free tier routing was active
    - is_cache_hit: Whether request was served from cache
    - unit_rates: Specific $/1M rates applied
    """
    inp = max(0, input_tokens or 0)
    out = max(0, output_tokens or 0)
    tot = max(0, total_tokens or (inp + out))

    # If only total tokens is known, estimate 30% prompt, 70% completion
    if inp == 0 and out == 0 and tot > 0:
        inp = int(tot * 0.3)
        out = tot - inp

    spec = get_model_price_spec(model, provider, is_paid=is_paid)

    # Commercial benchmark equivalent
    commercial_equivalent = (inp * (spec.benchmark_input_per_m / 1_000_000)) + (
        out * (spec.benchmark_output_per_m / 1_000_000)
    )

    if is_cache_hit:
        # Cache hit: $0.00 out of pocket to any provider; 100% of commercial value saved
        actual_cost = 0.0
        saved = commercial_equivalent
        effective_free = True
    elif is_paid is True or (is_paid is None and not spec.is_free_tier):
        # Paid commercial key: real dollars billed out of pocket
        actual_cost = (inp * (spec.input_cost_per_m / 1_000_000)) + (out * (spec.output_cost_per_m / 1_000_000))
        saved = max(0.0, commercial_equivalent - actual_cost)
        effective_free = False
    else:
        # Free tier key: $0 out of pocket; user saved the full commercial market equivalent
        actual_cost = 0.0
        saved = commercial_equivalent
        effective_free = True

    return {
        "actual_cost_usd": round(actual_cost, 6),
        "commercial_equivalent_usd": round(commercial_equivalent, 6),
        "saved_usd": round(saved, 6),
        "is_free_tier": effective_free,
        "is_cache_hit": is_cache_hit,
        "is_paid": not effective_free,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": tot,
        "model_identified": model or "auto",
        "benchmark_model": spec.benchmark_model,
        "benchmark": spec.benchmark_model,
        "benchmark_rates": {
            "input_per_m": spec.benchmark_input_per_m,
            "output_per_m": spec.benchmark_output_per_m,
        },
        "actual_rates": {
            "input_per_m": spec.input_cost_per_m,
            "output_per_m": spec.output_cost_per_m,
        },
    }
