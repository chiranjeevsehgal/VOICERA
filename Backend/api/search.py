from utils.error_email import send_error_alert_email
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from typing import Optional, List, Dict, Tuple
from services.pinecone_service import test_pinecone_connection
from services.enhanced_search import EnhancedSearch, TechnicalTermsScorer
from services.auth import get_current_user
from services.transcript_service import extract_transcript
from pydantic import BaseModel
import os
import json
from services.gemini_text_client import generate_text, GeminiAPIError
from services.gemini_key_manager import gemini_key_manager
import re
import logging
import asyncio
from services.database import podcasts_collection, uploads_collection
from utils.analytics import track_search_term, track_user_activity
from utils.logging import log_error, log_info, log_warning

router = APIRouter()

# Initialize EnhancedSearch
enhanced_search = EnhancedSearch()

# Initialize logger
logger = logging.getLogger(__name__)

# Configure max workers for parallel processing
MAX_PARALLEL_VALIDATIONS = 5  # Adjust based on your API rate limits and system capacity

class LLMConfig_Search:
    def __init__(self):
        self.api_key = None
        self.model_name = os.getenv("GEMINI_MODEL")
        self.temperature = 0.0  # 0 for deterministic expansion
        self.max_tokens = None
        self.top_p = 1.0
        self.top_k = 1
        
        # System prompt for generating answers from transcripts
        self.answer_generation_prompt = """You are an AI assistant analyzing audio transcripts.
        Your task is to answer a user's question based ONLY on the provided transcript content.
        
        Guidelines:
        1. Only answer based on information found in the transcript.
        2. If the transcript doesn't contain the information needed to answer the question, clearly state:
           "The transcript does not contain information about [specific topic from the question]."
        3. Be concise but thorough in your answers.
        4. Include relevant quotes or timestamps if available in the transcript.
        5. DO NOT make up or infer information that is not explicitly stated in the transcript.
        6. DO NOT use your general knowledge - rely EXCLUSIVELY on the provided transcript.
        
        Here is the full transcript content:
        -----------------------------
        {transcript}
        -----------------------------
        
        User question: {query}
        
        Your answer should directly respond to the question using ONLY information from the transcript.
        If the answer cannot be found in the transcript, clearly state that the information is not available."""
        
        # Initialize LLM if API key is available
        # Removed API key initialization


def parse_timestamp_range(query: str) -> tuple:
    """
    Parse timestamp ranges from queries like "policy 30-32"
    
    Args:
        query: The search query potentially containing timestamp range
        
    Returns:
        (cleaned_query, start_time, end_time) tuple
    """
    # Look for patterns like "text 30-32" or "text 1:30-2:45"
    time_range_pattern = r'(\d+:?\d*)-(\d+:?\d*)'
    match = re.search(time_range_pattern, query)
    
    if match:
        # Clean the query by removing the time range
        cleaned_query = re.sub(time_range_pattern, '', query).strip()
        
        # Parse start and end times
        start_str, end_str = match.groups()
        
        # Convert time strings to seconds
        start_time = parse_time_to_seconds(start_str)
        end_time = parse_time_to_seconds(end_str)
        
        return cleaned_query, start_time, end_time
    
    # No timestamp range found
    return query, None, None

