"""Preserve identities across explicit corrections and merges."""
from alembic import op
import sqlalchemy as sa

revision="20261030_project_aliases"
down_revision="bbad41c2a094"
branch_labels=depends_on=None


def upgrade():
    op.create_table("project_aliases",sa.Column("id",sa.String(36),primary_key=True),
                    sa.Column("created_at",sa.String,nullable=False),sa.Column("identity_key",sa.String,nullable=False,unique=True),
                    sa.Column("project_id",sa.String(36),sa.ForeignKey("projects.id"),nullable=False))
    op.create_index("ix_project_aliases_project_id","project_aliases",["project_id"])


def downgrade():
    raise RuntimeError("使用升级前备份隔离恢复，不删除身份关系")
