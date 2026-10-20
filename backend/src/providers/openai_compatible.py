import json
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
    ProviderModel,
    ProviderError,
    ProviderStreamEvent,
    ProviderUnavailableError,
    RateLimitError,
    StreamingError,
)


class OpenAICompatibleAdapter(ProviderAdapter):
    base_url: str
    models_url: str
    capabilities = ProviderCapabilities(streaming=True, response_format=True, max_completion_tokens=True, tool_calling=True)

    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        allowed = {
            "messages",
            "temperature",
            "top_p",
            "stream",
            "stop",
            "response_format",
            "tools",
            "tool_choice",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "user",
        }
        payload = {key: request[key] for key in allowed if key in request and request[key] is not None}
        payload["model"] = model
        if request.get("max_completion_tokens") is not None:
            payload["max_completion_tokens"] = request["max_completion_tokens"]
        elif request.get("max_tokens") is not None:
            payload["max_tokens"] = request["max_tokens"]
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
        return ProviderCompletion(response=body, usage=self._usage(body), quota=self.extract_quota(response.headers))

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
                    usage: dict[str, int | None] | None = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            yield ProviderStreamEvent(done=True, usage=usage, quota=quota)
                            return
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise StreamingError("Provider returned malformed streaming data") from exc
                        usage = self._usage(payload) or usage
                        yield ProviderStreamEvent(payload=payload, usage=usage, quota=quota)
            except ProviderError:
                raise
            except Exception as exc:
                raise self.normalize_error(exc) from exc

    async def list_models(self, *, api_key: str, timeout: float) -> list[ProviderModel]:
        if not getattr(self, "models_url", None):
            return [
                ProviderModel(
                    external_model_id=m,
                    display_name=m,
                    status="ACTIVE",
                    streaming=self.capabilities.streaming,
                    structured_output=self.capabilities.response_format,
                    tool_calling=self.capabilities.tool_calling,
                )
                for m in getattr(self, "default_models", ())
            ]

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(self.models_url, headers=self._headers(api_key, "catalog-sync"))
            except Exception as exc:
                if getattr(self, "default_models", ()):
                    return [
                        ProviderModel(
                            external_model_id=m,
                            display_name=m,
                            status="ACTIVE",
                            streaming=self.capabilities.streaming,
                            structured_output=self.capabilities.response_format,
                            tool_calling=self.capabilities.tool_calling,
                        )
                        for m in getattr(self, "default_models", ())
                    ]
                raise self.normalize_error(exc) from exc

        if response.status_code >= 400:
            if getattr(self, "default_models", ()) and response.status_code in (404, 405, 500, 501):
                return [
                    ProviderModel(
                        external_model_id=m,
                        display_name=m,
                        status="ACTIVE",
                        streaming=self.capabilities.streaming,
                        structured_output=self.capabilities.response_format,
                        tool_calling=self.capabilities.tool_calling,
                    )
                    for m in getattr(self, "default_models", ())
                ]
            raise self._error_from_response(response)

        models = []
        for item in response.json().get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            item_caps = item.get("capabilities") or {}
            supported_features = set(item.get("supported_features") or [])
            if "tools" in item_caps or "tools" in supported_features:
                supports_tools = True
            else:
                lower_id = model_id.lower()
                supports_tools = not any(x in lower_id for x in ["whisper", "embed", "tts", "moderation", "guard"])

            context_window = item.get("context_window") or item.get("context_length")
            max_output_tokens = item.get("max_completion_tokens") or item.get("max_output_length")
            supports_reasoning = (
                "reasoning" in supported_features
                or "thinking" in supported_features
                or any(x in model_id.lower() for x in ["r1", "reasoner", "o1", "o3", "120b"])
            )
            supports_structured = (
                "json_mode" in supported_features
                or "structured_outputs" in supported_features
                or self.capabilities.response_format
            )

            models.append(
                ProviderModel(
                    external_model_id=model_id,
                    display_name=item.get("display_name") or model_id,
                    status="ACTIVE",
                    context_window=context_window,
                    max_output_tokens=max_output_tokens,
                    reasoning=supports_reasoning,
                    streaming=self.capabilities.streaming,
                    structured_output=supports_structured,
                    tool_calling=supports_tools,
                    catalog_metadata={key: value for key, value in item.items() if key != "id"},
                )
            )
        return models or [
            ProviderModel(
                external_model_id=m,
                display_name=m,
                status="ACTIVE",
                streaming=self.capabilities.streaming,
                structured_output=self.capabilities.response_format,
                tool_calling=self.capabilities.tool_calling,
            )
            for m in getattr(self, "default_models", ())
        ]

    def _headers(self, api_key: str, request_id: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        if getattr(self, "name", "") == "openrouter":
            headers["HTTP-Referer"] = "https://wrap.dev"
            headers["X-Title"] = "WRAP AI Gateway"
        return headers

    def _usage(self, body: dict[str, Any]) -> dict[str, int | None]:
        usage = body.get("usage") or {}
        return {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }

    def _error_from_response(self, response: httpx.Response, text: str | None = None) -> ProviderError:
        message = "Provider request failed"
        if text:
            message = text[:500]
        else:
            try:
                payload = response.json()
                message = payload.get("error", {}).get("message") or payload.get("message") or message
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


class GroqAdapter(OpenAICompatibleAdapter):
    name = "groq"
    display_name = "Groq"
    base_url = "https://api.groq.com/openai/v1/chat/completions"
    models_url = "https://api.groq.com/openai/v1/models"
    default_models = (
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "deepseek-r1-distill-llama-70b",
        "mixtral-8x7b-32768",
    )

    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        payload = super().normalize_request(request, model)
        import copy
        payload = copy.deepcopy(payload)

        # 1. Prune verbose tool parameter schemas and $schema references
        if payload.get("tools"):
            for t in payload["tools"]:
                if t.get("type") == "function" and "function" in t:
                    fn = t["function"]
                    if "description" in fn and isinstance(fn["description"], str) and len(fn["description"]) > 160:
                        fn["description"] = fn["description"][:160] + "..."
                    params = fn.get("parameters") or {}
                    if isinstance(params, dict):
                        params.pop("$schema", None)
                        params.pop("title", None)
                        props = params.get("properties") or {}
                        for pk, pv in props.items():
                            if isinstance(pv, dict):
                                pv.pop("$schema", None)
                                pv.pop("title", None)
                                pv.pop("examples", None)
                                if "description" in pv and isinstance(pv["description"], str) and len(pv["description"]) > 100:
                                    pv["description"] = pv["description"][:100] + "..."

        # Calculate character mass
        def _calc_chars(p: dict) -> int:
            total = sum(len(str(m.get("content", ""))) for m in p.get("messages", []))
            if p.get("tools"):
                try:
                    total += len(json.dumps(p["tools"]))
                except Exception:
                    pass
            return total

        # Agentic Context Compaction for OpenAI-compatible upstreams (Groq, Cerebras, DeepSeek)
        if payload.get("messages"):
            try:
                from src.services.context_compactor import compact_agent_messages
                compacted_msgs, _ = compact_agent_messages(
                    payload["messages"],
                    max_history_turns=4,
                    max_tool_output_chars=800,
                    target_token_threshold=3500,
                )
                payload["messages"] = compacted_msgs
            except Exception:
                pass

        return payload


class CerebrasAdapter(OpenAICompatibleAdapter):
    name = "cerebras"
    display_name = "Cerebras"
    base_url = "https://api.cerebras.ai/v1/chat/completions"
    models_url = "https://api.cerebras.ai/v1/models"
    default_models = (
        "llama-3.3-70b",
        "llama3.1-8b",
        "qwen-2.5-72b",
    )


class OpenAIAdapter(OpenAICompatibleAdapter):
    name = "openai"
    display_name = "OpenAI"
    base_url = "https://api.openai.com/v1/chat/completions"
    models_url = "https://api.openai.com/v1/models"
    default_models = (
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o3-mini",
        "gpt-4-turbo",
    )

    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        payload = super().normalize_request(request, model)
        # Extreme case adaptation for OpenAI reasoning models (o1, o3-mini)
        if model.lower().startswith("o1") or model.lower().startswith("o3"):
            # Omit temperature as o1/o3-mini reject custom temperatures with HTTP 400
            payload.pop("temperature", None)
            # Map max_tokens -> max_completion_tokens
            if "max_tokens" in payload and "max_completion_tokens" not in payload:
                payload["max_completion_tokens"] = payload.pop("max_tokens")
            # Replace system role with developer role for reasoning models
            if "messages" in payload:
                new_msgs = []
                for m in payload["messages"]:
                    if isinstance(m, dict) and m.get("role") == "system":
                        new_msgs.append({**m, "role": "developer"})
                    else:
                        new_msgs.append(m)
                payload["messages"] = new_msgs
        return payload



class DeepSeekAdapter(OpenAICompatibleAdapter):
    name = "deepseek"
    display_name = "DeepSeek"
    base_url = "https://api.deepseek.com/v1/chat/completions"
    models_url = "https://api.deepseek.com/v1/models"
    default_models = (
        "deepseek-chat",
        "deepseek-reasoner",
    )


class MistralAdapter(OpenAICompatibleAdapter):
    name = "mistral"
    display_name = "Mistral AI"
    base_url = "https://api.mistral.ai/v1/chat/completions"
    models_url = "https://api.mistral.ai/v1/models"
    default_models = (
        "mistral-large-latest",
        "codestral-latest",
        "mistral-small-latest",
        "pixtral-large-latest",
    )


class TogetherAdapter(OpenAICompatibleAdapter):
    name = "together"
    display_name = "Together AI"
    base_url = "https://api.together.xyz/v1/chat/completions"
    models_url = "https://api.together.xyz/v1/models"
    default_models = (
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-R1",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
    )


class OpenRouterAdapter(OpenAICompatibleAdapter):
    name = "openrouter"
    display_name = "OpenRouter"
    base_url = "https://openrouter.ai/api/v1/chat/completions"
    models_url = "https://openrouter.ai/api/v1/models"
    default_models = (
        "auto",
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3.3-70b-instruct",
    )


class PerplexityAdapter(OpenAICompatibleAdapter):
    name = "perplexity"
    display_name = "Perplexity"
    base_url = "https://api.perplexity.ai/chat/completions"
    models_url = "https://api.perplexity.ai/models"
    default_models = (
        "sonar",
        "sonar-pro",
        "sonar-reasoning",
    )


class XAIAdapter(OpenAICompatibleAdapter):
    name = "xai"
    display_name = "xAI (Grok)"
    base_url = "https://api.x.ai/v1/chat/completions"
    models_url = "https://api.x.ai/v1/models"
    default_models = (
        "grok-2-1212",
        "grok-2-vision-1212",
        "grok-beta",
    )


class FireworksAdapter(OpenAICompatibleAdapter):
    name = "fireworks"
    display_name = "Fireworks AI"
    base_url = "https://api.fireworks.ai/inference/v1/chat/completions"
    models_url = "https://api.fireworks.ai/inference/v1/models"
    default_models = (
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/deepseek-r1",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
    )


class SambaNovaAdapter(OpenAICompatibleAdapter):
    name = "sambanova"
    display_name = "SambaNova"
    base_url = "https://api.sambanova.ai/v1/chat/completions"
    models_url = "https://api.sambanova.ai/v1/models"
    default_models = (
        "Meta-Llama-3.3-70B-Instruct",
        "Qwen2.5-72B-Instruct",
        "DeepSeek-R1",
    )


class CohereAdapter(OpenAICompatibleAdapter):
    name = "cohere"
    display_name = "Cohere"
    base_url = "https://api.cohere.com/v2/chat"
    models_url = "https://api.cohere.com/v1/models"
    default_models = (
        "command-r-plus-08-2024",
        "command-r-08-2024",
    )
