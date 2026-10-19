"""Fence a recovered collection job from a stale worker."""
from alembic import op
import sqlalchemy as sa

revision='0012_collection_lease_token'
down_revision='0011_independent_integrity'
branch_labels=None
depends_on=None


def upgrade():
    columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns('home_collection_job')}
    if 'lease_token' not in columns:
        op.add_column('home_collection_job',sa.Column('lease_token',sa.String(36),nullable=True))


def downgrade():
    pass  # Keep historical job information during an application rollback.
