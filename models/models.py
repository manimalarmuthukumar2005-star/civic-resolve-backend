from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='citizen')  # citizen, department, admin
    department = db.Column(db.String(100), nullable=True)  # for dept users
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaints = db.relationship('Complaint', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email,
            'phone': self.phone, 'role': self.role,
            'department': self.department,
            'created_at': self.created_at.isoformat()
        }


class Complaint(db.Model):
    __tablename__ = 'complaints'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.String(20), default='Low')
    status = db.Column(db.String(30), default='Pending')
    department_assigned = db.Column(db.String(100), nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_address = db.Column(db.String(300), nullable=True)
    ml_confidence = db.Column(db.Float, nullable=True)
    reopened_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    feedbacks = db.relationship('Feedback', backref='complaint', lazy=True)
    history = db.relationship('ComplaintHistory', backref='complaint', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'title': self.title, 'description': self.description,
            'category': self.category, 'priority': self.priority,
            'status': self.status, 'department_assigned': self.department_assigned,
            'image_path': self.image_path, 'latitude': self.latitude,
            'longitude': self.longitude, 'location_address': self.location_address,
            'ml_confidence': self.ml_confidence, 'reopened_count': self.reopened_count,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'user_name': self.user.name if self.user else None,
            'user_email': self.user.email if self.user else None,
        }


class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text, nullable=True)
    sentiment = db.Column(db.String(20), nullable=True)  # positive, negative, neutral
    sentiment_score = db.Column(db.Float, nullable=True)
    triggered_reopen = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'complaint_id': self.complaint_id,
            'user_id': self.user_id, 'rating': self.rating,
            'comment': self.comment, 'sentiment': self.sentiment,
            'sentiment_score': self.sentiment_score,
            'triggered_reopen': self.triggered_reopen,
            'created_at': self.created_at.isoformat()
        }


class ComplaintHistory(db.Model):
    __tablename__ = 'complaint_history'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False)
    changed_by = db.Column(db.String(100), nullable=False)
    change_type = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.String(200), nullable=True)
    new_value = db.Column(db.String(200), nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'complaint_id': self.complaint_id,
            'changed_by': self.changed_by, 'change_type': self.change_type,
            'old_value': self.old_value, 'new_value': self.new_value,
            'note': self.note, 'created_at': self.created_at.isoformat()
        }
