"""Phase 2B orchestration, model catalog, and API-key scope

Revision ID: 20260913_phase2b
Revises: 20260904_phase2a_routing
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260913_phase2b"
down_revision = "20260904_phase2a_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("external_model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("input_modalities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_modalities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("streaming", sa.Boolean(), nullable=False),
        sa.Column("tool_calling", sa.Boolean(), nullable=False),
        sa.Column("structured_output", sa.Boolean(), nullable=False),
        sa.Column("reasoning", sa.Boolean(), nullable=False),
        sa.Column("catalog_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_model_id", name="uq_provider_model_external_id"),
    )
    op.create_index(op.f("ix_provider_models_external_model_id"), "provider_models", ["external_model_id"], unique=False)
    op.create_index(op.f("ix_provider_models_provider_id"), "provider_models", ["provider_id"], unique=False)
    op.create_index(op.f("ix_provider_models_status"), "provider_models", ["status"], unique=False)

    op.add_column("workers", sa.Column("provider_model_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_workers_provider_model_id"), "workers", ["provider_model_id"], unique=False)
    op.create_foreign_key("fk_workers_provider_model_id_provider_models", "workers", "provider_models", ["provider_model_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "execution_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("execution_mode", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("completed_nodes", sa.Integer(), nullable=False),
        sa.Column("failed_nodes", sa.Integer(), nullable=False),
        sa.Column("max_parallelism", sa.Integer(), nullable=False),
        sa.Column("total_execution_ms", sa.Integer(), nullable=True),
        sa.Column("run_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_execution_runs_execution_mode"), "execution_runs", ["execution_mode"], unique=False)
    op.create_index(op.f("ix_execution_runs_request_id"), "execution_runs", ["request_id"], unique=False)
    op.create_index(op.f("ix_execution_runs_status"), "execution_runs", ["status"], unique=False)

    op.create_table(
        "execution_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=80), nullable=False),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("depends_on", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_token_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("node_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["execution_run_id"], ["execution_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_run_id", "node_id", name="uq_execution_node_run_node"),
    )
    op.create_index(op.f("ix_execution_nodes_execution_run_id"), "execution_nodes", ["execution_run_id"], unique=False)
    op.create_index(op.f("ix_execution_nodes_node_id"), "execution_nodes", ["node_id"], unique=False)
    op.create_index(op.f("ix_execution_nodes_status"), "execution_nodes", ["status"], unique=False)
    op.create_index(op.f("ix_execution_nodes_worker_id"), "execution_nodes", ["worker_id"], unique=False)

    op.add_column("routing_decisions", sa.Column("execution_run_id", sa.Uuid(), nullable=True))
    op.add_column("routing_decisions", sa.Column("execution_node_id", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_routing_decisions_execution_run_id"), "routing_decisions", ["execution_run_id"], unique=False)
    op.create_index(op.f("ix_routing_decisions_execution_node_id"), "routing_decisions", ["execution_node_id"], unique=False)

    op.add_column("gateway_api_keys", sa.Column("worker_selection_mode", sa.String(length=32), nullable=False, server_default="AUTO"))
    op.add_column("gateway_api_keys", sa.Column("routing_policy", sa.String(length=40), nullable=False, server_default="balanced"))
    op.add_column("gateway_api_keys", sa.Column("specific_worker_id", sa.Uuid(), nullable=True))
    op.add_column("gateway_api_keys", sa.Column("allowed_worker_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("gateway_api_keys", "allowed_worker_ids")
    op.drop_column("gateway_api_keys", "specific_worker_id")
    op.drop_column("gateway_api_keys", "routing_policy")
    op.drop_column("gateway_api_keys", "worker_selection_mode")
    op.drop_index(op.f("ix_routing_decisions_execution_node_id"), table_name="routing_decisions")
    op.drop_index(op.f("ix_routing_decisions_execution_run_id"), table_name="routing_decisions")
    op.drop_column("routing_decisions", "execution_node_id")
    op.drop_column("routing_decisions", "execution_run_id")
    op.drop_table("execution_nodes")
    op.drop_table("execution_runs")
    op.drop_constraint("fk_workers_provider_model_id_provider_models", "workers", type_="foreignkey")
    op.drop_index(op.f("ix_workers_provider_model_id"), table_name="workers")
    op.drop_column("workers", "provider_model_id")
    op.drop_table("provider_models")
