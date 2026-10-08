"""Phase 4 recruiter ATS pipeline and candidate evaluation.

Idempotent for fresh local installs.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_phase4"
down_revision = "0005_phase3"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "applications" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("applications")}
    indexes = {i["name"] for i in inspector.get_indexes("applications")}
    with op.batch_alter_table("applications") as batch_op:
        if "recruiter_rating" not in columns:
            batch_op.add_column(sa.Column("recruiter_rating", sa.Integer(), nullable=True))
        if "recruiter_tags" not in columns:
            batch_op.add_column(sa.Column("recruiter_tags", sa.String(length=500), nullable=True, server_default=""))
        if "ix_applications_recruiter_rating" not in indexes:
            batch_op.create_index("ix_applications_recruiter_rating", ["recruiter_rating"])

def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "applications" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("applications")}
    indexes = {i["name"] for i in inspector.get_indexes("applications")}
    with op.batch_alter_table("applications") as batch_op:
        if "ix_applications_recruiter_rating" in indexes:
            batch_op.drop_index("ix_applications_recruiter_rating")
        if "recruiter_tags" in columns:
            batch_op.drop_column("recruiter_tags")
        if "recruiter_rating" in columns:
            batch_op.drop_column("recruiter_rating")
