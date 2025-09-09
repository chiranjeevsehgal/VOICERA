from fastapi import APIRouter, Request, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
import requests
import os
import time
from typing import Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from services.auth import get_current_user
from utils.content_tracker import (
    create_podcast,
    create_transcript,
    update_podcast_transcription_status,
)
from utils.analytics import track_transcription
from utils.logging import log_info, log_warning, log_error
from services.retry_service import retry_decorator, CommonRetryConfigs
from services.circuit_breaker import ServiceCircuitBreakers
from requests.exceptions import RequestException, ConnectionError, Timeout

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
    detect_language: Optional[bool] = Field(
        None, description="Identifies the dominant language spoken"
    )
    diarize: Optional[bool] = Field(None, description="Recognize speaker changes")
    punctuate: Optional[bool] = Field(
        None, description="Add punctuation and capitalization"
    )
    smart_format: Optional[bool] = Field(
        None, description="Apply additional formatting for readability"
    )
    utterances: Optional[bool] = Field(
        None, description="Segment speech into meaningful units"
    )
    model: Optional[str] = Field(
        None, description="AI model used (e.g., 'nova', 'nova-2')"
    )
    language: Optional[str] = Field(
        None, description="Primary spoken language (e.g., 'en', 'es')"
    )
    numerals: Optional[bool] = Field(
        None, description="Convert numbers to numerical format"
    )
    profanity_filter: Optional[bool] = Field(None, description="Filter out profanity")
    redact: Optional[List[str]] = Field(
        None, description="Terms to redact from transcription"
    )
    keywords: Optional[List[str]] = Field(
        None, description="Keywords to boost in recognition"
    )
    sentiment: Optional[bool] = Field(None, description="Analyze sentiment in speech")
    topics: Optional[bool] = Field(
        None, description="Detect topics throughout transcript"
    )
    summarize: Optional[str] = Field(None, description="Generate summary (v1 or v2)")
    custom_intent_mode: Optional[str] = Field(
        None, description="Sets how model interprets intents ('extended' or 'strict')"
    )
    # For content management integration
    upload_id: Optional[str] = Field(
        None, description="ID of the uploaded file in the system"
    )
    title: Optional[str] = Field(None, description="Title for the podcast")
    description: Optional[str] = Field(None, description="Description for the podcast")

    class Config:
        schema_extra = {
            "example": {
                "url": "https://dpgr.am/spacewalk.wav",
                "punctuate": True,
                "diarize": True,
                "smart_format": True,
                "language": "en",
                "model": "nova-2",
                "title": "Sample Podcast Title",
                "description": "This is a sample podcast description.",
            }
        }


