from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from api import health, transcribe, embedding, upload, llm_translation, supabase_upload, auth, ip_detection, search, credit_management, oauth, all_in_one, admin, content_management, otpEmailService
import uvicorn
import time
from utils.analytics import track_api_usage
from starlette.middleware.base import BaseHTTPMiddleware
from services.auth import decode_token

# Create a middleware class for API usage tracking
class APIUsageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timer
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Calculate response time
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Extract user ID from authorization header if present
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            try:
                payload = decode_token(token)
                if payload and "sub" in payload:
                    user_id = payload["sub"]
            except Exception:
                pass
        
        # Track API usage asynchronously
        await track_api_usage(request, response, response_time, user_id)
        
        return response

# Create FastAPI application with concurrency settings
app = FastAPI(
    title="VOICERA Backend", 
    description="Backend for VOICERA",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API usage tracking middleware
app.add_middleware(APIUsageMiddleware)

@app.get("/")
async def root():
    
    return {
        "status": "Online",
        "message": "Voicera backend is running",
        "version": app.version
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
app.include_router(otpEmailService.router, prefix="/api", tags=["mail-service"])

# All-in-one Router
app.include_router(all_in_one.router, prefix="/api", tags=["all-in-one"])

# Admin Router
app.include_router(admin.router, prefix="/api", tags=["admin"])

# Content Management Router
app.include_router(content_management.router, prefix="/api", tags=["admin"])

# This allows the file to be run directly with the appropriate settings
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,  # Run with multiple worker processes
        reload=True
    )