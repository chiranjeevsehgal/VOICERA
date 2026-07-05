import os
from supabase import create_client, Client
from dotenv import load_dotenv
import uuid
from bson import ObjectId
import json
from services.database import users_collection
from utils.logging import log_info, log_warning, log_error
load_dotenv()
supabase_url = os.getenv('SUPABASE_URL')
supabase_service_role_key = None
supabase_key = os.getenv('SUPABASE_KEY')
supabase_bucket = os.getenv('SUPABASE_BUCKET', 'audiofiles')
supabase_bucket_original = os.getenv('SUPABASE_BUCKET_ORIGINAL', supabase_bucket)
supabase_bucket_embedded = os.getenv('SUPABASE_BUCKET_EMBEDDED', supabase_bucket)
supabase: Client = None

def init_supabase():
    """Initialize Supabase client if environment variables are set"""
    global supabase
    if supabase_url and supabase_key:
        try:
            supabase = create_client(supabase_url, supabase_key)
            key_mode = 'anon'
            log_info(f'Supabase client initialized ({key_mode} key). Default bucket: {supabase_bucket}; original: {supabase_bucket_original}; embedded: {supabase_bucket_embedded}', 'supabase_service', {'key_mode': key_mode, 'default_bucket': supabase_bucket, 'original_bucket': supabase_bucket_original, 'embedded_bucket': supabase_bucket_embedded})
        except Exception as e:
            log_warning(f'Failed to initialize Supabase client: {str(e)}', 'supabase_service', {'error': str(e)})
    else:
        log_warning('Supabase environment variables not set. Storage functionality disabled.', 'supabase_service')
init_supabase()

async def upload_file_to_supabase(file_path, file_name=None, user_id=None, bucket_name: str=None):
    """
    Upload a file to Supabase storage and track user ownership

    Args:
        file_path (str): Path to the file to upload
        file_name (str, optional): Custom filename for the uploaded file
        user_id (str/ObjectId, optional): ID of the user uploading the file

    Returns:
        dict: Response with file URL and metadata
    """
    if not supabase:
        raise ValueError('Supabase client not initialized. Check your environment variables.')
    log_info(f'Starting upload process with user_id: {user_id}, type: {type(user_id)}', 'supabase_service', {'user_id': str(user_id), 'user_id_type': str(type(user_id))})
    if not file_name:
        file_name = os.path.basename(file_path)
    unique_id = str(uuid.uuid4())[:8]
    base_name, ext = os.path.splitext(file_name)
    unique_file_name = f'{base_name}_{unique_id}{ext}'
    file_path_in_bucket = f'public/{unique_file_name}'
    selected_bucket = bucket_name or supabase_bucket
    try:
        with open(file_path, 'rb') as f:
            file_contents = f.read()
        log_info(f'File read successfully: {file_path}', 'supabase_service', {'file_path': file_path})
        response = supabase.storage.from_(selected_bucket).upload(path=file_path_in_bucket, file=file_contents, file_options={'content-type': 'audio/mpeg'})
        log_info(f'Storage upload response: {response}', 'supabase_service', {'response': str(response)})
        file_url = supabase.storage.from_(selected_bucket).get_public_url(file_path_in_bucket)
        try:
            if isinstance(file_url, str) and file_url.endswith('?'):
                file_url = file_url[:-1]
        except Exception:
            pass
        result = {'success': True, 'file_name': unique_file_name, 'file_path': file_path_in_bucket, 'file_url': file_url, 'bucket': selected_bucket}
        if user_id:
            log_info(f'Processing user_id: {user_id}, type: {type(user_id)}', 'supabase_service', {'user_id': str(user_id), 'user_id_type': str(type(user_id))})
            if isinstance(user_id, ObjectId):
                user_id = str(user_id)
            elif isinstance(user_id, dict) and '_id' in user_id:
                user_id = str(user_id['_id'])
            try:
                upload_data = {'user_id': user_id, 'file_name': unique_file_name, 'file_path': file_path_in_bucket, 'file_url': file_url, 'metadata': {}}
                log_info(f'Attempting to insert user_upload data: {json.dumps(upload_data, default=str)}', 'supabase_service', {'upload_data': upload_data})
                db_response = supabase.table('user_uploads').insert(upload_data).execute()
                log_info(f"Database insert response: {json.dumps(db_response.data if db_response.data else 'No data', default=str)}", 'supabase_service', {'response_data': db_response.data if db_response.data else None})
                if db_response.data:
                    result['user_upload'] = db_response.data[0]
                    log_info('Successfully recorded user upload', 'supabase_service')
                else:
                    log_warning('No data returned from user_uploads insert', 'supabase_service')
                    result['user_upload_warning'] = 'No data returned from insert'
            except Exception as e:
                log_error(f'Failed to record user upload: {str(e)}', 'supabase_service', {'error': str(e)})
                result['user_upload_error'] = str(e)
        return result
    except Exception as e:
        log_error(f'Upload failed with error: {str(e)}', 'supabase_service', {'error': str(e)})
        raise ValueError(f'Failed to upload file: {str(e)}')

