from flask import Flask, jsonify, render_template, request, g, send_from_directory
from config import Config, ProductionConfig
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text
import uuid
import logging
from logging.handlers import RotatingFileHandler
from .extensions import db, login_manager, migrate, csrf, limiter


def request_is_https(req):
    return req.is_secure or req.headers.get('X-Forwarded-Proto', '').lower() == 'https'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Production data safety: never silently fall back to the ephemeral local
    # filesystem/SQLite database. Render deployments must use the same persistent
    # PostgreSQL service so users, jobs, applications and profiles survive deploys.
    if config_class is ProductionConfig:
        production_db_url = str(app.config.get('DATABASE_URL') or '').strip()
        if production_db_url.startswith('postgres://'):
            production_db_url = production_db_url.replace('postgres://', 'postgresql://', 1)
            app.config['DATABASE_URL'] = production_db_url
            app.config['SQLALCHEMY_DATABASE_URI'] = production_db_url
        if not production_db_url:
            raise RuntimeError(
                'DATABASE_URL is required in production. '
                'CareerHub will not start with a local SQLite database.'
            )
        if not production_db_url.startswith('postgresql://'):
            raise RuntimeError(
                'Production DATABASE_URL must be a PostgreSQL URL. '
                'SQLite is disabled in production.'
            )

    if app.config.get('TRUST_PROXY'):
        # Render/nginx terminate TLS upstream. Trust one proxy hop so Flask sees
        # the original scheme/host without trusting arbitrary client headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if app.config.get('SECRET_KEY') == 'dev-secret-change-me' and not app.testing:
        raise RuntimeError('SECRET_KEY must be configured before running CareerHub outside tests.')
    import os
    os.makedirs(os.path.join(app.instance_path, 'uploads', 'resumes'), exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    if not app.debug and not app.testing:
        log_dir = os.path.join(app.instance_path, "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(log_dir, "careerhub.log"), maxBytes=5 * 1024 * 1024, backupCount=5)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .main.routes import main_bp
    from .auth.routes import auth_bp
    from .jobs.routes import jobs_bp
    from .candidate.routes import candidate_bp
    from .recruiter.routes import recruiter_bp
    from .admin.routes import admin_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(recruiter_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex

    @app.after_request
    def add_request_id(response):
        response.headers.setdefault('X-Request-ID', getattr(g, 'request_id', uuid.uuid4().hex))
        return response

    @app.get('/health')
    def health():
        if not app.config.get('HEALTHCHECK_ENABLED', True):
            return jsonify(status='disabled'), 404
        return jsonify(status='ok', service='careerhub')

    @app.get('/health/ready')
    def readiness():
        if not app.config.get('HEALTHCHECK_ENABLED', True):
            return jsonify(status='disabled'), 404
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ready', database='ok')
        except Exception:
            db.session.rollback()
            app.logger.exception('Readiness database check failed')
            return jsonify(status='not_ready', database='unavailable'), 503

    @app.template_filter('lpa_range')
    def lpa_range(minimum, maximum):
        if minimum is None and maximum is None:
            return 'Salary not disclosed'
        if minimum is None:
            return f'Up to ₹{maximum / 100000:.1f} LPA'
        if maximum is None:
            return f'₹{minimum / 100000:.1f}+ LPA'
        return f'₹{minimum / 100000:.1f}–{maximum / 100000:.1f} LPA'

    @app.template_filter('experience_range')
    def experience_range(minimum, maximum):
        minimum = 0 if minimum is None else minimum
        if maximum is None:
            return f'{minimum:g}+ years'
        return f'{minimum:g}–{maximum:g} years'

    @app.context_processor
    def inject_nav_state():
        unread_notifications = 0
        unread_messages = 0
        nav_notifications = []
        if getattr(current_user, 'is_authenticated', False):
            from .models import Notification, Message
            unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            unread_messages = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
            nav_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        return {'unread_notifications': unread_notifications, 'unread_messages': unread_messages, 'nav_notifications': nav_notifications}

    # Development/test installs may auto-create the schema. Production uses migrations.
    # For local SQLite, make startup schema repair deliberately defensive. Older CareerHub
    # databases may have been created by a previous version and can be missing either a
    # table or an additive column. db.create_all() creates missing tables; the compatibility
    # pass adds known columns without destroying existing data.
    def repair_local_schema():
        if not (app.config.get('AUTO_CREATE_DB') or app.testing or str(app.config.get('SQLALCHEMY_DATABASE_URI','')).startswith('sqlite')):
            return
        from sqlalchemy import inspect, text
        db.create_all()
        inspector = inspect(db.engine)
        if inspector.has_table('applications'):
            cols = {c['name'] for c in inspector.get_columns('applications')}
            if 'recruiter_notes' not in cols:
                db.session.execute(text("ALTER TABLE applications ADD COLUMN recruiter_notes TEXT DEFAULT ''"))
                app.logger.warning('Repaired missing applications.recruiter_notes')
        if inspector.has_table('job_seeker_profiles'):
            cols = {c['name'] for c in inspector.get_columns('job_seeker_profiles')}
            repairs = {
                'resume_is_fresher': "ALTER TABLE job_seeker_profiles ADD COLUMN resume_is_fresher BOOLEAN NOT NULL DEFAULT FALSE",
                'achievements': "ALTER TABLE job_seeker_profiles ADD COLUMN achievements TEXT DEFAULT ''",
                'languages': "ALTER TABLE job_seeker_profiles ADD COLUMN languages VARCHAR(1000) DEFAULT ''",
            }
            for column, statement in repairs.items():
                if column not in cols:
                    db.session.execute(text(statement))
                    app.logger.warning('Repaired missing job_seeker_profiles.%s', column)
        db.session.commit()

    app.repair_local_schema = repair_local_schema
    if app.config.get('AUTO_CREATE_DB') or app.testing or str(app.config.get('SQLALCHEMY_DATABASE_URI','')).startswith('sqlite'):
        with app.app_context():
            try:
                repair_local_schema()
            except Exception:
                db.session.rollback()
                app.logger.exception('Local database schema compatibility repair failed')

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        # CareerHub currently uses a small amount of inline JavaScript in a few
        # templates. Keep the policy strict on sources while remaining compatible
        # with the existing UI; this can be moved to nonces as the UI is split out.
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'; frame-ancestors 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        )
        if request_is_https(request):
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    @app.teardown_request
    def cleanup_db(exception=None):
        if exception is not None:
            db.session.rollback()
        db.session.remove()

    @app.errorhandler(403)
    def forbidden(e): return render_template('error.html', code=403, message='You do not have permission to access this page.'), 403
    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'favicon.svg', mimetype='image/svg+xml')

    @app.errorhandler(404)
    def not_found(e): return render_template('error.html', code=404, message='The page you requested was not found.'), 404
    @app.errorhandler(405)
    def method_not_allowed(e): return render_template('error.html', code=405, message='This method is not allowed.'), 405
    @app.errorhandler(413)
    def too_large(e): return render_template('error.html', code=413, message='The uploaded file is too large.'), 413
    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template('error.html', code=429, message='Too many attempts in a short period. Please wait a moment and try again.'), 429
    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception('Unhandled application error request_id=%s', getattr(g, 'request_id', '-'), exc_info=e)
        return render_template('error.html', code=500, message='Something went wrong on the server.', request_id=getattr(g, 'request_id', None)), 500

    from .cli import register_cli
    register_cli(app)
    return app
