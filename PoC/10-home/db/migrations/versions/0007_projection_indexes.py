"""Indexes for change detection, historical mapping rewind and latest batches."""
from alembic import op
from sqlalchemy import text

revision = '0007_projection_indexes'
down_revision = '0006_identity_plan'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_home_revision_recorded': ('home_revision', ['recorded_at DESC']),
    'ix_home_audit_entity_recorded': ('home_audit', ['entity_id', 'recorded_at DESC']),
    'ix_home_batch_status_source_started': ('home_batch', ['status', 'source_id', 'started_at DESC']),
}


def create_indexes(online=False):
    for name, (table, columns) in INDEXES.items():
        op.create_index(name, table, [text(column) for column in columns],
                        if_not_exists=True, postgresql_concurrently=online)


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            create_indexes(True)
    else:
        create_indexes()


def downgrade():
    for name in INDEXES:
        op.drop_index(name, if_exists=True)
