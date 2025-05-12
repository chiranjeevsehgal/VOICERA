import os
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from typing import List

router = APIRouter()

AUDIO_MIME_TYPES = [
    "audio/mpeg", 
    "audio/wav", 
    "audio/ogg", 
    "audio/x-wav", 
    "audio/x-m4a",
    "audio/mp4"
]
UPLOAD_DIR = "audio_uploads"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", status_code=201)
async def upload_audio(file: UploadFile = File(...)):
    # Check if uploaded file is audio
    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Please upload an audio file."
        )

    # Sanitize and construct file path
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # Save the file
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 2nd process will start and if the process is successful, delete the file
    # os.remove(file_path)  # Uncomment this line to delete the file after processing
    
    # Return file information
    return {"filename": file.filename, "size_bytes": len(content)}
