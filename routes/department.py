from flask import Blueprint, request, jsonify
from models.database import db, Complaint
from utils.auth import role_required
from datetime import datetime

department_bp = Blueprint('department', __name__)

@department_bp.route('/complaints', methods=['GET'])
@role_required('department', 'admin')
def dept_complaints(current_user):
    dept = current_user.department if current_user.role == 'department' else request.args.get('department')
    q = Complaint.query
    if dept:
        q = q.filter_by(department=dept)
    priority_order = {'Emergency': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    complaints = q.order_by(Complaint.created_at.desc()).all()
    complaints.sort(key=lambda c: priority_order.get(c.priority, 99))
    return jsonify([c.to_dict() for c in complaints])

@department_bp.route('/complaints/<int:cid>/status', methods=['PUT'])
@role_required('department', 'admin')
def update_status(current_user, cid):
    c = Complaint.query.get_or_404(cid)
    if current_user.role == 'department' and c.department != current_user.department:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    new_status = data.get('status')
    valid = ['Pending', 'In Progress', 'Completed']
    if new_status not in valid:
        return jsonify({'error': f'Invalid status. Must be one of {valid}'}), 400
    
    c.status = new_status
    c.updated_at = datetime.utcnow()
    if new_status == 'Completed':
        c.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Status updated', 'complaint': c.to_dict()})

@department_bp.route('/stats', methods=['GET'])
@role_required('department', 'admin')
def dept_stats(current_user):
    dept = current_user.department if current_user.role == 'department' else None
    q = Complaint.query
    if dept:
        q = q.filter_by(department=dept)
    complaints = q.all()
    total = len(complaints)
    statuses = {}
    priorities = {}
    for c in complaints:
        statuses[c.status] = statuses.get(c.status, 0) + 1
        priorities[c.priority] = priorities.get(c.priority, 0) + 1
    resolved = [c for c in complaints if c.resolved_at and c.created_at]
    avg_time = None
    if resolved:
        times = [(c.resolved_at - c.created_at).total_seconds() / 3600 for c in resolved]
        avg_time = round(sum(times) / len(times), 1)
    return jsonify({'total': total, 'statuses': statuses, 'priorities': priorities, 'avg_resolution_hours': avg_time})
