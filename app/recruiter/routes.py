from datetime import datetime, timedelta
import os
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for, send_from_directory, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from ..extensions import db
from ..models import RecruiterProfile, Company, Job, Skill, Application, Notification, User, ApplicationStatusHistory, record_activity
from ..services import notify_matching_job_alerts

recruiter_bp=Blueprint('recruiter',__name__,url_prefix='/recruiter')

@recruiter_bp.before_request
def guard():
    if not current_user.is_authenticated: return current_app.login_manager.unauthorized()
    if current_user.role!='recruiter': abort(403)

def slugify(text): return ''.join(ch.lower() if ch.isalnum() else '-' for ch in text).strip('-')

def valid_website(value):
    if not value:
        return True
    parsed=urlparse(value)
    return parsed.scheme in {'http','https'} and bool(parsed.netloc)

def profile(): return current_user.recruiter_profile

def owned_job(job_id):
    j=db.session.get(Job,job_id)
    if not j or j.recruiter_id!=current_user.id: abort(404)
    return j

@recruiter_bp.get('/dashboard')
@login_required
def dashboard():
    p=profile(); company=p.company
    jobs=Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.created_at.desc()).all() if company else []
    apps=Application.query.join(Job).filter(Job.recruiter_id==current_user.id).order_by(Application.applied_at.desc()).limit(10).all()
    all_apps=Application.query.join(Job).filter(Job.recruiter_id==current_user.id).all()
    pipeline_counts={st: sum(1 for a in all_apps if a.status==st) for st in ['Applied','Under Review','Shortlisted','Interview','Hired','Rejected']}
    return render_template('recruiter/dashboard.html',profile=p,company=company,jobs=jobs,applications=apps,pipeline_counts=pipeline_counts)

@recruiter_bp.route('/company',methods=['GET','POST'])
@login_required
def company():
    p=profile(); c=p.company
    if request.method=='POST':
        name=request.form.get('name','').strip(); industry=request.form.get('industry','').strip(); location=request.form.get('location','').strip(); website=request.form.get('website','').strip(); description=request.form.get('description','').strip()
        recruiter_name=request.form.get('recruiter_name','').strip()[:120]
        designation=request.form.get('designation','').strip()[:120]
        raw_employee_count=request.form.get('employee_count','').strip()
        if not name or not industry or not location: flash('Company name, industry and location are required.','error'); return redirect(url_for('recruiter.company'))
        if not valid_website(website): flash('Website must start with http:// or https://.','error'); return redirect(url_for('recruiter.company'))
        try:
            employee_count=int(raw_employee_count) if raw_employee_count else 0
        except ValueError:
            flash('Employee count must be a whole number.','error'); return redirect(url_for('recruiter.company'))
        if employee_count < 0 or employee_count > 100000000:
            flash('Employee count must be between 0 and 100,000,000.','error'); return redirect(url_for('recruiter.company'))
        duplicate=Company.query.filter(Company.name.ilike(name), Company.id != (c.id if c else 0)).first()
        if duplicate: flash('A company with this name already exists.','error'); return redirect(url_for('recruiter.company'))
        p.full_name=recruiter_name
        p.designation=designation or 'Recruiter'
        if not c:
            base=slugify(name); slug=base; n=2
            while Company.query.filter_by(slug=slug).first(): slug=f'{base}-{n}'; n+=1
            c=Company(name=name,slug=slug,industry=industry,location=location,website=website,description=description,employee_count=employee_count,approval_status='approved' if current_app.config.get('AUTO_APPROVE_RECRUITER_COMPANIES', True) else 'pending'); db.session.add(c); db.session.flush(); p.company_id=c.id
        else:
            c.name=name; c.industry=industry; c.location=location; c.website=website; c.description=description; c.employee_count=employee_count
            if current_app.config.get('AUTO_APPROVE_RECRUITER_COMPANIES', True):
                c.approval_status='approved'
            elif c.approval_status != 'approved':
                c.approval_status='pending'
        db.session.commit(); flash('Company profile saved.','success'); return redirect(url_for('recruiter.company'))
    return render_template('recruiter/company.html',company=c)

