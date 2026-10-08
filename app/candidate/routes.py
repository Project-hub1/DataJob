import os
import uuid
from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_from_directory, send_file, url_for, abort, g
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from ..security_utils import validate_upload
from ..services import calculate_job_match
from ..extensions import db, limiter
from ..models import Company
from ..models import SavedJob, Application, JobSeekerProfile, Education, Experience, JobAlert, Job, Notification, Skill, CandidateSkill, JobView, Certification, CandidateProject, CandidateLink, CandidateResume, CandidatePhoto, SearchHistory, SavedCompany, SavedSearch, Message, Interview, ActivityEvent, ApplicationStatusHistory, record_activity

candidate_bp=Blueprint('candidate',__name__,url_prefix='/candidate')

def candidate_only():
    return current_user.is_authenticated and current_user.role == 'candidate'

@candidate_bp.before_request
def guard():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.full_path))
    if current_user.role != 'candidate': abort(403)

@candidate_bp.get('/dashboard')
@login_required
def dashboard():
    """Render a candidate dashboard without allowing a legacy local DB to break login.

    Older CareerHub databases can be structurally behind the current models. The
    application repairs additive SQLite schema changes at startup, but this route
    also retries once after a database error so an interrupted first setup cannot
    turn a successful login into a blank HTTP 500 page.
    """
    from sqlalchemy.exc import SQLAlchemyError

    def load_dashboard_data():
        profile = current_user.candidate_profile
        if profile is None:
            profile = JobSeekerProfile(user_id=current_user.id, full_name='')
            db.session.add(profile)
            db.session.commit()

        applications = (Application.query.filter_by(candidate_id=current_user.id)
                        .order_by(Application.updated_at.desc(), Application.applied_at.desc())
                        .limit(8).all())
        saved_count = SavedJob.query.filter_by(user_id=current_user.id).count()
        resume_count = CandidateResume.query.filter_by(profile_id=profile.id).count()
        skill_count = CandidateSkill.query.filter_by(profile_id=profile.id).count()
        checks = [
            bool(profile.full_name), bool(profile.age), bool(profile.headline), bool(profile.location),
            bool(profile.summary), bool(profile.skills_text), bool(profile.preferred_role), bool(profile.photo),
            bool(profile.resume_filename or resume_count), bool(profile.education), bool(profile.experience),
            bool(skill_count), bool(profile.certifications), bool(profile.projects)
        ]
        profile_completion = round(sum(checks) / len(checks) * 100)

        candidates = (Job.query.filter(Job.status == 'Active', Job.is_flagged.is_(False),
                                       Job.company.has(Company.approval_status == 'approved'))
                      .order_by(Job.created_at.desc()).limit(60).all())
        scored = []
        for job in candidates:
            match_score, match_reasons = calculate_job_match(profile, job)
            scored.append((match_score, job.created_at, job, match_reasons))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        recommended = [{'job': x[2], 'score': x[0], 'reasons': x[3]} for x in scored[:6]]
        recent_views = (JobView.query.filter_by(viewer_id=current_user.id)
                        .order_by(JobView.viewed_at.desc()).limit(6).all())
        return profile, applications, saved_count, profile_completion, recommended, recent_views, resume_count, skill_count

    try:
        data = load_dashboard_data()
    except SQLAlchemyError:
        db.session.rollback()
        repair = getattr(current_app, 'repair_local_schema', None)
        if repair:
            try:
                repair()
                data = load_dashboard_data()
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Candidate dashboard failed after local schema recovery; request_id=%s',
                                              getattr(g, 'request_id', '-'))
                raise
        else:
            current_app.logger.exception('Candidate dashboard database error; request_id=%s',
                                         getattr(g, 'request_id', '-'))
            raise

    profile, applications, saved_count, profile_completion, recommended, recent_views, resume_count, skill_count = data
    return render_template('candidate/dashboard.html', profile=profile, applications=applications,
                           saved_count=saved_count, profile_completion=profile_completion,
                           recommended=recommended, recent_views=recent_views,
                           resume_count=resume_count, skill_count=skill_count)

