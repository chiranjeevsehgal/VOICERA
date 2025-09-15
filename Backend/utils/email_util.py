import os
import smtplib
from email.message import EmailMessage
from utils.logging import log_error

def send_email(to: str, subject: str='Default Subject', content: str='Default content') -> bool:
    try:
        msg = EmailMessage()
        msg['From'] = os.getenv('SMTP_USER')
        msg['To'] = to
        msg['Subject'] = subject
        msg.add_alternative(content, subtype='html')
        with smtplib.SMTP_SSL(os.getenv('SMTP_HOST'), int(os.getenv('SMTP_PORT'))) as server:
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
            server.send_message(msg)
        return True
    except Exception as e:
        log_error(f'Failed to send email: {str(e)}', 'send_email', {'error': str(e), 'recipient': to})
        return False