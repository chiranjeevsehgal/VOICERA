from datetime import datetime
import asyncio
import hashlib
from typing import Dict, List, Any, Optional
from bson import ObjectId
import json

from services.database import (
    podcasts_collection,
    transcripts_collection, 
    uploads_collection,
    featured_content_collection
)

from utils.logging import log_info, log_error, log_debug

async def track_upload(
    user_id: str,
    file_name: str,
    file_path: str,
    file_type: str,
    file_size: int,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Track a file upload in the uploads collection.
    
    Args:
        user_id: ID of the user who uploaded the file
        file_name: Original filename
        file_path: Path to the file on the server
        file_type: Type of file (audio, image, document)
        file_size: Size of the file in bytes
        metadata: Additional metadata about the file
        
    Returns:
        ID of the created upload record
    """
    if metadata is None:
        metadata = {}
    
    log_info(
        f"Tracking upload for user {user_id}",
        "content_tracker",
        {
            "user_id": user_id,
            "file_name": file_name,
            "metadata": json.loads(json.dumps(metadata, default=str)),
        },
    )
    
    upload_data = {
        "user_id": user_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_type": file_type,
        "file_size": file_size,
        "metadata": metadata,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    try:
        result = await uploads_collection.insert_one(upload_data)
        upload_id = str(result.inserted_id)
        
        log_info(
            f"Tracked upload: {file_name} for user {user_id}",
            "content_tracker",
            {"upload_id": upload_id, "user_id": user_id, "file_name": file_name}
        )
        
        return upload_id
    except Exception as e:
        log_error(
            f"Failed to track upload: {str(e)}",
            "content_tracker",
            {"user_id": user_id, "file_name": file_name, "error": str(e)}
        )
        return None

async def update_upload_status(
    upload_id: str, 
    status: str,
    processed_at: Optional[datetime] = None,
    podcast_id: Optional[str] = None,
    error_message: Optional[str] = None,
    supabase_url: Optional[str] = None
) -> bool:
    """
    Update the status of an upload.
    
    Args:
        upload_id: ID of the upload to update
        status: New status (pending, processing, completed, failed)
        processed_at: When processing completed (for completed status)
        podcast_id: ID of the podcast created from this upload
        error_message: Error message (for failed status)
        supabase_url: URL of the file in Supabase storage
        
    Returns:
        True if update was successful, False otherwise
    """
    try:
        log_debug(
            f"Updating upload {upload_id} with status {status}",
            "content_tracker",
            {"upload_id": upload_id, "status": status, "supabase_url": supabase_url},
        )
        
        # First validate the upload exists
        upload = await uploads_collection.find_one({"_id": ObjectId(upload_id)})
        if not upload:
            error_msg = f"Upload not found: {upload_id}"
            log_error(
                error_msg,
                "content_tracker",
                {"upload_id": upload_id}
            )
            log_debug(
                error_msg,
                "content_tracker",
                {"upload_id": upload_id},
            )
            return False

        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        
        if processed_at:
            update_data["processed_at"] = processed_at
            
        if podcast_id:
            update_data["podcast_id"] = podcast_id
            
        if error_message:
            update_data["error_message"] = error_message
            
        if supabase_url:
            update_data["supabase_url"] = supabase_url
            update_data["file_url"] = supabase_url  # Ensure file_url is set
            log_debug(
                "Setting file_url for upload",
                "content_tracker",
                {"upload_id": upload_id, "file_url": supabase_url},
            )
        
        result = await uploads_collection.update_one(
            {"_id": ObjectId(upload_id)},
            {"$set": update_data}
        )

        # Log the update details
        log_msg = f"Updated upload {upload_id} to status {status}"
        log_info(
            log_msg,
            "content_tracker",
            {
                "upload_id": upload_id,
                "status": status,
                "supabase_url_set": supabase_url is not None,
                "modified_count": result.modified_count,
                "update_data": update_data
            }
        )
        log_debug(
            log_msg,
            "content_tracker",
            {"upload_id": upload_id, "modified_count": result.modified_count},
        )
        
        if result.modified_count > 0:
            log_info(
                f"Updated upload status to {status}",
                "content_tracker",
                {"upload_id": upload_id, "status": status}
            )
            return True
        else:
            log_error(
                f"Failed to update upload status: no matching document",
                "content_tracker",
                {"upload_id": upload_id, "status": status}
            )
            return False
    except Exception as e:
        log_error(
            f"Error updating upload status: {str(e)}",
            "content_tracker",
            {"upload_id": upload_id, "status": status, "error": str(e)}
        )
        return False

async def create_podcast(
    title: str,
    description: str,
    raw_audio_url: str,
    duration_seconds: float,
    author: str,
    image_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    language: str = "en",
    is_featured: bool = False,
    is_published: bool = True,
    upload_id: Optional[str] = None,
    embedded_audio_url: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """
    Create a podcast entry in the podcasts collection.
    
    Args:
        title: Podcast title
        description: Podcast description
        raw_audio_url: URL to the audio file in Supabase
        duration_seconds: Duration of the audio in seconds
        author: Author/creator of the podcast
        image_url: Optional URL to cover image
        tags: Optional list of tags
        language: Language code (default: "en")
        is_featured: Whether this podcast is featured
        is_published: Whether this podcast is published
        upload_id: ID of the associated upload record
        embedded_audio_url: URL of the embedded file in Supabase storage
        
    Returns:
        ID of the created podcast
    """
    if tags is None:
        tags = []
    
    now = datetime.utcnow()

    # Creating file id from raw_audio_url to track pinecone chunks
    file_key_src = (raw_audio_url or "")
    file_id = hashlib.sha1(file_key_src.encode("utf-8")).hexdigest()[:12] if file_key_src else None
    
    podcast_data = {
        "title": title,
        "raw_audio_url": raw_audio_url,
        "embedded_audio_url": embedded_audio_url,
        "file_id": file_id,
        "duration_seconds": duration_seconds,
        "author": author,
        "published_date": now,
        "language": language,
        "created_at": now,
        "updated_at": now,
        "is_published": is_published
    }
    
    if upload_id:
        podcast_data["upload_id"] = upload_id
        
    # Do not persist supabase_url separately; audio_url will always point to the final embedded URL
    # Store user_id if provided (as ObjectId when valid)
    if user_id:
        try:
            podcast_data["user_id"] = ObjectId(user_id)
        except Exception:
            podcast_data["user_id"] = user_id
    
    try:
        result = await podcasts_collection.insert_one(podcast_data)
        podcast_id = str(result.inserted_id)
        
        # If there's an upload ID, update the upload record with the podcast ID
        if upload_id:
            await update_upload_status(
                upload_id=upload_id,
                status="completed",
                processed_at=now,
                podcast_id=podcast_id
            )
        
        log_info(
            f"Created podcast: {title}",
            "content_tracker",
            {"podcast_id": podcast_id, "title": title, "upload_id": upload_id}
        )
        
        return podcast_id
    except Exception as e:
        log_error(
            f"Failed to create podcast: {str(e)}",
            "content_tracker",
            {"title": title, "error": str(e)}
        )
        return None

async def update_podcast_transcription_status(
    podcast_id: str,
    status: str,
    transcript_id: Optional[str] = None
) -> bool:
    """
    Update the transcription status of a podcast.
    
    Args:
        podcast_id: ID of the podcast
        status: Transcription status (pending, in_progress, completed, failed)
        transcript_id: ID of the associated transcript
        
    Returns:
        True if update was successful, False otherwise
    """
    try:
        update_data = {
            "transcription_status": status,
            "updated_at": datetime.utcnow()
        }
        
        if transcript_id:
            update_data["transcript_id"] = transcript_id
        
        result = await podcasts_collection.update_one(
            {"_id": ObjectId(podcast_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            log_info(
                f"Updated podcast transcription status to {status}",
                "content_tracker",
                {"podcast_id": podcast_id, "status": status, "transcript_id": transcript_id}
            )
            return True
        else:
            log_error(
                f"Failed to update podcast transcription status: no matching document",
                "content_tracker",
                {"podcast_id": podcast_id, "status": status}
            )
            return False
    except Exception as e:
        log_error(
            f"Error updating podcast transcription status: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "status": status, "error": str(e)}
        )
        return False

async def create_transcript(
    podcast_id: str,
    content: str,
    language: str = "en",
    is_edited: bool = False,
    is_published: bool = True,
    segments: Optional[List[Dict[str, Any]]] = None,
    confidence_score: Optional[float] = None,
) -> str:
    """
    Create a transcript entry in the transcripts collection.
    
    Args:
        podcast_id: ID of the associated podcast
        content: Full transcript text
        language: Language code
        is_edited: Whether this transcript has been manually edited
        is_published: Whether this transcript is published
        segments: Optional time-aligned transcript segments
        confidence_score: Optional confidence score from the transcription service
        
    Returns:
        ID of the created transcript
    """
    now = datetime.utcnow()
    
    # Calculate word count
    words = content.split() if content else []
    word_count = len(words)
    
    transcript_data = {
        "podcast_id": podcast_id,
        "content": content,
        "language": language,
        "is_edited": is_edited,
        "created_at": now,
        "updated_at": now,
        "segments": segments,
        "confidence_score": confidence_score,
        "word_count": word_count,
        "is_published": is_published
    }
    
    try:
        result = await transcripts_collection.insert_one(transcript_data)
        transcript_id = str(result.inserted_id)
        
        # Update the podcast with the completed transcription status
        await update_podcast_transcription_status(
            podcast_id=podcast_id,
            status="completed",
            transcript_id=transcript_id
        )
        
        log_info(
            f"Created transcript for podcast {podcast_id}",
            "content_tracker",
            {"transcript_id": transcript_id, "podcast_id": podcast_id, "word_count": word_count}
        )
        
        return transcript_id
    except Exception as e:
        # Update podcast to failed transcription status
        await update_podcast_transcription_status(
            podcast_id=podcast_id,
            status="failed"
        )
        
        log_error(
            f"Failed to create transcript: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "error": str(e)}
        )
        return None

async def feature_podcast(
    podcast_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: int = 0,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> str:
    """
    Feature a podcast on the platform.
    
    Args:
        podcast_id: ID of the podcast to feature
        title: Optional custom title for the featured content
        description: Optional custom description
        priority: Priority level (higher = more prominent)
        start_date: When to start featuring this content
        end_date: When to stop featuring this content
        
    Returns:
        ID of the created featured content entry
    """
    try:
        # Get the podcast details
        podcast = await podcasts_collection.find_one({"_id": ObjectId(podcast_id)})
        
        if not podcast:
            log_error(
                f"Failed to feature podcast: podcast not found",
                "content_tracker",
                {"podcast_id": podcast_id}
            )
            return None
        
        now = datetime.utcnow()
        
        # Create featured content entry
        featured_data = {
            "title": title or podcast.get("title", "Featured Podcast"),
            "description": description or podcast.get("description", ""),
            "image_url": podcast.get("image_url", ""),
            "target_url": podcast.get("audio_url", ""),
            "content_type": "podcast",
            "priority": priority,
            "created_at": now,
            "updated_at": now,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True,
            "click_count": 0,
            "view_count": 0,
            "podcast_id": podcast_id
        }
        
        result = await featured_content_collection.insert_one(featured_data)
        featured_id = str(result.inserted_id)
        
        # Update the podcast to be featured
        await podcasts_collection.update_one(
            {"_id": ObjectId(podcast_id)},
            {"$set": {"is_featured": True, "updated_at": now}}
        )
        
        log_info(
            f"Featured podcast {podcast_id}",
            "content_tracker",
            {"podcast_id": podcast_id, "featured_id": featured_id}
        )
        
        return featured_id
    except Exception as e:
        log_error(
            f"Failed to feature podcast: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "error": str(e)}
        )
        return None

def sync_track_upload(
    user_id: str,
    file_name: str,
    file_path: str,
    file_type: str,
    file_size: int,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Synchronous wrapper for track_upload"""
    try:
        return asyncio.run(
            track_upload(
                user_id=user_id,
                file_name=file_name,
                file_path=file_path,
                file_type=file_type,
                file_size=file_size,
                metadata=metadata
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_track_upload: {str(e)}",
            "content_tracker",
            {"user_id": user_id, "file_name": file_name, "error": str(e)}
        )
        return None

def sync_update_upload_status(
    upload_id: str, 
    status: str,
    processed_at: Optional[datetime] = None,
    podcast_id: Optional[str] = None,
    error_message: Optional[str] = None,
    supabase_url: Optional[str] = None
) -> bool:
    """Synchronous wrapper for update_upload_status"""
    try:
        return asyncio.run(
            update_upload_status(
                upload_id=upload_id,
                status=status,
                processed_at=processed_at,
                podcast_id=podcast_id,
                error_message=error_message,
                supabase_url=supabase_url
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_update_upload_status: {str(e)}",
            "content_tracker",
            {"upload_id": upload_id, "status": status, "error": str(e)}
        )
        return False

def sync_create_podcast(
    title: str,
    description: str,
    raw_audio_url: str,
    duration_seconds: float,
    author: str,
    image_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    language: str = "en",
    is_featured: bool = False,
    is_published: bool = True,
    upload_id: Optional[str] = None,
    embedded_audio_url: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """Synchronous wrapper for create_podcast"""
    try:
        return asyncio.run(
            create_podcast(
                title=title,
                description=description,
                raw_audio_url=raw_audio_url,
                duration_seconds=duration_seconds,
                author=author,
                image_url=image_url,
                tags=tags,
                language=language,
                is_featured=is_featured,
                is_published=is_published,
                upload_id=upload_id,
                embedded_audio_url=embedded_audio_url,
                user_id=user_id
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_create_podcast: {str(e)}",
            "content_tracker",
            {"title": title, "error": str(e)}
        )
        return None

def sync_update_podcast_transcription_status(
    podcast_id: str,
    status: str,
    transcript_id: Optional[str] = None
) -> bool:
    """Synchronous wrapper for update_podcast_transcription_status"""
    try:
        return asyncio.run(
            update_podcast_transcription_status(
                podcast_id=podcast_id,
                status=status,
                transcript_id=transcript_id
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_update_podcast_transcription_status: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "status": status, "error": str(e)}
        )
        return False

def sync_create_transcript(
    podcast_id: str,
    content: str,
    language: str = "en",
    is_edited: bool = False,
    is_published: bool = True,
    segments: Optional[List[Dict[str, Any]]] = None,
    confidence_score: Optional[float] = None,
) -> str:
    """Synchronous wrapper for create_transcript"""
    try:
        return asyncio.run(
            create_transcript(
                podcast_id=podcast_id,
                content=content,
                language=language,
                is_edited=is_edited,
                is_published=is_published,
                segments=segments,
                confidence_score=confidence_score
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_create_transcript: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "error": str(e)}
        )
        return None

def sync_feature_podcast(
    podcast_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: int = 0,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> str:
    """Synchronous wrapper for feature_podcast"""
    try:
        return asyncio.run(
            feature_podcast(
                podcast_id=podcast_id,
                title=title,
                description=description,
                priority=priority,
                start_date=start_date,
                end_date=end_date
            )
        )
    except Exception as e:
        log_error(
            f"Error in sync_feature_podcast: {str(e)}",
            "content_tracker",
            {"podcast_id": podcast_id, "error": str(e)}
        )
        return None

async def process_transcription_data(transcription_data: Dict[str, Any], upload_data: Dict[str, Any], user_id: str) -> None:
    """
    Process transcription data to create podcast and transcript records.
    
    Args:
        transcription_data: Data from the transcription service
        upload_data: Data about the uploaded file
        user_id: ID of the user who uploaded the file
    """
    try:
        # Extract needed data from transcription
        results = transcription_data.get("results", {})
        channels = results.get("channels", [{}])[0]
        alternatives = channels.get("alternatives", [{}])[0]
        transcript = alternatives.get("transcript", "")
        
        # Create a podcast record
        podcast_id = await create_podcast(
            title=upload_data.get("file_name", "Untitled Podcast"),
            description=f"Uploaded on {datetime.utcnow().strftime('%Y-%m-%d')}",
            embedded_audio_url=upload_data.get("file_url", ""),
            duration_seconds=float(results.get("audio_duration", 0)),
            author=user_id,
            tags=["uploaded"],
            upload_id=upload_data.get("upload_id"),
            user_id=user_id
        )
        
        if podcast_id:
            # Create a transcript record
            transcript_id = await create_transcript(
                podcast_id=podcast_id,
                content=transcript,
                language=results.get("language", "en"),
                segments=alternatives.get("words", []),
                confidence_score=alternatives.get("confidence")
            )
            
            # Feature new podcasts with auto-generated title from first few words
            title_preview = " ".join(transcript.split()[:5]) + "..."
            await feature_podcast(
                podcast_id=podcast_id,
                title=f"New Upload: {title_preview}",
                priority=5  # Medium priority
            )
    except Exception as e:
        log_error(
            f"Error processing transcription data: {str(e)}",
            "content_tracker",
            {"user_id": user_id, "error": str(e)}
        )
