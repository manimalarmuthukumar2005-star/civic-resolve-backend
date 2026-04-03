import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'civic-app-secret-2024-dev')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///civic_issues.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_EXPIRY = timedelta(hours=24)
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Flask-Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'civic@example.com')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@civic.gov')
    
    DEPARTMENT_EMAILS = {
        'Roads/Public Works': os.environ.get('ROADS_EMAIL', 'roads@civic.gov'),
        'Sanitation': os.environ.get('SANITATION_EMAIL', 'sanitation@civic.gov'),
        'Drainage/Water': os.environ.get('DRAINAGE_EMAIL', 'drainage@civic.gov'),
        'Electrical': os.environ.get('ELECTRICAL_EMAIL', 'electrical@civic.gov'),
    }
