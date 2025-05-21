import os
import smtplib
from email.message import EmailMessage
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from utils.generateOtp import generate_otp, verify_otp
from services.auth import get_user_by_email
from fastapi.responses import JSONResponse


load_dotenv()

router = APIRouter(prefix='/mail')

# Load HTML template
TEMPLATE_PATH = Path(__file__).parent.parent / "utils" / "reset_password.html"
HTML_TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")

class EmailRequest(BaseModel):
    email: str
    
class OtpVerificationRequest(BaseModel):
    email: str
    otp: str

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

@router.post("/get-otp")
async def send_reset_email(request: EmailRequest):
    # Verify if the user exsists
    user = await get_user_by_email(request.email)
    
    if(user == None) :
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content = {
                "status": False,
                "detail": "user not registered",
            },
        )
    
    otp = str(generate_otp(request.email)) # Get your OTP from the utility function
    success = send_email(
        to=request.email,
        otp=otp
    )
    
    if success:
        return {
            "message": "Password reset email sent successfully!",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send password reset email"
        )
        
@router.post("/varify-otp")
async def verifyOtp(request : OtpVerificationRequest):
    
    email = request.email
    otp = request.otp
    
    result = verify_otp(email, otp)
    
    return {
    "status": result,
    "detail": "Email Verified Successfully" if result else "Invalid OTP"
}