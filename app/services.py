import smtplib
from email.message import EmailMessage
from flask import current_app


def send_email(subject, recipient, text_body, html_body=None):
    host = current_app.config.get('SMTP_HOST')
    sender = current_app.config.get('MAIL_FROM') or current_app.config.get('SMTP_USERNAME')
    if not host or not sender:
        current_app.logger.warning('Email not sent because SMTP is not configured. recipient=%s subject=%s', recipient, subject)
        return False
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')
    try:
        with smtplib.SMTP(host, current_app.config['SMTP_PORT'], timeout=15) as server:
            if current_app.config.get('SMTP_USE_TLS', True):
                server.starttls()
            username = current_app.config.get('SMTP_USERNAME')
            password = current_app.config.get('SMTP_PASSWORD')
            if username:
                server.login(username, password)
            server.send_message(msg)
        return True
    except Exception:
        current_app.logger.exception('Email delivery failed. recipient=%s subject=%s', recipient, subject)
        return False


def calculate_job_match(profile, job):
    """Return a transparent 0-100 job match score and short reasons for a candidate."""
    import re
    from difflib import SequenceMatcher

    def tokens(value):
        return {x for x in re.findall(r"[a-z0-9+#.]+", (value or '').lower()) if len(x) > 1}

    profile_terms = tokens(profile.skills_text)
    profile_terms.update(tokens(profile.preferred_role))
    for item in getattr(profile, 'skill_profiles', []) or []:
        if getattr(item, 'skill', None):
            profile_terms.update(tokens(item.skill.name))

    job_title = tokens(job.title)
    job_text = tokens(' '.join([job.title or '', job.description or '', job.requirements or '']))
    job_skills = set()
    for skill in getattr(job, 'skills', []) or []:
        job_skills.update(tokens(skill.name))

    reasons=[]
    score=0.0
    # Role/title relevance — the most important signal.
    preferred=tokens(profile.preferred_role)
    title_overlap=len(preferred & job_title) / max(1,len(preferred)) if preferred else 0
    fuzzy_title=SequenceMatcher(None, ' '.join(sorted(preferred)), ' '.join(sorted(job_title))).ratio() if preferred and job_title else 0
    role_score=max(title_overlap, fuzzy_title)
    score += 35 * role_score
    if role_score >= .45: reasons.append('Role match')

    # Skills — explicit candidate skills are compared with explicit job skills first.
    skill_score=(len(profile_terms & job_skills)/max(1,len(job_skills))) if job_skills else (len(profile_terms & job_text)/max(1,len(profile_terms)))
    score += 35 * min(1,skill_score)
    if skill_score >= .35: reasons.append('Skills match')

    # Location/work mode.
    loc=(profile.location or '').strip().lower()
    jobloc=(job.location or '').strip().lower()
    if loc and jobloc and (loc in jobloc or jobloc in loc):
        score += 12; reasons.append('Location match')
    elif str(job.work_mode or '').lower() == 'remote':
        score += 10; reasons.append('Remote friendly')

    # Experience.
    exp=sum(float(getattr(e,'years',0) or 0) for e in (getattr(profile,'experience',[]) or []))
    emin=float(job.experience_min or 0)
    emax=job.experience_max
    if exp >= emin and (emax is None or exp <= float(emax)+1):
        score += 10; reasons.append('Experience fit')
    elif exp + 1 >= emin:
        score += 6

    # Salary preference.
    expected=getattr(profile,'expected_salary',None)
    if expected and (job.salary_max is None or expected <= job.salary_max) and (job.salary_min is None or expected >= job.salary_min*.75):
        score += 8; reasons.append('Salary fit')

    # Fresh active listings get a small boost without overpowering relevance.
    score += 2
    return max(0,min(100,round(score))), reasons[:4]


def notify_matching_job_alerts(job):
    """Create one in-app alert notification per matching candidate.

    Alerts are intentionally lightweight: they match keyword and/or location
    against the published job. Email delivery is not required, so this also
    works on deployments without SMTP configuration.
    """
    import re
    from ..models import JobAlert, Notification

    if not getattr(job, 'is_active_public', False):
        return 0

    alerts = JobAlert.query.filter_by(is_active=True).all()
    searchable = ' '.join([
        job.title or '',
        job.description or '',
        job.requirements or '',
        job.responsibilities or '',
        job.education or '',
        job.location or '',
        job.work_mode or '',
        job.job_type or '',
        job.company.name if job.company else '',
        ' '.join(skill.name for skill in (job.skills or [])),
    ]).casefold()
    location = (job.location or '').casefold()
    notified_users = set()

    for alert in alerts:
        if alert.user_id in notified_users:
            continue
        keyword = (alert.keyword or '').strip().casefold()
        alert_location = (alert.location or '').strip().casefold()

        keyword_match = True
        if keyword:
            tokens = [x for x in re.findall(r'[a-z0-9+#.]+', keyword) if len(x) > 1]
            keyword_match = bool(tokens) and all(token in searchable for token in tokens)

        location_match = True
        if alert_location:
            location_match = alert_location in location or alert_location in searchable

        if keyword_match and location_match:
            db.session.add(Notification(
                user_id=alert.user_id,
                title='New job matches your alert',
                message=f'{job.title} at {job.company.name} matches your saved job alert.',
                link=url_for('jobs.detail', job_id=job.id),
            ))
            notified_users.add(alert.user_id)

    return len(notified_users)
