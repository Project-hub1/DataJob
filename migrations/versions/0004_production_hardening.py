"""Production hardening: email verification and query indexes."""
from alembic import op
import sqlalchemy as sa

revision = '0004_production_hardening'
down_revision = '0003_profile_application_upgrade'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_cols = {c['name'] for c in inspector.get_columns('users')}
    if 'email_verified' not in user_cols:
        op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
        op.create_index('ix_users_email_verified', 'users', ['email_verified'])
        op.execute(sa.text('UPDATE users SET email_verified = TRUE'))
    if 'email_verification_tokens' not in inspector.get_table_names():
        op.create_table(
            'email_verification_tokens',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('token_hash', sa.String(64), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])
        op.create_index('ix_email_verification_tokens_token_hash', 'email_verification_tokens', ['token_hash'], unique=True)

    # Common production query paths. Existing databases may already have some of these.
    existing = {idx['name'] for table in inspector.get_table_names() for idx in inspector.get_indexes(table)}
    indexes = [
        ('ix_jobs_status_created_at', 'jobs', ['status', 'created_at']),
        ('ix_jobs_company_status', 'jobs', ['company_id', 'status']),
        ('ix_applications_candidate_status', 'applications', ['candidate_id', 'status']),
        ('ix_applications_job_status', 'applications', ['job_id', 'status']),
    ]
    for name, table, columns in indexes:
        if name not in existing and table in inspector.get_table_names():
            op.create_index(name, table, columns)

def downgrade():
    for name, table in [
        ('ix_applications_job_status', 'applications'),
        ('ix_applications_candidate_status', 'applications'),
        ('ix_jobs_company_status', 'jobs'),
        ('ix_jobs_status_created_at', 'jobs'),
    ]:
        try: op.drop_index(name, table_name=table)
        except Exception: pass
    try: op.drop_index('ix_email_verification_tokens_token_hash', table_name='email_verification_tokens')
    except Exception: pass
    try: op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    except Exception: pass
    try: op.drop_table('email_verification_tokens')
    except Exception: pass
    try: op.drop_index('ix_users_email_verified', table_name='users')
    except Exception: pass
    try: op.drop_column('users', 'email_verified')
    except Exception: pass
