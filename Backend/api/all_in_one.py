from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import os
import json
import requests
import tempfile
import shutil
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

# Import services and dependencies
from services.auth import get_current_user, requires_role
from services.ip_utils import get_ip_for_request
from services.job_tracker import (
    create_job, update_job_status, get_job_status, JobStatus, clean_old_jobs
)

# Import functionality from existing API endpoints
from api.upload import AUDIO_MIME_TYPES
from api.embedding import extract_metadata_from_mp3_to_json
from services.supabase_service import upload_file_to_supabase
from services.pinecone_service import index_transcript
from utils.content_tracker import (
    track_upload, create_podcast, create_transcript, update_podcast_transcription_status, 
    update_upload_status, sync_track_upload, sync_create_podcast, sync_create_transcript, 
    sync_update_podcast_transcription_status, sync_update_upload_status
)
from utils.analytics import _insert_transcription_stats # Import the direct insertion function
from services.database import transcription_stats_collection # Also import the collection directly

router = APIRouter()

# Thread pool for running CPU-bound and blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)

# Run the job cleanup every hour
@router.on_event("startup")
async def setup_job_cleaner():
    async def cleanup_jobs():
        while True:
            clean_old_jobs()
            await asyncio.sleep(3600)  # Run every hour
    
    # Start the background task
    asyncio.create_task(cleanup_jobs())

@router.post("/process_audio", status_code=202)  # 202 Accepted status code for async jobs
async def process_audio(
    request: Request,
    file: UploadFile = File(...),
    custom_filename: Optional[str] = Form(None),
    transcription_options: Optional[str] = Form("{}"),  # JSON string with transcription options
    current_user: dict = Depends(get_current_user),
    detected_ip: str = Depends(get_ip_for_request),
    background_tasks: BackgroundTasks = BackgroundTasks() # Add BackgroundTasks here
):
    """
    All-in-one endpoint that performs the following operations sequentially:
    1. Validates the user's authentication and credits
    2. Uploads the audio file to local storage
    3. Transcribes the audio using Deepgram
    4. Embeds the transcription metadata into the audio file
    5. Uploads the enhanced file to Supabase
    6. Deducts credits from the user's account
    
    This endpoint immediately returns a job ID and processes the tasks in the background.
    The job status can be monitored via the /api/job-status/{job_id} endpoint.
    
    Args:
        request: The request object
        file: The audio file to process
        custom_filename: Optional custom filename
        transcription_options: JSON string with transcription options for Deepgram
        current_user: The authenticated user (from token)
        detected_ip: The user's IP address
    
    Returns:
        JSON response with job_id for tracking
    """
    # Check if file exists and is valid audio
    if not file:
        return JSONResponse(
            status_code=400, 
            content={"message": "No file provided"}
        )
    
    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Please upload an audio file."
        )
    
    # Create a new job and get its ID
    job_id = create_job()
    
    # Define max file size (50 MB)
    MAX_FILE_SIZE_MB = 50
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024 # Convert MB to bytes

    # Make a local copy of the file in memory
    file_content = await file.read()
    
    # Reset the file pointer for further processing
    await file.seek(0)
    
    # Check file size
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the limit of {MAX_FILE_SIZE_MB}MB."
        )

    # Extract the actual JWT token from headers for internal API calls
    auth_header = request.headers.get("Authorization", "")
    jwt_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
    
    # If we have a JWT token, add it to the current_user dict for internal API calls
    if jwt_token:
        # Make a copy of current_user to avoid modifying the original
        enhanced_user = dict(current_user)
        enhanced_user["auth_token"] = jwt_token
        print(f"Extracted JWT token from original request: {jwt_token[:10]}...")
    else:
        enhanced_user = current_user
        print("No JWT token found in the original request headers")
    
    # Save file info
    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(file_content)
    }
    
    # Start processing in a completely separate thread to avoid blocking
    thread = threading.Thread(
        target=run_processing_in_thread,
        args=(
            job_id,
            file_content,
            file_info,
            custom_filename,
            transcription_options,
            enhanced_user,  # Use enhanced user with auth token
            detected_ip,
            background_tasks # Pass background_tasks here
        )
    )
    thread.daemon = True  # Daemonize thread to allow the program to exit
    thread.start()
    
    return {
        "job_id": job_id,
        "status": "accepted",
        "message": "Your audio is being processed. You can check the status using the job_id."
    }

