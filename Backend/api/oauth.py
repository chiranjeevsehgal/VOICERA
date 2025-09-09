from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.oauth import (
    verify_google_token,
    get_or_create_user_from_google,
    verify_github_token,
    get_or_create_user_from_github,
)
from services.auth import create_access_token, get_current_user
from datetime import datetime, timedelta
import os
import requests

router = APIRouter(prefix="/auth")


class ManualJwtRequest(BaseModel):
    user_id: str
    role: str = "user"


class OAuthCodeExchangeRequest(BaseModel):
    code: str
    provider: str  # "google" or "github"


class OAuthCodeExchangeResponse(BaseModel):
    status: bool
    detail: str
    role: str
    access_token: str
    token_type: str


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

# Google OAuth Config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# GitHub OAuth Config
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")


@router.post("/oauth/callback", response_model=OAuthCodeExchangeResponse)
async def oauth_callback(request: OAuthCodeExchangeRequest):
    """
    Unified OAuth callback for Google and GitHub authentication.
    Exchange authorization code for tokens and return a JWT.
    """
    try:
        if request.provider == "google":
            return await handle_google_oauth(request.code)
        elif request.provider == "github":
            return await handle_github_oauth(request.code)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported OAuth provider",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authentication failed: {str(e)}",
        )


async def handle_google_oauth(code: str) -> OAuthCodeExchangeResponse:
    """Handle Google OAuth flow"""
    # Exchange authorization code for token
    token = await exchange_google_code_for_tokens(code)

    # Verify the Google token
    google_user_info = await verify_google_token(token["id_token"])

    # Get or create user
    user = await get_or_create_user_from_google(google_user_info)

    if user.get("status") == "inactive":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": False,
                "detail": "Your account is inactive. Please contact support for assistance.",
                "role": None,
                "access_token": None,
                "token_type": None,
            },
        )

    # Generate JWT
    access_token = generate_jwt_token(user)

    return OAuthCodeExchangeResponse(
        status=True,
        detail="Google login successful",
        role=user["role"],
        access_token=access_token,
        token_type="bearer",
    )


async def handle_github_oauth(code: str) -> OAuthCodeExchangeResponse:
    """Handle GitHub OAuth flow"""
    # Exchange authorization code for token
    access_token = await exchange_github_code_for_token(code)

    # Get user info from GitHub
    github_user_info = await get_github_user_info(access_token)

    # Get or create user
    user = await get_or_create_user_from_github(github_user_info)

    if user.get("status") == "inactive":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": False,
                "detail": "Your account is inactive. Please contact support for assistance.",
                "role": None,
                "access_token": None,
                "token_type": None,
            },
        )

    # Generate JWT
    jwt_token = generate_jwt_token(user)

    return OAuthCodeExchangeResponse(
        status=True,
        detail="GitHub login successful",
        role=user["role"],
        access_token=jwt_token,
        token_type="bearer",
    )


def generate_jwt_token(user: dict) -> str:
    """Generate JWT token for authenticated user"""
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "userId": str(user["_id"]),
    }

    return create_access_token(
        data=token_data, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )


async def exchange_google_code_for_tokens(code: str) -> dict:
    """
    Exchange Google authorization code for access and ID tokens.
    """
    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
    }

    response = requests.post(token_url, data=data)

    if response.status_code != 200:
        raise ValueError(f"Google token exchange failed: {response.text}")

    tokens = response.json()

    if "id_token" not in tokens:
        raise ValueError("No ID token received from Google")

    return tokens


async def exchange_github_code_for_token(code: str) -> str:
    """
    Exchange GitHub authorization code for access token.
    """
    token_url = "https://github.com/login/oauth/access_token"

    data = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": GITHUB_REDIRECT_URI,
    }

    headers = {"Accept": "application/json"}

    response = requests.post(token_url, data=data, headers=headers)

    if response.status_code != 200:
        raise ValueError(f"GitHub token exchange failed: {response.text}")

    token_data = response.json()

    if "access_token" not in token_data:
        raise ValueError(f"No access token received from GitHub: {token_data}")

    return token_data["access_token"]


async def get_github_user_info(access_token: str) -> dict:
    """
    Get user information from GitHub using access token.
    """
    user_url = "https://api.github.com/user"
    email_url = "https://api.github.com/user/emails"

    headers = {"Authorization": f"token {access_token}", "Accept": "application/json"}

    # Get user basic info
    user_response = requests.get(user_url, headers=headers)
    if user_response.status_code != 200:
        raise ValueError(f"Failed to get GitHub user info: {user_response.text}")

    user_data = user_response.json()

    # Get user email (GitHub API requires separate call for emails)
    email_response = requests.get(email_url, headers=headers)
    if email_response.status_code == 200:
        emails = email_response.json()
        # Find primary email
        primary_email = next(
            (email["email"] for email in emails if email["primary"]), None
        )
        if primary_email:
            user_data["email"] = primary_email

    return user_data


# Keep your existing Google login route for backward compatibility
@router.post("/google-login", response_model=OAuthCodeExchangeResponse)
async def google_login(request: OAuthCodeExchangeRequest):
    """
    Legacy Google login endpoint (for backward compatibility)
    """
    oauth_request = OAuthCodeExchangeRequest(code=request.code, provider="google")
    return await oauth_callback(oauth_request)
