"""
Refactored all-in-one API module that leverages existing services
to eliminate code duplication and redundancy.

This module simply re-exports the functionality from the dedicated service modules
to maintain API compatibility while using the clean, modular architecture.
"""

from fastapi import APIRouter

# Import the router from the dedicated process_audio module
from api.process_audio import router as process_audio_router

# Create our router instance
router = APIRouter()

# Include all routes from the process_audio module
# This gives us access to:
# - POST /process_audio (single file processing)
# - POST /process_audio_bulk (bulk file processing) 
# - GET /job-status/{job_id} (job status checking)
router.include_router(process_audio_router, tags=["audio-processing"])

# All the heavy lifting is now handled by the dedicated services:
# - services/background_processor.py: Contains the main processing pipeline
# - services/utility_wrappers.py: Contains all sync wrapper functions
# - api/process_audio.py: Contains the API endpoints
#
# This eliminates 1500+ lines of duplicate code while maintaining 
# full functionality and API compatibility.
