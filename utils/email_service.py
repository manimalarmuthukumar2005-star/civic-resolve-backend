from flask import current_app
from flask_mail import Message

def send_complaint_notification(complaint, mail):
    try:
        dept_email = current_app.config['DEPARTMENT_EMAILS'].get(complaint.department, '')
        admin_email = current_app.config['ADMIN_EMAIL']
        recipients = [r for r in [dept_email, admin_email] if r and '@' in r and 'example' not in r and 'civic.gov' not in r]
        if not recipients:
            print(f"[EMAIL SIMULATED] Complaint #{complaint.id} notification to {dept_email}, {admin_email}")
            return
        subject = f"New Complaint #{complaint.id}: {complaint.category} - {complaint.priority} Priority"
        body = f"""
New civic complaint submitted:

Complaint ID: #{complaint.id}
Category: {complaint.category}
Priority: {complaint.priority}
Department: {complaint.department}
Status: {complaint.status}

Description:
{complaint.description}

Location:
Latitude: {complaint.latitude}
Longitude: {complaint.longitude}
Address: {complaint.address or 'Not provided'}

Image: {complaint.image_path or 'No image'}

Submitted by: {complaint.user.name} ({complaint.user.email})
Time: {complaint.created_at}
        """
        msg = Message(subject=subject, recipients=recipients, body=body)
        mail.send(msg)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

def send_status_update_email(complaint, mail):
    try:
        user_email = complaint.user.email
        if not user_email or 'example' not in user_email:
            subject = f"Update on Complaint #{complaint.id}"
            body = f"Your complaint #{complaint.id} status has been updated to: {complaint.status}"
            print(f"[EMAIL SIMULATED] Status update to {user_email}: {complaint.status}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
