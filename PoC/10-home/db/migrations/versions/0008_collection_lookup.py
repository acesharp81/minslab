"""Indexed persisted evidence versions; online build for the large source table."""
from alembic import op

revision = '0008_collection_lookup'
down_revision = '0007_projection_indexes'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_revision_entity_version ON home_revision (entity_id, revision_no DESC)')
    else:
        op.execute('CREATE INDEX IF NOT EXISTS ix_home_revision_entity_version ON home_revision (entity_id, revision_no DESC)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_revision_entity_version')
