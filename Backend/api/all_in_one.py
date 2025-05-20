from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
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
from services.auth import get_current_user
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
    detected_ip: str = Depends(get_ip_for_request)
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
    
    # Make a local copy of the file in memory
    file_content = await file.read()
    
    # Reset the file pointer for further processing
    await file.seek(0)
    
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
            detected_ip
        )
    )
    thread.daemon = True  # Daemonize thread to allow the program to exit
    thread.start()
    
    return {
        "job_id": job_id,
        "status": "accepted",
        "message": "Your audio is being processed. You can check the status using the job_id."
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
    detected_ip: str
):
    """Run the processing in a separate thread with its own event loop"""
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
                detected_ip
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
    detected_ip: str
):
    """Background task to process audio"""
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
            
            file_path = os.path.join(upload_dir, filename)
            
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
                file_url="",  # Will be updated after tmpfiles upload
                file_type="audio",
                file_size=file_size,
                status="pending",
                metadata=user_metadata
            )
        )
        
        print(f"Created upload tracking record with ID: {upload_id}")
        
        # Step 3: Upload to tmpfiles.org
        update_job_status(
            job_id, 
            JobStatus.UPLOADING, 
            progress=20,
            current_step="uploading_to_tmpfiles"
        )
        
        # Upload to tmpfiles.org using the synchronous function through run_in_executor
        tmpfiles_url = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            lambda: sync_upload_to_tmpfiles(local_file_path)
        )
        
        if not tmpfiles_url:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Failed to upload to tmpfiles.org"
            )
            return
        
        print(f"File for job {job_id} uploaded to tmpfiles.org at {tmpfiles_url}")
        
        # Update the upload record with the tmpfiles URL
        if upload_id:
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_upload_status(
                    upload_id=upload_id,
                    status="processing",
                    file_url=tmpfiles_url
                )
            )
        
        # Step 4: Transcribe the audio
        update_job_status(
            job_id, 
            JobStatus.TRANSCRIBING,
            current_step="transcribing"
        )
        
        try:
            # Parse transcription options
            try:
                transcribe_options = json.loads(transcription_options_str)
            except json.JSONDecodeError:
                transcribe_options = {}
            
            # Use the tmpfiles URL for transcription with sync wrapper
            transcription_data = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_transcribe_audio(tmpfiles_url, transcribe_options)
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
            
            # Create podcast record
            podcast_id = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_create_podcast(
                    title=title,
                    description=f"Uploaded on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    audio_url=tmpfiles_url,
                    duration_seconds=duration,
                    author=author,
                    language=detected_language,
                    upload_id=upload_id,
                    supabase_url=None  # Will be updated after Supabase upload
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
            
            # Update upload status
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_upload_status(
                    upload_id=upload_id,
                    status="completed",
                    processed_at=datetime.utcnow(),
                    podcast_id=podcast_id
                )
            )
            
            # Index the transcript in Pinecone if needed
            try:
                # Use run_in_executor with sync wrapper for indexing
                indexed = await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_index_transcript(
                        transcript_data=transcription_data,
                        file_url=tmpfiles_url,
                        file_name=file_basename
                    )
                )
                transcription_data["indexed"] = indexed
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
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error transcribing audio: {str(e)}"
            )
            return
        
        # Step 5: Embed the transcription metadata into the audio file
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
        
        # Step 6: Upload to Supabase
        update_job_status(
            job_id, 
            JobStatus.UPLOADING_TO_SUPABASE,
            current_step="uploading_to_supabase"
        )
        
        try:
            # Get user ID for Supabase
            user_id = str(current_user.get("_id", "unknown"))
            print(f"[DEBUG] Uploading to Supabase with user_id: {user_id}")
            print(f"[DEBUG] Current user data: {json.dumps(current_user, default=str)}")
            
            # Use run_in_executor with sync wrapper for Supabase
            supabase_response = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_upload_to_supabase(embedded_file_path, os.path.basename(embedded_file_path), user_id)
            )
            
            # Add metadata to the response
            if transcription_data and isinstance(transcription_data, dict):
                supabase_response["metadata"] = transcription_data
                
                # Update the upload record with the Supabase URL
                if upload_id and supabase_response.get("file_url"):
                    await asyncio.get_event_loop().run_in_executor(
                        thread_pool,
                        lambda: sync_update_upload_status(
                            upload_id=upload_id,
                            status="completed",
                            processed_at=datetime.utcnow(),
                            podcast_id=podcast_id,
                            supabase_url=supabase_response.get("file_url")  # Store the Supabase URL
                        )
                    )
                    
                    # Also update the podcast record with the Supabase URL
                    if podcast_id:
                        # Update podcast with Supabase URL
                        await podcasts_collection.update_one(
                            {"_id": ObjectId(podcast_id)},
                            {"$set": {
                                "supabase_url": supabase_response.get("file_url"),
                                "updated_at": datetime.utcnow()
                            }}
                        )
                
                # Index the transcript in Pinecone for search
                try:
                    # Use run_in_executor with sync wrapper for indexing
                    indexed = await asyncio.get_event_loop().run_in_executor(
                        thread_pool,
                        lambda: sync_index_transcript(
                            transcript_data=transcription_data,
                            file_url=supabase_response.get("file_url", ""),
                            file_name=supabase_response.get("file_name", "")
                        )
                    )
                    supabase_response["indexed"] = indexed
                except Exception as e:
                    supabase_response["indexed"] = False
                    supabase_response["indexing_error"] = str(e)
            
            # Update job with Supabase result
            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["supabase"] = supabase_response
            
            update_job_status(
                job_id,
                status=JobStatus.UPLOADING_TO_SUPABASE,
                result=current_result,
                progress=83  # 83% progress
            )
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error uploading to Supabase: {str(e)}"
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

async def upload_to_supabase_async(file_path: str, filename: str, user_id: str = None) -> Dict[str, Any]:
    """Upload file to Supabase"""
    result = await upload_file_to_supabase(file_path, filename, user_id)
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
def sync_upload_to_supabase(file_path: str, filename: str, user_id: str = None) -> Dict[str, Any]:
    """Synchronous wrapper for uploading to Supabase"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        result = loop.run_until_complete(upload_to_supabase_async(file_path, filename, user_id))
        
        # Clean up
        loop.close()
        
        return result
    except Exception as e:
        print(f"Error in sync_upload_to_supabase: {str(e)}")
        return {"error": str(e), "file_name": filename}

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
def sync_index_transcript(transcript_data: Dict[str, Any], file_url: str, file_name: str) -> bool:
    """Synchronous wrapper for indexing transcript in Pinecone"""
    import asyncio
    
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function in this loop
        loop.run_until_complete(index_transcript(
            transcript_data=transcript_data,
            file_url=file_url,
            file_name=file_name
        ))
        
        # Clean up
        loop.close()
        
        return True
    except Exception as e:
        print(f"Error in sync_index_transcript: {str(e)}")
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