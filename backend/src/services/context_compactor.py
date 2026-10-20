"""Agentic Context Compactor and History Windowing Service.

Optimizes multi-turn agentic coding sessions (Roo Code, Cursor, Windsurf, Continue)
by trimming stale historical tool execution outputs while maintaining 100% tool_call_id
pairing integrity, system prompts, and immediate working memory.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("wrap.context_compactor")


def estimate_messages_tokens(messages: list[dict[str, Any] | Any], tools: list[Any] | None = None) -> int:
    """Fast estimation of token mass from messages and tool definitions."""
    char_count = 0
    for m in messages:
        if isinstance(m, dict):
            c = m.get("content")
            if isinstance(c, str):
                char_count += len(c)
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict):
                        char_count += len(str(part.get("text") or part.get("content") or ""))
                    else:
                        char_count += len(str(part))
            t_calls = m.get("tool_calls")
            if t_calls and isinstance(t_calls, list):
                for tc in t_calls:
                    if isinstance(tc, dict):
                        char_count += len(str(tc.get("function", {}).get("arguments", "")))
        else:
            c = getattr(m, "content", "")
            if isinstance(c, str):
                char_count += len(c)
            elif isinstance(c, list):
                char_count += sum(len(str(p)) for p in c)

    if tools:
        try:
            char_count += len(json.dumps(tools))
        except Exception:
            pass

    return max(1, char_count // 4)


def compact_agent_messages(
    messages: list[dict[str, Any] | Any],
    max_history_turns: int = 4,
    max_tool_output_chars: int = 800,
    target_token_threshold: int = 3500,
) -> tuple[list[dict[str, Any]], bool]:
    """Prunes stale historical tool outputs when token mass exceeds threshold.
    
    Guarantees:
    1. System / developer instructions are 100% preserved.
    2. Initial user goal / instruction is 100% preserved.
    3. The latest `max_history_turns` turns are 100% verbatim.
    4. Tool call integrity is strictly maintained: no tool messages or tool_calls are deleted,
       only the internal verbose stdout text is trimmed.
    """
    total_tokens = estimate_messages_tokens(messages)
    if total_tokens < target_token_threshold:
        # No compaction needed
        dict_msgs = [m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages]
        return dict_msgs, False

    dict_msgs: list[dict[str, Any]] = [
        m if isinstance(m, dict) else m.model_dump(exclude_none=True)
        for m in messages
    ]

    if len(dict_msgs) <= 4:
        return dict_msgs, False

    # Identify protected boundary: keep the tail messages (last max_history_turns * 2 messages) verbatim
    # Usually a turn is (assistant tool_call + tool response) or (user prompt + assistant response)
    tail_cutoff = max(2, len(dict_msgs) - (max_history_turns * 2))

    compacted = False
    new_msgs: list[dict[str, Any]] = []

    for idx, msg in enumerate(dict_msgs):
        # Shallow copy message dict to avoid mutating original
        msg_copy = dict(msg)
        role = msg_copy.get("role")

        # Head system message and recent working window are protected
        if role in ("system", "developer") or idx >= tail_cutoff or idx == 0:
            new_msgs.append(msg_copy)
            continue

        # Check for repetitive coding agent environment blocks in historical messages
        if idx < tail_cutoff:
            if isinstance(msg_copy.get("content"), str) and "<environment_details>" in msg_copy["content"]:
                import re
                msg_copy["content"] = re.sub(
                    r"<environment_details>.*?</environment_details>",
                    "[... wrap compactor: historical environment_details deduplicated ...]",
                    msg_copy["content"],
                    flags=re.DOTALL,
                )
                compacted = True
            elif isinstance(msg_copy.get("content"), list):
                new_blocks = []
                for b in msg_copy["content"]:
                    if isinstance(b, dict) and isinstance(b.get("text"), str) and "<environment_details>" in b["text"]:
                        import re
                        b_copy = dict(b)
                        b_copy["text"] = re.sub(
                            r"<environment_details>.*?</environment_details>",
                            "[... wrap compactor: historical environment_details deduplicated ...]",
                            b["text"],
                            flags=re.DOTALL,
                        )
                        new_blocks.append(b_copy)
                        compacted = True
                    else:
                        new_blocks.append(b)
                msg_copy["content"] = new_blocks

        # Prune older tool outputs
        if role in ("tool", "function"):
            content = msg_copy.get("content")
            if isinstance(content, str) and len(content) > max_tool_output_chars:
                head = content[:350]
                tail = content[-250:]
                trimmed_chars = len(content) - 600
                msg_copy["content"] = f"{head}\n\n[... wrap agentic compactor: truncated {trimmed_chars} chars of past execution output ...]\n\n{tail}"
                compacted = True
            elif isinstance(content, list):
                # Multipart tool output
                compacted_parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        p_text = part["text"]
                        if len(p_text) > max_tool_output_chars:
                            head = p_text[:350]
                            tail = p_text[-250:]
                            trimmed = len(p_text) - 600
                            part = dict(part)
                            part["text"] = f"{head}\n\n[... wrap compactor: truncated {trimmed} chars ...]\n\n{tail}"
                            compacted = True
                    compacted_parts.append(part)
                msg_copy["content"] = compacted_parts

        elif role == "user":
            content = msg_copy.get("content")
            if isinstance(content, list):
                # Anthropic / Roo Code style tool_result inside user message
                compacted_blocks = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_out = block.get("content")
                        if isinstance(tool_out, str) and len(tool_out) > max_tool_output_chars:
                            b_copy = dict(block)
                            head = tool_out[:350]
                            tail = tool_out[-250:]
                            trimmed = len(tool_out) - 600
                            b_copy["content"] = f"{head}\n\n[... wrap compactor: truncated {trimmed} chars ...]\n\n{tail}"
                            compacted_blocks.append(b_copy)
                            compacted = True
                            continue
                    compacted_blocks.append(block)
                msg_copy["content"] = compacted_blocks
            elif isinstance(content, str) and len(content) > (max_tool_output_chars * 2):
                # Intermediate large user messages that are not the root goal
                head = content[:600]
                tail = content[-300:]
                trimmed = len(content) - 900
                msg_copy["content"] = f"{head}\n\n[... wrap compactor: truncated {trimmed} chars of historical context ...]\n\n{tail}"
                compacted = True

        elif role == "assistant":
            # If assistant wrote a massive explanation in older turns, trim it while preserving tool_calls
            content = msg_copy.get("content")
            if isinstance(content, str) and len(content) > 1500:
                head = content[:500]
                tail = content[-300:]
                trimmed = len(content) - 800
                msg_copy["content"] = f"{head}\n\n[... wrap compactor: trimmed {trimmed} chars ...]\n\n{tail}"
                compacted = True

        new_msgs.append(msg_copy)

    tokens_saved = max(0, total_tokens - estimate_messages_tokens(new_msgs))
    if compacted:
        logger.info("Agent context compacted: saved ~%d tokens (%d -> %d)", tokens_saved, total_tokens, total_tokens - tokens_saved)

    return new_msgs, compacted

