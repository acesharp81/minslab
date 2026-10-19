"""Bound raw revision churn and keep index-only count visibility current."""
from alembic import op

revision = '0013_loading_performance'
down_revision = '0012_collection_lease_token'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE home_revision SET (autovacuum_vacuum_scale_factor=0.02, '
                   'autovacuum_vacuum_threshold=5000, autovacuum_vacuum_insert_scale_factor=0.02, '
                   'autovacuum_vacuum_insert_threshold=5000, autovacuum_analyze_scale_factor=0.02)')
        with op.get_context().autocommit_block():
            # The database container has a small /dev/shm; serial maintenance
            # avoids parallel index/vacuum shared-memory allocation failures.
            op.execute("SET maintenance_work_mem='32MB'")
            op.execute('SET max_parallel_maintenance_workers=0')
            op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_revision_kind_recorded '
                       'ON home_revision (kind, recorded_at DESC)')
    else:
        op.execute('CREATE INDEX IF NOT EXISTS ix_home_revision_kind_recorded '
                   'ON home_revision (kind, recorded_at DESC)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_revision_kind_recorded')
