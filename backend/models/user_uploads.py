from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserUpload(BaseModel):
    id: str
    user_id: str
    file_name: str
    file_path: str
    file_url: str
    created_at: datetime
    metadata: Optional[dict] = None

class UserUploadCreate(BaseModel):
    user_id: str
    file_name: str
    file_path: str
    file_url: str
    metadata: Optional[dict] = None