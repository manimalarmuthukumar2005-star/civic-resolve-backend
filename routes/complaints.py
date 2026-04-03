from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from models.database import db, Complaint, Feedback
from utils.auth import token_required
from ml.categorizer import classifier
from ml.sentiment import analyze_sentiment, should_reopen
from utils.email_service import send_complaint_notification, send_status_update_email
from datetime import datetime
import os, uuid

complaints_bp = Blueprint('complaints', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@complaints_bp.route('/submit', methods=['POST'])
@token_required
def submit_complaint(current_user):
    description = request.form.get('description', '').strip()
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    address = request.form.get('address', '')
    
    if not description:
        return jsonify({'error': 'Description is required'}), 400
    
    image_path = None
    image_filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            image_filename = f"{uuid.uuid4().hex}.{ext}"
            image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
            file.save(image_path)
            image_filename = file.filename
    
    valid, msg = classifier.validate_image_description(description, image_filename or 'dummy.jpg')
    if not valid:
        return jsonify({'error': msg}), 400
    
    category, confidence = classifier.predict_category(description)
    priority = classifier.predict_priority(description)
    
    complaint = Complaint(
        user_id=current_user.id,
        description=description,
        image_path=f"/api/complaints/image/{os.path.basename(image_path)}" if image_path else None,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
        address=address,
        category=category,
        priority=priority,
        status='Pending',
        department=category,
    )
    db.session.add(complaint)
    db.session.commit()
    
    try:
        from app import mail
        send_complaint_notification(complaint, mail)
    except Exception as e:
        print(f"Email error: {e}")
    
    return jsonify({
        'message': 'Complaint submitted successfully',
        'complaint': complaint.to_dict(),
        'category': category,
        'priority': priority,
        'confidence': round(confidence * 100, 1),
    }), 201

@complaints_bp.route('/my', methods=['GET'])
@token_required
def my_complaints(current_user):
    complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return jsonify([c.to_dict() for c in complaints])

@complaints_bp.route('/<int:cid>', methods=['GET'])
@token_required
def get_complaint(current_user, cid):
    c = Complaint.query.get_or_404(cid)
    if current_user.role == 'user' and c.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    data = c.to_dict()
    data['feedbacks'] = [f.to_dict() for f in c.feedbacks]
    return jsonify(data)

@complaints_bp.route('/<int:cid>/feedback', methods=['POST'])
@token_required
def submit_feedback(current_user, cid):
    c = Complaint.query.get_or_404(cid)
    if c.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if c.status != 'Completed':
        return jsonify({'error': 'Can only give feedback on completed complaints'}), 400
    
    data = request.json
    rating = int(data.get('rating', 0))
    comment = data.get('comment', '')
    
    sentiment = analyze_sentiment(comment, rating)
    fb = Feedback(complaint_id=cid, user_id=current_user.id, rating=rating,
                  comment=comment, sentiment=sentiment)
    db.session.add(fb)
    
    if should_reopen(rating, comment):
        c.status = 'In Progress'
        c.reopen_count = (c.reopen_count or 0) + 1
        c.resolved_at = None
        msg = 'Feedback submitted. Complaint reopened due to unsatisfactory resolution.'
    else:
        msg = 'Thank you for your feedback!'
    
    db.session.commit()
    return jsonify({'message': msg, 'sentiment': sentiment, 'reopened': c.status == 'In Progress'})

@complaints_bp.route('/image/<filename>', methods=['GET'])
def serve_image(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
