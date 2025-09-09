import os
import json
import time
import hashlib
import threading
import random
import math
from typing import List, Dict, Any, Optional
from collections import deque
from together import Together
from pinecone import Pinecone, ServerlessSpec, CloudProvider, AwsRegion
from dotenv import load_dotenv
import requests
from utils.logging import log_info, log_warning, log_error
from services.gemini_key_manager import gemini_key_manager

# Load environment variables
load_dotenv()

# Configuration
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "gcp-starter")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "voicera-audio-search")
EMBEDDING_MODEL = os.getenv("TOGETHER_EMBEDDING_MODEL", "togethercomputer/m2-bert-80M-32k-retrieval")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))  # 768 for m2-bert-80M-32k-retrieval
EMBED_MAX_CONCURRENCY = int(os.getenv("EMBED_MAX_CONCURRENCY", "3"))
EMBED_MAX_RETRIES = int(os.getenv("EMBED_MAX_RETRIES", "5"))
EMBED_RETRY_BASE_DELAY = float(os.getenv("EMBED_RETRY_BASE_DELAY", "0.5"))
UPSERT_BATCH_SIZE = int(os.getenv("UPSERT_BATCH_SIZE", "100"))
UPSERT_MAX_CONCURRENCY = int(os.getenv("UPSERT_MAX_CONCURRENCY", "2"))
UPSERT_MAX_RETRIES = int(os.getenv("UPSERT_MAX_RETRIES", "5"))
UPSERT_RETRY_BASE_DELAY = float(os.getenv("UPSERT_RETRY_BASE_DELAY", "0.5"))

