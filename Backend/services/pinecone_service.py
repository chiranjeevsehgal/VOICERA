import os
import json
import time
from typing import List, Dict, Any
from together import Together
from pinecone import Pinecone, ServerlessSpec, CloudProvider, AwsRegion
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "gcp-starter")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "voicera-audio-search")
EMBEDDING_MODEL = os.getenv("TOGETHER_EMBEDDING_MODEL", "togethercomputer/m2-bert-80M-32k-retrieval")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))  # 768 for m2-bert-80M-32k-retrieval

# Initialize the Together AI client
together_client = Together(api_key=TOGETHER_API_KEY)

# Initialize Pinecone client
pc = None
index = None

def init_pinecone():
    """Initialize the Pinecone client and create index if it doesn't exist"""
    global pc, index
    try:
        if not PINECONE_API_KEY:
            print("WARNING: PINECONE_API_KEY is not set. Vector search will not work.")
            return False

        print(f"Initializing Pinecone with API key: {PINECONE_API_KEY[:5]}...")
        
        # Initialize the Pinecone client
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # List all indexes and print them
        existing_indexes = pc.list_indexes()
        print(f"Found existing indexes: {[index.name for index in existing_indexes]}")
        
        # Check if our index already exists
        if PINECONE_INDEX_NAME not in [index.name for index in existing_indexes]:
            print(f"Creating new index: {PINECONE_INDEX_NAME}")
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
            print(f"Created new Pinecone index: {PINECONE_INDEX_NAME}")
            # Wait for index initialization
            time.sleep(10)
        
        # Connect to the index
        index_info = pc.describe_index(PINECONE_INDEX_NAME)
        print(f"Index info: {index_info}")
        index = pc.Index(host=index_info.host)
        
        # Get index stats
        try:
            stats = index.describe_index_stats()
            print(f"Index stats: {stats}")
            print(f"Total vectors in index: {stats.get('total_vector_count', 0)}")
        except Exception as e:
            print(f"Error getting index stats: {str(e)}")
        
        print(f"Successfully connected to Pinecone index: {PINECONE_INDEX_NAME}")
        return True
    except Exception as e:
        print(f"Error initializing Pinecone: {str(e)}")
        return False