def parse_time_to_seconds(time_str: str) -> float:
    """
    Convert time string (e.g., "30" or "1:30") to seconds
    
    Args:
        time_str: String representation of time
        
    Returns:
        Time in seconds
    """
    if ':' in time_str:
        # Format is minutes:seconds
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes, seconds = parts
            return float(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    
    # Format is just seconds
    return float(time_str)

async def validate_result_content(result: Dict, query: str, config: LLMConfig_Search) -> Tuple[bool, str]:
    """
    Use LLM to validate if the result's content actually contains information relevant to the query.
    Returns (is_relevant, explanation)
    """
    try:
        if not gemini_key_manager.has_keys():
            return True, "No LLM validation available"
        
        # Get the complete transcript using extract_transcript
        file_name = result.get('file_name')
        if not file_name:
            return False, "No file name provided"
            
        try:
            # Get transcript using the extract service
            full_transcript = await extract_transcript(file_name)
            if not full_transcript:
                return False, f"Could not extract transcript for: {file_name}"
                
            # Get the segment's time range for context
            start_time = result.get('start_time')
            end_time = result.get('end_time')
            time_context = f" (focusing on the segment from {format_seconds_to_time(start_time)} to {format_seconds_to_time(end_time)})" if start_time is not None and end_time is not None else ""
            
            # Create a more structured validation prompt
            validation_prompt = """You are a content validation system. Your task is to determine if a transcript contains relevant information to answer a specific query.

Analyze the following transcript and determine if it contains information relevant to the query.
Pay special attention to the segment timing provided, but consider the entire context.

Query: {query}

Full Transcript:
{transcript}

Segment Timing:{time_context}

Instructions:
1. Analyze if this transcript contains information that would help answer the query
2. Consider the entire transcript but focus on the specified time segment
3. Return your response in this exact JSON format:
{{
    "is_relevant": true/false,
    "explanation": "your explanation here",
    "found_in_segment": true/false,
    "relevant_context": "brief quote or summary of the relevant information"
}}

Rules for determining relevance:
- The transcript must contain specific information related to the query
- Just containing similar keywords is not enough
- The information should contribute to answering the query
- If the transcript is completely off-topic, mark as not relevant
- If unsure, lean towards marking as not relevant

Return ONLY the JSON object, no other text or formatting.""".format(
                query=query,
                transcript=full_transcript,
                time_context=time_context
            )
            
            # Get validation from LLM via REST client
            response_text = generate_text(
                model_name=config.model_name,
                messages=[validation_prompt],
                system_prompt=None,
                temperature=0.1,
                max_output_tokens=1024,
                top_p=0.95,
                top_k=40,
            ).strip()
            
            # Clean up the response text to ensure it's valid JSON
            # Remove any markdown formatting or extra text
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].strip()
                
            # Remove any leading/trailing whitespace or quotes
            response_text = response_text.strip('"\'')
            
            try:
                validation_result = json.loads(response_text)
                
                # Ensure the response has the required fields
                if not isinstance(validation_result, dict):
                    logger.error(f"Invalid validation result format: {validation_result}")
                    return True, "Invalid validation result format"
                    
                is_relevant = validation_result.get("is_relevant", False)
                explanation = validation_result.get("explanation", "No explanation provided")
                found_in_segment = validation_result.get("found_in_segment", False)
                relevant_context = validation_result.get("relevant_context", "")
                
                # Combine explanation with context
                full_explanation = f"{explanation}\n\nRelevant content: {relevant_context}"
                if found_in_segment:
                    full_explanation += "\n(Found in the specified time segment)"
                else:
                    full_explanation += "\n(Found in other parts of the transcript)"
                
                # Log the successful validation
                logger.info(f"Content validation - Relevant: {is_relevant}, Found in segment: {found_in_segment}")
                
                # Only consider it relevant if the information is found in or near the specified segment
                final_is_relevant = is_relevant and found_in_segment
                
                return final_is_relevant, full_explanation
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM validation response: {response_text}")
                logger.error(f"JSON parse error: {str(e)}")
                
                # Fallback: Try to extract meaning from non-JSON response
                response_lower = response_text.lower()
                
                # Look for clear indicators in the text
                if any(phrase in response_lower for phrase in ['not relevant', 'irrelevant', 'unrelated']):
                    return False, "Content appears not relevant (parsed from non-JSON response)"
                elif any(phrase in response_lower for phrase in ['is relevant', 'contains relevant', 'related to']):
                    return True, "Content appears relevant (parsed from non-JSON response)"
                else:
                    return True, "Unable to parse validation response, defaulting to relevant"
                    
        except Exception as e:
            logger.error(f"Error extracting transcript: {str(e)}")
            return False, f"Error extracting transcript: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error in content validation: {str(e)}")
        return False, f"Validation error: {str(e)}"

