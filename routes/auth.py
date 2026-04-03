from flask import Blueprint, request, jsonify
from bcrypt import hashpw, gensalt, checkpw
from models.database import db, User
from utils.auth import generate_token, token_required
import re

auth_bp = Blueprint('auth', __name__)

def validate_email(email):
    return re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    
    if not all([name, email, phone, password]):
        return jsonify({'error': 'All fields are required'}), 400
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409
    
    pw_hash = hashpw(password.encode(), gensalt()).decode()
    user = User(name=name, email=email, phone=phone, password_hash=pw_hash, role='citizen')
    db.session.add(user)
    db.session.commit()
    
    token = generate_token(user.id, user.role)
    return jsonify({'message': 'Registration successful', 'token': token, 'user': user.to_dict()}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    user = User.query.filter_by(email=email).first()
    if not user or not checkpw(password.encode(), user.password_hash.encode()):
        return jsonify({'error': 'Invalid email or password'}), 401
    
    token = generate_token(user.id, user.role, user.department)
    return jsonify({'message': 'Login successful', 'token': token, 'user': user.to_dict()})

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_me(current_user):
    return jsonify(current_user.to_dict())
