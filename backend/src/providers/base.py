from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool = True
    response_format: bool = False
    stop: bool = True
    max_completion_tokens: bool = False
    top_p: bool = True
    tool_calling: bool = False


@dataclass
class ProviderCompletion:
    response: dict[str, Any]
    usage: dict[str, int | None]
    quota: dict[str, Any] | None = None


@dataclass
class ProviderStreamEvent:
    payload: dict[str, Any] | None = None
    done: bool = False
    usage: dict[str, int | None] | None = None
    quota: dict[str, Any] | None = None


@dataclass
class ProviderModel:
    external_model_id: str
    display_name: str
    status: str = "ACTIVE"
    capabilities: dict[str, Any] = field(default_factory=dict)
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_modalities: list[str] = field(default_factory=lambda: ["text"])
    output_modalities: list[str] = field(default_factory=lambda: ["text"])
    streaming: bool = True
    tool_calling: bool = False
    structured_output: bool = False
    reasoning: bool = False
    catalog_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    error_type = "provider_error"
    status_code = 502

    def __init__(self, message: str, *, provider_status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider_status_code = provider_status_code


class AuthenticationError(ProviderError):
    error_type = "authentication_error"
    status_code = 401


class RateLimitError(ProviderError):
    error_type = "rate_limit_error"
    status_code = 429


class ProviderUnavailableError(ProviderError):
    error_type = "provider_unavailable"
    status_code = 503


class TimeoutError(ProviderError):
    error_type = "timeout"
    status_code = 504


class InvalidRequestError(ProviderError):
    error_type = "invalid_request_error"
    status_code = 400


class ModelNotFoundError(ProviderError):
    error_type = "model_not_found"
    status_code = 404


class StreamingError(ProviderError):
    error_type = "streaming_error"
    status_code = 502


class InternalError(ProviderError):
    error_type = "internal_error"
    status_code = 500


class ProviderAdapter(ABC):
    name: str
    display_name: str
    default_models: tuple[str, ...]
    capabilities: ProviderCapabilities

    @abstractmethod
    def normalize_request(self, request: dict[str, Any], model: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def create_completion(
        self,
        request: dict[str, Any],
        *,
        api_key: str,
        model: str,
        request_id: str,
        timeout: float,
    ) -> ProviderCompletion:
        raise NotImplementedError

    @abstractmethod
    async def stream_completion(
        self,
        request: dict[str, Any],
        *,
        api_key: str,
        model: str,
        request_id: str,
        timeout: float,
    ) -> AsyncIterator[ProviderStreamEvent]:
        raise NotImplementedError

    async def test_credential(self, *, api_key: str, model: str, timeout: float) -> None:
        request = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "stream": False,
        }
        await self.create_completion(request, api_key=api_key, model=model, request_id="credential-test", timeout=timeout)

    async def list_models(self, *, api_key: str, timeout: float) -> list[ProviderModel]:
        raise NotImplementedError("Provider adapter does not support model catalog discovery")

    def normalize_error(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return TimeoutError("Provider request timed out")
        if isinstance(exc, httpx.ConnectError):
            return ProviderUnavailableError("Provider connection failed")
        # Remote closed the connection mid-request / mid-stream (e.g. Groq terminations)
        if isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError)):
            return ProviderUnavailableError(f"Provider connection terminated: {exc}")
        if isinstance(exc, httpx.WriteError):
            return ProviderUnavailableError("Provider connection write error")
        return ProviderUnavailableError("Provider request failed")

    def extract_quota(self, headers: httpx.Headers) -> dict[str, Any] | None:
        requests_remaining = headers.get("x-ratelimit-remaining-requests")
        requests_limit = headers.get("x-ratelimit-limit-requests")
        tokens_remaining = headers.get("x-ratelimit-remaining-tokens")
        tokens_limit = headers.get("x-ratelimit-limit-tokens")
        if not any([requests_remaining, requests_limit, tokens_remaining, tokens_limit]):
            return None
        return {
            "requests_remaining": _to_int(requests_remaining),
            "requests_limit": _to_int(requests_limit),
            "tokens_remaining": _to_int(tokens_remaining),
            "tokens_limit": _to_int(tokens_limit),
            "reset_at": None,
            "source": "response_header",
        }


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None