async def list_files_in_bucket(user_id=None, bucket_name: str=None, folder: str='public', page: int=1, limit: int=10, sort_column: str='updated_at', sort_order: str='desc'):
    """
    List files in the storage bucket with user information, with pagination.

    Args:
        user_id (str, optional): If provided, only list files uploaded by this user
        bucket_name (str, optional): Supabase bucket name
        folder (str): Folder path to list (default: "public")
        page (int): 1-based page number (default: 1)
        limit (int): Max items per page (default: 10)
        sort_column (str): Column to sort by in storage (default: "updated_at")
        sort_order (str): Sort order, "asc" or "desc" (default: "desc")
    """
    if not supabase:
        raise ValueError('Supabase client not initialized. Check your environment variables.')
    try:
        selected_bucket = bucket_name or supabase_bucket
        safe_page = max(1, int(page) if isinstance(page, int) else 1)
        safe_limit = max(1, int(limit) if isinstance(limit, int) else 10)
        offset = (safe_page - 1) * safe_limit
        storage_files = supabase.storage.from_(selected_bucket).list(folder, {'limit': safe_limit, 'offset': offset, 'sortBy': {'column': sort_column, 'order': sort_order}})
        query = supabase.table('user_uploads').select('*')
        if user_id:
            if isinstance(user_id, ObjectId):
                user_id = str(user_id)
            elif isinstance(user_id, dict) and '_id' in user_id:
                user_id = str(user_id['_id'])
            query = query.eq('user_id', user_id)
        user_uploads = query.execute()
        user_upload_map = {}
        if user_uploads.data:
            for upload in user_uploads.data:
                try:
                    user_obj_id = ObjectId(upload['user_id'])
                    user = await users_collection.find_one({'_id': user_obj_id})
                    if user:
                        upload['user_details'] = {'email': user.get('email'), 'full_name': user.get('full_name')}
                except Exception as e:
                    log_warning(f"Failed to get user details for {upload['user_id']}: {str(e)}", 'supabase_service', {'user_id': upload['user_id'], 'error': str(e)})
                    upload['user_details'] = {'error': 'User not found'}
                user_upload_map[upload['file_name']] = upload
        enriched_files = []
        for file in storage_files:
            file_data = dict(file)
            if file['name'] in user_upload_map:
                file_data['user_data'] = user_upload_map[file['name']]
            enriched_files.append(file_data)
        return enriched_files
    except Exception as e:
        log_error(f'Error listing files: {str(e)}', 'supabase_service', {'error': str(e)})
        return []

async def delete_file_from_supabase(file_name, bucket_name: str=None):
    """Delete a file from Supabase storage"""
    if not supabase:
        raise ValueError('Supabase client not initialized. Check your environment variables.')
    if not file_name.startswith('public/'):
        file_name = f'public/{file_name}'
    selected_bucket = bucket_name or supabase_bucket
    try:
        response = supabase.storage.from_(selected_bucket).remove([file_name])
        if response and len(response) > 0:
            return {'success': True, 'message': f'File {file_name} deleted from {selected_bucket}', 'response': response}
        else:
            return {'success': False, 'message': f'Failed to delete {file_name} from {selected_bucket} - no response', 'response': response}
    except Exception as e:
        return {'success': False, 'message': f'Error deleting {file_name}: {str(e)}', 'response': None}