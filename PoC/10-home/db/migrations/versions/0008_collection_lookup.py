"""Indexed persisted evidence versions; online build for the large source table."""
from alembic import op

revision = '0008_collection_lookup'
down_revision = '0007_projection_indexes'
branch_labels = None
depends_on = None


def upgrade():
    sql = 'CREATE INDEX {online}IF NOT EXISTS ix_home_revision_entity_version ON home_revision (entity_id, revision_no DESC)'
    if op.get_bind().dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute(sql.format(online='CONCURRENTLY '))
    else:
        op.execute(sql.format(online=''))


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_revision_entity_version')
