"""0.5.0: business profile, source channel, bid deadline and stage age.

Owner-maintained channel list and stall thresholds are seeded as settings data. Runtime code
reads these rows directly so an empty or damaged settings table fails closed.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "20261124_marketing_fields"
down_revision = "20261117_candidate_quality"
branch_labels = depends_on = None

DEFAULT_SOURCE_CHANNELS = ["招投标", "物业协会", "抖音同城", "CABEP", "展会", "名单池", "竞品客户", "转介绍"]
DEFAULT_STALL_DAYS = {"EMC": 30, "买断": 7, "未定": 14}


def _seed_setting(connection, key, value):
    connection.execute(
        sa.text(
            "INSERT INTO settings (key, value) "
            "SELECT :key, :value "
            "WHERE NOT EXISTS (SELECT 1 FROM settings WHERE key = :key)"
        ),
        {"key": key, "value": json.dumps(value, ensure_ascii=False)},
    )


def upgrade():
    with op.batch_alter_table("candidates") as batch:
        batch.add_column(sa.Column("source_channel", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("bid_deadline", sa.String(), nullable=True))
    with op.batch_alter_table("opportunities") as batch:
        batch.add_column(sa.Column("stage_entered_at", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("bid_deadline", sa.String(), nullable=True))
        batch.add_column(sa.Column("source_channel", sa.String(), nullable=False, server_default=""))
    with op.batch_alter_table("inquiries") as batch:
        batch.add_column(sa.Column("annual_power_cost", sa.String(), nullable=True))
        batch.add_column(sa.Column("source_channel", sa.String(), nullable=False, server_default=""))
    op.execute("UPDATE opportunities SET stage_entered_at = created_at WHERE stage_entered_at = ''")
    connection = op.get_bind()
    _seed_setting(connection, "source_channels", DEFAULT_SOURCE_CHANNELS)
    _seed_setting(connection, "stall_days", DEFAULT_STALL_DAYS)


def downgrade():
    with op.batch_alter_table("inquiries") as batch:
        batch.drop_column("source_channel")
        batch.drop_column("annual_power_cost")
    with op.batch_alter_table("opportunities") as batch:
        batch.drop_column("source_channel")
        batch.drop_column("bid_deadline")
        batch.drop_column("stage_entered_at")
    with op.batch_alter_table("candidates") as batch:
        batch.drop_column("bid_deadline")
        batch.drop_column("source_channel")
    op.execute(
        sa.text("DELETE FROM settings WHERE key IN ('source_channels', 'stall_days')")
    )
