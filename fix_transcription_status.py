import asyncio
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

# Connect to MongoDB
MONGO_URI = "mongodb://localhost:27017/voicera_db"  # Update this with your actual MongoDB URI
client = MongoClient(MONGO_URI)
db = client.voicera_db

async def fix_podcast_transcript_links(podcast_id=None, transcript_id=None, stats_id=None):
    """
    Fix the links between podcasts, transcripts, and transcription stats.
    You can provide any of the IDs and the function will try to find and link related records.
    """
    # Find the podcast if ID is provided
    podcast = None
    if podcast_id:
        podcast = db.podcasts.find_one({"_id": ObjectId(podcast_id)})
        if podcast:
            print(f"Found podcast: {podcast['title']}")
            print(f"Current transcription status: {podcast.get('transcription_status', 'unknown')}")
        else:
            print(f"No podcast found with ID: {podcast_id}")
    
    # Find the transcript if ID is provided or try to find by podcast ID
    transcript = None
    if transcript_id:
        transcript = db.transcripts.find_one({"_id": ObjectId(transcript_id)})
    elif podcast_id:
        # Try to find transcript by podcast ID first
        transcript = db.transcripts.find_one({"podcast_id": podcast_id})
        # If not found, look for a transcript with null podcast_id that matches by timestamp
        if not transcript and podcast:
            # Find transcripts created around the same time as the podcast
            podcast_time = podcast["created_at"]
            transcripts = list(db.transcripts.find({
                "podcast_id": None,
                "created_at": {
                    "$gte": podcast_time.replace(second=podcast_time.second-5),
                    "$lte": podcast_time.replace(second=podcast_time.second+5)
                }
            }))
            if transcripts:
                transcript = transcripts[0]  # Use the first match
    
    if transcript:
        print(f"Found transcript with ID: {transcript['_id']}")
        print(f"Current podcast_id in transcript: {transcript.get('podcast_id', 'None')}")
    else:
        print("No matching transcript found")
    
    # Find transcription stats if ID is provided or try to find by podcast/transcript ID
    stats = None
    if stats_id:
        stats = db.transcription_stats_collection.find_one({"_id": ObjectId(stats_id)})
    elif podcast_id or transcript_id:
        # Try to find stats by podcast ID first
        if podcast_id:
            stats = db.transcription_stats_collection.find_one({"podcast_id": podcast_id})
        
        # If not found and we have a transcript, try by transcript ID
        if not stats and transcript_id:
            stats = db.transcription_stats_collection.find_one({"transcript_id": transcript_id})
        
        # If still not found, look for stats with null IDs that match by timestamp and audio length
        if not stats and podcast:
            podcast_time = podcast["created_at"]
            duration = podcast.get("duration_seconds")
            
            stats_list = list(db.transcription_stats_collection.find({
                "podcast_id": None,
                "timestamp": {
                    "$gte": podcast_time.replace(second=podcast_time.second-5),
                    "$lte": podcast_time.replace(second=podcast_time.second+5)
                }
            }))
            
            # If we have audio length, filter by that too
            if duration and stats_list:
                for stat in stats_list:
                    if abs(stat.get("audio_length", 0) - duration) < 0.1:  # Within 0.1 seconds
                        stats = stat
                        break
                
                # If no exact match, just use the first one
                if not stats:
                    stats = stats_list[0]
    
    if stats:
        print(f"Found transcription stats with ID: {stats['_id']}")
        print(f"Current podcast_id in stats: {stats.get('podcast_id', 'None')}")
        print(f"Current transcript_id in stats: {stats.get('transcript_id', 'None')}")
    else:
        print("No matching transcription stats found")
    
    # Now fix the links between these records
    updates_made = False
    
    # 1. Update podcast transcription status if needed
    if podcast and podcast.get("transcription_status") == "pending" and transcript:
        print("Updating podcast transcription status to 'completed'...")
        result = db.podcasts.update_one(
            {"_id": podcast["_id"]},
            {"$set": {
                "transcription_status": "completed",
                "transcript_id": str(transcript["_id"]),
                "updated_at": datetime.utcnow()
            }}
        )
        if result.modified_count > 0:
            print("Successfully updated podcast transcription status")
            updates_made = True
        else:
            print("No changes made to podcast")
    
    # 2. Update transcript with podcast_id if needed
    if transcript and not transcript.get("podcast_id") and podcast:
        print("Updating transcript with podcast_id...")
        result = db.transcripts.update_one(
            {"_id": transcript["_id"]},
            {"$set": {
                "podcast_id": str(podcast["_id"]),
                "updated_at": datetime.utcnow()
            }}
        )
        if result.modified_count > 0:
            print("Successfully updated transcript with podcast_id")
            updates_made = True
        else:
            print("No changes made to transcript")
    
    # 3. Update transcription stats with podcast_id and transcript_id if needed
    if stats and (not stats.get("podcast_id") or not stats.get("transcript_id")):
        update_data = {"updated_at": datetime.utcnow()}
        
        if podcast and not stats.get("podcast_id"):
            update_data["podcast_id"] = str(podcast["_id"])
        
        if transcript and not stats.get("transcript_id"):
            update_data["transcript_id"] = str(transcript["_id"])
        
        if update_data:
            print("Updating transcription stats with missing IDs...")
            result = db.transcription_stats_collection.update_one(
                {"_id": stats["_id"]},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                print("Successfully updated transcription stats")
                updates_made = True
            else:
                print("No changes made to transcription stats")
    
    if updates_made:
        print("All records have been successfully linked")
    else:
        print("No updates were needed or possible")

if __name__ == "__main__":
    # The IDs from your database records
    podcast_id = "682d4f345bb6da52a8d6b559"  # Your podcast ID
    transcript_id = "682d4f345bb6da52a8d6b55d"  # Your transcript ID
    stats_id = "682d4f345bb6da52a8d6b558"  # Your transcription stats ID
    
    # Run the fix
    asyncio.run(fix_podcast_transcript_links(podcast_id, transcript_id, stats_id))

print("MongoDB commands to manually fix the links between podcast, transcript, and stats:")
print("\n1. Update podcast transcription status to 'completed':")
print(f"""
db.podcasts.updateOne(
  {{ "_id": ObjectId("{podcast_id}") }},
  {{ 
    "$set": {{ 
      "transcription_status": "completed",
      "transcript_id": "{transcript_id}",
      "updated_at": new Date()
    }}
  }}
)
""")

print("\n2. Update transcript with podcast_id:")
print(f"""
db.transcripts.updateOne(
  {{ "_id": ObjectId("{transcript_id}") }},
  {{ 
    "$set": {{ 
      "podcast_id": "{podcast_id}",
      "updated_at": new Date()
    }}
  }}
)
""")

print("\n3. Update transcription stats with podcast_id and transcript_id:")
print(f"""
db.transcription_stats.updateOne(
  {{ "_id": ObjectId("{stats_id}") }},
  {{ 
    "$set": {{ 
      "podcast_id": "{podcast_id}",
      "transcript_id": "{transcript_id}",
      "updated_at": new Date()
    }}
  }}
)
""")

print("\nRun these commands in your MongoDB shell or MongoDB Compass to fix the links.")
print("After running these commands, the podcast will show as 'completed' and all records will be properly linked.") 