@recruiter_bp.route('/jobs/new',methods=['GET','POST'])
@login_required
def new_job():
    p=profile()
    if not p.company: flash('Create your company profile before posting a job.','error'); return redirect(url_for('recruiter.company'))
    if request.method=='POST':
        if p.company.approval_status != 'approved':
            flash('Your company must be approved before you can publish jobs.', 'error')
            return redirect(url_for('recruiter.company'))
        title=request.form.get('title','').strip(); location=request.form.get('location','').strip(); description=request.form.get('description','').strip()
        if not title or not location or not description: flash('Title, location and description are required.','error'); return redirect(url_for('recruiter.new_job'))
        base=slugify(title); slug=f'{base}-{int(datetime.utcnow().timestamp())}'
        def num(name, default=0):
            raw=request.form.get(name)
            if raw in (None, ''): return default
            try: return float(raw)
            except (ValueError, TypeError): return default
        def money(name):
            try: return int(float(request.form.get(name) or 0)*100000)
            except ValueError: return None
        exp_min=max(0, num('experience_min'))
        exp_max=num('experience_max', None)
        if exp_max is not None and exp_max <= 0: exp_max=None
        if exp_max is not None and exp_max < exp_min: flash('Maximum experience must be greater than or equal to minimum experience.','error'); return redirect(url_for('recruiter.new_job'))
        salary_min=money('salary_min'); salary_max=money('salary_max')
        if salary_min is not None and salary_min < 0: salary_min=None
        if salary_max is not None and salary_max < 0: salary_max=None
        if salary_min is not None and salary_max is not None and salary_max < salary_min: flash('Maximum salary must be greater than or equal to minimum salary.','error'); return redirect(url_for('recruiter.new_job'))
        try: deadline_days=max(1, min(int(request.form.get('deadline_days') or 30), 3650))
        except ValueError: deadline_days=30
        j=Job(company_id=p.company.id,recruiter_id=current_user.id,title=title[:180],slug=slug,description=description,responsibilities=request.form.get('responsibilities',''),requirements=request.form.get('requirements',''),education=request.form.get('education',''),benefits=request.form.get('benefits',''),location=location[:120],work_mode=request.form.get('work_mode','On-site'),job_type=request.form.get('job_type','Full-time'),experience_min=exp_min,experience_max=exp_max,salary_min=salary_min,salary_max=salary_max,industry=p.company.industry,status='Active',deadline=datetime.utcnow()+timedelta(days=deadline_days))
        skill_names=[x.strip() for x in request.form.get('skills','').split(',') if x.strip()]
        j.skills=[Skill.query.filter_by(name=x).first() or Skill(name=x) for x in skill_names]; db.session.add(j)
        try:
            db.session.commit()
            record_activity(current_user.id, 'recruiter', 'job_created', f'Created job: {j.title}', actor_id=current_user.id, entity_type='job', entity_id=j.id, details=f'{j.location} · {j.work_mode} · {j.job_type}')
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('The job could not be published. Please check the details and try again.','error')
            return redirect(url_for('recruiter.new_job'))
        try:
            matches = notify_matching_job_alerts(j)
            db.session.commit()
            if matches:
                current_app.logger.info('Job alert notifications created for job_id=%s users=%s', j.id, matches)
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Job alert notification failed for job_id=%s', j.id)
        flash('Job published successfully. It is now live on CareerHub.','success')
        return redirect(url_for('recruiter.jobs'))
    return render_template('recruiter/job_form.html',job=None)

