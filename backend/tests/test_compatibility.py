import json
from collections.abc import AsyncIterator
from datetime import timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.security import generate_random_token, get_password_hash, hash_token, utcnow
from src.db.models import AdminSession, AdminUser, Base, GatewayApiKey
from src.db.session import AsyncSessionLocal, engine
from src.main import app
from src.providers.base import ProviderCapabilities, ProviderCompletion, ProviderStreamEvent
from src.providers.registry import registry
from src.services.bootstrap import ensure_builtin_providers


class MockAgentProviderAdapter:
    name = "groq"
    display_name = "Groq"
    default_models = ("fake-agent-model",)
    capabilities = ProviderCapabilities(
        streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True
    )

    def normalize_request(self, request, model):
        return request

    async def create_completion(self, request, *, api_key, model, request_id, timeout):
        messages = request.get("messages", [])
        last_msg = messages[-1] if messages else {}

        # If last message is a tool response, complete the task
        if last_msg.get("role") == "tool":
            return ProviderCompletion(
                response={
                    "id": "chatcmpl_mock_done",
                    "object": "chat.completion",
                    "created": 1234567890,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "File created successfully with content: Hello from WRAP",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                },
                usage={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
                quota=None,
            )

        # If tools are requested, return a tool call
        if request.get("tools"):
            return ProviderCompletion(
                response={
                    "id": "chatcmpl_mock_tool",
                    "object": "chat.completion",
                    "created": 1234567890,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_mock_write_123",
                                        "type": "function",
                                        "function": {
                                            "name": "write_file",
                                            "arguments": json.dumps(
                                                {"path": "hello.txt", "content": "Hello from WRAP"}
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 12, "total_tokens": 27},
                },
                usage={"input_tokens": 15, "output_tokens": 12, "total_tokens": 27},
                quota=None,
            )

        # Plain assistant response
        return ProviderCompletion(
            response={
                "id": "chatcmpl_mock_plain",
                "object": "chat.completion",
                "created": 1234567890,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "I am a helpful assistant."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
            },
            usage={"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
            quota=None,
        )

    async def stream_completion(
        self, request, *, api_key, model, request_id, timeout
    ) -> AsyncIterator[ProviderStreamEvent]:
        if request.get("tools"):
            # Stream a tool call
            yield ProviderStreamEvent(
                payload={
                    "id": "chatcmpl_stream_tc",
                    "object": "chat.completion.chunk",
                    "created": 1234567890,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_stream_123",
                                        "type": "function",
                                        "function": {
                                            "name": "write_file",
                                            "arguments": '{"path": "hello.txt"}',
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            )
            yield ProviderStreamEvent(done=True)
            return

        # Stream regular content
        yield ProviderStreamEvent(
            payload={
                "id": "chatcmpl_stream_text",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}],
            }
        )
        yield ProviderStreamEvent(
            payload={
                "id": "chatcmpl_stream_text",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": "stop"}],
            }
        )
        yield ProviderStreamEvent(done=True)

    async def test_credential(self, *, api_key, model, timeout):
        return None


@pytest.fixture(autouse=True)
async def setup_test_environment():
    registry.register(MockAgentProviderAdapter())
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await ensure_builtin_providers(session)
    yield


@pytest.fixture
async def auth_context():
    async with AsyncSessionLocal() as session:
        user = AdminUser(password_hash=get_password_hash("testpwd"))
        session.add(user)
        token = generate_random_token(64)
        session_obj = AdminSession(
            session_token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(days=1),
        )
        session.add(session_obj)

        raw_key = generate_random_token(32)
        wrap_key = f"wrap_{raw_key}"
        key_obj = GatewayApiKey(
            name="test-key",
            prefix=wrap_key[:8],
            key_hash=hash_token(wrap_key),
        )
        session.add(key_obj)
        await session.commit()
    return {"cookies": {"session_id": token}, "wrap_key": wrap_key}


@pytest.mark.asyncio
async def test_compatibility_basic_chat(auth_context):
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create worker
        cred_resp = await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-cred",
                "api_key": "gsk_test_key",
                "model": "fake-agent-model",
            },
        )
        assert cred_resp.status_code == 201

        # Standard OpenAI client request
        chat_resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert chat_resp.status_code == 200
        data = chat_resp.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["finish_reason"] == "stop"
        assert "content" in data["choices"][0]["message"]


@pytest.mark.asyncio
async def test_compatibility_tool_calling_loop(auth_context):
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create worker
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-cred",
                "api_key": "gsk_test_key",
                "model": "fake-agent-model",
            },
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Create or write file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]

        # Step 1: Client sends request with tools (Real-world agent test from Section 41)
        step1_resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [
                    {
                        "role": "user",
                        "content": "Create hello.txt containing exactly: Hello from WRAP",
                    }
                ],
                "tools": tools,
                "tool_choice": "auto",
            },
        )
        assert step1_resp.status_code == 200
        step1_data = step1_resp.json()
        choice = step1_data["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        tool_calls = choice["message"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["type"] == "function"
        assert tool_calls[0]["function"]["name"] == "write_file"
        call_id = tool_calls[0]["id"]
        parsed_args = json.loads(tool_calls[0]["function"]["arguments"])
        assert parsed_args["path"] == "hello.txt"
        assert parsed_args["content"] == "Hello from WRAP"

        # Step 2: Client executes the tool locally and sends back tool result
        step2_resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [
                    {
                        "role": "user",
                        "content": "Create hello.txt containing exactly: Hello from WRAP",
                    },
                    choice["message"],  # assistant message with tool_calls
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"status": "success", "bytes_written": 15}),
                    },
                ],
                "tools": tools,
            },
        )
        assert step2_resp.status_code == 200
        step2_data = step2_resp.json()
        assert step2_data["choices"][0]["finish_reason"] == "stop"
        assert "Hello from WRAP" in step2_data["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_compatibility_streaming(auth_context):
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-cred",
                "api_key": "gsk_test_key",
                "model": "fake-agent-model",
            },
        )

        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Stream me"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data: " in body
        assert "[DONE]" in body
        assert "Hello" in body
        assert "world" in body


@pytest.mark.asyncio
async def test_compatibility_streaming_tool_calls(auth_context):
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-cred",
                "api_key": "gsk_test_key",
                "model": "fake-agent-model",
            },
        )

        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {wrap_key}"},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "Call tool"}],
                "tools": [{"type": "function", "function": {"name": "write_file"}}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        body = resp.text
        assert "tool_calls" in body
        assert "write_file" in body
        assert "[DONE]" in body


@pytest.mark.asyncio
async def test_compatibility_models_endpoint(auth_context):
    cookies = auth_context["cookies"]
    wrap_key = auth_context["wrap_key"]

    async with AsyncClient(app=app, base_url="http://test") as client:
        await client.post(
            "/api/credentials",
            cookies=cookies,
            json={
                "provider": "groq",
                "name": "groq-cred",
                "api_key": "gsk_test_key",
                "model": "fake-agent-model",
            },
        )
        resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {wrap_key}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        model_ids = [m["id"] for m in data["data"]]
        assert "auto" in model_ids
        assert "fake-agent-model" in model_ids


@pytest.mark.asyncio
async def test_compatibility_error_format(auth_context):
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test missing/bad auth error
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer bad_key"},
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data
        assert "message" in data["error"]
        assert "type" in data["error"]
