import pytest
from app import create_app
from app.extensions import db
from app.models import User, RecruiterProfile, Company, Job

class TestConfig:
    TESTING = True
    SECRET_KEY = 'test'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    DEV_SHOW_RESET_LINK = True
    REQUIRE_EMAIL_VERIFICATION = False
    AUTO_APPROVE_RECRUITER_COMPANIES = True

@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def recruiter_data(app):
    with app.app_context():
        recruiter = User(email='recruiter@test.com', role='recruiter', email_verified=True)
        recruiter.set_password('Password@123')
        other = User(email='other-recruiter@test.com', role='recruiter', email_verified=True)
        other.set_password('Password@123')
        db.session.add_all([recruiter, other])
        db.session.flush()
        company = Company(name='Acme Technologies', slug='acme-technologies', industry='IT', location='Delhi', employee_count=25, description='Original company')
        other_company = Company(name='Other Co', slug='other-co', industry='IT', location='Noida', employee_count=10)
        db.session.add_all([company, other_company])
        db.session.flush()
        db.session.add_all([
            RecruiterProfile(user_id=recruiter.id, full_name='Original Recruiter', designation='Recruiter', company_id=company.id),
            RecruiterProfile(user_id=other.id, full_name='Other Recruiter', designation='Recruiter', company_id=other_company.id),
        ])
        job = Job(company_id=company.id, recruiter_id=recruiter.id, title='Python Developer', slug='python-developer-edit-test', description='Original description', location='Delhi', work_mode='Remote', job_type='Full-time', status='Active')
        other_job = Job(company_id=other_company.id, recruiter_id=other.id, title='Other Job', slug='other-job-edit-test', description='Other description', location='Noida', work_mode='On-site', job_type='Full-time', status='Active')
        db.session.add_all([job, other_job])
        db.session.commit()
        return recruiter, other, company, other_company, job, other_job

def login(client, email='recruiter@test.com'):
    response = client.post('/login', data={'email': email, 'password': 'Password@123'})
    assert response.status_code == 302


def test_recruiter_can_edit_company_and_recruiter_details(client, app, recruiter_data):
    _, _, company, _, _, _ = recruiter_data
    login(client)
    response = client.post('/recruiter/company', data={
        'name': 'Acme Technologies India',
        'industry': 'Software',
        'location': 'Gurugram',
        'website': 'https://example.com',
        'employee_count': '120',
        'recruiter_name': 'Aisha Khan',
        'designation': 'Talent Acquisition Manager',
        'description': 'Updated company description',
    })
    assert response.status_code == 302
    with app.app_context():
        c = db.session.get(Company, company.id)
        assert c.name == 'Acme Technologies India'
        assert c.location == 'Gurugram'
        assert c.employee_count == 120
        assert c.description == 'Updated company description'
        profile = db.session.query(RecruiterProfile).filter_by(user_id=recruiter_data[0].id).one()
        assert profile.full_name == 'Aisha Khan'
        assert profile.designation == 'Talent Acquisition Manager'


def test_recruiter_can_edit_own_job(client, app, recruiter_data):
    _, _, _, _, job, _ = recruiter_data
    login(client)
    response = client.post(f'/recruiter/jobs/{job.id}/edit', data={
        'title': 'Senior Python Developer',
        'location': 'Bengaluru',
        'description': 'Updated role description',
        'responsibilities': 'Build APIs',
        'requirements': 'Python and Flask',
        'education': 'B.Tech',
        'benefits': 'Insurance',
        'work_mode': 'Hybrid',
        'job_type': 'Full-time',
        'experience_min': '2',
        'experience_max': '5',
        'salary_min': '8',
        'salary_max': '14',
        'deadline_days': '60',
        'skills': 'Python, Flask, SQL',
        'status': 'Active',
    })
    assert response.status_code == 302
    with app.app_context():
        j = db.session.get(Job, job.id)
        assert j.title == 'Senior Python Developer'
        assert j.location == 'Bengaluru'
        assert j.description == 'Updated role description'
        assert j.experience_min == 2
        assert j.experience_max == 5
        assert j.salary_min == 800000
        assert j.salary_max == 1400000
        assert j.work_mode == 'Hybrid'
        assert {skill.name for skill in j.skills} == {'Python', 'Flask', 'SQL'}


def test_recruiter_cannot_edit_another_recruiters_job(client, recruiter_data):
    _, _, _, _, _, other_job = recruiter_data
    login(client)
    response = client.get(f'/recruiter/jobs/{other_job.id}/edit')
    assert response.status_code == 404
