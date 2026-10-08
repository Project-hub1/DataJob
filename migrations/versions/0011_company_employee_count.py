"""Add company employee count for recruiter profile editing.

Revision ID: 0011_company_employee_count
Revises: 0010_resume_builder_sections
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_company_employee_count'
down_revision = '0010_resume_builder_sections'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('companies')}
    if 'employee_count' not in cols:
        op.add_column('companies', sa.Column('employee_count', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c['name'] for c in inspector.get_columns('companies')}
    if 'employee_count' in cols:
        op.drop_column('companies', 'employee_count')
