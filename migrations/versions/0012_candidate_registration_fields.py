"""Add candidate registration work status.

Revision ID: 0012_candidate_registration_fields
Revises: 0011_company_employee_count
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_candidate_registration_fields'
down_revision = '0011_company_employee_count'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('job_seeker_profiles')}
    if 'work_status' not in cols:
        op.add_column('job_seeker_profiles', sa.Column('work_status', sa.String(length=30), nullable=True, server_default=''))

def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('job_seeker_profiles')}
    if 'work_status' in cols:
        op.drop_column('job_seeker_profiles', 'work_status')
