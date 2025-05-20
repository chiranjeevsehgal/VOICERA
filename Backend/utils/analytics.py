from datetime import datetime
import asyncio
from typing import Dict, Any, Optional
from fastapi import Request, Response
import time
from services.database import (
    api_usage_collection, 
    search_trends_collection,
    user_activity_collection,
    transcription_stats_collection
)

async def track_api_usage(
    request: Request,
    response: Response,
    response_time: float,
    user_id: Optional[str] = None
):
    """
    Track API usage for analytics.
    
    Args:
        request: The FastAPI request object
        response: The FastAPI response object
        response_time: Response time in milliseconds
        user_id: Optional user ID if authenticated
    """
    usage_data = {
        "timestamp": datetime.utcnow(),
        "endpoint": f"{request.method} {request.url.path}",
        "response_time": response_time,
        "status_code": response.status_code,
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    
    if user_id:
        usage_data["user_id"] = user_id
    
    try:
        await api_usage_collection.insert_one(usage_data)
    except Exception as e:
        print(f"WARNING: Failed to track API usage: {e}")

def track_search_term(term: str, user_id: Optional[str] = None):
    """
    Track a search term for analytics.
    
    Args:
        term: The search term
        user_id: Optional user ID if authenticated
    """
    search_data = {
        "timestamp": datetime.utcnow(),
        "term": term,
        "user_id": user_id
    }
    
    asyncio.create_task(_insert_search_trend(search_data))

async def _insert_search_trend(search_data: Dict[str, Any]):
    try:
        await search_trends_collection.insert_one(search_data)
    except Exception as e:
        print(f"WARNING: Failed to track search trend: {e}")

def track_user_activity(
    user_id: str,
    feature: str,
    session_duration: Optional[float] = None,
    additional_data: Optional[Dict[str, Any]] = None
):
    """
    Track user activity for analytics.
    
    Args:
        user_id: User ID
        feature: Feature/section being used
        session_duration: Optional session duration in seconds
        additional_data: Any additional tracking data
    """
    activity_data = {
        "timestamp": datetime.utcnow(),
        "user_id": user_id,
        "feature": feature
    }
    
    if session_duration is not None:
        activity_data["session_duration"] = session_duration
    
    if additional_data:
        activity_data.update(additional_data)
    
    asyncio.create_task(_insert_user_activity(activity_data))

async def _insert_user_activity(activity_data: Dict[str, Any]):
    try:
        await user_activity_collection.insert_one(activity_data)
    except Exception as e:
        print(f"WARNING: Failed to track user activity: {e}")

def track_transcription(
    status: str,
    processing_time: float,
    audio_length: float,
    language: Optional[str] = None,
    user_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
):
    """
    Track transcription statistics.
    
    Args:
        status: Status of transcription (success/error)
        processing_time: Time taken to process in seconds
        audio_length: Length of audio in seconds
        language: Detected language
        user_id: Optional user ID
        additional_data: Any additional tracking data
    """
    transcription_data = {
        "timestamp": datetime.utcnow(),
        "status": status,
        "processing_time": processing_time,
        "audio_length": audio_length
    }
    
    if language:
        transcription_data["language"] = language
    
    if user_id:
        transcription_data["user_id"] = user_id
    
    if additional_data:
        transcription_data.update(additional_data)
    
    asyncio.create_task(_insert_transcription_stats(transcription_data))

async def _insert_transcription_stats(stats_data: Dict[str, Any]):
    try:
        await transcription_stats_collection.insert_one(stats_data)
    except Exception as e:
        print(f"WARNING: Failed to track transcription stats: {e}") 