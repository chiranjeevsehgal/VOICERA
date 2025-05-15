# VOICERA - Audio Transcription and Search Platform

## Overview

VOICERA is an audio processing application that provides:

1. **Audio Upload**: Upload MP3 files to a temporary hosting service
2. **Transcription**: Detailed transcriptions with timestamps and speaker diarization
3. **Metadata Embedding**: Embedding transcription data directly in MP3 files as ID3 tags
4. **Storage**: Permanent storage in Supabase
5. **Semantic Search**: Advanced search capabilities across all audio files with Together AI embeddings

## Audio Processing Workflow

1. **Audio Upload** (`/api/upload`):
   - User uploads an MP3 file
   - The file is temporarily saved locally
   - The file is then uploaded to tmpfiles.org
   - Returns a URL to the uploaded file

2. **Transcription** (`/api/transcribe`):
   - Receives the URL from the previous step
   - Sends the URL to Deepgram's API for transcription
   - Returns detailed transcription data

3. **Embedding** (`/api/embed`):
   - Takes the MP3 file and embeds the transcription metadata into the file as ID3 tags
   - The metadata is encoded as base64 and stored in a custom TXXX tag
   - Saves the file locally with a unique ID

4. **Supabase Upload** (`/api/uploadToSupabase`):
   - Takes the embedded MP3 file
   - Uploads it to Supabase storage
   - Indexes the transcription in Pinecone for search
   - Returns the Supabase URL and file path

5. **Search** (`/api/search`):
   - Searches through all transcribed audio using semantic search with Together AI embeddings
   - Returns matching audio files with precise timestamps
   - Supports time range queries like "policy 30-32" (search for "policy" between 30-32 seconds)
   - Filters by speaker and confidence level

## Setup

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# API Keys
DEEPGRAM_API_KEY=your_deepgram_api_key
TOGETHER_API_KEY=your_together_api_key
PINECONE_API_KEY=your_pinecone_api_key

# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SUPABASE_BUCKET=audiofiles

# Pinecone Configuration
PINECONE_ENVIRONMENT=gcp-starter
PINECONE_INDEX_NAME=voicera-audio-search
EMBEDDING_MODEL=togethercomputer/m2-bert-80M-8k-retrieval
EMBEDDING_DIMENSION=768
```

### Requirements

Install the required packages:

```
pip install together pinecone-client python-dotenv fastapi uvicorn supabase mutagen
```

### Running the Application

Start the FastAPI server:

```
uvicorn Backend.main:app --reload
```

## API Endpoints

### Audio Upload
- `POST /api/upload`: Upload audio to tmpfiles.org

### Transcription
- `POST /api/transcribe`: Transcribe audio from URL

### Embedding
- `POST /api/embed`: Embed transcription data in MP3 file
- `POST /api/extract`: Extract metadata from MP3 file

### Storage
- `POST /api/uploadToSupabase`: Upload to Supabase with automatic indexing
- `GET /api/listSupabaseFiles`: List files in Supabase storage

### Search
- `GET /api/search`: Search through audio transcripts
  - Parameters:
    - `query`: Search query (can include timestamp range, e.g., "policy 30-32")
    - `limit`: Maximum number of results
    - `min_confidence`: Minimum confidence threshold (0-1)
    - `speaker`: Filter by speaker ID

## How Search Works

The search functionality uses:
1. **Vector Embeddings**: Each transcript is split into meaningful chunks
2. **Together AI Embeddings**: Text is converted to vector embeddings using `togethercomputer/m2-bert-80M-8k-retrieval` model
3. **Pinecone Vector DB**: For semantic similarity search
4. **Timestamp Parsing**: Extracts time ranges from search queries
5. **Chunk Metadata**: Preserves timestamps, speaker info, and confidence scores

## **VOICERA – Intelligent Voice Search Engine**


### **Overview**


**Voicera** is an advanced voice tool software designed to revolutionize how organizations and individuals interact with large-scale audio databases. Leveraging cutting-edge AI and machine learning technologies, Voicera enables fast, accurate, and intelligent voice file retrieval from massive repositories of voice data. It transforms raw audio into structured, searchable insights, dramatically reducing the time and effort required to locate specific audio content.




### Installation
- Clone the repository: `git clone https://github.com/chiranjeevsehgal/VOICERA.git`
- Create a virtual environment: `python -m venv fastapi-env`
- Activate the environment: `fastapi-env\Scripts\activate.bat`
- Navigate to backend: `cd Backend`
- Install dependencies: `pip install -r requirements.txt`

