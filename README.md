# VOICERA - Intelligent Audio Search & Analysis Platform

## Overview

VOICERA is a comprehensive audio processing and analysis platform that transforms raw audio into structured, searchable insights using state-of-the-art AI technologies. The platform enables powerful semantic search across audio recordings, allowing users to quickly find relevant information without manually scanning through hours of audio content.

### Key Features

- **Audio Upload & Management**: Support for MP3 files with temporary and permanent storage
- **AI-Powered Transcription**: Detailed transcriptions with timestamps, speaker diarization, and smart formatting
- **Metadata Embedding**: Transcription data embedded directly in MP3 files as ID3 tags
- **Semantic Search**: Vector-based search with natural language processing capabilities
- **Multi-Speaker Analysis**: Speaker diarization and filtering capabilities
- **AI-Powered Answer Generation**: Generate concise answers to questions directly from audio content
- **User Authentication**: Secure access with JWT-based authentication

## Architecture

VOICERA consists of two main components:

1. **Backend API (FastAPI)**: RESTful API handling all audio processing, transcription, storage, and search functionality
2. **Frontend Interface (Streamlit)**: User-friendly interface for interacting with the platform's features

## Audio Processing Workflow

1. **Audio Upload**: User uploads an MP3 file, which is temporarily stored
2. **Transcription**: The file is transcribed using Deepgram's advanced speech-to-text API
3. **Metadata Embedding**: Transcription data is embedded into the MP3 file's ID3 tags
4. **Storage & Indexing**: File is uploaded to Supabase and indexed in Pinecone for semantic search
5. **Search & Analysis**: Users can search through all transcribed audio with natural language queries
6. **Answer Generation**: AI generates concise answers to user questions based on transcript content

## Setup

### Environment Variables

Create a `.env` file in the root directory with:

```
# API Keys
DEEPGRAM_API_KEY=your_deepgram_api_key
TOGETHER_API_KEY=your_together_api_key
PINECONE_API_KEY=your_pinecone_api_key
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-pro

# MongoDB Authentication
MONGO_URI=your_mongodb_uri
SECRET_KEY=your_jwt_secret_key

# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SUPABASE_BUCKET=audiofiles

# Vector Database Configuration
PINECONE_ENVIRONMENT=gcp-starter
PINECONE_INDEX_NAME=voicera-audio-search
EMBEDDING_MODEL=togethercomputer/m2-bert-80M-8k-retrieval
EMBEDDING_DIMENSION=768
```

### Installation

```bash
# Clone the repository
git clone https://github.com/chiranjeevsehgal/VOICERA.git

# Create a virtual environment
python -m venv fastapi-env

# Activate the environment
# On Windows
fastapi-env\Scripts\activate.bat
# On macOS/Linux
source fastapi-env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# Start the backend server
cd Backend
uvicorn main:app --reload --port 8000

# Start the frontend (in a separate terminal)
cd VOICERA
streamlit run wip_app.py
```

## API Endpoints

### Authentication
- `POST /api/auth/register`: Create a new user account
- `POST /api/auth/login`: Authenticate and get access token
- `GET /api/auth/users/profile`: Get current user profile

### Audio Processing
- `POST /api/upload`: Upload audio file to temporary storage
- `POST /api/transcribe`: Transcribe audio from URL with various options
- `POST /api/embed`: Embed transcription data in MP3 file
- `POST /api/extract`: Extract embedded metadata from MP3 file

### Storage & Indexing
- `POST /api/uploadToSupabase`: Upload to permanent storage with automatic indexing
- `GET /api/listSupabaseFiles`: List files in storage

### Search & Analysis
- `GET /api/search`: Search through audio transcripts
  - Supports natural language queries
  - Time range filtering (e.g., "policy 30-32")
  - Speaker filtering
  - LLM query expansion
- `POST /api/generate-answer`: Generate answers from transcript content
- `POST /api/search-and-answer`: Combined search and answer generation

## Answer Generation

VOICERA enables users to ask questions about their audio content and receive AI-generated answers:

- Questions are analyzed against transcript content
- The system uses contextual understanding to extract relevant information
- Answers are generated using language models trained to provide concise, accurate responses
- The feature integrates seamlessly with search results, allowing users to get immediate insights without listening to the entire audio

## Search Technology

VOICERA's search capabilities leverage:

1. **Semantic Vector Embeddings**: Audio transcripts are segmented and converted to vector embeddings using Together AI's embedding models
2. **Vector Database**: Pinecone for efficient similarity search
3. **LLM Integration**: Google's Gemini model for query expansion and answer generation
4. **Natural Language Processing**: Identification of key terms, entities, and temporal references
5. **Time-Based Navigation**: Automatically extracts and processes time references in queries

## Use Cases

- **Media & Journalism**: Find specific quotes or segments in interviews
- **Education**: Search through lecture recordings for specific topics
- **Business**: Analyze meeting recordings for key discussions and decisions
- **Research**: Extract insights from recorded interviews or focus groups
- **Legal & Compliance**: Locate specific clauses or discussions in recorded meetings

## License

[MIT License](LICENSE)


