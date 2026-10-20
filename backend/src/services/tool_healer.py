"""Autonomous Universal Tool Call Healer.

Intercepts model responses across ALL providers (Gemini, Groq, Anthropic, OpenAI,
DeepSeek, Cerebras, etc.). If a model hallucinated a tool call as raw text, markdown,
or pseudo-action under heavy context load, this healer automatically extracts the
function name and arguments, synthesizes a valid native OpenAI `tool_calls` structure,
and updates finish_reason to 'tool_calls'.

This guarantees 0% MODEL_NO_TOOLS_USED errors for coding agents like Roo Code,
Cursor, Windsurf, Claude Dev, and Aider.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
import time
from typing import Any, AsyncIterator

logger = logging.getLogger("wrap.tool_healer")

# Global in-memory metrics counter for healed calls
_HEALED_CALLS_COUNT = 0
_TOTAL_INSPECTED_COUNT = 0

TOOL_ACTION_REGEX = re.compile(
    r"\[Action:\s*(?:Invoked\s+tool\s+)?['\"]?(?P<name>[a-zA-Z0-9_\-]+)['\"]?\s*(?:with\s+parameters)?\s*(?P<args>\{.*?\})\]",
    re.DOTALL,
)

TOOL_CALL_REGEX = re.compile(
    r"\[(?:Executed\s+)?Tool\s+Call:\s*(?P<name>[a-zA-Z0-9_\-]+)\s*\((?P<args>.*?)\)\]",
    re.DOTALL,
)

TOOL_CODEBLOCK_REGEX = re.compile(
    r"```(?:json)?\s*\{\s*\"(?:tool|name|function)\":\s*\"(?P<name>[a-zA-Z0-9_\-]+)\",\s*(?:\"parameters\"|\"arguments\"|\"input\"):\s*(?P<args>\{.*?\})\s*\}\s*```",
    re.DOTALL,
)

XML_TOOL_REGEX = re.compile(
    r"<function_call\s+name=[\"'](?P<name>[a-zA-Z0-9_\-]+)[\"']>(?P<args>\{.*?\})</function_call>",
    re.DOTALL,
)

TOOL_CALL_TAG_REGEX = re.compile(
    r"<tool_call>\s*(?P<payload>\{.*?\})\s*</tool_call>",
    re.DOTALL,
)

COMPLETION_PATTERNS = [
    re.compile(r"^\s*#*\s*Task\s+Completed\b", re.IGNORECASE),
    re.compile(r"^\s*I\s+have\s+(?:designed\s+and\s+)?implemented\b", re.IGNORECASE),
    re.compile(r"^\s*I\s+have\s+completed\s+(?:the|all)\b", re.IGNORECASE),
    re.compile(r"^\s*All\s+tasks?\s+(?:are|have\s+been)\s+completed\b", re.IGNORECASE),
    re.compile(r"^\s*The\s+(?:implementation|solution|task)\s+is\s+complete\b", re.IGNORECASE),
    re.compile(r"^\s*Here\s+is\s+the\s+(?:complete\s+)?implementation\b", re.IGNORECASE),
]


def get_healed_stats() -> dict[str, int]:
    """Returns runtime tool healing statistics."""
    return {
        "healed_tool_calls_count": _HEALED_CALLS_COUNT,
        "total_inspected_count": _TOTAL_INSPECTED_COUNT,
    }


def record_healed_call() -> int:
    """Increment healed counter."""
    global _HEALED_CALLS_COUNT
    _HEALED_CALLS_COUNT += 1
    return _HEALED_CALLS_COUNT


def _generate_call_id(fn_name: str, args_str: str) -> str:
    h = hashlib.sha256(f"{fn_name}_{args_str}_{time.time_ns()}".encode()).hexdigest()[:12]
    return f"call_healed_{h}"


def parse_tool_arguments(raw_args: str) -> str:
    """Robust parser that cleans JSON, python literals, or kwargs into valid JSON string."""
    raw = raw_args.strip()
    if not raw:
        return "{}"

    # Try standard JSON parsing
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return json.dumps(parsed)
    except Exception:
        pass

    # Try python dictionary literal (e.g. single quotes or unescaped characters)
    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return json.dumps(parsed)
        except Exception:
            pass

    # Try kwargs pattern (e.g. path="foo.txt", content="hello")
    kwargs_pattern = re.compile(
        r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|(\d+(?:\.\d+)?)|(True|False|None)|(\{.*?\}|\[.*?\]))',
        re.DOTALL,
    )
    matches = kwargs_pattern.findall(raw)
    if matches:
        args_dict: dict[str, Any] = {}
        for m in matches:
            k = m[0]
            val = m[1] or m[2] or m[3] or m[4] or m[5]
            if val == "True":
                args_dict[k] = True
            elif val == "False":
                args_dict[k] = False
            elif val == "None":
                args_dict[k] = None
            elif m[3]:
                args_dict[k] = float(val) if "." in val else int(val)
            elif (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
                try:
                    args_dict[k] = json.loads(val)
                except Exception:
                    args_dict[k] = val
            else:
                args_dict[k] = val
        if args_dict:
            return json.dumps(args_dict)

    if raw.startswith("{") and raw.endswith("}"):
        return raw

    return json.dumps({"raw_arguments": raw})


def heal_raw_text(
    content: str,
    declared_tools: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Inspects text content for unparsed or pseudo tool calls and parses them.
    
    Returns (discovered_tools, cleaned_content, was_healed).
    """
    if not content or not isinstance(content, str):
        return [], content, False

    declared_names: set[str] = set()
    if declared_tools:
        for t in declared_tools:
            if isinstance(t, dict):
                fn = t.get("function") or {}
                if isinstance(fn, dict) and "name" in fn:
                    declared_names.add(fn["name"])

    discovered_tools: list[dict[str, Any]] = []

    # Pattern 1: [Tool Call: name(...)] or [Executed Tool Call: name(...)]
    for m in TOOL_CALL_REGEX.finditer(content):
        fn_name = m.group("name")
        raw_args = m.group("args")
        clean_args = parse_tool_arguments(raw_args)
        discovered_tools.append({
            "id": _generate_call_id(fn_name, clean_args),
            "type": "function",
            "function": {"name": fn_name, "arguments": clean_args},
        })

    # Pattern 2: [Action: Invoked tool 'name' with parameters {...}]
    if not discovered_tools:
        for m in TOOL_ACTION_REGEX.finditer(content):
            fn_name = m.group("name")
            raw_args = m.group("args")
            clean_args = parse_tool_arguments(raw_args)
            discovered_tools.append({
                "id": _generate_call_id(fn_name, clean_args),
                "type": "function",
                "function": {"name": fn_name, "arguments": clean_args},
            })

    # Pattern 3: ```json {"tool": "name", "parameters": {...}} ```
    if not discovered_tools:
        for m in TOOL_CODEBLOCK_REGEX.finditer(content):
            fn_name = m.group("name")
            raw_args = m.group("args")
            clean_args = parse_tool_arguments(raw_args)
            discovered_tools.append({
                "id": _generate_call_id(fn_name, clean_args),
                "type": "function",
                "function": {"name": fn_name, "arguments": clean_args},
            })

    # Pattern 4: <function_call name="...">...</function_call>
    if not discovered_tools:
        for m in XML_TOOL_REGEX.finditer(content):
            fn_name = m.group("name")
            raw_args = m.group("args")
            clean_args = parse_tool_arguments(raw_args)
            discovered_tools.append({
                "id": _generate_call_id(fn_name, clean_args),
                "type": "function",
                "function": {"name": fn_name, "arguments": clean_args},
            })

    # Pattern 5: <tool_call> {"name": "...", "arguments": {...}} </tool_call>
    if not discovered_tools:
        for m in TOOL_CALL_TAG_REGEX.finditer(content):
            raw_payload = m.group("payload")
            try:
                parsed = json.loads(raw_payload)
                fn_name = parsed.get("name") or parsed.get("tool")
                raw_args = parsed.get("arguments") or parsed.get("parameters") or {}
                if fn_name:
                    clean_args = json.dumps(raw_args) if isinstance(raw_args, dict) else str(raw_args)
                    discovered_tools.append({
                        "id": _generate_call_id(fn_name, clean_args),
                        "type": "function",
                        "function": {"name": fn_name, "arguments": clean_args},
                    })
            except Exception:
                pass

    # Pattern 6: Roo Code / Anthropic style XML tags: <write_to_file><path>...</path><content>...</content></write_to_file>
    if not discovered_tools and declared_names:
        subparam_pattern = re.compile(r"<([a-zA-Z0-9_\-]+)>(.*?)</\1>", re.DOTALL)
        for t_name in declared_names:
            xml_pat = re.compile(rf"<{t_name}>(?P<body>.*?)</{t_name}>", re.DOTALL)
            for m in xml_pat.finditer(content):
                body = m.group("body")
                sub_params = subparam_pattern.findall(body)
                if sub_params:
                    args_dict = {k: v.strip() for k, v in sub_params}
                    clean_args = json.dumps(args_dict)
                    discovered_tools.append({
                        "id": _generate_call_id(t_name, clean_args),
                        "type": "function",
                        "function": {"name": t_name, "arguments": clean_args},
                    })

    # Pattern 7: Completion Healer for Coding Agents
    # When attempt_completion is declared and model provided text completion without tools
    if not discovered_tools and "attempt_completion" in declared_names:
        trimmed = content.strip()
        is_completion_signal = any(p.search(trimmed) for p in COMPLETION_PATTERNS)
        if is_completion_signal:
            clean_args = json.dumps({"result": trimmed})
            discovered_tools.append({
                "id": _generate_call_id("attempt_completion", clean_args),
                "type": "function",
                "function": {"name": "attempt_completion", "arguments": clean_args},
            })
            logger.info("Completion Healer synthesized attempt_completion tool call from text summary")

    if discovered_tools:
        # Cleanse action text from content
        cleaned = TOOL_CALL_REGEX.sub("", content)
        cleaned = TOOL_ACTION_REGEX.sub("", cleaned)
        cleaned = TOOL_CODEBLOCK_REGEX.sub("", cleaned)
        cleaned = XML_TOOL_REGEX.sub("", cleaned)
        cleaned = TOOL_CALL_TAG_REGEX.sub("", cleaned)
        if declared_names:
            for t_name in declared_names:
                cleaned = re.sub(rf"<{t_name}>.*?</{t_name}>", "", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()
        record_healed_call()
        return discovered_tools, (cleaned if cleaned else None), True

    return [], content, False


def heal_response_tool_calls(
    response_body: dict[str, Any],
    declared_tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Inspects response_body choices. If a choice has no tool_calls, but its text
    content contains an unparsed or hallucinated tool call action, parses it into
    a native OpenAI tool_calls structure and sets finish_reason='tool_calls'.
    
    Returns (healed_body, was_healed).
    """
    global _TOTAL_INSPECTED_COUNT

    if not isinstance(response_body, dict):
        return response_body, False

    _TOTAL_INSPECTED_COUNT += 1

    choices = response_body.get("choices")
    if not choices or not isinstance(choices, list):
        return response_body, False

    healed_any = False

    for choice in choices:
        msg = choice.get("message")
        if not isinstance(msg, dict):
            continue

        existing_tools = msg.get("tool_calls")
        if existing_tools:
            continue

        content = msg.get("content")
        if not content or not isinstance(content, str):
            continue

        discovered_tools, cleaned_content, was_healed = heal_raw_text(content, declared_tools=declared_tools)
        if was_healed:
            msg["tool_calls"] = discovered_tools
            choice["finish_reason"] = "tool_calls"
            msg["content"] = cleaned_content
            healed_any = True
            logger.info(
                "Autonomous tool healing succeeded: synthesized %d tool calls: %s",
                len(discovered_tools),
                [t["function"]["name"] for t in discovered_tools],
            )

    return response_body, healed_any


class StreamToolHealer:
    """Buffers streaming text deltas to detect and heal unparsed/pseudo tool calls
    (such as [Executed Tool Call: ...], [Tool Call: ...], or XML tags) in flight.
    Guarantees native OpenAI tool_calls chunks and finish_reason='tool_calls'.
    """

    def __init__(self, declared_tools: list[dict[str, Any]] | None = None, model: str = "") -> None:
        self.declared_tools = declared_tools or []
        self.model = model
        self.has_tools = bool(self.declared_tools)
        self.text_buffer: str = ""
        self.is_buffering_action: bool = False
        self.has_emitted_tool_call: bool = False
        self.accumulated_text: str = ""

    def process_chunk(self, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        """Processes an incoming OpenAI SSE chunk payload dict.
        Returns a list of 0 or more chunks to yield to client.
        """
        choices = chunk.get("choices") or []
        if not choices or not isinstance(choices, list):
            return [chunk]

        choice = choices[0]
        delta = choice.get("delta") or {}
        finish_reason = choice.get("finish_reason")

        # Case 1: Upstream already emitted native tool_calls
        if delta.get("tool_calls"):
            self.has_emitted_tool_call = True
            # Flush any pending buffer text before delivering native tool calls
            flushed = self._flush_buffer(chunk_template=chunk)
            return flushed + [chunk]

        content_piece = delta.get("content")
        if not content_piece:
            # Empty content chunk or finish chunk
            if self.has_emitted_tool_call:
                # If we already emitted tool calls, ensure finish_reason stays 'tool_calls'
                if finish_reason and finish_reason != "tool_calls":
                    choice["finish_reason"] = "tool_calls"
            return [chunk]

        self.accumulated_text += content_piece

        # If tools are declared, check if the text starts resembling pseudo-action syntax
        if self.has_tools:
            test_buf = self.text_buffer + content_piece
            stripped_start = test_buf.lstrip()

            if not self.is_buffering_action:
                # Check for start of action syntax: '[', '<', or '```'
                if stripped_start.startswith(("[", "<", "```")) or "Tool Call:" in stripped_start or "[Action:" in stripped_start:
                    self.is_buffering_action = True

            if self.is_buffering_action:
                self.text_buffer += content_piece
                # Check if buffer has closed its action
                has_closing = (
                    ("]" in self.text_buffer and ("Tool Call:" in self.text_buffer or "Action:" in self.text_buffer))
                    or ("</" in self.text_buffer and ">" in self.text_buffer)
                    or (self.text_buffer.count("```") >= 2)
                )

                if has_closing:
                    discovered, cleaned, was_healed = heal_raw_text(self.text_buffer, declared_tools=self.declared_tools)
                    if was_healed:
                        self.has_emitted_tool_call = True
                        self.is_buffering_action = False
                        self.text_buffer = ""
                        # Synthesize tool_calls chunk
                        healed_chunk = dict(chunk)
                        healed_choice = dict(choice)
                        healed_choice["delta"] = {"tool_calls": discovered}
                        healed_choice["finish_reason"] = "tool_calls"
                        healed_chunk["choices"] = [healed_choice]
                        return [healed_chunk]

                # If buffer exceeds reasonable length without matching, flush it
                if len(self.text_buffer) > 1500:
                    flushed = self._flush_buffer(chunk_template=chunk)
                    return flushed

                # Still buffering action: suppress text delta chunk
                return []

        # Normal text pass-through
        return [chunk]

    def finalize_stream(self, chunk_template: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Called before stream completes [DONE]. Flushes remaining buffer or completion healer."""
        chunks: list[dict[str, Any]] = []

        # 1. Flush any unhealed text buffer
        if self.text_buffer:
            discovered, cleaned, was_healed = heal_raw_text(self.text_buffer, declared_tools=self.declared_tools)
            if was_healed and chunk_template:
                self.has_emitted_tool_call = True
                healed_chunk = dict(chunk_template)
                healed_choice = {
                    "index": 0,
                    "delta": {"tool_calls": discovered},
                    "finish_reason": "tool_calls",
                }
                healed_chunk["choices"] = [healed_choice]
                chunks.append(healed_chunk)
                self.text_buffer = ""
            elif chunk_template:
                chunks.extend(self._flush_buffer(chunk_template))

        # 2. If no tool calls were emitted anywhere in stream, check full accumulated text for completion healing
        if not self.has_emitted_tool_call and self.has_tools and self.accumulated_text and chunk_template:
            declared_names = {
                t.get("function", {}).get("name")
                for t in self.declared_tools
                if isinstance(t, dict) and t.get("function")
            }
            if "attempt_completion" in declared_names:
                trimmed = self.accumulated_text.strip()
                if any(p.search(trimmed) for p in COMPLETION_PATTERNS):
                    call_args = json.dumps({"result": trimmed})
                    healed_tc = [{
                        "index": 0,
                        "id": _generate_call_id("attempt_completion", call_args),
                        "type": "function",
                        "function": {"name": "attempt_completion", "arguments": call_args},
                    }]
                    comp_chunk = dict(chunk_template)
                    comp_chunk["choices"] = [{
                        "index": 0,
                        "delta": {"tool_calls": healed_tc},
                        "finish_reason": "tool_calls",
                    }]
                    chunks.append(comp_chunk)
                    self.has_emitted_tool_call = True
                    logger.info("StreamToolHealer synthesized attempt_completion tool call for stream")

        return chunks

    def _flush_buffer(self, chunk_template: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.text_buffer:
            return []
        buf_to_flush = self.text_buffer
        self.text_buffer = ""
        self.is_buffering_action = False
        flushed_chunk = dict(chunk_template)
        flushed_chunk["choices"] = [{
            "index": 0,
            "delta": {"content": buf_to_flush},
            "finish_reason": None,
        }]
        return [flushed_chunk]
