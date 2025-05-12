from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
import tempfile
import os
import json
from typing import Dict, Any, Optional
import shutil

from services.steganography import AudioSteganography
from models.steganography import SteganographyRequest, SteganographyResponse

router = APIRouter(prefix="/steganography", tags=["steganography"])
stego_service = AudioSteganography()

@router.post("/embed", response_model=SteganographyResponse)
async def embed_metadata(
    audio_file: UploadFile = File(...),
    metadata: str = Form(...),  # JSON string
    method: str = Form("lsb")
):
    """
    Embed metadata into an audio file using steganography.
    
    - **audio_file**: The audio file to embed metadata into
    - **metadata**: JSON string containing metadata to embed
    - **method**: Steganography method to use (lsb, echo, phase)
    """
    try:
        # Parse metadata JSON
        metadata_dict = json.loads(metadata)
        
        # Create a temporary file to store the uploaded audio
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file_path = temp_file.name
        
        # Save uploaded file to the temporary file
        with temp_file:
            shutil.copyfileobj(audio_file.file, temp_file)
        
        # Process the audio file with steganography
        with open(temp_file_path, "rb") as audio:
            output_path, _ = stego_service.embed_metadata(
                audio, metadata_dict, method=method
            )
        
        # Clean up the temporary input file
        os.unlink(temp_file_path)
        
        return {
            "success": True,
            "method": method,
            "file_path": output_path,
            "metadata_size": len(metadata),
            "message": "Metadata successfully embedded"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON metadata")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Ensure file is closed
        audio_file.file.close()

@router.post("/extract")
async def extract_metadata(
    audio_file: UploadFile = File(...),
    method: str = Form("lsb")
):
    """
    Extract metadata from an audio file using steganography.
    
    - **audio_file**: The audio file to extract metadata from
    - **method**: Steganography method used (lsb, echo, phase)
    """
    try:
        # Create a temporary file to store the uploaded audio
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file_path = temp_file.name
        
        # Save uploaded file to the temporary file
        with temp_file:
            shutil.copyfileobj(audio_file.file, temp_file)
        
        # Extract metadata from the audio file
        with open(temp_file_path, "rb") as audio:
            metadata = stego_service.extract_metadata(audio, method=method)
        
        # Clean up the temporary file
        os.unlink(temp_file_path)
        
        return {
            "success": True,
            "method": method,
            "metadata": metadata
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Ensure file is closed
        audio_file.file.close()

@router.post("/process-audio")
async def process_audio(
    audio_file: UploadFile = File(...),
    transcription: str = Form(...),
    metadata: str = Form(...),  # JSON string
    method: str = Form("lsb")
):
    """
    Process an audio file by embedding essential metadata.
    
    - **audio_file**: The audio file to process
    - **transcription**: Text transcription of the audio
    - **metadata**: JSON string containing metadata
    - **method**: Steganography method to use
    """
    try:
        # Parse metadata JSON
        metadata_dict = json.loads(metadata)
        
        # Create a temporary file to store the uploaded audio
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file_path = temp_file.name
        
        # Save uploaded file to the temporary file
        with temp_file:
            shutil.copyfileobj(audio_file.file, temp_file)
        
        # Process the audio file
        output_path = stego_service.process_audio_with_steganography(
            temp_file_path, transcription, metadata_dict, method
        )
        
        # Clean up the temporary input file
        if os.path.exists(temp_file_path) and temp_file_path != output_path:
            os.unlink(temp_file_path)
        
        return FileResponse(
            path=output_path, 
            filename=os.path.basename(output_path),
            media_type="audio/wav"
        )
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON metadata")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Ensure file is closed
        audio_file.file.close()