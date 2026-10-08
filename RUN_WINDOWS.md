# Running CareerHub on Windows

1. Extract the ZIP into a new folder.
2. Double-click `START.bat`.
3. The first run automatically calls `SETUP.bat`, creates `venv`, installs dependencies, creates `.env`, runs migrations, and starts the app.
4. Later, double-click `START.bat` again.
5. If anything fails, double-click `DOCTOR.bat` and send the complete output.

The local SQLite database is managed by Flask-SQLAlchemy. With the default `DATABASE_URL=sqlite:///careerhub.db`, the file is stored under the app's `instance` directory. Delete that database only if you intentionally want to reset local data.


## Database bootstrap fix

Local Windows setup uses `AUTO_CREATE_DB=1` so the current SQLAlchemy models create the base schema before Alembic applies Phase 3/4 migrations. This is required because the legacy `0001_initial` and `0002_marketplace_features` migrations are marker migrations rather than schema-creation migrations.

### Authentication UX
Local Windows development does not lock the user out with authentication rate limits. Login and registration still have production rate limits, and every password field includes an accessible Show/Hide control.
