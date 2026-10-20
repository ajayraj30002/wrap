import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from src.providers.base import (
    AuthenticationError,
    InvalidRequestError,
    ModelNotFoundError,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCompletion,
    ProviderError,
    ProviderModel,
    ProviderStreamEvent,
    ProviderUnavailableError,
    RateLimitError,
    StreamingError,
)


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    display_name = "Anthropic"
    base_url = "https://api.anthropic.com/v1/messages"
    capabilities = ProviderCapabilities(
        streaming=True,
        response_format=True,
        max_completion_tokens=True,
        tool_calling=True,
    )
    default_models = (
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
    )

    def _headers(self, api_key: str, request_id: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "X-Request-ID": request_id,
        }

    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        system_prompts: list[str] = []
        messages: list[dict[str, Any]] = []

        # Convert OpenAI messages to Anthropic messages
        for m in request.get("messages", []):
            role = m.get("role", "user")
            content = m.get("content", "")

            if role in ("system", "developer"):
                text = content if isinstance(content, str) else json.dumps(content)
                system_prompts.append(text)
                continue

            if role == "assistant":
                content_blocks: list[dict[str, Any]] = []
                if content:
                    content_blocks.append({"type": "text", "text": content if isinstance(content, str) else json.dumps(content)})
                
                # Check for assistant tool_calls
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    fn_name = fn.get("name", "tool")
                    raw_args = fn.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except Exception:
                            parsed_args = {"raw_input": raw_args}
                    else:
                        parsed_args = raw_args
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"tool_use_{int(time.time())}"),
                        "name": fn_name,
                        "input": parsed_args,
                    })

                if not content_blocks:
                    content_blocks = [{"type": "text", "text": ""}]
                messages.append({"role": "assistant", "content": content_blocks})
                continue

            if role == "tool":
                call_id = m.get("tool_call_id") or "tool"
                res_content = content if isinstance(content, str) else json.dumps(content)
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": res_content,
                }
                # In Anthropic, tool_result blocks must be inside a 'user' message
                if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
                    messages[-1]["content"].append(tool_result_block)
                else:
                    messages.append({"role": "user", "content": [tool_result_block]})
                continue

            # Standard user message
            if isinstance(content, list):
                # May contain text or tool_result blocks already
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": str(content) if content is not None else ""})

        if not messages:
            messages.append({"role": "user", "content": "Hello"})

        max_tokens = request.get("max_completion_tokens") or request.get("max_tokens") or 4096

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if request.get("temperature") is not None:
            payload["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            payload["top_p"] = request["top_p"]
        if request.get("stop"):
            stop_val = request["stop"]
            payload["stop_sequences"] = [stop_val] if isinstance(stop_val, str) else stop_val

        # Tools translation (OpenAI -> Anthropic)
        if request.get("tools"):
            anthropic_tools = []
            for t in request["tools"]:
                if t.get("type") == "function" and "function" in t:
                    fn = t["function"]
                    schema = fn.get("parameters") or {"type": "object", "properties": {}}
                    anthropic_tools.append({
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": schema,
                    })
            if anthropic_tools:
                payload["tools"] = anthropic_tools

        # Tool choice translation
        tool_choice = request.get("tool_choice")
        if tool_choice:
            if tool_choice == "auto":
                payload["tool_choice"] = {"type": "auto"}
            elif tool_choice == "required":
                payload["tool_choice"] = {"type": "any"}
            elif isinstance(tool_choice, dict) and "function" in tool_choice:
                payload["tool_choice"] = {"type": "tool", "name": tool_choice["function"]["name"]}

        return payload

    async def create_completion(
        self,
        request: dict[str, Any],
        *,
        api_key: str,
        model: str,
        request_id: str,
        timeout: float,
    ) -> ProviderCompletion:
        payload = self.normalize_request({**request, "stream": False}, model)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    self.base_url,
                    headers=self._headers(api_key, request_id),
                    json=payload,
                )
            except Exception as exc:
                raise self.normalize_error(exc) from exc

        if response.status_code >= 400:
            raise self._error_from_response(response)

        body = response.json()
        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for b in body.get("content", []):
            b_type = b.get("type")
            if b_type == "text":
                texts.append(b.get("text", ""))
            elif b_type == "tool_use":
                raw_args = b.get("input") or {}
                serialized_args = json.dumps(raw_args) if isinstance(raw_args, (dict, list)) else str(raw_args)
                tool_calls.append({
                    "id": b.get("id"),
                    "type": "function",
                    "function": {
                        "name": b.get("name", "tool"),
                        "arguments": serialized_args,
                    },
                })

        text_content = "".join(texts) if texts else None

        # Autonomous Tool Healing: Check if text contains unparsed tool call
        if not tool_calls and text_content:
            from src.services.tool_healer import heal_response_tool_calls
            dummy_resp = {"choices": [{"message": {"content": text_content}, "finish_reason": "stop"}]}
            healed, was_healed = heal_response_tool_calls(dummy_resp)
            if was_healed:
                healed_choice = healed["choices"][0]
                tool_calls = healed_choice["message"].get("tool_calls") or []
                text_content = healed_choice["message"].get("content")

        usage = body.get("usage") or {}
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")

        stop_reason = body.get("stop_reason")
        if tool_calls:
            finish_reason = "tool_calls"
        elif stop_reason == "end_turn":
            finish_reason = "stop"
        elif stop_reason == "max_tokens":
            finish_reason = "length"
        else:
            finish_reason = stop_reason or "stop"

        response_payload = {
            "id": body.get("id"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", model),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": text_content,
                        **({"tool_calls": tool_calls} if tool_calls else {}),
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": in_tok,
                "completion_tokens": out_tok,
                "total_tokens": (in_tok or 0) + (out_tok or 0),
            },
        }

        quota = self.extract_quota(response.headers)
        return ProviderCompletion(response=response_payload, usage=response_payload["usage"], quota=quota)

    async def stream_completion(
        self,
        request: dict[str, Any],
        *,
        api_key: str,
        model: str,
        request_id: str,
        timeout: float,
    ) -> AsyncIterator[ProviderStreamEvent]:
        payload = self.normalize_request({**request, "stream": True}, model)
        payload["stream"] = True

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    self.base_url,
                    headers=self._headers(api_key, request_id),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        error_text = await response.aread()
                        raise self._error_from_response(response, error_text.decode("utf-8", errors="ignore"))

                    quota = self.extract_quota(response.headers)
                    in_tok = 0
                    out_tok = 0
                    current_block_type: str | None = None
                    current_block_index: int = 0
                    current_tool_id: str | None = None
                    current_tool_name: str | None = None

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if not data:
                            continue
                        try:
                            payload_evt = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise StreamingError("Provider returned malformed streaming data") from exc

                        evt_type = payload_evt.get("type")
                        if evt_type == "message_start":
                            msg_usage = payload_evt.get("message", {}).get("usage", {})
                            in_tok = msg_usage.get("input_tokens", 0)

                        elif evt_type == "content_block_start":
                            current_block_index = payload_evt.get("index", 0)
                            block = payload_evt.get("content_block", {})
                            current_block_type = block.get("type")
                            if current_block_type == "tool_use":
                                current_tool_id = block.get("id")
                                current_tool_name = block.get("name")
                                chunk = {
                                    "id": f"chatcmpl_{int(time.time())}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {
                                                "tool_calls": [
                                                    {
                                                        "index": current_block_index,
                                                        "id": current_tool_id,
                                                        "type": "function",
                                                        "function": {
                                                            "name": current_tool_name,
                                                            "arguments": "",
                                                        },
                                                    }
                                                ]
                                            },
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield ProviderStreamEvent(payload=chunk, quota=quota)

                        elif evt_type == "content_block_delta":
                            delta = payload_evt.get("delta", {})
                            d_type = delta.get("type")
                            if d_type == "text_delta":
                                chunk = {
                                    "id": f"chatcmpl_{int(time.time())}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": delta.get("text", "")},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield ProviderStreamEvent(payload=chunk, quota=quota)
                            elif d_type == "input_json_delta":
                                partial_args = delta.get("partial_json", "")
                                chunk = {
                                    "id": f"chatcmpl_{int(time.time())}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {
                                                "tool_calls": [
                                                    {
                                                        "index": current_block_index,
                                                        "function": {"arguments": partial_args},
                                                    }
                                                ]
                                            },
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield ProviderStreamEvent(payload=chunk, quota=quota)

                        elif evt_type == "message_delta":
                            d_usage = payload_evt.get("usage", {})
                            out_tok = d_usage.get("output_tokens", 0)
                            stop_reason = payload_evt.get("delta", {}).get("stop_reason")
                            f_reason = "tool_calls" if stop_reason == "tool_use" else (stop_reason or "stop")
                            final_chunk = {
                                "id": f"chatcmpl_{int(time.time())}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [{"index": 0, "delta": {}, "finish_reason": f_reason}],
                            }
                            yield ProviderStreamEvent(payload=final_chunk, quota=quota)

                        elif evt_type == "message_stop":
                            final_usage = {
                                "input_tokens": in_tok,
                                "output_tokens": out_tok,
                                "total_tokens": in_tok + out_tok,
                            }
                            yield ProviderStreamEvent(done=True, usage=final_usage, quota=quota)
                            return
            except ProviderError:
                raise
            except Exception as exc:
                raise self.normalize_error(exc) from exc

    async def list_models(self, *, api_key: str, timeout: float) -> list[ProviderModel]:
        return [
            ProviderModel(
                external_model_id=m,
                display_name=m,
                status="ACTIVE",
                streaming=True,
                structured_output=True,
                tool_calling=True,
                catalog_metadata={"developer": "Anthropic"},
            )
            for m in self.default_models
        ]

    def _error_from_response(self, response: httpx.Response, text: str | None = None) -> ProviderError:
        message = "Provider request failed"
        if text:
            message = text[:500]
        else:
            try:
                payload = response.json()
                message = payload.get("error", {}).get("message") or message
            except Exception:
                message = response.text[:500] or message

        if response.status_code in (401, 403):
            return AuthenticationError("Provider authentication failed", provider_status_code=response.status_code)
        if response.status_code == 429:
            return RateLimitError("Provider rate limit exceeded", provider_status_code=response.status_code)
        if response.status_code == 404:
            return ModelNotFoundError("Provider model was not found", provider_status_code=response.status_code)
        if response.status_code == 400:
            return InvalidRequestError(message, provider_status_code=response.status_code)
        if response.status_code >= 500:
            return ProviderUnavailableError("Provider is unavailable", provider_status_code=response.status_code)
        return ProviderError(message, provider_status_code=response.status_code)
