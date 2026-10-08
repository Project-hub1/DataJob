"""Add first-class recruiter and candidate activity tracking.

This migration is intentionally idempotent because CareerHub's one-click
setup may bootstrap model tables with SQLAlchemy's create_all() before
Alembic runs.
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_activity_tracking'
down_revision = '0008_remove_seed_demo_reviews'
branch_labels = None
depends_on = None


def _index_names(inspector):
    return {item.get('name') for item in inspector.get_indexes('activity_events')}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('activity_events'):
        op.create_table(
            'activity_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('role', sa.String(length=30), nullable=False),
            sa.Column('event_type', sa.String(length=80), nullable=False),
            sa.Column('entity_type', sa.String(length=40), nullable=False, server_default='system'),
            sa.Column('entity_id', sa.Integer(), nullable=True),
            sa.Column('summary', sa.String(length=500), nullable=False),
            sa.Column('details', sa.Text(), server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )

    # create_all() may already have created these indexes. Only add missing ones.
    existing = _index_names(sa.inspect(bind))
    indexes = {
        'ix_activity_events_user_id': ['user_id'],
        'ix_activity_events_actor_id': ['actor_id'],
        'ix_activity_events_role': ['role'],
        'ix_activity_events_event_type': ['event_type'],
        'ix_activity_events_entity_id': ['entity_id'],
        'ix_activity_events_created_at': ['created_at'],
    }
    for name, columns in indexes.items():
        if name not in existing:
            op.create_index(name, 'activity_events', columns)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('activity_events'):
        op.drop_table('activity_events')
