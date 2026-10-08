"""Add indexes for high-frequency production queries.

Revision ID: 0013_production_query_indexes
Revises: 0012_candidate_registration_fields
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_production_query_indexes'
down_revision = '0012_candidate_registration_fields'
branch_labels = None
depends_on = None

INDEXES = [
    ('ix_applications_candidate_job', 'applications', ['candidate_id', 'job_id']),
    ('ix_applications_job_status', 'applications', ['job_id', 'status']),
    ('ix_saved_jobs_user_created', 'saved_jobs', ['user_id', 'created_at']),
    ('ix_job_alerts_user_active', 'job_alerts', ['user_id', 'is_active']),
    ('ix_saved_searches_user_active', 'saved_searches', ['user_id', 'is_active']),
    ('ix_search_history_user_created', 'search_history', ['user_id', 'created_at']),
    ('ix_candidate_skills_profile', 'candidate_skills', ['profile_id']),
    ('ix_certifications_profile', 'certifications', ['profile_id']),
    ('ix_candidate_projects_profile', 'candidate_projects', ['profile_id']),
    ('ix_company_reviews_company_created', 'company_reviews', ['company_id', 'created_at']),
    ('ix_job_reports_status_created', 'job_reports', ['status', 'created_at']),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for name, table, columns in INDEXES:
        if table not in tables:
            continue
        existing = {idx['name'] for idx in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