@candidate_bp.route('/profile', methods=['GET','POST'], endpoint='profile')
@candidate_bp.route('/profile/edit', methods=['GET','POST'], endpoint='edit_profile')
@login_required
def profile():
    p = current_user.candidate_profile
    if p.resume_filename and not CandidateResume.query.filter_by(profile_id=p.id).first():
        db.session.add(CandidateResume(
            profile_id=p.id, filename=p.resume_filename,
            original_name=p.resume_original_name or p.resume_filename,
            is_primary=True
        ))
        db.session.commit()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        if not full_name:
            flash('Full name is required.', 'error')
            return redirect(url_for('candidate.profile'))

        age_raw = request.form.get('age', '').strip()
        age = None
        if age_raw:
            try:
                age = int(age_raw)
            except ValueError:
                flash('Age must be a valid number.', 'error')
                return redirect(url_for('candidate.profile'))
            if age < 13 or age > 100:
                flash('Please enter a valid age between 13 and 100.', 'error')
                return redirect(url_for('candidate.profile'))

        p.full_name = full_name[:120]
        p.age = age
        p.headline = request.form.get('headline', '').strip()[:180]
        p.location = request.form.get('location', '').strip()[:120]
        p.phone = request.form.get('phone', '').strip()[:30]
        p.work_status = request.form.get('work_status', '').strip()[:30]
        p.summary = request.form.get('summary', '').strip()[:5000]
        p.skills_text = request.form.get('skills_text', '').strip()[:3000]
        p.preferred_role = request.form.get('preferred_role', '').strip()[:180]
        try:
            salary_lpa = float(request.form.get('expected_salary') or 0)
            p.expected_salary = int(salary_lpa * 100000) if salary_lpa > 0 else None
        except ValueError:
            p.expected_salary = None

        # Rebuild repeatable profile sections from this single Save Profile form.
        Education.query.filter_by(profile_id=p.id).delete()
        degrees = request.form.getlist('education_degree[]')
        institutions = request.form.getlist('education_institution[]')
        years = request.form.getlist('education_year[]')
        for i, degree in enumerate(degrees):
            degree, institution = degree.strip(), (institutions[i] if i < len(institutions) else '').strip()
            if not degree and not institution:
                continue
            if not degree or not institution:
                flash('Each education entry needs both degree and institution.', 'error')
                return redirect(url_for('candidate.profile'))
            year = years[i].strip() if i < len(years) else ''
            db.session.add(Education(
                profile_id=p.id, degree=degree[:160], institution=institution[:200],
                year=int(year) if year.isdigit() else None
            ))

        Experience.query.filter_by(profile_id=p.id).delete()
        titles = request.form.getlist('experience_title[]')
        companies = request.form.getlist('experience_company[]')
        exp_years = request.form.getlist('experience_years[]')
        for i, title in enumerate(titles):
            title, company = title.strip(), (companies[i] if i < len(companies) else '').strip()
            if not title and not company:
                continue
            if not title or not company:
                flash('Each experience entry needs both role and company.', 'error')
                return redirect(url_for('candidate.profile'))
            try:
                yrs = max(0, min(float(exp_years[i] or 0), 60)) if i < len(exp_years) else 0
            except ValueError:
                yrs = 0
            db.session.add(Experience(profile_id=p.id, title=title[:160], company=company[:200], years=yrs))

        Certification.query.filter_by(profile_id=p.id).delete()
        cert_names = request.form.getlist('cert_name[]')
        cert_issuers = request.form.getlist('cert_issuer[]')
        cert_years = request.form.getlist('cert_year[]')
        cert_urls = request.form.getlist('cert_url[]')
        for i, name in enumerate(cert_names):
            name = name.strip()
            if not name:
                continue
            raw_year = cert_years[i].strip() if i < len(cert_years) else ''
            db.session.add(Certification(
                profile_id=p.id, name=name[:180],
                issuer=(cert_issuers[i] if i < len(cert_issuers) else '').strip()[:180],
                issue_year=int(raw_year) if raw_year.isdigit() else None,
                credential_url=(cert_urls[i] if i < len(cert_urls) else '').strip()[:500]
            ))

        CandidateProject.query.filter_by(profile_id=p.id).delete()
        project_names = request.form.getlist('project_name[]')
        project_tech = request.form.getlist('project_technologies[]')
        project_desc = request.form.getlist('project_description[]')
        project_urls = request.form.getlist('project_url[]')
        for i, name in enumerate(project_names):
            name = name.strip()
            if not name:
                continue
            db.session.add(CandidateProject(
                profile_id=p.id, name=name[:180],
                technologies=(project_tech[i] if i < len(project_tech) else '').strip()[:500],
                description=(project_desc[i] if i < len(project_desc) else '').strip()[:5000],
                project_url=(project_urls[i] if i < len(project_urls) else '').strip()[:500]
            ))

        links = p.links or CandidateLink(profile_id=p.id)
        links.linkedin = request.form.get('linkedin', '').strip()[:500]
        links.github = request.form.get('github', '').strip()[:500]
        links.portfolio = request.form.get('portfolio', '').strip()[:500]
        if not p.links:
            db.session.add(links)

        # Photo and resume are part of the same Save Profile action.
        photo = request.files.get('photo')
        if photo and photo.filename:
            ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else ''
            if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
                flash('Profile photo must be JPG, PNG or WEBP.', 'error')
                return redirect(url_for('candidate.profile'))
            data = photo.read()
            ok, reason = validate_upload(data, ext, max_size=current_app.config['MAX_PHOTO_SIZE'])
            if not ok:
                flash(reason, 'error')
                return redirect(url_for('candidate.profile'))
            item = p.photo
            stored = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
            if item:
                item.filename, item.data, item.mimetype = stored, data, (photo.mimetype or 'image/jpeg')
            else:
                db.session.add(CandidatePhoto(
                    profile_id=p.id, filename=stored, data=data,
                    mimetype=photo.mimetype or 'image/jpeg'
                ))

        resume = request.files.get('resume')
        if resume and resume.filename:
            ext = resume.filename.rsplit('.', 1)[-1].lower() if '.' in resume.filename else ''
            if ext not in {'pdf', 'doc', 'docx'}:
                flash('Resume must be PDF, DOC or DOCX.', 'error')
                return redirect(url_for('candidate.profile'))
            data = resume.read()
            ok, reason = validate_upload(data, ext, max_size=current_app.config['MAX_RESUME_SIZE'])
            if not ok:
                flash(reason, 'error')
                return redirect(url_for('candidate.profile'))
            stored = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
            CandidateResume.query.filter_by(profile_id=p.id).update({CandidateResume.is_primary: False})
            db.session.add(CandidateResume(
                profile_id=p.id, filename=stored,
                original_name=secure_filename(resume.filename)[:255],
                is_primary=True, data=data,
                mimetype=resume.mimetype or 'application/octet-stream'
            ))
            p.resume_filename = stored
            p.resume_original_name = secure_filename(resume.filename)[:255]

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Profile save failed')
            flash('Profile could not be saved. Please check the entered details and try again.', 'error')
            return redirect(url_for('candidate.profile'))

        record_activity(current_user.id, 'candidate', 'profile_updated', 'Updated your candidate profile', actor_id=current_user.id, entity_type='user', entity_id=current_user.id)
        db.session.commit()
        flash('Your complete profile has been saved successfully.', 'success')
        return redirect(url_for('candidate.profile'))

    return render_template('candidate/profile.html', profile=p)


