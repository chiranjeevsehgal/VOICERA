import os
import time
import requests
import shutil
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from typing import List, Optional
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
from services.auth import get_current_user
from utils.content_tracker import track_upload

router = APIRouter()

AUDIO_MIME_TYPES = [
    "audio/mpeg", 
    "audio/wav", 
    "audio/wave", 
    "audio/ogg", 
    "audio/x-wav", 
    "audio/x-m4a",
    "audio/mp4"
]
UPLOAD_DIR = "audio_uploads"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", status_code=201)
async def upload_audio(
    file: UploadFile = File(...), 
    custom_filename: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a file to the server and then to tmpfiles.org.
    
    Args:
        file: The file to upload
        custom_filename: Optional custom filename to use
        
    Returns:
        JSON response with the tmpfiles.org URL and status
    """
    # Check if file exists
    if not file:
        return JSONResponse(
            status_code=400, 
            content={"message": "No file provided"}
        )
    
    # Check if uploaded file is audio
    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Please upload an audio file."
        )

    # Determine filename (use custom if provided, otherwise use original)
    original_filename = file.filename
    filename = secure_filename(custom_filename or original_filename)
    
    # Create upload directory if it doesn't exist
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Create file path
    file_path = os.path.join(upload_dir, filename)
    
    # Handle duplicates by adding a counter
    counter = 1
    while os.path.exists(file_path):
        name, ext = os.path.splitext(filename)
        file_path = os.path.join(upload_dir, f"{name}_{counter}{ext}")
        counter += 1
    
    # Save the file locally
    try:
        with open(file_path, "wb") as buffer:
            # Copy file content
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"Error saving file: {str(e)}"}
        )
    finally:
        # Make sure the file is closed
        file.file.close()
    
    # Local file details
    local_file_info = {
        "filename": os.path.basename(file_path),
        "original_filename": original_filename,
        "file_path": file_path,
        "file_size": os.path.getsize(file_path)
    }
    
    # Track upload in content management system
    user_id = str(current_user.get("_id", "unknown"))
    upload_id = await track_upload(
        user_id=user_id,
        file_name=os.path.basename(file_path),
        file_path=file_path,
        file_url="",  # Will be updated after tmpfiles upload
        file_type="audio",
        file_size=local_file_info["file_size"],
        status="pending",
        metadata={
            "content_type": file.content_type,
            "original_filename": original_filename
        }
    )
    
    # Now upload to tmpfiles.org
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
                    
                    # Update the upload record with the tmpfiles URL
                    if upload_id:
                        from utils.content_tracker import update_upload_status
                        await update_upload_status(
                            upload_id=upload_id,
                            status="uploaded",
                            file_url=url
                        )
                    
                    # We could remove the local file to save space, but keeping it for now
                    # os.remove(file_path)
                    return {
                        "status": "success", 
                        "url": url,
                        "local_file": local_file_info,
                        "upload_id": upload_id
                    }
                else:   
                    raise ValueError("Upload succeeded but no URL returned.")
            else:
                raise RuntimeError(f"Upload failed with status code {response.status_code}")
        except Exception as e:
            if attempt == max_retries:
                # If all retries fail, at least return the local file information
                return JSONResponse(
                    status_code=500, 
                    content={
                        "error": f"Upload to tmpfiles.org failed after {max_retries} attempts: {str(e)}",
                        "local_file": local_file_info,  # Still return local file info
                        "upload_id": upload_id
                    }
                )
            time.sleep(delay_seconds)
    