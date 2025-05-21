from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from api import health, transcribe, embedding, upload, llm_translation, supabase_upload, auth, ip_detection, search, credit_management, oauth, all_in_one, otpEmailService
import uvicorn

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

# This allows the file to be run directly with the appropriate settings
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,  # Run with multiple worker processes
        reload=True
    )