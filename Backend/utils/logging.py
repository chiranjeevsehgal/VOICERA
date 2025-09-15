from datetime import datetime
from services.database import logs_collection
import asyncio
from typing import Dict, Any, Optional
from fastapi import BackgroundTasks
import logging
from utils.logging_config import setup_logging
if not getattr(logging.getLogger(), '_voicera_logging_configured', False):
    setup_logging()
logger = logging.getLogger('voicera.app')

async def add_log_entry(level: str, message: str, source: str, context: Optional[Dict[str, Any]]=None):
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
    log_entry = {'timestamp': datetime.utcnow(), 'level': level, 'message': message, 'source': source, 'context': context}
    try:
        await logs_collection.insert_one(log_entry)
    except Exception as e:
        logger.warning('Failed to add log entry to DB: %s', e)
        _emit_to_python_logger(level, message, source, context)

def _emit_to_python_logger(level: str, message: str, source: str, context: Optional[Dict[str, Any]]=None) -> None:
    extra = {'source': source, **(context or {})}
    if context:
        message = f'{message} | context={context}'
    lvl = (level or 'info').lower()
    if lvl == 'debug':
        logger.debug(message, extra=extra)
    elif lvl == 'warning':
        logger.warning(message, extra=extra)
    elif lvl == 'error':
        logger.error(message, extra=extra)
    else:
        logger.info(message, extra=extra)

def log_info(message: str, source: str, context: Optional[Dict[str, Any]]=None, background_tasks: Optional[BackgroundTasks]=None):
    """Log an info-level message"""
    if background_tasks is not None:
        background_tasks.add_task(add_log_entry, 'info', message, source, context)
    else:
        _emit_to_python_logger('info', message, source, context)

def log_warning(message: str, source: str, context: Optional[Dict[str, Any]]=None, background_tasks: Optional[BackgroundTasks]=None):
    """Log a warning-level message"""
    if background_tasks is not None:
        background_tasks.add_task(add_log_entry, 'warning', message, source, context)
    else:
        _emit_to_python_logger('warning', message, source, context)

def log_error(message: str, source: str, context: Optional[Dict[str, Any]]=None, background_tasks: Optional[BackgroundTasks]=None):
    """Log an error-level message"""
    if background_tasks is not None:
        background_tasks.add_task(add_log_entry, 'error', message, source, context)
    else:
        _emit_to_python_logger('error', message, source, context)

def log_debug(message: str, source: str, context: Optional[Dict[str, Any]]=None, background_tasks: Optional[BackgroundTasks]=None):
    """Log a debug-level message"""
    if background_tasks is not None:
        background_tasks.add_task(add_log_entry, 'debug', message, source, context)
    else:
        _emit_to_python_logger('debug', message, source, context)