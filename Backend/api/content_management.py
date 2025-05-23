from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from pydantic import HttpUrl # Import HttpUrl

from services.auth import get_current_user, requires_role
from services.database import (
    podcasts_collection,
    transcripts_collection,
    uploads_collection,
    featured_content_collection
)
from models.content import (
    Podcast,
    PodcastsResponse,
    Transcript,
    TranscriptsResponse,
    Upload,
    UploadsResponse,
    FeaturedContent,
    FeaturedContentResponse,
    PodcastBase, # Import PodcastBase for update model
    TranscriptBase # Import TranscriptBase for update model
)
from utils.logging import log_info, log_error

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

class TranscriptUpdate(TranscriptBase):
    podcast_id: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    is_edited: Optional[bool] = None
    is_published: Optional[bool] = None
    segments: Optional[List[Dict[str, Any]]] = None
    confidence_score: Optional[float] = None
    word_count: Optional[int] = None

# Helper functions
def sanitize_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB ObjectId to string and handle date formatting."""
    if not doc:
        return {}
    
    # Convert ObjectId to string
    doc["id"] = str(doc.pop("_id")) if "_id" in doc else None
    
    return doc

# Podcasts Management
@router.get("/podcasts", response_model=PodcastsResponse, status_code=status.HTTP_200_OK)
async def list_podcasts(
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

@router.get("/podcasts/{podcast_id}", response_model=Podcast, status_code=status.HTTP_200_OK)
async def get_podcast_details(
    podcast_id: str = Path(..., description="Podcast ID")
):
    """
    Get detailed information about a specific podcast.
    """
    try:
        obj_id = ObjectId(podcast_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid podcast ID format"
        )
    
    podcast = await podcasts_collection.find_one({"_id": obj_id})
    
    if not podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Podcast with ID {podcast_id} not found"
        )
    
    log_info(
        f"Viewed podcast details. Podcast ID: {podcast_id}",
        "content_management",
        {"podcast_id": podcast_id}
    )
    
    return sanitize_mongo_doc(podcast)

@router.put("/podcasts/{podcast_id}", response_model=Podcast, status_code=status.HTTP_200_OK)
async def update_podcast(
    update_data: PodcastUpdate,
    podcast_id: str = Path(..., description="Podcast ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Update details of a specific podcast.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(podcast_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid podcast ID format"
        )
    
    existing_podcast = await podcasts_collection.find_one({"_id": obj_id})
    if not existing_podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Podcast with ID {podcast_id} not found"
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
        f"Admin updated podcast. Podcast ID: {podcast_id}, Changes: {update_dict}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "podcast_id": podcast_id}
    )
    
    return sanitize_mongo_doc(updated_podcast)

@router.delete("/podcasts/{podcast_id}", status_code=status.HTTP_200_OK)
async def delete_podcast(
    podcast_id: str = Path(..., description="Podcast ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Permanently delete a podcast from the system.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(podcast_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid podcast ID format"
        )
    
    existing_podcast = await podcasts_collection.find_one({"_id": obj_id})
    if not existing_podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Podcast with ID {podcast_id} not found"
        )
    
    await podcasts_collection.delete_one({"_id": obj_id})
    
    log_info(
        f"Admin deleted podcast. Podcast ID: {podcast_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "podcast_id": podcast_id}
    )
    
    return {"status": "success", "detail": f"Podcast {podcast_id} has been permanently deleted"}

# Transcripts Management
@router.get("/transcripts", response_model=TranscriptsResponse, status_code=status.HTTP_200_OK)
async def list_transcripts(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    podcast_id: Optional[str] = Query(None, description="Filter by podcast ID"),
    language: Optional[str] = Query(None, description="Filter by language"),
    is_edited: Optional[bool] = Query(None, description="Filter by edited status"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
    content_search: Optional[str] = Query(None, description="Search in transcript content")
):
    """
    List and filter transcripts with pagination.
    Only accessible to administrators.
    """
    # Build the filter query
    filter_query = {}
    
    if podcast_id:
        try:
            filter_query["podcast_id"] = podcast_id
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid podcast ID format"
            )
    
    if language:
        filter_query["language"] = language
    
    if is_edited is not None:
        filter_query["is_edited"] = is_edited
    
    if is_published is not None:
        filter_query["is_published"] = is_published
    
    if content_search:
        filter_query["content"] = {"$regex": content_search, "$options": "i"}
    
    # Get total count for pagination
    total_count = await transcripts_collection.count_documents(filter_query)
    
    # Calculate skip for pagination
    skip = (page - 1) * limit
    
    # Get transcripts with pagination and sorting
    cursor = transcripts_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    
    transcripts = await cursor.to_list(length=limit)
    
    # Convert MongoDB documents to Pydantic models
    sanitized_transcripts = [sanitize_mongo_doc(transcript) for transcript in transcripts]
    
    log_info(
        f"Admin listed transcripts. Filters: {filter_query}, Total: {total_count}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "page": page, "limit": limit}
    )
    
    return TranscriptsResponse(
        transcripts=sanitized_transcripts,
        total_count=total_count,
        page=page,
        limit=limit
    )

@router.get("/transcripts/{transcript_id}", response_model=Transcript, status_code=status.HTTP_200_OK)
async def get_transcript_details(
    transcript_id: str = Path(..., description="Transcript ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Get detailed information about a specific transcript.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(transcript_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid transcript ID format"
        )
    
    transcript = await transcripts_collection.find_one({"_id": obj_id})
    
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript with ID {transcript_id} not found"
        )
    
    log_info(
        f"Admin viewed transcript details. Transcript ID: {transcript_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "transcript_id": transcript_id}
    )
    
    return sanitize_mongo_doc(transcript)

@router.put("/transcripts/{transcript_id}", response_model=Transcript, status_code=status.HTTP_200_OK)
async def update_transcript(
    update_data: TranscriptUpdate,
    transcript_id: str = Path(..., description="Transcript ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Update details of a specific transcript.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(transcript_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid transcript ID format"
        )
    
    existing_transcript = await transcripts_collection.find_one({"_id": obj_id})
    if not existing_transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript with ID {transcript_id} not found"
        )
    
    update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
    
    if not update_dict:
        return sanitize_mongo_doc(existing_transcript)
    
    update_dict["updated_at"] = datetime.utcnow()
    
    await transcripts_collection.update_one(
        {"_id": obj_id},
        {"$set": update_dict}
    )
    
    updated_transcript = await transcripts_collection.find_one({"_id": obj_id})
    
    log_info(
        f"Admin updated transcript. Transcript ID: {transcript_id}, Changes: {update_dict}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "transcript_id": transcript_id}
    )
    
    return sanitize_mongo_doc(updated_transcript)

@router.delete("/transcripts/{transcript_id}", status_code=status.HTTP_200_OK)
async def delete_transcript(
    transcript_id: str = Path(..., description="Transcript ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Permanently delete a transcript from the system.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(transcript_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid transcript ID format"
        )
    
    existing_transcript = await transcripts_collection.find_one({"_id": obj_id})
    if not existing_transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript with ID {transcript_id} not found"
        )
    
    await transcripts_collection.delete_one({"_id": obj_id})
    
    log_info(
        f"Admin deleted transcript. Transcript ID: {transcript_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "transcript_id": transcript_id}
    )
    
    return {"status": "success", "detail": f"Transcript {transcript_id} has been permanently deleted"}

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

# Featured Content Management
@router.get("/featured-content", response_model=FeaturedContentResponse, status_code=status.HTTP_200_OK)
async def list_featured_content(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("priority", description="Field to sort by"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    title_search: Optional[str] = Query(None, description="Search in title")
):
    """
    List and filter featured content items with pagination.
    Only accessible to administrators.
    """
    # Build the filter query
    filter_query = {}
    
    if is_active is not None:
        filter_query["is_active"] = is_active
    
    if content_type:
        filter_query["content_type"] = content_type
    
    if title_search:
        filter_query["title"] = {"$regex": title_search, "$options": "i"}
    
    # Get total count for pagination
    total_count = await featured_content_collection.count_documents(filter_query)
    
    # Calculate skip for pagination
    skip = (page - 1) * limit
    
    # Get featured content with pagination and sorting
    cursor = featured_content_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    
    featured_items = await cursor.to_list(length=limit)
    
    # Convert MongoDB documents to Pydantic models
    sanitized_items = [sanitize_mongo_doc(item) for item in featured_items]
    
    log_info(
        f"Admin listed featured content. Filters: {filter_query}, Total: {total_count}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "page": page, "limit": limit}
    )
    
    return FeaturedContentResponse(
        featured_items=sanitized_items,
        total_count=total_count,
        page=page,
        limit=limit
    )

@router.get("/featured-content/{content_id}", response_model=FeaturedContent, status_code=status.HTTP_200_OK)
async def get_featured_content_details(
    content_id: str = Path(..., description="Featured content ID"),
    current_user: Dict[str, Any] = Depends(requires_role("admin"))
):
    """
    Get detailed information about a specific featured content item.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(content_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid featured content ID format"
        )
    
    content_item = await featured_content_collection.find_one({"_id": obj_id})
    
    if not content_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Featured content with ID {content_id} not found"
        )
    
    log_info(
        f"Admin viewed featured content details. Content ID: {content_id}",
        "content_management",
        {"admin_id": str(current_user["_id"]), "content_id": content_id}
    )
    
    return sanitize_mongo_doc(content_item)
