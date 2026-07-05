import os
import smtplib
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from utils.logging import log_error

IST = timezone(timedelta(hours=5, minutes=30))

def get_contact_email_template() -> str:
    """Load the contact email HTML template from file"""
    try:
        current_dir = Path(__file__).parent
        template_path = current_dir.parent / 'email_templates' / 'voicera_contact.html'
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        log_error(f'Contact email template not found at {template_path}', 'get_contact_email_template')
    
    except Exception as e:
        # Fallback Template
        log_error(f'Error reading contact email template: {str(e)}', 'get_contact_email_template')
        return '''
        <html>
        <body>
            <h1>New Contact Form Submission-Voicera</h1>
            <p>Contact form template could not be loaded properly.</p>
            <p><strong>Name:</strong> {{name}}</p>
            <p><strong>Email:</strong> {{email}}</p>
            <p><strong>Phone:</strong> {{phone_number}}</p>
            <p><strong>Message:</strong> {{message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
        </body>
        </html>
        '''

def safe_replace(text: str, placeholder: str, value: Any, default: str = 'Not provided') -> str:
    """Safely replace template placeholders, handling None values"""
    replacement = str(value) if value is not None else default
    return text.replace(placeholder, replacement)

def prepare_contact_email(name: str, email: str, message: str, phone_number: Optional[str] = None) -> dict:
    """Prepare contact email content for admin notification"""
    template = get_contact_email_template()
    
    # Get current timestamp in IST
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now.astimezone(IST)
    
    # Replace template placeholders
    email_content = template.replace('{{timestamp}}', ist_now.strftime('%Y-%m-%d %H:%M:%S'))
    email_content = safe_replace(email_content, '{{timezone}}', 'IST')
    email_content = safe_replace(email_content, '{{name}}', name)
    email_content = safe_replace(email_content, '{{email}}', email)
    email_content = safe_replace(email_content, '{{phone_number}}', phone_number)
    email_content = safe_replace(email_content, '{{message}}', message)
    
    return {
        'subject': f'New Contact: {name} - {email}',
        'content': email_content
    }

def send_email(to: str, subject: str, content: str, reply_to: Optional[str] = None) -> bool:
    """Send email using SMTP"""
    try:
        msg = EmailMessage()
        msg['From'] = os.getenv('SMTP_USER')
        msg['To'] = to
        msg['Subject'] = subject
        
        # Set reply-to as the contact form submitter's email
        if reply_to:
            msg['Reply-To'] = reply_to
            
        msg.add_alternative(content, subtype='html')
        
        with smtplib.SMTP_SSL(os.getenv('SMTP_HOST'), int(os.getenv('SMTP_PORT'))) as server:
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
            server.send_message(msg)
        return True
    except Exception as e:
        log_error(f'Failed to send email: {str(e)}', 'send_email', {
            'error': str(e), 
            'recipient': to,
            'reply_to': reply_to
        })
        return False

async def send_contact_form_email(name: str, email: str, message: str, phone_number: Optional[str] = None) -> bool:
    """Send contact form notification to all configured admin emails"""
    try:
        # Get admin emails from environment variable
        admin_emails = os.getenv('ADMIN_CONTACT_EMAILS', '').split(',')
        admin_emails = [email_addr.strip() for email_addr in admin_emails if email_addr.strip()]
        
        if not admin_emails:
            log_error('No admin emails configured for contact form alerts', 'send_contact_form_email')
            return False
        
        # Prepare email content
        email_data = prepare_contact_email(
            name=name, 
            email=email, 
            message=message, 
            phone_number=phone_number
        )
        
        # Send to all admin emails
        success_count = 0
        for admin_email in admin_emails:
            success = send_email(
                to=admin_email, 
                subject=email_data['subject'], 
                content=email_data['content'],
                reply_to=email  # Set submitter's email as reply-to
            )
            
            if success:
                success_count += 1
                print(f'Contact form email sent successfully to {admin_email}')
            else:
                print(f'Failed to send contact form email to {admin_email}')
                log_error(f'Failed to send contact form email to {admin_email}', 'send_contact_form_email')
        
        # Return True if at least one email was sent successfully
        return success_count > 0
        
    except Exception as e:
        log_error(f'Error sending contact form email: {str(e)}', 'send_contact_form_email', {
            'error': str(e), 
            'name': name,
            'email': email,
            'phone': phone_number
        })
        return False