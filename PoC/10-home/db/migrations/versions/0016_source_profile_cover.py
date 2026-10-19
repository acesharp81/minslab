"""Cover source profile counts without reading large JSON records."""
from alembic import op
from sqlalchemy import text
revision = '0016_source_profile_cover'
down_revision = '0015_delivery_cache_version'
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != 'postgresql': return
    with op.get_context().autocommit_block():
        op.execute("SET maintenance_work_mem='32MB'")
        op.execute('SET max_parallel_maintenance_workers=0')
        valid = op.get_bind().execute(text("SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass('ix_home_source_profile')")).scalar()
        if valid is False:
            op.execute('DROP INDEX CONCURRENTLY ix_home_source_profile')
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_source_profile '
                   'ON home_revision (source_id, kind, recorded_at) INCLUDE (entity_id) '
                   'WHERE superseded_at IS NULL')

def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP INDEX IF EXISTS ix_home_source_profile')
