import os
import time
import requests
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from typing import List
from fastapi.responses import JSONResponse

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

    # Upload to tmpfiles.org
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
                    # os.remove(file_path)  # Commenting out to keep local file
                    return {"status": "success", "url": url}
                else:   
                    raise ValueError("Upload succeeded but no URL returned.")
            else:
                raise RuntimeError(f"Upload failed with status code {response.status_code}")
        except Exception as e:
            if attempt == max_retries:
                return JSONResponse(status_code=500, content={"error": f"Upload failed after {max_retries} attempts: {str(e)}"})
            time.sleep(delay_seconds)
    