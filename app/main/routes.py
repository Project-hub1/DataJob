from flask import Blueprint, render_template
from flask_login import current_user
from sqlalchemy import or_
from ..models import Job, Company, User, SavedJob, Application, JobSeekerProfile, CandidateResume, CandidateSkill, JobView
from ..extensions import db
from ..services import calculate_job_match
from datetime import datetime

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    active_jobs = Job.query.filter(
        Job.status == 'Active',
        Job.is_flagged.is_(False),
        Job.company.has(Company.approval_status == 'approved'),
        or_(Job.deadline.is_(None), Job.deadline >= datetime.utcnow())
    )
    featured_jobs = active_jobs.order_by(Job.created_at.desc()).limit(6).all()
    if current_user.is_authenticated and current_user.role == 'candidate':
        profile = current_user.candidate_profile
        resume_count = CandidateResume.query.filter_by(profile_id=profile.id).count() if profile else 0
        skill_count = CandidateSkill.query.filter_by(profile_id=profile.id).count() if profile else 0
        checks = [
            bool(profile and profile.full_name), bool(profile and profile.age),
            bool(profile and profile.headline), bool(profile and profile.location),
            bool(profile and profile.summary), bool(profile and profile.skills_text),
            bool(profile and profile.preferred_role), bool(profile and profile.photo),
            bool(profile and (profile.resume_filename or resume_count)),
            bool(profile and profile.education), bool(profile and profile.experience),
            bool(skill_count), bool(profile and profile.certifications),
            bool(profile and profile.projects)
        ]
        profile_completion = round(sum(checks) / len(checks) * 100) if checks else 0

        candidates = active_jobs.order_by(Job.created_at.desc()).limit(60).all()
        scored = []
        for job in candidates:
            score, reasons = calculate_job_match(profile, job)
            scored.append((score, job.created_at, job, reasons))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        recommended = [{'job': x[2], 'score': x[0], 'reasons': x[3]} for x in scored[:6]]

        applications = (Application.query.filter_by(candidate_id=current_user.id)
                        .order_by(Application.updated_at.desc(), Application.applied_at.desc()).limit(5).all())
        recent_views = (JobView.query.filter_by(viewer_id=current_user.id)
                        .order_by(JobView.viewed_at.desc()).limit(4).all())
        saved_count = SavedJob.query.filter_by(user_id=current_user.id).count()
        return render_template(
            'candidate/home.html', profile=profile, profile_completion=profile_completion,
            recommended=recommended, applications=applications, recent_views=recent_views,
            saved_count=saved_count, resume_count=resume_count, skill_count=skill_count
        )

    # CareerHub's public entry point is intentionally an account-first experience.
    # Logged-out visitors get the registration screen; authenticated candidates are
    # handled above and land on their personalised My Home. Public job/company
    # pages remain directly accessible from their URLs and navigation.
    register_form = None
    if not current_user.is_authenticated:
        from ..auth.forms import RegisterForm
        register_form = RegisterForm()
    return render_template(
        'home.html',
        job_count=active_jobs.count(),
        company_count=Company.query.filter_by(approval_status='approved').count(),
        candidate_count=User.query.filter_by(role='candidate', is_active=True).count(),
        featured_jobs=featured_jobs,
        register_form=register_form
    )