### Running the Application

- Activate the environment: `fastapi-env\Scripts\activate.bat`
- Run the application: `uvicorn main:app --reload --port 8000`
- Access the API documentation at `http://localhost:8000/docs`



### **Core Functionality**


#### 🔍 **Smart Voice Search**


Voicera excels at finding relevant voice recordings quickly and accurately. By converting raw audio into searchable transcriptions, it enables users to input a query—textual or verbal—and retrieve the most contextually relevant voice files from extensive archives.


#### 🎙️ **Raw Audio Input & Processing**


Voicera accepts raw audio inputs through uploads, APIs, or real-time streams. These audio files undergo a sophisticated processing pipeline:


* **Noise Filtering & Preprocessing**
* **Automatic Speech Recognition (ASR)** for transcription
* **Speaker Diarization** for identifying different speakers
* **Timestamp Alignment** for precise navigation


#### 🤖 **AI-Powered Understanding**


After transcription, Voicera uses **pre-trained Large Language Models (LLMs)** to interpret the semantic meaning of the spoken content. It understands context, intent, and topics discussed, offering a level of search precision far beyond traditional keyword matching.


#### 🧠 **Semantic Search with Vector Databases**


Transcriptions and audio metadata are encoded into high-dimensional vectors and stored in a **vector database**. Advanced similarity search algorithms (such as cosine similarity or approximate nearest neighbors) are used to compare query vectors against stored data to retrieve the most relevant audio files with high accuracy.


#### 🔁 **Iterative Search Refinement**


Voicera supports dynamic query refinement, allowing users to improve search results interactively using feedback loops and relevance scoring. This enables continuous learning and precision tuning for complex or ambiguous queries.


---


### **Key Features**


* **Multi-format Audio Support** (MP3, WAV, FLAC, etc.)
* **Natural Language Query Interface**
* **Real-time Transcription & Indexing**
* **Speaker & Language Identification**
* **Scalable Architecture for Enterprise Use**
* **Secure Audio Data Handling & Compliance**


---


### **Technology Stack**


* **Audio Processing:** FFmpeg, WebRTC, custom DSP filters
* **Speech Recognition:** Whisper, DeepSpeech, or Google Cloud Speech-to-Text
* **LLMs:** OpenAI GPT models, LLaMA, or similar
* **Vector Database:** FAISS, Pinecone, or Weaviate
* **Backend:** Python (FastAPI), Java (Spring Boot for integration layers)
* **Frontend (Optional):** React or Angular with intuitive UI for playback and navigation
* **Deployment:** Dockerized microservices, scalable with Kubernetes, integrated with cloud platforms (AWS/GCP/Azure)


---


### **Use Cases**


* **Media & Journalism:** Locate quotes or audio snippets in interviews
* **Legal & Compliance:** Retrieve specific clauses or discussions from recorded meetings
* **Customer Support:** Analyze voice calls to detect repeated issues or complaints
* **Enterprise Knowledge Management:** Make voice memos and meetings searchable across departments
* **Research & Academia:** Search voice archives in linguistics or ethnography projects


---


### **Benefits**


* **Time Efficiency:** Dramatically reduces manual effort in browsing hours of recordings
* **Enhanced Accuracy:** Semantic search reduces false positives compared to traditional keyword methods
* **Customizability:** Adaptable for domain-specific vocabularies and dialects
* **Scalability:** Designed to handle millions of audio files seamlessly


---


### **Conclusion**


Voicera is more than just a voice search tool—it's a transformative platform for making voice data accessible, insightful, and actionable. By bridging the gap between raw audio and meaningful understanding, Voicera empowers users to unlock the full potential of their voice datasets with speed, precision, and intelligence.


