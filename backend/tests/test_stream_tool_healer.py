import json
import pytest
from src.services.tool_healer import heal_raw_text, heal_response_tool_calls, StreamToolHealer

def test_heal_executed_tool_call_text():
    text = '[Executed Tool Call: write_to_file({"path": "CMakeLists.txt", "content": "cmake_minimum_required(VERSION 3.20)"})]'
    tools, cleaned, healed = heal_raw_text(text, declared_tools=[{"function": {"name": "write_to_file"}}])
    assert healed is True
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "write_to_file"
    args = json.loads(tools[0]["function"]["arguments"])
    assert args["path"] == "CMakeLists.txt"
    assert "cmake_minimum_required" in args["content"]
    assert cleaned is None

def test_heal_tool_call_kwargs():
    text = '[Tool Call: execute_command(command="cargo test --release")]'
    tools, cleaned, healed = heal_raw_text(text, declared_tools=[{"function": {"name": "execute_command"}}])
    assert healed is True
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "execute_command"
    args = json.loads(tools[0]["function"]["arguments"])
    assert args["command"] == "cargo test --release"

def test_heal_xml_tool_call():
    text = '<write_to_file>\n<path>main.cpp</path>\n<content>int main() { return 0; }</content>\n</write_to_file>'
    tools, cleaned, healed = heal_raw_text(text, declared_tools=[{"function": {"name": "write_to_file"}}])
    assert healed is True
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "write_to_file"
    args = json.loads(tools[0]["function"]["arguments"])
    assert args["path"] == "main.cpp"

def test_heal_completion_text_into_attempt_completion():
    text = "Task Completed\nI have designed and implemented a production-grade, lock-free SPMC Ring Buffer in C++20."
    tools, cleaned, healed = heal_raw_text(text, declared_tools=[{"function": {"name": "attempt_completion"}}])
    assert healed is True
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "attempt_completion"
    args = json.loads(tools[0]["function"]["arguments"])
    assert "Task Completed" in args["result"]

def test_stream_tool_healer_intercepts_split_chunks():
    healer = StreamToolHealer(
        declared_tools=[{"function": {"name": "write_to_file"}}],
        model="gpt-4o",
    )
    # Stream arriving in fragments
    chunks = [
        {"id": "c1", "choices": [{"index": 0, "delta": {"content": "[Executed "}}]},
        {"id": "c1", "choices": [{"index": 0, "delta": {"content": "Tool Call: write_to_file("}}]},
        {"id": "c1", "choices": [{"index": 0, "delta": {"content": '{"path": "CMakeLists.txt", '}}]},
        {"id": "c1", "choices": [{"index": 0, "delta": {"content": '"content": "test"}'}}]},
        {"id": "c1", "choices": [{"index": 0, "delta": {"content": ")]"}}]},
    ]
    emitted = []
    for c in chunks:
        emitted.extend(healer.process_chunk(c))
    
    assert len(emitted) == 1
    tc = emitted[0]["choices"][0]["delta"]["tool_calls"][0]
    assert tc["function"]["name"] == "write_to_file"
    assert emitted[0]["choices"][0]["finish_reason"] == "tool_calls"
