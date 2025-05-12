# Backend/main.py
from fastapi import FastAPI
from api import health  # We'll create this next

app = FastAPI()

# Include the health check router
app.include_router(health.router)