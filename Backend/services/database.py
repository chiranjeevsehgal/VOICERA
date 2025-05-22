import motor.motor_asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.voicera_db

# Export collections
users_collection = db.users
ip_credits_collection = db.ip_credits

# Analytics and monitoring collections
api_usage_collection = db.api_usage
transcription_stats_collection = db.transcription_stats  
search_trends_collection = db.search_trends
user_activity_collection = db.user_activity
logs_collection = db.logs

# Content management collections
podcasts_collection = db.podcasts
transcripts_collection = db.transcripts
uploads_collection = db.uploads
featured_content_collection = db.featured_content