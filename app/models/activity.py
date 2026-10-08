from datetime import datetime
from ..extensions import db

class ActivityEvent(db.Model):
    __tablename__ = 'activity_events'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    role = db.Column(db.String(30), nullable=False, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(40), default='system', nullable=False)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    summary = db.Column(db.String(500), nullable=False)
    details = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user = db.relationship('User', foreign_keys=[user_id])
    actor = db.relationship('User', foreign_keys=[actor_id])


def record_activity(user_id, role, event_type, summary, *, actor_id=None, entity_type='system', entity_id=None, details=''):
    if not user_id:
        return None
    item = ActivityEvent(user_id=user_id, actor_id=actor_id, role=role, event_type=event_type,
                         entity_type=entity_type, entity_id=entity_id,
                         summary=summary[:500], details=(details or '')[:3000])
    db.session.add(item)
    return item
