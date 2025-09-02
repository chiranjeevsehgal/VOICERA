from google.oauth2 import id_token
from google.auth.transport import requests
import os
from fastapi import HTTPException, status
from services.database import users_collection
from services.auth import create_access_token
from datetime import datetime, timedelta

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

async def verify_google_token(token: str):
    """
    Verify a Google OAuth token and get user info.
    
    Args:
        token: Google ID token
        
    Returns:
        dict: User information from Google
    """
    try:
        # Token Verification
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), GOOGLE_CLIENT_ID
        )
        
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
            
        # Return user info
        return idinfo
        
    except ValueError as e:
        # Invalid token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {str(e)}"
        )

async def get_or_create_user_from_google(google_user_info):
    """
    Get an existing user or create a new one based on Google info.
    
    Args:
        google_user_info: User information from Google
        
    Returns:
        dict: User document from database
    """
    email = google_user_info.get('email')
    
    # Check if user exists
    user = await users_collection.find_one({"email": email})
    
    if not user:
        # Create new user
        user = {
            "email": email,
            "full_name": google_user_info.get('name'),
            "profile_picture": google_user_info.get('picture'),
            "role": "user",  # Default role
            "status": "active",  # Default status
            "created_at": datetime.utcnow(),
            "auth_provider": "google"
        }
        
        result = await users_collection.insert_one(user)
        user = await users_collection.find_one({"_id": result.inserted_id})
    
    return user