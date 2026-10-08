"""Add resume builder section fields.

Revision ID: 0010_resume_builder_sections
Revises: 0009_activity_tracking
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_resume_builder_sections'
down_revision = '0009_activity_tracking'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('job_seeker_profiles')}
    if 'resume_is_fresher' not in cols:
        op.add_column('job_seeker_profiles', sa.Column('resume_is_fresher', sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'achievements' not in cols:
        op.add_column('job_seeker_profiles', sa.Column('achievements', sa.Text(), nullable=True, server_default=''))
    if 'languages' not in cols:
        op.add_column('job_seeker_profiles', sa.Column('languages', sa.String(length=1000), nullable=True, server_default=''))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('job_seeker_profiles')}
    if 'languages' in cols:
        op.drop_column('job_seeker_profiles', 'languages')
    if 'achievements' in cols:
        op.drop_column('job_seeker_profiles', 'achievements')
    if 'resume_is_fresher' in cols:
        op.drop_column('job_seeker_profiles', 'resume_is_fresher')
