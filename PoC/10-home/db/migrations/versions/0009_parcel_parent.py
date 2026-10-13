"""Native permit-key lookup for project-scoped parcel evidence."""
from alembic import op
revision='0009_parcel_parent'
down_revision='0008_collection_lookup'
branch_labels=None
depends_on=None

def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        with op.get_context().autocommit_block():
            op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_parcel_parent ON home_revision ((payload ->> 'parent_permit_native_id')) WHERE kind = 'permit_parcel' AND superseded_at IS NULL")
    else:
        op.execute("CREATE INDEX IF NOT EXISTS ix_home_parcel_parent ON home_revision (json_extract(payload, '$.parent_permit_native_id')) WHERE kind = 'permit_parcel' AND superseded_at IS NULL")

def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_parcel_parent')
