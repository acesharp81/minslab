"""Cover current observation count/year predicates using compact metadata only."""
from alembic import op
revision='0003_observation_counts'
down_revision='0002_observation_fields'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('CREATE INDEX IF NOT EXISTS ix_home_sample_counts ON home_revision (kind,sample_source_date,sample_event_day,sample_region) INCLUDE (recorded_at,sample_base_date) WHERE superseded_at IS NULL')


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_sample_counts')
