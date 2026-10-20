"""FeatureExtractor — extracts raw features from ChatCompletionRequest.

This module performs cheap, deterministic feature extraction. It never
makes network calls or database queries. All heuristics are documented.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.intelligence.analysis.request_profile import RawFeatures


# Rough token estimation: ~4 chars per token for English text.
_CHARS_PER_TOKEN = 4

# Code indicators — simple heuristics, not a full parser
_CODE_PATTERNS = re.compile(
    r"```|def\s+\w+|class\s+\w+|import\s+\w+|function\s+\w+|"
    r"const\s+\w+|let\s+\w+|var\s+\w+|=>|&&|\|\||"
    r"#include|public\s+class|SELECT\s+|CREATE\s+TABLE",
    re.IGNORECASE,
)

# Question indicators
_QUESTION_PATTERN = re.compile(r"\?\s*$|\bwhat\b|\bhow\b|\bwhy\b|\bcan\b|\bwould\b|\bcould\b", re.IGNORECASE | re.MULTILINE)

# Instruction indicators
_INSTRUCTION_PATTERN = re.compile(
    r"\bwrite\b|\bcreate\b|\bgenerate\b|\bbuild\b|\bimplement\b|\bdesign\b|\brefactor\b|\bfix\b|\boptimize\b",
    re.IGNORECASE,
)

# JSON structure indicators
_JSON_PATTERN = re.compile(r'\{[^{}]*"[^"]*"\s*:', re.DOTALL)


def extract_features(
    model: str,
    messages: list[dict[str, Any]],
    stream: bool = False,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    **kwargs: Any,
) -> RawFeatures:
    """Extract raw features from request parameters.

    All extraction is synchronous and cheap (string scanning only).
    """
    is_auto = model.lower() in ("auto", "wrap-auto", "default", "wrap", "", "intelligent", "router")

    # Flatten all message content into strings
    all_text = ""
    system_present = False
    longest_msg_len = 0
    assistant_count = 0

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        text = content if isinstance(content, str) else json.dumps(content)

        if role == "system":
            system_present = True
        if role == "assistant":
            assistant_count += 1

        msg_len = len(text)
        if msg_len > longest_msg_len:
            longest_msg_len = msg_len

        all_text += text + "\n"

    tool_chars = 0
    if tools:
        try:
            tool_chars = len(json.dumps(tools))
        except Exception:
            tool_chars = len(str(tools))

    total_chars = len(all_text) + tool_chars
    input_tokens = max(1, total_chars // _CHARS_PER_TOKEN)
    longest_msg_tokens = longest_msg_len // _CHARS_PER_TOKEN

    # Content ratios
    code_matches = len(_CODE_PATTERNS.findall(all_text))
    code_ratio = min(1.0, code_matches / max(1, total_chars // 200))

    json_matches = len(_JSON_PATTERN.findall(all_text))
    json_ratio = min(1.0, json_matches / max(1, len(messages)))

    nl_ratio = max(0.0, 1.0 - code_ratio - json_ratio)

    question_count = len(_QUESTION_PATTERN.findall(all_text))
    instruction_count = len(_INSTRUCTION_PATTERN.findall(all_text))

    # Context thresholds
    has_long_context = input_tokens > 4000
    has_multiple_constraints = instruction_count >= 3

    # Output estimation
    max_out = max_completion_tokens or max_tokens
    estimated_output = max_out if max_out else _estimate_output_tokens(input_tokens, code_ratio, instruction_count)

    has_tools = bool(tools and len(tools) > 0)

    return RawFeatures(
        input_tokens=input_tokens,
        estimated_output_tokens=estimated_output,
        context_length=input_tokens,
        message_count=len(messages),
        system_message_present=system_present,
        longest_message_tokens=longest_msg_tokens,
        conversational_depth=assistant_count,
        code_ratio=round(code_ratio, 4),
        json_ratio=round(json_ratio, 4),
        natural_language_ratio=round(nl_ratio, 4),
        question_count=question_count,
        instruction_count=instruction_count,
        has_long_context=has_long_context,
        has_multiple_constraints=has_multiple_constraints,
        requested_model=model,
        is_auto_model=is_auto,
        streaming=stream,
        response_format=response_format,
        tools=tools,
        has_tool_requirement=has_tools,
        max_output_tokens=max_out,
    )


def _estimate_output_tokens(input_tokens: int, code_ratio: float, instruction_count: int) -> int:
    """Rough heuristic for expected output length when max_tokens is not set.

    - Simple questions → short answers (~100-200 tokens)
    - Code generation → medium answers (~300-800 tokens)
    - Complex instructions → longer answers (~500-2000 tokens)
    """
    base = 200
    if code_ratio > 0.3:
        base = 500
    if instruction_count >= 3:
        base = max(base, 800)
    # Scale slightly with input length for context-heavy requests
    return min(4096, base + input_tokens // 10)
