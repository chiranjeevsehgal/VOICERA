from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
import os
import tempfile
import shutil
from werkzeug.utils import secure_filename
import time
from typing import Dict, Any
import uuid

from services.supabase_service import upload_file_to_supabase, list_files_in_bucket
from services.pinecone_service import index_transcript
from api.embedding import extract_metadata_from_mp3_to_json

router = APIRouter()

@router.post("/uploadToSupabase", status_code=201)
async def upload_to_supabase(file: UploadFile = File(...)):
    """
    Upload an audio file to Supabase storage.
    If the file is an MP3 with ID3 tags, the metadata will be preserved.
    The transcription data will also be indexed in Pinecone for search.
    
    Args:
        file (UploadFile): The audio file to upload
        
    Returns:
        JSON response with the Supabase URL and metadata
    """
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
        
        # Extract metadata if it's an MP3 file
        metadata = None
        if file.content_type == "audio/mpeg":
            try:
                extracted_data = extract_metadata_from_mp3_to_json(file_path)
                
                # Only use metadata if it doesn't contain an error
                if extracted_data and isinstance(extracted_data, dict) and "error" not in extracted_data:
                    metadata = extracted_data
                else:
                    # File doesn't have ID3 tags or extraction failed, but we continue with upload
                    metadata = {"info": "No ID3 metadata found in file"}
            except Exception as e:
                # Log the error but continue with the upload
                print(f"Failed to extract metadata: {str(e)}")
                metadata = {"info": "Failed to extract metadata"}
        
        # Upload the file to Supabase
        response = await upload_file_to_supabase(file_path, file.filename)
        
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
                    print(f"Warning: Failed to index transcript in Pinecone: {str(e)}")
                    response["indexed"] = False
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to Supabase: {str(e)}"
        )
    finally:
        # Clean up temporary files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

@router.get("/listSupabaseFiles")
async def list_supabase_files():
    """List all files stored in the Supabase bucket"""
    try:
        response = await list_files_in_bucket()
        return {"files": response}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        ) 