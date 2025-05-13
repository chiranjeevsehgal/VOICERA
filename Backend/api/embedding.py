from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
import json
import tempfile
import os
from mutagen.id3 import ID3, TXXX
from mutagen.mp3 import MP3
import shutil
from typing import Dict, Any
import uuid
import base64

router = APIRouter()

OUTPUT_DIR = os.path.abspath(".")  # Path to store embedded file

def extract_metadata_from_mp3_to_json(file_path: str) -> Dict[str, Any]:
    """
    Extract ID3 metadata from an MP3 file and format it as transcription JSON.
    
    Args:
        file_path: Path to the MP3 file
        
    Returns:
        dict: Full transcription JSON structure with metadata
    """
    try:
        # Loading ID3 tags
        tags = ID3(file_path)
        
        # Checking if the JSON is stored in a TXXX tag
        for key in tags.keys():
            if key.startswith('TXXX:'):
                try:
                    # Decoding the tag content
                    encoded_data = str(tags[key])
                    # Checking if it's base64 encoded
                    if encoded_data.startswith('base64:'):
                        encoded_data = encoded_data[7:]  # Removing 'base64:' prefix
                        json_str = base64.b64decode(encoded_data).decode('utf-8')
                    else:
                        json_str = encoded_data
                    
                    # Tring to parse as JSON
                    json_data = json.loads(json_str)
                    
                    if isinstance(json_data, dict):
                        return json_data
                except:
                    pass
        
        # If we didn't find valid JSON in any TXXX tag.
        return {}
        
    except Exception as e:
        return {"error": f"Error while extracting: {str(e)}"}

@router.post("/extract")
async def extract_metadata(mp3_file: UploadFile = File(...)):
    """
    Endpoint to extract metadata FROM an MP3 file into a full transcription JSON.
    
    Args:
        mp3_file: The MP3 file to extract metadata from
        
    Returns:
        JSON response with full transcription JSON
    """
    # Checking if the file is valid
    if not mp3_file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    # Creating a temporary directory
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, secure_filename(mp3_file.filename))
    
    try:
        # Saving the uploaded file temporarily to parse
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(mp3_file.file, buffer)
        
        # Extracting metadata from the MP3
        extracted_json = extract_metadata_from_mp3_to_json(file_path)
        
        # Checking if there was an error during extraction
        if "error" in extracted_json:
            raise HTTPException(status_code=500, detail=extracted_json["error"])
            
        return JSONResponse(content=extracted_json)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")
        
    finally:
        # Cleaning up temporary files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

@router.post("/embed")
async def add_mp3_tags(
    mp3_file: UploadFile = File(...),
    metadata: str = Form(...)
):
    """
    Endpoint to add ID3v2 tags TO an MP3 file and save it to disk.
    
    Args:
        mp3_file: The MP3 file to modify
        metadata: JSON string containing metadata
        
    Returns:
        JSON with path to the saved file
    """
    # Checking if the file is valid
    if not mp3_file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    try:
        # Parsing metadata from JSON
        json_data = json.loads(metadata)
        
        # Validating that the metadata is in json form
        if not isinstance(json_data, dict):
            raise HTTPException(status_code=400, detail="Metadata must be a JSON object")
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON metadata")
    
    # Creating a temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, secure_filename(mp3_file.filename))
    
    try:
        # Saving the uploaded file temporarily
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(mp3_file.file, buffer)
        
        # Trying to load existing ID3 tags, or creating new ones if none
        try:
            tags = ID3(temp_file_path)
        except:
            # Creating new ID3 tags and associating them with the file
            tags = ID3()
            tags.save(temp_file_path)
            # Reloading the tags to ensure they're associated with the file
            tags = ID3(temp_file_path)
        
        # Encoding as base64 to avoid issues with special characters
        try:
            json_str = json.dumps(json_data)
            encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            tags['TXXX:transcription_json'] = TXXX(encoding=3, desc='transcription_json', text=f"base64:{encoded_json}")
        except Exception as e:
            # If encoding fails
            raise HTTPException(status_code=500, detail=f"Failed to encode metadata: {str(e)}")
        
        # Saving the tags to the file
        tags.save(temp_file_path)
        
        # Generating a unique filename to avoid overwriting
        file_name = secure_filename(mp3_file.filename)
        base_name, ext = os.path.splitext(file_name)
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"{base_name}_{unique_id}{ext}"
        
        # To verify OUTPUT_DIR exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Creating the output path in the root directory
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # Copying the modified file to the output location
        shutil.copy2(temp_file_path, output_path)
        
        # Returning the path to the saved file
        return JSONResponse(content={
            "success": True,
            "file_path": output_path,
            "file_name": output_filename,
            "message": f"File saved successfully at {output_path}"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add tags: {str(e)}")
        
    finally:
        # Cleaning up temporary files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)