from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict
from services.pinecone_service import search_transcripts
import re
import google.generativeai as genai
import os
from pydantic import BaseModel

router = APIRouter()

class LLMConfig_Search:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL")
        self.temperature = 0.0  # 0 for deterministic expansion
        self.max_tokens = None
        self.top_p = 1.0
        self.top_k = 1
        
        # System prompt for query expansion
        self.system_prompt = """You are a query expansion assistant. Your task is to expand search queries 
        to include alternative formats of numbers and words. For example, if the query contains "21", 
        include "twenty one" and "twenty-one". If it contains "twenty one", include "21". 
        Don't change the meaning of the query - just expand it to include alternative formats.
        Return a JSON object with the original query and expanded variations like:
        {"original": "original query", "expanded": ["variation1", "variation2"]}"""
        
        # System prompt for natural language query processing
        self.nl_query_prompt = """You are a natural language query processor for an audio search system.
        Your task is to analyze natural language queries and extract the following in JSON format:
        1. key_terms: Important words or phrases to search for (list of strings)
        2. entities: Named entities like people, places, or dates (list of strings)
        3. temporal_references: Any time references like days, dates, or times (list of strings)
        4. search_intent: The primary information the user is looking for (string)
        5. search_query: A reformulated search query optimized for semantic search (string)
        
        For example, if the query is "which audio file talks about the marketing meeting on Thursday?", return:
        {
          "key_terms": ["marketing meeting", "meeting", "Thursday"],
          "entities": ["marketing"],
          "temporal_references": ["Thursday"],
          "search_intent": "Find audio files discussing a marketing meeting scheduled on Thursday",
          "search_query": "marketing meeting Thursday"
        }
        
        Return the JSON object only, with no additional text."""
        
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
        if self.api_key:
            genai.configure(api_key=self.api_key)

async def expand_query_with_llm(query: str) -> List[str]:
    """
    Use LLM to expand query with alternative formats (e.g., numbers as words)
    """
    config = LLMConfig_Search()
    
    if not config.api_key:
        # If no API key, just return the original query
        return [query]
    
    try:
        # Configuring the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                "max_output_tokens": config.max_tokens,
                "top_p": config.top_p,
                "top_k": config.top_k
            }
        )
        
        # Construct prompt to expand the query
        prompt = f"Expand this search query to include variations of numbers and words: {query}"
        
        response = model.generate_content(
            [config.system_prompt, prompt]
        )
        
        try:
            # Parse the response as JSON
            import json
            result = json.loads(response.text)
            
            # Return the expanded queries
            expanded_queries = result.get("expanded", [])
            if not expanded_queries or not isinstance(expanded_queries, list):
                return [query]  # Fallback to original if no proper expansions
                
            # Add the original query if not already in the list
            if query not in expanded_queries:
                expanded_queries.insert(0, query)
                
            return expanded_queries
            
        except json.JSONDecodeError:
            # If not JSON, just return the original query
            return [query]
            
    except Exception as e:
        print(f"Error in query expansion: {str(e)}")
        return [query]  # Fallback to original query

async def process_natural_language_query(query: str) -> Dict:
    """
    Process natural language queries to extract relevant search terms and context
    """
    config = LLMConfig_Search()
    
    # Common English stopwords to filter out
    stopwords = {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where", "why",
        "how", "all", "any", "both", "each", "few", "more", "most", "other",
        "some", "such", "no", "nor", "not", "only", "own", "same", "so",
        "than", "too", "very", "s", "t", "can", "will", "just", "don", "don't",
        "should", "now", "d", "ll", "m", "o", "re", "ve", "y", "ain", "aren",
        "aren't", "couldn", "couldn't", "didn", "didn't", "doesn", "doesn't",
        "hadn", "hadn't", "hasn", "hasn't", "haven", "haven't", "isn", "isn't",
        "ma", "mightn", "mightn't", "mustn", "mustn't", "needn", "needn't",
        "shan", "shan't", "shouldn", "shouldn't", "wasn", "wasn't", "weren",
        "weren't", "won", "won't", "wouldn", "wouldn't", "what", "which", "who",
        "whom", "this", "that", "these", "those", "am", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "having", "do",
        "does", "did", "doing", "i", "me", "my", "myself", "we", "our", "ours",
        "ourselves", "you", "your", "yours", "yourself", "yourselves", "he",
        "him", "his", "himself", "she", "her", "hers", "herself", "it", "its",
        "itself", "they", "them", "their", "theirs", "themselves",
    }
    
    if not config.api_key:
        # If no API key, return basic structure with original query
        # Filter out stopwords from the key terms
        key_terms = [term.lower() for term in query.lower().split() 
                     if term.lower() not in stopwords and len(term) > 2]
        return {
            "key_terms": key_terms,
            "entities": [],
            "temporal_references": [],
            "search_intent": f"Find information about {query}",
            "search_query": query
        }
    
    try:
        # Configuring the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                "max_output_tokens": config.max_tokens,
                "top_p": config.top_p,
                "top_k": config.top_k
            }
        )
        
        # Get NL query analysis
        response = model.generate_content(
            [config.nl_query_prompt, query]
        )
        
        try:
            # Parse the response as JSON
            import json
            result = json.loads(response.text)
            return result
            
        except json.JSONDecodeError:
            # Fallback to basic analysis if parsing fails
            key_terms = [term.lower() for term in query.lower().split() 
                         if term.lower() not in stopwords and len(term) > 2]
            return {
                "key_terms": key_terms,
                "entities": [],
                "temporal_references": [],
                "search_intent": f"Find information about {query}",
                "search_query": query
            }
            
    except Exception as e:
        print(f"Error in natural language query processing: {str(e)}")
        # Return basic fallback
        key_terms = [term.lower() for term in query.lower().split() 
                     if term.lower() not in stopwords and len(term) > 2]
        return {
            "key_terms": key_terms,
            "entities": [],
            "temporal_references": [],
            "search_intent": f"Find information about {query}",
            "search_query": query
        }

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

