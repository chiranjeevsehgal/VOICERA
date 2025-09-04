from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import hashlib
from pydantic import BaseModel, HttpUrl # Import BaseModel and HttpUrl

from services.auth import requires_role
from services.database import (
    podcasts_collection,
    uploads_collection,
    transcripts_collection,
    transcription_stats_collection,
)
from models.content import (
    Podcast,
    PodcastsResponse,
    Upload,
    UploadsResponse,
)
from utils.logging import log_info

router = APIRouter()

# Pydantic model for update operations (all fields optional for partial updates)
class PodcastUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    embedded_audio_url: Optional[HttpUrl] = None
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
    transcription_status: Optional[str] = None  # Add transcription_status for updates

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
    This will remove the audio from:
    - MongoDB collections: podcasts, transcripts, uploads, transcription_stats
    - Supabase buckets: audiofiles, audiofiles-embedded
    - Pinecone: all chunks associated with this audio
    
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(audio_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio ID format"
        )
    
    # Find the podcast to get file information for deletion
    existing_podcast = await podcasts_collection.find_one({"_id": obj_id})
    if not existing_podcast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio with ID {audio_id} not found"
        )
    
    deletion_summary = {
        "podcast_deleted": False,
        "transcripts_deleted": 0,
        "uploads_deleted": 0,
        "transcription_stats_deleted": 0,
        "supabase_files_deleted": [],
        "supabase_errors": [],
        "pinecone_deleted": False,
        "pinecone_error": None
    }
    
    # Step 1: Delete from MongoDB collections
    try:
        # Delete podcast
        await podcasts_collection.delete_one({"_id": obj_id})
        deletion_summary["podcast_deleted"] = True
        
        # Delete related transcripts - they may link by file_name or be orphaned (podcast_id: null)
        # Try multiple patterns to find related transcripts
        file_name = existing_podcast.get("title", "").replace(" ", "_")
        transcript_queries = []
        
        # Add query for exact audio_id match (if any transcripts use this)
        transcript_queries.append({"podcast_id": audio_id})
        
        # Add query for null podcast_id with matching user_id and timeframe
        user_id_str = str(existing_podcast.get("user_id", ""))
        created_at = existing_podcast.get("created_at")
        if user_id_str and created_at:
            # Find transcripts created around the same time (within 1 hour)
            from datetime import timedelta
            time_window_start = created_at - timedelta(hours=1)
            time_window_end = created_at + timedelta(hours=1)
            transcript_queries.append({
                "podcast_id": None,
                "created_at": {"$gte": time_window_start, "$lte": time_window_end}
            })
        
        transcript_delete_count = 0
        for query in transcript_queries:
            result = await transcripts_collection.delete_many(query)
            transcript_delete_count += result.deleted_count
        deletion_summary["transcripts_deleted"] = transcript_delete_count
        
        # Delete related uploads - match by file_name pattern or user_id + timeframe
        upload_queries = []
        if file_name:
            # Try to match by filename patterns
            upload_queries.append({"file_name": {"$regex": file_name.replace("_", ".*"), "$options": "i"}})
        
        # Match by user_id and creation timeframe
        if user_id_str and created_at:
            upload_queries.append({
                "user_id": user_id_str,
                "created_at": {"$gte": time_window_start, "$lte": time_window_end}
            })
        
        upload_delete_count = 0
        for query in upload_queries:
            result = await uploads_collection.delete_many(query)
            upload_delete_count += result.deleted_count
        deletion_summary["uploads_deleted"] = upload_delete_count
        
        # Delete related transcription stats - match by user_id (string) and timeframe
        stats_delete_count = 0
        if user_id_str and created_at:
            stats_result = await transcription_stats_collection.delete_many({
                "user_id": user_id_str,
                "timestamp": {"$gte": time_window_start, "$lte": time_window_end}
            })
            stats_delete_count = stats_result.deleted_count
        deletion_summary["transcription_stats_deleted"] = stats_delete_count
        
    except Exception as e:
        log_info(
            f"Error deleting from MongoDB collections for audio {audio_id}: {str(e)}",
            "content_management_error",
            {"admin_id": str(current_user["_id"]), "audio_id": audio_id, "error": str(e)}
        )
    
    # Step 2: Delete from Supabase buckets
    try:
        from services.supabase_service import delete_file_from_supabase
        
        # Extract file paths from URLs
        supabase_files_to_delete = []
        supabase_errors = []
        
        for url_field in ["raw_audio_url", "embedded_audio_url", "audio_url"]:
            url = existing_podcast.get(url_field, "")
            if url:
                try:
                    # Parse Supabase URL to extract bucket and file path
                    # Expected format: https://xxx.supabase.co/storage/v1/object/public/{bucket}/{path}
                    if "/storage/v1/object/public/" in url:
                        path_part = url.split("/storage/v1/object/public/", 1)[1]
                        if "?" in path_part:
                            path_part = path_part.split("?", 1)[0]  # Remove query params
                        
                        # Extract bucket name from URL and file path
                        path_segments = path_part.split("/", 1)
                        if len(path_segments) >= 2:
                            url_bucket = path_segments[0]
                            file_path = path_segments[1]
                        else:
                            # Fallback if path format is unexpected
                            import os
                            if url_field == "embedded_audio_url":
                                url_bucket = os.getenv("SUPABASE_BUCKET_EMBEDDED", "audiofiles-embedded")
                            else:
                                url_bucket = os.getenv("SUPABASE_BUCKET_ORIGINAL", "audiofiles")
                            file_path = path_part
                        
                        bucket_name = url_bucket
                        
                        # Delete file
                        delete_result = await delete_file_from_supabase(file_path, bucket_name)
                        if delete_result.get("success"):
                            supabase_files_to_delete.append(f"{bucket_name}/{file_path}")
                        else:
                            supabase_errors.append(f"Failed to delete {bucket_name}/{file_path}")
                except Exception as e:
                    supabase_errors.append(f"Error processing {url_field}: {str(e)}")
        
        deletion_summary["supabase_files_deleted"] = supabase_files_to_delete
        deletion_summary["supabase_errors"] = supabase_errors
        
    except Exception as e:
        deletion_summary["supabase_errors"] = [f"Supabase deletion error: {str(e)}"]
    
    # Step 3: Delete from Pinecone
    try:
        # Generate file_id from the audio filename or use a derived identifier
        file_name = existing_podcast.get("title", "").replace(" ", "_")
        if not file_name:
            # Extract from URL if available
            for url_field in ["raw_audio_url", "embedded_audio_url", "audio_url"]:
                url = existing_podcast.get(url_field, "")
                if url:
                    file_name = url.split("/")[-1].split("?")[0]
                    if "." in file_name:
                        file_name = file_name.rsplit(".", 1)[0]
                    break
        
        # Use the actual file_id from the podcast document (this is what Pinecone uses)
        from services.pinecone_service import delete_by_file_id
        file_ids_to_try = []
        
        # Generate file_id the same way it's created during indexing (SHA1 hash of URL)
        import hashlib
        
        # Primary: Generate file_id from raw_audio_url (matches content_tracker.py logic)
        raw_audio_url = existing_podcast.get("raw_audio_url", "")
        if raw_audio_url:
            podcast_file_id = hashlib.sha1(raw_audio_url.encode("utf-8")).hexdigest()[:12]
            file_ids_to_try.append(podcast_file_id)
            
        
        # Also try from embedded_audio_url if different
        embedded_audio_url = existing_podcast.get("embedded_audio_url", "")
        if embedded_audio_url and embedded_audio_url != raw_audio_url:
            embedded_file_id = hashlib.sha1(embedded_audio_url.encode("utf-8")).hexdigest()[:12]
            file_ids_to_try.append(embedded_file_id)
            
        
        # Also try audio_url if different from both above
        audio_url = existing_podcast.get("audio_url", "")
        if audio_url and audio_url not in [raw_audio_url, embedded_audio_url]:
            audio_file_id = hashlib.sha1(audio_url.encode("utf-8")).hexdigest()[:12]
            file_ids_to_try.append(audio_file_id)
            
        
        # Fallback: Generate file_ids using various heuristics
        file_ids_set = set()
        if file_name:
            file_ids_set.add(audio_id[:12])
            file_ids_set.add(file_name.replace(" ", "_")[:12])
            file_ids_set.add(f"{audio_id[:8]}_{audio_id[8:12]}")
        
        # Hash-based IDs derived from Supabase URLs
        url_candidates = []
        for url_field in ["raw_audio_url", "embedded_audio_url", "audio_url"]:
            u = existing_podcast.get(url_field, "")
            if u:
                url_candidates.append(u)
        for u in url_candidates:
            try:
                fid = hashlib.sha1(u.encode("utf-8")).hexdigest()[:12]
                file_ids_set.add(fid)
                # Also attempt without query params, if any
                if "?" in u:
                    u2 = u.split("?", 1)[0]
                    fid2 = hashlib.sha1(u2.encode("utf-8")).hexdigest()[:12]
                    file_ids_set.add(fid2)
            except Exception:
                pass
        
        # Add fallback IDs to the list
        file_ids_to_try.extend([fid for fid in file_ids_set if fid and fid not in file_ids_to_try])
        
        if file_ids_to_try:
            deleted_any = False
            for file_id in file_ids_to_try:
                try:
                    delete_result = await delete_by_file_id(file_id)
                    
                    if delete_result.get("deleted_count", 0) > 0:
                        deletion_summary["pinecone_deleted"] = True
                        deletion_summary["pinecone_vectors_deleted"] = delete_result.get("deleted_count", 0)
                        deleted_any = True
                        break
                    elif delete_result.get("success") and delete_result.get("error") is None:
                        # Success but 0 vectors - this is fine, continue to next file_id
                        continue
                except Exception as e:
                    continue
            
            if not deleted_any:
                deletion_summary["pinecone_error"] = f"No vectors found for any file_ids: {file_ids_to_try}"
        else:
            deletion_summary["pinecone_error"] = "Could not determine file_id candidates for Pinecone deletion"
            
    except Exception as e:
        deletion_summary["pinecone_error"] = f"Pinecone deletion error: {str(e)}"
    
    log_info(
        f"Admin deleted audio with comprehensive cleanup. Audio ID: {audio_id}",
        "content_management",
        {
            "admin_id": str(current_user["_id"]), 
            "audio_id": audio_id,
            "deletion_summary": deletion_summary
        }
    )
    
    return {
        "status": "success", 
    }

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