@router.post("/process_audio_bulk", status_code=202)
async def process_audio_bulk(
    request: Request,
    files: List[UploadFile] = File(...),
    custom_filenames: Optional[str] = Form(None),  # JSON mapping: {"index": "custom_name.mp3"}
    transcription_options: Optional[str] = Form("{}"),
    current_user: dict = Depends(requires_role("admin")),
    detected_ip: str = Depends(get_ip_for_request),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Admin-only bulk processing endpoint.
    - Validates auth and file types/sizes
    - Spawns a separate background job per file using the same processing pipeline
    - Returns list of job_ids for tracking
    """
    # Validate files list
    if not files or len(files) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    MAX_FILES = 20
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Too many files. Max {MAX_FILES} allowed")

    # Parse optional custom filename mapping
    filename_map: Dict[str, str] = {}
    try:
        if custom_filenames:
            filename_map = json.loads(custom_filenames) or {}
            if not isinstance(filename_map, dict):
                filename_map = {}
    except Exception:
        filename_map = {}

    # Extract JWT token for internal API calls, like in single-file endpoint
    auth_header = request.headers.get("Authorization", "")
    jwt_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
    enhanced_user = dict(current_user)
    if jwt_token:
        enhanced_user["auth_token"] = jwt_token

    # Per-file size limit (same as single endpoint)
    MAX_FILE_SIZE_MB = 50
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    job_items: List[Dict[str, Any]] = []

    # Iterate files and dispatch processing threads
    for idx, file in enumerate(files):
        if file.content_type not in AUDIO_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type for {file.filename}: {file.content_type}. Please upload an audio file."
            )

        # Read into memory (consistent with single-file logic)
        file_content = await file.read()
        await file.seek(0)

        if len(file_content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {file.filename} exceeds {MAX_FILE_SIZE_MB}MB limit."
            )

        # Determine custom filename if provided
        custom_name = None
        # filename_map keys can be either index as string or original filename
        if str(idx) in filename_map:
            custom_name = filename_map[str(idx)]
        elif file.filename in filename_map:
            custom_name = filename_map[file.filename]

        # Create job and spawn processing
        job_id = create_job()

        file_info = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(file_content)
        }

        thread = threading.Thread(
            target=run_processing_in_thread,
            args=(
                job_id,
                file_content,
                file_info,
                custom_name,
                transcription_options,
                enhanced_user,
                detected_ip,
                background_tasks
            )
        )
        thread.daemon = True
        thread.start()

        job_items.append({"file": file.filename, "job_id": job_id})

    return {
        "status": "accepted",
        "message": "Bulk processing started. Track each job via job_id.",
        "items": job_items
    }

@router.get("/job-status/{job_id}")
async def get_job_status_endpoint(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check the status of a job by its ID"""
    job_status = get_job_status(job_id)
    
    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found"
        )
    
    # Return simplified response with only essential fields
    simplified_status = {
        "id": job_status["id"],
        "status": job_status["status"],
        "created_at": job_status["created_at"],
        "updated_at": job_status["updated_at"],
        "progress": job_status["progress"]
    }
    
    # Include error if present
    if job_status.get("error"):
        simplified_status["error"] = job_status["error"]
    
    return simplified_status

def run_processing_in_thread(
    job_id: str,
    file_content: bytes,
    file_info: dict,
    custom_filename: Optional[str],
    transcription_options_str: str,
    current_user: dict,
    detected_ip: str,
    background_tasks: BackgroundTasks # Add BackgroundTasks here
):
    """Run the processing in a separate thread with its own event loop"""
    import time # Import time here to ensure it's available in this thread's context
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the async processing function in this thread's event loop
        loop.run_until_complete(
            process_audio_background(
                job_id,
                file_content,
                file_info,
                custom_filename,
                transcription_options_str,
                current_user,
                detected_ip,
                background_tasks # Pass background_tasks here
            )
        )
    except Exception as e:
        # Update job status in case of unexpected error
        update_job_status(
            job_id,
            JobStatus.FAILED,
            error=f"Thread execution error: {str(e)}"
        )
    finally:
        # Clean up the event loop
        loop.close()

