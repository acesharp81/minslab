"""Content-addressed snapshot payloads; existing snapshots retain their IDs."""
from alembic import op
import sqlalchemy as sa
revision='0018_snapshot_content'
down_revision='0017_candidate_lookup'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('home_metric_snapshot_content',sa.Column('id',sa.String(64),primary_key=True),sa.Column('payload',sa.JSON(),nullable=False))

def downgrade():
    # The referenced payloads must be expanded before removing this table.
    connection=op.get_bind()
    if connection.scalar(sa.text('SELECT count(*) FROM home_metric_snapshot_content')):
        raise RuntimeError('공유 기준본 내용을 복원한 뒤 downgrade 하세요')
    op.drop_table('home_metric_snapshot_content')
