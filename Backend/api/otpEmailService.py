from fastapi import APIRouter, HTTPException, Request, status
from dotenv import load_dotenv
from utils.generateOtp import generate_otp, verify_otp
from utils.send_email import send_email
from services.auth import get_user_by_email
from fastapi.responses import JSONResponse
from models.otpRequest_models import GenerateOtpRequest, OtpVerificationRequest

load_dotenv()

router = APIRouter(prefix='/mail')


@router.post("/get-otp")
async def send_reset_email(request: GenerateOtpRequest):
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