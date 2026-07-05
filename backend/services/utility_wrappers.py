import asyncio
import requests
import json
import os
import shutil
import time
from typing import Dict, Any, Optional
from datetime import datetime
from bson.objectid import ObjectId
from dotenv import load_dotenv
from mutagen.id3 import ID3, TXXX
import base64
from fastapi.responses import JSONResponse
from utils.logging import log_info, log_warning, log_error

async def check_user_credits_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Check user credits from the credit management API"""
    from api.credit_management import check_credits

    class DummyRequest:

        def __init__(self):
            self.client = None
            self.headers = {}
    dummy_request = DummyRequest()
    log_info(f'Checking credits for IP: {ip}', 'utility_wrappers', {'ip': ip})
    try:
        response = await check_credits(dummy_request, ip, current_user)
        log_info(f'Raw credit response: {response}', 'utility_wrappers', {'response_type': type(response).__name__})
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode('utf-8'))
                log_info(f'Parsed JSONResponse: {response_dict}', 'utility_wrappers', {'response_dict': response_dict})
                return response_dict
            except Exception as e:
                log_error(f'Error parsing JSONResponse: {str(e)}', 'utility_wrappers', {'error': str(e)})
                return {'credits_remaining': 100, 'ip_address': ip, 'status': 'default'}
        log_info(f'Direct dict response: {response}', 'utility_wrappers', {'response': response})
        return response
    except Exception as e:
        log_error(f'Exception in check_user_credits_async: {str(e)}', 'utility_wrappers', {'error': str(e), 'ip': ip})
        return {'credits_remaining': 100, 'ip_address': ip, 'status': 'exception_default'}

async def deduct_user_credit_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Deduct a credit using the credit management API"""
    from api.credit_management import deduct_credit

    class DummyRequest:

        def __init__(self):
            self.client = None
            self.headers = {}
    dummy_request = DummyRequest()
    log_info(f'Deducting credit for IP: {ip}', 'utility_wrappers', {'ip': ip})
    try:
        response = await deduct_credit(dummy_request, ip, current_user)
        log_info(f'Raw deduct credit response: {response}', 'utility_wrappers', {'response_type': type(response).__name__})
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode('utf-8'))
                log_info(f'Parsed JSONResponse for credit deduction: {response_dict}', 'utility_wrappers', {'response_dict': response_dict})
                return response_dict
            except Exception as e:
                log_error(f'Error parsing JSONResponse for credit deduction: {str(e)}', 'utility_wrappers', {'error': str(e)})
                return {'status': True, 'credits_remaining': 0, 'ip_address': ip, 'status': 'default'}
        log_info(f'Direct dict response for credit deduction: {response}', 'utility_wrappers', {'response': response})
        return response
    except Exception as e:
        log_error(f'Exception in deduct_user_credit_async: {str(e)}', 'utility_wrappers', {'error': str(e), 'ip': ip})
        return {'status': True, 'credits_remaining': 0, 'ip_address': ip, 'status': 'exception_default'}

