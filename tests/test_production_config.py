import os
from config import Config, ProductionConfig


def test_production_config_is_hardened():
    assert ProductionConfig.DEV_SHOW_RESET_LINK is False
    assert ProductionConfig.REQUIRE_EMAIL_VERIFICATION is True
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.REMEMBER_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == 'Lax'
    assert ProductionConfig.AUTO_CREATE_DB is False
    assert ProductionConfig.TRUST_PROXY is True
    assert ProductionConfig.AUTO_APPROVE_RECRUITER_COMPANIES is False


def test_production_startup_command_initializes_schema_before_migrations():
    from pathlib import Path
    procfile = Path(__file__).resolve().parents[1] / 'Procfile'
    command = procfile.read_text()
    assert 'flask --app run:app init-db' in command
    assert 'flask --app run:app db upgrade' in command
