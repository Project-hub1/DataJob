"""Remove legacy demo company reviews from seed data.

Real reviews must always come from an authenticated candidate who has applied
for at least one job belonging to the reviewed company.
"""
from alembic import op
from sqlalchemy import text

revision = '0008_remove_seed_demo_reviews'
down_revision = '0007_production_indexes'
branch_labels = None
depends_on = None


def upgrade():
    # Older CareerHub builds inserted this exact seed review. Remove only that
    # known synthetic content; genuine user reviews are left untouched.
    op.execute(text("DELETE FROM company_reviews WHERE title = 'Demo candidate review' AND body = 'Demo review created by the seed script.'"))


def downgrade():
    pass
