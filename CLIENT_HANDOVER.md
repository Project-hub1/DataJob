# CareerHub — Client Handover Checklist

## Before handover
- Set a strong production `SECRET_KEY`.
- Use PostgreSQL for production.
- Configure SMTP if email verification/password reset emails are required.
- Create a real admin account with `flask create-admin`.
- Do not use the demo accounts in production.
- Keep `.env` out of Git/source delivery.

## Deployment
The project includes `render.yaml` for Render.

Render provisions:
- CareerHub web service
- PostgreSQL database
- production environment settings
- `/health` health check
- database initialization + Alembic upgrade before Gunicorn

After deployment, verify:
- `/health` returns `{"status":"ok","service":"careerhub"}`
- `/health/ready` reports database `ok`
- candidate registration/login
- recruiter company approval + job publishing
- candidate search/save/apply
- recruiter applicant pipeline
- resume upload/download
- job report moderation
- job alerts/notifications
- password reset email delivery

## Important production notes
- Uploaded resumes/photos are stored in the database in the current application version.
- Rate limiting uses `memory://` by default. For multiple web instances, use a shared Redis/Key Value URL.
- Company approval is disabled by default in production; an admin must approve recruiter companies before their jobs become public.
- Run database migrations before application startup. The supplied Render startup command already does this.


## Render production decision
- The supplied Blueprint is suitable for a quick preview using Render Free.
- **Do not present the Free Postgres instance as permanent production storage:** Render currently states that Free Postgres expires after 30 days. Upgrade the database before the 30-day period if client data must remain available. citeturn0search1
- Render Free web services cannot use persistent disks. CareerHub stores candidate resume/photo bytes in the database, so these uploads do not depend on the service filesystem in the current build. citeturn0search0
- Free web services also cannot send outbound SMTP traffic on ports 25/465/587. If email verification/password reset must work on a Free web service, use an HTTP-based transactional email provider/API or move the service to a plan that permits the required email delivery path. citeturn0search1
- The Render start command explicitly binds Gunicorn to `$PORT`, matching Render's current web-service port requirements. citeturn2search4turn2search7

### Latest final pass

**Resume Builder:** rebuilt for easier candidate use with a guided editor, readiness indicator, live resume preview, profile completeness checklist and direct PDF download.

**Company Reviews:** review content is now strictly real-user generated. Seed data does not create reviews, legacy synthetic seed reviews are removed by migration 0008, and only candidates with an actual application to that company can publish/update one review. Reviews require a meaningful written experience and are visibly marked as verified applicant reviews.

### Migration 0009 repair (V3.1)
- Fixed an idempotency bug in `0009_activity_tracking`: the one-click installer may create `activity_events` with SQLAlchemy `create_all()` before Alembic runs.
- Migration 0009 now safely reuses an existing `activity_events` table and only creates missing indexes.
- This fixes the Windows setup failure: `sqlite3.OperationalError: table activity_events already exists`.
