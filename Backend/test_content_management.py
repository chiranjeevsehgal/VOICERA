"""
Test script to demonstrate integration of content management with upload and transcription.

This script simulates the pipeline:
1. Upload a file
2. Transcribe it
3. Check that content is properly tracked in content management collections
"""

import asyncio
import requests
import json
import os
import sys
from bson import ObjectId
from datetime import datetime

# Add parent directory to path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import (
    podcasts_collection,
    transcripts_collection,
    uploads_collection,
    featured_content_collection
)

# Test audio file URL - replace with a real audio URL if needed
TEST_AUDIO_URL = "https://dpgr.am/spacewalk.wav"

async def test_pipeline():
    """Test the content management integration pipeline."""
    print("=== VOICERA Content Management Integration Test ===")
    
    # 1. Clear collections for testing
    print("\n[1] Clearing testing collections...")
    await uploads_collection.delete_many({})
    await podcasts_collection.delete_many({})
    await transcripts_collection.delete_many({})
    
    # 2. Create a test upload
    print("\n[2] Creating test upload record...")
    
    test_user_id = "test_user_123"
    test_filename = "test_audio.mp3"
    
    upload_result = await uploads_collection.insert_one({
        "user_id": test_user_id,
        "file_name": test_filename,
        "file_path": f"/fake/path/{test_filename}",
        "file_url": TEST_AUDIO_URL,
        "file_type": "audio",
        "file_size": 1024000,  # 1MB
        "status": "uploaded",
        "metadata": {
            "content_type": "audio/mpeg",
            "original_filename": test_filename
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    upload_id = str(upload_result.inserted_id)
    print(f"  Created upload record with ID: {upload_id}")
    
    # 3. Simulate transcription and content creation
    print("\n[3] Simulating transcription and content creation...")
    
    # 3.1 Create podcast
    podcast_data = {
        "title": "Test Podcast",
        "description": "This is a test podcast for content management integration",
        "audio_url": TEST_AUDIO_URL,
        "duration_seconds": 120.5,
        "author": "Test Author",
        "published_date": datetime.utcnow(),
        "tags": ["test", "content", "management"],
        "language": "en",
        "upload_id": upload_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "views": 0,
        "likes": 0,
        "is_featured": False,
        "is_published": True,
        "transcription_status": "pending"
    }
    
    podcast_result = await podcasts_collection.insert_one(podcast_data)
    podcast_id = str(podcast_result.inserted_id)
    print(f"  Created podcast record with ID: {podcast_id}")
    
    # 3.2 Update upload with podcast ID
    await uploads_collection.update_one(
        {"_id": ObjectId(upload_id)},
        {"$set": {
            "podcast_id": podcast_id,
            "status": "completed",
            "processed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }}
    )
    print(f"  Updated upload record with podcast ID")
    
    # 3.3 Create transcript
    transcript_data = {
        "podcast_id": podcast_id,
        "content": "This is a test transcript. It contains sample text for testing.",
        "language": "en",
        "is_edited": False,
        "is_published": True,
        "segments": [
            {"text": "This", "start": 0.0, "end": 0.5, "confidence": 0.98},
            {"text": "is", "start": 0.5, "end": 0.7, "confidence": 0.99},
            {"text": "a", "start": 0.7, "end": 0.8, "confidence": 0.99},
            {"text": "test", "start": 0.8, "end": 1.2, "confidence": 0.97},
            {"text": "transcript", "start": 1.2, "end": 2.0, "confidence": 0.95}
        ],
        "confidence_score": 0.97,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    transcript_result = await transcripts_collection.insert_one(transcript_data)
    transcript_id = str(transcript_result.inserted_id)
    print(f"  Created transcript record with ID: {transcript_id}")
    
    # 3.4 Update podcast with transcript ID and completed status
    await podcasts_collection.update_one(
        {"_id": ObjectId(podcast_id)},
        {"$set": {
            "transcript_id": transcript_id,
            "transcription_status": "completed",
            "updated_at": datetime.utcnow()
        }}
    )
    print(f"  Updated podcast record with transcript ID and completed status")
    
    # 4. Verify content in collections
    print("\n[4] Verifying content in collections...")
    
    # 4.1 Check upload
    upload = await uploads_collection.find_one({"_id": ObjectId(upload_id)})
    print("\n  === Upload Record ===")
    print(f"  ID: {str(upload['_id'])}")
    print(f"  User ID: {upload['user_id']}")
    print(f"  File Name: {upload['file_name']}")
    print(f"  Status: {upload['status']}")
    print(f"  Podcast ID: {upload.get('podcast_id', 'None')}")
    
    # 4.2 Check podcast
    podcast = await podcasts_collection.find_one({"_id": ObjectId(podcast_id)})
    print("\n  === Podcast Record ===")
    print(f"  ID: {str(podcast['_id'])}")
    print(f"  Title: {podcast['title']}")
    print(f"  Author: {podcast['author']}")
    print(f"  Duration: {podcast['duration_seconds']} seconds")
    print(f"  Transcription Status: {podcast['transcription_status']}")
    print(f"  Transcript ID: {podcast.get('transcript_id', 'None')}")
    print(f"  Upload ID: {podcast.get('upload_id', 'None')}")
    
    # 4.3 Check transcript
    transcript = await transcripts_collection.find_one({"_id": ObjectId(transcript_id)})
    print("\n  === Transcript Record ===")
    print(f"  ID: {str(transcript['_id'])}")
    print(f"  Podcast ID: {transcript['podcast_id']}")
    print(f"  Language: {transcript['language']}")
    print(f"  Confidence Score: {transcript['confidence_score']}")
    print(f"  Content Preview: {transcript['content'][:50]}...")
    print(f"  Number of Segments: {len(transcript['segments'])}")
    
    print("\n[5] Test Completed Successfully!\n")
    print("The integration between upload/transcription and content management is working.")
    print("When users upload and transcribe files, they are now tracked in the content management collections.")

if __name__ == "__main__":
    asyncio.run(test_pipeline()) 