from pydantic import BaseModel, Field, HttpUrl
from typing import Dict, List, Optional, Any
from datetime import datetime

class PodcastBase(BaseModel):
    title: str
    description: str
    image_url: Optional[HttpUrl] = None
    audio_url: HttpUrl
    duration_seconds: float
    author: str
    published_date: datetime
    tags: List[str] = []
    language: str = "en"
    
class PodcastCreate(PodcastBase):
    pass

class Podcast(PodcastBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    views: int = 0
    likes: int = 0
    average_rating: Optional[float] = None
    is_featured: bool = False
    is_published: bool = True
    transcription_status: str = "pending"  # pending, in_progress, completed, failed

class PodcastsResponse(BaseModel):
    podcasts: List[Podcast]
    total_count: int
    page: int
    limit: int

class TranscriptBase(BaseModel):
    podcast_id: Optional[str] = None
    content: str
    language: str = "en"
    is_edited: bool = False
    
class TranscriptCreate(TranscriptBase):
    pass

class Transcript(TranscriptBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    segments: Optional[List[Dict[str, Any]]] = None
    confidence_score: Optional[float] = None
    word_count: Optional[int] = None
    is_published: bool = True

class TranscriptsResponse(BaseModel):
    transcripts: List[Transcript]
    total_count: int
    page: int
    limit: int

class UploadBase(BaseModel):
    user_id: str
    file_name: str
    file_path: str
    file_url: str
    file_type: str  # audio, image, document
    file_size: int  # in bytes
    metadata: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending, processing, completed, failed

class UploadCreate(UploadBase):
    pass

class Upload(UploadBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    podcast_id: Optional[str] = None
    error_message: Optional[str] = None

class UploadsResponse(BaseModel):
    uploads: List[Upload]
    total_count: int
    page: int
    limit: int

class FeaturedContentBase(BaseModel):
    title: str
    description: str
    image_url: HttpUrl
    target_url: HttpUrl
    content_type: str  # podcast, playlist, channel, etc.
    priority: int = 0  # Higher number = higher priority
    
class FeaturedContentCreate(FeaturedContentBase):
    pass

class FeaturedContent(FeaturedContentBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    click_count: int = 0
    view_count: int = 0

class FeaturedContentResponse(BaseModel):
    featured_items: List[FeaturedContent]
    total_count: int
    page: int
    limit: int 