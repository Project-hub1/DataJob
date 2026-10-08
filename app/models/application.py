from datetime import datetime
from ..extensions import db
class Application(db.Model):
    __tablename__ = 'applications'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(40), default='Applied', nullable=False, index=True)
    cover_letter = db.Column(db.Text, default='')
    additional_info = db.Column(db.Text, default='')
    resume_filename = db.Column(db.String(255))
    resume_original_name = db.Column(db.String(255))
    resume_data = db.Column(db.LargeBinary)
    resume_mimetype = db.Column(db.String(120))
    applicant_name = db.Column(db.String(120))
    applicant_education = db.Column(db.Text, default='')
    applicant_age = db.Column(db.Integer)
    applicant_skills = db.Column(db.Text, default='')
    applicant_experience = db.Column(db.String(120), default='')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recruiter_notes = db.Column(db.Text, default='')
    recruiter_rating = db.Column(db.Integer, nullable=True)
    recruiter_tags = db.Column(db.String(500), default='')
    job = db.relationship('Job', back_populates='applications')
    candidate = db.relationship('User', foreign_keys=[candidate_id])
    __table_args__ = (db.UniqueConstraint('job_id','candidate_id', name='uq_application_job_candidate'),)
class Interview(db.Model):
    __tablename__ = 'interviews'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    scheduled_at = db.Column(db.DateTime)
    mode = db.Column(db.String(40))
    meeting_link = db.Column(db.String(500))
    notes = db.Column(db.Text)
    application = db.relationship('Application')


class ApplicationStatusHistory(db.Model):
    __tablename__ = 'application_status_history'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False)
    note = db.Column(db.String(500), default='')
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    application = db.relationship('Application', backref=db.backref('status_history', cascade='all, delete-orphan', order_by='ApplicationStatusHistory.changed_at.asc()'))
