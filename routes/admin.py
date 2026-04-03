from flask import Blueprint, request, jsonify
from models.database import db, Complaint, User, Feedback
from utils.auth import role_required
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/complaints', methods=['GET'])
@role_required('admin')
def all_complaints(current_user):
    status = request.args.get('status')
    category = request.args.get('category')
    priority = request.args.get('priority')
    q = Complaint.query
    if status: q = q.filter_by(status=status)
    if category: q = q.filter_by(category=category)
    if priority: q = q.filter_by(priority=priority)
    complaints = q.order_by(Complaint.created_at.desc()).all()
    data = []
    for c in complaints:
        cd = c.to_dict()
        cd['feedbacks'] = [f.to_dict() for f in c.feedbacks]
        data.append(cd)
    return jsonify(data)

@admin_bp.route('/stats', methods=['GET'])
@role_required('admin')
def admin_stats(current_user):
    complaints = Complaint.query.all()
    total = len(complaints)
    by_cat = {}
    by_priority = {}
    by_status = {}
    by_dept = {}
    for c in complaints:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
        by_priority[c.priority] = by_priority.get(c.priority, 0) + 1
        by_status[c.status] = by_status.get(c.status, 0) + 1
        by_dept[c.department] = by_dept.get(c.department, 0) + 1
    
    completed = [c for c in complaints if c.status == 'Completed']
    resolution_rate = round(len(completed) / total * 100, 1) if total > 0 else 0
    
    resolved_time = [c for c in complaints if c.resolved_at and c.created_at]
    avg_time = None
    if resolved_time:
        times = [(c.resolved_at - c.created_at).total_seconds() / 3600 for c in resolved_time]
        avg_time = round(sum(times) / len(times), 1)
    
    feedbacks = Feedback.query.all()
    avg_rating = round(sum(f.rating for f in feedbacks if f.rating) / len(feedbacks), 1) if feedbacks else None
    
    return jsonify({
        'total': total,
        'by_category': by_cat,
        'by_priority': by_priority,
        'by_status': by_status,
        'by_department': by_dept,
        'resolution_rate': resolution_rate,
        'avg_resolution_hours': avg_time,
        'total_feedbacks': len(feedbacks),
        'avg_rating': avg_rating,
    })

@admin_bp.route('/users', methods=['GET'])
@role_required('admin')
def all_users(current_user):
    users = User.query.filter_by(role='user').all()
    return jsonify([u.to_dict() for u in users])