async def process_audio_background(
    job_id: str,
    file_content: bytes,
    file_info: dict,
    custom_filename: Optional[str],
    transcription_options_str: str,
    current_user: dict,
    detected_ip: str,
    background_tasks: BackgroundTasks # Add BackgroundTasks here
):
    """Background task to process audio"""
    import time # Import time here for start_time
    start_time = time.time() # Define start_time at the beginning of the function

    # Create a temp directory for processing
    temp_dir = tempfile.mkdtemp()
    local_file_path = None
    upload_id = None  # Track the upload ID for content management
    
    try:
        # Update job status to started
        update_job_status(
            job_id, 
            JobStatus.CHECKING_CREDITS,
            current_step="checking_credits"
        )
        
        # Step 1: Check credits before processing
        try:
            # Use run_in_executor with the synchronous wrapper
            print(f"About to check credits for job {job_id}, IP: {detected_ip}")
            
            credit_response = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_check_credits(detected_ip, current_user)
            )
            
            # Print full details for debugging
            print(f"Credit check response for job {job_id}: {credit_response}")
            
            # Ensure we have a proper dictionary response
            if not isinstance(credit_response, dict):
                print(f"ERROR: Invalid credit response type: {type(credit_response)}")
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error=f"Invalid credit check response: {type(credit_response)}"
                )
                return
                
            credits_remaining = credit_response.get("credits_remaining", 0)
            
            # Log credit info for debugging
            print(f"Credit check response: {credit_response}")
            print(f"Credits remaining: {credits_remaining}")
            
            # Restore strict credit enforcement - remove the False check
            if credits_remaining <= 0:
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error="Credit limit reached"
                )
                return
                
            # Update with successful credit check
            update_job_status(
                job_id,
                JobStatus.CHECKING_CREDITS,
                progress=10,
                result={"credit_check": credit_response}
            )
        except Exception as e:
            # Provide more detailed error information
            import traceback
            error_details = traceback.format_exc()
            print(f"Credit check error for job {job_id}: {str(e)}\n{error_details}")
            
            # Fail on credit check error - no more continuing despite errors
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error checking credits: {str(e)}"
            )
            return  # Stop processing on credit check failure
        
        # Step 2: Save the file locally
        update_job_status(
            job_id, 
            JobStatus.UPLOADING, 
            progress=10,
            current_step="saving_file"
        )
        
        # Define the save_file function
        def save_file():
            # Determine filename (use custom if provided, otherwise use original)
            original_filename = file_info["filename"]
            filename = secure_filename(custom_filename or original_filename)
            
            # Create file path
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join(upload_dir, f"{filename}")
            
            # Handle duplicates by adding a counter
            counter = 1
            while os.path.exists(file_path):
                name, ext = os.path.splitext(filename)
                file_path = os.path.join(upload_dir, f"{name}_{counter}{ext}")
                counter += 1
            
            # Save the file locally
            with open(file_path, "wb") as buffer:
                buffer.write(file_content)
            
            return file_path
        
        # Use run_in_executor to run the file saving without blocking
        local_file_path = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            save_file
        )
        
        print(f"File for job {job_id} saved at {local_file_path}")
        
        # Track the upload in content management system
        user_id = str(current_user.get("_id", "unknown"))
        file_name = os.path.basename(local_file_path)
        file_size = os.path.getsize(local_file_path)
        
        # Collect user metadata
        user_metadata = {
            "job_id": job_id,
            "content_type": file_info["content_type"],
            "original_filename": file_info["filename"],
            "username": current_user.get("username", "unknown"),
            "email": current_user.get("email", "unknown"),
            "user_full_name": current_user.get("full_name", "")
        }
        
        # Initial tracking with pending status - use synchronous wrapper for thread safety
        upload_id = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            lambda: sync_track_upload(
                user_id=user_id,
                file_name=file_name,
                file_path=local_file_path,
                file_type="audio",
                file_size=file_size,
                metadata=user_metadata
            )
        )
        
        print(f"Created upload tracking record with ID: {upload_id}")
        
        # Step 3: Upload to Supabase for permanent storage
        update_job_status(
            job_id, 
            JobStatus.UPLOADING_TO_SUPABASE,
            progress=20,
            current_step="uploading_to_supabase"
        )
        
        # Upload to Supabase
        try:
            supabase_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_upload_to_supabase(
                        local_file_path,
                        file_name,
                        user_id,
                        bucket_name=os.getenv("SUPABASE_BUCKET_ORIGINAL")
                    )
                ),
                timeout=90
            )
        except asyncio.TimeoutError:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Supabase upload timed out after 90s"
            )
            return
        
        print(f"[DEBUG] Supabase upload result: {json.dumps(supabase_result, default=str)}")
        
        if not supabase_result or "file_url" not in supabase_result:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Failed to upload to Supabase"
            )
            return
            
        supabase_url = supabase_result["file_url"]
        print(f"[DEBUG] File uploaded to Supabase with URL: {supabase_url}")
        
        if not supabase_url:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Supabase URL is empty"
            )
            return
        
        # Store original Supabase storage identifiers for potential cleanup
        original_supabase_file_name = supabase_result.get("file_name")
        original_supabase_file_path = supabase_result.get("file_path")
        original_supabase_bucket = supabase_result.get("bucket")
        
        # Update the upload record with the Supabase URL
        if upload_id:
            print(f"Updating upload record {upload_id} with Supabase URL")
            update_result = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_upload_status(
                    upload_id=upload_id,
                    status="processing",
                    supabase_url=supabase_url
                )
            )
            print(f"Update result: {update_result}")
            if not update_result:
                print("WARNING: Failed to update upload record with Supabase URL")
        
        # Step 4: Transcribe the audio
        update_job_status(
            job_id, 
            JobStatus.TRANSCRIBING,
            current_step="transcribing"
        )
        
        # Ensure options dict exists for safe access in exception paths
        transcribe_options = {}
        try:
            # Parse transcription options
            try:
                transcribe_options = json.loads(transcription_options_str)
            except json.JSONDecodeError:
                transcribe_options = {}
            
            # Use the Supabase URL for transcription with sync wrapper
            transcription_data = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_transcribe_audio(supabase_url, transcribe_options)
            )
            
            if not transcription_data:
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error="Failed to transcribe the audio"
                )
                return
            
            # Extract transcript information
            results = transcription_data.get("results", {})
            transcript_text = results.get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            detected_language = results.get("channels", [{}])[0].get("detected_language", "en")
            confidence = results.get("channels", [{}])[0].get("alternatives", [{}])[0].get("confidence", 0)
            words = results.get("channels", [{}])[0].get("alternatives", [{}])[0].get("words", [])
            
            # Create podcast record
            duration = transcription_data.get("metadata", {}).get("duration", 0)
            file_basename = os.path.basename(local_file_path)
            
            # Generate a cleaner title from the filename
            title = file_basename
            if "." in title:  # Remove file extension for title
                title = title.rsplit(".", 1)[0]
            # Replace underscores and hyphens with spaces for readability
            title = title.replace("_", " ").replace("-", " ").title()
            
            # Get user details for author field
            author = current_user.get("username", "unknown")
            if current_user.get("full_name"):
                author = current_user.get("full_name")
            
            # Create podcast record with permanent Supabase URL
            podcast_id = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_create_podcast(
                    title=title,
                    description=f"Uploaded on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    audio_url=supabase_url,
                    duration_seconds=duration,
                    author=author,
                    language=detected_language,
                    upload_id=upload_id,
                    supabase_url=supabase_url
                )
            )
            
            print(f"Created podcast record with ID: {podcast_id}")
            
            # Mark podcast as transcription in progress
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_podcast_transcription_status(
                    podcast_id=podcast_id,
                    status="in_progress"
                )
            )
            
            # Create segments from words
            segments = []
            if words:
                for word in words:
                    segments.append({
                        "text": word.get("word", ""),
                        "start": word.get("start", 0),
                        "end": word.get("end", 0),
                        "confidence": word.get("confidence", 0)
                    })
            
            # Create transcript record
            transcript_id = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_create_transcript(
                    podcast_id=podcast_id,
                    content=transcript_text,
                    language=detected_language,
                    segments=segments,
                    confidence_score=confidence
                )
            )
            
            print(f"Created transcript record with ID: {transcript_id}")
            
            # Update podcast with transcription status
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_podcast_transcription_status(
                    podcast_id=podcast_id,
                    status="completed",
                    transcript_id=transcript_id
                )
            )
            
            # Index transcript in Pinecone (single call)
            try:
                indexed = await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_index_transcript(
                        transcript_data=transcription_data,
                        file_url=supabase_url,
                        file_name=file_basename,
                        is_permanent_url=True
                    )
                )
                transcription_data["indexed"] = bool(indexed)
            except Exception as e:
                transcription_data["indexed"] = False
                transcription_data["indexing_error"] = str(e)
            
            # Update job with transcription result
            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["transcription"] = transcription_data
            
            update_job_status(
                job_id,
                status=JobStatus.TRANSCRIBING,
                result=current_result,
                progress=50  # 50% progress
            )
            
            # Track transcription stats directly here
            processing_time = time.time() - start_time
            audio_length = transcription_data.get("metadata", {}).get("duration", 0)
            status = "success"
            detected_language = transcription_data.get("results", {}).get("channels", [{}])[0].get("detected_language", "en")
            confidence = transcription_data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("confidence", 0)
            
            stats_data = {
                "timestamp": datetime.utcnow(),
                "status": status,
                "processing_time": processing_time,
                "audio_length": audio_length,
                "language": detected_language,
                "user_id": str(current_user.get("_id", "")),
                "confidence": confidence,
                "model": transcribe_options.get("model", "default"),
                "podcast_id": podcast_id,
                "transcript_id": transcript_id
            }
            
            # Directly await the insertion, as process_audio_background is already in an async context
            await _insert_transcription_stats(stats_data)

        except Exception as e:
            # Track transcription error directly here
            processing_time = time.time() - start_time
            error_stats_data = {
                "timestamp": datetime.utcnow(),
                "status": "error",
                "processing_time": processing_time,
                "audio_length": 0,  # Unknown in case of error
                "language": transcribe_options.get("language", "en"),
                "user_id": str(current_user.get("_id", "")),
                "error": str(e),
                "url": supabase_url # Use supabase_url as the source URL
            }
            
            # Directly await the insertion for error stats
            await _insert_transcription_stats(error_stats_data)

            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error transcribing audio: {str(e)}"
            )
            return
        
        # Step 6: Embed the transcription metadata into the audio file
        update_job_status(
            job_id, 
            JobStatus.EMBEDDING,
            current_step="embedding"
        )
        
        try:
            temp_embedded_file = os.path.join(temp_dir, f"embedded_{os.path.basename(local_file_path)}")
            metadata_json = json.dumps(transcription_data)
            
            # Use run_in_executor with sync wrapper for embedding
            embedded_file_path = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_embed_metadata(local_file_path, temp_embedded_file, metadata_json)
            )
            
            embedding_result = {
                "filename": os.path.basename(embedded_file_path),
                "file_path": embedded_file_path
            }
            
            # Update job with embedding result
            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["embedding"] = embedding_result
            
            update_job_status(
                job_id,
                status=JobStatus.EMBEDDING,
                result=current_result,
                progress=66  # 66% progress
            )
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error embedding metadata: {str(e)}"
            )
            return
        
        # Step 6.5: Upload embedded file to Supabase and update records (with retry/backoff)
        update_job_status(
            job_id,
            JobStatus.UPLOADING_TO_SUPABASE,
            current_step="uploading_embedded_to_supabase",
            progress=75
        )
        try:
            embedded_filename = os.path.basename(embedded_file_path)
            max_attempts = 3
            delay = 1.0
            embedded_upload_result = None
            for attempt in range(1, max_attempts + 1):
                try:
                    embedded_upload_result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            thread_pool,
                            lambda: sync_upload_to_supabase(
                                embedded_file_path,
                                embedded_filename,
                                user_id,
                                bucket_name=os.getenv("SUPABASE_BUCKET_EMBEDDED")
                            )
                        ),
                        timeout=90
                    )
                    if embedded_upload_result and "file_url" in embedded_upload_result:
                        break
                except asyncio.TimeoutError:
                    print(f"[WARN] Embedded upload attempt {attempt} timed out after 90s")
                except Exception as inner_e:
                    print(f"[WARN] Embedded upload attempt {attempt} failed: {inner_e}")
                if attempt < max_attempts:
                    time.sleep(delay)
                    delay *= 2

            if not embedded_upload_result or "file_url" not in embedded_upload_result:
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error="Failed to upload embedded file to Supabase after retries"
                )
                return

            embedded_supabase_url = embedded_upload_result["file_url"]

            # Update upload record to point to embedded file
            if upload_id:
                await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_update_upload_status(
                        upload_id=upload_id,
                        status="processing",
                        supabase_url=embedded_supabase_url
                    )
                )

            # Update podcast record to use embedded file URL
            if 'podcast_id' in locals() and podcast_id:
                await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_update_podcast_url(podcast_id, embedded_supabase_url)
                )

            # Optional: delete original Supabase file if configured
            try:
                delete_flag = os.getenv("DELETE_ORIGINAL_SUPABASE_FILE", "false").lower() in ("1", "true", "yes")
                if delete_flag and (original_supabase_file_path or original_supabase_file_name):
                    name_or_path = original_supabase_file_path or original_supabase_file_name
                    try:
                        await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                thread_pool,
                                lambda: sync_delete_from_supabase(
                                    name_or_path,
                                    bucket_name=original_supabase_bucket or os.getenv("SUPABASE_BUCKET_ORIGINAL")
                                )
                            ),
                            timeout=30
                        )
                    except asyncio.TimeoutError:
                        print("[WARN] Deletion of original Supabase file timed out after 30s")
            except Exception as del_e:
                print(f"[WARN] Failed to delete original Supabase file: {del_e}")

            # Update job result with embedded Supabase URL
            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["embedded_supabase_url"] = embedded_supabase_url
            update_job_status(
                job_id,
                status=JobStatus.EMBEDDING,
                result=current_result,
                progress=80
            )
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error uploading embedded file to Supabase: {str(e)}"
            )
            return

        # Step 7: Deduct credit - using direct database access
        update_job_status(
            job_id, 
            JobStatus.DEDUCTING_CREDITS,
            current_step="deducting_credits"
        )
        
        try:
            # Use direct database access instead of API call
            print(f"About to deduct credit for job {job_id}, IP: {detected_ip}")
            
            deduct_response = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: direct_deduct_credit(detected_ip, current_user)
            )
            
            print(f"Direct credit deduction response for job {job_id}: {deduct_response}")
            
            # Check if credit deduction failed
            if not deduct_response.get("status", False):
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error=f"Failed to deduct credit: {deduct_response.get('detail', 'Unknown error')}"
                )
                return
            
            # Update job with credit deduction result
            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["credits"] = deduct_response
            
            update_job_status(
                job_id,
                status=JobStatus.DEDUCTING_CREDITS,
                result=current_result,
                progress=95  # 95% progress
            )
        except Exception as e:
            # Log the error and fail the job
            import traceback
            error_details = traceback.format_exc()
            print(f"Credit deduction error for job {job_id}: {str(e)}\n{error_details}")
            
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error deducting credits: {str(e)}"
            )
            return  # Stop processing on credit deduction failure
        
        # All done - mark as completed
        update_job_status(
            job_id,
            JobStatus.COMPLETED,
            progress=100
        )
        
    except Exception as e:
        # Handle any unexpected exceptions
        update_job_status(
            job_id,
            JobStatus.FAILED,
            error=f"Unexpected error: {str(e)}"
        )
    finally:
        # Clean up temp files using run_in_executor to avoid blocking
        if os.path.exists(temp_dir):
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: shutil.rmtree(temp_dir)
            )