@candidate_bp.post('/photo')
@login_required
def upload_photo():
    f = request.files.get('photo')
    if not f or not f.filename:
        flash('Please choose a profile photo.', 'error')
        return redirect(url_for('candidate.profile'))
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
        flash('Use JPG, PNG or WEBP for your profile photo.', 'error')
        return redirect(url_for('candidate.profile'))
    data = f.read()
    ok, reason = validate_upload(data, ext, max_size=current_app.config['MAX_PHOTO_SIZE'])
    if not ok:
        flash(reason, 'error')
        return redirect(url_for('candidate.profile'))
    item = current_user.candidate_profile.photo
    stored = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
    if item:
        item.filename, item.data, item.mimetype = stored, data, (f.mimetype or 'image/jpeg')
    else:
        db.session.add(CandidatePhoto(profile_id=current_user.candidate_profile.id,
                                      filename=stored, data=data,
                                      mimetype=f.mimetype or 'image/jpeg'))
    db.session.commit()
    flash('Profile photo updated.', 'success')
    return redirect(url_for('candidate.profile'))


@candidate_bp.post('/resume')
@login_required
def upload_resume():
    p = current_user.candidate_profile
    f = request.files.get('resume')
    if not f or not f.filename:
        flash('Please choose a resume PDF/DOC/DOCX.', 'error')
        return redirect(url_for('candidate.profile'))
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in {'pdf', 'doc', 'docx'}:
        flash('Only PDF, DOC and DOCX files are allowed.', 'error')
        return redirect(url_for('candidate.profile'))
    data = f.read()
    ok, reason = validate_upload(data, ext, max_size=current_app.config['MAX_RESUME_SIZE'])
    if not ok:
        flash(reason, 'error')
        return redirect(url_for('candidate.profile'))
    stored = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
    original = secure_filename(f.filename)[:255]
    CandidateResume.query.filter_by(profile_id=p.id).update({CandidateResume.is_primary: False})
    db.session.add(CandidateResume(
        profile_id=p.id, filename=stored, original_name=original,
        is_primary=True, data=data, mimetype=f.mimetype or 'application/octet-stream'
    ))
    p.resume_filename, p.resume_original_name = stored, original
    record_activity(current_user.id, 'candidate', 'resume_uploaded', f'Uploaded resume: {original}', actor_id=current_user.id, entity_type='resume', entity_id=None)
    db.session.commit()
    flash('Resume uploaded and set as your primary resume.', 'success')
    return redirect(url_for('candidate.profile'))


@candidate_bp.get('/photo')
@login_required
def photo():
    item = current_user.candidate_profile.photo
    if not item:
        abort(404)
    if item.data:
        from io import BytesIO
        return send_file(BytesIO(item.data), mimetype=item.mimetype or 'image/jpeg',
                         download_name=item.filename, max_age=3600)
    return send_from_directory(os.path.join(current_app.instance_path, 'uploads', 'profiles'), item.filename)


@candidate_bp.get('/resume')
@login_required
def resume():
    p = current_user.candidate_profile
    item = CandidateResume.query.filter_by(profile_id=p.id, is_primary=True).order_by(CandidateResume.created_at.desc()).first()
    if item and item.data:
        from io import BytesIO
        return send_file(BytesIO(item.data), mimetype=item.mimetype or 'application/octet-stream',
                         as_attachment=True, download_name=item.original_name or item.filename)
    if not p.resume_filename:
        abort(404)
    return send_from_directory(os.path.join(current_app.instance_path, 'uploads', 'resumes'),
                               p.resume_filename, as_attachment=True,
                               download_name=p.resume_original_name or p.resume_filename)


@candidate_bp.route('/education/add', methods=['POST'])
@login_required
def add_education():
    p=current_user.candidate_profile
    degree=request.form.get('degree','').strip(); institution=request.form.get('institution','').strip()
    if not degree or not institution: flash('Degree and institution are required.','error'); return redirect(url_for('candidate.profile'))
    year=request.form.get('year'); db.session.add(Education(profile_id=p.id,degree=degree[:160],institution=institution[:200],year=int(year) if year and year.isdigit() else None)); db.session.commit(); flash('Education added.','success'); return redirect(url_for('candidate.profile'))

@candidate_bp.post('/education/<int:item_id>/delete')
@login_required
def delete_education(item_id):
    item=db.session.get(Education,item_id)
    if item and item.profile_id==current_user.candidate_profile.id: db.session.delete(item); db.session.commit()
    return redirect(url_for('candidate.profile'))

@candidate_bp.post('/experience/add')
@login_required
def add_experience():
    p=current_user.candidate_profile; title=request.form.get('title','').strip(); company=request.form.get('company','').strip()
    if not title or not company: flash('Role and company are required.','error'); return redirect(url_for('candidate.profile'))
    try: years=float(request.form.get('years') or 0)
    except ValueError: years=0
    years=max(0, min(years, 60))
    db.session.add(Experience(profile_id=p.id,title=title[:160],company=company[:200],years=years)); db.session.commit(); flash('Experience added.','success'); return redirect(url_for('candidate.profile'))

@candidate_bp.post('/experience/<int:item_id>/delete')
@login_required
def delete_experience(item_id):
    item=db.session.get(Experience,item_id)
    if item and item.profile_id==current_user.candidate_profile.id: db.session.delete(item); db.session.commit()
    return redirect(url_for('candidate.profile'))

