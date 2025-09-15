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

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Audio Processing Workflow](#audio-processing-workflow)
- [Setup](#setup)
  - [Environment Variables](#environment-variables)
  - [Installation](#installation)
  - [Running the Application](#running-the-application)
  - [Running with Docker](#running-with-docker)
- [API Endpoints](#api-endpoints)
- [All-in-One Processing Endpoint](#all-in-one-processing-endpoint)
- [Credit Management System](#credit-management-system)
- [Search Technology](#search-technology)
- [Use Cases](#use-cases)
- [Error Handling and Resilience](#error-handling-and-resilience)
- [Deployment Notes](#deployment-notes)
- [License](#license)

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
# Core
MONGO_URI=your_mongodb_uri
SECRET_KEY=your_jwt_secret_key
BACKEND_URL=http://localhost:8000  # used by internal wrappers for self-calls

# Auth token expiry (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=60
GUEST_ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS is configured in code; set your frontend origins in main.py

# Rate limiting / IP trust
REDIS_URL=redis://localhost:6379            # optional; in-memory fallback if unset
EXCLUDED_IPS=127.0.0.1                      # comma-separated, bypass limiter
TRUST_CLIENT_IP_HEADER=false                # true in controlled env only
CLIENT_IP_HEADER_TOKEN=                     # optional shared secret when trusting header

# Deepgram (transcription)
DEEPGRAM_API_KEY=your_deepgram_api_key

# Supabase Storage
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_BUCKET=audiofiles
# Optional: Separate buckets for originals vs embedded files
SUPABASE_BUCKET_ORIGINAL=audiofiles
SUPABASE_BUCKET_EMBEDDED=audiofiles-embedded
DELETE_ORIGINAL_SUPABASE_FILE=false

# Pinecone (vector DB)
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=gcp-starter
PINECONE_INDEX_NAME=voicera-audio-search

# Embedding provider (0 = Together, 1 = Gemini)
EMBED_PROVIDER=1
# Together AI (if EMBED_PROVIDER=0)
TOGETHER_API_KEY=your_together_api_key
TOGETHER_EMBEDDING_MODEL=togethercomputer/m2-bert-80M-32k-retrieval
EMBEDDING_DIMENSION=768

# Gemini (LLM/embeddings)
GEMINI_API_KEYS=key1,key2                 # or GEMINI_API_KEY, or GEMINI_API_KEY_1..N
GEMINI_MODEL=gemini-1.5-flash             # used by translation/LLM endpoints
# Budgets (defaults are safe)
GEMINI_EMBED_RPM=100
GEMINI_EMBED_RPS=2
GEMINI_EMBED_TPM=30000
GEMINI_TPM_SAFETY=0.9
GEMINI_EMBED_RPD=1000
GEMINI_BATCH_SIZE=16
GEMINI_TOKEN_OVERHEAD=32

# OAuth (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=

# Credit system
DEFAULT_CREDITS=10
RESET_TIMEFRAME=86400

# SMTP email (admin notifications)
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
ADMIN_EMAIL_ALERTS=admin@example.com

# Admin bootstrap (used by internal flows)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
```

### Supabase Bucket Separation

VOICERA can store original uploads and embedded (metadata-enriched) audio in different Supabase buckets.

- **Original uploads** go to `SUPABASE_BUCKET_ORIGINAL`.
- **Embedded files** go to `SUPABASE_BUCKET_EMBEDDED`.

If these are not set, both will fall back to `SUPABASE_BUCKET`.

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

### Running with Docker

```bash
# from VOICERA/Backend
docker build -t voicera-backend .
docker run --env-file ../.env -p 8000:8000 voicera-backend
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

### System & Admin
- `GET /api/system/health`: Circuit breakers and rate limiter summary (admin)
- `GET /api/system/circuit-breakers`: Detailed breaker states (admin)
- `POST /api/system/circuit-breakers/reset`: Reset all breakers (admin)
- `GET /api/system/rate-limits`: Current limiter configuration (admin)
- `POST /api/send-email`: Admin-only outbound email
- `GET /api/ip-info`, `GET /api/ip`: IP detection/debug
- `GET /api/admin/users`, `PUT /api/admin/users/{id}`, `DELETE /api/admin/users/{id}` (admin)

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

## Deployment Notes

- Configure allowed CORS origins in `Backend/main.py` `CORSMiddleware`. When deploying behind a reverse proxy (e.g., nginx), ensure response headers such as `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` are forwarded/set correctly; otherwise some non-OPTIONS requests may fail in browsers.
- For cluster deployments, set `REDIS_URL` to enable shared rate limiting; the in-memory limiter is suitable for single-instance development.
- Ensure Supabase buckets exist and are public paths under `public/` to match RLS policies used by the service.
- Pinecone index must exist or will be created on startup; confirm `PINECONE_INDEX_NAME`, `EMBEDDING_DIMENSION` match your embedding model.

## License

[MIT License](LICENSE)


