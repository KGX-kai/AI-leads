"""Persistent key identity, command receipts and backup results."""

from alembic import op
import sqlalchemy as sa

revision = "20261030_reliability"
down_revision = "4f162dbfa398"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "key_metadata",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("key_ref", sa.String, nullable=False),
        sa.Column("sentinel", sa.String, nullable=False),
    )
    op.create_table(
        "operation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("request_id", sa.String, nullable=False),
        sa.Column("payload_hash", sa.String, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.UniqueConstraint("actor", "action", "request_id"),
    )
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("filename", sa.String, nullable=False),
    )


def downgrade():
    raise RuntimeError("使用已验证的升级前备份回退，禁止丢弃运行记录")