@candidate_bp.post('/companies/<int:company_id>/save')
@login_required
def save_company(company_id):
    company=db.session.get(Company,company_id)
    if not company or company.approval_status!='approved': abort(404)
    item=SavedCompany.query.filter_by(user_id=current_user.id,company_id=company_id).first()
    if item: db.session.delete(item); message='Company removed from saved list.'
    else: db.session.add(SavedCompany(user_id=current_user.id,company_id=company_id)); message='Company saved.'
    db.session.commit(); flash(message,'success'); return redirect(url_for('jobs.company_detail',company_id=company_id))

@candidate_bp.get('/saved-companies')
@login_required
def saved_companies():
    saved=SavedCompany.query.filter_by(user_id=current_user.id).order_by(SavedCompany.created_at.desc()).all()
    return render_template('candidate/saved_companies.html',saved=saved)

@candidate_bp.route('/alerts', methods=['GET', 'POST'])
@login_required
def alerts():
    """Manage genuine candidate job alerts."""
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip()[:180]
        location = request.form.get('location', '').strip()[:120]
        if not keyword and not location:
            flash('Enter a keyword or location for your alert.', 'error')
            return redirect(url_for('candidate.alerts'))
        db.session.add(JobAlert(user_id=current_user.id, keyword=keyword, location=location, is_active=True))
        record_activity(current_user.id, 'candidate', 'job_alert_created', 'Created a job alert',
                        entity_type='job_alert', details=f'{keyword or "Any job"} · {location or "Any location"}')
        db.session.commit()
        flash('Job alert created successfully.', 'success')
        return redirect(url_for('candidate.alerts'))
    alerts_list = JobAlert.query.filter_by(user_id=current_user.id).order_by(JobAlert.created_at.desc()).all()
    return render_template('candidate/alerts.html', alerts=alerts_list)