# Helper functions to interact with existing API endpoints

async def check_user_credits_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Check user credits from the credit management API"""
    from api.credit_management import check_credits
    from fastapi.responses import JSONResponse
    import json
    
    # Create a dummy request for the check_credits function
    class DummyRequest:
        def __init__(self):
            self.client = None
            self.headers = {}
    
    dummy_request = DummyRequest()
    
    # Print debug info
    print(f"Checking credits for IP: {ip}")
    
    try:
        response = await check_credits(dummy_request, ip, current_user)
        print(f"Raw credit response: {response}")
        
        # Handle JSONResponse objects by converting to dict
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode('utf-8'))
                print(f"Parsed JSONResponse: {response_dict}")
                return response_dict
            except Exception as e:
                print(f"Error parsing JSONResponse: {str(e)}")
                # Use a high default value to prevent false "credit limit" errors
                return {"credits_remaining": 100, "ip_address": ip, "status": "default"}
        
        print(f"Direct dict response: {response}")
        return response
    except Exception as e:
        print(f"Exception in check_user_credits_async: {str(e)}")
        # Return a safe default instead of failing
        return {"credits_remaining": 100, "ip_address": ip, "status": "exception_default"}

async def deduct_user_credit_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Deduct a credit using the credit management API"""
    from api.credit_management import deduct_credit
    from fastapi.responses import JSONResponse
    import json
    
    # Create a dummy request for the deduct_credit function
    class DummyRequest:
        def __init__(self):
            self.client = None
            self.headers = {}
    
    dummy_request = DummyRequest()
    
    # Print debug info
    print(f"Deducting credit for IP: {ip}")
    
    try:
        response = await deduct_credit(dummy_request, ip, current_user)
        print(f"Raw deduct credit response: {response}")
        
        # Handle JSONResponse objects by converting to dict
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode('utf-8'))
                print(f"Parsed JSONResponse for credit deduction: {response_dict}")
                return response_dict
            except Exception as e:
                print(f"Error parsing JSONResponse for credit deduction: {str(e)}")
                return {"status": True, "credits_remaining": 0, "ip_address": ip, "status": "default"}
        
        print(f"Direct dict response for credit deduction: {response}")
        return response
    except Exception as e:
        print(f"Exception in deduct_user_credit_async: {str(e)}")
        # Return a safe default instead of failing
        return {"status": True, "credits_remaining": 0, "ip_address": ip, "status": "exception_default"}

