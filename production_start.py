"""Safe Render production entrypoint for CareerHub.

Production startup is fail-closed: it requires PostgreSQL, applies only
incremental Alembic migrations, and never seeds or resets the database.
"""
import os
import subprocess
import sys


def main():
    env = os.environ.copy()
    env["CAREERHUB_ENV"] = "production"
    database_url = env.get("DATABASE_URL", "").strip()
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if not database_url:
        raise SystemExit(
            "DEPLOYMENT STOPPED: DATABASE_URL is missing. "
            "Configure the persistent Render PostgreSQL database first."
        )
    if not database_url.startswith("postgresql://"):
        raise SystemExit(
            "DEPLOYMENT STOPPED: production DATABASE_URL must be PostgreSQL. "
            "SQLite is intentionally disabled in production."
        )
    env["DATABASE_URL"] = database_url

    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "run:app", "db", "upgrade"],
        env=env,
        check=True,
    )

    port = env.get("PORT", "10000")
    os.execvpe(
        "gunicorn",
        ["gunicorn", "--bind", f"0.0.0.0:{port}", "run:app"],
        env,
    )


if __name__ == "__main__":
    main()
