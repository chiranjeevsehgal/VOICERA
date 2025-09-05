from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

class APIUsageStats(BaseModel):
    total_requests: int = 0
    endpoint_counts: Dict[str, int] = {}
    user_counts: Dict[str, int] = {}
    ip_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    hourly_distribution: Dict[str, int] = {}
    date_range: Dict[str, datetime] = {}
    average_response_time: Optional[float] = None
    min_response_time: Optional[float] = None
    max_response_time: Optional[float] = None
    # New detailed analytics
    endpoint_details: List["EndpointDetail"] = []
    ip_details: List["IPDetail"] = []


class EndpointDetail(BaseModel):
    endpoint: str
    count: int
    avg_response_time: Optional[float] = None
    success_rate: Optional[float] = None


class IPDetail(BaseModel):
    ip: str
    count: int
    avg_response_time: Optional[float] = None
    last_seen: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    unique_endpoints: int = 0

class TranscriptionStats(BaseModel):
    total_transcriptions: int = 0
    successful_transcriptions: int = 0
    failed_transcriptions: int = 0
    average_duration: Optional[float] = None
    total_audio_length: Optional[float] = None
    languages: Dict[str, int] = {}
    date_range: Dict[str, datetime] = {}

class SearchTrend(BaseModel):
    term: str
    count: int
    last_searched: datetime

class SearchTrendsResponse(BaseModel):
    top_terms: List[SearchTrend]
    total_searches: int
    unique_terms: int
    date_range: Dict[str, datetime] = {}

class UserActivityData(BaseModel):
    total_active_users: int = 0
    new_users: int = 0
    returning_users: int = 0
    average_session_duration: Optional[float] = None
    most_active_hours: Dict[int, int] = {}
    most_used_features: Dict[str, int] = {}
    date_range: Dict[str, datetime] = {}

class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str
    message: str
    source: str
    context: Dict[str, Any] = {}

class LogFile(BaseModel):
    filename: str
    size: int
    last_modified: datetime
    date: str  # YYYY-MM-DD format extracted from filename

class LogFilesResponse(BaseModel):
    log_files: List[LogFile]
    total_count: int

class LogContentResponse(BaseModel):
    filename: str
    content: str
    size: int
    last_modified: datetime
    total_lines: int

class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total_count: int
    levels_count: Dict[str, int] = {}

# Resolve forward references for Pydantic v2 (no-op if already resolved)
try:
    APIUsageStats.model_rebuild()
except Exception:
    pass