@recruiter_bp.route('/jobs/<int:job_id>/edit',methods=['GET','POST'])
@login_required
def edit_job(job_id):
    j=owned_job(job_id)
    if request.method=='POST':
        title=request.form.get('title','').strip()
        location=request.form.get('location','').strip()
        description=request.form.get('description','').strip()
        if not title or not location or not description:
            flash('Job title, location and description are required.','error')
            return redirect(url_for('recruiter.edit_job',job_id=j.id))
        try:
            experience_min=max(0,float(request.form.get('experience_min') or 0))
            experience_max=float(request.form.get('experience_max') or 0) or None
            if experience_max is not None and experience_max < experience_min:
                raise ValueError('Maximum experience must be greater than or equal to minimum experience.')
        except ValueError as exc:
            flash(str(exc) if str(exc) else 'Please enter valid experience values.','error')
            return redirect(url_for('recruiter.edit_job',job_id=j.id))
        try:
            salary_min=int(float(request.form.get('salary_min') or 0)*100000)
            salary_max=int(float(request.form.get('salary_max') or 0)*100000)
            if salary_min < 0 or salary_max < 0:
                raise ValueError('Salary cannot be negative.')
            if salary_min and salary_max and salary_max < salary_min:
                raise ValueError('Maximum salary must be greater than or equal to minimum salary.')
        except ValueError as exc:
            flash(str(exc) if str(exc) else 'Please enter valid salary values.','error')
            return redirect(url_for('recruiter.edit_job',job_id=j.id))
        try:
            deadline_days=int(request.form.get('deadline_days') or 30)
            if deadline_days < 1 or deadline_days > 3650:
                raise ValueError('Application deadline must be between 1 and 3650 days.')
        except ValueError as exc:
            flash(str(exc) if str(exc) else 'Please enter a valid application deadline.','error')
            return redirect(url_for('recruiter.edit_job',job_id=j.id))

        j.title=title[:180]
        j.description=description
        j.responsibilities=request.form.get('responsibilities','').strip()
        j.requirements=request.form.get('requirements','').strip()
        j.education=request.form.get('education','').strip()
        j.benefits=request.form.get('benefits','').strip()
        j.location=location[:120]
        j.work_mode=request.form.get('work_mode','On-site').strip()
        j.job_type=request.form.get('job_type','Full-time').strip()
        if request.form.get('status') in {'Active','Paused','Closed'}:
            j.status=request.form.get('status')
        j.experience_min=experience_min
        j.experience_max=experience_max
        j.salary_min=salary_min or None
        j.salary_max=salary_max or None
        j.deadline=datetime.utcnow()+timedelta(days=deadline_days)
        names=[x.strip()[:100] for x in request.form.get('skills','').split(',') if x.strip()]
        j.skills=[Skill.query.filter_by(name=x).first() or Skill(name=x) for x in dict.fromkeys(names)]
        try:
            db.session.commit()
            record_activity(current_user.id, 'recruiter', 'job_updated', f'Updated job: {j.title}', actor_id=current_user.id, entity_type='job', entity_id=j.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Job update failed for job_id=%s', j.id)
            flash('The job could not be updated. Your previous data was kept. Please try again.','error')
            return redirect(url_for('recruiter.edit_job',job_id=j.id))
        flash('Job updated successfully.','success')
        return redirect(url_for('recruiter.jobs'))
    remaining_days=30
    if j.deadline:
        remaining_days=max(1,min(3650,(j.deadline-datetime.utcnow()).days or 1))
    return render_template('recruiter/job_form.html',job=j,deadline_days=remaining_days)

@recruiter_bp.get('/jobs')
@login_required
def jobs():
    jobs=Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.created_at.desc()).all(); return render_template('recruiter/jobs.html',jobs=jobs)

@recruiter_bp.post('/jobs/<int:job_id>/status')
@login_required
def job_status(job_id):
    j=owned_job(job_id); status=request.form.get('status','Active')
    if status not in {'Active','Paused','Closed'}: abort(400)
    was_public = j.is_active_public
    j.status=status
    record_activity(current_user.id, 'recruiter', 'job_status_changed', f'Marked {j.title} as {status}', actor_id=current_user.id, entity_type='job', entity_id=j.id)
    db.session.commit()
    if status == 'Active' and not was_public:
        try:
            matches = notify_matching_job_alerts(j)
            db.session.commit()
            if matches:
                current_app.logger.info('Job alert notifications created for reactivated job_id=%s users=%s', j.id, matches)
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Job alert notification failed for job_id=%s', j.id)
    flash(f'Job marked {status}.','success'); return redirect(url_for('recruiter.jobs'))

