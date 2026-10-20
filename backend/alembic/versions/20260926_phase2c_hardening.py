"""Phase 2C hardening: transactional event sequence counter, separated metrics, and performance indexes.

Revision ID: 20260926_phase2c_hardening
Revises: 20260925_phase2c
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


revision = "20260926_phase2c_hardening"
down_revision = "20260925_phase2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add event_sequence_counter to workflow_runs for multi-process sequence coordination
    op.add_column(
        "workflow_runs",
        sa.Column("event_sequence_counter", sa.Integer(), nullable=False, server_default="0"),
    )
    # 2. Add performance query indexes on execution facts
    op.create_index(op.f("ix_workflow_runs_executed_model"), "workflow_runs", ["executed_model"], unique=False)
    op.create_index(op.f("ix_workflow_runs_provider"), "workflow_runs", ["provider"], unique=False)
    op.create_index(op.f("ix_task_attempts_provider"), "task_attempts", ["provider"], unique=False)
    op.create_index(op.f("ix_task_attempts_model"), "task_attempts", ["model"], unique=False)

    # 3. Add separated and instrumented metric columns to workflow_metrics
    op.add_column("workflow_metrics", sa.Column("workflow_queue_wait_ms", sa.Integer(), nullable=True))
    op.add_column("workflow_metrics", sa.Column("task_queue_wait_ms", sa.Integer(), nullable=True))
    op.add_column("workflow_metrics", sa.Column("orchestration_gap_ms", sa.Integer(), nullable=True))
    op.add_column("workflow_metrics", sa.Column("synthesis_overhead_ms", sa.Integer(), nullable=True))
    op.add_column("workflow_metrics", sa.Column("telemetry_overhead_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    # 1. Drop metric columns from workflow_metrics
    op.drop_column("workflow_metrics", "telemetry_overhead_ms")
    op.drop_column("workflow_metrics", "synthesis_overhead_ms")
    op.drop_column("workflow_metrics", "orchestration_gap_ms")
    op.drop_column("workflow_metrics", "task_queue_wait_ms")
    op.drop_column("workflow_metrics", "workflow_queue_wait_ms")

    # 2. Drop indexes
    op.drop_index(op.f("ix_task_attempts_model"), table_name="task_attempts")
    op.drop_index(op.f("ix_task_attempts_provider"), table_name="task_attempts")
    op.drop_index(op.f("ix_workflow_runs_provider"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_executed_model"), table_name="workflow_runs")

    # 3. Drop event_sequence_counter from workflow_runs
    op.drop_column("workflow_runs", "event_sequence_counter")
