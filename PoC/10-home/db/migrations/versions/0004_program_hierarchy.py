"""Separate programme→policy and project→programme review records."""
from alembic import op
import sqlalchemy as sa

revision = '0004_program_hierarchy'
down_revision = '0003_observation_counts'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'program_id' not in {column['name'] for column in inspector.get_columns('home_mapping')}:
        op.add_column('home_mapping', sa.Column('program_id', sa.String(36), nullable=True))
    if 'ix_home_mapping_program_id' not in {index['name'] for index in inspector.get_indexes('home_mapping')}:
        op.create_index('ix_home_mapping_program_id', 'home_mapping', ['program_id'])
    if 'home_program_mapping' not in inspector.get_table_names():
        op.create_table('home_program_mapping',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('name', sa.Text(), nullable=False),
            sa.Column('seed_policy_id', sa.String(80), nullable=False),
            sa.Column('policy_id', sa.String(80), nullable=False),
            sa.Column('status', sa.String(24), nullable=False),
            sa.Column('revision_no', sa.Integer(), nullable=False),
            sa.Column('basis', sa.Text(), nullable=False),
            sa.Column('evidence_url', sa.Text(), nullable=False),
            sa.Column('reviewed_at', sa.DateTime(timezone=True)),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('home_program_mapping')
    op.drop_index('ix_home_mapping_program_id', table_name='home_mapping')
    op.drop_column('home_mapping', 'program_id')