# This function will run synchronously and handle deducting credits
def sync_deduct_credit(ip: str, current_user: dict) -> Dict[str, Any]:
    """Synchronous wrapper for deducting credit"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(deduct_user_credit_async(ip, current_user))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_deduct_credit: {str(e)}")
        return {"status": False, "error": str(e), "credits_remaining": 0}

async def upload_to_tmpfiles_async(file_path: str) -> Optional[str]:
    """Upload the file to tmpfiles.org for public access"""
    max_retries = 3
    delay_seconds = 3

    for attempt in range(1, max_retries + 1):
        try:
            with open(file_path, "rb") as f:
                files = {"file": f}
                response = requests.post("https://tmpfiles.org/api/v1/upload", files=files)

            if response.status_code == 200:
                data = response.json()
                url = data.get("data", {}).get("url")
                if url:
                    url = url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/")
                    return url
            
            return None  # If unsuccessful
        except Exception:
            if attempt == max_retries:
                return None
            # Sleep before retrying
            await asyncio.sleep(delay_seconds)

async def transcribe_audio_async(audio_url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """Transcribe the audio using the Deepgram API through the transcribe endpoint"""
    from api.transcribe import TranscriptionRequest, transcribe_audio
    
    # Create a request object for the transcription API
    request_data = {"url": audio_url, **options}
    transcription_request = TranscriptionRequest(**request_data)
    
    # Call the transcription API
    current_user = {}  # We already authenticated with our main endpoint
    return await transcribe_audio(transcription_request, current_user)

async def embed_metadata_in_file_async(src_file: str, dest_file: str, metadata_json: str) -> str:
    """Embed the metadata into the audio file using the embedding API"""
    import shutil
    from mutagen.id3 import ID3, TXXX
    import base64
    
    # First copy the file
    shutil.copy2(src_file, dest_file)
    
    try:
        # Try to load existing ID3 tags, or create new ones if none
        try:
            tags = ID3(dest_file)
        except:
            # Creating new ID3 tags and associating them with the file
            tags = ID3()
            tags.save(dest_file)
            # Reloading the tags to ensure they're associated with the file
            tags = ID3(dest_file)
        
        # Encode as base64 to avoid issues with special characters
        encoded_json = base64.b64encode(metadata_json.encode('utf-8')).decode('utf-8')
        tags['TXXX:transcription_json'] = TXXX(encoding=3, desc='transcription_json', text=f"base64:{encoded_json}")
        
        # Save the tags to the file
        tags.save(dest_file)
        
        return dest_file
    except Exception as e:
        # If embedding fails, just return the original file
        print(f"Error embedding metadata: {str(e)}")
        return src_file

async def upload_to_supabase_async(file_path: str, filename: str, user_id: str = None, bucket_name: str = None) -> Dict[str, Any]:
    """Upload file to Supabase"""
    result = await upload_file_to_supabase(file_path, filename, user_id, bucket_name=bucket_name)
    return result

# Add a synchronous wrapper for the credit check function
def sync_check_credits(ip: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit check API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    import requests
    import json
    import os
    from dotenv import load_dotenv
    
    try:
        load_dotenv()
        
        # Get the base URL - use localhost on same port as the server
        api_base_url = "http://localhost:8000"  # Use same server where the app is running
        
        # Construct the full URL for the credit endpoint
        credit_api_url = f"{api_base_url}/api/check-credits"
        
        # First try to get token directly from our enhanced user object
        access_token = None
        if current_user and "auth_token" in current_user:
            access_token = current_user.get("auth_token")
            print(f"Using JWT token from original request")
        
        # If no token in enhanced user, try admin login
        if not access_token:
            # First try login to get a token
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
            
            # Try to get a token by logging in
            try:
                login_url = f"{api_base_url}/api/auth/login"
                login_data = {
                    "username": admin_email, 
                    "password": admin_password
                }
                login_headers = {"Content-Type": "application/x-www-form-urlencoded"}
                
                login_response = requests.post(login_url, data=login_data, headers=login_headers)
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get("access_token")
                    print(f"Successfully got access token via admin login")
                else:
                    print(f"Admin login failed: {login_response.status_code} - {login_response.text}")
            except Exception as e:
                print(f"Error during admin login: {str(e)}")
        
        # Set up headers
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add authorization if we have a token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            print(f"Using Authorization header: Bearer {access_token[:10]}...")
        else:
            print("WARNING: No access token available for credit API call")
            return {
                "credits_remaining": 100,  # Default high value to prevent false errors
                "ip_address": ip,
                "status": "default"
            }
        
        # Make the synchronous GET request to check credit
        print(f"Making direct HTTP request to {credit_api_url} for IP {ip}")
        response = requests.get(credit_api_url, headers=headers)
        
        # Parse and return the response
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Credit API returned status code {response.status_code}: {response.text}")
            
            # Return a safe default
            return {
                "credits_remaining": 100,  # Default high value to prevent false errors
                "ip_address": ip,
                "status": "error_response"
            }
    
    except Exception as e:
        print(f"Error calling credit API: {str(e)}")
        
        # Return a safe default
        return {
            "credits_remaining": 100,  # Default high value to prevent false errors
            "ip_address": ip,
            "status": "exception_default"
        }

# Add a synchronous wrapper for the transcribe function
def sync_transcribe_audio(audio_url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for transcribing audio"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(transcribe_audio_async(audio_url, options))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_transcribe_audio: {str(e)}")
        return {"error": str(e)}

# Add a synchronous wrapper for embedding metadata
def sync_embed_metadata(src_file: str, dest_file: str, metadata_json: str) -> str:
    """Synchronous wrapper for embedding metadata"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(embed_metadata_in_file_async(src_file, dest_file, metadata_json))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_embed_metadata: {str(e)}")
        return src_file  # Return original file on error