@candidate_bp.post('/alerts/<int:alert_id>/delete')
@login_required
def delete_alert(alert_id):
    item = db.session.get(JobAlert, alert_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    db.session.delete(item)
    record_activity(current_user.id, 'candidate', 'job_alert_deleted', 'Deleted a job alert',
                    entity_type='job_alert', entity_id=item.id)
    db.session.commit()
    flash('Job alert deleted.', 'success')
    return redirect(url_for('candidate.alerts'))


@candidate_bp.get('/saved-searches')
@login_required
def saved_searches():
    import urllib.parse
    searches = SavedSearch.query.filter_by(user_id=current_user.id).order_by(SavedSearch.created_at.desc()).all()
    prepared = []
    for item in searches:
        query = urllib.parse.urlencode({'q': item.query, 'location': item.location}, doseq=True)
        prepared.append((item, query))
    return render_template('candidate/saved_searches.html', searches=prepared)


@candidate_bp.post('/saved-searches/<int:search_id>/delete')
@login_required
def delete_saved_search(search_id):
    item = db.session.get(SavedSearch, search_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    db.session.delete(item)
    record_activity(current_user.id, 'candidate', 'saved_search_deleted', f'Deleted saved search: {item.name}',
                    entity_type='saved_search', entity_id=item.id)
    db.session.commit()
    flash('Saved search deleted.', 'success')
    return redirect(url_for('candidate.saved_searches'))


@candidate_bp.get('/search-history')
@login_required
def search_history():
    history = SearchHistory.query.filter_by(user_id=current_user.id).order_by(SearchHistory.created_at.desc()).limit(100).all()
    return render_template('candidate/search_history.html', history=history)


@candidate_bp.post('/search-history/clear')
@login_required
def clear_search_history():
    SearchHistory.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
    record_activity(current_user.id, 'candidate', 'search_history_cleared', 'Cleared job search history')
    db.session.commit()
    flash('Search history cleared.', 'success')
    return redirect(url_for('candidate.search_history'))


@candidate_bp.get('/messages')
@login_required
def messages():
    from sqlalchemy import or_
    items = (Message.query.filter(or_(Message.sender_id == current_user.id, Message.receiver_id == current_user.id))
             .order_by(Message.created_at.desc()).limit(100).all())
    unread = Message.query.filter_by(receiver_id=current_user.id, is_read=False).all()
    for item in unread:
        item.is_read = True
    if unread:
        db.session.commit()
    return render_template('candidate/messages.html', messages=items)


@candidate_bp.get('/interviews')
@login_required
def interviews():
    from datetime import datetime
    items = (Interview.query.join(Application, Interview.application_id == Application.id)
             .filter(Application.candidate_id == current_user.id)
             .filter(Interview.scheduled_at.isnot(None))
             .order_by(Interview.scheduled_at.asc()).all())
    return render_template('candidate/interviews.html', interviews=items)


@candidate_bp.get('/activity')
@login_required
def activity():
    events = (ActivityEvent.query.filter_by(user_id=current_user.id)
              .order_by(ActivityEvent.created_at.desc()).limit(200).all())
    return render_template('candidate/activity.html', events=events)




@candidate_bp.post('/saved/<int:job_id>/remove')
@login_required
def remove_saved(job_id):
    item = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if not item:
        abort(404)
    job_title = item.job.title if item.job else 'job'
    db.session.delete(item)
    record_activity(current_user.id, 'candidate', 'job_unsaved', f'Removed {job_title} from saved jobs',
                    entity_type='job', entity_id=job_id)
    db.session.commit()
    flash('Job removed from saved jobs.', 'success')
    return redirect(url_for('candidate.saved_jobs'))


@candidate_bp.get('/resumes')
@login_required
def resumes():
    p = current_user.candidate_profile
    items = CandidateResume.query.filter_by(profile_id=p.id).order_by(CandidateResume.created_at.desc()).all()
    return render_template('candidate/resumes.html', resumes=items)


@candidate_bp.get('/resumes/<int:resume_id>/download')
@login_required
def download_resume(resume_id):
    item = db.session.get(CandidateResume, resume_id)
    if not item or item.profile_id != current_user.candidate_profile.id:
        abort(404)
    if item.data:
        from io import BytesIO
        return send_file(BytesIO(item.data), mimetype=item.mimetype or 'application/octet-stream',
                         as_attachment=True, download_name=item.original_name or item.filename)
    abort(404)


@candidate_bp.post('/resumes/<int:resume_id>/primary')
@login_required
def primary_resume(resume_id):
    item = db.session.get(CandidateResume, resume_id)
    if not item or item.profile_id != current_user.candidate_profile.id:
        abort(404)
    CandidateResume.query.filter_by(profile_id=item.profile_id).update({CandidateResume.is_primary: False})
    item.is_primary = True
    current_user.candidate_profile.resume_filename = item.filename
    current_user.candidate_profile.resume_original_name = item.original_name
    record_activity(current_user.id, 'candidate', 'primary_resume_changed', f'Made {item.original_name} the primary resume',
                    entity_type='resume', entity_id=item.id)
    db.session.commit()
    flash('Primary resume updated.', 'success')
    return redirect(url_for('candidate.resumes'))


@candidate_bp.post('/resumes/<int:resume_id>/delete')
@login_required
def delete_resume(resume_id):
    item = db.session.get(CandidateResume, resume_id)
    if not item or item.profile_id != current_user.candidate_profile.id:
        abort(404)
    was_primary = item.is_primary
    db.session.delete(item)
    if was_primary:
        replacement = (CandidateResume.query.filter_by(profile_id=current_user.candidate_profile.id)
                       .filter(CandidateResume.id != item.id)
                       .order_by(CandidateResume.created_at.desc()).first())
        if replacement:
            replacement.is_primary = True
            current_user.candidate_profile.resume_filename = replacement.filename
            current_user.candidate_profile.resume_original_name = replacement.original_name
        else:
            current_user.candidate_profile.resume_filename = None
            current_user.candidate_profile.resume_original_name = None
    record_activity(current_user.id, 'candidate', 'resume_deleted', f'Deleted resume {item.original_name}',
                    entity_type='resume', entity_id=item.id)
    db.session.commit()
    flash('Resume deleted.', 'success')
    return redirect(url_for('candidate.resumes'))


@candidate_bp.post('/companies/<int:company_id>/review')
@login_required
def review_company_profile(company_id):
    from ..models import Company, CompanyReview
    company = db.session.get(Company, company_id)
    if not company or company.approval_status != 'approved':
        abort(404)
    eligible = (Application.query.join(Job).filter(Application.candidate_id == current_user.id,
                                                     Job.company_id == company_id).first())
    if not eligible:
        flash('You can review a company only after applying to one of its jobs.', 'error')
        return redirect(url_for('jobs.company_detail', company_id=company_id))
    rating = request.form.get('rating', type=int) or 0
    title = request.form.get('title', '').strip()[:160]
    body = request.form.get('body', '').strip()[:3000]
    if rating not in range(1, 6) or len(body) < 20:
        flash('Please provide a rating from 1–5 and at least 20 characters of review text.', 'error')
        return redirect(url_for('jobs.company_detail', company_id=company_id))
    from ..models import CompanyReview
    existing = CompanyReview.query.filter_by(company_id=company_id, user_id=current_user.id).first()
    if existing:
        existing.rating, existing.title, existing.body = rating, title, body
        action = 'company_review_updated'
    else:
        db.session.add(CompanyReview(company_id=company_id, user_id=current_user.id,
                                     rating=rating, title=title, body=body))
        action = 'company_review_created'
    record_activity(current_user.id, 'candidate', action, f'Reviewed {company.name}',
                    entity_type='company', entity_id=company_id)
    db.session.commit()
    flash('Your verified company review has been saved.', 'success')
    return redirect(url_for('jobs.company_detail', company_id=company_id))

@candidate_bp.get('/notifications')
def notifications():
    """Show the signed-in candidate's real notification feed."""
    notifications = (Notification.query.filter_by(user_id=current_user.id)
                     .order_by(Notification.created_at.desc()).limit(100).all())
    unread = [n for n in notifications if not n.is_read]
    if unread:
        for n in unread:
            n.is_read = True
        db.session.commit()
    return render_template('candidate/notifications.html', notifications=notifications)

@candidate_bp.get('/saved')
@login_required
def saved_jobs():
    saved = SavedJob.query.filter_by(user_id=current_user.id).order_by(SavedJob.created_at.desc()).all()
    active_saved = [item for item in saved if item.job.is_active_public]
    return render_template('candidate/saved.html', saved=active_saved)


@candidate_bp.post('/applications/<int:application_id>/withdraw')
@login_required
def withdraw_application(application_id):
    item=db.session.get(Application,application_id)
    if not item or item.candidate_id!=current_user.id: abort(404)
    if item.status in {'Hired','Rejected','Withdrawn'}:
        flash('This application can no longer be withdrawn.','error')
    else:
        item.status='Withdrawn'; db.session.add(ApplicationStatusHistory(application_id=item.id, status='Withdrawn', note='Withdrawn by candidate', changed_by_id=current_user.id)); record_activity(current_user.id, 'candidate', 'application_withdrawn', f'Withdrew application for {item.job.title}', entity_type='application', entity_id=item.id); db.session.commit(); flash('Application withdrawn.','success')
    return redirect(url_for('candidate.applications'))

@candidate_bp.route('/applications')
@login_required
def applications():
    status=request.args.get('status','').strip(); q=Application.query.filter_by(candidate_id=current_user.id)
    if status: q=q.filter_by(status=status)
    apps=q.order_by(Application.applied_at.desc()).all(); return render_template('candidate/applications.html',applications=apps,status=status)

@candidate_bp.route('/apply/<int:job_id>', methods=['GET','POST'])
@login_required
def apply(job_id):
    job = db.session.get(Job, job_id)
    if not job or not job.is_active_public:
        abort(404)

    existing = Application.query.filter_by(job_id=job.id, candidate_id=current_user.id).first()
    if existing:
        flash('You have already applied to this job.', 'error')
        return redirect(url_for('candidate.applications'))

    p = current_user.candidate_profile
    primary = CandidateResume.query.filter_by(
        profile_id=p.id, is_primary=True
    ).order_by(CandidateResume.created_at.desc()).first()

    if request.method == 'POST':
        name = request.form.get('applicant_name', '').strip()[:120]
        education = request.form.get('applicant_education', '').strip()[:3000]
        skills = request.form.get('applicant_skills', '').strip()[:3000]
        experience = request.form.get('applicant_experience', '').strip()[:120]
        age_raw = request.form.get('applicant_age', '').strip()
        if not name or not education or not skills or not age_raw or not experience:
            flash('Name, education, age, skills and experience are required.', 'error')
            return redirect(url_for('candidate.apply', job_id=job.id))
        try:
            age = int(age_raw)
        except ValueError:
            flash('Please enter a valid age.', 'error')
            return redirect(url_for('candidate.apply', job_id=job.id))
        if age < 13 or age > 100:
            flash('Please enter a valid age between 13 and 100.', 'error')
            return redirect(url_for('candidate.apply', job_id=job.id))

        uploaded = request.files.get('application_resume')
        resume_data = resume_name = resume_mimetype = resume_filename = None
        if uploaded and uploaded.filename:
            ext = uploaded.filename.rsplit('.', 1)[-1].lower() if '.' in uploaded.filename else ''
            if ext not in {'pdf', 'doc', 'docx'}:
                flash('Application resume must be PDF, DOC or DOCX.', 'error')
                return redirect(url_for('candidate.apply', job_id=job.id))
            resume_data = uploaded.read()
            ok, reason = validate_upload(resume_data, ext, max_size=current_app.config['MAX_RESUME_SIZE'])
            if not ok:
                flash(reason, 'error')
                return redirect(url_for('candidate.apply', job_id=job.id))
            resume_name = secure_filename(uploaded.filename)[:255]
            resume_mimetype = uploaded.mimetype or 'application/octet-stream'
            resume_filename = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
        elif primary and primary.data:
            resume_data = primary.data
            resume_name = primary.original_name
            resume_mimetype = primary.mimetype
            resume_filename = primary.filename
        else:
            flash('Please upload a resume to apply.', 'error')
            return redirect(url_for('candidate.apply', job_id=job.id))

        cover = request.form.get('cover_letter', '').strip()[:5000]
        info = request.form.get('additional_info', '').strip()[:3000]
        app = Application(
            job_id=job.id, candidate_id=current_user.id, status='Applied',
            cover_letter=cover, additional_info=info,
            resume_filename=resume_filename, resume_original_name=resume_name,
            resume_data=resume_data, resume_mimetype=resume_mimetype,
            applicant_name=name, applicant_education=education,
            applicant_age=age, applicant_skills=skills,
            applicant_experience=experience
        )
        db.session.add(app)
        db.session.flush()
        db.session.add(ApplicationStatusHistory(application_id=app.id, status='Applied', note='Application submitted', changed_by_id=current_user.id))
        record_activity(current_user.id, 'candidate', 'application_submitted', f'Applied for {job.title}', entity_type='application', entity_id=app.id, details=f'{job.company.name} · {job.location}')
        if job.recruiter_id:
            record_activity(job.recruiter_id, 'recruiter', 'application_received', f'New application for {job.title}', actor_id=current_user.id, entity_type='application', entity_id=app.id, details=f'{name} submitted an application')
        if job.recruiter_id:
            db.session.add(Notification(
                user_id=job.recruiter_id, title='New job application',
                message=f'{name} applied for {job.title}.',
                link=url_for('recruiter.applicants', job_id=job.id)
            ))
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Application save failed')
            flash('Application could not be submitted. Please try again.', 'error')
            return redirect(url_for('candidate.apply', job_id=job.id))
        flash('Application submitted successfully.', 'success')
        return redirect(url_for('candidate.applications'))

    education_text = '; '.join(
        f'{e.degree} — {e.institution}' + (f' ({e.year})' if e.year else '')
        for e in p.education
    )
    experience_text = '; '.join(
        f'{e.title} — {e.company} ({e.years:g} years)' for e in p.experience
    )
    return render_template(
        'candidate/apply.html', job=job, profile=p, primary_resume=primary,
        education_text=education_text, experience_text=experience_text
    )


@candidate_bp.get('/applications/<int:application_id>/timeline')
@login_required
def application_timeline(application_id):
    item=db.session.get(Application, application_id)
    if not item or item.candidate_id != current_user.id:
        abort(404)
    history=ApplicationStatusHistory.query.filter_by(application_id=item.id).order_by(ApplicationStatusHistory.changed_at.asc()).all()
    if not history:
        history=[ApplicationStatusHistory(application_id=item.id,status=item.status,note='Current status',changed_at=item.updated_at or item.applied_at)]
    return render_template('candidate/application_timeline.html', application=item, history=history)

@candidate_bp.route('/resume-builder', methods=['GET', 'POST'])
@login_required
def resume_builder():
    p = current_user.candidate_profile

    def section_state():
        return {
            'personal': bool(p.full_name and p.phone and p.location),
            'summary': bool((p.summary or '').strip()),
            'skills': bool((p.skills_text or '').strip()),
            'education': bool(p.education),
            'experience': bool(p.resume_is_fresher or p.experience),
            'projects': bool(p.projects),
            'certifications': bool(p.certifications),
            'links': bool(p.links and any((p.links.linkedin, p.links.github, p.links.portfolio))),
            'achievements': bool((p.achievements or '').strip()),
            'languages': bool((p.languages or '').strip()),
        }

    def save_builder_form():
        p.full_name = request.form.get('full_name', '').strip()[:120]
        p.phone = request.form.get('phone', '').strip()[:30]
        p.location = request.form.get('location', '').strip()[:120]
        p.headline = request.form.get('headline', '').strip()[:180]
        p.summary = request.form.get('summary', '').strip()[:5000]
        p.skills_text = request.form.get('skills_text', '').strip()[:3000]
        p.resume_is_fresher = request.form.get('resume_is_fresher') == '1'
        p.achievements = request.form.get('achievements', '').strip()[:5000]
        p.languages = request.form.get('languages', '').strip()[:1000]

        Education.query.filter_by(profile_id=p.id).delete()
        degrees = request.form.getlist('education_degree[]')
        institutions = request.form.getlist('education_institution[]')
        years = request.form.getlist('education_year[]')
        for i, degree in enumerate(degrees):
            degree = degree.strip(); institution = (institutions[i] if i < len(institutions) else '').strip()
            year = (years[i] if i < len(years) else '').strip()
            if not degree and not institution and not year:
                continue
            if not degree or not institution:
                raise ValueError('Each education entry needs a degree and institution.')
            db.session.add(Education(profile_id=p.id, degree=degree[:160], institution=institution[:200], year=int(year) if year.isdigit() else None))

        Experience.query.filter_by(profile_id=p.id).delete()
        titles = request.form.getlist('experience_title[]')
        companies = request.form.getlist('experience_company[]')
        exp_years = request.form.getlist('experience_years[]')
        for i, title in enumerate(titles):
            title = title.strip(); company = (companies[i] if i < len(companies) else '').strip()
            raw_years = (exp_years[i] if i < len(exp_years) else '').strip()
            if not title and not company and not raw_years:
                continue
            if not title or not company:
                raise ValueError('Each experience entry needs a role and company.')
            try: yrs = max(0, min(float(raw_years or 0), 60))
            except ValueError: yrs = 0
            db.session.add(Experience(profile_id=p.id, title=title[:160], company=company[:200], years=yrs))

        Certification.query.filter_by(profile_id=p.id).delete()
        cert_names = request.form.getlist('cert_name[]'); cert_issuers = request.form.getlist('cert_issuer[]')
        cert_years = request.form.getlist('cert_year[]'); cert_urls = request.form.getlist('cert_url[]')
        for i, name in enumerate(cert_names):
            name = name.strip(); issuer = (cert_issuers[i] if i < len(cert_issuers) else '').strip()
            year = (cert_years[i] if i < len(cert_years) else '').strip(); url = (cert_urls[i] if i < len(cert_urls) else '').strip()
            if not name and not issuer and not year and not url: continue
            if not name: raise ValueError('Each certification needs a certificate name.')
            db.session.add(Certification(profile_id=p.id, name=name[:180], issuer=issuer[:180], issue_year=int(year) if year.isdigit() else None, credential_url=url[:500]))

        CandidateProject.query.filter_by(profile_id=p.id).delete()
        names = request.form.getlist('project_name[]'); techs = request.form.getlist('project_technologies[]')
        descs = request.form.getlist('project_description[]'); urls = request.form.getlist('project_url[]')
        for i, name in enumerate(names):
            name = name.strip(); tech = (techs[i] if i < len(techs) else '').strip(); desc = (descs[i] if i < len(descs) else '').strip(); url = (urls[i] if i < len(urls) else '').strip()
            if not name and not tech and not desc and not url: continue
            if not name: raise ValueError('Each project needs a project name.')
            db.session.add(CandidateProject(profile_id=p.id, name=name[:180], technologies=tech[:500], description=desc[:5000], project_url=url[:500]))

        links = p.links or CandidateLink(profile_id=p.id)
        links.linkedin = request.form.get('linkedin', '').strip()[:500]
        links.github = request.form.get('github', '').strip()[:500]
        links.portfolio = request.form.get('portfolio', '').strip()[:500]
        if not p.links:
            db.session.add(links)

    def required_sections():
        state = section_state()
        return ['personal', 'summary', 'skills', 'education', 'experience', 'projects']

    if request.method == 'POST':
        try:
            save_builder_form()
            db.session.flush()
            # Repeatable relationship collections were rebuilt above; expire them so
            # the completion checker reads the just-saved rows in the same request.
            for attr in ('education', 'experience', 'certifications', 'projects', 'links'):
                try:
                    db.session.expire(p, [attr])
                except Exception:
                    pass
            state = section_state()
            missing = [name for name in required_sections() if not state[name]]
            # Always persist a valid form submission before checking completeness.
            # Previously an incomplete "Create Resume" request rolled the entire form
            # back, unexpectedly discarding everything the candidate had just entered.
            db.session.commit()
            if request.form.get('action') == 'create':
                if missing:
                    labels = {'personal':'Personal Information','summary':'Professional Summary','skills':'Skills','education':'Education','experience':'Experience / Fresher','projects':'Projects'}
                    flash('Your progress was saved. Complete: ' + ', '.join(labels[x] for x in missing) + '.', 'error')
                    return redirect(url_for('candidate.resume_builder'))
                record_activity(current_user.id, 'candidate', 'resume_created', 'Created a resume with Resume Builder', actor_id=current_user.id, entity_type='resume', entity_id=None)
                db.session.commit()
                return _send_builder_pdf(p, request.form.get('resume_template', 'modern'))
            record_activity(current_user.id, 'candidate', 'resume_builder_updated', 'Updated Resume Builder sections', actor_id=current_user.id, entity_type='resume', entity_id=None)
            db.session.commit()
            flash('Resume sections saved.', 'success')
            return redirect(url_for('candidate.resume_builder'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('candidate.resume_builder'))

    sections = section_state()
    missing = [x for x in required_sections() if not sections[x]]
    return render_template('candidate/resume_builder.html', profile=p, sections=sections, missing=missing, created=request.args.get('created') == '1', selected_template=request.args.get('template', 'modern'))


def _send_builder_pdf(p, template='modern'):
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import mm
    from flask import make_response

    buf = BytesIO()
    template = template if template in {'modern', 'classic', 'minimal'} else 'modern'
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm, title='CareerHub Resume')
    styles = getSampleStyleSheet()
    # Three ATS-safe print layouts. They share the same content model so a
    # candidate can switch appearance without rebuilding the resume.
    if template == 'classic':
        title_size, title_leading, accent = 19, 23, '#1d2939'
        title_weight, section_weight = 'Helvetica-Bold', 'Helvetica-Bold'
    elif template == 'minimal':
        title_size, title_leading, accent = 22, 25, '#111827'
        title_weight, section_weight = 'Helvetica-Bold', 'Helvetica'
    else:
        title_size, title_leading, accent = 21, 25, '#2457d6'
        title_weight, section_weight = 'Helvetica-Bold', 'Helvetica-Bold'

    title = ParagraphStyle('ResumeTitle', parent=styles['Title'], fontName=title_weight,
                           fontSize=title_size, leading=title_leading, textColor=accent,
                           spaceAfter=3, alignment=TA_LEFT)
    sub = ParagraphStyle('ResumeSub', parent=styles['Normal'], fontSize=9, leading=12,
                         textColor='#475467', spaceAfter=7)
    h = ParagraphStyle('ResumeH', parent=styles['Heading2'], fontName=section_weight,
                       fontSize=10 if template != 'minimal' else 10.5, leading=13,
                       textColor=accent, spaceBefore=9, spaceAfter=4)
    body = ParagraphStyle('ResumeBody', parent=styles['BodyText'], fontSize=8.8,
                          leading=12.2, textColor='#344054', spaceAfter=3)
    esc = lambda x: str(x or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    links = p.links
    contact = ' · '.join(x for x in [p.headline, p.location, p.phone, current_user.email] if x)
    story = [Paragraph(esc(p.full_name or current_user.email), title), Paragraph(esc(contact), sub), HRFlowable(width='100%', spaceBefore=2, spaceAfter=6)]
    sections = [
        ('SUMMARY', p.summary), ('SKILLS', p.skills_text),
    ]
    for heading, text_value in sections:
        if text_value: story += [Paragraph(heading, h), Paragraph(esc(text_value).replace('\n','<br/>'), body)]
    if p.experience:
        story.append(Paragraph('EXPERIENCE', h))
        for e in p.experience: story.append(Paragraph(f'<b>{esc(e.title)}</b> — {esc(e.company)}' + (f' ({esc(e.years)} years)' if e.years else ''), body))
    if p.education:
        story.append(Paragraph('EDUCATION', h))
        for e in p.education: story.append(Paragraph(f'<b>{esc(e.degree)}</b> — {esc(e.institution)}{(" ("+esc(e.year)+")") if e.year else ""}', body))
    if p.projects:
        story.append(Paragraph('PROJECTS', h))
        for x in p.projects:
            line = f'<b>{esc(x.name)}</b>'
            if x.technologies: line += f' — {esc(x.technologies)}'
            if x.description: line += f'<br/>{esc(x.description)}'
            if x.project_url: line += f'<br/>{esc(x.project_url)}'
            story.append(Paragraph(line, body))
    if p.certifications:
        story.append(Paragraph('CERTIFICATIONS', h))
        for c in p.certifications: story.append(Paragraph(f'<b>{esc(c.name)}</b> — {esc(c.issuer)}' + (f' ({esc(c.issue_year)})' if c.issue_year else ''), body))
    if p.achievements: story += [Paragraph('ACHIEVEMENTS', h), Paragraph(esc(p.achievements).replace('\n','<br/>'), body)]
    if p.languages: story += [Paragraph('LANGUAGES', h), Paragraph(esc(p.languages), body)]
    if links and any((links.linkedin, links.github, links.portfolio)):
        story.append(Paragraph('LINKS', h))
        for label, value in [('LinkedIn', links.linkedin), ('GitHub', links.github), ('Portfolio', links.portfolio)]:
            if value: story.append(Paragraph(f'<b>{label}:</b> {esc(value)}', body))
    doc.build(story)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename="CareerHub_Resume.pdf"'
    return response


@candidate_bp.get('/resume-builder/download')
@login_required
def resume_builder_download():
    p = current_user.candidate_profile
    state = {
        'personal': bool(p.full_name and p.phone and p.location),
        'summary': bool((p.summary or '').strip()),
        'skills': bool((p.skills_text or '').strip()),
        'education': bool(p.education),
        'experience': bool(p.resume_is_fresher or p.experience),
        'projects': bool(p.projects),
    }
    missing = [x for x in state if not state[x]]
    if missing:
        flash('Complete all required Resume Builder sections before downloading.', 'error')
        return redirect(url_for('candidate.resume_builder'))
    return _send_builder_pdf(p, request.args.get('template', 'modern'))
