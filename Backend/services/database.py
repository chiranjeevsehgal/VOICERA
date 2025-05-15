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