"""Record query-scoped coverage separately from source batch success."""
from alembic import op
import sqlalchemy as sa

revision = '0005_source_coverage'
down_revision = '0004_program_hierarchy'
branch_labels = None
depends_on = None


def upgrade():
    if 'home_coverage' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('home_coverage',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('batch_id', sa.String(36), nullable=False),
        sa.Column('source_id', sa.String(40), nullable=False),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('region', sa.String(30)),
        sa.Column('area_code', sa.String(20)),
        sa.Column('source_period', sa.String(30)),
        sa.Column('expected_count', sa.Integer()),
        sa.Column('fetched_count', sa.Integer(), nullable=False),
        sa.Column('query_status', sa.String(24), nullable=False),
        sa.Column('population_status', sa.String(24), nullable=False),
        sa.Column('scope_note', sa.Text()),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_home_coverage_batch_id', 'home_coverage', ['batch_id'])
    op.create_index('ix_home_coverage_source_id', 'home_coverage', ['source_id'])


def downgrade():
    op.drop_index('ix_home_coverage_source_id', table_name='home_coverage')
    op.drop_index('ix_home_coverage_batch_id', table_name='home_coverage')
    op.drop_table('home_coverage')
