"""Add stable candidate identities and legal plan/event review records."""
from alembic import op
import sqlalchemy as sa

revision = "0006_identity_plan"
down_revision = "0005_source_coverage"
branch_labels = None
depends_on = None


def upgrade():
    names = set(sa.inspect(op.get_bind()).get_table_names())
    if "home_project" not in names:
        op.create_table("home_project",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("region", sa.String(30), nullable=False),
            sa.Column("identity_status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if "home_identity_alias" not in names:
        op.create_table("home_identity_alias",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(32), sa.ForeignKey("home_project.id"), nullable=False),
            sa.Column("source_entity_id", sa.String(80), nullable=False, unique=True),
            sa.Column("source_id", sa.String(40), nullable=False),
            sa.Column("relation_status", sa.String(24), nullable=False),
            sa.Column("match_rule", sa.String(80), nullable=False),
            sa.Column("unit_comparison", sa.String(24)),
            sa.Column("basis", sa.Text(), nullable=False),
            sa.Column("evidence_revision_id", sa.String(36), nullable=False),
            sa.Column("evidence_url", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)))
        op.create_index("ix_home_identity_alias_project_id", "home_identity_alias", ["project_id"])
    if "home_project_evidence" not in names:
        op.create_table("home_project_evidence",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(32), sa.ForeignKey("home_project.id"), nullable=False),
            sa.Column("revision_id", sa.String(36), nullable=False),
            sa.Column("evidence_role", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "revision_id", name="uq_home_project_evidence_revision"))
        op.create_index("ix_home_project_evidence_project_id", "home_project_evidence", ["project_id"])
    if "home_plan" not in names:
        op.create_table("home_plan",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("region", sa.String(30), nullable=False),
            sa.Column("plan_type", sa.String(40), nullable=False),
            sa.Column("legal_status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if "home_plan_event" not in names:
        op.create_table("home_plan_event",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("plan_id", sa.String(32), sa.ForeignKey("home_plan.id"), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("notice_no", sa.String(100)),
            sa.Column("notice_date", sa.String(10)),
            sa.Column("evidence_url", sa.Text(), nullable=False),
            sa.Column("evidence_sha256", sa.String(64)),
            sa.Column("source_revision_id", sa.String(36)),
            sa.Column("verification_status", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_home_plan_event_plan_id", "home_plan_event", ["plan_id"])
    if "home_plan_project_link" not in names:
        op.create_table("home_plan_project_link",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("plan_id", sa.String(32), sa.ForeignKey("home_plan.id"), nullable=False),
            sa.Column("project_id", sa.String(32), sa.ForeignKey("home_project.id"), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("basis", sa.Text(), nullable=False),
            sa.Column("evidence_url", sa.Text(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("plan_id", "project_id", name="uq_home_plan_project"))
        op.create_index("ix_home_plan_project_link_plan_id", "home_plan_project_link", ["plan_id"])
        op.create_index("ix_home_plan_project_link_project_id", "home_plan_project_link", ["project_id"])


def downgrade():
    for table in ("home_plan_project_link", "home_plan_event", "home_plan",
                  "home_project_evidence", "home_identity_alias", "home_project"):
        op.drop_table(table)

