from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from utils.generateOtp import generate_otp, verify_otp
from utils.send_email import send_email
from services.auth import get_user_by_email, get_current_user
from services.update_user_password import update_user_password
from fastapi.responses import JSONResponse
from models.otpRequest_models import GenerateOtpRequest, OtpVerificationRequest

load_dotenv()

router = APIRouter(prefix='/mail')


@router.post("/get-otp")
async def send_reset_email(current_user: dict = Depends(get_current_user)):
    
    user  = {
        "email" : current_user["email"],
        "full_name" : current_user.get("full_name"),
    }
    
    
    if(user == None) :
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content = {
                "status": False,
                "detail": "user not registered",
            },
        )
    
    otp = str(generate_otp(user['email'])) # Get your OTP from the utility function
    success = send_email(
        to=user['email'],
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
async def verifyOtp(
    request: OtpVerificationRequest,
    current_user: dict = Depends(get_current_user), 
    ):
    
    email = current_user['email']
    otp = request.otp
    
    result = verify_otp(email, otp)
    
    if(result) :
        updatePassword = await update_user_password(request.password, current_user)
        
        return {
            "status": result,
            "detail": "Password Updated Successfully" if result and updatePassword['status'] else "Password was not updated"
        }
    
    return {
    "status": result,
    "detail": "Email Verified Successfully" if result else "Invalid OTP"
}