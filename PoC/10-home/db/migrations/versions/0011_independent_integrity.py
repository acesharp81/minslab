"""Independent snapshots, remediation rounds, and durable per-source jobs."""
from alembic import op
from backend.db import MetricSnapshot, IntegrityRound, CollectionJob

revision = '0011_independent_integrity'
down_revision = '0010_cache_change_indexes'
branch_labels = None
depends_on = None


def upgrade():
    for table in (MetricSnapshot.__table__, IntegrityRound.__table__, CollectionJob.__table__):
        table.create(op.get_bind(), checkfirst=True)


def downgrade():
    # Historical evidence is retained even when rolling back the application.
    pass
