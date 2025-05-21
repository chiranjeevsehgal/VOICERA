from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from datetime import datetime

from services.auth import get_current_user, get_password_hash, users_collection


async def update_user_password(
    password : str,
    current_user: dict,
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
        {"email": current_user['email']},  # Filter by email
        update_data
    )
    
    return {
        "status" : True,
        "detail" : "Password updated successfully"
    } 
    
    
    
    