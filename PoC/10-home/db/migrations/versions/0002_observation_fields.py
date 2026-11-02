"""Index observation fields without decoding large raw API JSON for every dashboard count."""
from alembic import op
import sqlalchemy as sa
revision='0002_observation_fields'
down_revision='0001_home'
branch_labels=None
depends_on=None


def upgrade():
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('home_revision')}
    for name,kind in (('sample_base_date',sa.String(10)),('sample_region',sa.String(30)),('sample_name',sa.Text()),('sample_source_date',sa.String(10)),('sample_event_day',sa.String(10))):
        if name not in existing:
            op.add_column('home_revision', sa.Column(name,kind))
    op.execute("""UPDATE home_revision SET sample_base_date=payload->>'base_date', sample_region=payload->>'region',
        sample_name=payload->>'name', sample_source_date=payload->>'source_date',
        sample_event_day=CASE WHEN kind='permit' THEN COALESCE(NULLIF(payload->'dates'->>'원천 허가일 (apprvDay)',''),payload->>'source_date') ELSE payload->>'source_date' END
        WHERE sample_base_date IS NULL""")
    op.execute('CREATE INDEX IF NOT EXISTS ix_home_sample_order ON home_revision (kind,sample_region,sample_name,entity_id) WHERE superseded_at IS NULL')
    op.execute('CREATE INDEX IF NOT EXISTS ix_home_sample_dates ON home_revision (kind,sample_source_date,sample_event_day,sample_region) WHERE superseded_at IS NULL')
    op.execute('ANALYZE home_revision')


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_home_sample_dates')
    op.execute('DROP INDEX IF EXISTS ix_home_sample_order')
    existing = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('home_revision')}
    for name in ('sample_base_date','sample_region','sample_name','sample_source_date','sample_event_day'):
        if name in existing:
            op.drop_column('home_revision',name)
