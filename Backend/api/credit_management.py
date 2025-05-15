from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
import os
from dotenv import load_dotenv
from services.ip_utils import get_ip_for_request
from services.database import db, ip_credits_collection

load_dotenv()
router = APIRouter()

# Get the default credit value
DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS"))

# Reset timeframe in seconds
RESET_TIMEFRAME = int(os.getenv("RESET_TIMEFRAME"))

@router.post("/credit")
async def deduct_credit(
    request: Request,
    detected_ip: str = Depends(get_ip_for_request)
):
    """
    Endpoint that tracks IP usage and enforces credit limits.
    
    For each IP address:
    - First time: Initialize with DEFAULT_CREDITS
    - Each upload: Decrement credits if > 0
    - Track creation time and last usage time
    - Prevent upload when credits reach 0
    """
    try:
        ip_address = detected_ip
        
        # Current time in seconds in epoch format
        current_time = int(datetime.utcnow().timestamp())
        
        # Finding the IP record
        ip_record = await ip_credits_collection.find_one({"ip": ip_address})
        
        # Check if we should reset the credits based on time
        if ip_record and should_reset_credits(ip_record):
            await ip_credits_collection.update_one(
                {"ip": ip_address},
                {
                    "$set": {
                        "credits": DEFAULT_CREDITS - 1,  
                        "created": ip_record.get("created"),
                        "last_used": current_time       
                    }
                }
            )
            return {
                "status": True,
                "message": "File uploaded successfully",
                "credits_remaining": DEFAULT_CREDITS - 1,
            }

        
        if not ip_record:
            # First time this IP is seen - create new record with (default credits-1)
            new_record = {
                "ip": ip_address,
                "credits": DEFAULT_CREDITS-1,
                "created": current_time,
                "last_used": current_time
            }
            await ip_credits_collection.insert_one(new_record)
            credits_remaining = DEFAULT_CREDITS - 1
        else:
            # IP exists - check remaining credits
            credits_remaining = ip_record.get("credits", 0)
            
            if credits_remaining <= 0:
                # No credits left
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "status": False,
                        "detail": "Credit limit reached for the day",
                        "credits_remaining": 0,
                    }
                )
            
            # Decrement credits and update last_used
            await ip_credits_collection.update_one(
                {"ip": ip_address},
                {
                    "$inc": {"credits": -1},
                    "$set": {"last_used": current_time}
                }
            )
            
            # Update credits_remaining after decrement
            credits_remaining -= 1
        
        return {
            "status": True,
            "message": "File uploaded successfully",
            "credits_remaining": credits_remaining,
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": False,
                "detail": f"An error occurred: {str(e)}"
            }
        )

# Endpoint to check current credits
@router.get("/check-credits")
async def check_credits(
    request: Request,
    detected_ip: str = Depends(get_ip_for_request),
):
    """Check remaining credits for the current IP address."""
    try:
        ip_address = detected_ip
        current_time = int(datetime.utcnow().timestamp())
        
        # Find the IP record
        ip_record = await ip_credits_collection.find_one({"ip": ip_address})

        if not ip_record:
            # IP not found, would get default credits on first check
            return {
                "ip_address": ip_address,
                "credits_remaining": DEFAULT_CREDITS,
                "status": "unused"
            }

        should_reset = should_reset_credits(ip_record)
        
        credits = ip_record.get("credits")
        
        if should_reset:
            updated_doc = await ip_credits_collection.find_one_and_update(
                {"ip": ip_address},
                {
                    "$set": {
                        "credits": DEFAULT_CREDITS,
                        "last_used": current_time
                    }
                },
                return_document=True
            )
            
            credits = updated_doc.get("credits", DEFAULT_CREDITS)
            created = updated_doc.get("created", current_time)
            last_used = updated_doc.get("last_used", current_time)
            
            return {
                "ip_address": ip_address,
                "credits_remaining": credits,
            }
        
        return {
            "ip_address": ip_address,
            "credits_remaining": credits,
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": False,
                "detail": f"An error occurred: {str(e)}"
            }
        )
    

def should_reset_credits(ip_record):
    """
    Check if credits should be reset based on time difference.
    
    Args:
        ip_record: The IP record from the database
        
    Returns:
        bool: True if credits should be reset, False otherwise
    """
    if not ip_record:
        return False
    
    current_time = int(datetime.utcnow().timestamp())
    last_used_time = ip_record.get("last_used")
    
    time_diff = current_time - last_used_time

    # Returns if time more than RESET_TIMEFRAME have passed
    return time_diff >= RESET_TIMEFRAME