"""Cover latest-change probes used by all read caches."""
from alembic import op
from sqlalchemy import column as sql_column
revision = '0010_cache_change_indexes'
down_revision = '0009_parcel_parent'
branch_labels = None
depends_on = None


def upgrade():
    indexes = [('ix_home_audit_recorded', 'home_audit', 'recorded_at'),
               ('ix_home_batch_finished', 'home_batch', 'finished_at')]
    def create(online=False):
        for name, table, column in indexes:
            op.create_index(name, table, [sql_column(column).desc()], if_not_exists=True, postgresql_concurrently=online)
    if op.get_bind().dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            create(True)
    else:
        create()


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_audit_recorded')
    op.execute('DROP INDEX IF EXISTS ix_home_batch_finished')
