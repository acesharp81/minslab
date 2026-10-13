"""Indexes for change detection, historical mapping rewind and latest batches."""
from alembic import op

revision = '0007_projection_indexes'
down_revision = '0006_identity_plan'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_home_revision_recorded': 'home_revision (recorded_at DESC)',
    'ix_home_audit_entity_recorded': 'home_audit (entity_id, recorded_at DESC)',
    'ix_home_batch_status_source_started': 'home_batch (status, source_id, started_at DESC)',
}


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        # Online builds keep collection and normal reads available.
        with op.get_context().autocommit_block():
            for name, target in INDEXES.items():
                op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}')
    else:
        for name, target in INDEXES.items():
            op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {target}')


def downgrade():
    for name in INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')
