import asyncio
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "voicera")

async def main():
    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # Collections
    podcasts_collection = db["podcasts"]
    transcripts_collection = db["transcripts"]
    
    print("Starting podcast schema update...")
    
    # 1. Remove transcription_status field from all podcasts
    print("Removing transcription_status field from all podcasts...")
    result = podcasts_collection.update_many(
        {},
        {"$unset": {"transcription_status": ""}}
    )
    print(f"Updated {result.modified_count} podcasts to remove transcription_status field")
    
    # 2. Ensure all podcasts have transcript_id if a transcript exists
    print("\nChecking for podcasts without transcript_id...")
    podcasts_without_transcript_id = list(podcasts_collection.find(
        {"transcript_id": {"$exists": False}}
    ))
    
    print(f"Found {len(podcasts_without_transcript_id)} podcasts without transcript_id")
    
    # For each podcast without transcript_id, check if a transcript exists and update
    for podcast in podcasts_without_transcript_id:
        podcast_id = str(podcast["_id"])
        transcript = transcripts_collection.find_one({"podcast_id": podcast_id})
        
        if transcript:
            transcript_id = str(transcript["_id"])
            print(f"Found transcript {transcript_id} for podcast {podcast_id}")
            
            # Update podcast with transcript_id
            podcasts_collection.update_one(
                {"_id": podcast["_id"]},
                {
                    "$set": {
                        "transcript_id": transcript_id,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            print(f"Updated podcast {podcast_id} with transcript_id {transcript_id}")
    
    # 3. Ensure all transcripts have podcast_id
    print("\nChecking for transcripts without podcast_id...")
    transcripts_without_podcast_id = list(transcripts_collection.find(
        {"podcast_id": {"$exists": False}}
    ))
    
    print(f"Found {len(transcripts_without_podcast_id)} transcripts without podcast_id")
    
    # For each transcript without podcast_id, check if a podcast references it
    for transcript in transcripts_without_podcast_id:
        transcript_id = str(transcript["_id"])
        podcast = podcasts_collection.find_one({"transcript_id": transcript_id})
        
        if podcast:
            podcast_id = str(podcast["_id"])
            print(f"Found podcast {podcast_id} for transcript {transcript_id}")
            
            # Update transcript with podcast_id
            transcripts_collection.update_one(
                {"_id": transcript["_id"]},
                {
                    "$set": {
                        "podcast_id": podcast_id,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            print(f"Updated transcript {transcript_id} with podcast_id {podcast_id}")
    
    # 4. Print summary of the current state
    podcast_count = podcasts_collection.count_documents({})
    transcript_count = transcripts_collection.count_documents({})
    podcasts_with_transcript = podcasts_collection.count_documents({"transcript_id": {"$exists": True}})
    transcripts_with_podcast = transcripts_collection.count_documents({"podcast_id": {"$exists": True}})
    
    print("\nDatabase Summary:")
    print(f"Total podcasts: {podcast_count}")
    print(f"Total transcripts: {transcript_count}")
    print(f"Podcasts with transcript_id: {podcasts_with_transcript}")
    print(f"Transcripts with podcast_id: {transcripts_with_podcast}")
    
    print("\nSchema update completed successfully!")

if __name__ == "__main__":
    asyncio.run(main()) 