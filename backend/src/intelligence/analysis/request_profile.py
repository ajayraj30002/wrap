"""RequestProfile — stable internal representation of an incoming request.

Raw features are extracted from the ChatCompletionRequest, then normalized
into bounded [0,1] signals that the routing pipeline consumes. This
separation allows raw features to expand over time while the routing
engine consumes a smaller, stable normalized representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawFeatures:
    """Directly observable features from the request payload."""

    # Input / context
    input_tokens: int = 0
    estimated_output_tokens: int | None = None
    context_length: int = 0
    message_count: int = 0
    system_message_present: bool = False
    longest_message_tokens: int = 0
    conversational_depth: int = 0  # number of assistant messages

    # Content characteristics (ratios ∈ [0,1])
    code_ratio: float = 0.0
    json_ratio: float = 0.0
    natural_language_ratio: float = 1.0
    question_count: int = 0
    instruction_count: int = 0
    has_long_context: bool = False
    has_multiple_constraints: bool = False

    # API characteristics
    requested_model: str = "auto"
    is_auto_model: bool = True
    streaming: bool = False
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    has_tool_requirement: bool = False
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class RequestProfile:
    """Normalized request representation consumed by the routing pipeline.

    All normalized signals are bounded to [0, 1] where 1.0 means the
    highest demand / sensitivity for that dimension.
    """

    request_id: str

    # Original request info
    model_requested: str = "auto"
    is_auto_model: bool = True
    streaming: bool = False

    # Raw features (available for inspection / diagnostics)
    raw: RawFeatures = field(default_factory=RawFeatures)

    # Normalized signals ∈ [0, 1]
    reasoning_demand: float = 0.5
    coding_demand: float = 0.0
    context_demand: float = 0.0
    quality_requirement: float = 0.5
    latency_sensitivity: float = 0.5
    output_complexity: float = 0.5
    structured_output_need: float = 0.0
    tool_requirement: float = 0.0
    factuality_requirement: float = 0.5

    # Derived complexity ∈ [0, 1]
    complexity: float = 0.5
