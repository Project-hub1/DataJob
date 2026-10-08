import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


def _as_bool(name, default=False):
    return os.getenv(name, '1' if default else '0').lower() in {'1', 'true', 'yes', 'on'}


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR / "careerhub.db"}')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Keep database connections healthy across Render's long-lived Gunicorn workers.
    # Values are conservative so a small Postgres instance is not overwhelmed.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '300')),
        'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '5')),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '2')),
    }

    WTF_CSRF_TIME_LIMIT = 3600
    DEV_SHOW_RESET_LINK = _as_bool('DEV_SHOW_RESET_LINK', False)
    REQUIRE_EMAIL_VERIFICATION = _as_bool('REQUIRE_EMAIL_VERIFICATION', False)
    JOBS_PER_PAGE = 20
    # A profile save may contain both a photo and a resume in one multipart request.
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(12 * 1024 * 1024)))
    UPLOAD_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'webp'}
    MAX_RESUME_SIZE = int(os.getenv('MAX_RESUME_SIZE', str(4 * 1024 * 1024)))
    MAX_PHOTO_SIZE = int(os.getenv('MAX_PHOTO_SIZE', str(2 * 1024 * 1024)))
    # A single profile form can carry both files. Never let the request-wide limit
    # be smaller than the sum of the supported individual upload limits.
    MAX_CONTENT_LENGTH = max(MAX_CONTENT_LENGTH, MAX_RESUME_SIZE + MAX_PHOTO_SIZE + 1024 * 1024)

    SESSION_COOKIE_SECURE = _as_bool('SESSION_COOKIE_SECURE', False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = _as_bool('REMEMBER_COOKIE_SECURE', False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12

    RATELIMIT_DEFAULT = '300 per hour'
    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True
    # Local development should never get locked out while testing the auth UI.
    # ProductionConfig disables this bypass.
    ALLOW_LOCAL_AUTH_BYPASS = _as_bool('ALLOW_LOCAL_AUTH_BYPASS', True)

    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = _as_bool('SMTP_USE_TLS', True)
    MAIL_FROM = os.getenv('MAIL_FROM', '')
    APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000')
    AUTO_CREATE_DB = _as_bool('AUTO_CREATE_DB', True)
    TRUST_PROXY = _as_bool('TRUST_PROXY', False)
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'http')
    AUTO_APPROVE_RECRUITER_COMPANIES = _as_bool('AUTO_APPROVE_RECRUITER_COMPANIES', True)
    HEALTHCHECK_ENABLED = _as_bool('HEALTHCHECK_ENABLED', True)
    MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '500'))


class ProductionConfig(Config):
    # Render Postgres supports TLS on internal connections. Requiring TLS prevents
    # an accidental plaintext connection if DATABASE_URL is copied incorrectly.
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'connect_args': {
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '10')),
            'sslmode': os.getenv('DB_SSLMODE', 'require'),
        },
    }
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    DEV_SHOW_RESET_LINK = False
    REQUIRE_EMAIL_VERIFICATION = True
    AUTO_CREATE_DB = False
    TRUST_PROXY = True
    AUTO_APPROVE_RECRUITER_COMPANIES = False
    ALLOW_LOCAL_AUTH_BYPASS = False
