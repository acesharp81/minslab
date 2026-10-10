"""Initial collection / validation slice; later full Master migrations are additive."""
from alembic import op
from backend.db import Base

revision = "0001_home"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
