import os
import smtplib
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from utils.logging import log_error

# Define IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

def get_error_email_template() -> str:
    """Load the error email HTML template from file"""
    try:
        # Get the path relative to the current file
        current_dir = Path(__file__).parent
        template_path = current_dir.parent / "email_templates" / "error.html"
        
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        log_error(f"Error email template not found at {template_path}", "get_error_email_template")
        # Fallback to a basic template
        return """
        <html>
        <body>
            <h1>VOICERA Error Alert</h1>
            <p><strong>Error:</strong> {{error_message}}</p>
            <p><strong>Time:</strong> {{timestamp}}</p>
            <p><strong>Endpoint:</strong> {{api_endpoint}}</p>
        </body>
        </html>
        """
    except Exception as e:
        log_error(f"Error reading error email template: {str(e)}", "get_error_email_template")
        return """
        <html>
        <body>
            <h1>VOICERA Error Alert</h1>
            <p>Error details could not be loaded.</p>
        </body>
        </html>
        """

def safe_replace(text: str, placeholder: str, value: Any, default: str = "Unknown") -> str:
    """Safely replace template placeholders, handling None values"""
    replacement = str(value) if value is not None else default
    return text.replace(placeholder, replacement)


def prepare_error_email(
    error_message: str,
    api_endpoint: str,
    error_code: str = "UNKNOWN",
) -> dict:
    """Prepare error email content with error-specific data"""
    template = get_error_email_template()
    
    # Get current timestamp in IST
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now.astimezone(IST)
    
    # Replace template variables
    email_content = template.replace("{{timestamp}}", ist_now.strftime("%Y-%m-%d %H:%M:%S"))
    email_content = safe_replace(email_content, "{{timezone}}", "IST")
    email_content = safe_replace(email_content, "{{error_code}}", error_code)
    email_content = safe_replace(email_content, "{{error_message}}", error_message)
    email_content = safe_replace(email_content, "{{api_endpoint}}", api_endpoint)
    email_content = safe_replace(email_content, "{{dashboard_url}}", f"{os.getenv("FRONTEND_URL")}/admin/dashboard", "#")
    
    return {
        "subject": f"VOICERA Error Alert: {error_message}",
        "content": email_content
    }

def send_email(to: str, subject: str = "Error Detected", content: str = "Error Detected") -> bool:
    """Send email using SMTP"""
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_USER")
        msg["To"] = to
        msg["Subject"] = subject
        msg.add_alternative(content, subtype="html")

        with smtplib.SMTP_SSL(
            os.getenv("SMTP_HOST"),
            int(os.getenv("SMTP_PORT")),
        ) as server:
            server.login(
                os.getenv("SMTP_USER"),
                os.getenv("SMTP_PASSWORD"),
            )
            server.send_message(msg)
        return True
    except Exception as e:
        log_error(f"Failed to send email: {str(e)}", "send_email", {"error": str(e), "recipient": to})
        return False

async def send_error_alert_email(
    error_message: str,
    api_endpoint: Optional[str] = None,
    error_code: Optional[str] = "UNKNOWN",
):
    """Send error alert email to admins"""
    try:
        # Get admin email(s) from environment
        admin_emails = os.getenv("ADMIN_EMAIL_ALERTS", "").split(",")
        admin_emails = [email.strip() for email in admin_emails if email.strip()]
        
        if not admin_emails:
            log_error("No admin emails configured for error alerts", "send_error_alert_email")
            return
        
        # Prepare email content
        email_data = prepare_error_email(
            error_message=error_message,
            api_endpoint=api_endpoint,
            error_code=error_code,
        )
        
        # Send to all admin emails
        for admin_email in admin_emails:
            success = send_email(
                to=admin_email,
                subject=email_data["subject"],
                content=email_data["content"]
            )
            if success:
                print(f"Error alert email sent successfully to {admin_email}")
                log_error(f"Error alert email sent successfully to {admin_email}", "send_error_alert_email")
            else:
                print(f"Failed to send error alert email to {admin_email}")
                log_error(f"Failed to send error alert email to {admin_email}", "send_error_alert_email")
                
    except Exception as e:
        log_error(f"Error sending error alert email: {str(e)}", "send_error_alert_email", {
            "error": str(e), 
            "endpoint": api_endpoint,
            "original_error": error_message
        })