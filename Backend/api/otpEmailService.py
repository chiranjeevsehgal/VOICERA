from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from utils.generateOtp import generate_otp, verify_otp, otp_store
from utils.send_email import send_email
from services.auth import get_user_by_email, get_current_user
from services.update_user_password import update_user_password
from fastapi.responses import JSONResponse
from models.otpRequest_models import GenerateOtpRequest, OtpVerificationRequest, UpdatePasswordRequest

load_dotenv()

router = APIRouter(prefix='/mail')


@router.post("/get-otp")
async def send_reset_email(req : GenerateOtpRequest):
    
    user = get_user_by_email(req.email);
    
    
    if(user == None) :
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content = {
                "status": False,
                "detail": "user not registered",
            },
        )
    
    otp = str(generate_otp(req.email)) # Get your OTP from the utility function
    success = send_email(
        to=req.email,
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
        
        
@router.post("/verify-otp")
async def verifyOtp(
    req: OtpVerificationRequest, 
    ):
    
    email = req.email
    otp = req.otp
    
    result = verify_otp(email, otp)
    
    return {
    "status": result,
    "detail": "Email Verified Successfully" if result else "Invalid OTP"
}
    
@router.post("/update-password")
async def update_email(
    req : UpdatePasswordRequest
):
    result = verify_otp(req.email, req.otp);
    
    if(result) :
        updatePassword = await update_user_password(req.email, req.password)
        
        return {
            "status": updatePassword["status"],
            "detail": "Password Updated Successfully" if updatePassword['status'] else "Something went wrong !"
        }
    
    return {
        "status" : False,
        "detail" : "Invalid Otp. Please try again !"
    }
    