async def rerank_results_for_nl_query(results: List[Dict], nl_query_info: Dict) -> List[Dict]:
    """
    Rerank search results based on natural language query analysis
    
    Args:
        results: List of search results
        nl_query_info: Natural language query analysis
        
    Returns:
        Reranked list of results
    """
    if not results or not nl_query_info:
        return results
        
    # Calculate new scores based on NL query intent
    key_terms = [term.lower() for term in nl_query_info.get("key_terms", [])]
    entities = [entity.lower() for entity in nl_query_info.get("entities", [])]
    temporal_references = [ref.lower() for ref in nl_query_info.get("temporal_references", [])]
    
    all_important_terms = key_terms + entities + temporal_references
    
    # No reranking needed if we don't have important terms to match
    if not all_important_terms:
        return results
    
    for result in results:
        # Get the text and calculate a match score
        text = result.get("text", "").lower()
        
        # Base match score from semantic search
        base_score = result.get("score", 0)
        
        # Calculate bonus for each important term that appears in the text
        term_match_bonus = 0
        matched_terms = []
        
        for term in all_important_terms:
            if term in text:
                term_match_bonus += 0.1  # Add 0.1 for each term match
                matched_terms.append(term)
        
        # Calculate time reference bonus if applicable
        time_bonus = 0
        if temporal_references and any(ref in text for ref in temporal_references):
            time_bonus = 0.2  # Add 0.2 if any time reference is found
        
        # Calculate final score
        nl_score = base_score + term_match_bonus + time_bonus
        
        # Store the NL-specific scoring info
        result["nl_score"] = nl_score
        result["matched_terms"] = matched_terms
        result["has_time_match"] = time_bonus > 0
    
    # Sort by the new NL score
    results.sort(key=lambda x: -x.get("nl_score", 0))
    
    return results

