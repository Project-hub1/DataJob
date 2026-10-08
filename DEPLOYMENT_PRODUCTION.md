# CareerHub production deployment

## Render architecture

- Web service: Flask + Gunicorn
- Database: Render Postgres `basic-256mb`
- Database connection: Render managed PgBouncer (`connectionPool: pgbouncer`)
- `DATABASE_URL`: Render internal connection-pool URL
- Schema changes: `flask --app run:app db upgrade`
- Health checks: `/health` and `/health/ready`

The application does **not** run `db.create_all()` during production startup. Production schema changes are applied only through the checked-in Alembic migrations.

## Required Render environment

- `SECRET_KEY`: generate a secure value in Render
- `DATABASE_URL`: connect the Render Postgres database to the web service
- `CAREERHUB_ENV=production`
- `SESSION_COOKIE_SECURE=1`
- `REMEMBER_COOKIE_SECURE=1`
- `TRUST_PROXY=1`
- `AUTO_CREATE_DB=0`
- `AUTO_APPROVE_RECRUITER_COMPANIES=0`
- `HEALTHCHECK_ENABLED=1`
- `PREFERRED_URL_SCHEME=https`
- `REQUIRE_EMAIL_VERIFICATION=0` until SMTP is configured. Set it to `1` only after SMTP credentials and `MAIL_FROM` are working.

## Data persistence

Candidate photos and uploaded resumes are stored in PostgreSQL as binary data, so they are not dependent on Render's ephemeral web-service filesystem. Application resume snapshots are also stored in PostgreSQL.

Do not use the local SQLite database for production.
