"""Additional production indexes for notification, messaging and analytics paths."""
from alembic import op
import sqlalchemy as sa

revision = "0007_production_indexes"
down_revision = "0006_phase4"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_notifications_user_read", "notifications", ["user_id", "is_read"]),
    ("ix_notifications_created_at", "notifications", ["created_at"]),
    ("ix_messages_receiver_read", "messages", ["receiver_id", "is_read"]),
    ("ix_job_views_job_id", "job_views", ["job_id"]),
    ("ix_job_views_viewer_viewed_at", "job_views", ["viewer_id", "viewed_at"]),
]

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for name, table, columns in INDEXES:
        if table not in tables:
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)

def downgrade():
    for name, table, _ in reversed(INDEXES):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
