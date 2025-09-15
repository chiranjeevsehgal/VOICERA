from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api import health, transcribe, embedding, upload, llm_translation, supabase_upload, auth, ip_detection, search, credit_management, oauth, admin, content_management, send_email, process_audio, system_health
import uvicorn
import time
import logging
import os
from utils.analytics import track_api_usage
from starlette.middleware.base import BaseHTTPMiddleware
from services.auth import decode_token
from services.ip_utils import get_client_ip
from utils.logging_config import setup_logging
from services.credit_reset_scheduler import start_scheduler, shutdown_scheduler
from middleware.user_status import UserStatusMiddleware
from middleware.rate_limiter import rate_limit_middleware, initialize_rate_limiter
setup_logging()
logger = logging.getLogger('voicera.main')

class APIUsageMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        if request.method == 'OPTIONS':
            return await call_next(request)
        start_time = time.time()
        user_id = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '')
            try:
                payload = decode_token(token)
                if payload and 'sub' in payload:
                    user_id = payload['sub']
            except Exception:
                pass
        try:
            response = await call_next(request)
        except Exception:
            response_time = (time.time() - start_time) * 1000
            logger.exception('Unhandled exception processing %s %s for user=%s after %.2fms', request.method, request.url.path, user_id, response_time)
            raise
        response_time = (time.time() - start_time) * 1000
        client_ip = get_client_ip(request)
        logger.info('HTTP %s %s status=%s user=%s rt=%.2fms ip=%s ua=%s', request.method, request.url.path, response.status_code, user_id, response_time, client_ip, request.headers.get('user-agent'))
        await track_api_usage(request, response, response_time, user_id)
        return response
redis_url = os.getenv('REDIS_URL')
initialize_rate_limiter(redis_url)
app = FastAPI(title='VOICERA Backend', description='Backend for VOICERA', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['https://voicera.trixlabs.in', 'http://voicera.trixlabs.in', 'http://localhost:4200'], allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'], allow_headers=['Accept', 'Accept-Language', 'Content-Language', 'Content-Type', 'Authorization', 'X-Requested-With', 'Origin', 'Cache-Control', 'Pragma', 'User-Agent', 'DNT', 'If-Modified-Since', 'Keep-Alive', 'X-Requested-With', 'X-CSRF-Token', 'X-Accept-Version', 'Content-Length', 'X-Api-Version', 'X-File-Name', 'X-Client-IP', 'X-Client-IP-Token'], expose_headers=['*'])
app.middleware('http')(rate_limit_middleware)
app.add_middleware(UserStatusMiddleware)
app.add_middleware(APIUsageMiddleware)

@app.on_event('startup')
async def _start_scheduler():
    start_scheduler()

@app.on_event('shutdown')
async def _shutdown_scheduler():
    shutdown_scheduler()

@app.get('/')
async def root():
    return {'status': 'Online', 'message': 'Voicera backend is running', 'version': app.version}

@app.options('/{path:path}')
async def options_handler(path: str):
    """Handle OPTIONS requests for CORS preflight"""
    return {}
app.include_router(health.router)
app.include_router(upload.router, prefix='/api', tags=['upload'])
app.include_router(embedding.router, prefix='/api', tags=['embedding'])
app.include_router(transcribe.router, prefix='/api', tags=['transcribe'])
app.include_router(llm_translation.router, prefix='/api', tags=['llm'])
app.include_router(supabase_upload.router, prefix='/api', tags=['supabase'])
app.include_router(search.router, prefix='/api', tags=['search'])
app.include_router(auth.router, prefix='/api', tags=['auth'])
app.include_router(ip_detection.router, prefix='/api', tags=['ip'])
app.include_router(credit_management.router, prefix='/api', tags=['credit'])
app.include_router(oauth.router, prefix='/api', tags=['oauth'])
app.include_router(send_email.router, prefix='/api', tags=['mail-service'])
app.include_router(process_audio.router, prefix='/api', tags=['process-audio'])
app.include_router(admin.router, prefix='/api', tags=['admin'])
app.include_router(content_management.router, prefix='/api', tags=['content'])
app.include_router(system_health.router, prefix='/api', tags=['system'])
if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)