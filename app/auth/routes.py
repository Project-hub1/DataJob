import hashlib, secrets
from datetime import datetime, timedelta
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from ..extensions import db, limiter
from ..models import User, JobSeekerProfile, RecruiterProfile, PasswordResetToken, EmailVerificationToken
from .forms import LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm
from .utils import is_safe_next_url
auth_bp=Blueprint('auth',__name__)

def _local_auth_bypass():
    return bool(current_app.config.get('ALLOW_LOCAL_AUTH_BYPASS', False)) and request.remote_addr in {'127.0.0.1', '::1'}

def dashboard_for(user): return {'candidate':'main.home','recruiter':'recruiter.dashboard','admin':'admin.dashboard'}[user.role]
@auth_bp.route('/login',methods=['GET','POST'])
@limiter.limit('20 per minute', methods=['POST'], exempt_when=_local_auth_bypass)
def login():
    if current_user.is_authenticated: return redirect(url_for(dashboard_for(current_user)))
    form=LoginForm()
    if form.validate_on_submit():
        u=User.query.filter_by(email=form.email.data.strip().lower()).first()
        if not u or not u.check_password(form.password.data): flash('Invalid email or password.','error')
        elif not u.is_active: flash('Your account is inactive.','error')
        elif current_app.config.get('REQUIRE_EMAIL_VERIFICATION') and not u.email_verified:
            flash('Please verify your email address before logging in.', 'error')
        else:
            u.last_login_at=datetime.utcnow(); db.session.commit(); login_user(u,remember=form.remember.data)
            nxt=request.args.get('next'); return redirect(nxt if is_safe_next_url(nxt) else url_for(dashboard_for(u)))
    return render_template('auth/login.html',form=form)
@auth_bp.route('/register',methods=['GET','POST'])
@limiter.limit('10 per 10 minutes', methods=['POST'], exempt_when=_local_auth_bypass)
def register():
    if current_user.is_authenticated: return redirect(url_for(dashboard_for(current_user)))
    form=RegisterForm()
    if form.validate_on_submit():
        email=form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists. Please log in instead.', 'error')
        else:
            u=User(email=email,role=form.role.data); u.set_password(form.password.data)
            db.session.add(u); db.session.flush()
            if u.role=='candidate':
                # The first registration screen intentionally captures the minimum
                # profile data needed to make the candidate's My Home useful.
                mobile = form.mobile.data.strip() if form.mobile.data else ''
                if not mobile:
                    form.mobile.errors.append('Mobile number is required for a job seeker.')
                    db.session.rollback()
                    return render_template('home.html', form=form, register_form=form)
                db.session.add(JobSeekerProfile(
                    user_id=u.id,
                    full_name=form.full_name.data.strip(),
                    phone=mobile,
                    work_status=form.work_status.data or 'fresher'
                ))
            else:
                db.session.add(RecruiterProfile(user_id=u.id,full_name=form.full_name.data.strip()))
            db.session.commit()
            if current_app.config.get('REQUIRE_EMAIL_VERIFICATION'):
                raw = secrets.token_urlsafe(32)
                token = EmailVerificationToken(user_id=u.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(hours=24))
                db.session.add(token); db.session.commit()
                verify_url = url_for('auth.verify_email', token=raw, _external=True)
                from ..services import send_email
                delivered = send_email('Verify your CareerHub email', u.email, f'Verify your CareerHub account within 24 hours: {verify_url}')
                if not delivered:
                    current_app.logger.warning('Verification email could not be delivered for user_id=%s', u.id)
                flash('Account created. Please verify your email address before logging in.', 'success')
            else:
                u.email_verified = True
                db.session.commit()
                flash('Account created. Please log in.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('home.html', register_form=form)

@auth_bp.get('/verify-email/<token>')
@limiter.limit('20 per hour')
def verify_email(token):
    h = hashlib.sha256(token.encode()).hexdigest()
    t = EmailVerificationToken.query.filter_by(token_hash=h).first()
    if not t or t.used_at or t.expires_at < datetime.utcnow():
        flash('This email verification link is invalid or expired.', 'error')
        return redirect(url_for('auth.login'))
    u = db.session.get(User, t.user_id)
    u.email_verified = True
    t.used_at = datetime.utcnow()
    db.session.commit()
    flash('Email verified successfully. You can now log in.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.post('/logout')
@login_required
def logout(): logout_user(); flash('You have been logged out.','success'); return redirect(url_for('main.home'))
@auth_bp.route('/forgot-password',methods=['GET','POST'])
@limiter.limit('10 per 10 minutes', methods=['POST'], exempt_when=_local_auth_bypass)
def forgot_password():
    form=ForgotPasswordForm(); reset_url=None
    if form.validate_on_submit():
        u=User.query.filter_by(email=form.email.data.strip().lower()).first()
        if u:
            PasswordResetToken.query.filter_by(user_id=u.id,used_at=None).update({'used_at':datetime.utcnow()})
            raw=secrets.token_urlsafe(32); token=PasswordResetToken(user_id=u.id,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=datetime.utcnow()+timedelta(minutes=60)); db.session.add(token); db.session.commit()
            reset_url_value = url_for('auth.reset_password', token=raw, _external=True)
            if current_app.config['DEV_SHOW_RESET_LINK']:
                reset_url = reset_url_value
            else:
                from ..services import send_email
                send_email(
                    'Reset your CareerHub password',
                    u.email,
                    f'Use this link within 60 minutes to reset your CareerHub password: {reset_url_value}',
                )
        flash('If an account exists for that email, a password reset link has been generated.','success')
    return render_template('auth/forgot_password.html',form=form,reset_url=reset_url)
@auth_bp.route('/reset-password/<token>',methods=['GET','POST'])
@limiter.limit('20 per 15 minutes', methods=['POST'], exempt_when=_local_auth_bypass)
def reset_password(token):
    h=hashlib.sha256(token.encode()).hexdigest(); t=PasswordResetToken.query.filter_by(token_hash=h).first()
    if not t or t.used_at or t.expires_at < datetime.utcnow(): flash('This reset link is invalid or expired.','error'); return redirect(url_for('auth.forgot_password'))
    form=ResetPasswordForm()
    if form.validate_on_submit():
        u=db.session.get(User,t.user_id); u.set_password(form.password.data); t.used_at=datetime.utcnow(); db.session.commit(); flash('Password reset successfully.','success'); return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html',form=form)
