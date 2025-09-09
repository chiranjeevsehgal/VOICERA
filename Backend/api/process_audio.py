from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    status,
    Depends,
    Request,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import json
import threading
import asyncio

import os
import re

from services.auth import get_current_user, requires_role
from services.ip_utils import get_ip_for_request
from services.job_tracker import create_job, get_job_status, clean_old_jobs
from api.upload import AUDIO_MIME_TYPES

# Import the background processor entrypoint
from services.background_processor import run_processing_in_thread

router = APIRouter()

# Limit concurrent background processing threads for bulk uploads to reduce memory spikes
MAX_CONCURRENT_BULK_THREADS = 4
_thread_semaphore = threading.Semaphore(MAX_CONCURRENT_BULK_THREADS)


def _run_with_semaphore(
    job_id: str,
    file_content: bytes,
    file_info: Dict[str, Any],
    custom_filename: Optional[str],
    transcription_options: str,
    enhanced_user: Dict[str, Any],
    detected_ip: str,
    background_tasks: BackgroundTasks,
):
    try:
        _thread_semaphore.acquire()
        run_processing_in_thread(
            job_id,
            file_content,
            file_info,
            custom_filename,
            transcription_options,
            enhanced_user,
            detected_ip,
            background_tasks,
        )
    finally:
        _thread_semaphore.release()


def sanitize_filename(name: str) -> str:
    """Return a safe filename limited to common characters and strip path components."""
    base = os.path.basename(name or "").strip()
    safe = re.sub(r"[^A-Za-z0-9._\-\s]", "_", base)
    # Avoid empty names after sanitization
    return safe[:255] if safe else base[:255]


@router.on_event("startup")
async def setup_job_cleaner():
    async def cleanup_jobs():
        while True:
            clean_old_jobs()
            await asyncio.sleep(3600)

    asyncio.create_task(cleanup_jobs())


@router.post("/process_audio", status_code=202)
async def process_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    custom_filename: Optional[str] = Form(None),
    transcription_options: Optional[str] = Form("{}"),
    current_user: dict = Depends(get_current_user),
    detected_ip: str = Depends(get_ip_for_request),
):
    # Validate file
    if not file:
        return JSONResponse(status_code=400, content={"message": "No file provided"})

    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Please upload an audio file.",
        )

    job_id = create_job()

    MAX_FILE_SIZE_MB = 50
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    file_content = await file.read()
    await file.seek(0)

    if len(file_content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the limit of {MAX_FILE_SIZE_MB}MB.",
        )

    # Extract JWT for internal calls
    auth_header = request.headers.get("Authorization", "")
    jwt_token = (
        auth_header.replace("Bearer ", "")
        if auth_header.startswith("Bearer ")
        else None
    )

    enhanced_user = dict(current_user)
    if jwt_token:
        enhanced_user["auth_token"] = jwt_token

    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(file_content),
    }

    # Dispatch processing thread
    thread = threading.Thread(
        target=run_processing_in_thread,
        args=(
            job_id,
            file_content,
            file_info,
            custom_filename,
            transcription_options,
            enhanced_user,
            detected_ip,
            background_tasks,
        ),
    )
    thread.daemon = True
    thread.start()

    return {
        "job_id": job_id,
        "status": "accepted",
        "message": "Your audio is being processed. You can check the status using the job_id.",
    }


@router.post("/process_audio_bulk", status_code=202)
async def process_audio_bulk(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    custom_filenames: Optional[str] = Form(None),
    current_user: dict = Depends(requires_role("admin")),
    detected_ip: str = Depends(get_ip_for_request),
):
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided"
        )

    MAX_FILES = 50
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Max {MAX_FILES} allowed",
        )

    # Validate transcription options format
    try:
        if custom_filenames:
            filename_map = json.loads(custom_filenames) or {}
        else:
            filename_map = {}
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in custom_filenames: {str(e)}",
        )

    filename_map: Dict[str, str] = {}
    try:
        if custom_filenames:
            filename_map = json.loads(custom_filenames) or {}
            if not isinstance(filename_map, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="custom_filenames must be a valid JSON object",
                )
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in custom_filenames: {str(e)}",
        )

    auth_header = request.headers.get("Authorization", "")
    jwt_token = (
        auth_header.replace("Bearer ", "")
        if auth_header.startswith("Bearer ")
        else None
    )
    enhanced_user = dict(current_user)
    if jwt_token:
        enhanced_user["auth_token"] = jwt_token

    MAX_FILE_SIZE_MB = 50
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    job_items: List[Dict[str, Any]] = []
    failed_files: List[Dict[str, str]] = []

    for idx, file in enumerate(files):
        try:
            # Validate file type
            if file.content_type not in AUDIO_MIME_TYPES:
                failed_files.append(
                    {
                        "file": file.filename,
                        "error": f"Unsupported file type: {file.content_type}",
                    }
                )
                continue

            # Read file content in chunks to enforce size limit without large memory spikes
            total_read = 0
            buffer = bytearray()
            try:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    total_read += len(chunk)
                    if total_read > MAX_FILE_SIZE_BYTES:
                        failed_files.append(
                            {
                                "file": file.filename,
                                "error": f"File exceeds {MAX_FILE_SIZE_MB}MB limit",
                            }
                        )
                        buffer = None  # signal oversize
                        break
            finally:
                # Always reset file pointer after reading
                try:
                    await file.seek(0)
                except Exception:
                    pass

            if buffer is None:
                continue

            if total_read == 0:
                failed_files.append(
                    {
                        "file": file.filename,
                        "error": "File is empty or could not be read",
                    }
                )
                continue

            file_content = bytes(buffer)

            # Get custom filename if provided
            custom_name = None
            if str(idx) in filename_map:
                custom_name = filename_map[str(idx)]
            elif file.filename in filename_map:
                custom_name = filename_map[file.filename]

            if custom_name:
                custom_name = sanitize_filename(custom_name)

            # Create job and file info
            job_id = create_job()
            file_info = {
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(file_content),
            }

            # Start processing thread with concurrency gating
            thread = threading.Thread(
                target=_run_with_semaphore,
                args=(
                    job_id,
                    file_content,
                    file_info,
                    custom_name,
                    filename_map,
                    enhanced_user,
                    detected_ip,
                    background_tasks,
                ),
            )
            thread.daemon = True
            thread.start()

            job_items.append({"file": file.filename, "job_id": job_id})

        except Exception as e:
            failed_files.append(
                {"file": file.filename, "error": f"Processing error: {str(e)}"}
            )
            continue

    # If no files were successfully queued, return error
    if not job_items and failed_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "No files could be processed",
                "failed_files": failed_files,
            },
        )

    response = {
        "status": "accepted",
        "message": "Bulk processing started. Track each job via job_id.",
        "items": job_items,
    }

    # Include failed files in response if any
    if failed_files:
        response["failed_files"] = failed_files
        response["message"] = (
            f"Bulk processing started for {len(job_items)} files. {len(failed_files)} files failed validation."
        )

    return response


@router.get("/job-status/{job_id}")
async def get_job_status_endpoint(
    job_id: str, current_user: dict = Depends(get_current_user)
):
    job_status = get_job_status(job_id)
    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    simplified_status = {
        "id": job_status["id"],
        "status": job_status["status"],
        "created_at": job_status["created_at"],
        "updated_at": job_status["updated_at"],
        "progress": job_status["progress"],
    }

    if job_status.get("error"):
        simplified_status["error"] = job_status["error"]

    return simplified_status
