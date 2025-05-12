from fastapi import FastAPI
from api import health, upload

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
app.include_router(upload.router, prefix="/api", tags=["upload"])