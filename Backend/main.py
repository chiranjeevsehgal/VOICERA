from fastapi import FastAPI
from api import health, transcribe, embedding, upload, llm_translation, auth

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

# Embedding router
app.include_router(embedding.router, prefix="/api", tags=["embedding"])

# Transcription router
app.include_router(transcribe.router, prefix="/api", tags=["transcribe"])

# LLM router
app.include_router(llm_translation.router, prefix="/api", tags=["llm"])

# Auth router
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
