from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from pydantic import HttpUrl # Import HttpUrl

from services.auth import requires_role
from services.database import (
    podcasts_collection,
    uploads_collection,
)
from models.content import (
    Podcast,
    PodcastsResponse,
    Upload,
    UploadsResponse,
    PodcastBase, # Import PodcastBase for update model
)
from utils.logging import log_info

router = APIRouter()

# Pydantic models for update operations
class PodcastUpdate(PodcastBase):
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    audio_url: Optional[HttpUrl] = None
    duration_seconds: Optional[float] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    language: Optional[str] = None
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    average_rating: Optional[float] = None
    transcription_status: Optional[str] = None # Add transcription_status for updates

# Helper functions
def sanitize_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB ObjectId to string and handle date formatting."""
    if not doc:
        return {}
    
    # Convert ObjectId to string
    doc["id"] = str(doc.pop("_id")) if "_id" in doc else None
    
    return doc

# Podcasts Management
@router.get("/audios", response_model=PodcastsResponse, status_code=status.HTTP_200_OK)
async def list_audios(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    title_search: Optional[str] = Query(None, description="Search in podcast title"),
    author: Optional[str] = Query(None, description="Filter by author"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    language: Optional[str] = Query(None, description="Filter by language"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured status"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
    transcription_status: Optional[str] = Query(None, description="Filter by transcription status")
):
    """
    List and filter podcasts with pagination.
    """
    # Build the filter query
    filter_query = {}
    
    if title_search:
        filter_query["title"] = {"$regex": title_search, "$options": "i"}
    
    if author:
        filter_query["author"] = {"$regex": author, "$options": "i"}
    
    if tag:
        filter_query["tags"] = tag
    
    if language:
        filter_query["language"] = language
    
    if is_featured is not None:
        filter_query["is_featured"] = is_featured
    
    if is_published is not None:
        filter_query["is_published"] = is_published
    
    if transcription_status:
        filter_query["transcription_status"] = transcription_status
    
    # Get total count for pagination
    total_count = await podcasts_collection.count_documents(filter_query)
    
    # Calculate skip for pagination
    skip = (page - 1) * limit
    
    # Get podcasts with pagination and sorting
    cursor = podcasts_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    
    podcasts = await cursor.to_list(length=limit)
    # Convert MongoDB documents to Pydantic models
    sanitized_podcasts = [sanitize_mongo_doc(podcast) for podcast in podcasts]
    
    log_info(
        f"Listed podcasts. Filters: {filter_query}, Total: {total_count}",
        "content_management",
        {"page": page, "limit": limit}
    )
    
    return PodcastsResponse(
        podcasts=sanitized_podcasts,
        total_count=total_count,
        page=page,
        limit=limit
    )

@router.get("/audios/{audio_id}", response_model=Podcast, status_code=status.HTTP_200_OK)
async def get_audio_details(
    audio_id: str = Path(..., description="Audio ID")
):
    """
    Get detailed information about a specific podcast.
    """
    try:
        obj_id = ObjectId(audio_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio ID format"
        )
    
    podcast = await podcasts_collection.find_one({"_id": obj_id})
    
    if not podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio with ID {audio_id} not found"
        )
    
    log_info(
        f"Viewed audio details. Audio ID: {audio_id}",
        "content_management",
        {"audio_id": audio_id}
    )
    
    return sanitize_mongo_doc(podcast)

@router.put("/audios/{audio_id}", response_model=Podcast, status_code=status.HTTP_200_OK)
async def update_audio(
    update_data: PodcastUpdate,
    audio_id: str = Path(..., description="Audio ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Update details of a specific audio.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(audio_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio ID format"
        )
    
    existing_podcast = await podcasts_collection.find_one({"_id": obj_id})
    if not existing_podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio with ID {audio_id} not found"
        )
    
    update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
    
    if not update_dict:
        return sanitize_mongo_doc(existing_podcast)
    
    update_dict["updated_at"] = datetime.utcnow()
    
    await podcasts_collection.update_one(
        {"_id": obj_id},
        {"$set": update_dict}
    )
    
    updated_podcast = await podcasts_collection.find_one({"_id": obj_id})
    
    log_info(
        f"Admin updated podcast. Podcast ID: {audio_id}, Changes: {update_dict}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "podcast_id": audio_id}
    )
    
    return sanitize_mongo_doc(updated_podcast)

@router.delete("/audios/{audio_id}", status_code=status.HTTP_200_OK)
async def delete_audio(
    audio_id: str = Path(..., description="Audio ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Permanently delete an audio from the system.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(audio_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio ID format"
        )
    
    existing_podcast = await podcasts_collection.find_one({"_id": obj_id})
    if not existing_podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio with ID {audio_id} not found"
        )
    
    await podcasts_collection.delete_one({"_id": obj_id})
    
    log_info(
        f"Admin deleted audio. Audio ID: {audio_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "audio_id": audio_id}
    )
    
    return {"status": "success", "detail": f"Audio {audio_id} has been permanently deleted"}

# Uploads Management
@router.get("/uploads", response_model=UploadsResponse, status_code=status.HTTP_200_OK)
async def list_uploads(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    file_type: Optional[str] = Query(None, description="Filter by file type"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    filename_search: Optional[str] = Query(None, description="Search in filename")
):
    """
    List and filter user uploads with pagination.
    Only accessible to administrators.
    """
    # Build the filter query
    filter_query = {}
    
    if user_id:
        try:
            filter_query["user_id"] = user_id
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
    
    if file_type:
        filter_query["file_type"] = file_type
    
    if status:
        filter_query["status"] = status
    
    if filename_search:
        filter_query["file_name"] = {"$regex": filename_search, "$options": "i"}
    
    # Get total count for pagination
    total_count = await uploads_collection.count_documents(filter_query)
    
    # Calculate skip for pagination
    skip = (page - 1) * limit
    
    # Get uploads with pagination and sorting
    cursor = uploads_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    
    uploads = await cursor.to_list(length=limit)
    
    # Convert MongoDB documents to Pydantic models
    sanitized_uploads = [sanitize_mongo_doc(upload) for upload in uploads]
    
    log_info(
        f"Admin listed uploads. Filters: {filter_query}, Total: {total_count}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "page": page, "limit": limit}
    )
    
    return UploadsResponse(
        uploads=sanitized_uploads,
        total_count=total_count,
        page=page,
        limit=limit
    )

@router.get("/uploads/{upload_id}", response_model=Upload, status_code=status.HTTP_200_OK)
async def get_upload_details(
    upload_id: str = Path(..., description="Upload ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Get detailed information about a specific upload.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(upload_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid upload ID format"
        )
    
    upload = await uploads_collection.find_one({"_id": obj_id})
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload with ID {upload_id} not found"
        )
    
    log_info(
        f"Admin viewed upload details. Upload ID: {upload_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "upload_id": upload_id}
    )
    
    return sanitize_mongo_doc(upload)
