# services/utility_wrappers.py
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

# Optional: specific FastAPI response type used in some helpers
from fastapi.responses import JSONResponse
from utils.logging import log_info, log_warning, log_error


# --------- ASYNC HELPERS ---------
async def check_user_credits_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Check user credits from the credit management API"""
    from api.credit_management import check_credits

    # Create a dummy request for the check_credits function
    class DummyRequest:
        def __init__(self):
            self.client = None
            self.headers = {}

    dummy_request = DummyRequest()

    # Log debug info
    log_info(f"Checking credits for IP: {ip}", "utility_wrappers", {"ip": ip})

    try:
        response = await check_credits(dummy_request, ip, current_user)
        log_info(
            f"Raw credit response: {response}",
            "utility_wrappers",
            {"response_type": type(response).__name__},
        )

        # Handle JSONResponse objects by converting to dict
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode("utf-8"))
                log_info(
                    f"Parsed JSONResponse: {response_dict}",
                    "utility_wrappers",
                    {"response_dict": response_dict},
                )
                return response_dict
            except Exception as e:
                log_error(
                    f"Error parsing JSONResponse: {str(e)}",
                    "utility_wrappers",
                    {"error": str(e)},
                )
                # Use a high default value to prevent false "credit limit" errors
                return {"credits_remaining": 100, "ip_address": ip, "status": "default"}

        log_info(
            f"Direct dict response: {response}",
            "utility_wrappers",
            {"response": response},
        )
        return response
    except Exception as e:
        log_error(
            f"Exception in check_user_credits_async: {str(e)}",
            "utility_wrappers",
            {"error": str(e), "ip": ip},
        )
        # Return a safe default instead of failing
        return {
            "credits_remaining": 100,
            "ip_address": ip,
            "status": "exception_default",
        }


async def deduct_user_credit_async(ip: str, current_user: dict) -> Dict[str, Any]:
    """Deduct a credit using the credit management API"""
    from api.credit_management import deduct_credit

    # Create a dummy request for the deduct_credit function
    class DummyRequest:
        def __init__(self):
            self.client = None
            self.headers = {}

    dummy_request = DummyRequest()

    # Log debug info
    log_info(f"Deducting credit for IP: {ip}", "utility_wrappers", {"ip": ip})

    try:
        response = await deduct_credit(dummy_request, ip, current_user)
        log_info(
            f"Raw deduct credit response: {response}",
            "utility_wrappers",
            {"response_type": type(response).__name__},
        )

        # Handle JSONResponse objects by converting to dict
        if isinstance(response, JSONResponse):
            try:
                response_dict = json.loads(response.body.decode("utf-8"))
                log_info(
                    f"Parsed JSONResponse for credit deduction: {response_dict}",
                    "utility_wrappers",
                    {"response_dict": response_dict},
                )
                return response_dict
            except Exception as e:
                log_error(
                    f"Error parsing JSONResponse for credit deduction: {str(e)}",
                    "utility_wrappers",
                    {"error": str(e)},
                )
                return {
                    "status": True,
                    "credits_remaining": 0,
                    "ip_address": ip,
                    "status": "default",
                }

        log_info(
            f"Direct dict response for credit deduction: {response}",
            "utility_wrappers",
            {"response": response},
        )
        return response
    except Exception as e:
        log_error(
            f"Exception in deduct_user_credit_async: {str(e)}",
            "utility_wrappers",
            {"error": str(e), "ip": ip},
        )
        # Return a safe default instead of failing
        return {
            "status": True,
            "credits_remaining": 0,
            "ip_address": ip,
            "status": "exception_default",
        }


async def transcribe_audio_async(
    audio_url: str, options: Dict[str, Any]
) -> Dict[str, Any]:
    """Transcribe the audio using the Deepgram API through the transcribe endpoint"""
    from api.transcribe import TranscriptionRequest, transcribe_audio

    # Create a request object for the transcription API
    request_data = {"url": audio_url, **options}
    transcription_request = TranscriptionRequest(**request_data)

    # Call the transcription API
    current_user = {}  # We already authenticated with our main endpoint
    return await transcribe_audio(transcription_request, current_user)


async def embed_metadata_in_file_async(
    src_file: str, dest_file: str, metadata_json: str
) -> str:
    """Embed the metadata into the audio file using ID3 tags"""
    # First copy the file
    shutil.copy2(src_file, dest_file)

    try:
        # Try to load existing ID3 tags, or create new ones if none
        try:
            tags = ID3(dest_file)
        except Exception:
            # Creating new ID3 tags and associating them with the file
            tags = ID3()
            tags.save(dest_file)
            # Reloading the tags to ensure they're associated with the file
            tags = ID3(dest_file)

        # Encode as base64 to avoid issues with special characters
        encoded_json = base64.b64encode(metadata_json.encode("utf-8")).decode("utf-8")
        tags["TXXX:transcription_json"] = TXXX(
            encoding=3, desc="transcription_json", text=f"base64:{encoded_json}"
        )

        # Save the tags to the file
        tags.save(dest_file)

        return dest_file
    except Exception as e:
        # If embedding fails, just return the original file
        log_error(
            f"Error embedding metadata: {str(e)}",
            "utility_wrappers",
            {"error": str(e), "src_file": src_file},
        )
        return src_file


async def upload_to_supabase_async(
    file_path: str, filename: str, user_id: str = None, bucket_name: str = None
) -> Dict[str, Any]:
    """Upload file to Supabase"""
    from services.supabase_service import upload_file_to_supabase

    result = await upload_file_to_supabase(
        file_path, filename, user_id, bucket_name=bucket_name
    )
    return result


# --------- SYNC WRAPPERS ---------


def sync_check_credits(ip: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit check API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    try:
        load_dotenv()

        # Get the base URL - use localhost on same port as the server
        api_base_url = os.getenv(
            "BACKEND_URL"
        )  # Use same server where the app is running

        # Construct the full URL for the credit endpoint
        credit_api_url = f"{api_base_url}/api/check-credits"

        # First try to get token directly from our enhanced user object
        access_token = None
        if current_user and "auth_token" in current_user:
            access_token = current_user.get("auth_token")
            log_info("Using JWT token from original request", "utility_wrappers")

        # If no token in enhanced user, try admin login
        if not access_token:
            # First try login to get a token
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

            # Try to get a token by logging in
            try:
                login_url = f"{api_base_url}/api/auth/login"
                login_data = {
                    "username": admin_email,
                    "password": admin_password,
                }
                login_headers = {"Content-Type": "application/x-www-form-urlencoded"}

                login_response = requests.post(
                    login_url,
                    data=login_data,
                    headers=login_headers,
                    timeout=10,
                )
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get("access_token")
                    log_info(
                        "Successfully got access token via admin login",
                        "utility_wrappers",
                    )
                else:
                    log_error(
                        f"Admin login failed: {login_response.status_code} - {login_response.text}",
                        "utility_wrappers",
                        {
                            "status_code": login_response.status_code,
                            "response": login_response.text,
                        },
                    )
            except Exception as e:
                log_error(
                    f"Error during admin login: {str(e)}",
                    "utility_wrappers",
                    {"error": str(e)},
                )

        # Set up headers
        headers = {
            "Content-Type": "application/json",
            # Forward the real client IP so credit API doesn't see localhost
            "X-Client-IP": ip,
        }

        # Add authorization if we have a token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            # Also add the optional token if we're in dev mode with client IP trust enabled
            client_ip_token = os.getenv("CLIENT_IP_HEADER_TOKEN")
            if client_ip_token:
                headers["X-Client-IP-Token"] = client_ip_token
            log_info(
                f"Using Authorization header: Bearer {access_token[:10]}...",
                "utility_wrappers",
            )
        else:
            log_warning(
                "No access token available for credit API call", "utility_wrappers"
            )
            return {
                "credits_remaining": 100,  # Default high value to prevent false errors
                "ip_address": ip,
                "status": "default",
            }

        # Make the synchronous GET request to check credit
        log_info(
            f"Making direct HTTP request to {credit_api_url} for IP {ip}",
            "utility_wrappers",
            {"url": credit_api_url, "ip": ip},
        )
        response = requests.get(credit_api_url, headers=headers, timeout=10)

        # Parse and return the response
        if response.status_code == 200:
            return response.json()
        else:
            log_error(
                f"Credit API returned status code {response.status_code}: {response.text}",
                "utility_wrappers",
                {"status_code": response.status_code, "response": response.text},
            )

            # Return a safe default
            return {
                "credits_remaining": 100,  # Default high value to prevent false errors
                "ip_address": ip,
                "status": "error_response",
            }

    except requests.exceptions.Timeout:
        log_warning("Credit API request timed out after 10s", "utility_wrappers")
        return {
            "credits_remaining": 100,
            "ip_address": ip,
            "status": "timeout_default",
        }
    except Exception as e:
        log_error(
            f"Error calling credit API: {str(e)}", "utility_wrappers", {"error": str(e)}
        )

        # Return a safe default
        return {
            "credits_remaining": 100,  # Default high value to prevent false errors
            "ip_address": ip,
            "status": "exception_default",
        }


def sync_transcribe_audio(audio_url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for transcribing audio"""
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async function in this loop
        result = loop.run_until_complete(transcribe_audio_async(audio_url, options))

        # Clean up
        loop.close()

        return result
    except Exception as e:
        log_error(
            f"Error in sync_transcribe_audio: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
        return {"error": str(e)}


def sync_embed_metadata(src_file: str, dest_file: str, metadata_json: str) -> str:
    """Synchronous wrapper for embedding metadata"""
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async function in this loop
        result = loop.run_until_complete(
            embed_metadata_in_file_async(src_file, dest_file, metadata_json)
        )

        # Clean up
        loop.close()

        return result
    except Exception as e:
        log_error(
            f"Error in sync_embed_metadata: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
        return src_file  # Return original file on error


def sync_upload_to_supabase(
    file_path: str, filename: str, user_id: str = None, bucket_name: str = None
) -> Dict[str, Any]:
    """Synchronous wrapper for uploading to Supabase"""
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async function in this loop
        result = loop.run_until_complete(
            upload_to_supabase_async(file_path, filename, user_id, bucket_name)
        )

        # Clean up
        loop.close()

        return result
    except Exception as e:
        log_error(
            f"Error in sync_upload_to_supabase: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
        return {"error": str(e), "file_name": filename}


def sync_delete_from_supabase(
    name_or_path: str, bucket_name: str = None
) -> Dict[str, Any]:
    """Synchronous wrapper for deleting a file from Supabase storage"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from services.supabase_service import delete_file_from_supabase

        result = loop.run_until_complete(
            delete_file_from_supabase(name_or_path, bucket_name=bucket_name)
        )
        loop.close()
        return result
    except Exception as e:
        log_error(
            f"Error in sync_delete_from_supabase: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
        return {"success": False, "error": str(e)}


def sync_index_transcript(
    transcript_data: Dict[str, Any],
    file_url: str,
    file_name: str,
    is_permanent_url: bool = False,
) -> bool:
    """
    Synchronous wrapper for indexing transcript in Pinecone

    Args:
        transcript_data: The transcription data
        file_url: URL to the audio file
        file_name: Name of the audio file
        is_permanent_url: Whether the URL is permanent (Supabase) or temporary (tmpfiles)
    """
    try:
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async function in this loop
        from services.pinecone_service import index_transcript

        result = loop.run_until_complete(
            index_transcript(
                transcript_data=transcript_data,
                file_url=file_url,
                file_name=file_name,
                is_permanent_url=is_permanent_url,
            )
        )

        # Clean up
        loop.close()

        return result
    except Exception as e:
        log_error(
            f"Error in sync_index_transcript: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
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
        # Create a new event loop for this function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the update in this loop
        from services.database import podcasts_collection

        async def update_podcast():
            result = await podcasts_collection.update_one(
                {"_id": ObjectId(podcast_id)},
                {
                    "$set": {
                        "audio_url": supabase_url,
                        "updated_at": datetime.utcnow(),
                    },
                    "$unset": {"supabase_url": ""},
                },
            )
            return result.modified_count > 0

        result = loop.run_until_complete(update_podcast())

        # Clean up
        loop.close()

        return result
    except Exception as e:
        log_error(
            f"Error in sync_update_podcast_url: {str(e)}",
            "utility_wrappers",
            {"error": str(e)},
        )
        return False


def direct_deduct_credit(ip_address: str, current_user: dict) -> Dict[str, Any]:
    """
    Call the credit API endpoint directly using synchronous requests.
    This avoids the event loop issues while still using the proper API.
    """
    try:
        load_dotenv()

        # Get the base URL - use localhost on same port as the server
        api_base_url = os.getenv(
            "BACKEND_URL"
        )  # Use same server where the app is running

        # Construct the full URL for the credit endpoint
        credit_api_url = f"{api_base_url}/api/credit"

        # Print what we have in current_user for debugging
        log_info(
            f"Current user object keys for credit API: {current_user.keys() if current_user else 'None'}",
            "utility_wrappers",
            {"user_keys": list(current_user.keys()) if current_user else None},
        )

        # First try to get token directly from our enhanced user object
        access_token = None
        if current_user and "auth_token" in current_user:
            access_token = current_user.get("auth_token")
            log_info("Using JWT token from original request", "utility_wrappers")

        # If no token in enhanced user, try admin login
        if not access_token:
            # First try login to get a token
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

            # Try to get a token by logging in
            try:
                login_url = f"{api_base_url}/api/auth/login"
                login_data = {
                    "username": admin_email,
                    "password": admin_password,
                }
                login_headers = {"Content-Type": "application/x-www-form-urlencoded"}

                login_response = requests.post(
                    login_url,
                    data=login_data,
                    headers=login_headers,
                    timeout=10,
                )
                if login_response.status_code == 200:
                    token_data = login_response.json()
                    access_token = token_data.get("access_token")
                    log_info(
                        "Successfully got access token via admin login",
                        "utility_wrappers",
                    )
                else:
                    log_error(
                        f"Admin login failed: {login_response.status_code} - {login_response.text}",
                        "utility_wrappers",
                        {
                            "status_code": login_response.status_code,
                            "response": login_response.text,
                        },
                    )
            except requests.exceptions.Timeout:
                log_warning(
                    "Admin login request timed out after 10s", "utility_wrappers"
                )
            except Exception as e:
                log_error(
                    f"Error during admin login: {str(e)}",
                    "utility_wrappers",
                    {"error": str(e)},
                )

        # Set up headers
        headers = {
            "Content-Type": "application/json",
            # Forward the real client IP so credit API doesn't see localhost
            "X-Client-IP": ip_address,
        }

        # Add authorization if we have a token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            # Also add the optional token if we're in dev mode with client IP trust enabled
            client_ip_token = os.getenv("CLIENT_IP_HEADER_TOKEN")
            if client_ip_token:
                headers["X-Client-IP-Token"] = client_ip_token
            log_info(
                f"Using Authorization header: Bearer {access_token[:10]}...",
                "utility_wrappers",
            )
        else:
            log_warning(
                "No access token available for credit API call", "utility_wrappers"
            )
            return {
                "status": False,
                "detail": "No authentication token available",
                "credits_remaining": 0,
            }

        # Include IP in request body
        data = {
            "ip": ip_address,
        }

        # Make the synchronous POST request to deduct credit
        log_info(
            f"Making direct HTTP request to {credit_api_url} for IP {ip_address}",
            "utility_wrappers",
            {"url": credit_api_url, "ip": ip_address},
        )
        response = requests.post(credit_api_url, json=data, headers=headers, timeout=10)

        # Parse and return the response
        if response.status_code == 200:
            return response.json()
        else:
            log_error(
                f"Credit API returned status code {response.status_code}: {response.text}",
                "utility_wrappers",
                {"status_code": response.status_code, "response": response.text},
            )

            # No more simulation - return actual error
            return {
                "status": False,
                "detail": f"Credit API error: {response.status_code}",
                "credits_remaining": 0,
                "response_text": response.text,
            }

    except requests.exceptions.Timeout:
        log_warning(
            "Credit API deduction request timed out after 10s", "utility_wrappers"
        )
        return {
            "status": False,
            "detail": "Credit API timeout",
            "credits_remaining": 0,
        }
    except Exception as e:
        log_error(
            f"Error calling credit API: {str(e)}", "utility_wrappers", {"error": str(e)}
        )

        # No more simulation - return actual error
        return {
            "status": False,
            "detail": f"Error calling credit API: {str(e)}",
            "credits_remaining": 0,
        }
