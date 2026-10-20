import pytest
from src.services.context_compactor import compact_agent_messages, estimate_messages_tokens


def test_compact_agent_messages_preserves_structure_and_prunes_bloat():
    # Construct a simulated multi-turn agent conversation (like Roo Code)
    system_msg = {"role": "system", "content": "You are an elite autonomous software engineer."}
    initial_user_msg = {"role": "user", "content": "Build a real-time monitor application from scratch."}
    
    messages = [system_msg, initial_user_msg]
    
    # Add 8 turns of tool execution with massive stdout logs
    for i in range(1, 9):
        messages.append({
            "role": "assistant",
            "content": f"Step {i}: running command and writing files.",
            "tool_calls": [{
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "arguments": f'{{"command": "npm install pkg_{i}"}}'
                }
            }]
        })
        # Massive 3,000-character stdout log
        huge_stdout = f"npm install progress for pkg_{i}...\n" + ("x" * 2800) + f"\nInstalled pkg_{i} successfully."
        messages.append({
            "role": "tool",
            "tool_call_id": f"call_{i}",
            "name": "execute_command",
            "content": huge_stdout,
        })

    initial_tokens = estimate_messages_tokens(messages)
    assert initial_tokens > 5000, f"Expected initial token count > 5000, got {initial_tokens}"

    compacted_msgs, was_compacted = compact_agent_messages(
        messages,
        max_history_turns=3,
        max_tool_output_chars=600,
        target_token_threshold=2000,
    )

    assert was_compacted is True
    assert len(compacted_msgs) == len(messages), "Compactor must never delete messages to preserve tool call chains"

    # 1. System and initial user messages preserved 100%
    assert compacted_msgs[0]["role"] == "system"
    assert compacted_msgs[0]["content"] == system_msg["content"]
    assert compacted_msgs[1]["role"] == "user"
    assert compacted_msgs[1]["content"] == initial_user_msg["content"]

    # 2. Older tool outputs (e.g. index 3, which is turn 1 tool response) must be truncated
    old_tool_out = compacted_msgs[3]["content"]
    assert len(old_tool_out) < 1200
    assert "truncated" in old_tool_out

    # 3. Recent tool outputs (the last 3 turns) must be completely preserved
    recent_tool_out = compacted_msgs[-1]["content"]
    assert "truncated" not in recent_tool_out
    assert len(recent_tool_out) > 2000

    # 4. Total tokens drastically reduced
    compacted_tokens = estimate_messages_tokens(compacted_msgs)
    assert compacted_tokens < initial_tokens
    print(f"Token mass reduced from {initial_tokens} down to {compacted_tokens} tokens!")


def test_compact_agent_messages_no_op_when_small():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    compacted, was_compacted = compact_agent_messages(messages, target_token_threshold=3500)
    assert was_compacted is False
    assert len(compacted) == 3
