"""RequestAnalyzer — builds a RequestProfile from a ChatCompletionRequest.

Pipeline: ChatCompletionRequest → FeatureExtractor → RawFeatures → normalize → RequestProfile

This is deterministic and cheap. No database or network calls.
"""

from __future__ import annotations

from src.intelligence.analysis.feature_extractor import extract_features
from src.intelligence.analysis.request_profile import RawFeatures, RequestProfile
from src.schemas.openai import ChatCompletionRequest


class RequestAnalyzer:
    """Analyzes incoming chat completion requests into routing-ready profiles."""

    def analyze(self, request: ChatCompletionRequest, *, request_id: str) -> RequestProfile:
        """Analyze a request and produce a normalized RequestProfile.

        This method is synchronous and deterministic.
        """
        raw = extract_features(
            model=request.model,
            messages=[msg.model_dump() for msg in request.messages],
            stream=request.stream,
            response_format=request.response_format,
            tools=request.tools,
            max_tokens=request.max_tokens,
            max_completion_tokens=request.max_completion_tokens,
        )
        return self._normalize(raw, request_id=request_id)

    def _normalize(self, raw: RawFeatures, *, request_id: str) -> RequestProfile:
        """Convert raw features into bounded normalized signals.

        Each signal ∈ [0, 1] where 1.0 = highest demand/sensitivity.
        Derivation documented inline.
        """
        # coding_demand: based on code ratio and instruction count
        #   code_ratio > 0.5 → high coding demand
        coding_demand = _clamp(raw.code_ratio * 1.5 + (0.2 if raw.instruction_count >= 2 else 0.0))

        # reasoning_demand: questions + complex instructions + conversational depth
        reasoning_demand = _clamp(
            0.3  # baseline
            + min(0.3, raw.question_count * 0.1)
            + min(0.2, raw.instruction_count * 0.05)
            + (0.1 if raw.conversational_depth > 2 else 0.0)
            + (0.1 if raw.has_multiple_constraints else 0.0)
        )

        # context_demand: proportion of context used relative to typical limits
        #   0 tokens → 0.0, 8k tokens → 0.5, 32k+ → 1.0
        context_demand = _clamp(raw.input_tokens / 32000)

        # quality_requirement: complex requests need better models
        quality_requirement = _clamp(
            0.3  # baseline
            + (0.2 if coding_demand > 0.5 else 0.0)
            + (0.2 if reasoning_demand > 0.6 else 0.0)
            + (0.15 if raw.has_long_context else 0.0)
            + (0.15 if raw.has_multiple_constraints else 0.0)
        )

        # latency_sensitivity: streaming requests are more latency-sensitive,
        #   short simple requests expect fast responses
        latency_sensitivity = _clamp(
            0.3  # baseline
            + (0.3 if raw.streaming else 0.0)
            + (0.2 if raw.input_tokens < 500 and raw.message_count <= 2 else 0.0)
            - (0.2 if raw.has_long_context else 0.0)  # long context = user expects it takes time
        )

        # output_complexity: expected output length and structured output
        est_output = raw.estimated_output_tokens or 200
        output_complexity = _clamp(est_output / 4096)

        # structured_output_need: response_format or JSON ratio
        structured_output_need = _clamp(
            (0.8 if raw.response_format else 0.0) + raw.json_ratio * 0.4
        )

        # tool_requirement: binary-ish based on tools presence
        tool_requirement = 1.0 if raw.has_tool_requirement else 0.0

        # factuality_requirement: questions and code requests need accuracy
        factuality_requirement = _clamp(
            0.3
            + min(0.3, raw.question_count * 0.15)
            + (0.2 if coding_demand > 0.3 else 0.0)
            + (0.1 if raw.system_message_present else 0.0)
        )

        # Overall complexity: weighted combination of demands
        complexity = _clamp(
            0.3 * coding_demand
            + 0.25 * reasoning_demand
            + 0.2 * context_demand
            + 0.15 * output_complexity
            + 0.1 * tool_requirement
        )

        return RequestProfile(
            request_id=request_id,
            model_requested=raw.requested_model,
            is_auto_model=raw.is_auto_model,
            streaming=raw.streaming,
            raw=raw,
            reasoning_demand=round(reasoning_demand, 4),
            coding_demand=round(coding_demand, 4),
            context_demand=round(context_demand, 4),
            quality_requirement=round(quality_requirement, 4),
            latency_sensitivity=round(latency_sensitivity, 4),
            output_complexity=round(output_complexity, 4),
            structured_output_need=round(structured_output_need, 4),
            tool_requirement=round(tool_requirement, 4),
            factuality_requirement=round(factuality_requirement, 4),
            complexity=round(complexity, 4),
        )


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))
