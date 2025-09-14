from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from services.ip_utils import get_ip_for_request
from services.database import db, ip_credits_collection
from services.auth import get_current_user
import pytz

load_dotenv()
router = APIRouter()

# Get the default credit value
DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS"))

# Daily reset at 04:00 IST
IST_TZ = pytz.timezone("Asia/Kolkata")


@router.post("/credit")
async def deduct_credit(
    request: Request,
    detected_ip: str = Depends(get_ip_for_request),
    current_user: dict = Depends(get_current_user),
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
                        "last_used": current_time,
                    }
                },
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
                "credits": DEFAULT_CREDITS - 1,
                "created": current_time,
                "last_used": current_time,
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
                    },
                )

            # Decrement credits and update last_used
            await ip_credits_collection.update_one(
                {"ip": ip_address},
                {"$inc": {"credits": -1}, "$set": {"last_used": current_time}},
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
            content={"status": False, "detail": f"An error occurred: {str(e)}"},
        )


# Endpoint to check current credits
@router.get("/check-credits")
async def check_credits(
    request: Request,
    detected_ip: str = Depends(get_ip_for_request),
    current_user: dict = Depends(get_current_user),
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
                # "ip_address": ip_address,
                "credits_remaining": DEFAULT_CREDITS,
                "status": "unused",
            }

        should_reset = should_reset_credits(ip_record)

        credits = ip_record.get("credits")

        if should_reset:
            updated_doc = await ip_credits_collection.find_one_and_update(
                {"ip": ip_address},
                {"$set": {"credits": DEFAULT_CREDITS, "last_used": current_time}},
                return_document=True,
            )

            credits = updated_doc.get("credits", DEFAULT_CREDITS)
            created = updated_doc.get("created", current_time)
            last_used = updated_doc.get("last_used", current_time)

            return {
                # "ip_address": ip_address,
                "credits_remaining": credits,
            }

        return {
            # "ip_address": ip_address,
            "credits_remaining": credits,
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": False, "detail": f"An error occurred: {str(e)}"},
        )


def should_reset_credits(ip_record):
    """
    Determine if credits should reset at the daily boundary of 04:00 IST.

    Logic:
    - Compute the most recent 04:00 IST boundary (today at 04:00 if current time >= 04:00 IST,
      otherwise yesterday at 04:00 IST) and convert to UTC epoch.
    - If the record's last_used is strictly before that boundary and the current time is after
      that boundary, return True.
    """
    if not ip_record:
        return False

    now_utc_ts = int(datetime.utcnow().timestamp())
    now_ist = datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(IST_TZ)

    # Determine most recent 04:00 IST boundary
    today_4am_ist = now_ist.replace(hour=4, minute=0, second=0, microsecond=0)
    boundary_ist = today_4am_ist if now_ist >= today_4am_ist else (today_4am_ist - timedelta(days=1))

    boundary_utc_ts = int(boundary_ist.astimezone(pytz.UTC).timestamp())

    last_used_time = ip_record.get("last_used", 0)

    return last_used_time < boundary_utc_ts <= now_utc_ts
