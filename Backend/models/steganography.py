from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class SteganographyRequest(BaseModel):
    """Request model for steganography operations."""
    method: str = Field(default="lsb", description="Steganography method (lsb, echo, phase)")
    metadata: Dict[str, Any] = Field(..., description="Metadata to embed")

class SteganographyResponse(BaseModel):
    """Response model for steganography operations."""
    success: bool = Field(..., description="Operation success status")
    method: str = Field(..., description="Steganography method used")
    file_path: Optional[str] = Field(None, description="Path to the output file")
    metadata_size: Optional[int] = Field(None, description="Size of embedded metadata in bytes")
    message: Optional[str] = Field(None, description="Additional information")

class ExtractedMetadata(BaseModel):
    """Model for extracted metadata."""
    id: str = Field(..., description="Unique identifier")
    timestamp: Optional[float] = Field(None, description="Timestamp when metadata was embedded")
    checksum: Optional[str] = Field(None, description="Original file checksum")
    keywords: Optional[List[str]] = Field(None, description="Keywords extracted from audio")
    vector_id: Optional[str] = Field(None, description="Reference to vector database")
    duration: Optional[float] = Field(None, description="Audio duration in seconds")
    transcription_sample: Optional[str] = Field(None, description="Sample of transcription")
    stego_version: str = Field(..., description="Steganography format version")
    stego_id: str = Field(..., description="Steganography identifier")