from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProviderRead(BaseModel):
    id: UUID
    name: str
    display_name: str
    enabled: bool
    metadata: dict[str, Any]


class CredentialCreate(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=1)
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class CredentialRead(BaseModel):
    id: UUID
    provider_id: UUID
    provider: str
    name: str
    masked_identifier: str
    enabled: bool
    metadata: dict[str, Any]
    last_health_status: str | None
    last_health_check_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkerPatch(BaseModel):
    enabled: bool | None = None
    health_status: str | None = None
    capabilities: dict[str, Any] | None = None


class WorkerCreate(BaseModel):
    credential_id: UUID
    provider_model_id: UUID
    enabled: bool = True


class WorkerRead(BaseModel):
    id: UUID
    provider: str
    provider_id: UUID
    credential_id: UUID
    credential_name: str
    masked_identifier: str | None = None
    model: str
    worker_type: str
    enabled: bool
    health_status: str
    capabilities: dict[str, Any]
    provider_model_id: UUID | None = None
    catalog_status: str = "UNKNOWN"
    last_used_at: datetime | None
    p50_latency_ms: int | None = None
    requests_per_second: float | None = None
    quota_remaining_pct: int | None = None
    load_pct: int | None = None
    active_requests: int = 0
    total_requests: int = 0


class ProviderModelRead(BaseModel):
    id: UUID
    provider_id: UUID
    provider: str
    external_model_id: str
    display_name: str
    status: str
    capabilities: dict[str, Any]
    context_window: int | None
    max_output_tokens: int | None
    input_modalities: list[str]
    output_modalities: list[str]
    streaming: bool
    tool_calling: bool
    structured_output: bool
    reasoning: bool
    last_seen_at: datetime
    last_verified_at: datetime | None


class QuotaSnapshotCreate(BaseModel):
    worker_id: UUID
    requests_remaining: int | None = None
    requests_limit: int | None = None
    tokens_remaining: int | None = None
    tokens_limit: int | None = None
    reset_at: datetime | None = None
    source: str = "unknown"
