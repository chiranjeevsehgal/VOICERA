from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Query
import os
import tempfile
import shutil
from werkzeug.utils import secure_filename
import time
from typing import Dict, Any, Optional
import json
from services.supabase_service import upload_file_to_supabase
from services.pinecone_service import index_transcript
from api.embedding import extract_metadata_from_mp3_to_json
from services.auth import get_current_user
from services.database import podcasts_collection
from bson.objectid import ObjectId
from utils.logging import log_info, log_warning, log_error
router = APIRouter()

@router.post('/uploadToSupabase', status_code=201)
async def upload_to_supabase(file: UploadFile=File(...), current_user: dict=Depends(get_current_user)):
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
    log_info(f'Upload request received. Current user: {json.dumps(current_user, default=str)}', 'supabase_upload', {'user_id': str(current_user.get('_id', 'unknown'))})
    AUDIO_MIME_TYPES = ['audio/mpeg']
    if file.content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Unsupported file type: {file.content_type}. Please upload an audio file.')
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, secure_filename(file.filename))
    try:
        with open(file_path, 'wb') as buffer:
            content = await file.read()
            buffer.write(content)
        log_info(f'File saved temporarily at: {file_path}', 'supabase_upload', {'file_path': file_path})
        metadata = None
        if file.content_type == 'audio/mpeg':
            try:
                extracted_data = extract_metadata_from_mp3_to_json(file_path)
                if extracted_data and isinstance(extracted_data, dict) and ('error' not in extracted_data):
                    metadata = extracted_data
                else:
                    metadata = {'info': 'No ID3 metadata found in file'}
            except Exception as e:
                log_warning(f'Metadata extraction failed: {str(e)}', 'supabase_upload', {'error': str(e)})
                metadata = {'info': 'Failed to extract metadata'}
        user_id = current_user.get('_id')
        log_info(f'Extracted user_id from current_user: {user_id}', 'supabase_upload', {'user_id': str(user_id)})
        response = await upload_file_to_supabase(file_path=file_path, file_name=file.filename, user_id=user_id, bucket_name=os.getenv('SUPABASE_BUCKET_ORIGINAL'))
        log_info(f'Upload response received: {json.dumps(response, default=str)}', 'supabase_upload', {'response': response})
        if metadata and isinstance(metadata, dict):
            response['metadata'] = metadata
            if 'results' in metadata:
                try:
                    await index_transcript(transcript_data=metadata, file_url=response.get('file_url', ''), file_name=response.get('file_name', ''))
                    response['indexed'] = True
                except Exception as e:
                    log_error(f'Failed to index transcript: {str(e)}', 'supabase_upload', {'error': str(e)})
                    response['indexed'] = False
        return response
    except Exception as e:
        log_error(f'Upload failed with error: {str(e)}', 'supabase_upload', {'error': str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Failed to upload file to Supabase: {str(e)}')
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            log_info('Temporary files cleaned up', 'supabase_upload')

@router.get('/listAudioFiles')
async def list_audio_files(current_user: dict=Depends(get_current_user), user_files_only: bool=False, page: int=1, limit: Optional[int]=Query(None, ge=1, le=100, description='Items per page (default 10)'), search: Optional[str]=Query(None, description='Search in title, author, or file name')):
    """
    List podcasts from MongoDB collection

    Args:
        current_user (dict): The authenticated user information
        user_files_only (bool): If True, only return files uploaded by the current user
        page (int): Page number for pagination
    """
    try:
        per_page = limit or 10
        skip = (page - 1) * per_page
        query_filter: Dict[str, Any] = {}
        if user_files_only:
            user_id = current_user.get('id') or current_user.get('_id') or (current_user.get('_id', {}).get('$oid') if isinstance(current_user.get('_id'), dict) else None)
            if user_id:
                if isinstance(user_id, str):
                    try:
                        user_id = ObjectId(user_id)
                    except Exception:
                        pass
                query_filter['user_id'] = user_id
        if search:
            query_filter['$or'] = [{'title': {'$regex': search, '$options': 'i'}}, {'author': {'$regex': search, '$options': 'i'}}, {'file_name': {'$regex': search, '$options': 'i'}}, {'user_data.file_name': {'$regex': search, '$options': 'i'}}]
        cursor = podcasts_collection.find(query_filter).sort('created_at', -1).skip(skip).limit(per_page + 1)
        podcasts_list = await cursor.to_list(length=per_page + 1)
        has_next = len(podcasts_list) > per_page
        podcasts = podcasts_list[:per_page]
        for podcast in podcasts:
            podcast['_id'] = str(podcast['_id'])
            if 'upload_id' in podcast and isinstance(podcast['upload_id'], ObjectId):
                podcast['upload_id'] = str(podcast['upload_id'])
            if 'user_id' in podcast and isinstance(podcast['user_id'], ObjectId):
                podcast['user_id'] = str(podcast['user_id'])
        return {'files': podcasts, 'page': page, 'limit': per_page, 'has_next': has_next, 'total_count': await podcasts_collection.count_documents(query_filter)}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Failed to list podcasts: {str(e)}')