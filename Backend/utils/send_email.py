import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

# Load HTML template
TEMPLATE_PATH = Path(__file__).parent.parent / "utils" / "reset_password.html"
HTML_TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")

def send_email(to: str, otp: str) -> bool:
    try:
        # Inject OTP into HTML template
        email_body = HTML_TEMPLATE.replace("{{OTP}}", otp)
        
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_USER")
        msg["To"] = to
        msg["Subject"] = "Password Reset OTP"
        msg.add_alternative(email_body, subtype="html")  # Set as HTML email

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
        print(f"Failed to send email: {str(e)}")
        return False