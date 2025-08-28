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
- **Credit Management System**: IP-based credit tracking with automatic daily resets
- **Asynchronous Processing**: Real-time job tracking with status updates

## Architecture

VOICERA consists of two main components:

1. **Backend API (FastAPI)**: RESTful API handling all audio processing, transcription, storage, and search functionality
2. **Frontend Interface (Angular)**: Modern, responsive UI for interacting with the platform's features

## Audio Processing Workflow

1. **Audio Upload**: User uploads an MP3 file, which is temporarily stored
2. **Credit Check**: System verifies user has available credits
3. **Transcription**: The file is transcribed using Deepgram's advanced speech-to-text API
4. **Metadata Embedding**: Transcription data is embedded into the MP3 file's ID3 tags
5. **Storage & Indexing**: File is uploaded to Supabase and indexed in Pinecone for semantic search
6. **Credit Deduction**: One credit is deducted from the user's account
7. **Search & Analysis**: Users can search through all transcribed audio with natural language queries
8. **Answer Generation**: AI generates concise answers to user questions based on transcript content

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

# Credit System Configuration
DEFAULT_CREDITS=10
RESET_TIMEFRAME=86400  # 24 hours in seconds

# Admin Credentials
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
```

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/VOICERA.git

# Backend Setup
cd VOICERA/Backend
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
pip install -r requirements.txt

# Frontend Setup
cd ../frontend
npm install
```

### Running the Application

```bash
# Start the backend server
cd Backend
uvicorn main:app --reload --port 8000

# Start the frontend (in a separate terminal)
cd frontend
ng serve
```

## API Endpoints

### Authentication
- `POST /api/auth/register`: Create a new user account
- `POST /api/auth/login`: Authenticate and get access token
- `GET /api/auth/users/profile`: Get current user profile

### Credit Management
- `POST /api/credit`: Deduct a credit from user account
- `GET /api/check-credits`: Check remaining credits for current IP

### Audio Processing
- `POST /api/upload`: Upload audio file to temporary storage
- `POST /api/transcribe`: Transcribe audio from URL with various options
- `POST /api/embed`: Embed transcription data in MP3 file
- `POST /api/extract`: Extract embedded metadata from MP3 file

### Storage & Indexing
- `POST /api/uploadToSupabase`: Upload to permanent storage with automatic indexing
- `GET /api/listAudioFiles`: List files in storage

### Search & Analysis
- `GET /api/search`: Search through audio transcripts
  - Supports natural language queries
  - Time range filtering (e.g., "policy 30-32")
  - Speaker filtering
  - LLM query expansion
- `POST /api/generate-answer`: Generate answers from transcript content
- `POST /api/search-and-answer`: Combined search and answer generation

## All-in-One Processing Endpoint

A unified API endpoint processes audio files through all necessary steps in a single request with real-time status tracking:

### Process Audio (Async)
```
POST /api/process_audio
```

This endpoint initiates audio processing in the background and immediately returns a job ID for tracking progress.

**Required parameters:**
- `file`: The audio file to process (multipart/form-data)

**Optional parameters:**
- `custom_filename`: Alternative filename
- `transcription_options`: JSON string with Deepgram transcription options

**Authentication:**
- Bearer token in Authorization header

**Response:**
```json
{
  "job_id": "f7c45b9a-1234-5678-90ab-cdef12345678",
  "status": "accepted",
  "message": "Your audio is being processed. You can check the status using the job_id."
}
```

### Check Job Status
```
GET /api/job-status/{job_id}
```

Use this endpoint to poll the progress of your audio processing job.

**Authentication:**
- Bearer token in Authorization header

**Response:**
```json
{
  "id": "f7c45b9a-1234-5678-90ab-cdef12345678",
  "status": "transcribing",
  "created_at": "2023-08-15T14:22:30.123456",
  "updated_at": "2023-08-15T14:22:35.654321",
  "progress": 50
}
```

**Possible Status Values:**
- `pending`: Job is queued but not yet started
- `checking_credits`: Checking if user has enough credits
- `uploading`: Uploading the audio file to local storage
- `transcribing`: Transcribing the audio with Deepgram
- `embedding`: Embedding metadata into the audio file
- `uploading_to_supabase`: Uploading to Supabase storage
- `deducting_credits`: Deducting credits from user account
- `completed`: All processing completed successfully
- `failed`: Processing failed (check the error field)

The system automatically cleans up old job records after 24 hours.

## Credit Management System

VOICERA uses an IP-based credit system to manage usage:

- Each IP address receives a default number of credits (configurable)
- One credit is consumed per audio file processing
- Credits automatically reset after a configurable timeframe (default: 24 hours)
- Admin accounts can bypass credit limitations
- Real-time credit checking and deduction

## Search Technology

VOICERA's search capabilities leverage:

1. **Semantic Vector Embeddings**: Audio transcripts are segmented and converted to vector embeddings
2. **Vector Database**: Pinecone for efficient similarity search
3. **Natural Language Processing**: Identification of key terms, entities, and temporal references
4. **Time-Based Navigation**: Automatically extracts and processes time references in queries

## Use Cases

- **Media & Journalism**: Find specific quotes or segments in interviews
- **Education**: Search through lecture recordings for specific topics
- **Business**: Analyze meeting recordings for key discussions and decisions
- **Research**: Extract insights from recorded interviews or focus groups
- **Legal & Compliance**: Locate specific clauses or discussions in recorded meetings

## Error Handling and Resilience

The application includes robust error handling and resilience features:

- Concurrent processing through thread pools
- Automatic cleanup of temporary files
- Graceful degradation when services are unavailable
- Detailed error reporting through job status API
- Background tasks for system maintenance

## License

[MIT License](LICENSE)