@recruiter_bp.get('/jobs/<int:job_id>/applications')
@login_required
def applicants(job_id):
    j=owned_job(job_id)
    q=Application.query.filter_by(job_id=j.id)
    search=request.args.get('q','').strip(); status=request.args.get('status','').strip()
    rating=request.args.get('rating','').strip()
    if status in {'Applied','Under Review','Shortlisted','Interview','Rejected','Hired','Withdrawn'}:
        q=q.filter(Application.status==status)
    if rating.isdigit() and 1 <= int(rating) <= 5:
        q=q.filter(Application.recruiter_rating >= int(rating))
    if search:
        term=f'%{search}%'
        q=q.filter((Application.applicant_name.ilike(term)) | (Application.applicant_skills.ilike(term)) | (Application.applicant_education.ilike(term)) | (Application.recruiter_tags.ilike(term)))
    apps=q.order_by(Application.recruiter_rating.desc().nullslast(), Application.applied_at.desc()).all()
    return render_template('recruiter/applicants.html',job=j,applications=apps,search=search,status=status,rating=rating)


@recruiter_bp.get('/jobs/<int:job_id>/pipeline')
@login_required
def pipeline(job_id):
    j=owned_job(job_id)
    apps=Application.query.filter_by(job_id=j.id).order_by(Application.applied_at.desc()).all()
    columns={st: [] for st in ['Applied','Under Review','Shortlisted','Interview','Hired','Rejected','Withdrawn']}
    for a in apps:
        columns.setdefault(a.status, []).append(a)
    return render_template('recruiter/pipeline.html', job=j, columns=columns, total=len(apps))


