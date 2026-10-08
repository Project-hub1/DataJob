from datetime import datetime, timedelta
import re
from flask import Blueprint, current_app, flash, jsonify, render_template, request, url_for, abort
from flask_login import current_user, login_required
from sqlalchemy import or_, and_, func, case
from rapidfuzz import fuzz
from ..extensions import db
from ..models import Job, Company, Skill, SavedJob, Application, JobView, JobReport, SavedSearch, CompanyReview, SearchHistory, SavedCompany, record_activity

jobs_bp=Blueprint('jobs',__name__)

def active_query():
    return Job.query.filter(Job.status=='Active', Job.is_flagged.is_(False), Job.company.has(Company.approval_status=='approved'), or_(Job.deadline.is_(None), Job.deadline >= datetime.utcnow()))

def parse_float(name):
    try: return float(request.args.get(name)) if request.args.get(name) else None
    except ValueError: return None

class FuzzySearchPagination:
    """Small pagination adapter for fuzzy-ranked in-memory search results."""
    def __init__(self, items, page, per_page=20):
        self.total = len(items)
        self.per_page = per_page
        self.pages = max((self.total + per_page - 1) // per_page, 1)
        self.page = min(max(page, 1), self.pages)
        self.first = ((self.page - 1) * per_page + 1) if self.total else 0
        self.last = min(self.page * per_page, self.total)
        self.has_prev = self.page > 1
        self.has_next = self.page < self.pages
        self.prev_num = self.page - 1 if self.has_prev else None
        self.next_num = self.page + 1 if self.has_next else None
        self.items = items[(self.page - 1) * per_page:self.page * per_page]

    def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
        last = 0
        for page in range(1, self.pages + 1):
            if (page <= left_edge or page > self.pages - right_edge or
                    self.page - left_current <= page <= self.page + right_current):
                if last + 1 != page:
                    yield None
                yield page
                last = page


def _base_job_search_query():
    """Apply all structured filters except the free-text keyword."""
    q = active_query()
    location = request.args.get('location', '').strip()

    if location:
        loc = ' '.join(location.split()).strip()
        loc_key = loc.casefold()
        aliases = {
            'up':'Uttar Pradesh', 'uttar pradesh':'Uttar Pradesh',
            'mp':'Madhya Pradesh', 'madhya pradesh':'Madhya Pradesh',
            'wb':'West Bengal', 'west bengal':'West Bengal',
            'hp':'Himachal Pradesh', 'himachal pradesh':'Himachal Pradesh',
            'jk':'Jammu and Kashmir', 'j&k':'Jammu and Kashmir', 'jammu kashmir':'Jammu and Kashmir',
            'tn':'Tamil Nadu', 'tamil nadu':'Tamil Nadu', 'ka':'Karnataka',
            'kl':'Kerala', 'mh':'Maharashtra', 'rj':'Rajasthan', 'gj':'Gujarat',
            'hr':'Haryana', 'pb':'Punjab', 'br':'Bihar', 'jh':'Jharkhand',
            'od':'Odisha', 'or':'Odisha', 'tg':'Telangana', 'ts':'Telangana',
            'ap':'Andhra Pradesh', 'uk':'Uttarakhand', 'uttarakhand':'Uttarakhand',
            'ga':'Goa', 'as':'Assam', 'sikkim':'Sikkim', 'tripura':'Tripura',
            'manipur':'Manipur', 'meghalaya':'Meghalaya', 'mizoram':'Mizoram',
            'nagaland':'Nagaland', 'arunachal':'Arunachal Pradesh',
            'arunachal pradesh':'Arunachal Pradesh', 'chhattisgarh':'Chhattisgarh',
            'delhi':'Delhi', 'ncr':'Delhi', 'chandigarh':'Chandigarh',
            'ladakh':'Ladakh', 'puducherry':'Puducherry', 'pondicherry':'Puducherry',
            'andaman':'Andaman and Nicobar Islands',
            'andaman and nicobar islands':'Andaman and Nicobar Islands',
            'lakshadweep':'Lakshadweep',
            'dadra nagar haveli':'Dadra and Nagar Haveli and Daman and Diu',
            'dadra and nagar haveli and daman and diu':'Dadra and Nagar Haveli and Daman and Diu',
            'india':'India', 'pan india':'India', 'all india':'India'
        }
        canonical = aliases.get(loc_key, loc)
        if canonical.casefold() == 'india':
            q = q.filter(Job.location.ilike('%India%'))
        elif canonical in aliases.values() and canonical.casefold() != 'india':
            q = q.filter(Job.location.ilike(f'%, {canonical}, India%'))
        else:
            q = q.filter(Job.location.ilike(f'%{loc}%'))

    company = request.args.get('company', '').strip()
    if company:
        q = q.filter(Job.company.has(Company.name.ilike(f'%{company}%')))

    exp = parse_float('experience')
    if exp is not None:
        q = q.filter(Job.experience_min <= exp, or_(Job.experience_max.is_(None), Job.experience_max >= exp))
    exp_min = parse_float('experience_min')
    exp_max = parse_float('experience_max')
    if exp_min is not None:
        q = q.filter(or_(Job.experience_max.is_(None), Job.experience_max >= exp_min))
    if exp_max is not None:
        q = q.filter(Job.experience_min <= exp_max)

    min_salary = parse_float('salary_min')
    max_salary = parse_float('salary_max')
    if min_salary is not None:
        q = q.filter(or_(Job.salary_max.is_(None), Job.salary_max >= min_salary * 100000))
    if max_salary is not None:
        q = q.filter(or_(Job.salary_min.is_(None), Job.salary_min <= max_salary * 100000))

    for field in ['job_type', 'work_mode']:
        value = request.args.get(field, '').strip()
        if value:
            q = q.filter(getattr(Job, field) == value)

    education = request.args.get('education', '').strip()
    if education:
        q = q.filter(Job.education.ilike(f'%{education}%'))

    skill_filter = request.args.get('skills', '').strip()
    if skill_filter:
        requested = [x.strip() for x in skill_filter.split(',') if x.strip()]
        for skill_name in requested:
            q = q.filter(Job.skills.any(Skill.name.ilike(skill_name)))

    level = request.args.get('level', '').strip().lower()
    if level == 'fresher':
        q = q.filter(Job.experience_min <= 0)
    elif level == 'internship':
        q = q.filter(Job.job_type == 'Internship')

    posted = request.args.get('date_posted', '')
    if posted in {'1', '7', '30', '90'}:
        q = q.filter(Job.created_at >= datetime.utcnow() - timedelta(days=int(posted)))
    return q


def _keyword_search_query(base_query, keyword):
    """Keep the existing exact search behavior for fast/normal searches."""
    if not keyword:
        return base_query
    tokens = [t for t in keyword.split() if len(t) > 1]
    q = base_query.outerjoin(Job.company).outerjoin(Job.skills)
    for token in tokens or [keyword]:
        like = f'%{token}%'
        q = q.filter(or_(
            Job.title.ilike(like), Job.description.ilike(like),
            Job.requirements.ilike(like), Job.responsibilities.ilike(like),
            Job.location.ilike(like), Company.name.ilike(like), Skill.name.ilike(like)
        ))
    return q.distinct()


def _parse_smart_query(raw):
    """Extract common job-search intent from a natural-language query.

    Examples: ``python developer fresher delhi remote`` and
    ``react developer 5 lpa 2 years`` become structured filters plus a clean
    keyword search. This keeps the normal filter UI and old URLs compatible.
    """
    text = ' '.join((raw or '').split())
    lowered = text.casefold()
    filters = {}
    consumed = set()
    if re.search(r'\b(remote|work from home|wfh)\b', lowered):
        filters['work_mode'] = 'Remote'; consumed.add('workmode')
    elif re.search(r'\bhybrid\b', lowered):
        filters['work_mode'] = 'Hybrid'; consumed.add('hybrid')
    elif re.search(r'\b(on[- ]?site)\b', lowered):
        filters['work_mode'] = 'On-site'; consumed.add('onsite')
    if re.search(r'\bfresher\b|\bentry[- ]level\b', lowered):
        filters['level'] = 'fresher'; consumed.add('level')
    if re.search(r'\bintern(ship)?\b', lowered):
        filters['level'] = 'internship'; consumed.add('internship')
    m = re.search(r'(?:under|below|up to|max(?:imum)?)\s*₹?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh)', lowered)
    if m:
        filters['salary_max'] = m.group(1); text = text[:m.start()] + ' ' + text[m.end():]
    m = re.search(r'(?:above|over|min(?:imum)?|from)\s*₹?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh)', lowered)
    if m:
        filters['salary_min'] = m.group(1); text = text[:m.start()] + ' ' + text[m.end():]
    m = re.search(r'(?:\bfor\s*)?(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:experience)?', lowered)
    if m:
        filters['experience'] = m.group(1); text = text[:m.start()] + ' ' + text[m.end():]
    locations = ['delhi','delhi ncr','mumbai','pune','bengaluru','bangalore','hyderabad','chennai','noida','gurugram','gurgaon','kolkata','ahmedabad','jaipur','remote']
    for loc in sorted(locations, key=len, reverse=True):
        if re.search(r'\b'+re.escape(loc)+r'\b', lowered) and loc != 'remote':
            filters['location'] = loc
            text = re.sub(r'\b'+re.escape(loc)+r'\b', ' ', text, flags=re.I)
            break
    # Remove standalone intent words only; preserve actual role/skill keywords.
    text = re.sub(r'\b(remote|work from home|wfh|hybrid|on[- ]?site|fresher|entry[- ]level|internship|intern)\b', ' ', text, flags=re.I)
    return filters, ' '.join(text.split())

def _job_search_query():
    raw_keyword = request.args.get('q', '').strip()
    smart, keyword = _parse_smart_query(raw_keyword)
    base = _base_job_search_query()
    # Smart-query filters are applied only when the user did not explicitly
    # supply the same structured filter in the URL.
    for field in ['work_mode','level','salary_min','salary_max','experience','location']:
        if smart.get(field) and not request.args.get(field):
            if field == 'work_mode':
                base = base.filter(Job.work_mode == smart[field])
            elif field == 'level':
                base = base.filter(Job.experience_min <= 0) if smart[field] == 'fresher' else base.filter(Job.job_type == 'Internship')
            elif field == 'salary_min':
                base = base.filter(or_(Job.salary_max.is_(None), Job.salary_max >= float(smart[field]) * 100000))
            elif field == 'salary_max':
                base = base.filter(or_(Job.salary_min.is_(None), Job.salary_min <= float(smart[field]) * 100000))
            elif field == 'experience':
                exp=float(smart[field]); base=base.filter(Job.experience_min <= exp, or_(Job.experience_max.is_(None), Job.experience_max >= exp))
            elif field == 'location':
                base = base.filter(Job.location.ilike(f'%{smart[field]}%'))
    return _keyword_search_query(base, keyword), keyword, base


def _job_search_text(job):
    skills = ' '.join(sk.name for sk in job.skills)
    return ' '.join([
        job.title or '', job.company.name if job.company else '', skills,
        job.description or '', job.requirements or '', job.responsibilities or '',
        job.education or ''
    ])


def _fuzzy_rank_jobs(base_query, keyword):
    """Rank only when exact search returned nothing.

    RapidFuzz makes small spelling mistakes such as `pyhton`, `javscript`,
    `develper`, etc. resolve to the closest real job terms. A conservative
    threshold prevents unrelated jobs from being shown.
    """
    tokens = [t.casefold() for t in keyword.split() if len(t) > 1]
    candidates = base_query.distinct().limit(current_app.config.get('MAX_SEARCH_RESULTS', 500)).all()
    ranked = []
    for job in candidates:
        title = (job.title or '').casefold()
        company = (job.company.name if job.company else '').casefold()
        skills = ' '.join(sk.name for sk in job.skills).casefold()
        description = ' '.join([
            job.description or '', job.requirements or '', job.responsibilities or ''
        ]).casefold()
        fields = [title, company, skills, description, (job.education or '').casefold()]

        token_scores = []
        for token in tokens or [keyword.casefold()]:
            token_scores.append(max(
                fuzz.partial_ratio(token, field)
                for field in fields if field
            ))
        token_avg = sum(token_scores) / len(token_scores) if token_scores else 0
        whole_score = max(
            fuzz.token_set_ratio(keyword.casefold(), title),
            fuzz.token_set_ratio(keyword.casefold(), company),
            fuzz.token_set_ratio(keyword.casefold(), skills),
            fuzz.partial_ratio(keyword.casefold(), description)
        )
        score = max(token_avg, whole_score)
        # Require a genuinely close match. This avoids turning arbitrary input
        # into an unrelated recommendation.
        if score >= 60 and (not token_scores or min(token_scores) >= 50):
            ranked.append((score, job))

    ranked.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    return [job for _, job in ranked]


def job_search_query():
    q, keyword, _ = _job_search_query()
    return q, keyword



def sort_jobs(q, sort, keyword):
    if sort == 'oldest':
        return q.order_by(Job.created_at.asc())
    if sort == 'salary_high':
        return q.order_by(Job.salary_max.desc().nullslast(), Job.created_at.desc())
    if sort == 'salary_low':
        return q.order_by(Job.salary_min.asc().nullslast(), Job.created_at.desc())
    if sort == 'relevance' and keyword:
        like = f'%{keyword}%'
        score = (
            case((Job.title.ilike(like), 5), else_=0) +
            case((Job.description.ilike(like), 2), else_=0) +
            case((Job.requirements.ilike(like), 1), else_=0)
        )
        return q.order_by(score.desc(), Job.created_at.desc())
    return q.order_by(Job.created_at.desc())


@jobs_bp.get('/jobs')
def listing():
    exact_query, keyword, base_query = _job_search_query()
    sort = request.args.get('sort', 'relevance')
    page = max(request.args.get('page', 1, type=int), 1)
    fuzzy_used = False
    spelling_failed = False

    if keyword and not exact_query.first():
        fuzzy_jobs = _fuzzy_rank_jobs(base_query, keyword)
        fuzzy_used = bool(fuzzy_jobs)
        spelling_failed = not fuzzy_used
        pagination = FuzzySearchPagination(fuzzy_jobs, page, per_page=20)
        jobs = pagination.items
    else:
        q = sort_jobs(exact_query, sort, keyword)
        pagination = q.paginate(page=page, per_page=20, error_out=False)
        jobs = pagination.items

    if current_user.is_authenticated and current_user.role == 'candidate' and request.args and any(
        v for k, v in request.args.items() if k != 'page'
    ):
        query_string = request.query_string.decode('utf-8')[:1000]
        last = SearchHistory.query.filter_by(user_id=current_user.id).order_by(SearchHistory.created_at.desc()).first()
        if not last or last.query_string != query_string:
            db.session.add(SearchHistory(user_id=current_user.id, query_string=query_string))
            db.session.commit()

    saved_ids = set()
    applied_ids = set()
    if current_user.is_authenticated and current_user.role == 'candidate':
        saved_ids = {x.job_id for x in SavedJob.query.filter_by(user_id=current_user.id).all()}
        applied_ids = {x.job_id for x in Application.query.filter_by(candidate_id=current_user.id).all()}

    return render_template(
        'jobs/list.html', jobs=jobs, pagination=pagination, saved_ids=saved_ids, applied_ids=applied_ids,
        query=request.args, fuzzy_used=fuzzy_used, spelling_failed=spelling_failed,
        fuzzy_keyword=keyword
    )

@jobs_bp.get('/jobs/<int:job_id>')
def detail(job_id):
    job=Job.query.get_or_404(job_id)
    if not job.is_active_public: abort(404)
    # Count a genuine page view. Recruiters use this for lightweight analytics.
    viewer_id=current_user.id if current_user.is_authenticated else None
    db.session.add(JobView(job_id=job.id, viewer_id=viewer_id))
    if viewer_id and current_user.role == 'candidate':
        record_activity(current_user.id, 'candidate', 'job_viewed', f'Viewed {job.title}', entity_type='job', entity_id=job.id, details=f'{job.company.name} · {job.location}')
    db.session.commit()
    similar=active_query().filter(Job.id!=job.id).filter(or_(Job.location==job.location,Job.industry==job.industry)).order_by(Job.created_at.desc()).limit(6).all()
    saved=False; already_applied=False
    if current_user.is_authenticated and current_user.role=='candidate':
        saved=SavedJob.query.filter_by(user_id=current_user.id,job_id=job.id).first() is not None
        from ..models import Application
        already_applied=Application.query.filter_by(candidate_id=current_user.id,job_id=job.id).first() is not None
    reviews=CompanyReview.query.filter_by(company_id=job.company_id).order_by(CompanyReview.created_at.desc()).limit(8).all()
    avg=(sum(r.rating for r in reviews)/len(reviews)) if reviews else 0
    return render_template('jobs/detail.html',job=job,similar=similar,saved=saved,already_applied=already_applied,reviews=reviews,review_avg=avg)

@jobs_bp.post('/jobs/<int:job_id>/save')
@login_required
def save_job(job_id):
    if current_user.role!='candidate': return jsonify(ok=False,message='Only candidates can save jobs.'),403
    job=Job.query.get_or_404(job_id)
    if not job.is_active_public: return jsonify(ok=False,message='This job is no longer active.'),404
    saved=SavedJob.query.filter_by(user_id=current_user.id,job_id=job.id).first()
    if saved:
        db.session.delete(saved); state=False
        record_activity(current_user.id, 'candidate', 'job_unsaved', f'Removed {job.title} from saved jobs', entity_type='job', entity_id=job.id)
    else:
        db.session.add(SavedJob(user_id=current_user.id,job_id=job.id)); state=True
        record_activity(current_user.id, 'candidate', 'job_saved', f'Saved {job.title}', entity_type='job', entity_id=job.id)
    db.session.commit(); return jsonify(ok=True,saved=state)

@jobs_bp.get('/companies')
def companies():
    q=request.args.get('q','').strip(); query=Company.query.filter_by(approval_status='approved')
    if q: query=query.filter(or_(Company.name.ilike(f'%{q}%'),Company.industry.ilike(f'%{q}%'),Company.location.ilike(f'%{q}%')))
    pagination=query.order_by(Company.name.asc()).paginate(page=max(request.args.get('page',1,type=int),1),per_page=12,error_out=False)
    open_job_counts={c.id: Job.query.filter(Job.company_id==c.id, Job.status=='Active', Job.is_flagged.is_(False), or_(Job.deadline.is_(None), Job.deadline >= datetime.utcnow())).count() for c in pagination.items}
    return render_template('companies/list.html',companies=pagination.items,pagination=pagination,query=request.args,open_job_counts=open_job_counts)

@jobs_bp.get('/companies/<int:company_id>')
def company_detail(company_id):
    company=Company.query.get_or_404(company_id)
    if company.approval_status!='approved': abort(404)
    jobs=active_query().filter(Job.company_id==company.id).order_by(Job.created_at.desc()).all()
    saved_company=False
    review_eligible=False
    my_review=None
    if current_user.is_authenticated and current_user.role=='candidate':
        saved_company=SavedCompany.query.filter_by(user_id=current_user.id,company_id=company.id).first() is not None
        review_eligible=Application.query.join(Job).filter(Application.candidate_id==current_user.id,Job.company_id==company.id).first() is not None
        my_review=CompanyReview.query.filter_by(company_id=company.id,user_id=current_user.id).first()
    return render_template('companies/detail.html',company=company,jobs=jobs,saved_company=saved_company,review_eligible=review_eligible,my_review=my_review)


@jobs_bp.post('/jobs/<int:job_id>/report')
@login_required
def report_job(job_id):
    if current_user.role != 'candidate':
        return jsonify(ok=False, message='Only candidates can report jobs.'), 403
    job = Job.query.get_or_404(job_id)
    reason = request.form.get('reason', 'Other').strip()
    if reason not in {'Fake job', 'Spam', 'Incorrect information', 'Scam', 'Other'}:
        reason = 'Other'
    db.session.add(JobReport(
        job_id=job.id,
        reporter_id=current_user.id,
        reason=reason,
        details=request.form.get('details', '').strip()[:2000]
    ))
    db.session.commit()
    message = 'Thanks. The job has been reported to the CareerHub moderation team.'
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(ok=True, message=message)
    flash(message, 'success')
    return redirect(url_for('jobs.detail', job_id=job.id))

@jobs_bp.post('/jobs/<int:job_id>/review')
@login_required
def review_company(job_id):
    if current_user.role != 'candidate': abort(403)
    job=Job.query.get_or_404(job_id)
    applied=Application.query.filter_by(job_id=job.id,candidate_id=current_user.id).first()
    if not applied: return jsonify(ok=False,message='Apply to the job before reviewing the company.'), 400
    rating=request.form.get('rating',type=int) or 0
    title=request.form.get('title','').strip()[:160]
    body=request.form.get('body','').strip()[:3000]
    if rating not in range(1,6): return jsonify(ok=False,message='Rating must be between 1 and 5.'),400
    if len(body) < 20: return jsonify(ok=False,message='Please share at least 20 characters.'),400
    existing=CompanyReview.query.filter_by(company_id=job.company_id,user_id=current_user.id).first()
    if existing:
        existing.rating=rating; existing.title=title; existing.body=body
    else:
        db.session.add(CompanyReview(company_id=job.company_id,user_id=current_user.id,rating=rating,title=title,body=body))
    db.session.commit(); return jsonify(ok=True,message='Company review saved.')

@jobs_bp.post('/saved-searches')
@login_required
def save_search():
    if current_user.role!='candidate': abort(403)
    import json
    name=request.form.get('name','My job search').strip()[:120]
    filters={k:v for k,v in request.form.items() if k not in {'name','csrf_token'}}
    db.session.add(SavedSearch(user_id=current_user.id,name=name,query=request.form.get('q','').strip(),location=request.form.get('location','').strip(),filters_json=json.dumps(filters)))
    db.session.commit(); return jsonify(ok=True,message='Search saved.')
