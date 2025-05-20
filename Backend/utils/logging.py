from datetime import datetime
from services.database import logs_collection
import asyncio
from typing import Dict, Any, Optional

async def add_log_entry(
    level: str,
    message: str,
    source: str,
    context: Optional[Dict[str, Any]] = None
):
    """
    Add a log entry to the application logs collection.
    
    Args:
        level: Log level (info, warning, error, debug)
        message: Log message content
        source: Source/component generating the log
        context: Additional contextual information (optional)
    """
    if context is None:
        context = {}
    
    log_entry = {
        "timestamp": datetime.utcnow(),
        "level": level,
        "message": message,
        "source": source,
        "context": context
    }
    
    try:
        await logs_collection.insert_one(log_entry)
    except Exception as e:
        # Fallback to print if DB insert fails
        print(f"WARNING: Failed to add log entry: {e}")
        print(f"LOG: [{level.upper()}] {message} - {source}")

def log_info(message: str, source: str, context: Optional[Dict[str, Any]] = None):
    """Log an info-level message"""
    asyncio.create_task(add_log_entry("info", message, source, context))

def log_warning(message: str, source: str, context: Optional[Dict[str, Any]] = None):
    """Log a warning-level message"""
    asyncio.create_task(add_log_entry("warning", message, source, context))

def log_error(message: str, source: str, context: Optional[Dict[str, Any]] = None):
    """Log an error-level message"""
    asyncio.create_task(add_log_entry("error", message, source, context))

def log_debug(message: str, source: str, context: Optional[Dict[str, Any]] = None):
    """Log a debug-level message"""
    asyncio.create_task(add_log_entry("debug", message, source, context)) 