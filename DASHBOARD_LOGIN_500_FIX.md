# Login -> Candidate Dashboard 500 Fix (V4.3)

This release hardens the candidate dashboard against legacy/local SQLite databases.

- Local schema repair now always runs `db.create_all()` before additive compatibility fixes.
- Missing Resume Builder columns are added without deleting existing data.
- Missing `applications.recruiter_notes` is repaired.
- Candidate dashboard creates a missing candidate profile safely.
- Candidate dashboard retries once after a SQLAlchemy database error by running the local schema repair.
- Existing users, jobs, applications and resumes are preserved.

Production PostgreSQL remains migration-owned; the local compatibility repair is not enabled for ProductionConfig.
