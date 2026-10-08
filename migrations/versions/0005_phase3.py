"""Phase 3 candidate experience and recruiter ATS fields.

Idempotent so fresh local installs that create the current model schema before
Alembic can still upgrade safely.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_phase3"
down_revision = "0004_production_hardening"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "applications" in tables:
        app_cols = {c["name"] for c in inspector.get_columns("applications")}
        if "recruiter_notes" not in app_cols:
            with op.batch_alter_table("applications") as batch_op:
                batch_op.add_column(sa.Column("recruiter_notes", sa.Text(), nullable=True, server_default=""))

    if "application_status_history" not in tables:
        op.create_table(
            "application_status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id"), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    existing_indexes = {i["name"] for i in sa.inspect(bind).get_indexes("application_status_history")} if "application_status_history" in tables or "application_status_history" in sa.inspect(bind).get_table_names() else set()
    if "ix_application_status_history_application_id" not in existing_indexes:
        op.create_index("ix_application_status_history_application_id", "application_status_history", ["application_id"])
    if "ix_application_status_history_changed_at" not in existing_indexes:
        op.create_index("ix_application_status_history_changed_at", "application_status_history", ["changed_at"])

def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "application_status_history" in inspector.get_table_names():
        indexes = {i["name"] for i in inspector.get_indexes("application_status_history")}
        if "ix_application_status_history_changed_at" in indexes:
            op.drop_index("ix_application_status_history_changed_at", table_name="application_status_history")
        if "ix_application_status_history_application_id" in indexes:
            op.drop_index("ix_application_status_history_application_id", table_name="application_status_history")
        op.drop_table("application_status_history")
    if "applications" in inspector.get_table_names():
        cols = {c["name"] for c in sa.inspect(bind).get_columns("applications")}
        if "recruiter_notes" in cols:
            with op.batch_alter_table("applications") as batch_op:
                batch_op.drop_column("recruiter_notes")
