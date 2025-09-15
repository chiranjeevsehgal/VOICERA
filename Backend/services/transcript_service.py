import os
import json
import logging
from typing import Optional
from services.pinecone_service import index, get_embedding
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
        if index:
            dummy_vector = [0] * 768
            results = index.query(vector=dummy_vector, top_k=1000, include_metadata=True, filter={'file_name': file_name})
            if results and results.get('matches'):
                segments = sorted(results['matches'], key=lambda x: float(x['metadata'].get('start_time', 0)))
                full_transcript = ' '.join((segment['metadata'].get('text', '') for segment in segments if 'text' in segment['metadata']))
                if full_transcript:
                    return full_transcript
        logger.warning(f'Could not find transcript for file: {file_name}')
        return None
    except Exception as e:
        logger.error(f'Error extracting transcript: {str(e)}')
        return None