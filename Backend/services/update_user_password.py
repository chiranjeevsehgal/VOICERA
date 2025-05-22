from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from datetime import datetime
from utils.generateOtp import delete_otp

from services.auth import get_current_user, get_password_hash, users_collection


async def update_user_password(
    email: str,
    password : str,
):
    
    # Update the user's password and set updated_at
    hashed_password = get_password_hash(password)
    update_data = {
        "$set": {
            "password": hashed_password,
            "updated_at": datetime.utcnow()
        }
    }

    await users_collection.update_one(
        {"email": email},  # Filter by email
        update_data
    )
    
    # Call delete OTP func
    delete_otp(email)
    
    return {
        "status" : True,
        "detail" : "Password updated successfully"
    } 
    
    
    
    