from fastapi import FastAPI
from api import health
from api.endpoints import steganography

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

# Steganography router
app.include_router(steganography.router)