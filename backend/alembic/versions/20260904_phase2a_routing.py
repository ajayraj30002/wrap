"""Phase 2A routing intelligence columns

Revision ID: 20260904_phase2a_routing
Revises: 91d56c6be4f6
Create Date: 2026-09-04

Adds columns to routing_decisions for:
- policy (routing policy used)
- predicted_latency_ms / predicted_ttft_ms (prediction data)
- prediction_confidence (sample-size-based confidence)
- decision_metadata (full structured explanation JSON)

These are all nullable to preserve backward compatibility with
existing Phase 1 routing decisions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260904_phase2a_routing"
down_revision = "91d56c6be4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("routing_decisions", sa.Column("policy", sa.String(40), nullable=True))
    op.add_column("routing_decisions", sa.Column("predicted_latency_ms", sa.Integer(), nullable=True))
    op.add_column("routing_decisions", sa.Column("predicted_ttft_ms", sa.Integer(), nullable=True))
    op.add_column("routing_decisions", sa.Column("prediction_confidence", sa.Float(), nullable=True))
    op.add_column("routing_decisions", sa.Column("decision_metadata", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("routing_decisions", "decision_metadata")
    op.drop_column("routing_decisions", "prediction_confidence")
    op.drop_column("routing_decisions", "predicted_ttft_ms")
    op.drop_column("routing_decisions", "predicted_latency_ms")
    op.drop_column("routing_decisions", "policy")