# Embedding provider switch: 0 = Together, 1 = Google Gemini
EMBED_PROVIDER = int(os.getenv("EMBED_PROVIDER", "1"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_EMBED_RPM = int(os.getenv("GEMINI_EMBED_RPM", "100"))       # requests per minute
GEMINI_EMBED_TPM = int(os.getenv("GEMINI_EMBED_TPM", "30000"))      # tokens per minute
GEMINI_EMBED_RPD = int(os.getenv("GEMINI_EMBED_RPD", "1000"))       # requests per day
GEMINI_BATCH_SIZE = int(os.getenv("GEMINI_BATCH_SIZE", "16"))       # max texts per batch request
GEMINI_EMBED_RPS = int(os.getenv("GEMINI_EMBED_RPS", "2"))          # requests per second (soft throttle)
GEMINI_TPM_SAFETY = float(os.getenv("GEMINI_TPM_SAFETY", "0.9"))    # use 90% of TPM to be safe
GEMINI_TOKEN_OVERHEAD = int(os.getenv("GEMINI_TOKEN_OVERHEAD", "32")) # overhead tokens per request
GEMINI_MAX_BATCH_TOKENS = int(os.getenv("GEMINI_MAX_BATCH_TOKENS", "20000"))

SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
CLASSIFICATION = "CLASSIFICATION"
CLUSTERING = "CLUSTERING"
RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
RETRIEVAL_QUERY = "RETRIEVAL_QUERY"
CODE_RETRIEVAL_QUERY = "CODE_RETRIEVAL_QUERY"
FACT_VERIFICATION = "FACT_VERIFICATION"

# Initialize the Together AI client lazily to avoid requiring the key when using Google
together_client = None  # type: ignore

# Global semaphore to limit concurrent embedding requests (helps prevent 429s in bulk)
_embedding_sem = threading.Semaphore(EMBED_MAX_CONCURRENCY)

# Global semaphore to limit concurrent Pinecone upserts
_upsert_sem = threading.Semaphore(UPSERT_MAX_CONCURRENCY)

# --- Google Gemini embedding rate limiter (RPM/TPM/RPD) ---
_rate_lock = threading.Lock()
_rpm_timestamps: deque = deque()           # timestamps of requests in last 60s
_tpm_entries: deque = deque()              # (timestamp, token_count) in last 60s
_rps_timestamps: deque = deque()           # timestamps of requests in last 1s
_daily_date: Optional[str] = None
_daily_count: int = 0

def _estimate_tokens_for_gemini(text: str) -> int:
    """Rough token estimate for Gemini embeddings. ~4 chars per token heuristic.
    Avoids external deps while being conservative for TPM budgeting.
    """
    if not text:
        return 1
    # Use max of words and char/3 to be more conservative
    words = len([w for w in text.split() if w])
    approx_chars = max(1, len(text))
    return max(1, max(words, approx_chars // 3))

def _enforce_gemini_rate_limits(token_count: int) -> None:
    """Block until Gemini RPM/TPM budgets allow another request.
    Enforces per-minute request and token limits and a per-day request cap.
    Thread-safe; uses a rolling window.
    """
    global _daily_date, _daily_count
    while True:
        now = time.time()
        with _rate_lock:
            # Reset daily counters if day changed
            today = time.strftime("%Y-%m-%d", time.localtime(now))
            if _daily_date != today:
                _daily_date = today
                _daily_count = 0
                _rpm_timestamps.clear()
                _tpm_entries.clear()

            # Enforce per-day limit
            if GEMINI_EMBED_RPD > 0 and _daily_count >= GEMINI_EMBED_RPD:
                raise RuntimeError("Gemini embedding daily request limit reached (RPD)")

            # Prune entries older than 60s / 1s
            one_min_ago = now - 60.0
            one_sec_ago = now - 1.0
            while _rpm_timestamps and _rpm_timestamps[0] <= one_min_ago:
                _rpm_timestamps.popleft()
            while _tpm_entries and _tpm_entries[0][0] <= one_min_ago:
                _tpm_entries.popleft()
            while _rps_timestamps and _rps_timestamps[0] <= one_sec_ago:
                _rps_timestamps.popleft()

            reqs_last_min = len(_rpm_timestamps)
            tokens_last_min = sum(t for (_, t) in _tpm_entries)
            reqs_last_sec = len(_rps_timestamps)

            rpm_ok = reqs_last_min < GEMINI_EMBED_RPM
            rps_ok = reqs_last_sec < GEMINI_EMBED_RPS
            tpm_limit_eff = int(GEMINI_EMBED_TPM * GEMINI_TPM_SAFETY)
            tpm_ok = (tokens_last_min + token_count) <= tpm_limit_eff

            if rpm_ok and rps_ok and tpm_ok:
                # Reserve budget and proceed
                _rpm_timestamps.append(now)
                _tpm_entries.append((now, token_count))
                _rps_timestamps.append(now)
                _daily_count += 1
                return

            # Compute wait time until budget frees
            waits: List[float] = []
            if not rpm_ok and _rpm_timestamps:
                waits.append(_rpm_timestamps[0] + 60.0 - now)
            if not rps_ok and _rps_timestamps:
                waits.append(_rps_timestamps[0] + 1.0 - now)
            if not tpm_ok and _tpm_entries:
                # Find time when enough tokens expire
                need = tokens_last_min + token_count - tpm_limit_eff
                acc = 0
                for ts, t in _tpm_entries:
                    acc += t
                    if acc >= need:
                        waits.append(ts + 60.0 - now)
                        break

        # Sleep outside lock for the minimum required time
        sleep_s = max(0.05, min(max(waits) if waits else 0.5, 60.0))
        time.sleep(sleep_s)

# Initialize Pinecone client
pc = None
index = None

def _l2_normalize(vec: List[float]) -> List[float]:
    """L2-normalize a vector to unit length."""
    if not vec:
        return vec
    norm = math.sqrt(sum((x * x) for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]

def init_pinecone():
    """Initialize the Pinecone client and create index if it doesn't exist"""
    global pc, index
    try:
        if not PINECONE_API_KEY:
            log_warning("PINECONE_API_KEY is not set. Vector search will not work.", "pinecone_service")
            return False

        log_info(f"Initializing Pinecone with API key: {PINECONE_API_KEY[:5]}...", "pinecone_service")
        
        # Initialize the Pinecone client
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # List all indexes and print them
        existing_indexes = pc.list_indexes()
        log_info(f"Found existing indexes: {[index.name for index in existing_indexes]}", "pinecone_service")
        
        # Check if our index already exists
        if PINECONE_INDEX_NAME not in [index.name for index in existing_indexes]:
            log_info(f"Creating new index: {PINECONE_INDEX_NAME}", "pinecone_service")
            # Create a new index
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=CloudProvider.AWS,
                    region=AwsRegion.US_EAST_1
                )
            )
            log_info(f"Created new Pinecone index: {PINECONE_INDEX_NAME}", "pinecone_service")
            # Wait for index initialization
            time.sleep(10)
        
        # Connect to the index
        index_info = pc.describe_index(PINECONE_INDEX_NAME)
        log_info(f"Index info: {index_info}", "pinecone_service")
        index = pc.Index(host=index_info.host)
        
        # Get index stats
        try:
            stats = index.describe_index_stats()
            log_info(f"Index stats: {stats}", "pinecone_service")
            log_info(f"Total vectors in index: {stats.get('total_vector_count', 0)}", "pinecone_service")
        except Exception as e:
            log_error(f"Error getting index stats: {str(e)}", "pinecone_service", {"error": str(e)})
        
        log_info(f"Successfully connected to Pinecone index: {PINECONE_INDEX_NAME}", "pinecone_service")
        return True
    except Exception as e:
        log_error(f"Error initializing Pinecone: {str(e)}", "pinecone_service", {"error": str(e)})
        return False

def get_embedding(text: str, task_type: Optional[str] = None) -> List[float]:
    """
    Generate an embedding vector for a text string using the selected provider.
    Provider switch: 0=Together, 1=Google Gemini.
    Bounded concurrency and retries are applied to handle rate limits in bulk mode.
    """
    last_err = None

    # Provider: Together AI
    if EMBED_PROVIDER == 0:
        if not TOGETHER_API_KEY:
            log_error("TOGETHER_API_KEY is not set", "pinecone_service")
            raise ValueError("TOGETHER_API_KEY is not set")

        global together_client
        if together_client is None:
            together_client = Together(api_key=TOGETHER_API_KEY)

        for attempt in range(1, EMBED_MAX_RETRIES + 1):
            try:
                # Bound concurrency across threads
                with _embedding_sem:
                    log_info(f"Generating embedding (attempt {attempt}) for text: {text[:100]}...", "pinecone_service", {"attempt": attempt, "model": EMBEDDING_MODEL})
                    response = together_client.embeddings.create(
                        model=EMBEDDING_MODEL,
                        input=text
                    )
                embedding = response.data[0].embedding
                log_info(f"Generated embedding of dimension: {len(embedding)}", "pinecone_service", {"dimension": len(embedding)})
                return embedding
            except Exception as e:
                last_err = e
                # Exponential backoff with jitter
                sleep_s = EMBED_RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                msg = str(e)
                log_warning(f"Together embedding attempt {attempt} failed: {msg}. Retrying in {sleep_s:.2f}s...", "pinecone_service", {"attempt": attempt, "error": msg, "sleep_time": sleep_s})
                time.sleep(sleep_s)

        # Exhausted retries
        log_error(f"Failed to generate Together embedding after {EMBED_MAX_RETRIES} attempts: {last_err}", "pinecone_service", {"max_retries": EMBED_MAX_RETRIES, "error": str(last_err)})
        raise last_err

    # Provider: Google Gemini
    elif EMBED_PROVIDER == 1:
        if not gemini_key_manager.has_keys():
            log_error("No Gemini API keys configured", "pinecone_service")
            raise ValueError("No Gemini API keys configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:embedContent"

        for attempt in range(1, EMBED_MAX_RETRIES + 1):
            try:
                # Estimate tokens and acquire a key with available budget
                token_count = _estimate_tokens_for_gemini(text) + GEMINI_TOKEN_OVERHEAD
                api_key = gemini_key_manager.acquire(token_count, request_type="embed")
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                }
                with _embedding_sem:
                    log_info(f"Generating Google embedding (attempt {attempt}) for text: {text[:100]}...", "pinecone_service", {"attempt": attempt, "model": GEMINI_EMBED_MODEL, "dimension": EMBEDDING_DIMENSION})
                    payload: Dict[str, Any] = {
                        "content": {"parts": [{"text": text}]}
                    }
                    if EMBEDDING_DIMENSION and EMBEDDING_DIMENSION != 3072:
                        payload["outputDimensionality"] = EMBEDDING_DIMENSION
                    # Respect caller-provided task_type; default to document embeddings
                    if task_type:
                        payload["taskType"] = task_type
                    else:
                        payload["taskType"] = RETRIEVAL_DOCUMENT

                    try:
                        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
                    except requests.Timeout:
                        # Deadline exceeded
                        gemini_key_manager.report_result(api_key, 504, None, status="DEADLINE_EXCEEDED")
                        raise
                    except requests.ConnectionError:
                        gemini_key_manager.report_result(api_key, 503, None, status="UNAVAILABLE")
                        raise
                    except requests.RequestException:
                        gemini_key_manager.report_result(api_key, 500, None, status="INTERNAL")
                        raise
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    # Inform manager so it can cooldown this key
                    try:
                        ra = float(retry_after) if retry_after and str(retry_after).isdigit() else None
                    except Exception:
                        ra = None
                    gemini_key_manager.report_result(api_key, 429, ra, status="RESOURCE_EXHAUSTED")
                    sleep_s = ra if ra is not None else EMBED_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    log_warning(f"Google embedding 429. Respecting Retry-After: sleeping {sleep_s:.2f}s", "pinecone_service", {"sleep_time": sleep_s})
                    time.sleep(sleep_s)
                    continue
                if resp.status_code >= 400:
                    err_status = None
                    try:
                        body = resp.json()
                        err = body.get("error") if isinstance(body, dict) else None
                        if isinstance(err, dict):
                            err_status = err.get("status")
                    except Exception:
                        err_status = None
                    gemini_key_manager.report_result(api_key, resp.status_code, None, status=err_status)
                    raise RuntimeError(f"Google Embedding HTTP {resp.status_code}: {resp.text}")

                # Success
                gemini_key_manager.report_result(api_key, 200, None)
                data = resp.json()
                # Response may be either {"embedding": {"values": [...]}} or batched {"embeddings": [{"values": [...]}]}
                embedding = None
                if isinstance(data, dict):
                    if "embedding" in data and isinstance(data["embedding"], dict):
                        embedding = data["embedding"].get("values")
                    elif "embeddings" in data and isinstance(data["embeddings"], list) and data["embeddings"]:
                        embedding = data["embeddings"][0].get("values")

                if not embedding or not isinstance(embedding, list):
                    raise RuntimeError(f"Google Embedding: no embedding values in response: {data}")

                # Normalize for non-default dimensionality (per Google guidance)
                if EMBEDDING_DIMENSION != 3072:
                    embedding = _l2_normalize([float(x) for x in embedding])

                log_info(f"Generated Google embedding of dimension: {len(embedding)}", "pinecone_service", {"dimension": len(embedding)})
                return embedding  # type: ignore
            except Exception as e:
                last_err = e
                sleep_s = EMBED_RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                msg = str(e)
                log_warning(f"Google embedding attempt {attempt} failed: {msg}. Retrying in {sleep_s:.2f}s...", "pinecone_service", {"attempt": attempt, "error": msg, "sleep_time": sleep_s})
                time.sleep(sleep_s)

        log_error(f"Failed to generate Google embedding after {EMBED_MAX_RETRIES} attempts: {last_err}", "pinecone_service", {"max_retries": EMBED_MAX_RETRIES, "error": str(last_err)})
        raise last_err

    else:
        raise ValueError(f"Unsupported EMBED_PROVIDER value: {EMBED_PROVIDER}")

def _gemini_embed_batch(texts: List[str], task_type: Optional[str] = None) -> List[List[float]]:
    """
    Batch embed multiple texts with Google Gemini to reduce API calls.
    Respects RPM/TPM/RPD using the same limiter with summed token estimate.
    Returns list of embeddings aligned to input order.
    """
    if not gemini_key_manager.has_keys():
        raise ValueError("No Gemini API keys configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:batchEmbedContents"
    # headers will be constructed per-attempt after acquiring a key

    # Build requests array
    reqs: List[Dict[str, Any]] = []
    for t in texts:
        item: Dict[str, Any] = {
            "content": {"parts": [{"text": t}]}
        }
        # Batch endpoint requires model per request item
        item["model"] = f"models/{GEMINI_EMBED_MODEL}"
        if EMBEDDING_DIMENSION and EMBEDDING_DIMENSION != 3072:
            item["outputDimensionality"] = EMBEDDING_DIMENSION
        if task_type:
            item["taskType"] = task_type
        reqs.append(item)

    # Token estimate for the whole batch; manager will block until a key is available
    batch_tokens = sum(_estimate_tokens_for_gemini(t) + GEMINI_TOKEN_OVERHEAD for t in texts)

    last_err: Optional[Exception] = None
    for attempt in range(1, EMBED_MAX_RETRIES + 1):
        try:
            # Acquire a key for this batch attempt
            api_key = gemini_key_manager.acquire(batch_tokens, request_type="embed")
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            with _embedding_sem:
                payload = {"requests": reqs}
                log_info(f"Batch embedding {len(texts)} items (attempt {attempt}) with model {GEMINI_EMBED_MODEL}, dim {EMBEDDING_DIMENSION}", "pinecone_service", {"batch_size": len(texts), "attempt": attempt, "model": GEMINI_EMBED_MODEL, "dimension": EMBEDDING_DIMENSION})
                try:
                    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
                except requests.Timeout:
                    gemini_key_manager.report_result(api_key, 504, None, status="DEADLINE_EXCEEDED")
                    raise
                except requests.ConnectionError:
                    gemini_key_manager.report_result(api_key, 503, None, status="UNAVAILABLE")
                    raise
                except requests.RequestException:
                    gemini_key_manager.report_result(api_key, 500, None, status="INTERNAL")
                    raise
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    ra = float(retry_after) if retry_after and str(retry_after).isdigit() else None
                except Exception:
                    ra = None
                gemini_key_manager.report_result(api_key, 429, ra, status="RESOURCE_EXHAUSTED")
                sleep_s = ra if ra is not None else EMBED_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log_warning(f"Google batch embedding 429. Respecting Retry-After: sleeping {sleep_s:.2f}s", "pinecone_service", {"sleep_time": sleep_s})
                time.sleep(sleep_s)
                continue
            if resp.status_code >= 400:
                err_status = None
                try:
                    body = resp.json()
                    err = body.get("error") if isinstance(body, dict) else None
                    if isinstance(err, dict):
                        err_status = err.get("status")
                except Exception:
                    err_status = None
                gemini_key_manager.report_result(api_key, resp.status_code, None, status=err_status)
                raise RuntimeError(f"Google Batch Embedding HTTP {resp.status_code}: {resp.text}")
            gemini_key_manager.report_result(api_key, 200, None)
            data = resp.json()
            if not isinstance(data, dict) or "embeddings" not in data or not isinstance(data["embeddings"], list):
                raise RuntimeError(f"Google Batch Embedding: invalid response: {data}")
            embeddings_out: List[List[float]] = []
            for e in data["embeddings"]:
                vals = e.get("values") if isinstance(e, dict) else None
                if not vals or not isinstance(vals, list):
                    raise RuntimeError("Google Batch Embedding: missing values in one item")
                if EMBEDDING_DIMENSION != 3072:
                    vals = _l2_normalize([float(x) for x in vals])
                embeddings_out.append(vals)  # type: ignore

            if len(embeddings_out) != len(texts):
                raise RuntimeError("Google Batch Embedding: response count mismatch")

            return embeddings_out
        except Exception as e:
            last_err = e
            sleep_s = EMBED_RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            log_warning(f"Google batch embedding attempt {attempt} failed: {e}. Retrying in {sleep_s:.2f}s...", "pinecone_service", {"attempt": attempt, "error": str(e), "sleep_time": sleep_s})
            time.sleep(sleep_s)

    log_error(f"Failed Google batch embedding after {EMBED_MAX_RETRIES} attempts: {last_err}", "pinecone_service", {"max_retries": EMBED_MAX_RETRIES, "error": str(last_err)})
    raise last_err  # type: ignore

def chunk_transcript(transcript_data: Dict) -> List[Dict]:
    """
    Break transcript into meaningful chunks with metadata
    
    Args:
        transcript_data: The complete transcript data from Deepgram
        
    Returns:
        List of chunks with text and metadata
    """
    chunks = []
    
    # Extract results from transcript if present
    if not transcript_data or "results" not in transcript_data:
        return chunks
    
    results = transcript_data.get("results", {})
    utterances = results.get("utterances", [])
    channels = results.get("channels", [])
    paragraphs = results.get("paragraphs", {}).get("paragraphs", [])
    
    # If we have diarized utterances, use them as the primary chunk boundaries
    if utterances:
        for utterance in utterances:
            chunks.append({
                "text": utterance.get("transcript", ""),
                "start_time": utterance.get("start", 0),
                "end_time": utterance.get("end", 0),
                "speaker": utterance.get("speaker", 0),
                "confidence": utterance.get("confidence", 0)
            })
    # If we have paragraphs, use them
    elif paragraphs:
        for paragraph in paragraphs:
            chunks.append({
                "text": paragraph.get("text", ""),
                "start_time": paragraph.get("start", 0),
                "end_time": paragraph.get("end", 0),
                "confidence": paragraph.get("confidence", 0)
            })
    # If we have channel data, use that
    elif channels and len(channels) > 0 and "alternatives" in channels[0]:
        # Get the best alternative from the first channel
        alternatives = channels[0].get("alternatives", [])
        if alternatives and len(alternatives) > 0:
            words = alternatives[0].get("words", [])
            
            # Group words into chunks of roughly 50-100 words
            current_chunk = []
            current_start = None
            current_end = None
            
            for word in words:
                if current_start is None:
                    current_start = word.get("start", 0)
                
                current_chunk.append(word.get("word", ""))
                current_end = word.get("end", 0)
                
                # If chunk is long enough or there's a meaningful pause, create a new chunk
                if len(current_chunk) >= 50 or (len(current_chunk) > 10 and word.get("punctuated_word", "").endswith((".", "!", "?"))):
                    chunks.append({
                        "text": " ".join(current_chunk),
                        "start_time": current_start,
                        "end_time": current_end,
                        "confidence": sum(word.get("confidence", 0) for word in words) / len(words) if words else 0
                    })
                    current_chunk = []
                    current_start = None
            
            # Add any remaining words as the final chunk
            if current_chunk:
                chunks.append({
                    "text": " ".join(current_chunk),
                    "start_time": current_start,
                    "end_time": current_end,
                    "confidence": sum(word.get("confidence", 0) for word in words) / len(words) if words else 0
                })
    
    return chunks

async def index_transcript(transcript_data: Dict, file_url: str, file_name: str, is_permanent_url: bool = False) -> bool:
    """
    Index a transcript in Pinecone for search.
    
    Args:
        transcript_data: The transcription data
        file_url: URL to the audio file
        file_name: Name of the audio file
        is_permanent_url: Whether the URL is permanent (Supabase) or temporary (tmpfiles)
        
    Returns:
        bool: True if indexing was successful, False otherwise
    """
    global index
    if not index:
        log_warning("Pinecone index not initialized, attempting to initialize...", "pinecone_service")
        if not init_pinecone():
            log_error("Failed to initialize Pinecone", "pinecone_service")
            return False
    
    try:
        log_info(f"Indexing transcript for file: {file_name}", "pinecone_service", {"file_name": file_name, "file_url": file_url, "is_permanent_url": is_permanent_url})
        
        # Build a stable, unique file_id using the (ideally permanent) URL to avoid collisions across same filenames
        file_key_src = (file_url or "")
        # Prefer Supabase URL if available later; we'll recompute after lookup below
        file_id = hashlib.sha1(file_key_src.encode("utf-8")).hexdigest()[:12] if file_key_src else (
            hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:12]
        )
        log_info(f"Initial file_id (pre-supabase-lookup): {file_id}", "pinecone_service", {"file_id": file_id})
        
        # Look up the Supabase URL from the database if not already a permanent URL
        supabase_url = file_url  # Default to the provided URL
        
        if not is_permanent_url:
            from services.database import uploads_collection, podcasts_collection
            
            try:
                # Check uploads collection first
                upload_record = await uploads_collection.find_one({"file_name": {"$regex": file_name}})
                if upload_record and "supabase_url" in upload_record and upload_record["supabase_url"]:
                    supabase_url = upload_record["supabase_url"]
                    log_info(f"Found Supabase URL in uploads collection: {supabase_url}", "pinecone_service", {"supabase_url": supabase_url})
                else:
                    # If not in uploads, try podcasts collection 
                    podcast_record = await podcasts_collection.find_one({"file_name": {"$regex": file_name}})
                    if podcast_record and "supabase_url" in podcast_record and podcast_record["supabase_url"]:
                        supabase_url = podcast_record["supabase_url"]
                        log_info(f"Found Supabase URL in podcasts collection: {supabase_url}", "pinecone_service", {"supabase_url": supabase_url})
                    else:
                        log_warning(f"No Supabase URL found for {file_name}, using original URL", "pinecone_service", {"file_name": file_name})
            except Exception as e:
                log_error(f"Error looking up Supabase URL: {str(e)}", "pinecone_service", {"error": str(e), "file_name": file_name})
        
        # If we resolved a permanent URL, recompute file_id for uniqueness
        if supabase_url:
            file_id = hashlib.sha1(supabase_url.encode("utf-8")).hexdigest()[:12]
            log_info(f"Resolved file_id from Supabase URL: {file_id}", "pinecone_service", {"file_id": file_id})

        # Get the complete transcript text
        complete_text = ""
        if "results" in transcript_data and "channels" in transcript_data["results"]:
            channels = transcript_data["results"]["channels"]
            if channels and len(channels) > 0 and "alternatives" in channels[0]:
                alternatives = channels[0]["alternatives"]
                if alternatives and len(alternatives) > 0:
                    complete_text = alternatives[0].get("transcript", "")
        
        log_info(f"Complete text length: {len(complete_text)}", "pinecone_service", {"text_length": len(complete_text)})
        
        # Chunk the transcript
        chunks = chunk_transcript(transcript_data)
        log_info(f"Created {len(chunks)} chunks", "pinecone_service", {"chunk_count": len(chunks)})
        
        # Prepare items (id, text, metadata) for embedding
        items: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            txt = (chunk.get("text") or "").strip()
            if not txt:
                log_warning(f"Skipping empty text chunk at index {i}", "pinecone_service", {"chunk_index": i})
                continue
            vector_id = f"{file_id}_{i}"
            meta = {
                "file_url": supabase_url,
                "file_id": file_id,
                "file_name": file_name,
                "text": txt,
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "confidence": chunk.get("confidence", 0),
                "chunk_index": i,  # Chunk index
                "total_chunks": len(chunks)  # Total chunks for this file
            }
            if chunk.get("speaker") is not None:
                meta["speaker"] = chunk.get("speaker")
            if not is_permanent_url and "tmpfiles.org" in file_url:
                meta["tmp_url"] = file_url
            items.append({"id": vector_id, "text": txt, "metadata": meta})

        # Create vectors for each chunk (batched for Gemini)
        vectors = []
        if not items:
            log_warning("No non-empty chunks available, skipping Pinecone update", "pinecone_service")
            return False

        if EMBED_PROVIDER == 1:
            # Gemini: token-aware batch embed
            # Precompute token estimates (including overhead)
            token_counts = [_estimate_tokens_for_gemini(it["text"]) + GEMINI_TOKEN_OVERHEAD for it in items]
            i = 0
            while i < len(items):
                cur_batch = []
                cur_tokens = 0
                while i < len(items) and len(cur_batch) < GEMINI_BATCH_SIZE:
                    tkns = token_counts[i]
                    if cur_tokens + tkns > GEMINI_MAX_BATCH_TOKENS and cur_batch:
                        break
                    cur_batch.append(items[i])
                    cur_tokens += tkns
                    i += 1
                texts = [b["text"] for b in cur_batch]
                try:
                    embeddings = _gemini_embed_batch(texts, task_type="RETRIEVAL_DOCUMENT")
                except Exception as e:
                    start_idx = i - len(cur_batch)
                    end_idx = i - 1
                    log_warning(f"Batch embedding failed for items {start_idx}-{end_idx}: {e}. Falling back to single calls for this batch.", "pinecone_service", {"start_idx": start_idx, "end_idx": end_idx, "error": str(e)})
                    embeddings = []
                    for j, b in enumerate(cur_batch):
                        try:
                            emb = get_embedding(b["text"], task_type="RETRIEVAL_DOCUMENT")
                            embeddings.append(emb)
                        except Exception as e2:
                            log_error(f"Single embedding failed for item {start_idx + j}: {e2}. Skipping.", "pinecone_service", {"item_index": start_idx + j, "error": str(e2)})
                            embeddings.append([])  # placeholder

                for b, emb in zip(cur_batch, embeddings):
                    if not emb:
                        continue
                    vector = {"id": b["id"], "values": emb, "metadata": b["metadata"]}
                    vectors.append(vector)
                    log_info(f"Created vector {len(vectors)}/{len(items)}: {b['id']}", "pinecone_service", {"vector_count": len(vectors), "total_items": len(items), "vector_id": b['id']})
        else:
            # Together or other: single calls
            for idx, it in enumerate(items):
                try:
                    emb = get_embedding(it["text"], task_type="RETRIEVAL_DOCUMENT")
                    vector = {"id": it["id"], "values": emb, "metadata": it["metadata"]}
                    vectors.append(vector)
                    log_info(f"Created vector {len(vectors)}/{len(items)}: {it['id']}", "pinecone_service", {"vector_count": len(vectors), "total_items": len(items), "vector_id": it['id']})
                except Exception as e:
                    log_error(f"Error creating vector for item {idx}: {e}", "pinecone_service", {"item_index": idx, "error": str(e)})
        
        # Skip update if no vectors were created
        if not vectors:
            log_warning("No vectors created, skipping Pinecone update", "pinecone_service")
            return False
            
        # Upsert vectors in batches with retries and bounded concurrency
        failed_batches = 0
        total_batches = (len(vectors) + UPSERT_BATCH_SIZE - 1) // UPSERT_BATCH_SIZE
        for i in range(0, len(vectors), UPSERT_BATCH_SIZE):
            batch = vectors[i:i+UPSERT_BATCH_SIZE]
            batch_no = i // UPSERT_BATCH_SIZE + 1
            attempts = 0
            while attempts < UPSERT_MAX_RETRIES:
                attempts += 1
                try:
                    with _upsert_sem:
                        log_info(f"Upserting batch {batch_no}/{total_batches} (size={len(batch)}), attempt {attempts}", "pinecone_service", {"batch_no": batch_no, "total_batches": total_batches, "batch_size": len(batch), "attempt": attempts})
                        response = index.upsert(vectors=batch)
                        log_info(f"Batch {batch_no} upsert response: {response}", "pinecone_service", {"batch_no": batch_no, "response": response})
                    break
                except Exception as e:
                    sleep_s = UPSERT_RETRY_BASE_DELAY * (2 ** (attempts - 1)) + random.uniform(0, 0.3)
                    log_warning(f"Upsert batch {batch_no} failed on attempt {attempts}: {e}. Retrying in {sleep_s:.2f}s...", "pinecone_service", {"batch_no": batch_no, "attempt": attempts, "error": str(e), "sleep_time": sleep_s})
                    time.sleep(sleep_s)
            else:
                log_error(f"Upsert batch {batch_no} failed after {UPSERT_MAX_RETRIES} attempts.", "pinecone_service", {"batch_no": batch_no, "max_retries": UPSERT_MAX_RETRIES})
                failed_batches += 1
            
        if failed_batches == 0:
            log_info(f"Successfully indexed transcript with {len(vectors)} chunks across {total_batches} batches", "pinecone_service", {"vector_count": len(vectors), "total_batches": total_batches})
            return True
        else:
            log_warning(f"Indexed transcript with errors: {failed_batches}/{total_batches} batches failed", "pinecone_service", {"failed_batches": failed_batches, "total_batches": total_batches})
            return False
    except Exception as e:
        log_error(f"Error indexing transcript: {str(e)}", "pinecone_service", {"error": str(e), "file_name": file_name})
        import traceback
        traceback.print_exc()
        return False

async def search_transcripts(query: str, limit: int = None, filter_dict: Dict = None) -> List[Dict]:
    """
    Search for transcripts by vector similarity
    """
    global index
    if not index:
        log_warning("Pinecone index not initialized, attempting to initialize...", "pinecone_service")
        if not init_pinecone():
            log_error("Failed to initialize Pinecone", "pinecone_service")
            return []
    
    try:
        # RAJDEEP_TESTING
        query_embedding = get_embedding(query, task_type="RETRIEVAL_QUERY")
        
        # Execute search
        search_response = index.query(
            vector=query_embedding,
            top_k=limit,
            include_metadata=True,
            filter=filter_dict
        )
        
        # Process results
        results = []
        for match in search_response.get("matches", []):
            # Get metadata
            metadata = match.get("metadata", {})
            
            # Get the best available URL - prioritize file_url (which should be Supabase)
            file_url = metadata.get("file_url", "")
            
            # If file_url contains tmpfiles.org and we have a supabase_url, use that instead
            if "tmpfiles.org" in file_url and metadata.get("supabase_url"):
                file_url = metadata.get("supabase_url")
            
            result = {
                "file_url": file_url,
                "file_name": metadata.get("file_name", ""),
                "text": metadata.get("text", ""),
                "start_time": metadata.get("start_time", 0),
                "end_time": metadata.get("end_time", 0),
                "confidence": metadata.get("confidence", 0),
                "score": match.get("score", 0)
            }
            
            # Add speaker only if it's not None/null
            if "speaker" in metadata and metadata["speaker"] is not None:
                result["speaker"] = metadata["speaker"]
            
            # If we have a temporary URL, include it for reference
            if metadata.get("tmp_url"):
                result["tmp_url"] = metadata.get("tmp_url")
            
            results.append(result)
        
        return results
    except Exception as e:
        log_error(f"Error searching transcripts: {str(e)}", "pinecone_service", {"error": str(e), "query": query})
        import traceback
        traceback.print_exc()
        return []

async def delete_by_file_id(file_id: str) -> Dict[str, Any]:
    """
    Delete all Pinecone vectors that have metadata.file_id == file_id.
    Returns a dict with keys: success (bool), deleted_count (int), error (str|None).
    """
    global index
    if not index:
        if not init_pinecone():
            msg = "Failed to initialize Pinecone"
            return {"success": False, "deleted_count": 0, "error": msg}
    try:
        # Collect matching vector IDs via a filtered query
        dummy_vector = [0.0] * EMBEDDING_DIMENSION
        
        search_response = index.query(
            vector=dummy_vector,
            top_k=10000,
            include_metadata=True,
            filter={"file_id": {"$eq": file_id}}
        )
        
        # Access matches from Pinecone response object
        matches = search_response.matches if hasattr(search_response, 'matches') else []
        
        if not matches:
            return {"success": True, "deleted_count": 0, "error": None}

        vector_ids = [m.id for m in matches if hasattr(m, 'id')]

        batch_size = 1000  # Pinecone's delete limit per request
        deleted_count = 0
        errors = []

        for i in range(0, len(vector_ids), batch_size):
            batch_ids = vector_ids[i:i + batch_size]
            try:
                index.delete(ids=batch_ids)
                deleted_count += len(batch_ids)
            except Exception as de:
                err = f"Error deleting batch {i//batch_size + 1}: {str(de)}"
                errors.append(err)

        if errors:
            return {"success": False, "deleted_count": deleted_count, "error": "; ".join(errors)}

        return {"success": True, "deleted_count": deleted_count, "error": None}
    except Exception as e:
        error_msg = f"Error deleting vectors for file_id {file_id}: {str(e)}"
        return {"success": False, "deleted_count": 0, "error": error_msg}

async def count_vectors_by_file_id(file_id: str) -> Dict[str, Any]:
    """
    Count Pinecone vectors that have metadata.file_id == file_id without deleting anything.
    Returns a dict with keys: success (bool), total_count (int), error (str|None).
    """
    global index
    if not index:
        if not init_pinecone():
            msg = "Failed to initialize Pinecone"
            return {"success": False, "total_count": 0, "error": msg}
    try:
        # Use a filtered query to count matches reliably
        dummy_vector = [0.0] * EMBEDDING_DIMENSION
        try:
            resp = index.query(
                vector=dummy_vector,
                top_k=10000,
                include_metadata=False,
                filter={"file_id": {"$eq": file_id}},
            )
            matches = resp.matches if hasattr(resp, "matches") else []
            total_count = len(matches)
        except Exception:
            total_count = 0
        return {"success": True, "total_count": total_count, "error": None}
    except Exception as e:
        return {"success": False, "total_count": 0, "error": str(e)}

def test_pinecone_connection():
    """Test Pinecone connection and index status"""
    try:
        if not init_pinecone():
            log_error("Failed to initialize Pinecone", "pinecone_service")
            return
            
        # Get index stats
        stats = index.describe_index_stats()
        log_info("Pinecone Index Status", "pinecone_service", {"total_vectors": stats.get('total_vector_count', 0), "index_fullness": stats.get('index_fullness', 0), "dimension": stats.get('dimension', 0)})
        
        # Try a simple query
        if stats.get('total_vector_count', 0) > 0:
            log_info("Testing simple query...", "pinecone_service")
            results = index.query(
                vector=[0.0] * EMBEDDING_DIMENSION,  # Zero vector
                top_k=1,
                include_metadata=True
            )
            if results and results.get('matches'):
                log_info("Query successful!", "pinecone_service", {"match_count": len(results['matches']), "sample_metadata": results['matches'][0]['metadata']})
            else:
                log_warning("Query returned no results", "pinecone_service")
    except Exception as e:
        log_error(f"Error testing Pinecone: {str(e)}", "pinecone_service", {"error": str(e)})
        import traceback
        traceback.print_exc()

# Initialize on module import
init_pinecone() 