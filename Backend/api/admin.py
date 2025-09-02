from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field
import os
import shutil
import asyncio

from services.auth import get_current_user, requires_role, get_password_hash, get_user_by_email
from services.database import (
    users_collection, 
    api_usage_collection,
    transcription_stats_collection,
    search_trends_collection,
    user_activity_collection,
    logs_collection
)
from models.analytics import (
    APIUsageStats,
    TranscriptionStats,
    SearchTrendsResponse,
    UserActivityData,
    LogsResponse,
    LogEntry
)

router = APIRouter(prefix='/admin')

# Pydantic models for request/response validation
class UserListResponse(BaseModel):
    total_count: int
    users: List[Dict[str, Any]]

class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None 
    status: Optional[str] = None  # active, inactive, suspended

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = "user"
    status: str = "active"

# Helper functions
def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive data and format the user object for API responses"""
    if not user:
        return {}
    
    # Convert ObjectId to string
    user["id"] = str(user.pop("_id")) if "_id" in user else None
    
    # Remove sensitive fields
    user.pop("password", None)
    
    return user

@router.get("/users", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    role: Optional[str] = Query(None, description="Filter by user role"),
    status: Optional[str] = Query(None, description="Filter by user status"),
    search: Optional[str] = Query(None, description="Search in email and full_name")
):
    """
    List all users with pagination and filtering.
    Only accessible to administrators.
    """
    # Build the filter query
    filter_query = {}
    
    if role:
        filter_query["role"] = role
    
    if status:
        filter_query["status"] = status
    
    if search:
        filter_query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"full_name": {"$regex": search, "$options": "i"}}
        ]
    
    # Get total count for pagination
    total_count = await users_collection.count_documents(filter_query)
    
    # Calculate skip for pagination
    skip = (page - 1) * limit
    
    # Get users with pagination and sorting
    cursor = users_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    
    users = await cursor.to_list(length=limit)
    
    # Sanitize user data before returning
    sanitized_users = [sanitize_user(user) for user in users]
    
    return UserListResponse(
        total_count=total_count,
        users=sanitized_users
    )

@router.get("/users/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user_details(
    user_id: str = Path(..., description="User ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Get detailed information about a specific user.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    user = await users_collection.find_one({"_id": obj_id})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    return sanitize_user(user)

@router.put("/users/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user(
    update_data: UserUpdateRequest,
    user_id: str = Path(..., description="User ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Update user details (role, status, etc.).
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Check if user exists
    existing_user = await users_collection.find_one({"_id": obj_id})
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prepare update data
    update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
    
    if not update_dict:
        return sanitize_user(existing_user)
    
    # Add updated_at timestamp
    update_dict["updated_at"] = datetime.utcnow()
    
    # Update user in database
    await users_collection.update_one(
        {"_id": obj_id},
        {"$set": update_dict}
    )
    
    # Get updated user
    updated_user = await users_collection.find_one({"_id": obj_id})
    
    return sanitize_user(updated_user)

@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str = Path(..., description="User ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Permanently delete a user from the system.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Check if user exists
    existing_user = await users_collection.find_one({"_id": obj_id})
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prevent deletion of the admin user making the request
    if str(existing_user["_id"]) == str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Delete user
    await users_collection.delete_one({"_id": obj_id})
    return {"status": "success", "detail": f"User {user_id} has been permanently deleted"}

@router.patch("/users/{user_id}/status", status_code=status.HTTP_200_OK)
async def update_user_status(
    user_id: str = Path(..., description="User ID"),
    status_update: Dict[str, str] = Body(..., example={"status": "inactive"}),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Update a user's status (activate/deactivate/suspend).
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Check if user exists
    existing_user = await users_collection.find_one({"_id": obj_id})
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Validate status
    new_status = status_update.get("status")
    if not new_status or new_status not in ["active", "inactive", "suspended"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid status required: 'active', 'inactive', or 'suspended'"
        )
    
    # Prevent changing status of the admin user making the request
    if str(existing_user["_id"]) == str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the status of your own account"
        )
    
    # Update user status
    await users_collection.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "status": new_status,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    status_message = "activated" if new_status == "active" else new_status
    return {"status": "success", "detail": f"User {user_id} has been {status_message}"}

@router.post("/users/create", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateRequest,
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Create a new user directly from the admin panel.
    Only accessible to administrators.
    """
    # Check if user with this email already exists
    existing_user = await get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {user_data.email} already exists"
        )
    
    # Validate role
    valid_roles = ["user", "premium", "admin"]
    if user_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Validate status
    valid_statuses = ["active", "inactive", "suspended"]
    if user_data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Hash the password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user document
    new_user = {
        "email": user_data.email,
        "password": hashed_password,
        "full_name": user_data.full_name,
        "role": user_data.role,
        "status": user_data.status,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": str(current_user["_id"])  # Track who created this user
    }
    
    # Insert into database
    result = await users_collection.insert_one(new_user)
    
    # Get the created user
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    
    return sanitize_user(created_user)