@router.post(
    "/transcribe",
    summary="Transcribe audio using Deepgram API",
    description="Transcribes audio from a URL using Deepgram's speech-to-text API with multiple customization options",
)
async def transcribe_audio(
    request: TranscriptionRequest,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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
    # Start timer for tracking processing time
    start_time = time.time()

    # Check if API key is available
    if not DEEPGRAM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deepgram API key not configured on server",
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
            "detect_language",
            "diarize",
            "punctuate",
            "smart_format",
            "utterances",
            "model",
            "language",
            "numerals",
            "profanity_filter",
            "sentiment",
            "topics",
            "summarize",
            "custom_intent_mode",
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

        # Make request to Deepgram API with circuit breaker protection
        deepgram_breaker = ServiceCircuitBreakers.get_deepgram_breaker()

        async def make_deepgram_request():
            return requests.post(
                deepgram_url,
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=body_params,
                timeout=30,
            )

        response = await deepgram_breaker.call(make_deepgram_request)

        # Log request details for debugging
        log_info(
            f"Making Deepgram API request",
            "transcribe",
            {"url": deepgram_url, "body_params": body_params},
        )

        # Check if request was successful
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Error from Deepgram API: {response.text}",
            )

        # Get the response data
        transcription_data = response.json()

        # Create podcast and transcript records if upload_id is provided
        podcast_id = None
        transcript_id = None

        if request.upload_id:
            # Extract transcript information
            results = transcription_data.get("results", {})
            transcript_text = (
                results.get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            detected_language = results.get("channels", [{}])[0].get(
                "detected_language", "en"
            )
            confidence = (
                results.get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("confidence", 0)
            )
            words = (
                results.get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("words", [])
            )

            # Get duration
            duration = transcription_data.get("metadata", {}).get("duration", 0)

            # Get file name from URL
            file_name = os.path.basename(request.url)

            # Create podcast record
            podcast_id = await create_podcast(
                title=request.title or file_name,
                description=request.description
                or f"Transcribed on {os.environ.get('HOSTNAME', 'Voicera')}",
                audio_url=request.url,
                duration_seconds=duration,
                author=current_user.get("username", "unknown"),
                language=detected_language or request.language or "en",
                upload_id=request.upload_id,
                user_id=str(current_user.get("_id", "")),
            )

            log_info(
                f"Created podcast record with ID: {podcast_id}",
                "transcribe",
                {"podcast_id": podcast_id, "upload_id": request.upload_id},
            )

            if podcast_id:  # Only proceed if podcast was successfully created
                # Mark podcast as transcription in progress
                await update_podcast_transcription_status(
                    podcast_id=podcast_id, status="in_progress"
                )

                # Create segments from words
                segments = []
                if words:
                    for word in words:
                        segments.append(
                            {
                                "text": word.get("word", ""),
                                "start": word.get("start", 0),
                                "end": word.get("end", 0),
                                "confidence": word.get("confidence", 0),
                            }
                        )

                # Create transcript record
                transcript_id = await create_transcript(
                    podcast_id=podcast_id,
                    content=transcript_text,
                    language=detected_language or request.language or "en",
                    segments=segments,
                    confidence_score=confidence,
                )

                log_info(
                    f"Created transcript record with ID: {transcript_id}",
                    "transcribe",
                    {"transcript_id": transcript_id, "podcast_id": podcast_id},
                )

                # Update podcast with transcription status
                # Verify transcription status was properly updated
                status_update = await update_podcast_transcription_status(
                    podcast_id=podcast_id,
                    status="completed",
                    transcript_id=transcript_id,
                )

                # If update failed, retry once with a delay
                if not status_update:
                    log_warning(
                        "First attempt to update transcription status failed, retrying",
                        "transcribe",
                        {"podcast_id": podcast_id},
                    )
                    import asyncio

                    await asyncio.sleep(1)  # Short delay before retry
                    await update_podcast_transcription_status(
                        podcast_id=podcast_id,
                        status="completed",
                        transcript_id=transcript_id,
                    )

                    # Verify the status was actually updated
                    from services.database import podcasts_collection
                    from bson import ObjectId

                    podcast_check = await podcasts_collection.find_one(
                        {"_id": ObjectId(podcast_id)}
                    )
                    if (
                        podcast_check
                        and podcast_check.get("transcription_status") != "completed"
                    ):
                        log_error(
                            f"Failed to update transcription status for podcast {podcast_id}",
                            "transcribe",
                            {"podcast_id": podcast_id},
                        )

                # Add the IDs to the response
                transcription_data["podcast_id"] = podcast_id
                transcription_data["transcript_id"] = transcript_id
            else:
                # If podcast creation failed, log and potentially update upload status to failed
                log_error(
                    f"Podcast creation failed for upload_id: {request.upload_id}. Skipping transcript creation.",
                    "transcribe",
                    {"upload_id": request.upload_id},
                )
                if request.upload_id:
                    from utils.content_tracker import update_upload_status

                    await update_upload_status(
                        upload_id=request.upload_id,
                        status="failed",
                        error_message="Podcast creation failed during transcription.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create podcast record during transcription.",
                )

        # Track transcription
        processing_time = time.time() - start_time
        audio_length = transcription_data.get("metadata", {}).get("duration", 0)
        status = "success"

        # Initialize variables for tracking
        detected_language = "en"
        confidence = 0

        # Extract transcript information if available
        if "results" in transcription_data:
            results = transcription_data.get("results", {})
            detected_language = results.get("channels", [{}])[0].get(
                "detected_language", "en"
            )
            confidence = (
                results.get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("confidence", 0)
            )

        # Make sure podcast_id and transcript_id are included in tracking
        track_data = {"confidence": confidence, "model": request.model or "default"}

        if podcast_id:
            track_data["podcast_id"] = podcast_id
        if transcript_id:
            track_data["transcript_id"] = transcript_id

        track_transcription(
            status=status,
            processing_time=processing_time,
            audio_length=audio_length,
            language=detected_language or request.language or "en",
            user_id=str(current_user.get("_id", "")),
            additional_data=track_data,
            background_tasks=background_tasks,  # Pass background_tasks here
        )

        return transcription_data
    except Exception as e:
        # Track transcription error
        try:
            processing_time = time.time() - start_time
            track_transcription(
                status="error",
                processing_time=processing_time,
                audio_length=0,  # Unknown in case of error
                language=request.language or "en",
                user_id=str(current_user.get("_id", "")),
                additional_data={"error": str(e), "url": request.url},
                background_tasks=background_tasks,  # Pass background_tasks here
            )
        except Exception as tracking_error:
            log_error(
                f"Error tracking transcription failure: {tracking_error}",
                "transcribe",
                {"tracking_error": str(tracking_error)},
            )

        raise HTTPException(
            status_code=500, detail=f"Error transcribing audio: {str(e)}"
        )