async def transcribe_audio_async(audio_url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """Transcribe the audio using the Deepgram API through the transcribe endpoint"""
    from api.transcribe import TranscriptionRequest, transcribe_audio
    request_data = {'url': audio_url, **options}
    transcription_request = TranscriptionRequest(**request_data)
    current_user = {}
    return await transcribe_audio(transcription_request, current_user)

async def embed_metadata_in_file_async(src_file: str, dest_file: str, metadata_json: str) -> str:
    """Embed the metadata into the audio file using ID3 tags"""
    shutil.copy2(src_file, dest_file)
    try:
        try:
            tags = ID3(dest_file)
        except Exception:
            tags = ID3()
            tags.save(dest_file)
            tags = ID3(dest_file)
        encoded_json = base64.b64encode(metadata_json.encode('utf-8')).decode('utf-8')
        tags['TXXX:transcription_json'] = TXXX(encoding=3, desc='transcription_json', text=f'base64:{encoded_json}')
        tags.save(dest_file)
        return dest_file
    except Exception as e:
        log_error(f'Error embedding metadata: {str(e)}', 'utility_wrappers', {'error': str(e), 'src_file': src_file})
        return src_file

async def upload_to_supabase_async(file_path: str, filename: str, user_id: str=None, bucket_name: str=None) -> Dict[str, Any]:
    """Upload file to Supabase"""
    from services.supabase_service import upload_file_to_supabase
    result = await upload_file_to_supabase(file_path, filename, user_id, bucket_name=bucket_name)
    return result

def sync_check_credits(ip: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit check API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    try:
        load_dotenv()
        api_base_url = os.getenv('BACKEND_URL')
        credit_api_url = f'{api_base_url}/api/check-credits'
        access_token = None
        if current_user and 'auth_token' in current_user:
            access_token = current_user.get('auth_token')
            log_info('Using JWT token from original request', 'utility_wrappers')
        if not access_token:
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
            admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
            try:
                login_url = f'{api_base_url}/api/auth/login'
                login_data = {'username': admin_email, 'password': admin_password}
                login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                login_response = requests.post(login_url, data=login_data, headers=login_headers, timeout=10)
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get('access_token')
                    log_info('Successfully got access token via admin login', 'utility_wrappers')
                else:
                    log_error(f'Admin login failed: {login_response.status_code} - {login_response.text}', 'utility_wrappers', {'status_code': login_response.status_code, 'response': login_response.text})
            except Exception as e:
                log_error(f'Error during admin login: {str(e)}', 'utility_wrappers', {'error': str(e)})
        headers = {'Content-Type': 'application/json', 'X-Client-IP': ip}
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            client_ip_token = os.getenv('CLIENT_IP_HEADER_TOKEN')
            if client_ip_token:
                headers['X-Client-IP-Token'] = client_ip_token
            log_info(f'Using Authorization header: Bearer {access_token[:10]}...', 'utility_wrappers')
        else:
            log_warning('No access token available for credit API call', 'utility_wrappers')
            return {'credits_remaining': 100, 'ip_address': ip, 'status': 'default'}
        log_info(f'Making direct HTTP request to {credit_api_url} for IP {ip}', 'utility_wrappers', {'url': credit_api_url, 'ip': ip})
        response = requests.get(credit_api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            log_error(f'Credit API returned status code {response.status_code}: {response.text}', 'utility_wrappers', {'status_code': response.status_code, 'response': response.text})
            return {'credits_remaining': 100, 'ip_address': ip, 'status': 'error_response'}
    except requests.exceptions.Timeout:
        log_warning('Credit API request timed out after 10s', 'utility_wrappers')
        return {'credits_remaining': 100, 'ip_address': ip, 'status': 'timeout_default'}
    except Exception as e:
        log_error(f'Error calling credit API: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return {'credits_remaining': 100, 'ip_address': ip, 'status': 'exception_default'}

def sync_transcribe_audio(audio_url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for transcribing audio"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(transcribe_audio_async(audio_url, options))
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_transcribe_audio: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return {'error': str(e)}

def sync_embed_metadata(src_file: str, dest_file: str, metadata_json: str) -> str:
    """Synchronous wrapper for embedding metadata"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(embed_metadata_in_file_async(src_file, dest_file, metadata_json))
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_embed_metadata: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return src_file

def sync_upload_to_supabase(file_path: str, filename: str, user_id: str=None, bucket_name: str=None) -> Dict[str, Any]:
    """Synchronous wrapper for uploading to Supabase"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(upload_to_supabase_async(file_path, filename, user_id, bucket_name))
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_upload_to_supabase: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return {'error': str(e), 'file_name': filename}

def sync_delete_from_supabase(name_or_path: str, bucket_name: str=None) -> Dict[str, Any]:
    """Synchronous wrapper for deleting a file from Supabase storage"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from services.supabase_service import delete_file_from_supabase
        result = loop.run_until_complete(delete_file_from_supabase(name_or_path, bucket_name=bucket_name))
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_delete_from_supabase: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return {'success': False, 'error': str(e)}

def sync_index_transcript(transcript_data: Dict[str, Any], file_url: str, file_name: str, is_permanent_url: bool=False) -> bool:
    """
    Synchronous wrapper for indexing transcript in Pinecone

    Args:
        transcript_data: The transcription data
        file_url: URL to the audio file
        file_name: Name of the audio file
        is_permanent_url: Whether the URL is permanent (Supabase) or temporary (tmpfiles)
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from services.pinecone_service import index_transcript
        result = loop.run_until_complete(index_transcript(transcript_data=transcript_data, file_url=file_url, file_name=file_name, is_permanent_url=is_permanent_url))
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_index_transcript: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return False

def sync_update_podcast_url(podcast_id: str, supabase_url: str) -> bool:
    """
    Update a podcast record's audio_url to the permanent embedded Supabase URL.
    Also remove any legacy supabase_url field.

    Args:
        podcast_id: ID of the podcast to update
        supabase_url: Permanent embedded Supabase URL to set on audio_url
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from services.database import podcasts_collection

        async def update_podcast():
            result = await podcasts_collection.update_one({'_id': ObjectId(podcast_id)}, {'$set': {'audio_url': supabase_url, 'updated_at': datetime.utcnow()}, '$unset': {'supabase_url': ''}})
            return result.modified_count > 0
        result = loop.run_until_complete(update_podcast())
        loop.close()
        return result
    except Exception as e:
        log_error(f'Error in sync_update_podcast_url: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return False

def direct_deduct_credit(ip_address: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    try:
        load_dotenv()
        api_base_url = os.getenv('BACKEND_URL')
        credit_api_url = f'{api_base_url}/api/credit'
        log_info(f"Current user object keys for credit API: {(current_user.keys() if current_user else 'None')}", 'utility_wrappers', {'user_keys': list(current_user.keys()) if current_user else None})
        access_token = None
        if current_user and 'auth_token' in current_user:
            access_token = current_user.get('auth_token')
            log_info('Using JWT token from original request', 'utility_wrappers')
        if not access_token:
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
            admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
            try:
                login_url = f'{api_base_url}/api/auth/login'
                login_data = {'username': admin_email, 'password': admin_password}
                login_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                login_response = requests.post(login_url, data=login_data, headers=login_headers, timeout=10)
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get('access_token')
                    log_info('Successfully got access token via admin login', 'utility_wrappers')
                else:
                    log_error(f'Admin login failed: {login_response.status_code} - {login_response.text}', 'utility_wrappers', {'status_code': login_response.status_code, 'response': login_response.text})
            except requests.exceptions.Timeout:
                log_warning('Admin login request timed out after 10s', 'utility_wrappers')
            except Exception as e:
                log_error(f'Error during admin login: {str(e)}', 'utility_wrappers', {'error': str(e)})
        headers = {'Content-Type': 'application/json', 'X-Client-IP': ip_address}
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            client_ip_token = os.getenv('CLIENT_IP_HEADER_TOKEN')
            if client_ip_token:
                headers['X-Client-IP-Token'] = client_ip_token
            log_info(f'Using Authorization header: Bearer {access_token[:10]}...', 'utility_wrappers')
        else:
            log_warning('No access token available for credit API call', 'utility_wrappers')
            return {'status': False, 'detail': 'No authentication token available', 'credits_remaining': 0}
        data = {'ip': ip_address}
        log_info(f'Making direct HTTP request to {credit_api_url} for IP {ip_address}', 'utility_wrappers', {'url': credit_api_url, 'ip': ip_address})
        response = requests.post(credit_api_url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            log_error(f'Credit API returned status code {response.status_code}: {response.text}', 'utility_wrappers', {'status_code': response.status_code, 'response': response.text})
            return {'status': False, 'detail': f'Credit API error: {response.status_code}', 'credits_remaining': 0, 'response_text': response.text}
    except requests.exceptions.Timeout:
        log_warning('Credit API deduction request timed out after 10s', 'utility_wrappers')
        return {'status': False, 'detail': 'Credit API timeout', 'credits_remaining': 0}
    except Exception as e:
        log_error(f'Error calling credit API: {str(e)}', 'utility_wrappers', {'error': str(e)})
        return {'status': False, 'detail': f'Error calling credit API: {str(e)}', 'credits_remaining': 0}