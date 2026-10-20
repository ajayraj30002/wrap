"""Phase 2C analytics, event history, and deterministic replay

Revision ID: 20260925_phase2c
Revises: 20260913_phase2b
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260925_phase2c"
down_revision = "20260913_phase2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. workflow_runs
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_id", sa.String(length=120), nullable=True),
        sa.Column("execution_run_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("execution_mode", sa.String(length=24), nullable=False),
        sa.Column("routing_policy", sa.String(length=40), nullable=False),
        sa.Column("requested_model", sa.String(length=160), nullable=False),
        sa.Column("executed_model", sa.String(length=160), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_metadata", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_run_id"], ["execution_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_runs_execution_mode"), "workflow_runs", ["execution_mode"], unique=False)
    op.create_index(op.f("ix_workflow_runs_execution_run_id"), "workflow_runs", ["execution_run_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_request_id"), "workflow_runs", ["request_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_requested_model"), "workflow_runs", ["requested_model"], unique=False)
    op.create_index(op.f("ix_workflow_runs_status"), "workflow_runs", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_runs_worker_id"), "workflow_runs", ["worker_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_workflow_definition_id"), "workflow_runs", ["workflow_definition_id"], unique=False)

    # 2. workflow_events
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=80), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("logical_sequence", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "logical_sequence", name="uq_workflow_event_run_seq"),
    )
    op.create_index(op.f("ix_workflow_events_event_type"), "workflow_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_workflow_events_logical_sequence"), "workflow_events", ["logical_sequence"], unique=False)
    op.create_index(op.f("ix_workflow_events_task_id"), "workflow_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_workflow_events_timestamp"), "workflow_events", ["timestamp"], unique=False)
    op.create_index(op.f("ix_workflow_events_workflow_run_id"), "workflow_events", ["workflow_run_id"], unique=False)

    # 3. task_attempts
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=80), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_metadata", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "task_id", "attempt_number", name="uq_task_attempt_run_task_attempt"),
    )
    op.create_index(op.f("ix_task_attempts_status"), "task_attempts", ["status"], unique=False)
    op.create_index(op.f("ix_task_attempts_task_id"), "task_attempts", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_attempts_worker_id"), "task_attempts", ["worker_id"], unique=False)
    op.create_index(op.f("ix_task_attempts_workflow_run_id"), "task_attempts", ["workflow_run_id"], unique=False)

    # 4. workflow_metrics
    op.create_table(
        "workflow_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("is_partial", sa.Boolean(), nullable=False),
        sa.Column("wall_clock_duration_ms", sa.Integer(), nullable=True),
        sa.Column("total_task_execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("critical_path_duration_ms", sa.Integer(), nullable=True),
        sa.Column("successful_critical_path_duration_ms", sa.Integer(), nullable=True),
        sa.Column("queue_wait_time_ms", sa.Integer(), nullable=True),
        sa.Column("scheduler_overhead_ms", sa.Integer(), nullable=True),
        sa.Column("retry_overhead_ms", sa.Integer(), nullable=True),
        sa.Column("max_concurrent_tasks", sa.Integer(), nullable=True),
        sa.Column("parallelism_factor", sa.Float(), nullable=True),
        sa.Column("observed_speedup_ratio", sa.Float(), nullable=True),
        sa.Column("total_attempts", sa.Integer(), nullable=False),
        sa.Column("total_retries", sa.Integer(), nullable=False),
        sa.Column("max_retries_per_task", sa.Integer(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("successful_after_retry_count", sa.Integer(), nullable=False),
        sa.Column("metrics_metadata", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_metrics_status"), "workflow_metrics", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_metrics_workflow_run_id"), "workflow_metrics", ["workflow_run_id"], unique=True)


def downgrade() -> None:
    op.drop_table("workflow_metrics")
    op.drop_table("task_attempts")
    op.drop_table("workflow_events")
    op.drop_table("workflow_runs")
