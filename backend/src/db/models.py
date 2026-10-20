import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


JsonType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    credentials: Mapped[list["Credential"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    workers: Mapped[list["Worker"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    catalog_models: Mapped[list["ProviderModel"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    masked_identifier: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    credential_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    last_health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[Provider] = relationship(back_populates="credentials")
    workers: Mapped[list["Worker"]] = relationship(back_populates="credential", cascade="all, delete-orphan")


class Worker(Base, TimestampMixin):
    __tablename__ = "workers"
    __table_args__ = (UniqueConstraint("provider_id", "credential_id", "model", name="uq_worker_provider_credential_model"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credentials.id", ondelete="CASCADE"), index=True)
    provider_model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provider_models.id", ondelete="SET NULL"), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(160), index=True)
    worker_type: Mapped[str] = mapped_column(String(32), default="cloud")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    capabilities: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[Provider] = relationship(back_populates="workers")
    credential: Mapped[Credential] = relationship(back_populates="workers")
    provider_model: Mapped["ProviderModel | None"] = relationship(back_populates="workers")


class ProviderModel(Base):
    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider_id", "external_model_id", name="uq_provider_model_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    external_model_id: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_modalities: Mapped[list[str]] = mapped_column(JsonType, default=list)
    output_modalities: Mapped[list[str]] = mapped_column(JsonType, default=list)
    streaming: Mapped[bool] = mapped_column(Boolean, default=False)
    tool_calling: Mapped[bool] = mapped_column(Boolean, default=False)
    structured_output: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning: Mapped[bool] = mapped_column(Boolean, default=False)
    catalog_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[Provider] = relationship(back_populates="catalog_models")
    workers: Mapped[list[Worker]] = relationship(back_populates="provider_model")


class RequestMetric(Base):
    __tablename__ = "request_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer)
    output_tokens_per_second: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    value_saved_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paid_key: Mapped[bool] = mapped_column(Boolean, default=False)
    gateway_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gateway_api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuotaSnapshot(Base):
    __tablename__ = "quota_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    requests_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="unknown")


class HealthEvent(Base):
    __tablename__ = "health_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    candidate_workers: Mapped[list[str]] = mapped_column(JsonType, default=list)
    selected_worker: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_reason: Mapped[str] = mapped_column(String(240))
    routing_version: Mapped[str] = mapped_column(String(40), default="phase1-deterministic-v1")

    # Phase 2A additions
    policy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    predicted_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_metadata: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    execution_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    execution_node_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)


class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    execution_mode: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_nodes: Mapped[int] = mapped_column(Integer, default=0)
    failed_nodes: Mapped[int] = mapped_column(Integer, default=0)
    max_parallelism: Mapped[int] = mapped_column(Integer, default=1)
    total_execution_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    nodes: Mapped[list["ExecutionNode"]] = relationship(back_populates="execution_run", cascade="all, delete-orphan")


class ExecutionNode(Base):
    __tablename__ = "execution_nodes"
    __table_args__ = (UniqueConstraint("execution_run_id", "node_id", name="uq_execution_node_run_node"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution_runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(80), index=True)
    node_type: Mapped[str] = mapped_column(String(40))
    depends_on: Mapped[list[str]] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(40), index=True)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    execution_run: Mapped[ExecutionRun] = relationship(back_populates="nodes")

class AdminUser(Base):
    __tablename__ = 'admin_users'

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminSession(Base):
    __tablename__ = 'admin_sessions'

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GatewayApiKey(Base):
    __tablename__ = 'gateway_api_keys'

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    encrypted_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_selection_mode: Mapped[str] = mapped_column(String(32), default="AUTO")
    routing_policy: Mapped[str] = mapped_column(String(40), default="balanced")
    specific_worker_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    allowed_worker_ids: Mapped[list[str] | None] = mapped_column(JsonType, nullable=True)
    allowed_model_groups: Mapped[list[str] | None] = mapped_column(JsonType, nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True, default=120)
    max_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    spend_usd: Mapped[float] = mapped_column(Float, default=0.0)
    value_saved_usd: Mapped[float] = mapped_column(Float, default=0.0)
    budget_reset_period: Mapped[str] = mapped_column(String(20), default="monthly")
    budget_exceeded_action: Mapped[str] = mapped_column(String(24), default="hard_cap")
    budget_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    spend_velocity_limit_usd: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    spend_velocity_window_sec: Mapped[int] = mapped_column(Integer, default=300)

    @property
    def is_active(self) -> bool:
        return self.enabled and self.revoked_at is None




class WorkflowRun(Base, TimestampMixin):
    """Historical execution record for a workflow run."""

    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_definition_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    execution_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default="PENDING")
    execution_mode: Mapped[str] = mapped_column(String(24), default="DAG", index=True)
    routing_policy: Mapped[str] = mapped_column(String(40), default="balanced")

    # Distinct requested vs executed model and execution facts
    requested_model: Mapped[str] = mapped_column(String(160), index=True)
    executed_model: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_sequence_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan", order_by="WorkflowEvent.logical_sequence"
    )
    attempts: Mapped[list["TaskAttempt"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan", order_by="TaskAttempt.attempt_number"
    )
    metrics: Mapped["WorkflowMetrics | None"] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan", uselist=False
    )


class WorkflowEvent(Base):
    """Immutable, strongly typed event for deterministic replay and audit."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "logical_sequence", name="uq_workflow_event_run_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    logical_sequence: Mapped[int] = mapped_column(Integer, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="events")


class TaskAttempt(Base):
    """Explicit attempt-level record for tracking retries, durations, and errors."""

    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "task_id", "attempt_number", name="uq_task_attempt_run_task_attempt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(80), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="attempts")


class WorkflowMetrics(Base):
    """Calculated execution and performance metrics for a workflow run."""

    __tablename__ = "workflow_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), index=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)

    wall_clock_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_task_execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    critical_path_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    successful_critical_path_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_wait_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workflow_queue_wait_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_queue_wait_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduler_overhead_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orchestration_gap_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synthesis_overhead_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telemetry_overhead_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_overhead_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent_tasks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parallelism_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_speedup_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    total_retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries_per_task: Mapped[int] = mapped_column(Integer, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    successful_after_retry_count: Mapped[int] = mapped_column(Integer, default=0)

    metrics_metadata: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="metrics")
