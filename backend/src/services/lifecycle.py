import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.providers.base import ProviderError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


@dataclass
class RequestLifecycle:
    request_id: str
    streamed: bool
    started_at: datetime = field(default_factory=_now)
    first_token_at: datetime | None = None
    completed_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    status: str = "started"
    error_type: str | None = None
    error_message_sanitized: str | None = None

    has_exact_usage: bool = False

    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = _now()

    def apply_usage(self, usage: dict[str, int | None] | None) -> None:
        if not usage:
            return
        if usage.get("input_tokens") is not None:
            self.input_tokens = usage["input_tokens"]
        if usage.get("output_tokens") is not None:
            self.output_tokens = usage["output_tokens"]
            self.has_exact_usage = True
        if usage.get("total_tokens") is not None:
            self.total_tokens = usage["total_tokens"]

    def estimate_output_tokens_from_text(self, text: str) -> None:
        if self.has_exact_usage:
            return
        estimated = max(1, len(text) // 4) if text else 0
        self.output_tokens = (self.output_tokens or 0) + estimated

    def complete(self, status: str = "success") -> None:
        if self.status == "success" and status == "stream_interrupted":
            return
        self.status = status
        self.completed_at = _now()

    def fail(self, exc: Exception) -> None:
        self.status = "error"
        if isinstance(exc, ProviderError):
            self.error_type = exc.error_type
            self.error_message_sanitized = str(exc)[:500]
        else:
            self.error_type = type(exc).__name__
            self.error_message_sanitized = "Unexpected request failure"
        self.completed_at = _now()


    @property
    def total_latency_ms(self) -> int:
        completed = self.completed_at or _now()
        return _ms(self.started_at, completed)

    @property
    def error_message(self) -> str | None:
        return self.error_message_sanitized

    def snapshot(self) -> dict[str, Any]:
        completed = self.completed_at or _now()
        ttft_ms = _ms(self.started_at, self.first_token_at) if self.first_token_at else None
        generation_ms = _ms(self.first_token_at, completed) if self.first_token_at else None
        total_latency_ms = _ms(self.started_at, completed)
        tps = None
        if self.output_tokens and generation_ms and generation_ms > 0:
            tps = int(self.output_tokens / (generation_ms / 1000))
        return {
            "started_at": self.started_at,
            "first_token_at": self.first_token_at,
            "completed_at": completed,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "ttft_ms": ttft_ms,
            "generation_ms": generation_ms,
            "total_latency_ms": total_latency_ms,
            "output_tokens_per_second": tps,
            "status": self.status,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "streamed": self.streamed,
        }