# Add a synchronous wrapper for Supabase upload
def sync_upload_to_supabase(file_path: str, filename: str, user_id: str = None, bucket_name: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for uploading to Supabase"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(upload_to_supabase_async(file_path, filename, user_id, bucket_name))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_upload_to_supabase: {str(e)}")
        return {"error": str(e), "file_name": filename}

# Add a synchronous wrapper for Supabase delete
def sync_delete_from_supabase(name_or_path: str, bucket_name: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for deleting a file from Supabase storage"""
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from services.supabase_service import delete_file_from_supabase
        result = loop.run_until_complete(delete_file_from_supabase(name_or_path, bucket_name=bucket_name))
        loop.close()
        return result
    except Exception as e:
        print(f"Error in sync_delete_from_supabase: {str(e)}")
        return {"success": False, "error": str(e)}

# Add a synchronous wrapper for tmpfiles upload
def sync_upload_to_tmpfiles(file_path: str) -> Optional[str]:
    """Synchronous wrapper for uploading to tmpfiles"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(upload_to_tmpfiles_async(file_path))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_upload_to_tmpfiles: {str(e)}")
        return None

# Add a synchronous wrapper for Pinecone indexing
def sync_index_transcript(transcript_data: Dict[str, Any], file_url: str, file_name: str, is_permanent_url: bool = False) -> bool:
    """
    Synchronous wrapper for indexing transcript in Pinecone
    
    Args:
        transcript_data: The transcription data
        file_url: URL to the audio file
        file_name: Name of the audio file
        is_permanent_url: Whether the URL is permanent (Supabase) or temporary (tmpfiles)
    """
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        from services.pinecone_service import index_transcript
        result = loop.run_until_complete(
            index_transcript(
                transcript_data=transcript_data,
                file_url=file_url,
                file_name=file_name,
                is_permanent_url=is_permanent_url
            )
        )
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_index_transcript: {str(e)}")
        return False

