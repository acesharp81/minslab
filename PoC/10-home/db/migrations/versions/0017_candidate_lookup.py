"""Index current permit candidate lookups without blocking ingestion/readers."""
from alembic import op
from sqlalchemy import text

revision = '0017_candidate_lookup'
down_revision = '0016_source_profile_cover'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'postgresql': return
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    with op.get_context().autocommit_block():
        op.execute("SET maintenance_work_mem='32MB'")
        op.execute('SET max_parallel_maintenance_workers=0')
        indexes = {
            'ix_home_permit_name_trgm': "USING gin (sample_name gin_trgm_ops)",
            'ix_home_permit_address': "(sample_region, (CAST(payload->>'address' AS VARCHAR)))",
        }
        for name, definition in indexes.items():
            valid = op.get_bind().execute(text(
                'SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)'), {'name': name}).scalar()
            if valid is False:
                op.execute(f'DROP INDEX CONCURRENTLY {name}')
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON home_revision {definition} '
                       "WHERE kind='permit' AND superseded_at IS NULL")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('ix_home_permit_name_trgm', 'ix_home_permit_address'):
            op.execute(f'DROP INDEX IF EXISTS {name}')
