# services/background_processor.py
import os
import json
import asyncio
import tempfile
import shutil
import time
from typing import Optional, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename
from fastapi import BackgroundTasks

from services.job_tracker import (
    update_job_status,
    get_job_status,
    JobStatus,
)

# Utility wrappers and services
from services.utility_wrappers import (
    sync_check_credits,
    sync_transcribe_audio,
    sync_embed_metadata,
    sync_upload_to_supabase,
    sync_delete_from_supabase,
    sync_index_transcript,
    sync_update_podcast_url,
    direct_deduct_credit,
)
from utils.content_tracker import (
    sync_track_upload,
    sync_update_upload_status,
    sync_create_podcast,
    sync_create_transcript,
    sync_update_podcast_transcription_status,
)
from utils.analytics import _insert_transcription_stats

# Thread pool for running CPU-bound and blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)


def run_processing_in_thread(
    job_id: str,
    file_content: bytes,
    file_info: dict,
    custom_filename: Optional[str],
    transcription_options_str: str,
    current_user: dict,
    detected_ip: str,
    background_tasks: BackgroundTasks,
):
    """Run the processing in a separate thread with its own event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            process_audio_background(
                job_id,
                file_content,
                file_info,
                custom_filename,
                transcription_options_str,
                current_user,
                detected_ip,
                background_tasks,
            )
        )
    except Exception as e:
        update_job_status(
            job_id,
            JobStatus.FAILED,
            error=f"Thread execution error: {str(e)}",
        )
    finally:
        loop.close()


async def process_audio_background(
    job_id: str,
    file_content: bytes,
    file_info: dict,
    custom_filename: Optional[str],
    transcription_options_str: str,
    current_user: dict,
    detected_ip: str,
    background_tasks: BackgroundTasks,
):
    """Background task to process audio"""
    start_time = time.time()

    # Create a temp directory for processing
    temp_dir = tempfile.mkdtemp()
    local_file_path: Optional[str] = None
    upload_id: Optional[str] = None

    try:
        # Step 1: Check credits
        update_job_status(
            job_id,
            JobStatus.CHECKING_CREDITS,
            current_step="checking_credits",
        )

        try:
            credit_response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    thread_pool, lambda: sync_check_credits(detected_ip, current_user)
                ),
                timeout=15,
            )

            if not isinstance(credit_response, dict):
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error=f"Invalid credit check response: {type(credit_response)}",
                )
                return

            credits_remaining = credit_response.get("credits_remaining", 0)
            if credits_remaining <= 0:
                update_job_status(
                    job_id, JobStatus.FAILED, error="Credit limit reached"
                )
                return

            update_job_status(
                job_id,
                JobStatus.CHECKING_CREDITS,
                progress=10,
                result={"credit_check": credit_response},
            )
        except asyncio.TimeoutError:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Credit check timed out after 15s",
            )
            return
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error checking credits: {str(e)}",
            )
            return

        # Step 2: Save the file locally
        update_job_status(
            job_id,
            JobStatus.UPLOADING,
            progress=10,
            current_step="saving_file",
        )

        def save_file() -> str:
            # Determine filename
            original_filename = file_info["filename"]
            filename = secure_filename(custom_filename or original_filename)

            # Create file path
            upload_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "audio_uploads"
            )
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, f"{filename}")

            # Handle duplicates by adding a counter
            counter = 1
            while os.path.exists(file_path):
                name, ext = os.path.splitext(filename)
                file_path = os.path.join(upload_dir, f"{name}_{counter}{ext}")
                counter += 1

            with open(file_path, "wb") as buffer:
                buffer.write(file_content)

            return file_path

        local_file_path = await asyncio.get_event_loop().run_in_executor(
            thread_pool, save_file
        )

        # Track the upload in content management system
        user_id = str(current_user.get("_id", "unknown"))
        file_name = os.path.basename(local_file_path)
        file_size = os.path.getsize(local_file_path)

        user_metadata: Dict[str, Any] = {
            "job_id": job_id,
            "content_type": file_info["content_type"],
            "original_filename": file_info["filename"],
            "username": current_user.get("username", "unknown"),
            "email": current_user.get("email", "unknown"),
            "user_full_name": current_user.get("full_name", ""),
        }

        upload_id = await asyncio.get_event_loop().run_in_executor(
            thread_pool,
            lambda: sync_track_upload(
                user_id=user_id,
                file_name=file_name,
                file_path=local_file_path,
                file_type="audio",
                file_size=file_size,
                metadata=user_metadata,
            ),
        )

        # Step 3: Upload to Supabase
        update_job_status(
            job_id,
            JobStatus.UPLOADING_TO_SUPABASE,
            progress=20,
            current_step="uploading_to_supabase",
        )

        try:
            supabase_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_upload_to_supabase(
                        local_file_path,
                        file_name,
                        user_id,
                        bucket_name=os.getenv("SUPABASE_BUCKET_ORIGINAL"),
                    ),
                ),
                timeout=90,
            )
        except asyncio.TimeoutError:
            update_job_status(
                job_id, JobStatus.FAILED, error="Supabase upload timed out after 90s"
            )
            return

        if not supabase_result or "file_url" not in supabase_result:
            update_job_status(
                job_id, JobStatus.FAILED, error="Failed to upload to Supabase"
            )
            return

        supabase_url = supabase_result["file_url"]
        original_supabase_file_name = supabase_result.get("file_name")
        original_supabase_file_path = supabase_result.get("file_path")
        original_supabase_bucket = supabase_result.get("bucket")

        if upload_id:
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_upload_status(
                    upload_id=upload_id, status="processing", supabase_url=supabase_url
                ),
            )

        # Step 4: Transcribe the audio
        update_job_status(
            job_id, JobStatus.TRANSCRIBING, current_step="transcribing"
        )

        transcribe_options: Dict[str, Any] = {}
        try:
            try:
                transcribe_options = json.loads(transcription_options_str or "{}")
            except json.JSONDecodeError:
                transcribe_options = {}

            transcription_data = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    thread_pool, lambda: sync_transcribe_audio(supabase_url, transcribe_options)
                ),
                timeout=300,
            )

            if not transcription_data:
                update_job_status(
                    job_id, JobStatus.FAILED, error="Failed to transcribe the audio"
                )
                return

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

            duration = transcription_data.get("metadata", {}).get("duration", 0)
            file_basename = os.path.basename(local_file_path)

            title = file_basename
            if "." in title:
                title = title.rsplit(".", 1)[0]
            title = title.replace("_", " ").replace("-", " ").title()

            author = current_user.get("username", "unknown")
            if current_user.get("full_name"):
                author = current_user.get("full_name")

            # Store podcast creation data for later use after embedded upload
            podcast_creation_data = {
                "title": title,
                "description": f"Uploaded on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                "duration_seconds": duration,
                "author": author,
                "language": detected_language,
                "upload_id": upload_id,
            }

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

            # Store transcript data for later creation after podcast is created
            transcript_creation_data = {
                "content": transcript_text,
                "language": detected_language,
                "segments": segments,
                "confidence_score": confidence,
            }

            try:
                indexed = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        thread_pool,
                        lambda: sync_index_transcript(
                            transcript_data=transcription_data,
                            file_url=supabase_url,
                            file_name=file_basename,
                            is_permanent_url=True,
                        ),
                    ),
                    timeout=120,
                )
                transcription_data["indexed"] = bool(indexed)
            except Exception as e:
                transcription_data["indexed"] = False
                transcription_data["indexing_error"] = str(e)

            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["transcription"] = transcription_data

            update_job_status(
                job_id,
                status=JobStatus.TRANSCRIBING,
                result=current_result,
                progress=50,
            )

            processing_time = time.time() - start_time
            audio_length = transcription_data.get("metadata", {}).get("duration", 0)
            status_val = "success"
            detected_language = transcription_data.get("results", {}).get("channels", [{}])[0].get("detected_language", "en")
            confidence = transcription_data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("confidence", 0)

            # Note: podcast_id and transcript_id will be set after embedded upload
            stats_data = {
                "timestamp": datetime.utcnow(),
                "status": status_val,
                "processing_time": processing_time,
                "audio_length": audio_length,
                "language": detected_language,
                "user_id": str(current_user.get("_id", "")),
                "confidence": confidence,
                "model": transcribe_options.get("model", "default"),
            }

            try:
                await asyncio.wait_for(_insert_transcription_stats(stats_data), timeout=5)
            except asyncio.TimeoutError:
                print("[WARN] _insert_transcription_stats timed out after 5s (success case)")
            except Exception as e:
                print(f"[WARN] _insert_transcription_stats error: {e}")

        except Exception as e:
            processing_time = time.time() - start_time
            error_stats_data = {
                "timestamp": datetime.utcnow(),
                "status": "error",
                "processing_time": processing_time,
                "audio_length": 0,
                "language": transcribe_options.get("language", "en"),
                "user_id": str(current_user.get("_id", "")),
                "error": str(e),
                "url": supabase_url,
            }

            try:
                await asyncio.wait_for(_insert_transcription_stats(error_stats_data), timeout=5)
            except asyncio.TimeoutError:
                print("[WARN] _insert_transcription_stats timed out after 5s (error case)")
            except Exception as e:
                print(f"[WARN] _insert_transcription_stats error (error case): {e}")

            update_job_status(
                job_id, JobStatus.FAILED, error=f"Error transcribing audio: {str(e)}"
            )
            return

        # Step 5: Embed metadata into the audio file
        update_job_status(
            job_id, JobStatus.EMBEDDING, current_step="embedding"
        )

        try:
            temp_embedded_file = os.path.join(
                temp_dir, f"{os.path.basename(local_file_path)}"
            )
            metadata_json = json.dumps(transcription_data)

            embedded_file_path = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_embed_metadata(
                    local_file_path, temp_embedded_file, metadata_json
                ),
            )

            embedding_result = {
                "filename": os.path.basename(embedded_file_path),
                "file_path": embedded_file_path,
            }

            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["embedding"] = embedding_result

            update_job_status(
                job_id,
                status=JobStatus.EMBEDDING,
                result=current_result,
                progress=66,
            )
        except Exception as e:
            update_job_status(
                job_id, JobStatus.FAILED, error=f"Error embedding metadata: {str(e)}"
            )
            return

        # Step 6: Upload embedded file to Supabase (with retry/backoff)
        update_job_status(
            job_id,
            JobStatus.UPLOADING_TO_SUPABASE,
            current_step="uploading_embedded_to_supabase",
            progress=75,
        )
        try:
            embedded_filename = os.path.basename(embedded_file_path)
            max_attempts = 3
            delay = 1.0
            embedded_upload_result = None
            for attempt in range(1, max_attempts + 1):
                try:
                    embedded_upload_result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            thread_pool,
                            lambda: sync_upload_to_supabase(
                                embedded_file_path,
                                embedded_filename,
                                user_id,
                                bucket_name=os.getenv("SUPABASE_BUCKET_EMBEDDED"),
                            ),
                        ),
                        timeout=90,
                    )
                    if embedded_upload_result and "file_url" in embedded_upload_result:
                        break
                except asyncio.TimeoutError:
                    print(
                        f"[WARN] Embedded upload attempt {attempt} timed out after 90s"
                    )
                except Exception as inner_e:
                    print(
                        f"[WARN] Embedded upload attempt {attempt} failed: {inner_e}"
                    )
                if attempt < max_attempts:
                    time.sleep(delay)
                    delay *= 2

            if not embedded_upload_result or "file_url" not in embedded_upload_result:
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error="Failed to upload embedded file to Supabase after retries",
                )
                return

            embedded_supabase_url = embedded_upload_result["file_url"]

            # Now create the podcast with the embedded URL
            podcast_id = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_create_podcast(
                    title=podcast_creation_data["title"],
                    description=podcast_creation_data["description"],
                    audio_url=embedded_supabase_url,  # Use embedded URL
                    duration_seconds=podcast_creation_data["duration_seconds"],
                    author=podcast_creation_data["author"],
                    language=podcast_creation_data["language"],
                    upload_id=podcast_creation_data["upload_id"],
                    supabase_url=embedded_supabase_url,  # Use embedded URL
                    user_id=user_id,
                ),
            )

            # Set transcription status to in_progress
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_podcast_transcription_status(
                    podcast_id=podcast_id, status="in_progress"
                ),
            )

            # Create the transcript
            transcript_id = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_create_transcript(
                    podcast_id=podcast_id,
                    content=transcript_creation_data["content"],
                    language=transcript_creation_data["language"],
                    segments=transcript_creation_data["segments"],
                    confidence_score=transcript_creation_data["confidence_score"],
                ),
            )

            # Update transcription status to completed
            await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: sync_update_podcast_transcription_status(
                    podcast_id=podcast_id,
                    status="completed",
                    transcript_id=transcript_id,
                ),
            )

            # Update analytics stats with podcast_id and transcript_id
            stats_data["podcast_id"] = podcast_id
            stats_data["transcript_id"] = transcript_id

            if upload_id:
                await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    lambda: sync_update_upload_status(
                        upload_id=upload_id,
                        status="processing",
                        supabase_url=embedded_supabase_url,
                    ),
                )

            try:
                delete_flag = (
                    os.getenv("DELETE_ORIGINAL_SUPABASE_FILE", "false").lower()
                    in ("1", "true", "yes")
                )
                if delete_flag and (
                    original_supabase_file_path or original_supabase_file_name
                ):
                    name_or_path = (
                        original_supabase_file_path or original_supabase_file_name
                    )
                    try:
                        await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                thread_pool,
                                lambda: sync_delete_from_supabase(
                                    name_or_path,
                                    bucket_name=(
                                        original_supabase_bucket
                                        or os.getenv("SUPABASE_BUCKET_ORIGINAL")
                                    ),
                                ),
                            ),
                            timeout=30,
                        )
                    except asyncio.TimeoutError:
                        print(
                            "[WARN] Deletion of original Supabase file timed out after 30s"
                        )
            except Exception as del_e:
                print(f"[WARN] Failed to delete original Supabase file: {del_e}")

            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["embedded_supabase_url"] = embedded_supabase_url
            update_job_status(
                job_id,
                status=JobStatus.EMBEDDING,
                result=current_result,
                progress=80,
            )
        except Exception as e:
            update_job_status(
                job_id,
                JobStatus.FAILED,
                error=f"Error uploading embedded file to Supabase: {str(e)}",
            )
            return

        # Step 7: Deduct credit
        update_job_status(
            job_id, JobStatus.DEDUCTING_CREDITS, current_step="deducting_credits"
        )

        try:
            deduct_response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    thread_pool, lambda: direct_deduct_credit(detected_ip, current_user)
                ),
                timeout=20,
            )

            if not deduct_response.get("status", False):
                update_job_status(
                    job_id,
                    JobStatus.FAILED,
                    error=f"Failed to deduct credit: {deduct_response.get('detail', 'Unknown error')}",
                )
                return

            current_result = get_job_status(job_id).get("result", {}) or {}
            current_result["credits"] = deduct_response

            update_job_status(
                job_id,
                status=JobStatus.DEDUCTING_CREDITS,
                result=current_result,
                progress=95,
            )
        except asyncio.TimeoutError:
            update_job_status(
                job_id, JobStatus.FAILED, error="Credit deduction timed out after 20s"
            )
            return
        except Exception as e:
            update_job_status(
                job_id, JobStatus.FAILED, error=f"Error deducting credits: {str(e)}"
            )
            return

        # Done
        update_job_status(job_id, JobStatus.COMPLETED, progress=100)

    except Exception as e:
        update_job_status(
            job_id, JobStatus.FAILED, error=f"Unexpected error: {str(e)}"
        )
    finally:
        if os.path.exists(temp_dir):
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        thread_pool, lambda: shutil.rmtree(temp_dir)
                    ),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                print("[WARN] Temp dir cleanup timed out after 10s")
            except Exception as e:
                print(f"[WARN] Temp dir cleanup error: {e}")