# Analytics & Monitoring API endpoints

@router.get("/analytics/usage", response_model=APIUsageStats, status_code=status.HTTP_200_OK)
async def get_api_usage_metrics(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    days: int = Query(30, ge=1, le=365, description="Number of days to include in analytics")
):
    """
    Track API usage metrics.
    Returns data on API usage patterns, endpoint popularity, and performance metrics.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get usage metrics from the database
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": None,
            "total_requests": {"$sum": 1},
            "average_response_time": {"$avg": "$response_time"},
            "min_date": {"$min": "$timestamp"},
            "max_date": {"$max": "$timestamp"}
        }}
    ]
    
    result = await api_usage_collection.aggregate(pipeline).to_list(length=1)
    
    if not result:
        # Return empty stats if no data found
        return APIUsageStats(
            date_range={
                "start": start_date,
                "end": datetime.utcnow()
            }
        )
    
    # Get endpoint distribution
    endpoint_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$endpoint",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    endpoint_results = await api_usage_collection.aggregate(endpoint_pipeline).to_list(length=100)
    endpoint_counts = {item["_id"]: item["count"] for item in endpoint_results}
    
    # Get user distribution
    user_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}, "user_id": {"$exists": True}}},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 50}
    ]
    
    user_results = await api_usage_collection.aggregate(user_pipeline).to_list(length=50)
    user_counts = {str(item["_id"]): item["count"] for item in user_results}
    
    # Construct the response
    stats = APIUsageStats(
        total_requests=result[0].get("total_requests", 0),
        endpoint_counts=endpoint_counts,
        user_counts=user_counts,
        average_response_time=result[0].get("average_response_time"),
        date_range={
            "start": result[0].get("min_date", start_date),
            "end": result[0].get("max_date", datetime.utcnow())
        }
    )
    
    return stats

@router.get("/analytics/transcriptions", response_model=TranscriptionStats, status_code=status.HTTP_200_OK)
async def get_transcription_statistics(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    days: int = Query(30, ge=1, le=365, description="Number of days to include in statistics")
):
    """
    Monitor transcription statistics.
    Returns data on transcription success rates, durations, and language distributions.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get transcription metrics from the database
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": None,
            "total_transcriptions": {"$sum": 1},
            "successful_transcriptions": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "failed_transcriptions": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "average_duration": {"$avg": "$processing_time"},
            "total_audio_length": {"$sum": "$audio_length"},
            "min_date": {"$min": "$timestamp"},
            "max_date": {"$max": "$timestamp"}
        }}
    ]
    
    result = await transcription_stats_collection.aggregate(pipeline).to_list(length=1)
    
    if not result:
        # Return empty stats if no data found
        return TranscriptionStats(
            date_range={
                "start": start_date,
                "end": datetime.utcnow()
            }
        )
    
    # Get language distribution
    language_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}, "language": {"$exists": True}}},
        {"$group": {
            "_id": "$language",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    language_results = await transcription_stats_collection.aggregate(language_pipeline).to_list(length=50)
    language_counts = {item["_id"]: item["count"] for item in language_results}
    
    # Construct the response
    stats = TranscriptionStats(
        total_transcriptions=result[0].get("total_transcriptions", 0),
        successful_transcriptions=result[0].get("successful_transcriptions", 0),
        failed_transcriptions=result[0].get("failed_transcriptions", 0),
        average_duration=result[0].get("average_duration"),
        total_audio_length=result[0].get("total_audio_length"),
        languages=language_counts,
        date_range={
            "start": result[0].get("min_date", start_date),
            "end": result[0].get("max_date", datetime.utcnow())
        }
    )
    
    return stats

@router.get("/analytics/search-trends", response_model=SearchTrendsResponse, status_code=status.HTTP_200_OK)
async def get_search_trends(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    days: int = Query(30, ge=1, le=365, description="Number of days to include in trends"),
    limit: int = Query(20, ge=5, le=100, description="Number of top search terms to return")
):
    """
    Track popular search terms.
    Returns data on trending search terms and patterns.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get top search terms
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": "$term",
            "count": {"$sum": 1},
            "last_searched": {"$max": "$timestamp"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]
    
    results = await search_trends_collection.aggregate(pipeline).to_list(length=limit)
    
    # Get overall metrics
    metrics_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": None,
            "total_searches": {"$sum": 1},
            "min_date": {"$min": "$timestamp"},
            "max_date": {"$max": "$timestamp"}
        }}
    ]
    
    metrics = await search_trends_collection.aggregate(metrics_pipeline).to_list(length=1)
    
    # Get unique terms count
    unique_terms_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {"_id": "$term"}},
        {"$count": "unique_terms"}
    ]
    
    unique_terms_result = await search_trends_collection.aggregate(unique_terms_pipeline).to_list(length=1)
    
    # Format the response
    top_terms = []
    for result in results:
        top_terms.append({
            "term": result["_id"],
            "count": result["count"],
            "last_searched": result["last_searched"]
        })
    
    # Construct the response
    response = {
        "top_terms": top_terms,
        "total_searches": metrics[0]["total_searches"] if metrics else 0,
        "unique_terms": unique_terms_result[0]["unique_terms"] if unique_terms_result else 0,
        "date_range": {
            "start": metrics[0]["min_date"] if metrics else start_date,
            "end": metrics[0]["max_date"] if metrics else datetime.utcnow()
        }
    }
    
    return response

@router.get("/analytics/user-activity", response_model=UserActivityData, status_code=status.HTTP_200_OK)
async def get_user_activity(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    days: int = Query(30, ge=1, le=365, description="Number of days to include in activity data")
):
    """
    Monitor user engagement.
    Returns data on user activity, session metrics, and feature usage.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get user activity metrics
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$group": {
            "_id": None,
            "total_active_users": {"$addToSet": "$user_id"},
            "average_session_duration": {"$avg": "$session_duration"},
            "min_date": {"$min": "$timestamp"},
            "max_date": {"$max": "$timestamp"}
        }}
    ]
    
    result = await user_activity_collection.aggregate(pipeline).to_list(length=1)
    
    # Get new users in the period
    new_users_pipeline = [
        {"$match": {"created_at": {"$gte": start_date}}},
        {"$count": "new_users"}
    ]
    
    new_users_result = await users_collection.aggregate(new_users_pipeline).to_list(length=1)
    
    # Get most active hours
    hours_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}}},
        {"$project": {
            "hour": {"$hour": "$timestamp"}
        }},
        {"$group": {
            "_id": "$hour",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    hours_result = await user_activity_collection.aggregate(hours_pipeline).to_list(length=24)
    hours_distribution = {item["_id"]: item["count"] for item in hours_result}
    
    # Get most used features
    features_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date}, "feature": {"$exists": True}}},
        {"$group": {
            "_id": "$feature",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    
    features_result = await user_activity_collection.aggregate(features_pipeline).to_list(length=10)
    features_distribution = {item["_id"]: item["count"] for item in features_result}
    
    # Construct the response
    stats = UserActivityData(
        total_active_users=len(result[0]["total_active_users"]) if result and "total_active_users" in result[0] else 0,
        new_users=new_users_result[0]["new_users"] if new_users_result else 0,
        returning_users=(len(result[0]["total_active_users"]) - (new_users_result[0]["new_users"] if new_users_result else 0)) 
            if result and "total_active_users" in result[0] else 0,
        average_session_duration=result[0].get("average_session_duration") if result else None,
        most_active_hours=hours_distribution,
        most_used_features=features_distribution,
        date_range={
            "start": result[0].get("min_date", start_date) if result else start_date,
            "end": result[0].get("max_date", datetime.utcnow()) if result else datetime.utcnow()
        }
    )
    
    return stats

@router.get("/logs", response_model=LogsResponse, status_code=status.HTTP_200_OK)
async def get_application_logs(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    level: Optional[str] = Query(None, description="Filter logs by level (info, warning, error, debug)"),
    source: Optional[str] = Query(None, description="Filter logs by source/component"),
    start_date: Optional[datetime] = Query(None, description="Start date for logs"),
    end_date: Optional[datetime] = Query(None, description="End date for logs"),
    limit: int = Query(100, ge=10, le=1000, description="Maximum number of logs to return"),
    skip: int = Query(0, ge=0, description="Number of logs to skip for pagination")
):
    """
    Access application logs for troubleshooting.
    Returns filtered logs with pagination support.
    Only accessible to administrators.
    """
    # Build the filter query
    filter_query = {}
    
    if level:
        filter_query["level"] = level
    
    if source:
        filter_query["source"] = source
    
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        filter_query["timestamp"] = date_filter
    
    # Get levels count for statistics
    levels_pipeline = [
        {"$match": filter_query},
        {"$group": {
            "_id": "$level",
            "count": {"$sum": 1}
        }}
    ]
    
    levels_result = await logs_collection.aggregate(levels_pipeline).to_list(length=10)
    levels_count = {item["_id"]: item["count"] for item in levels_result}
    
    # Get total count for pagination
    total_count = await logs_collection.count_documents(filter_query)
    
    # Get the logs with pagination
    cursor = logs_collection.find(filter_query)
    cursor = cursor.sort("timestamp", -1)  # Sort by newest first
    cursor = cursor.skip(skip).limit(limit)
    
    logs = await cursor.to_list(length=limit)
    
    # Construct the response
    response = LogsResponse(
        logs=logs,
        total_count=total_count,
        levels_count=levels_count
    )
    
    return response 

@router.delete("/cleanup/audio-uploads", status_code=status.HTTP_200_OK)
async def cleanup_audio_uploads(
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Delete all files and subdirectories inside the audio uploads folder.
    Folder path: Backend/audio_uploads
    Only accessible to administrators.
    """
    # Resolve path to Backend/audio_uploads relative to this file (Backend/api/admin.py)
    base_dir = os.path.dirname(os.path.dirname(__file__))  # -> Backend
    upload_dir = os.path.join(base_dir, "audio_uploads")

    if not os.path.isdir(upload_dir):
        return {
            "status": "success",
            "detail": "audio_uploads directory does not exist",
            "deleted_files": 0,
            "deleted_dirs": 0,
            "deleted_bytes": 0,
            "errors": []
        }

    def _cleanup_sync():
        deleted_files = 0
        deleted_dirs = 0
        deleted_bytes = 0
        errors: List[Dict[str, Any]] = []

        try:
            with os.scandir(upload_dir) as it:
                for entry in it:
                    path = entry.path
                    try:
                        if entry.is_file() or entry.is_symlink():
                            try:
                                deleted_bytes += os.path.getsize(path)
                            except Exception:
                                pass
                            os.remove(path)
                            deleted_files += 1
                        elif entry.is_dir():
                            # Pre-calculate size of directory contents
                            for root, _, files in os.walk(path):
                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    try:
                                        deleted_bytes += os.path.getsize(fpath)
                                    except Exception:
                                        pass
                            shutil.rmtree(path)
                            deleted_dirs += 1
                    except Exception as e:
                        errors.append({"path": path, "error": str(e)})
        except Exception as e:
            # Scandir failure (permissions, etc.)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to scan directory: {str(e)}")

        return deleted_files, deleted_dirs, deleted_bytes, errors

    # Run potentially blocking file operations off the event loop
    loop = asyncio.get_event_loop()
    deleted_files, deleted_dirs, deleted_bytes, errors = await loop.run_in_executor(None, _cleanup_sync)

    detail_msg = "Cleanup completed"
    if errors:
        detail_msg += f" with {len(errors)} errors (likely locked files)"

    return {
        "status": "success",
        "detail": detail_msg,
        "deleted_files": deleted_files,
        "deleted_dirs": deleted_dirs,
        "deleted_bytes": deleted_bytes,
        "errors": errors,
    }