async def validate_results_batch(results: List[Dict], query: str, config: LLMConfig_Search) -> List[Dict]:
    """
    Validate a batch of results in parallel using ThreadPoolExecutor.
    
    Args:
        results: List of search results to validate
        query: Original search query
        config: LLM configuration
        
    Returns:
        List of validated results
    """
    if not results:
        return []
        
    validation_stats = {
        "total_validated": 0,
        "relevant_count": 0,
        "irrelevant_count": 0
    }
    
    async def validate_single_result(result: Dict) -> Tuple[Dict, bool]:
        """Validate a single result and return tuple of (result, is_relevant)"""
        is_relevant, explanation = await validate_result_content(result, query, config)
        if is_relevant:
            result["content_validation"] = {
                "is_relevant": True,
                "explanation": explanation
            }
            return result, True
        return result, False
    
    # Create tasks for all results
    tasks = [validate_single_result(result) for result in results]
    
    # Process tasks in parallel with semaphore to limit concurrency
    semaphore = asyncio.Semaphore(MAX_PARALLEL_VALIDATIONS)
    
    async def bounded_validate(task):
        async with semaphore:
            return await task
    
    # Execute all tasks with bounded concurrency
    validated_results = []
    validation_tasks = [bounded_validate(task) for task in tasks]
    
    for result, is_relevant in await asyncio.gather(*validation_tasks):
        validation_stats["total_validated"] += 1
        if is_relevant:
            validation_stats["relevant_count"] += 1
            validated_results.append(result)
        else:
            validation_stats["irrelevant_count"] += 1
            
    logger.info(f"Batch validation complete: {validation_stats}")
    return validated_results, validation_stats

