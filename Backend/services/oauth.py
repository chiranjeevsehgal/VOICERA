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

async def get_or_create_user_from_github(github_user_info: dict) -> dict:
    """
    Get or create user from GitHub user information.
    """
    email = github_user_info.get('email')
    github_id = str(github_user_info.get('id'))
    name = github_user_info.get('name') or github_user_info.get('login')
    avatar_url = github_user_info.get('avatar_url')
    
    if not email:
        raise ValueError("No email found in GitHub profile")
    
    # Check if user exists by email
    existing_user = await users_collection.find_one({"email": email})
    
    if existing_user:
        # Update GitHub info if not present
        update_data = {}
        if not existing_user.get('github_id'):
            update_data['github_id'] = github_id
        if not existing_user.get('avatar_url') and avatar_url:
            update_data['avatar_url'] = avatar_url
            
        if update_data:
            await users_collection.update_one(
                {"_id": existing_user["_id"]}, 
                {"$set": update_data}
            )
            existing_user.update(update_data)
        
        return existing_user
    
    # Create new user
    new_user = {
        "email": email,
        "full_name": name,
        "github_id": github_id,
        "profile_picture": avatar_url,
        "role": "user",
        "status": "active",
        "created_at": datetime.utcnow(),
        "auth_provider": "github"
    }
    
    result = await users_collection.insert_one(new_user)
    new_user["_id"] = result.inserted_id
    
    return new_user

async def verify_github_token(access_token: str) -> dict:
    """
    Verify GitHub access token and return user info.
    This is optional - you can use the token directly to get user info.
    """
    headers = {
        'Authorization': f'token {access_token}',
        'Accept': 'application/json'
    }
    
    response = requests.get("https://api.github.com/user", headers=headers)
    
    if response.status_code != 200:
        raise ValueError("Invalid GitHub token")
    
    return response.json()