from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.oauth import verify_google_token, get_or_create_user_from_google
from services.auth import create_access_token, get_current_user
from services.ip_utils import get_ip_for_request
from services.database import users_collection
from datetime import datetime, timedelta
import os

router = APIRouter(prefix='/auth')

class GoogleTokenRequest(BaseModel):
    token: str

class ManualJwtRequest(BaseModel):
    user_id: str
    role: str = "user"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

@router.post("/google-login")
async def google_login(
    token_request: GoogleTokenRequest
):
    """
    Authenticate with Google OAuth token and return a JWT.
    """
    # Verify the Google token
    google_user_info = await verify_google_token(token_request.token)
    
    # Get or create user
    user = await get_or_create_user_from_google(google_user_info)
    
    # Generate JWT
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "userId": str(user["_id"])
    }
    
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "status": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "full_name": user.get("full_name"),
            "role": user["role"],
            "profile_picture": user.get("profile_picture")
        }
    }

@router.get("/validate-token")
async def validate_token(current_user = Depends(get_current_user)):
    """
    Validate a JWT token and return user information.
    """
    return {
        "valid": True,
        "user": {
            "id": str(current_user["_id"]),
            "email": current_user["email"],
            "role": current_user["role"]
        }
    }