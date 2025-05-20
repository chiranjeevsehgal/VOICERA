"""
Test script for the all_in_one processing endpoint.

This script demonstrates how to use the all_in_one processing endpoint
to upload, transcribe, and store an audio file with proper content tracking.
"""

import asyncio
import aiohttp
import os
import json
import sys
import time
from bson import ObjectId
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import services and dependencies
from services.database import uploads_collection, podcasts_collection, transcripts_collection

# Configuration
API_URL = "http://localhost:8000"  # Change as needed
TEST_AUDIO_FILE = "audio_uploads/nasa.mp3"  # Use an existing file


async def login_admin():
    """Login and get an access token for admin"""
    print("[1] Logging in as admin...")
    
    async with aiohttp.ClientSession() as session:
        # Use hardcoded default admin credentials 
        login_data = {
            "username": "admin@voicera.ai",  # Default admin email
            "password": "admin123"  # Default admin password
        }
        
        async with session.post(
            f"{API_URL}/api/auth/login", 
            data=login_data
        ) as response:
            if response.status == 200:
                result = await response.json()
                token = result.get("access_token")
                print(f"✓ Login successful")
                return token
            else:
                text = await response.text()
                print(f"✗ Login failed: {response.status} - {text}")
                return None


async def process_audio(file_path, auth_token):
    """Process an audio file using the all_in_one endpoint"""
    print(f"[2] Processing audio file: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"✗ File not found: {file_path}")
        return
    
    # Prepare the multipart form data
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    filename = os.path.basename(file_path)
    
    async with aiohttp.ClientSession() as session:
        # Create form data
        data = aiohttp.FormData()
        data.add_field('file', 
                       file_data,
                       filename=filename,
                       content_type='audio/mpeg')
        
        # Add transcription options
        transcription_options = {
            "punctuate": True,
            "smart_format": True,
            "model": "nova-2"
        }
        data.add_field('transcription_options', json.dumps(transcription_options))
        
        # Process the audio
        headers = {"Authorization": f"Bearer {auth_token}"}
        async with session.post(
            f"{API_URL}/api/process_audio", 
            data=data,
            headers=headers
        ) as response:
            if response.status == 202:
                result = await response.json()
                job_id = result.get("job_id")
                print(f"✓ Processing started with job ID: {job_id}")
                return job_id
            else:
                text = await response.text()
                print(f"✗ Processing failed: {response.status} - {text}")
                return None


async def check_job_status(job_id, auth_token):
    """Check the status of a job"""
    print(f"[3] Checking job status for: {job_id}")
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Poll until complete or failed
        max_attempts = 30
        for attempt in range(1, max_attempts + 1):
            print(f"  Polling attempt {attempt}/{max_attempts}...")
            
            async with session.get(
                f"{API_URL}/api/job-status/{job_id}", 
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    status = result.get("status")
                    progress = result.get("progress", 0)
                    
                    print(f"  Status: {status}, Progress: {progress}%")
                    
                    if status == "completed":
                        print(f"✓ Job completed successfully")
                        return True
                    elif status == "failed":
                        error = result.get("error", "Unknown error")
                        print(f"✗ Job failed: {error}")
                        return False
                    elif attempt == max_attempts:
                        print(f"✗ Max polling attempts reached")
                        return False
                    
                    # Wait before next attempt
                    await asyncio.sleep(3)
                else:
                    text = await response.text()
                    print(f"✗ Failed to check job status: {response.status} - {text}")
                    return False


async def verify_content_tracking():
    """Verify that content was properly tracked in the database"""
    print("[4] Verifying content tracking in the database...")
    
    # Check uploads collection
    upload_count = await uploads_collection.count_documents({})
    podcast_count = await podcasts_collection.count_documents({})
    transcript_count = await transcripts_collection.count_documents({})
    
    print(f"  Found {upload_count} uploads, {podcast_count} podcasts, and {transcript_count} transcripts")
    
    # Get the latest upload
    latest_upload = await uploads_collection.find_one(
        sort=[("created_at", -1)]
    )
    
    if not latest_upload:
        print("✗ No uploads found in the database")
        return False
    
    print("\n=== Latest Upload ===")
    print(f"ID: {latest_upload['_id']}")
    print(f"User ID: {latest_upload.get('user_id', 'Not set')}")
    print(f"File Name: {latest_upload.get('file_name', 'Not set')}")
    print(f"Status: {latest_upload.get('status', 'Not set')}")
    print(f"Metadata: {json.dumps(latest_upload.get('metadata', {}), default=str)}")
    
    # If this upload has a podcast, show it too
    podcast_id = latest_upload.get("podcast_id")
    if podcast_id:
        podcast = await podcasts_collection.find_one({"_id": ObjectId(podcast_id)})
        if podcast:
            print("\n=== Associated Podcast ===")
            print(f"ID: {podcast['_id']}")
            print(f"Title: {podcast.get('title', 'Not set')}")
            print(f"Author: {podcast.get('author', 'Not set')}")
            print(f"Transcription Status: {podcast.get('transcription_status', 'Not set')}")
            
            # If this podcast has a transcript, show it too
            transcript_id = podcast.get("transcript_id")
            if transcript_id:
                transcript = await transcripts_collection.find_one({"_id": ObjectId(transcript_id)})
                if transcript:
                    print("\n=== Associated Transcript ===")
                    print(f"ID: {transcript['_id']}")
                    print(f"Length: {len(transcript.get('content', ''))} characters")
                    print(f"Language: {transcript.get('language', 'Not set')}")
                    print(f"Confidence: {transcript.get('confidence_score', 'Not set')}")
                    
                    # Show a preview of the transcript
                    content = transcript.get('content', '')
                    if content:
                        preview = content[:150] + "..." if len(content) > 150 else content
                        print(f"Preview: {preview}")
    
    print("\n✓ Content tracking verification complete")
    return True


async def main():
    print("=== VOICERA All-In-One Processing Test ===")
    
    # Step 1: Login as admin
    auth_token = await login_admin()
    if not auth_token:
        return
    
    # Ensure test file exists
    test_file_path = os.path.join(os.path.dirname(__file__), TEST_AUDIO_FILE)
    if not os.path.exists(test_file_path):
        print(f"✗ Test file not found: {test_file_path}")
        print("Please update TEST_AUDIO_FILE to point to a valid audio file")
        return
    
    # Step 2: Process the audio
    job_id = await process_audio(test_file_path, auth_token)
    if not job_id:
        return
    
    # Step 3: Check job status
    success = await check_job_status(job_id, auth_token)
    if not success:
        return
    
    # Step 4: Verify content tracking
    await verify_content_tracking()
    
    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(main()) 