from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.oauth import verify_google_token, get_or_create_user_from_google
from services.auth import create_access_token, get_current_user
from datetime import datetime, timedelta
import os
import requests

router = APIRouter(prefix='/auth')

class ManualJwtRequest(BaseModel):
    user_id: str
    role: str = "user"

class GoogleCodeExchangeRequest(BaseModel):
    code: str

class GoogleCodeExchangeResponse(BaseModel):
    status: bool
    detail: str
    role: str
    access_token: str
    token_type: str

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

@router.post("/google-login", response_model=GoogleCodeExchangeResponse)
async def google_login(
    request: GoogleCodeExchangeRequest
):
    """
    Authenticates, Exchange Google authorization code for tokens and return a JWT.
    """
    # Exchange authorization code for token
    token = await exchange_code_for_tokens(request.code)
    
    # Verify the Google token
    google_user_info = await verify_google_token(token['id_token'])
    
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
        "detail": "Login Successful",
        "role": user["role"],
        "access_token": access_token,
        "token_type": "bearer",
    }


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange authorization code for access and ID tokens.
    
    Args:
        code: Authorization code from Google
        
    Returns:
        dict: Token response from Google
    """
    token_url = "https://oauth2.googleapis.com/token"
    
    data = {
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }
    
    response = requests.post(token_url, data=data)
    
    if response.status_code != 200:
        raise ValueError(f"Token exchange failed: {response.text}")
    
    tokens = response.json()
    
    # Validate required tokens
    if 'id_token' not in tokens:
        raise ValueError("No ID token received from Google")
    
    return tokens