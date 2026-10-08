# Resume Builder / Candidate Dashboard 500 Fix

V4.1 includes a compatibility repair for local databases created by an older CareerHub build.
If `job_seeker_profiles` is missing the Resume Builder columns (`resume_is_fresher`, `achievements`, or `languages`), the local startup schema repair adds only those missing columns without deleting existing data.

Production deployments should continue to use `flask db upgrade` so Alembic remains the schema source of truth.
