"""Upgrade candidate profiles, uploads and application snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0003_profile_application_upgrade'
down_revision = '0002_marketplace_features'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add(table, column, col):
        if column not in {c['name'] for c in inspector.get_columns(table)}:
            op.add_column(table, col)

    add('job_seeker_profiles', 'age', sa.Column('age', sa.Integer(), nullable=True))
    add('candidate_resumes', 'data', sa.Column('data', sa.LargeBinary(), nullable=True))
    add('candidate_resumes', 'mimetype', sa.Column('mimetype', sa.String(120), nullable=True))
    add('candidate_photos', 'data', sa.Column('data', sa.LargeBinary(), nullable=True))
    add('candidate_photos', 'mimetype', sa.Column('mimetype', sa.String(120), nullable=True))
    add('applications', 'resume_original_name', sa.Column('resume_original_name', sa.String(255), nullable=True))
    add('applications', 'resume_data', sa.Column('resume_data', sa.LargeBinary(), nullable=True))
    add('applications', 'resume_mimetype', sa.Column('resume_mimetype', sa.String(120), nullable=True))
    add('applications', 'applicant_name', sa.Column('applicant_name', sa.String(120), nullable=True))
    add('applications', 'applicant_education', sa.Column('applicant_education', sa.Text(), nullable=True))
    add('applications', 'applicant_age', sa.Column('applicant_age', sa.Integer(), nullable=True))
    add('applications', 'applicant_skills', sa.Column('applicant_skills', sa.Text(), nullable=True))
    add('applications', 'applicant_experience', sa.Column('applicant_experience', sa.String(120), nullable=True))

def downgrade():
    for table, columns in {
        'applications': ['applicant_experience','applicant_skills','applicant_age','applicant_education','applicant_name','resume_mimetype','resume_data','resume_original_name'],
        'candidate_photos': ['mimetype','data'],
        'candidate_resumes': ['mimetype','data'],
        'job_seeker_profiles': ['age'],
    }.items():
        for column in columns:
            try:
                op.drop_column(table, column)
            except Exception:
                pass
