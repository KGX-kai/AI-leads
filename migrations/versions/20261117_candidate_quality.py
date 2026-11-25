"""Candidate review date, public organization phone and separate source claims."""

import sqlalchemy as sa
from alembic import op

revision = "20261117_candidate_quality"
down_revision = "20261030_project_aliases"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "candidate_review_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("next_review_at", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
    )
    op.create_index("ix_candidate_review_events_candidate_id", "candidate_review_events", ["candidate_id"])
    with op.batch_alter_table("candidates") as batch:
        batch.add_column(sa.Column("org_phone", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("unknowns", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("next_review_at", sa.String(), nullable=True))
        batch.add_column(sa.Column("review_reason_code", sa.String(), nullable=False, server_default=""))
    with op.batch_alter_table("source_evidence") as batch:
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("claim", sa.Text(), nullable=False, server_default=""))
    op.execute("UPDATE source_evidence SET source_url = "
               "(SELECT source_url FROM candidates WHERE candidates.id = source_evidence.candidate_id) "
               "WHERE source_url = ''")


def downgrade():
    raise RuntimeError("使用升级前备份隔离恢复；禁止丢弃候选复核和来源证据")
