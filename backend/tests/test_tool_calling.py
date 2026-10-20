import json
import pytest
from unittest.mock import MagicMock
import uuid

from src.providers.base import ModelNotFoundError, ProviderCapabilities, ProviderModel
from src.providers.gemini import GeminiAdapter
from src.providers.openai_compatible import OpenAICompatibleAdapter
from src.schemas.openai import ChatCompletionRequest, ChatMessage
from src.intelligence.analysis.request_profile import RawFeatures, RequestProfile
from src.intelligence.resources.worker_state import WorkerState
from src.intelligence.scheduling.hard_constraint_filter import HardEligibilityFilter


def test_chat_message_schema_supports_tool_calls():
    # Test assistant message with tool calls and None content
    msg = ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ],
    )
    dumped = msg.model_dump(exclude_none=True)
    assert dumped["role"] == "assistant"
    assert "tool_calls" in dumped
    assert dumped["tool_calls"][0]["id"] == "call_123"

    # Test tool result message
    tool_msg = ChatMessage(
        role="tool",
        tool_call_id="call_123",
        content='{"temp": 22}',
    )
    assert tool_msg.tool_call_id == "call_123"


def test_gemini_normalize_request_with_tools_and_tool_choice():
    adapter = GeminiAdapter()
    request = {
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": "What is the weather?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Fetch weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }
    normalized = adapter.normalize_request(request, "gemini-2.5-flash")
    assert "tools" in normalized
    declarations = normalized["tools"][0]["functionDeclarations"]
    assert len(declarations) == 1
    assert declarations[0]["name"] == "get_weather"
    assert declarations[0]["description"] == "Fetch weather"
    assert "parameters" in declarations[0]
    assert normalized["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}


def test_gemini_normalize_request_specific_tool_choice():
    adapter = GeminiAdapter()
    request = {
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": "Fetch weather"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "Fetch weather"},
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
    }
    normalized = adapter.normalize_request(request, "gemini-2.5-flash")
    assert normalized["toolConfig"] == {
        "functionCallingConfig": {
            "mode": "ANY",
            "allowedFunctionNames": ["get_weather"],
        }
    }


def test_gemini_normalize_conversation_with_tool_calls_and_results():
    adapter = GeminiAdapter()
    request = {
        "model": "gemini-2.5-flash",
        "messages": [
            {"role": "user", "content": "What is the weather in Paris?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_abc123",
                "content": '{"temperature": 21, "condition": "sunny"}',
            },
        ],
    }
    normalized = adapter.normalize_request(request, "gemini-2.5-flash")
    contents = normalized["contents"]
    assert len(contents) == 3

    # User message
    assert contents[0]["role"] == "user"

    # Assistant message with native functionCall
    assert contents[1]["role"] == "model"
    part = contents[1]["parts"][0]
    assert "functionCall" in part
    assert part["functionCall"]["name"] == "get_weather"
    assert part["functionCall"]["args"] == {"city": "Paris"}

    # Tool result message with native functionResponse
    assert contents[2]["role"] == "user"
    resp_part = contents[2]["parts"][0]
    assert "functionResponse" in resp_part
    assert resp_part["functionResponse"]["name"] == "get_weather"
    assert resp_part["functionResponse"]["response"] == {"temperature": 21, "condition": "sunny"}


def test_gemini_normalize_roo_code_multipart_tool_results():
    adapter = GeminiAdapter()
    request = {
        "model": "gemini-flash-lite-latest",
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": '{"path": "."}'}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call_1", "content": "No files found."},
                    {"type": "text", "text": "What next?"},
                ],
            },
        ],
    }
    normalized = adapter.normalize_request(request, "gemini-flash-lite-latest")
    contents = normalized["contents"]
    assert len(contents) == 3
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["functionCall"]["name"] == "list_files"
    assert contents[2]["role"] == "user"
    assert len(contents[2]["parts"]) == 2
    assert contents[2]["parts"][0]["functionResponse"]["response"]["output"] == "No files found."
    assert contents[2]["parts"][1]["text"] == "What next?"



def test_gemini_parse_candidate_with_function_call():
    adapter = GeminiAdapter()
    candidate = {
        "content": {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": "write_file",
                        "args": {"path": "hello.txt", "content": "Hello from WRAP"},
                    }
                }
            ],
        },
        "finishReason": "STOP",
    }
    text, tool_calls, finish_reason = adapter._parse_gemini_candidate(candidate, "gemini-2.5-flash")
    assert text is None
    assert finish_reason == "tool_calls"
    assert len(tool_calls) == 1
    tc = tool_calls[0]
    assert tc["id"].startswith("call_")
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "write_file"
    args = json.loads(tc["function"]["arguments"])
    assert args == {"path": "hello.txt", "content": "Hello from WRAP"}

    # Test constructing full OpenAI response
    resp = adapter._openai_response("gemini-2.5-flash", text, tool_calls, finish_reason)
    assert resp["choices"][0]["finish_reason"] == "tool_calls"
    msg = resp["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg["content"] is None
    assert len(msg["tool_calls"]) == 1
    assert msg["tool_calls"][0]["function"]["name"] == "write_file"


def test_gemini_error_from_response_maps_404():
    adapter = GeminiAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"error": {"message": "models/nonexistent is not found"}}
    err = adapter._error_from_response(mock_resp)
    assert isinstance(err, ModelNotFoundError)
    assert err.provider_status_code == 404


def test_openai_compatible_adapter_preserves_tools_and_tool_choice():
    adapter = OpenAICompatibleAdapter()
    adapter.base_url = "https://example.com/v1/chat/completions"
    adapter.models_url = "https://example.com/v1/models"
    request = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function", "function": {"name": "test"}}],
        "tool_choice": "auto",
    }
    normalized = adapter.normalize_request(request, "llama-3.3-70b-versatile")
    assert normalized["tools"] == request["tools"]
    assert normalized["tool_choice"] == "auto"


def test_hard_eligibility_filter_gates_tool_calling():
    f = HardEligibilityFilter()

    # Request requiring tools
    profile_with_tools = RequestProfile(
        request_id="r1",
        raw=RawFeatures(
            tools=[{"type": "function", "function": {"name": "foo"}}],
            has_tool_requirement=True,
        ),
        tool_requirement=1.0,
    )

    # Worker with tool calling capability
    capable_worker = WorkerState(
        worker_id=uuid.uuid4(),
        provider="groq",
        credential_id=uuid.uuid4(),
        model="llama-3.3-70b",
        capabilities={"tool_calling": True},
    )

    # Worker without tool calling capability
    incapable_worker = WorkerState(
        worker_id=uuid.uuid4(),
        provider="groq",
        credential_id=uuid.uuid4(),
        model="llama-guard-3-8b",
        capabilities={"tool_calling": False},
    )

    result = f.filter(profile_with_tools, [capable_worker, incapable_worker])
    assert len(result.eligible) == 1
    assert result.eligible[0].worker_id == capable_worker.worker_id
    assert len(result.rejected) == 1
    assert result.rejected[0].worker_id == incapable_worker.worker_id
    assert result.rejected[0].reason == "tool_calling_not_supported"