@recruiter_bp.get('/applications/<int:application_id>')
@login_required
def application_detail(application_id):
    a=db.session.get(Application, application_id)
    if not a or not a.job or a.job.recruiter_id != current_user.id: abort(404)
    history=ApplicationStatusHistory.query.filter_by(application_id=a.id).order_by(ApplicationStatusHistory.changed_at.asc()).all()
    record_activity(current_user.id, 'recruiter', 'candidate_profile_viewed', f'Viewed {a.applicant_name or a.candidate.email}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=a.job.title)
    db.session.commit()
    from ..services import calculate_job_match
    try:
        score,reasons=calculate_job_match(a.candidate.candidate_profile, a.job)
    except Exception:
        score,reasons=0,[]
    return render_template('recruiter/application_detail.html', application=a, history=history, match_score=score, match_reasons=reasons)


@recruiter_bp.post('/applications/<int:application_id>/bulk-status')
@login_required
def bulk_application_status(application_id):
    # Endpoint kept separate from the single-record status route so existing forms remain stable.
    a=db.session.get(Application, application_id)
    if not a or not a.job or a.job.recruiter_id != current_user.id: abort(404)
    status=request.form.get('status','').strip()
    if status not in {'Applied','Under Review','Shortlisted','Interview','Rejected','Hired'}: abort(400)
    if status != a.status:
        a.status=status
        db.session.add(ApplicationStatusHistory(application_id=a.id,status=status,note='Moved from recruiter pipeline',changed_by_id=current_user.id))
        record_activity(current_user.id, 'recruiter', 'candidate_stage_changed', f'Moved candidate to {status}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=a.job.title)
        record_activity(a.candidate_id, 'candidate', 'application_stage_changed', f'Application for {a.job.title} moved to {status}', actor_id=current_user.id, entity_type='application', entity_id=a.id)
        db.session.add(Notification(user_id=a.candidate_id,title='Application update',message=f'Your application for {a.job.title} is now {status}.',link=url_for('candidate.applications')))
    db.session.commit()
    return redirect(url_for('recruiter.pipeline', job_id=a.job_id))


@recruiter_bp.get('/applications/<int:application_id>/resume')
@login_required
def applicant_resume(application_id):
    a=db.session.get(Application,application_id)
    if not a or not a.job or a.job.recruiter_id!=current_user.id or not a.resume_filename: abort(404)
    if a.resume_data:
        from io import BytesIO
        return send_file(BytesIO(a.resume_data), mimetype=a.resume_mimetype or 'application/octet-stream',
                         as_attachment=True, download_name=a.resume_original_name or a.resume_filename)
    return send_from_directory(os.path.join(current_app.instance_path,'uploads','resumes'),a.resume_filename,as_attachment=True,download_name=a.resume_original_name or a.resume_filename)

@recruiter_bp.post('/applications/<int:application_id>/status')
@login_required
def application_status(application_id):
    a=db.session.get(Application,application_id)
    if not a or not a.job or a.job.recruiter_id!=current_user.id: abort(404)
    status=request.form.get('status','Applied')
    if status not in {'Applied','Under Review','Shortlisted','Interview','Rejected','Hired'}: abort(400)
    note=request.form.get('note','').strip()[:500]
    if status != a.status or note:
        db.session.add(ApplicationStatusHistory(application_id=a.id,status=status,note=note or 'Status updated',changed_by_id=current_user.id))
        record_activity(current_user.id, 'recruiter', 'candidate_stage_changed', f'Moved candidate to {status}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=note or '')
        record_activity(a.candidate_id, 'candidate', 'application_stage_changed', f'Application for {a.job.title} moved to {status}', actor_id=current_user.id, entity_type='application', entity_id=a.id)
    a.recruiter_notes=request.form.get('recruiter_notes',a.recruiter_notes or '').strip()[:5000]
    try:
        rating=int(request.form.get('recruiter_rating','')) if request.form.get('recruiter_rating','').strip() else None
    except ValueError:
        rating=None
    if rating is not None and rating not in range(1,6):
        flash('Candidate rating must be between 1 and 5.','error')
        return redirect(url_for('recruiter.applicants',job_id=a.job_id))
    a.recruiter_rating=rating
    a.recruiter_tags=','.join(dict.fromkeys([x.strip()[:40] for x in request.form.get('recruiter_tags','').split(',') if x.strip()]))[:500]
    a.status=status
    message=f'Your application for {a.job.title} is now {status}.'
    db.session.add(Notification(user_id=a.candidate_id,title='Application update',message=message,link=url_for('candidate.applications')))
    record_activity(current_user.id, 'recruiter', 'candidate_evaluated', f'Updated evaluation for {a.applicant_name or a.candidate.email}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=f'Status: {status}')
    db.session.commit()
    try:
        from ..services import send_email
        send_email(f'CareerHub application update — {a.job.title}', a.candidate.email, message)
    except Exception:
        current_app.logger.exception('Application update email failed')
    flash('Application status updated.','success'); return redirect(url_for('recruiter.applicants',job_id=a.job_id))

@recruiter_bp.get('/activity')
@login_required
def activity():
    ActivityEvent = __import__('app.models', fromlist=['ActivityEvent']).ActivityEvent
    events = ActivityEvent.query.filter_by(user_id=current_user.id).order_by(ActivityEvent.created_at.desc()).limit(150).all()
    return render_template('recruiter/activity.html', events=events)

@recruiter_bp.get('/analytics')
@login_required
def analytics():
    from ..models import JobView
    jobs=Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.created_at.desc()).all()
    rows=[]
    for j in jobs:
        views=JobView.query.filter_by(job_id=j.id).count()
        apps=Application.query.filter_by(job_id=j.id).count()
        shortlisted=Application.query.filter_by(job_id=j.id,status='Shortlisted').count()
        rows.append({'job':j,'views':views,'applications':apps,'shortlisted':shortlisted})
    return render_template('recruiter/analytics.html',rows=rows,total_views=sum(r['views'] for r in rows),total_apps=sum(r['applications'] for r in rows),total_shortlisted=sum(r['shortlisted'] for r in rows))

@recruiter_bp.route('/interviews/<int:application_id>/schedule',methods=['POST'])
@login_required
def schedule_interview(application_id):
    from ..models import Interview
    a=db.session.get(Application,application_id)
    if not a or not a.job or a.job.recruiter_id!=current_user.id: abort(404)
    raw=request.form.get('scheduled_at','').strip()
    try: scheduled=datetime.fromisoformat(raw)
    except ValueError: flash('Please provide a valid interview date and time.','error'); return redirect(url_for('recruiter.applicants',job_id=a.job_id))
    interview=Interview.query.filter_by(application_id=a.id).first()
    if not interview: interview=Interview(application_id=a.id); db.session.add(interview)
    interview.scheduled_at=scheduled; interview.mode=request.form.get('mode','Video').strip(); interview.meeting_link=request.form.get('meeting_link','').strip()[:500]; interview.notes=request.form.get('notes','').strip()[:3000]
    if a.status != 'Interview':
        db.session.add(ApplicationStatusHistory(application_id=a.id,status='Interview',note='Interview scheduled',changed_by_id=current_user.id))
    a.status='Interview'
    record_activity(current_user.id, 'recruiter', 'interview_scheduled', f'Scheduled interview for {a.applicant_name or a.candidate.email}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=scheduled.strftime('%d %b %Y, %I:%M %p'))
    record_activity(a.candidate_id, 'candidate', 'interview_scheduled', f'Interview scheduled for {a.job.title}', actor_id=current_user.id, entity_type='application', entity_id=a.id, details=scheduled.strftime('%d %b %Y, %I:%M %p'))
    interview_message=f'Interview for {a.job.title} scheduled for {scheduled.strftime("%d %b %Y, %I:%M %p")}. Mode: {interview.mode or "Video"}.'
    db.session.add(Notification(user_id=a.candidate_id,title='Interview scheduled',message=interview_message,link=url_for('candidate.interviews')))
    db.session.commit()
    try:
        from ..services import send_email
        send_email(f'CareerHub interview scheduled — {a.job.title}', a.candidate.email, interview_message)
    except Exception:
        current_app.logger.exception('Interview email failed')
    flash('Interview scheduled and candidate notified.','success'); return redirect(url_for('recruiter.applicants',job_id=a.job_id))

@recruiter_bp.get('/interviews')
@login_required
def interviews():
    from ..models import Interview
    items=Interview.query.join(Application).join(Job).filter(Job.recruiter_id==current_user.id).order_by(Interview.scheduled_at.asc()).all()
    return render_template('recruiter/interviews.html',interviews=items)

@recruiter_bp.get('/messages')
@login_required
def messages():
    from ..models import Message
    items=Message.query.filter((Message.sender_id==current_user.id)|(Message.receiver_id==current_user.id)).order_by(Message.created_at.desc()).limit(100).all()
    for m in items:
        if m.receiver_id==current_user.id: m.is_read=True
    db.session.commit()
    return render_template('recruiter/messages.html',messages=items)

@recruiter_bp.post('/messages/<int:user_id>')
@login_required
def send_message(user_id):
    from ..models import Message, User
    receiver=db.session.get(User,user_id)
    if not receiver or receiver.id==current_user.id: abort(404)
    body=request.form.get('body','').strip()
    if not body: flash('Message cannot be empty.','error'); return redirect(url_for('recruiter.messages'))
    subject=request.form.get('subject','CareerHub message').strip()[:180]
    db.session.add(Message(sender_id=current_user.id,receiver_id=receiver.id,subject=subject,body=body[:5000]))
    record_activity(current_user.id, 'recruiter', 'message_sent', f'Sent a message to {receiver.email}', actor_id=current_user.id, entity_type='user', entity_id=receiver.id, details=subject)
    record_activity(receiver.id, receiver.role, 'message_received', f'Received a message from {current_user.email}', actor_id=current_user.id, entity_type='user', entity_id=current_user.id, details=subject)
    db.session.add(Notification(user_id=receiver.id,title='New CareerHub message',message=f'You received a message from {current_user.email}.',link=url_for('candidate.messages') if receiver.role=='candidate' else url_for('recruiter.messages')))
    db.session.commit(); flash('Message sent.','success'); return redirect(url_for('recruiter.messages'))
