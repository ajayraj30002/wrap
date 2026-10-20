import hashlib
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
)

_THOUGHT_SIGNATURE_CACHE: dict[str, str] = {}


class GeminiAdapter(ProviderAdapter):
    name = "gemini"
    display_name = "Gemini"
    default_models = (
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
    )
    capabilities = ProviderCapabilities(
        streaming=True,
        response_format=False,
        max_completion_tokens=False,
        tool_calling=True,
    )

    FLASH_FALLBACK_CHAIN = (
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
    )

    def _get_model_candidates(self, requested_model: str) -> list[str]:
        if "flash" in requested_model.lower():
            candidates = [requested_model]
            for m in self.FLASH_FALLBACK_CHAIN:
                if m != requested_model and m not in candidates:
                    candidates.append(m)
            return candidates
        return [requested_model]

    @staticmethod
    def _clean_gemini_schema(schema: Any) -> Any:
        if not isinstance(schema, dict):
            return schema
        allowed = {
            "type", "format", "description", "nullable", "enum",
            "properties", "required", "items",
        }
        cleaned: dict[str, Any] = {}
        for k, v in schema.items():
            if k not in allowed:
                continue
            if k == "type":
                if isinstance(v, str):
                    cleaned[k] = v.upper()
                elif isinstance(v, list) and v:
                    non_null = [t for t in v if str(t).lower() != "null"]
                    cleaned[k] = (str(non_null[0]) if non_null else "string").upper()
                    if any(str(t).lower() == "null" for t in v):
                        cleaned["nullable"] = True
            elif k == "properties" and isinstance(v, dict):
                cleaned[k] = {pk: GeminiAdapter._clean_gemini_schema(pv) for pk, pv in v.items()}
            elif k == "items":
                cleaned[k] = GeminiAdapter._clean_gemini_schema(v)
            else:
                cleaned[k] = v

        if "properties" in cleaned and "type" not in cleaned:
            cleaned["type"] = "OBJECT"
        if "enum" in cleaned and "type" not in cleaned:
            cleaned["type"] = "STRING"
        if "properties" in cleaned and not cleaned["properties"]:
            cleaned.pop("properties", None)
        if "required" in cleaned and "properties" in cleaned:
            cleaned["required"] = [r for r in cleaned["required"] if r in cleaned["properties"]]
            if not cleaned["required"]:
                cleaned.pop("required", None)
        return cleaned

    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        contents = []
        system_texts = []
        tool_call_name_map: dict[str, str] = {}

        for message in request.get("messages", []):
            role = message.get("role", "user")
            content = message.get("content", "")

            if role in ("system", "developer"):
                text = content if isinstance(content, str) else json.dumps(content)
                system_texts.append(text)
                continue

            if role == "user":
                user_parts: list[dict[str, Any]] = []
                if isinstance(content, list):
                    # Multi-part content (Roo Code / Anthropic style blocks containing text and/or tool_result)
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type")
                            if btype == "tool_result":
                                tool_id = block.get("tool_use_id", "tool")
                                fn_name = tool_call_name_map.get(tool_id, tool_id)
                                tool_res = block.get("content", "")
                                if isinstance(tool_res, str):
                                    try:
                                        res_obj = json.loads(tool_res)
                                        if not isinstance(res_obj, dict):
                                            res_obj = {"output": tool_res}
                                    except Exception:
                                        res_obj = {"output": tool_res}
                                elif isinstance(tool_res, dict):
                                    res_obj = tool_res
                                else:
                                    res_obj = {"output": str(tool_res)}
                                user_parts.append({
                                    "functionResponse": {
                                        "name": fn_name,
                                        "response": res_obj,
                                    }
                                })
                            elif btype == "text":
                                if block.get("text"):
                                    user_parts.append({"text": block.get("text", "")})
                            else:
                                user_parts.append({"text": json.dumps(block)})
                        else:
                            user_parts.append({"text": str(block)})
                else:
                    user_parts.append({"text": content if isinstance(content, str) else json.dumps(content)})
                if not user_parts:
                    user_parts = [{"text": ""}]
                contents.append({"role": "user", "parts": user_parts})
                continue

            if role == "assistant":
                parts: list[dict[str, Any]] = []
                if isinstance(content, list):
                    # Multi-part assistant content (Anthropic style blocks)
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type")
                            if btype == "text" and block.get("text"):
                                parts.append({"text": block["text"]})
                            elif btype == "tool_use":
                                tu_name = block.get("name", "tool")
                                tu_id = block.get("id")
                                if tu_id:
                                    tool_call_name_map[tu_id] = tu_name
                                tu_args = block.get("input") or {}
                                if isinstance(tu_args, str):
                                    try:
                                        tu_args = json.loads(tu_args)
                                    except Exception:
                                        tu_args = {"raw_arguments": tu_args}
                                if not isinstance(tu_args, dict):
                                    tu_args = {"value": tu_args}
                                fc_part: dict[str, Any] = {
                                    "functionCall": {
                                        "name": tu_name,
                                        "args": tu_args,
                                    }
                                }
                                sig = _THOUGHT_SIGNATURE_CACHE.get(tu_id) if tu_id else None
                                if sig:
                                    fc_part["thoughtSignature"] = sig
                                parts.append(fc_part)
                elif content:
                    text = content if isinstance(content, str) else json.dumps(content)
                    parts.append({"text": text})

                for tc in message.get("tool_calls") or []:
                    tc_id = tc.get("id")
                    fn = tc.get("function") or {}
                    fn_name = fn.get("name", "tool")
                    if tc_id and fn_name:
                        tool_call_name_map[tc_id] = fn_name
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {"raw_arguments": fn_args}
                    if not isinstance(fn_args, dict):
                        fn_args = {"value": fn_args}
                    fc_part = {
                        "functionCall": {
                            "name": fn_name,
                            "args": fn_args,
                        }
                    }
                    sig = _THOUGHT_SIGNATURE_CACHE.get(tc_id) if tc_id else None
                    if sig:
                        fc_part["thoughtSignature"] = sig
                    parts.append(fc_part)

                if not parts:
                    parts = [{"text": ""}]
                contents.append({"role": "model", "parts": parts})
                continue

            if role == "tool":
                call_id = message.get("tool_call_id", "")
                fn_name = message.get("name") or tool_call_name_map.get(call_id) or "tool"
                res_content = message.get("content", "")
                if isinstance(res_content, str):
                    try:
                        res_obj = json.loads(res_content)
                        if not isinstance(res_obj, dict):
                            res_obj = {"output": res_content}
                    except Exception:
                        res_obj = {"output": res_content}
                elif isinstance(res_content, dict):
                    res_obj = res_content
                else:
                    res_obj = {"output": str(res_content)}

                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": fn_name,
                            "response": res_obj,
                        }
                    }],
                })

        payload: dict[str, Any] = {"contents": contents}

        # Tools translation (OpenAI tools -> Gemini functionDeclarations)
        if request.get("tools"):
            declarations = []
            for t in request["tools"]:
                if t.get("type") == "function" and "function" in t:
                    fn = t["function"]
                    decl: dict[str, Any] = {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                    }
                    if "parameters" in fn:
                        decl["parameters"] = self._clean_gemini_schema(fn["parameters"])
                    declarations.append(decl)
            if declarations:
                payload["tools"] = [{"functionDeclarations": declarations}]

        # Tool choice translation
        tool_choice = request.get("tool_choice")
        if tool_choice:
            if tool_choice == "none":
                payload["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
            elif tool_choice == "auto":
                payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
            elif tool_choice == "required":
                payload["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
            elif isinstance(tool_choice, dict) and "function" in tool_choice:
                payload["toolConfig"] = {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [tool_choice["function"]["name"]],
                    }
                }

        generation_config: dict[str, Any] = {}
        if request.get("temperature") is not None:
            generation_config["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            generation_config["topP"] = request["top_p"]
        if request.get("max_completion_tokens") is not None:
            generation_config["maxOutputTokens"] = request["max_completion_tokens"]
        elif request.get("max_tokens") is not None:
            generation_config["maxOutputTokens"] = request["max_tokens"]
        if request.get("stop") is not None:
            generation_config["stopSequences"] = request["stop"] if isinstance(request["stop"], list) else [request["stop"]]
        if request.get("tools") and any(k in model.lower() for k in ("thinking", "3.7-flash", "pro")):
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        if generation_config:
            payload["generationConfig"] = generation_config
        if system_texts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_texts)}]}
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
        candidates = self._get_model_candidates(model)
        last_error = None
        for cand_model in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent"
            async with httpx.AsyncClient(timeout=timeout) as client:
                try:
                    response = await client.post(url, headers={"x-goog-api-key": api_key}, json=self.normalize_request(request, cand_model))
                except Exception as exc:
                    norm_err = self.normalize_error(exc)
                    last_error = norm_err
                    if len(candidates) > 1 and cand_model != candidates[-1]:
                        continue
                    raise norm_err from exc

            if response.status_code >= 400:
                err = self._error_from_response(response)
                last_error = err
                if isinstance(err, (ProviderUnavailableError, RateLimitError, ModelNotFoundError)) and cand_model != candidates[-1]:
                    continue
                raise err

            body = response.json()
            candidates_data = body.get("candidates") or []
            if candidates_data:
                text, tool_calls, finish_reason = self._parse_gemini_candidate(candidates_data[0], cand_model)
            else:
                text, tool_calls, finish_reason = None, [], "stop"

            completion = self._openai_response(cand_model, text, tool_calls, finish_reason)
            return ProviderCompletion(response=completion, usage=self._usage(body), quota=None)

        if last_error:
            raise last_error
        raise ProviderUnavailableError(f"All Gemini model candidates exhausted for {model}")

    async def stream_completion(
        self,
        request: dict[str, Any],
        *,
        api_key: str,
        model: str,
        request_id: str,
        timeout: float,
    ) -> AsyncIterator[ProviderStreamEvent]:
        candidates = self._get_model_candidates(model)
        last_error = None

        for cand_model in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:streamGenerateContent"
            first_token_seen = False
            has_emitted_tools = False
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        url,
                        headers={"x-goog-api-key": api_key},
                        params={"alt": "sse"},
                        json=self.normalize_request(request, cand_model),
                    ) as response:
                        if response.status_code >= 400:
                            await response.aread()
                            raise self._error_from_response(response)

                        completion_id = f"chatcmpl-wrap-{int(time.time() * 1000)}"
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw_data = line.removeprefix("data:").strip()
                            if not raw_data:
                                continue
                            payload = json.loads(raw_data)
                            candidates_list = payload.get("candidates") or []
                            if not candidates_list:
                                continue
                            text, tool_calls, candidate_finish = self._parse_gemini_candidate(candidates_list[0], cand_model)
                            delta: dict[str, Any] = {}
                            if text:
                                delta["content"] = text
                            if tool_calls:
                                has_emitted_tools = True
                                delta["tool_calls"] = [
                                    {
                                        "index": idx,
                                        "id": tc["id"],
                                        "type": "function",
                                        "function": tc["function"],
                                    }
                                    for idx, tc in enumerate(tool_calls)
                                ]

                            if has_emitted_tools:
                                finish_reason = "tool_calls"
                            else:
                                finish_reason = candidate_finish

                            if not delta and not finish_reason:
                                continue

                            first_token_seen = True
                            choice: dict[str, Any] = {"index": 0, "delta": delta, "finish_reason": finish_reason}
                            yield ProviderStreamEvent(
                                payload={
                                    "id": completion_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": cand_model,
                                    "choices": [choice],
                                },
                                usage=self._usage(payload),
                            )
                        if not first_token_seen:
                            raise ProviderUnavailableError(f"Gemini stream for {cand_model} closed without producing any tokens")
                        yield ProviderStreamEvent(done=True)
                        return
            except ProviderError as exc:
                last_error = exc
                if not first_token_seen and isinstance(exc, (ProviderUnavailableError, RateLimitError, ModelNotFoundError)) and cand_model != candidates[-1]:
                    continue
                raise
            except Exception as exc:
                norm_err = self.normalize_error(exc)
                last_error = norm_err
                if not first_token_seen and cand_model != candidates[-1]:
                    continue
                raise norm_err from exc

        if last_error:
            raise last_error
        raise ProviderUnavailableError(f"All Gemini model candidates exhausted for {model}")

    async def test_credential(self, *, api_key: str, model: str, timeout: float) -> None:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers={"x-goog-api-key": api_key})
                if response.status_code == 200:
                    return
                if response.status_code in (401, 403, 404, 429):
                    raise self._error_from_response(response)
            except ProviderError:
                raise
            except Exception:
                pass
        request = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "stream": False,
        }
        await self.create_completion(request, api_key=api_key, model=model, request_id="credential-test", timeout=timeout)

    async def list_models(self, *, api_key: str, timeout: float) -> list[ProviderModel]:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers={"x-goog-api-key": api_key})
            except Exception as exc:
                raise self.normalize_error(exc) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response)
        models: list[ProviderModel] = []
        for item in response.json().get("models", []):
            name = item.get("name", "")
            model_id = name.removeprefix("models/")
            methods = set(item.get("supportedGenerationMethods") or [])
            if not model_id or "generateContent" not in methods:
                continue
            is_chat = not any(x in model_id.lower() for x in ["embedding", "aqa", "imagen", "medlm"])
            is_reasoning = any(x in model_id.lower() for x in ["thinking", "pro", "deep-research", "antigravity", "3.7-flash"])
            models.append(
                ProviderModel(
                    external_model_id=model_id,
                    display_name=item.get("displayName") or model_id,
                    status="ACTIVE",
                    context_window=item.get("inputTokenLimit"),
                    max_output_tokens=item.get("outputTokenLimit"),
                    streaming="generateContent" in methods,
                    tool_calling=is_chat,
                    structured_output=is_chat,
                    reasoning=is_reasoning,
                    catalog_metadata=item,
                )
            )
        return models

    def _parse_gemini_candidate(
        self, candidate: dict[str, Any], model: str
    ) -> tuple[str | None, list[dict[str, Any]], str]:
        content_obj = candidate.get("content") or {}
        parts = content_obj.get("parts") or []
        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for idx, part in enumerate(parts):
            if "text" in part:
                texts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                fn_name = fc.get("name", "")
                fn_args = fc.get("args") or {}
                serialized_args = json.dumps(fn_args)
                hash_input = f"{model}:{fn_name}:{serialized_args}:{idx}".encode()
                tc_id = fc.get("id") or f"call_{hashlib.sha256(hash_input).hexdigest()[:16]}"
                sig = part.get("thoughtSignature") or candidate.get("thoughtSignature")
                if sig and tc_id:
                    _THOUGHT_SIGNATURE_CACHE[tc_id] = sig
                    if len(_THOUGHT_SIGNATURE_CACHE) > 500:
                        for k in list(_THOUGHT_SIGNATURE_CACHE.keys())[:100]:
                            _THOUGHT_SIGNATURE_CACHE.pop(k, None)
                tool_calls.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": serialized_args,
                    },
                })

        full_text = "".join(texts) if texts else None

        # Autonomous Tool Healing: If no native tool_calls were emitted, check if candidate text contains unparsed tools
        if not tool_calls and full_text:
            from src.services.tool_healer import heal_response_tool_calls
            dummy_resp = {"choices": [{"message": {"content": full_text}, "finish_reason": "stop"}]}
            healed, was_healed = heal_response_tool_calls(dummy_resp)
            if was_healed:
                healed_choice = healed["choices"][0]
                tool_calls = healed_choice["message"].get("tool_calls") or []
                full_text = healed_choice["message"].get("content")

        raw_finish = candidate.get("finishReason")
        if tool_calls:
            finish_reason = "tool_calls"
        elif raw_finish == "MAX_TOKENS":
            finish_reason = "length"
        elif raw_finish == "STOP":
            finish_reason = "stop"
        elif raw_finish:
            finish_reason = raw_finish.lower()
        else:
            finish_reason = None

        return full_text, tool_calls, finish_reason


    def _openai_response(
        self, model: str, text: str | None, tool_calls: list[dict[str, Any]], finish_reason: str
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant"}
        if text is not None:
            message["content"] = text
        else:
            message["content"] = None
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "id": f"chatcmpl-wrap-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason or "stop",
                }
            ],
            "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        }

    def _usage(self, body: dict[str, Any]) -> dict[str, int | None] | None:
        usage = body.get("usageMetadata")
        if not usage:
            return None
        return {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        }

    def _error_from_response(self, response: httpx.Response) -> ProviderError:
        try:
            error_body = response.json()
            error_info = error_body.get("error", {})
            message = error_info.get("message", "Gemini request failed")
            details = error_info.get("details", [])
            reasons = [d.get("reason") for d in details if isinstance(d, dict) and "reason" in d]
        except Exception:
            message = "Gemini request failed"
            reasons = []

        if response.status_code == 401 or "API_KEY_INVALID" in reasons or "API key not valid" in message:
            return AuthenticationError(f"Gemini authentication failed: {message}", provider_status_code=response.status_code)
        if response.status_code == 429:
            return RateLimitError(message, provider_status_code=response.status_code)
        if response.status_code == 404:
            return ModelNotFoundError(f"Gemini model not found: {message}", provider_status_code=response.status_code)
        if response.status_code == 400:
            return InvalidRequestError(message, provider_status_code=response.status_code)
        return ProviderUnavailableError(message, provider_status_code=response.status_code)
