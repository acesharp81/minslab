"""Index current source counts and actual-start candidate lookups."""
from alembic import op

revision = '0014_raw_collection_indexes'
down_revision = '0013_loading_performance'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    with op.get_context().autocommit_block():
        op.execute("SET maintenance_work_mem='32MB'")
        op.execute('SET max_parallel_maintenance_workers=0')
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_current_source '
                   'ON home_revision (source_id) WHERE superseded_at IS NULL')
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_general_actual_start "
                   "ON home_revision ((CAST((payload -> 'dates') ->> '실제착공일 (realStcnsDay)' AS VARCHAR))) "
                   "WHERE kind='general_permit' AND superseded_at IS NULL")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_home_general_actual_start')
        op.execute('DROP INDEX IF EXISTS ix_home_current_source')