@router.get(
    "/search",
    summary="Search audio transcripts",
    description="Search through audio transcripts using semantic search"
)
async def search(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, description="Maximum number of results to return"),
    min_confidence: Optional[float] = Query(0.7, description="Minimum confidence threshold (0-1)"),
    speaker: Optional[int] = Query(None, description="Filter by speaker ID"),
    use_llm_expansion: bool = Query(True, description="Use LLM to expand search query"),
    natural_language: bool = Query(False, description="Process as natural language query")
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
    - /search?query=21&use_llm_expansion=true (will also search for "twenty one", "twenty-one", etc.)
    - /search?query=which audio mentions the meeting on Thursday?&natural_language=true
    """
    try:
        # Process as natural language query if specified
        nl_query_info = None
        original_query = query
        
        if natural_language:
            nl_query_info = await process_natural_language_query(query)
            # Use the optimized search query for further processing
            query = nl_query_info.get("search_query", query)
            
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
            # We want segments that overlap with the specified range
            # This means start_time <= chunk.end_time AND end_time >= chunk.start_time
            filter_dict["$and"] = [
                {"start_time": {"$lte": end_time}},
                {"end_time": {"$gte": start_time}}
            ]
        
        # Use LLM to expand the query if enabled
        expanded_queries = []
        if use_llm_expansion:
            expanded_queries = await expand_query_with_llm(cleaned_query)
            
            # Common English stopwords to filter out
            stopwords = {
                "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
                "at", "by", "for", "with", "about", "against", "between", "into",
                "through", "during", "before", "after", "above", "below", "to", "from",
                "up", "down", "in", "out", "on", "off", "over", "under", "again",
                "further", "then", "once", "here", "there", "when", "where", "why",
                "how", "all", "any", "both", "each", "few", "more", "most", "other",
                "some", "such", "no", "nor", "not", "only", "own", "same", "so"
            }
            
            # If we have natural language processing results, add key terms and entities to expanded queries
            if nl_query_info:
                for term in nl_query_info.get("key_terms", []):
                    if (term not in expanded_queries and len(term) > 2 
                        and term.lower() not in stopwords):
                        expanded_queries.append(term)
                        
                for entity in nl_query_info.get("entities", []):
                    if (entity not in expanded_queries and len(entity) > 2 
                        and entity.lower() not in stopwords):
                        expanded_queries.append(entity)
                        
                for temporal in nl_query_info.get("temporal_references", []):
                    if (temporal not in expanded_queries and len(temporal) > 2 
                        and temporal.lower() not in stopwords):
                        expanded_queries.append(temporal)
        else:
            expanded_queries = [cleaned_query]
            
        # Search for each expanded query and merge results
        all_results = []
        seen_ids = set()
        
        for expanded_query in expanded_queries:
            # Search for transcripts with this expanded query
            query_results = await search_transcripts(
                query=expanded_query,
                limit=limit * 2,  # Get more results to account for duplicates
                filter_dict=filter_dict
            )
            
            # Add only unique results
            for result in query_results:
                # Create a unique identifier for the result
                result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
                
                if result_id not in seen_ids:
                    seen_ids.add(result_id)
                    # Track which expanded query matched this result
                    result["matched_query"] = expanded_query
                    all_results.append(result)
        
        # Sort results by exact match presence first, then by score
        all_results.sort(key=lambda x: (not x.get('has_exact_match', False), -x.get('score', 0)))
        
        # If using natural language processing, rerank based on query intent
        if natural_language and nl_query_info:
            all_results = await rerank_results_for_nl_query(all_results, nl_query_info)
        
        # Limit to requested number
        results = all_results[:limit]
        
        # Format timestamps in human-readable format
        for result in results:
            if "start_time" in result:
                result["start_time_formatted"] = format_seconds_to_time(result["start_time"])
            if "end_time" in result:
                result["end_time_formatted"] = format_seconds_to_time(result["end_time"])
        
        response_data = {
            "query": original_query,
            "cleaned_query": cleaned_query if cleaned_query != original_query else None,
            "expanded_queries": expanded_queries if use_llm_expansion else None,
            "time_range": {
                "start": start_time,
                "end": end_time,
                "start_formatted": format_seconds_to_time(start_time) if start_time is not None else None,
                "end_formatted": format_seconds_to_time(end_time) if end_time is not None else None
            } if start_time is not None else None,
            "total": len(results),
            "exact_matches": sum(1 for r in results if r.get("has_exact_match", False)),
            "results": results
        }
        
        # Add natural language processing info if available
        if nl_query_info:
            response_data["natural_language_analysis"] = nl_query_info
        
        return response_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching transcripts: {str(e)}")

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
async def generate_answer(request: AnswerRequest):
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
        
        if not config.api_key:
            raise HTTPException(status_code=500, detail="LLM API key not configured")
        
        # Validate input
        if not request.query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        if not request.transcript:
            raise HTTPException(status_code=400, detail="Transcript is required")
            
        # Configure the LLM
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.3,  # Slightly higher temperature for more natural answers
                "max_output_tokens": 1024,  # Allow longer answers
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Format the prompt with the transcript and query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.query
        )
        
        # Generate the answer
        response = model.generate_content(formatted_prompt)
        
        # Return the generated answer
        return {
            "query": request.query,
            "answer": response.text,
            "model": config.model_name,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

class SearchAndAnswerRequest(BaseModel):
    search_query: str 
    result_id: str
    transcript: str

@router.post(
    "/search-and-answer",
    summary="Search and generate answer in one request",
    description="Generates an answer for a specific search result without requiring separate requests"
)
async def search_and_answer(request: SearchAndAnswerRequest):
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
        print("=== SEARCH AND ANSWER REQUEST ===")
        print(f"Search Query: {request.search_query}")
        print(f"Result ID: {request.result_id}")
        if request.transcript:
            transcript_len = len(request.transcript)
            transcript_words = len(request.transcript.split())
            print(f"Transcript length: {transcript_len} chars, {transcript_words} words")
            print(f"Transcript start: {request.transcript[:100]}...")
            print(f"Transcript end: ...{request.transcript[-100:]}")
        else:
            print("Warning: Empty transcript received")
        
        config = LLMConfig_Search()
        
        if not config.api_key:
            print("Error: LLM API key not configured")
            raise HTTPException(status_code=500, detail="LLM API key not configured")
            
        # Validate the transcript
        if not request.transcript or len(request.transcript.strip()) < 10:
            print("Error: Transcript too short or empty")
            return {
                "result_id": request.result_id,
                "search_query": request.search_query,
                "answer": "Error: The transcript is too short or empty. Cannot generate an answer.",
                "model": config.model_name,
            }
            
        # Log transcript length for debugging
        transcript_word_count = len(request.transcript.split())
        print(f"Processing answer for '{request.search_query}' with transcript of {transcript_word_count} words")
        
        # Configure the LLM
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.2,  # Lower temperature for more factual answers
                "max_output_tokens": 1024,  # Allow longer answers
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Format the prompt with the transcript and query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.search_query
        )
        
        print(f"Sending prompt to LLM (length: {len(formatted_prompt)} chars)")
        
        # Generate the answer
        response = model.generate_content(formatted_prompt)
        
        print(f"LLM response received (length: {len(response.text)} chars)")
        print(f"Response start: {response.text[:100]}...")
        
        # Return the generated answer along with identifying information
        return {
            "result_id": request.result_id,
            "search_query": request.search_query,
            "answer": response.text,
            "model": config.model_name,
        }
        
    except Exception as e:
        print(f"Error generating answer: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}") 