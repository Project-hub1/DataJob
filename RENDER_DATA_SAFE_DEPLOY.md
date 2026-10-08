# CareerHub — Render Data-Safe Deployment

## What changed

- Production refuses to start without a PostgreSQL `DATABASE_URL`.
- Production refuses to use SQLite.
- Production startup runs only `flask db upgrade` and then Gunicorn.
- The production startup path does **not** run `seed.py`.
- No `drop_all()`, `TRUNCATE`, or database reset is used by production startup.
- Alembic migrations are incremental; already-applied migrations are not rerun.
- Demo seeding is explicit and opt-in.

## Render Web Service

**Build Command**
```text
pip install -r requirements.txt
```

**Start Command**
```text
python production_start.py
```

Set:
```text
CAREERHUB_ENV=production
DATABASE_URL=<same persistent Render PostgreSQL connection pool URL>
AUTO_CREATE_DB=0
TRUST_PROXY=1
SESSION_COOKIE_SECURE=1
REMEMBER_COOKIE_SECURE=1
HEALTHCHECK_ENABLED=1
PREFERRED_URL_SCHEME=https
```

Do not put `python seed.py` in Build or Start Command.

## Existing data

A code deploy does not copy a local SQLite database into Render PostgreSQL.
If old demo data exists only in local SQLite, it must be imported/seeded into
Render PostgreSQL once.

If the Render PostgreSQL database already contains real users/jobs, **do not
delete or recreate that database**.

For a one-time demo seed, after migrations have completed, use the Render
service shell:
```text
ALLOW_PRODUCTION_SEED=1 python seed.py
```
The seed script only adds missing demo records. It does not drop, truncate, or
clear existing records. Never make this command part of deployment.

## File uploads

Database rows are persistent in PostgreSQL, but files stored on the Render
web-service filesystem (such as uploaded resumes/photos) are not guaranteed to
survive redeploys. For permanent uploads, use persistent disk or object storage.
