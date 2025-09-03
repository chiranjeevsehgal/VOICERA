"""
DEPRECATED: The all-in-one audio processing endpoints have been modularized.

Use `api/process_audio.py` for the new implementation. This module re-exports the
APIRouter for backwards compatibility if any code imports `api.all_in_one`.
"""
import warnings

# Re-export the new router
from api.process_audio import router as router  # noqa: F401

# Emit a deprecation warning at import time
warnings.warn(
    "api.all_in_one is deprecated. Use api.process_audio instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["router"]
