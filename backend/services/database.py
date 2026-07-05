import motor.motor_asyncio
import os
import logging
from typing import Optional
from dotenv import load_dotenv
from utils.logging_config import setup_logging
load_dotenv()
if not getattr(logging.getLogger(), '_voicera_logging_configured', False):
    setup_logging()
logger = logging.getLogger('voicera.db')
MONGO_URI = os.getenv('MONGO_URI')

def _mask_mongo_uri(uri: Optional[str]) -> str:
    if not uri:
        return '<missing>'
    try:
        if '://' in uri:
            scheme, rest = uri.split('://', 1)
            if '@' in rest:
                _creds, host = rest.split('@', 1)
                return f'{scheme}://***:***@{host}'
            return f'{scheme}://{rest}'
        return uri
    except Exception:
        return '<masked>'
if not MONGO_URI:
    logger.warning('MONGO_URI is not set; attempting default client. DB operations may fail.')
try:
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI) if MONGO_URI else motor.motor_asyncio.AsyncIOMotorClient()
    db = client.voicera_db
    logger.info('Initialized MongoDB client. uri=%s db=%s', _mask_mongo_uri(MONGO_URI), 'voicera_db')
except Exception as e:
    logger.exception('Failed to initialize MongoDB client: %s', e)
    raise
users_collection = db.users
guests_collection = db.guests
ip_credits_collection = db.ip_credits
credit_requests_collection = db.credit_requests
api_usage_collection = db.api_usage
transcription_stats_collection = db.transcription_stats
search_trends_collection = db.search_trends
user_activity_collection = db.user_activity
logs_collection = db.logs
podcasts_collection = db.podcasts
transcripts_collection = db.transcripts
uploads_collection = db.uploads
featured_content_collection = db.featured_content
ip_hits_collection = db.ip_hits