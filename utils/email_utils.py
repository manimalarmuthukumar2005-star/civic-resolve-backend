from flask_mail import Message
from flask import current_app


def send_complaint_notification(mail, complaint_data: dict, dept_email: str, admin_email: str):
    """Send email to department and admin when a new complaint is submitted."""
    subject = f"[NEW COMPLAINT #{complaint_data['id']}] {complaint_data['category']} - Priority: {complaint_data['priority']}"
    
    body = f"""
=== CIVIC ISSUE REPORTING SYSTEM ===
New Complaint Submitted

Complaint ID   : #{complaint_data['id']}
Title          : {complaint_data['title']}
Category       : {complaint_data['category']}
Priority       : {complaint_data['priority']}
Department     : {complaint_data['department_assigned']}
Status         : {complaint_data['status']}

Description:
{complaint_data['description']}

Location:
  Latitude  : {complaint_data.get('latitude', 'N/A')}
  Longitude : {complaint_data.get('longitude', 'N/A')}
  Address   : {complaint_data.get('location_address', 'N/A')}

Reporter:
  Name  : {complaint_data.get('user_name', 'N/A')}
  Email : {complaint_data.get('user_email', 'N/A')}

Image: {'Attached (see system)' if complaint_data.get('image_path') else 'None'}
ML Confidence: {complaint_data.get('ml_confidence', 'N/A')}

Submitted At: {complaint_data['created_at']}

Please log in to the Department Dashboard to view and update this complaint.
================================================
    """
    
    try:
        recipients = [dept_email]
        if admin_email and admin_email not in recipients:
            recipients.append(admin_email)
        
        msg = Message(
            subject=subject,
            recipients=recipients,
            body=body,
            sender=current_app.config.get('MAIL_USERNAME', 'noreply@civic.gov')
        )
        mail.send(msg)
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)


def send_status_update_email(mail, complaint_data: dict, user_email: str):
    """Notify user when complaint status changes."""
    subject = f"[UPDATE] Your Complaint #{complaint_data['id']} - {complaint_data['status']}"
    
    body = f"""
=== CIVIC ISSUE REPORTING SYSTEM ===
Complaint Status Update

Your complaint has been updated.

Complaint ID : #{complaint_data['id']}
Title        : {complaint_data['title']}
New Status   : {complaint_data['status']}
Department   : {complaint_data['department_assigned']}
Priority     : {complaint_data['priority']}

{'Your issue has been resolved! Please log in to submit your feedback.' if complaint_data['status'] == 'Completed' else ''}

Thank you for helping improve our city.
================================================
    """
    
    try:
        msg = Message(
            subject=subject,
            recipients=[user_email],
            body=body,
            sender=current_app.config.get('MAIL_USERNAME', 'noreply@civic.gov')
        )
        mail.send(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)