def get_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector for a text string using Together AI's API
    """
    if not TOGETHER_API_KEY:
        print("ERROR: TOGETHER_API_KEY is not set")
        raise ValueError("TOGETHER_API_KEY is not set")
    
    try:
        print(f"\nGenerating embedding for text: {text[:100]}...")
        print(f"Using model: {EMBEDDING_MODEL}")
        
        response = together_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        
        # Extract the embedding vector from the response
        embedding = response.data[0].embedding
        print(f"Generated embedding of dimension: {len(embedding)}")
        
        return embedding
    except Exception as e:
        print(f"Error generating embedding: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

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
        print("Pinecone index not initialized, attempting to initialize...")
        if not init_pinecone():
            print("Failed to initialize Pinecone")
            return False
    
    try:
        print(f"\nIndexing transcript for file: {file_name}")
        print(f"Original File URL: {file_url}")
        print(f"Is permanent URL: {is_permanent_url}")
        
        # Extract file_id from file_name
        file_id = file_name.split("_")[-1].split(".")[0] if "_" in file_name else file_name.split(".")[0]
        print(f"Extracted file_id: {file_id}")
        
        # Look up the Supabase URL from the database if not already a permanent URL
        supabase_url = file_url  # Default to the provided URL
        
        if not is_permanent_url:
            from services.database import uploads_collection, podcasts_collection
            import asyncio
            
            try:
                # Check uploads collection first
                upload_record = await uploads_collection.find_one({"file_name": {"$regex": file_name}})
                if upload_record and "supabase_url" in upload_record and upload_record["supabase_url"]:
                    supabase_url = upload_record["supabase_url"]
                    print(f"Found Supabase URL in uploads collection: {supabase_url}")
                else:
                    # If not in uploads, try podcasts collection 
                    podcast_record = await podcasts_collection.find_one({"file_name": {"$regex": file_name}})
                    if podcast_record and "supabase_url" in podcast_record and podcast_record["supabase_url"]:
                        supabase_url = podcast_record["supabase_url"]
                        print(f"Found Supabase URL in podcasts collection: {supabase_url}")
                    else:
                        print(f"No Supabase URL found for {file_name}, using original URL")
            except Exception as e:
                print(f"Error looking up Supabase URL: {str(e)}")
        
        # Get the complete transcript text
        complete_text = ""
        if "results" in transcript_data and "channels" in transcript_data["results"]:
            channels = transcript_data["results"]["channels"]
            if channels and len(channels) > 0 and "alternatives" in channels[0]:
                alternatives = channels[0]["alternatives"]
                if alternatives and len(alternatives) > 0:
                    complete_text = alternatives[0].get("transcript", "")
        
        print(f"Complete text length: {len(complete_text)}")
        
        # Chunk the transcript
        chunks = chunk_transcript(transcript_data)
        print(f"Created {len(chunks)} chunks")
        
        # Create vectors for each chunk
        vectors = []
        for i, chunk in enumerate(chunks):
            # Generate a unique ID for each chunk
            vector_id = f"{file_id}_{i}"
            
            try:
                # Get embedding for the chunk text
                embedding = get_embedding(chunk["text"])
                
                # Prepare metadata
                metadata = {
                    "file_url": supabase_url,  # Use Supabase URL if available
                    "text": chunk["text"],
                    "start_time": chunk["start_time"],
                    "end_time": chunk["end_time"],
                    "confidence": chunk.get("confidence", 0)
                }
                
                # Add temporary URL only if we're using a temporary URL
                if not is_permanent_url and "tmpfiles.org" in file_url:
                    metadata["tmp_url"] = file_url  # Store tmpfiles URL as backup
                
                # Add file_name
                metadata["file_name"] = file_name
                
                # Add speaker only if it's not None/null
                if chunk.get("speaker") is not None:
                    metadata["speaker"] = chunk.get("speaker")
                
                # Create vector object
                vector = {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                }
                
                vectors.append(vector)
                print(f"Created vector {i+1}/{len(chunks)}: {vector_id}")
            except Exception as e:
                print(f"Error creating vector for chunk {i}: {str(e)}")
                # Continue with the next chunk instead of failing completely
                continue
        
        # Skip update if no vectors were created
        if not vectors:
            print("No vectors created, skipping Pinecone update")
            return False
            
        # Upsert vectors in batches to avoid timeouts
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i+batch_size]
            print(f"Upserting batch {i//batch_size + 1}/{(len(vectors) + batch_size - 1) // batch_size}: {len(batch)} vectors")
            response = index.upsert(vectors=batch)
            print(f"Batch upsert response: {response}")
            
        print(f"Successfully indexed transcript with {len(vectors)} chunks")
        return True
    except Exception as e:
        print(f"Error indexing transcript: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def search_transcripts(query: str, limit: int = 10, filter_dict: Dict = None) -> List[Dict]:
    """
    Search for transcripts by vector similarity
    """
    global index
    if not index:
        print("Pinecone index not initialized, attempting to initialize...")
        if not init_pinecone():
            print("Failed to initialize Pinecone")
            return []
    
    try:
        query_embedding = get_embedding(query)
        
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
        print(f"Error searching transcripts: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def test_pinecone_connection():
    """Test Pinecone connection and index status"""
    try:
        if not init_pinecone():
            print("Failed to initialize Pinecone")
            return
            
        # Get index stats
        stats = index.describe_index_stats()
        print("\nPinecone Index Status:")
        print(f"Total vectors: {stats.get('total_vector_count', 0)}")
        print(f"Index fullness: {stats.get('index_fullness', 0)}")
        print(f"Dimension: {stats.get('dimension', 0)}")
        
        # Try a simple query
        if stats.get('total_vector_count', 0) > 0:
            print("\nTesting simple query...")
            results = index.query(
                vector=[0.0] * EMBEDDING_DIMENSION,  # Zero vector
                top_k=1,
                include_metadata=True
            )
            if results and results.get('matches'):
                print("Query successful!")
                print(f"Found {len(results['matches'])} matches")
                print(f"Sample match metadata: {results['matches'][0]['metadata']}")
            else:
                print("Query returned no results")
    except Exception as e:
        print(f"Error testing Pinecone: {str(e)}")
        import traceback
        traceback.print_exc()

# Initialize on module import
init_pinecone() 