"""Keep policy cache version checks independent of bulk raw revision volume."""
from alembic import op

revision='0015_delivery_cache_version'
down_revision='0014_raw_collection_indexes'
branch_labels=None
depends_on=None


def upgrade():
    if op.get_bind().dialect.name=='postgresql':
        with op.get_context().autocommit_block():
            op.execute("SET maintenance_work_mem='32MB'")
            op.execute('SET max_parallel_maintenance_workers=0')
            op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_home_delivery_revision "
                       "ON home_revision (recorded_at DESC) WHERE kind NOT IN "
                       "('permit','general_permit','register','register_recap','permit_dong','permit_parcel')")
    else:
        op.execute("CREATE INDEX IF NOT EXISTS ix_home_delivery_revision "
                   "ON home_revision (recorded_at DESC) WHERE kind NOT IN "
                   "('permit','general_permit','register','register_recap','permit_dong','permit_parcel')")


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_delivery_revision')
