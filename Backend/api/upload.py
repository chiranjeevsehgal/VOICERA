import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from typing import List, Optional
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
from services.auth import get_current_user
from utils.content_tracker import track_upload
from services.supabase_service import upload_file_to_supabase

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
    Upload an audio file to the server and then to Supabase storage.
    
    Args:
        file: The audio file to upload
        custom_filename: Optional custom filename to use
        
    Returns:
        JSON response with the Supabase URL and status
    """
    # Define max file size (50 MB)
    MAX_FILE_SIZE_MB = 50
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024 # Convert MB to bytes

    # Read file content into memory to check size
    file_content = await file.read()
    await file.seek(0) # Reset file pointer after reading

    # Check if file exists
    if not file:
        return JSONResponse(
            status_code=400, 
            content={"message": "No file provided"}
        )
    
    # Check file size
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the limit of {MAX_FILE_SIZE_MB}MB."
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
            buffer.write(file_content) # Write the content already read into memory
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"Error saving file: {str(e)}"}
        )
    finally:
        # Make sure the file is closed (if it was opened by FastAPI, it will be closed automatically)
        # No need to explicitly close file.file here as we read it into memory
        pass
    
    # Local file details
    local_file_info = {
        "filename": os.path.basename(file_path),
        "original_filename": original_filename,
        "file_path": file_path,
        "file_size": len(file_content) # Use len(file_content) for size
    }
    
    # Track upload in content management system
    user_id = str(current_user.get("_id", "unknown"))
    upload_id = await track_upload(
        user_id=user_id,
        file_name=os.path.basename(file_path),
        file_path=file_path,
        file_type="audio",
        file_size=local_file_info["file_size"],
        metadata={
            "content_type": file.content_type,
            "original_filename": original_filename
        }
    )
    
    # Upload to Supabase storage
    try:
        response = await upload_file_to_supabase(
            file_path=file_path,
            file_name=filename,
            user_id=str(current_user.get("_id", "unknown"))
        )
        
        if not response or "file_url" not in response:
            raise ValueError("Supabase upload failed - no URL returned")
            
        # Update the upload record with the Supabase URL
        if upload_id:
            from utils.content_tracker import update_upload_status
            await update_upload_status(
                upload_id=upload_id,
                status="uploaded",
                supabase_url=response["file_url"]
            )
            
        return {
            "status": "success",
            "url": response["file_url"],
            "local_file": local_file_info,
            "upload_id": upload_id
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Upload to Supabase failed: {str(e)}",
                "local_file": local_file_info,
                "upload_id": upload_id
            }
        )
