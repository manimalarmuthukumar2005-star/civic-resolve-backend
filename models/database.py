from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # user, admin, department
    department = db.Column(db.String(50))  # for dept users
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    complaints = db.relationship('Complaint', backref='user', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email,
                'phone': self.phone, 'role': self.role, 'department': self.department}

class Complaint(db.Model):
    __tablename__ = 'complaints'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    address = db.Column(db.String(300))
    category = db.Column(db.String(50))
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(20), default='Pending')
    department = db.Column(db.String(50))
    reopen_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    feedbacks = db.relationship('Feedback', backref='complaint', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'description': self.description, 'image_path': self.image_path,
            'latitude': self.latitude, 'longitude': self.longitude,
            'address': self.address, 'category': self.category,
            'priority': self.priority, 'status': self.status,
            'department': self.department, 'reopen_count': self.reopen_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'user_name': self.user.name if self.user else None,
            'user_email': self.user.email if self.user else None,
        }

class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    sentiment = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'complaint_id': self.complaint_id,
            'rating': self.rating, 'comment': self.comment,
            'sentiment': self.sentiment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

def init_db():
    db.create_all()
    # Create default admin
    from bcrypt import hashpw, gensalt
    admin = User.query.filter_by(email='admin@civic.gov').first()
    if not admin:
        pw = hashpw(b'Admin@1234', gensalt()).decode()
        admin = User(name='Admin', email='admin@civic.gov', phone='0000000000',
                     password_hash=pw, role='admin')
        db.session.add(admin)
    # Create department users
    depts = [
        ('Roads Officer', 'roads@civic.gov', 'Roads/Public Works'),
        ('Sanitation Officer', 'sanitation@civic.gov', 'Sanitation'),
        ('Drainage Officer', 'drainage@civic.gov', 'Drainage/Water'),
        ('Electrical Officer', 'electrical@civic.gov', 'Electrical'),
    ]
    for name, email, dept in depts:
        if not User.query.filter_by(email=email).first():
            pw = hashpw(b'Dept@1234', gensalt()).decode()
            u = User(name=name, email=email, phone='1111111111',
                     password_hash=pw, role='department', department=dept)
            db.session.add(u)
    db.session.commit()
