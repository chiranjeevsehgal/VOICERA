import os
import json
import logging
from typing import Optional
from services.pinecone_service import index, get_embedding  # Add import for get_embedding

logger = logging.getLogger(__name__)

async def extract_transcript(file_name: str) -> Optional[str]:
    """
    Extract the full transcript for a given audio file.
    
    Args:
        file_name: The name of the audio file
        
    Returns:
        The full transcript text if found, None otherwise
    """
    try:
        # First try to get from the transcripts collection in the database
        # This would be the preferred method if you have a database
        # transcript = await db.transcripts.find_one({"file_name": file_name})
        # if transcript:
        #     return transcript.get("text")
        
        # If not in database, try to get from the index metadata
        if index:
            # Create a dummy query vector with correct dimension
            dummy_vector = [0] * 768  # Changed from 1536 to 768 to match index dimension
            
            # Query the index for vectors from this file
            results = index.query(
                vector=dummy_vector,
                top_k=1000,  # Get all segments from this file
                include_metadata=True,
                filter={"file_name": file_name}
            )
            
            if results and results.get("matches"):
                # Sort segments by start time
                segments = sorted(
                    results["matches"],
                    key=lambda x: float(x["metadata"].get("start_time", 0))
                )
                
                # Combine all segments
                full_transcript = " ".join(
                    segment["metadata"].get("text", "")
                    for segment in segments
                    if "text" in segment["metadata"]
                )
                
                if full_transcript:
                    return full_transcript
                    
        logger.warning(f"Could not find transcript for file: {file_name}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting transcript: {str(e)}")
        return None