"""
Centralized logging configuration for the VOICERA backend.
Creates a rotating TXT log file and sets a consistent format across modules.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


class DateRotatingFileHandler(TimedRotatingFileHandler):
    """
    Custom rotating file handler that includes date in filename.
    Creates files like: 2025-09-04.log, 2025-09-05.log, etc.
    """
    
    def __init__(self, filename_pattern: str, *args, **kwargs):
        """
        Initialize with a filename pattern containing {date} placeholder.
        
        Args:
            filename_pattern: Pattern like "logs/{date}.log" where {date} will be replaced
        """
        self.filename_pattern = filename_pattern
        
        # Generate initial filename with today's date
        current_date = datetime.now().strftime("%Y-%m-%d")
        initial_filename = filename_pattern.format(date=current_date)
        
        super().__init__(initial_filename, *args, **kwargs)
    
    def doRollover(self):
        """
        Override to create new file with current date in filename.
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # Generate new filename with current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.baseFilename = self.filename_pattern.format(date=current_date)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        
        # Open new log file
        if not self.delay:
            self.stream = self._open()


def setup_logging(log_dir: Optional[str] = None, level: Optional[str] = None) -> None:
    """
    Configure application-wide logging.

    - Writes logs to a rotating TXT log file (daily rotation, 14 backups)
    - Files are named with current date: YYYY-MM-DD.log
    - Also logs to console
    - Safe to call multiple times
    """
    # Determine log directory
    if log_dir is None:
        backend_dir = Path(__file__).resolve().parents[1]
        default_dir = backend_dir / "logs"
        log_dir = os.environ.get("LOG_DIR", str(default_dir))

    os.makedirs(log_dir, exist_ok=True)

    # Determine level
    log_level_name = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logger = logging.getLogger()

    # Avoid duplicating handlers if already configured
    if getattr(logger, "_voicera_logging_configured", False):
        return

    logger.setLevel(log_level)

    fmt = (
        "%(asctime)s | %(levelname)s | %(name)s | pid=%(process)d | "
        "%(filename)s:%(lineno)d | %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"

    # File handler (daily rotation with date in filename)
    log_file_pattern = os.path.join(log_dir, "{date}.log")
    file_handler = DateRotatingFileHandler(
        filename_pattern=log_file_pattern,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    # Attach handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Mark as configured to prevent duplicates
    setattr(logger, "_voicera_logging_configured", True)

    # Example initial log
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_log_file = os.path.join(log_dir, f"{current_date}.log")
    logging.getLogger("voicera").info(
        "Logging initialized. level=%s file=%s", log_level_name, current_log_file
    )