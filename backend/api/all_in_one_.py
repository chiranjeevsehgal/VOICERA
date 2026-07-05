"""
Refactored all-in-one API module that leverages existing services
to eliminate code duplication and redundancy.

This module simply re-exports the functionality from the dedicated service modules
to maintain API compatibility while using the clean, modular architecture.
"""
from fastapi import APIRouter
from api.process_audio import router as process_audio_router
router = APIRouter()
router.include_router(process_audio_router, tags=['audio-processing'])