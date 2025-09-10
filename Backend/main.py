from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from api import (
    health,
    transcribe,
    embedding,
    upload,
    llm_translation,
    supabase_upload,
    auth,
    ip_detection,
    search,
    credit_management,
    oauth,
    admin,
    content_management,
    send_email,
    process_audio,
    system_health,
)
import uvicorn
import time
import logging
from utils.analytics import track_api_usage
from starlette.middleware.base import BaseHTTPMiddleware
from services.auth import decode_token
from services.ip_utils import get_client_ip
from utils.logging_config import setup_logging

# Initialize logging before app and routers
setup_logging()
logger = logging.getLogger("voicera.main")
from middleware.user_status import UserStatusMiddleware
from middleware.rate_limiter import rate_limit_middleware, initialize_rate_limiter
import os


# Create a middleware class for API usage tracking
class APIUsageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timer
        start_time = time.time()

        # Extract user ID from authorization header if present (before processing for logging)
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            try:
                payload = decode_token(token)
                if payload and "sub" in payload:
                    user_id = payload["sub"]
            except Exception:
                # Avoid failing request due to logging concerns
                pass

        # Process the request with error logging
        try:
            response = await call_next(request)
        except Exception as ex:
            response_time = (time.time() - start_time) * 1000
            logger.exception(
                "Unhandled exception processing %s %s for user=%s after %.2fms",
                request.method,
                request.url.path,
                user_id,
                response_time,
            )
            raise

        # Calculate response time
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        # Structured access log
        client_ip = get_client_ip(request)
        logger.info(
            "HTTP %s %s status=%s user=%s rt=%.2fms ip=%s ua=%s",
            request.method,
            request.url.path,
            response.status_code,
            user_id,
            response_time,
            client_ip,
            request.headers.get("user-agent"),
        )

        # Track API usage asynchronously
        await track_api_usage(request, response, response_time, user_id)

        return response


# Initialize rate limiter with optional Redis support
redis_url = os.getenv("REDIS_URL")  # e.g., "redis://localhost:6379"
initialize_rate_limiter(redis_url)

# Create FastAPI application with concurrency settings
app = FastAPI(
    title="VOICERA Backend", description="Backend for VOICERA", version="1.0.0"
)

# Add rate limiting middleware (first to catch requests early)
app.middleware("http")(rate_limit_middleware)

# Add user status checking middleware
app.add_middleware(UserStatusMiddleware)

# Add API usage tracking middleware
app.add_middleware(APIUsageMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "Online",
        "message": "Voicera backend is running",
        "version": app.version,
    }


# Health check router
app.include_router(health.router)

# Upload router
app.include_router(upload.router, prefix="/api", tags=["upload"])

# Embedding router
app.include_router(embedding.router, prefix="/api", tags=["embedding"])

# Transcription router
app.include_router(transcribe.router, prefix="/api", tags=["transcribe"])

# LLM router
app.include_router(llm_translation.router, prefix="/api", tags=["llm"])

# Supabase router
app.include_router(supabase_upload.router, prefix="/api", tags=["supabase"])

# Search router
app.include_router(search.router, prefix="/api", tags=["search"])

# Auth router
app.include_router(auth.router, prefix="/api", tags=["auth"])

# IP router
app.include_router(ip_detection.router, prefix="/api", tags=["ip"])

# Credit router
app.include_router(credit_management.router, prefix="/api", tags=["credit"])

# OAUTH Router
app.include_router(oauth.router, prefix="/api", tags=["oauth"])

# Mail Service Router
app.include_router(send_email.router, prefix="/api", tags=["mail-service"])

# Process Audio Router (modularized)
app.include_router(process_audio.router, prefix="/api", tags=["process-audio"])

# Admin Router
app.include_router(admin.router, prefix="/api", tags=["admin"])

# Content Management Router
app.include_router(content_management.router, prefix="/api", tags=["content"])

# System Health Router (for monitoring circuit breakers and rate limits)
app.include_router(system_health.router, prefix="/api", tags=["system"])

# This allows the file to be run directly with the appropriate settings
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        # workers=4,  
        reload=True,
    )