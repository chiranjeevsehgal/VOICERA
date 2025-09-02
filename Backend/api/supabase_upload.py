from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import os
import tempfile
import shutil
from werkzeug.utils import secure_filename
import time
from typing import Dict, Any
import uuid
import json

from services.supabase_service import upload_file_to_supabase, list_files_in_bucket
from services.pinecone_service import index_transcript
from api.embedding import extract_metadata_from_mp3_to_json
from services.auth import get_current_user

router = APIRouter()

@router.post("/uploadToSupabase", status_code=201)
async def upload_to_supabase(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload an audio file to Supabase storage.
    If the file is an MP3 with ID3 tags, the metadata will be preserved.
    The transcription data will also be indexed in Pinecone for search.
    The file ownership will be tracked in the database.
    
    Args:
        file (UploadFile): The audio file to upload
        current_user (dict): The authenticated user information
        
    Returns:
        JSON response with the Supabase URL, metadata, and user information
    """
    print(f"[DEBUG] Upload request received. Current user: {json.dumps(current_user, default=str)}")
    
    # Check if uploaded file is an MP3
    AUDIO_MIME_TYPES = ["audio/mpeg"]
    
    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Please upload an audio file."
        )

    # Create temporary directory to store the file
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, secure_filename(file.filename))
    
    try:
        # Save the uploaded file temporarily
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        print(f"[DEBUG] File saved temporarily at: {file_path}")
        
        # Extract metadata if it's an MP3 file
        metadata = None
        if file.content_type == "audio/mpeg":
            try:
                extracted_data = extract_metadata_from_mp3_to_json(file_path)
                
                # Only use metadata if it doesn't contain an error
                if extracted_data and isinstance(extracted_data, dict) and "error" not in extracted_data:
                    metadata = extracted_data
                else:
                    metadata = {"info": "No ID3 metadata found in file"}
            except Exception as e:
                print(f"[DEBUG] Metadata extraction failed: {str(e)}")
                metadata = {"info": "Failed to extract metadata"}
        
        # Get user ID from current_user
        user_id = current_user.get("_id")
        print(f"[DEBUG] Extracted user_id from current_user: {user_id}")
        
        # Upload the file to Supabase with user information
        response = await upload_file_to_supabase(
            file_path=file_path, 
            file_name=file.filename,
            user_id=user_id,
            bucket_name=os.getenv("SUPABASE_BUCKET_ORIGINAL")
        )
        
        print(f"[DEBUG] Upload response received: {json.dumps(response, default=str)}")
        
        # Add metadata to the response if available
        if metadata and isinstance(metadata, dict):
            response["metadata"] = metadata
            
            # Index the transcript in Pinecone for search
            if "results" in metadata:
                try:
                    await index_transcript(
                        transcript_data=metadata,
                        file_url=response.get("file_url", ""),
                        file_name=response.get("file_name", "")
                    )
                    response["indexed"] = True
                except Exception as e:
                    print(f"[DEBUG] Failed to index transcript: {str(e)}")
                    response["indexed"] = False
        
        return response
        
    except Exception as e:
        print(f"[DEBUG] Upload failed with error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to Supabase: {str(e)}"
        )
    finally:
        # Clean up temporary files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print("[DEBUG] Temporary files cleaned up")

@router.get("/listAudioFiles")
async def list_audio_files(
    current_user: dict = Depends(get_current_user),
    user_files_only: bool = False
):
    """
    List files stored in the Supabase bucket
    
    Args:
        current_user (dict): The authenticated user information
        user_files_only (bool): If True, only return files uploaded by the current user
    """
    try:
        user_id = current_user["id"] if user_files_only else None
        response = await list_files_in_bucket(user_id=user_id, bucket_name=os.getenv("SUPABASE_BUCKET_EMBEDDED"))
        return {"files": response}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        ) 