from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from werkzeug.utils import secure_filename
import json
import tempfile
import os
from mutagen.id3 import ID3, TXXX
from mutagen.mp3 import MP3
import shutil
from typing import Dict, Any, Optional
import uuid
import base64
import requests
from services.auth import get_current_user
from utils.logging import log_info, log_warning, log_error
router = APIRouter()
OUTPUT_DIR = os.path.abspath('.')

def extract_metadata_from_mp3_to_json(file_path: str) -> Dict[str, Any]:
    """
    Extract ID3 metadata from an MP3 file and format it as transcription JSON.

    Args:
        file_path: Path to the MP3 file

    Returns:
        dict: Full transcription JSON structure with metadata
    """
    try:
        tags = ID3(file_path)
        for key in tags.keys():
            if key.startswith('TXXX:'):
                try:
                    encoded_data = str(tags[key])
                    if encoded_data.startswith('base64:'):
                        encoded_data = encoded_data[7:]
                        json_str = base64.b64decode(encoded_data).decode('utf-8')
                    else:
                        json_str = encoded_data
                    json_data = json.loads(json_str)
                    if isinstance(json_data, dict):
                        return json_data
                except:
                    pass
        return {}
    except Exception as e:
        return {'error': f'Error while extracting: {str(e)}'}

@router.post('/extract')
async def extract_metadata(request: Request, mp3_file: UploadFile=File(None), mp3_url: Optional[str]=Form(None), current_user: dict=Depends(get_current_user)):
    """
    Endpoint to extract metadata FROM an MP3 file/URL into a full transcription JSON.

    Args:
        request: The request object to handle JSON body
        mp3_file: The MP3 file to extract metadata from (optional)
        mp3_url: URL of an MP3 file to extract metadata from (optional)

    Returns:
        JSON response with full transcription JSON
    """
    json_body = None
    try:
        if request.headers.get('content-type') == 'application/json':
            json_body = await request.json()
            if json_body and 'mp3_url' in json_body:
                mp3_url = json_body['mp3_url']
    except Exception:
        pass
    if not mp3_file and (not mp3_url):
        raise HTTPException(status_code=400, detail='Must provide either mp3_file or mp3_url')
    log_info(f"Extracting metadata from {('mp3_file' if mp3_file else 'mp3_url')}: {(mp3_url if mp3_url else mp3_file.filename)}", 'embedding', {'source_type': 'mp3_file' if mp3_file else 'mp3_url', 'source_filename': mp3_url if mp3_url else mp3_file.filename})
    temp_dir = tempfile.mkdtemp()
    try:
        if mp3_url:
            filename = secure_filename(os.path.basename(mp3_url)) or f'audio_{uuid.uuid4().hex}.mp3'
            file_path = os.path.join(temp_dir, filename)
            response = requests.get(mp3_url)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail='Failed to download MP3 from URL')
            with open(file_path, 'wb') as f:
                f.write(response.content)
        else:
            if not mp3_file.filename:
                raise HTTPException(status_code=400, detail='No file selected')
            file_path = os.path.join(temp_dir, secure_filename(mp3_file.filename))
            with open(file_path, 'wb') as buffer:
                shutil.copyfileobj(mp3_file.file, buffer)
        extracted_json = extract_metadata_from_mp3_to_json(file_path)
        if 'error' in extracted_json:
            raise HTTPException(status_code=500, detail=extracted_json['error'])
        return JSONResponse(content=extracted_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to extract metadata: {str(e)}')
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

@router.post('/embed')
async def add_mp3_tags(mp3_file: UploadFile=File(...), metadata: str=Form(...), current_user: dict=Depends(get_current_user)):
    """
    Endpoint to add ID3v2 tags TO an MP3 file and save it to disk.

    Args:
        mp3_file: The MP3 file to modify
        metadata: JSON string containing metadata

    Returns:
        JSON with path to the saved file
    """
    if not mp3_file.filename:
        raise HTTPException(status_code=400, detail='No file selected')
    try:
        json_data = json.loads(metadata)
        if not isinstance(json_data, dict):
            raise HTTPException(status_code=400, detail='Metadata must be a JSON object')
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid JSON metadata')
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, secure_filename(mp3_file.filename))
    try:
        with open(temp_file_path, 'wb') as buffer:
            shutil.copyfileobj(mp3_file.file, buffer)
        try:
            tags = ID3(temp_file_path)
        except:
            tags = ID3()
            tags.save(temp_file_path)
            tags = ID3(temp_file_path)
        try:
            json_str = json.dumps(json_data)
            encoded_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            tags['TXXX:transcription_json'] = TXXX(encoding=3, desc='transcription_json', text=f'base64:{encoded_json}')
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Failed to encode metadata: {str(e)}')
        tags.save(temp_file_path)
        file_name = secure_filename(mp3_file.filename)
        base_name, ext = os.path.splitext(file_name)
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f'{base_name}_{unique_id}{ext}'
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        shutil.copy2(temp_file_path, output_path)
        return JSONResponse(content={'success': True, 'file_path': output_path, 'file_name': output_filename, 'message': f'File saved successfully at {output_path}'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to add tags: {str(e)}')
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)