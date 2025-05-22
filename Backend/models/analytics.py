from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

class APIUsageStats(BaseModel):
    total_requests: int = 0
    endpoint_counts: Dict[str, int] = {}
    user_counts: Dict[str, int] = {}
    date_range: Dict[str, datetime] = {}
    average_response_time: Optional[float] = None

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

class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total_count: int
    levels_count: Dict[str, int] = {} 