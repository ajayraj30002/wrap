"""phase1 foundation

Revision ID: 20260829_0001
Revises:
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260829_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_providers_name"), "providers", ["name"], unique=True)
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("masked_identifier", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("credential_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_health_status", sa.String(length=32), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_credentials_provider_id"), "credentials", ["provider_id"])
    op.create_table(
        "workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("worker_type", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider_id", "credential_id", "model", name="uq_worker_provider_credential_model"),
    )
    op.create_index(op.f("ix_workers_credential_id"), "workers", ["credential_id"])
    op.create_index(op.f("ix_workers_model"), "workers", ["model"])
    op.create_index(op.f("ix_workers_provider_id"), "workers", ["provider_id"])
    op.create_table(
        "request_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_token_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("generation_ms", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("output_tokens_per_second", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("error_message_sanitized", sa.Text(), nullable=True),
        sa.Column("streamed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_request_metrics_request_id"), "request_metrics", ["request_id"])
    op.create_index(op.f("ix_request_metrics_status"), "request_metrics", ["status"])
    op.create_index(op.f("ix_request_metrics_worker_id"), "request_metrics", ["worker_id"])
    op.create_table(
        "quota_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests_remaining", sa.Integer(), nullable=True),
        sa.Column("requests_limit", sa.Integer(), nullable=True),
        sa.Column("tokens_remaining", sa.Integer(), nullable=True),
        sa.Column("tokens_limit", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_quota_snapshots_timestamp"), "quota_snapshots", ["timestamp"])
    op.create_index(op.f("ix_quota_snapshots_worker_id"), "quota_snapshots", ["worker_id"])
    op.create_table(
        "health_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_health_events_timestamp"), "health_events", ["timestamp"])
    op.create_index(op.f("ix_health_events_worker_id"), "health_events", ["worker_id"])
    op.create_table(
        "routing_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_workers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_worker", sa.String(length=80), nullable=True),
        sa.Column("decision_reason", sa.String(length=240), nullable=False),
        sa.Column("routing_version", sa.String(length=40), nullable=False),
    )
    op.create_index(op.f("ix_routing_decisions_request_id"), "routing_decisions", ["request_id"])
    op.create_index(op.f("ix_routing_decisions_timestamp"), "routing_decisions", ["timestamp"])


def downgrade() -> None:
    op.drop_table("routing_decisions")
    op.drop_table("health_events")
    op.drop_table("quota_snapshots")
    op.drop_table("request_metrics")
    op.drop_table("workers")
    op.drop_table("credentials")
    op.drop_table("providers")
