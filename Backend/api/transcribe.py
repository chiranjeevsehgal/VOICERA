from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import requests
import os
from typing import Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from services.auth import get_current_user

# Load environment variables
load_dotenv()

# Get Deepgram API key from environment variables
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

router = APIRouter()

class TranscriptionRequest(BaseModel):
    """
    Request model for the Deepgram transcription API.
    
    Required Parameters:
    - url: The URL of the audio file to transcribe
    
    Optional Parameters (all features from Deepgram's API):
    - detect_language: Identifies the dominant language spoken in the audio
    - diarize: Recognizes and labels different speakers in the conversation
    - punctuate: Adds punctuation and capitalization to make transcripts more readable
    - smart_format: Applies additional formatting for numbers, dates, and other entities
    - utterances: Segments speech into meaningful semantic units based on natural pauses
    - model: Specifies which Deepgram AI model to use (e.g., 'nova', 'nova-2', 'whisper')
    - language: Hints at the primary spoken language using BCP-47 language tag (e.g., 'en', 'es', 'fr')
    - numerals: Converts numbers from words to numerical format (e.g., "twenty three" -> "23")
    - profanity_filter: Removes or replaces profanity in the transcript
    - redact: List of sensitive terms or phrases to remove from the transcript
    - keywords: List of terms to boost recognition for (improves accuracy for specific terminology)
    - sentiment: Analyzes the emotional tone of the speech (positive, negative, neutral)
    - topics: Identifies the main subjects discussed in the audio
    - summarize: Generates a concise summary of the audio content (v1 or v2)
    - custom_intent_mode: Sets how the model interprets intents ('extended' or 'strict')
    
    For full documentation on these parameters, see:
    https://developers.deepgram.com/reference/speech-to-text-api/listen
    """
    url: str
    # Add more optional parameters from Deepgram API
    detect_language: Optional[bool] = Field(None, description="Identifies the dominant language spoken")
    diarize: Optional[bool] = Field(None, description="Recognize speaker changes")
    punctuate: Optional[bool] = Field(None, description="Add punctuation and capitalization")
    smart_format: Optional[bool] = Field(None, description="Apply additional formatting for readability")
    utterances: Optional[bool] = Field(None, description="Segment speech into meaningful units")
    model: Optional[str] = Field(None, description="AI model used (e.g., 'nova', 'nova-2')")
    language: Optional[str] = Field(None, description="Primary spoken language (e.g., 'en', 'es')")
    numerals: Optional[bool] = Field(None, description="Convert numbers to numerical format")
    profanity_filter: Optional[bool] = Field(None, description="Filter out profanity")
    redact: Optional[List[str]] = Field(None, description="Terms to redact from transcription")
    keywords: Optional[List[str]] = Field(None, description="Keywords to boost in recognition")
    sentiment: Optional[bool] = Field(None, description="Analyze sentiment in speech")
    topics: Optional[bool] = Field(None, description="Detect topics throughout transcript")
    summarize: Optional[str] = Field(None, description="Generate summary (v1 or v2)")
    custom_intent_mode: Optional[str] = Field(None, description="Sets how model interprets intents ('extended' or 'strict')")

    class Config:
        schema_extra = {
            "example": {
                "url": "https://dpgr.am/spacewalk.wav",
                "punctuate": True,
                "diarize": True,
                "smart_format": True,
                "language": "en",
                "model": "nova-2"
            }
        }

@router.post(
    "/transcribe", 
    summary="Transcribe audio using Deepgram API",
    description="Transcribes audio from a URL using Deepgram's speech-to-text API with multiple customization options"
)
async def transcribe_audio(
    request: TranscriptionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Transcribe audio from a URL using Deepgram API.
    
    This endpoint takes a URL to an audio file and returns a full transcription.
    It supports various customization options such as language detection, diarization,
    punctuation, and more.
    
    Example body:
    {
        "url": "https://storage.googleapis.com/example-audio.mp3",
        "detect_language": true,
        "diarize": true,
        "model": "general"
    }
    """
    # Check if API key is available
    if not DEEPGRAM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deepgram API key not configured on server"
        )
    
    try:
        # Initialize API URL
        deepgram_url = "https://api.deepgram.com/v1/listen"
        
        # Extract query parameters (Deepgram sometimes works better with query params for certain features)
        query_params = {}
        body_params = {"url": request.url}
        
        # Parameters that work better as query parameters
        query_param_fields = ["language", "custom_intent_mode"]
        
        # Add parameters to the appropriate destination
        for param in [
            "detect_language", "diarize", "punctuate", "smart_format", 
            "utterances", "model", "language", "numerals", 
            "profanity_filter", "sentiment", "topics", "summarize",
            "custom_intent_mode"
        ]:
            value = getattr(request, param)
            if value is not None:
                # Some parameters work better as query parameters for Deepgram
                if param in query_param_fields:
                    query_params[param] = value
                else:
                    body_params[param] = value
                
        # Handle list parameters separately (always in body)
        if request.redact:
            body_params["redact"] = request.redact
        if request.keywords:
            body_params["keywords"] = request.keywords
            
        # Construct URL with query parameters if any
        if query_params:
            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            deepgram_url = f"{deepgram_url}?{query_string}"
        
        # Make request to Deepgram API
        response = requests.post(
            deepgram_url,
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json"
            },
            json=body_params,
        )
        
        # Log request details for debugging (remove in production)
        print(f"Request URL: {deepgram_url}")
        print(f"Request Body: {body_params}")
        
        # Check if request was successful
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"Error from Deepgram API: {response.text}"
            )
            
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error transcribing audio: {str(e)}") 