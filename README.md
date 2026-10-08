# CareerHub — Full Job Portal (Phases 1–3 + Platform Core)

CareerHub is a Flask + SQLAlchemy job marketplace with separate candidate, recruiter and admin workflows. It is designed to be a real functional application rather than a static UI.

## What is included

### Candidate
- Registration, login, logout, remember-me and password reset
- Professional profile with skills, education and experience
- Resume upload (PDF/DOC/DOCX, max 5 MB)
- Job search with keyword, location, experience, salary, type, work mode, education and date filters
- Relevance/newest/oldest/salary sorting and server-side pagination
- Save/unsave jobs and a dedicated Saved Jobs page
- Job applications with cover letter and application status tracking
- Job alerts and notifications with unread badge

### Recruiter
- Recruiter account and company profile
- Company approval workflow
- Create, edit, pause and close job postings
- Skills, salary, experience, location and work-mode fields
- Applicant management and application status updates
- Candidate resume access limited to the recruiter's own applications

### Admin
- Dashboard statistics
- User activation/deactivation
- Company approval/rejection
- Job flagging/opening/closing
- Audit log records

### Public marketplace
- Search across job title, description, requirements, responsibilities, skills and company name
- Active-job visibility checks including deadline, moderation and company approval
- Company directory and company detail pages
- Similar jobs
- Share/copy job link
- Responsive UI for desktop, tablet and mobile, including a mobile filter drawer
- XSS-safe Jinja rendering and safe external website validation for recruiter company profiles

## Windows setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask db upgrade
python seed.py
python run.py
```

Or run `setup.bat` once and then `start.bat`.

Open: `http://127.0.0.1:5000`

## Demo accounts

Candidate: `candidate@example.com` / `Candidate@123`

Recruiter: `recruiter@example.com` / `Recruiter@123`

Admin:
```powershell
flask create-admin
```

## Tests

```powershell
python -m pytest -q
```

## Troubleshooting

If an older CareerHub database is being reused, stop the server before running setup again. The development application creates its schema automatically and Flask-Migrate remains available for future schema changes.

If the browser appears to keep loading, check the PowerShell window for the server output. `http://127.0.0.1:5000/login` and `http://127.0.0.1:5000/jobs` are useful quick health checks.

## Validation performed for this package

- Python source compilation: passed.
- Jinja template syntax parsing: passed.
- Template endpoint-reference scan: no missing `url_for` endpoints detected.
- The earlier duplicate `page` keyword pagination bug has been removed.
- Full Flask/pytest execution could not be run in the packaging environment because external Python packages could not be downloaded due to unavailable network/DNS access. Run `python -m pytest -q` locally after installing `requirements.txt`.

## Production notes

Do not use the development `SECRET_KEY` in production. Use PostgreSQL, a strong secret, HTTPS, proper email delivery for password resets, and production WSGI hosting before deployment.

## Smart spelling-tolerant job search

The job search now has a two-stage matching system:

1. **Exact/normal search first** — existing filters, relevance sorting and pagination remain unchanged.
2. **Fuzzy fallback** — only when the exact keyword search returns zero jobs, the app uses RapidFuzz to find close matches for typos such as `pyhton` → `Python`, `javscript` → `JavaScript`, or `develper` → `Developer`.
3. If no sufficiently close result exists, the results page shows **“Please check spelling”** and suggests using a broader keyword.

This keeps normal searches efficient while making typo searches forgiving.

## Public deployment

This project is prepared for a production WSGI server with `Procfile`:

```text
web: gunicorn run:app
```

For a real public deployment, use a hosted PostgreSQL database instead of SQLite. The production startup command first creates any missing current-schema tables and then runs Alembic migrations, so a brand-new PostgreSQL database is initialized safely. Set these environment variables on your hosting provider:

```text
SECRET_KEY=<long-random-secret>
DATABASE_URL=<your-postgresql-connection-string>
DEV_SHOW_RESET_LINK=0
REQUIRE_EMAIL_VERIFICATION=1
SESSION_COOKIE_SECURE=1
REMEMBER_COOKIE_SECURE=1
TRUST_PROXY=1
AUTO_CREATE_DB=0
AUTO_APPROVE_RECRUITER_COMPANIES=0
HEALTHCHECK_ENABLED=1
RATELIMIT_STORAGE_URI=<shared-redis-url>
```

After the service is deployed, open the provider's generated `https://...` URL. The `/health` endpoint is a lightweight liveness check and `/health/ready` verifies database readiness. Do not expose `.env`, database files, or uploaded resume files through source control.

**Important for resumes:** many cloud hosts use ephemeral storage. If uploaded resumes must survive redeploys/restarts, store them in persistent disk/object storage (for example S3-compatible storage) rather than relying on the app container's local filesystem.


## Profile & application upgrade
- Candidate profile now saves personal details, age, photo, resume, education, experience, certifications, projects, skills and links from one Save Profile action.
- Profile photos and resumes are stored in the database for reliable persistence on Render; no Render disk is required for these new uploads.
- Job applications capture applicant name, education, age, skills, experience and the submitted resume as an immutable application snapshot.
- Render startup runs `flask db upgrade` before Gunicorn so existing databases receive the new columns automatically.

### Windows database note

The one-click `setup.bat` and `start.bat` scripts validate the configured database connection directly. They do not assume that `careerhub.db` is located in the project root. For the default SQLite configuration, Flask-SQLAlchemy stores the database under the application's `instance` directory.


## Production hardening added
- Proxy-aware HTTPS handling for Render/reverse proxies.
- Liveness and database readiness endpoints: `/health` and `/health/ready`.
- Request IDs for support/debugging and stronger response security headers.
- Automatic DB-session rollback/cleanup after failed requests.
- Registration, verification and password-reset rate limits.
- Stronger password requirements for newly created/reset passwords.
- Production recruiter-company moderation defaults to admin approval.
- Additional indexes for notifications, messages and job-view analytics.
- Fuzzy-search fallback is bounded so a typo cannot trigger an unbounded in-memory scan.
- Company reviews require a candidate to have applied to that company.

### Authentication UX
Local Windows development does not lock the user out with authentication rate limits. Login and registration still have production rate limits, and every password field includes an accessible Show/Hide control.


### Fresh production database initialization
The `Procfile` runs `flask init-db` before `flask db upgrade`. This is intentional: the original project schema is maintained by SQLAlchemy's current models while later Alembic migrations add incremental production fields/indexes. The command is idempotent and safe for an existing database.


### Render deployment

This package includes `render.yaml` for a Render Blueprint. It provisions the web service and PostgreSQL database, generates the production `SECRET_KEY`, runs `init-db` plus migrations before Gunicorn, and exposes `/health` as the service health check. Render supports Python web services, PostgreSQL references and Blueprint-managed deployments.

SMTP variables are intentionally marked as secrets in the Blueprint. Add the SMTP provider values in Render before enabling password-reset/verification email delivery.
