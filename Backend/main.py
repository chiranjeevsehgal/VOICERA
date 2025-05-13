from fastapi import FastAPI
from api import health, transcribe, steganography, upload

app = FastAPI(
    title="VOICERA Backend", 
    description="Backend for VOICERA",
    version="1.0.0"
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

# Steganography router
app.include_router(steganography.router, prefix="/api", tags=["steganography"])

# Transcription router
app.include_router(transcribe.router, prefix="/api", tags=["transcribe"])