@router.get(
    "/search",
    summary="Search audio transcripts",
    description="Search through audio transcripts using enhanced semantic search"
)
async def search(
    query: str = Query(..., description="Search query"),
    limit: Optional[int] = Query(5, description="Maximum number of results to return"),
    min_confidence: Optional[float] = Query(0.7, description="Minimum confidence threshold (0-1)"),
    min_relevance: Optional[float] = Query(0.5, description="Minimum relevance (combined score) threshold (0-1)"),
    speaker: Optional[int] = Query(None, description="Filter by speaker ID"),
    validate_content: Optional[bool] = Query(False, description="Use LLM to validate result content relevance"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for audio based on transcript content.
    
    This endpoint uses semantic search to find audio files and specific segments
    where the content matches the search query. It can filter results by confidence
    level and speaker, and also supports searching for specific time ranges.
    
    Examples:
    - /search?query=policy discussion
    - /search?query=policy 30-32 (search for "policy" between 30-32 seconds)
    - /search?query=AI&speaker=2 (search for "AI" spoken by speaker 2)
    """
    try:
        # Initialize LLM config
        config = LLMConfig_Search()
        
        # Log search request
        logger.info(f"Search request - Query: {query}, Limit: {limit}")
        
        # Store original query for technical term scoring
        original_query = query
        
        # Natural-language processing disabled/removed
                
        # Check if the query contains a timestamp range
        cleaned_query, start_time, end_time = parse_timestamp_range(query)
        
        # Prepare filter dictionary
        filter_dict = {}
        
        if min_confidence:
            filter_dict["confidence"] = {"$gte": min_confidence}
            
        if speaker is not None:
            filter_dict["speaker"] = speaker
            
        # Add time range filter if specified
        if start_time is not None and end_time is not None:
            filter_dict["$and"] = [
                {"start_time": {"$lte": end_time}},
                {"end_time": {"$gte": start_time}}
            ]
        
        # Log filter configuration
        logger.info(f"Search filters: {filter_dict}")
        
        # Single-query search flow
        all_results = []
        seen_ids = set()
        pre_filter_count = 0

        try:
            query_results = await enhanced_search.hybrid_search(
                query=cleaned_query,
                limit=limit * 2,
                filter_dict=filter_dict,
                original_query=original_query,
            )

            for result in query_results:
                result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
                if result_id not in seen_ids:
                    seen_ids.add(result_id)
                    result["matched_query"] = cleaned_query
                    result["original_query"] = original_query
                    result["has_exact_match"] = result.get("keyword_score", 0) > 0.5
                    all_results.append(result)
        except Exception as e:
            logger.error(f"Error searching with query '{cleaned_query}': {str(e)}")
        
        # Apply relevance threshold to combined scores before any expensive validation/reranking
        if all_results:
            pre_filter_count = len(all_results)
            all_results = [r for r in all_results if r.get("combined_score", 0) >= (min_relevance or 0.0)]
            logger.info(f"Applied min_relevance={min_relevance}: kept {len(all_results)} of {pre_filter_count} candidates")

        if not all_results:
            return {
                "query": original_query,
                "total": 0,
                "results": [],
                "message": "No results met the relevance threshold",
                "search_stats": {
                    "total_candidates": pre_filter_count,
                    "unique_results": len(seen_ids),
                    "content_validation_applied": validate_content,
                    "min_relevance": min_relevance,
                    "min_confidence": min_confidence,
                    "candidates_post_relevance": 0
                }
            }

        # After getting initial results but before final reranking, validate content if enabled
        if validate_content and gemini_key_manager.has_keys():
            logger.info("Validating result content relevance in parallel...")
            
            # Process results in parallel batches
            validated_results, validation_stats = await validate_results_batch(
                results=all_results,
                query=original_query,
                config=config
            )
            
            # Update results list with only validated results
            all_results = validated_results
            
            logger.info(f"Content validation complete: {validation_stats}")
            
            # If no results remain after validation, return empty with explanation
            if not all_results:
                return {
                    "query": original_query,
                    "total": 0,
                    "results": [],
                    "message": "No results contained relevant information for the query after validation",
                    "validation_stats": validation_stats
                }
        
        # Sort results by combined score and take top N
        all_results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        results = all_results[:limit]
        
        # Format timestamps in human-readable format
        for result in results:
            if "start_time" in result:
                result["start_time_formatted"] = format_seconds_to_time(result["start_time"])
            if "end_time" in result:
                result["end_time_formatted"] = format_seconds_to_time(result["end_time"])
        
        # Process the results with keyword scoring, technical term recognition
        processed_results = []
        tech_scorer = TechnicalTermsScorer()
        
        for result in results:
            # Always check for embedded_audio_url from podcasts collection
            file_name = result.get("file_name", "")
            if file_name:
                try:
                    # Check podcasts collection for embedded_audio_url using multiple search strategies
                    base_name = file_name.replace('.mp3', '').replace('.wav', '').replace('.m4a', '')
                    
                    # Try multiple query patterns to find the podcast
                    podcast = None
                    
                    # First try exact file_name match
                    podcast = await podcasts_collection.find_one({"file_name": {"$regex": file_name, "$options": "i"}})
                    
                    # If not found, try matching against title field
                    if not podcast:
                        # Create a flexible pattern from the base filename
                        title_pattern = base_name.replace('_', '.*').replace('-', '.*')
                        podcast = await podcasts_collection.find_one({"title": {"$regex": title_pattern, "$options": "i"}})
                    
                    # If still not found, try partial matches on raw_audio_url or embedded_audio_url
                    if not podcast:
                        podcast = await podcasts_collection.find_one({
                            "$or": [
                                {"raw_audio_url": {"$regex": base_name, "$options": "i"}},
                                {"embedded_audio_url": {"$regex": base_name, "$options": "i"}}
                            ]
                        })
                    
                    if podcast and "embedded_audio_url" in podcast and podcast["embedded_audio_url"]:
                        # Store original URL as tmp_url if it's different
                        original_url = result.get("file_url", "")
                        if original_url != podcast["embedded_audio_url"]:
                            result["tmp_url"] = original_url
                        result["file_url"] = podcast["embedded_audio_url"]
                        logger.info(f"Updated file_url for {file_name} to embedded_audio_url")
                    else:
                        # Fallback to find_permanent_url for tmpfiles.org URLs
                        file_url = result.get("file_url", "")
                        if "tmpfiles.org" in file_url:
                            await find_permanent_url(result)
                except Exception as e:
                    logger.error(f"Error updating file_url for {file_name}: {str(e)}")
                    # Fallback to find_permanent_url for tmpfiles.org URLs
                    file_url = result.get("file_url", "")
                    if "tmpfiles.org" in file_url:
                        await find_permanent_url(result)
            
            # Use existing technical and keyword scores if present; otherwise compute minimal fallback
            technical_score = result.get("technical_score")
            if technical_score is None:
                technical_score = tech_scorer.calculate_technical_score(
                    result.get("text", ""), 
                    result.get("original_query", query)
                )
                # Map to 0..1 consistent with EnhancedSearch
                technical_score = max(0.0, min(1.0, technical_score - 1.0))

            keyword_score = result.get("keyword_score")
            if keyword_score is None:
                # Fallback heuristic if keyword_score unavailable
                keyword_score = 1.0 if result.get("has_exact_match", False) else 0.0
            
            # Format result with additional scores
            processed_result = {
                "text": result.get("text", ""),
                "file_name": result.get("file_name", ""),
                "file_url": result.get("file_url", ""),  # Use the result's file_url which may have been updated
                "start_time": result.get("start_time", 0),
                "end_time": result.get("end_time", 0),
                "confidence": result.get("confidence", 0),
                # Provide both normalized and raw semantic scores when available
                "semantic_score": result.get("semantic_score", result.get("semantic_score_raw", 0)),
                "semantic_score_raw": result.get("semantic_score_raw", None),
                "original_query": original_query,
                "combined_score": result.get("combined_score", 0),
                "keyword_score": keyword_score,
                "technical_score": technical_score
            }
            
            # Add tmp_url if present in the result
            if result.get("tmp_url"):
                processed_result["tmp_url"] = result.get("tmp_url")
            
            processed_results.append(processed_result)
        
        response_data = {
            "query": original_query,
            "cleaned_query": cleaned_query if cleaned_query != original_query else None,
            "time_range": {
                "start": start_time,
                "end": end_time,
                "start_formatted": format_seconds_to_time(start_time) if start_time is not None else None,
                "end_formatted": format_seconds_to_time(end_time) if end_time is not None else None
            } if start_time is not None else None,
            "total": len(results),
            "exact_matches": sum(1 for r in results if r.get("has_exact_match", False)),
            "results": processed_results,
            "search_stats": {
                "total_candidates": pre_filter_count or len(all_results),
                "unique_results": len(seen_ids),
                "content_validation_applied": validate_content,
                "min_relevance": min_relevance,
                "min_confidence": min_confidence,
                "candidates_post_relevance": len(all_results)
            }
        }
        
        # Add validation stats if content validation was performed
        if validate_content and gemini_key_manager.has_keys():
            response_data["validation_stats"] = validation_stats
        
        # Log search completion
        logger.info(f"Search completed - Found {len(results)} results from {len(all_results)} candidates")
        
        # Track search term
        track_search_term(query, user_id=str(current_user.get("_id", "")))
        
        # Track user activity if user is authenticated
        if current_user and "_id" in current_user:
            track_user_activity(
                user_id=str(current_user.get("_id", "")),
                feature="search",
                additional_data={
                    "query": query,
                    "results_count": len(results),
                    "total_candidates": len(all_results)
                }
            )
        
        return response_data
        
    except Exception as e:
        error_msg = f"Error searching transcripts: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

def format_seconds_to_time(seconds: float) -> str:
    """
    Format seconds as HH:MM:SS or MM:SS
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    if seconds is None:
        return None
        
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    else:
        return f"{minutes:02d}:{secs:06.3f}"

class AnswerRequest(BaseModel):
    query: str
    transcript: str

@router.post(
    "/generate-answer",
    summary="Generate answer from transcript and query",
    description="Generate an answer to a user query based on transcript content using LLM"
)
async def generate_answer(
    request: AnswerRequest,
    req: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an answer to a user query based on transcript content.
    
    This endpoint uses an LLM to analyze the transcript content and generate
    a relevant answer to the user's question based solely on the information
    in the transcript.
    
    Example body:
    {
        "query": "Artemis I is described as the first uncrewed test flight of the integrated SLS and Orion system. Based on the transcript, how does this mission serve both engineering and scientific purposes simultaneously?",
        "transcript": "The complete transcript text from the audio file..."
    }
    """
    try:
        config = LLMConfig_Search()
        
        if not gemini_key_manager.has_keys():
            await send_error_alert_email(
            error_message="Gemini API keys not configured",
            error_code="500",
            api_endpoint="/generate-answer"
            )
            raise HTTPException(status_code=500, detail="Gemini API keys not configured")
                
        # Validate input
        if not request.query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        if not request.transcript:
            raise HTTPException(status_code=400, detail="Transcript is required")
            
        # Format the prompt with the transcript and query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.query
        )
        
        # Generate the answer via REST Gemini client
        response_text = generate_text(
            model_name=config.model_name,
            messages=[formatted_prompt],
            system_prompt=None,
            temperature=0.3,
            max_output_tokens=1024,
            top_p=0.95,
            top_k=40,
        )
        
        # Return the generated answer
        return {
            "query": request.query,
            "answer": response_text,
            "model": config.model_name,
        }
        
    except GeminiAPIError as ge:
        # Return aligned Gemini error to client
        raise HTTPException(
            status_code=ge.http_code,
            detail={
                "status": ge.status,
                "message": ge.message or ge.description,
                "solution": ge.solution,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

class SearchAndAnswerRequest(BaseModel):
    search_query: str 
    result_id: str
    transcript: str
    # Optional conversational context from the frontend chat UI
    history: Optional[List[Dict[str, str]]] = None
    context: Optional[str] = None

@router.post(
    "/search-and-answer",
    summary="Search and generate answer in one request",
    description="Generates an answer for a specific search result without requiring separate requests"
)
async def search_and_answer(
    request: SearchAndAnswerRequest,
    req: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an answer for a specific search result without requiring a separate request.
    This helps avoid UI refreshes in the frontend.
    
    Example body:
    {
        "search_query": "How does plants grow in lunar soil?",
        "result_id": "file123_10.5_20.8",
        "transcript": "The transcript text from the result..."
    }
    """
    try:
        # Debug logging
        log_info("Search and answer request received", "search.search_and_answer", {"search_query": request.search_query, "result_id": request.result_id})
        if request.transcript:
            transcript_len = len(request.transcript)
            transcript_words = len(request.transcript.split())
            log_info(f"Processing transcript with {transcript_len} chars, {transcript_words} words", "search.search_and_answer", {"transcript_length": transcript_len, "transcript_words": transcript_words})
        else:
            log_warning("Empty transcript received", "search.search_and_answer")
        
        config = LLMConfig_Search()
        
        if not gemini_key_manager.has_keys():
            await send_error_alert_email(
            error_message="Gemini API keys not configured",
            error_code="500",
            api_endpoint="/search-and-answer"
            )
            log_error("Gemini API keys not configured", "search.search_and_answer")
            raise HTTPException(status_code=500, detail="Gemini API keys not configured")
            
        # Validate the transcript
        if not request.transcript or len(request.transcript.strip()) < 10:
            log_error("Transcript too short or empty", "search.search_and_answer", {"transcript_length": len(request.transcript.strip()) if request.transcript else 0})
            return {
                "result_id": request.result_id,
                "search_query": request.search_query,
                "answer": "Error: The transcript is too short or empty. Cannot generate an answer.",
                "model": config.model_name,
            }
            
        # Log transcript length for debugging
        transcript_word_count = len(request.transcript.split())
        log_info(f"Processing answer for '{request.search_query}' with transcript of {transcript_word_count} words", "search.search_and_answer", {"search_query": request.search_query, "transcript_word_count": transcript_word_count})
        
        # Base prompt with transcript and current query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.search_query
        )

        # Append conversation history and optional context (if provided)
        history_block = ""
        if request.history:
            try:
                # Limit to last 10 messages to control prompt size
                recent = request.history[-10:]
                history_lines = []
                for m in recent:
                    role = (m.get('role') or 'user').strip()
                    content = (m.get('content') or '').strip()
                    if content:
                        history_lines.append(f"{role}: {content}")
                if history_lines:
                    history_block = "\n\nConversation history (for coherence, do not add facts not in transcript):\n" + "\n".join(history_lines)
            except Exception as e:
                log_warning(f"Failed to format history for prompt: {str(e)}", "search.search_and_answer")

        context_block = ""
        if request.context:
            context_block = f"\n\nAdditional context from UI: {request.context}"

        full_prompt = formatted_prompt + history_block + context_block
        
        log_info(f"Sending prompt to LLM (length: {len(full_prompt)} chars)", "search.search_and_answer", {"prompt_length": len(full_prompt)})
        
        # Generate the answer via REST Gemini client
        response_text = generate_text(
            model_name=config.model_name,
            messages=[full_prompt],
            system_prompt=None,
            temperature=0.2,
            max_output_tokens=1024,
            top_p=0.95,
            top_k=40,
        )
        
        log_info(f"LLM response received (length: {len(response_text)} chars)", "search.search_and_answer", {"response_length": len(response_text)})
        
        # Return the generated answer along with identifying information
        return {
            "result_id": request.result_id,
            "search_query": request.search_query,
            "answer": response_text,
            "model": config.model_name,
        }
        
    except GeminiAPIError as ge:
        log_error(
            f"Gemini error generating answer: {ge}",
            "search.search_and_answer",
            {"http_code": ge.http_code, "status": ge.status},
        )
        raise HTTPException(
            status_code=ge.http_code,
            detail={
                "status": ge.status,
                "message": ge.message or ge.description,
                "solution": ge.solution,
            },
        )
    except Exception as e:
        log_error(f"Error generating answer: {str(e)}", "search.search_and_answer", {"error": str(e), "search_query": request.search_query if 'request' in locals() else "unknown"})
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

@router.get(
    "/test-connection",
    summary="Test Pinecone connection",
    description="Test the connection to Pinecone and check index status"
)
async def test_connection():
    """Test the connection to Pinecone and check index status"""
    try:
        test_pinecone_connection()
        return {"status": "completed", "message": "Check the logs for details"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing connection: {str(e)}")

async def find_permanent_url(result: Dict) -> None:
    """
    Find a permanent Supabase URL for a result with a temporary URL.
    Updates the result in place if a permanent URL is found.
    
    Args:
        result: The search result to update
    """
    file_url = result.get("file_url", "")
    file_name = result.get("file_name", "")
    
    if not file_name or "tmpfiles.org" not in file_url:
        return
        
    try:
        # First check podcasts collection for embedded_audio_url
        podcast = await podcasts_collection.find_one({"file_name": {"$regex": file_name}})
        if podcast and "embedded_audio_url" in podcast and podcast["embedded_audio_url"]:
            result["file_url"] = podcast["embedded_audio_url"]
            # Store the temporary URL as tmp_url if not already present
            if not result.get("tmp_url"):
                result["tmp_url"] = file_url
            return
            
        # Try uploads collection
        upload = await uploads_collection.find_one({"file_name": {"$regex": file_name}})
        if upload and "supabase_url" in upload and upload["supabase_url"]:
            result["file_url"] = upload["supabase_url"]
            # Store the temporary URL as tmp_url if not already present
            if not result.get("tmp_url"):
                result["tmp_url"] = file_url
            return
            
        # If we get here, no permanent URL was found
        logger.warning(f"No permanent URL found for file: {file_name}")
    except Exception as e:
        logger.error(f"Error finding permanent URL: {str(e)}") 