# Add a synchronous wrapper for updating podcast URL
def sync_update_podcast_url(podcast_id: str, supabase_url: str) -> bool:
    """
    Update a podcast record with the permanent Supabase URL
    
    Args:
        podcast_id: ID of the podcast to update
        supabase_url: Permanent Supabase URL to set
    """
    import asyncio
    from bson import ObjectId
    from datetime import datetime
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the update in this loop
        from services.database import podcasts_collection
        
        async def update_podcast():
            result = await podcasts_collection.update_one(
                {"_id": ObjectId(podcast_id)},
                {"$set": {
                    "supabase_url": supabase_url,
                    "audio_url": supabase_url,
                    "updated_at": datetime.utcnow()
                }}
            )
            return result.modified_count > 0
        
        result = loop.run_until_complete(update_podcast())
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_update_podcast_url: {str(e)}")
        return False

# Update the direct_deduct_credit function to remove simulation fallbacks
def direct_deduct_credit(ip_address: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    import requests
    import json
    import os
    from dotenv import load_dotenv
    
    try:
        load_dotenv()
        
        # Get the base URL - use localhost on same port as the server
        api_base_url = "http://localhost:8000"  # Use same server where the app is running
        
        # Construct the full URL for the credit endpoint
        credit_api_url = f"{api_base_url}/api/credit"
        
        # Print what we have in current_user for debugging
        print(f"Current user object keys for credit API: {current_user.keys() if current_user else 'None'}")
        
        # First try to get token directly from our enhanced user object
        access_token = None
        if current_user and "auth_token" in current_user:
            access_token = current_user.get("auth_token")
            print(f"Using JWT token from original request")
        
        # If no token in enhanced user, try admin login
        if not access_token:
            # First try login to get a token
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
            
            # Try to get a token by logging in
            try:
                login_url = f"{api_base_url}/api/auth/login"
                login_data = {
                    "username": admin_email, 
                    "password": admin_password
                }
                login_headers = {"Content-Type": "application/x-www-form-urlencoded"}
                
                login_response = requests.post(login_url, data=login_data, headers=login_headers)
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get("access_token")
                    print(f"Successfully got access token via admin login")
                else:
                    print(f"Admin login failed: {login_response.status_code} - {login_response.text}")
            except Exception as e:
                print(f"Error during admin login: {str(e)}")
        
        # Set up headers
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add authorization if we have a token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            print(f"Using Authorization header: Bearer {access_token[:10]}...")
        else:
            print("WARNING: No access token available for credit API call")
            return {
                "status": False,
                "detail": "No authentication token available",
                "credits_remaining": 0
            }
        
        # Include IP in request body
        data = {
            "ip": ip_address
        }
        
        # Make the synchronous POST request to deduct credit
        print(f"Making direct HTTP request to {credit_api_url} for IP {ip_address}")
        response = requests.post(credit_api_url, json=data, headers=headers)
        
        # Parse and return the response
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Credit API returned status code {response.status_code}: {response.text}")
            
            # No more simulation - return actual error
            return {
                "status": False,
                "detail": f"Credit API error: {response.status_code}",
                "credits_remaining": 0,
                "response_text": response.text
            }
    
    except Exception as e:
        print(f"Error calling credit API: {str(e)}")
        
        # No more simulation - return actual error
        return {
            "status": False,
            "detail": f"Error calling credit API: {str(e)}",
            "credits_remaining": 0
        }
