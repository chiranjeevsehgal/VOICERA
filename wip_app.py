import streamlit as st
import requests
import json
import os
import tempfile
import time
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()

# API Configuration
API_BASE_URL = "http://localhost:8000/api"

# Set page configuration
st.set_page_config(
    page_title="VOICERA - Audio Search Platform",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* General Body and Text */
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
        background-color: #121212; /* Dark background */
        color: #E0E0E0 !important; /* Lighter text for better contrast */
    }
    
    p, div, span, li, label { /* Applied to most text elements, h1-h6 handled separately or via classes */
        color: #E0E0E0 !important; 
        font-size: 16px !important;
        line-height: 1.6 !important;
    }

    /* Headers */
    .main-header {
        font-size: 2.8rem !important; /* Slightly larger */
        color: #FFFFFF !important; /* Pure white for emphasis */
        margin-bottom: 0.5rem; /* Reduced margin */
        font-weight: 700;
    }
    
    .app-subtitle {
        font-size: 1.2rem !important;
        color: #A0A0A0 !important;
        margin-bottom: 1.5rem;
        font-weight: 400;
    }

    .sub-header { /* Used for sidebar headers */
        font-size: 1.6rem !important; 
        color: #FFFFFF !important;
        margin-top: 1rem;
        margin-bottom: 0.8rem;
        font-weight: 600;
        padding-bottom: 5px;
        border-bottom: 1px solid #333;
    }
    
    .step-header { /* Used for main content section headers */
        font-size: 2rem !important; 
        color: #FFFFFF !important;
        margin-top: 2rem; /* More top margin for sections */
        margin-bottom: 1.5rem; /* More bottom margin */
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #4F8BF9; /* Accent color border */
        font-weight: 600;
    }
    
    /* Containers and Boxes */
    .highlight, .success-box, .info-box {
        padding: 20px !important; 
        border-radius: 8px; 
        margin: 15px 0 !important;
        color: #E0E0E0 !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }

    .highlight {
        background-color: #222222 !important; 
        border-left: 5px solid #4F8BF9; 
    }
    
    .success-box {
        background-color: #1c331c !important; 
        border-left: 5px solid #4CAF50; 
    }
    
    .info-box {
        background-color: #1c2a38 !important; 
        border-left: 5px solid #2196F3; 
    }

    .success-box h3, .info-box h3, .highlight h3,
    .success-box h4, .info-box h4, .highlight h4 {
        color: #FFFFFF !important;
        margin-top: 0;
    }
    .success-box p, .info-box p, .highlight p {
        color: #E0E0E0 !important;
    }
    .success-box a, .info-box a, .highlight a {
        color: #64B5F6 !important;
        font-weight: 600;
    }
    .success-box a:hover, .info-box a:hover, .highlight a:hover {
        color: #90CAF9 !important;
        text-decoration: underline !important;
    }
    
    /* Expanders */
    .stExpander {
        border: 1px solid #383838 !important; 
        border-radius: 8px;
        margin-bottom: 20px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.3);
        overflow: hidden; /* Ensures border-radius applies to children */
    }
    
    .stExpander > div:first-child { /* Expander header */
        background-color: #2a2a2a !important;
        color: #FFFFFF !important;
        padding: 12px 15px !important; 
        border-bottom: 1px solid #383838; /* Separator line */
    }

    .stExpander > div > div[data-testid="stExpanderDetails"] { /* Expander content */
        padding: 20px !important;
        background-color: #1e1e1e !important;
        color: #E0E0E0 !important;
    }
    
    /* Text Elements specific styling */
    div[data-testid="stText"], div[data-testid="stMarkdown"] p {
        font-size: 16px !important;
        color: #E0E0E0 !important;
        line-height: 1.6 !important;
    }
    
    label[data-testid="stWidgetLabel"] { /* Streamlit widget labels */
        font-weight: 500 !important;
        color: #C0C0C0 !important; 
        font-size: 15px !important;
        margin-bottom: 0.3rem !important;
    }
    
    pre {
        background-color: #2a2a2a !important;
        padding: 15px !important;
        border-radius: 5px;
        white-space: pre-wrap;
        font-size: 14px !important;
        color: #E0E0E0 !important;
        line-height: 1.5 !important;
        border: 1px solid #383838;
    }
    
    /* Buttons */
    .stButton button {
        background-color: #4F8BF9 !important;
        color: white !important;
        font-weight: bold !important;
        padding: 10px 18px !important; /* Adjusted padding */
        font-size: 16px !important;
        border-radius: 5px;
        border: none;
        transition: background-color 0.2s ease, box-shadow 0.2s ease;
    }
    
    .stButton button:hover {
        background-color: #3B7DFA !important;
        box-shadow: 0 3px 6px rgba(0,0,0,0.25) !important; 
    }
    
    /* Important Text */
    strong, b {
        color: #FFFFFF !important; /* Pure white for strong text */
        font-weight: 600 !important;
    }
    
    mark {
        background-color: #FFC107 !important; /* Brighter yellow for <mark> */
        padding: 2px 4px !important;
        color: black !important;
        font-weight: bold !important;
        border-radius: 3px;
    }
        
    /* Links */
    a {
        color: #64B5F6 !important; 
        text-decoration: none !important;
        font-weight: 500 !important;
        transition: color 0.2s ease;
    }
    
    a:hover {
        text-decoration: underline !important;
        color: #90CAF9 !important; 
    }
    
    /* Custom Components */
    .result-text { /* For search results */
        font-size: 16px !important;
        background-color: #2a2a2a !important; 
        padding: 15px !important;
        border-radius: 5px;
        margin-bottom: 10px !important;
        color: #E0E0E0 !important;
        border: 1px solid #383838;
        line-height: 1.7 !important;
    }
    
    .metadata-box {
        display: flex;
        flex-wrap: wrap; 
        gap: 15px; 
        background-color: #1e1e1e !important; 
        padding: 12px 18px !important;
        border-radius: 5px;
        margin: 10px 0 !important;
        border: 1px solid #333;
    }
    
    .metadata-item {
        color: #C0C0C0 !important; 
        font-size: 14px !important;
    }
    .metadata-item strong { color: #E0E0E0 !important; } 
    
    /* Input Fields */
    .stTextInput > div > div, .stNumberInput > div > div {
        background-color: #2a2a2a !important; 
        border-radius: 5px;
    }
    
    .stTextInput input, .stNumberInput input {
        color: #E0E0E0 !important;
        background-color: #2a2a2a !important; 
        border: 1px solid #444 !important; 
        border-radius: 5px;
        padding: 8px 10px !important;
    }
    
    .stSlider > div { /* Slider track and thumb container */
        color: #E0E0E0 !important;
    }
    .stSlider [data-testid="stTickBarMin"], .stSlider [data-testid="stTickBarMax"] {
        color: #A0A0A0 !important;
    }
    
    /* Radio buttons and Checkboxes */
    .stRadio label span, .stCheckbox label span { /* Target the span inside label for text */
        color: #D0D0D0 !important; 
        font-size: 16px !important;
    }
    
    /* Streamlit Headers default styling override */
    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important; /* Default to pure white */
        font-weight: 600 !important;
    }
    
    /* Alerts */
    .stAlert {
        background-color: #2a2a2a !important; 
        color: #E0E0E0 !important;
        border-left-width: 4px !important; /* Ensure border is visible */
        border-radius: 5px !important;
    }
    .stAlert[data-baseweb="notification"] { /* Specific for alert content text */
         color: #E0E0E0 !important;
    }
    .stAlert strong { color: #FFFFFF !important; } /* Make strong text in alerts pop */

    /* Dropdowns */
    .stSelectbox label span { /* Label text */
        color: #D0D0D0 !important;
    }
    .stSelectbox > div > div[data-baseweb="select"] > div { /* Selectbox input area */
        background-color: #2a2a2a !important;
        border: 1px solid #444 !important;
        color: #E0E0E0 !important;
        border-radius: 5px;
    }
     /* Selected value text color */
    .stSelectbox div[data-baseweb="select"] div[data-testid="stText"] {
        color: #E0E0E0 !important;
    }
    /* Dropdown menu items */
    div[data-baseweb="popover"] ul li {
        background-color: #2a2a2a !important;
        color: #E0E0E0 !important;
    }
    div[data-baseweb="popover"] ul li:hover {
        background-color: #383838 !important;
    }

    /* Styling for file uploader message */
    div[data-testid="stFileUploader"] small {
        color: #AAAAAA !important; 
    }
    div[data-testid="stFileUploaderFileData"] { /* File name display */
        color: #C0C0C0 !important;
    }
    
    /* Styling for audio player */
    .stAudio {
        background-color: transparent !important; /* Make Streamlit's audio container transparent */
        border-radius: 5px;
        padding: 0; /* Remove padding if audio controls have their own */
    }
    .stAudio audio { /* Target the HTML5 audio element directly */
        width: 100%;
        border-radius: 5px;
        /* Basic theming for Chrome/Edge if possible, limited capabilities */
        /* filter: invert(1) sepia(0) saturate(0) hue-rotate(0deg) brightness(1.1) contrast(0.9); */
    }

    /* Action and Download Links (used in search results) */
    .action-link {
        display: inline-block;
        padding: 7px 12px;
        background-color: #3949AB !important; /* Indigo family */
        color: white !important;
        text-decoration: none !important;
        border-radius: 4px;
        text-align: center;
        font-size: 13px !important;
        font-weight: 500 !important;
        width: 100%;
        margin-top: 5px;
        border: none;
        transition: background-color 0.2s ease;
    }
    .action-link:hover {
        background-color: #283593 !important; /* Darker indigo */
        text-decoration: none !important;
    }
    .download-link {
        display: block; 
        padding: 8px 12px;
        background-color: #455A64 !important; /* Blue Grey */
        color: white !important;
        text-decoration: none !important;
        border-radius: 4px;
        text-align: center;
        font-size: 14px !important;
        font-weight: 500 !important;
        width: 100%;
        margin-top: 10px;
        border: none;
        transition: background-color 0.2s ease;
    }
    .download-link:hover {
        background-color: #37474F !important; /* Darker Blue Grey */
        text-decoration: none !important;
    }
    hr {
        border-top: 1px solid #333;
        margin-top: 1.5rem;
        margin-bottom: 1.5rem;
    }

</style>
""", unsafe_allow_html=True)

def display_header():
    col1, col2 = st.columns([1, 6]) # Adjusted column ratio
    with col1:
        st.image("https://img.icons8.com/pulsar-color/96/microphone.png", width=90) # Slightly larger
    with col2:
        st.markdown("<div class='main-header'>VOICERA</div>", unsafe_allow_html=True)
        st.markdown("<div class='app-subtitle'>Intelligent Audio Search & Analysis Platform</div>", unsafe_allow_html=True)
    
    st.markdown("<hr style='margin-top: 1rem; margin-bottom: 2rem;'>", unsafe_allow_html=True)

def display_sidebar():
    st.sidebar.markdown("<div class='sub-header'>Workflow Navigation</div>", unsafe_allow_html=True)
    workflow_option = st.sidebar.radio(
        "Select Workflow Step:", # Added colon for clarity
        ["Complete Workflow", "Upload Audio", "Transcribe Audio", "Embed Metadata", "Supabase Upload", "Search Audio"],
        label_visibility="collapsed" # Use sub-header as label
    )
    
    st.sidebar.markdown("<hr style='margin: 1rem 0;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sub-header'>About VOICERA</div>", unsafe_allow_html=True)
    st.sidebar.info("""
    VOICERA is an advanced platform designed to revolutionize your interaction with audio files. 
    It transforms raw audio into structured, searchable insights using cutting-edge AI.
    """)
    
    return workflow_option

def upload_audio_section():
    st.markdown("<div class='step-header'>1️⃣ Audio Upload</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='info-box'>Upload an MP3 file to begin the processing workflow. The file will be temporarily stored for the next steps.</div>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Select an MP3 audio file:", type=["mp3"], label_visibility="visible")
    
    if uploaded_file:
        st.markdown("<div style='padding: 10px 0; margin-bottom: 15px;'>", unsafe_allow_html=True)
        st.audio(uploaded_file, format="audio/mp3")
        st.markdown("</div>", unsafe_allow_html=True)
        
        if st.button("Upload to Temporary Storage", key="upload_btn", use_container_width=True):
            with st.spinner("Uploading audio to temporary storage..."):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/upload", 
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "audio/mpeg")}
                    )
                    
                    if response.status_code == 201:
                        st.session_state.upload_result = response.json()
                        st.markdown(f"""
                        <div class='success-box'>
                        <h4>Audio uploaded successfully!</h4>
                        <p>Temporary URL: <a href="{st.session_state.upload_result['url']}" target="_blank">
                        {st.session_state.upload_result['url']}</a></p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.error(f"Error uploading audio: {response.status_code} - {response.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"API Connection Error: {str(e)}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {str(e)}")
    
    st.markdown("---")
    return uploaded_file

def transcribe_audio_section():
    st.markdown("<div class='step-header'>2️⃣ Transcription</div>", unsafe_allow_html=True)
    
    upload_result = st.session_state.get('upload_result')
    url_value = upload_result.get('url', '') if upload_result and isinstance(upload_result, dict) else ''
    
    url_input = st.text_input(
        "Audio URL to transcribe:", 
        value=url_value,
        placeholder="Enter URL of the uploaded audio file"
    )
    
    st.markdown("<h5 style='margin-top: 1.5rem; margin-bottom: 0.5rem; color: white !important;'>Transcription Options:</h5>", unsafe_allow_html=True)
    with st.container(): # Removed bordered container for cleaner look
        col1, col2 = st.columns(2)
        with col1:
            diarize = st.checkbox("Speaker Diarization", value=True, help="Identify different speakers in the audio.")
            punctuate = st.checkbox("Add Punctuation", value=True, help="Include punctuation in the transcript.")
            detect_language = st.checkbox("Detect Language", value=False, help="Automatically detect the spoken language.")
        
        with col2:
            smart_format = st.checkbox("Smart Formatting", value=True, help="Format numbers, dates, etc., intelligently.")
            utterances = st.checkbox("Generate Utterances", value=True, help="Break transcript into meaningful utterances.")
            model = st.selectbox("Transcription Model", ["nova-2", "nova", "whisper"], index=0, help="Select the AI model for transcription.")
    
    if url_input and st.button("Transcribe Audio", use_container_width=True, key="transcribe_btn"):
        with st.spinner("Transcribing audio... This may take a moment."):
            try:
                payload = {
                    "url": url_input, "diarize": diarize, "punctuate": punctuate,
                    "smart_format": smart_format, "utterances": utterances,
                    "detect_language": detect_language, "model": model
                }
                response = requests.post(f"{API_BASE_URL}/transcribe", json=payload)
                
                if response.status_code == 200:
                    st.session_state.transcription_result = response.json()
                    transcript_data = st.session_state.transcription_result
                    
                    transcript = "No transcript found in response."
                    duration = 0
                    
                    if "results" in transcript_data:
                        results = transcript_data["results"]
                        if "channels" in results and len(results["channels"]) > 0:
                            alternatives = results["channels"][0].get("alternatives", [])
                            if alternatives and len(alternatives) > 0:
                                transcript = alternatives[0].get("transcript", "No transcript text.")
                        duration = results.get("duration", 0)
                    
                    st.markdown("<div class='success-box'><h4>Transcription completed successfully!</h4></div>", unsafe_allow_html=True)
                    
                    with st.expander("View Transcription Summary", expanded=True):
                        st.markdown(f"""
                        <div class='info-box' style='margin-top:0;'>
                        <strong>Duration:</strong> {duration:.2f} seconds<br>
                        <strong>Model Used:</strong> {model}<br>
                        <strong>Features Enabled:</strong> {"Diarization, " if diarize else ""}{"Punctuation, " if punctuate else ""}{"Smart Formatting" if smart_format else ""}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("<h5 style='margin-top: 1rem; margin-bottom: 0.5rem; color: white !important;'>Full Transcript:</h5>", unsafe_allow_html=True)
                        st.markdown(f"""
                        <div class='highlight' style='max-height: 400px; overflow-y: auto; font-size: 16px !important; line-height: 1.7 !important; background-color: #2d2d2d !important; border: 1px solid #444; box-shadow: 0 1px 2px rgba(0,0,0,0.3); color: #E0E0E0 !important;'>
                            {transcript}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.session_state.transcription_json = json.dumps(transcript_data)
                else:
                    st.error(f"Error transcribing audio: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"API Connection Error: {str(e)}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")
    
    st.markdown("---")

def embed_metadata_section(uploaded_file_obj): # Renamed for clarity
    st.markdown("<div class='step-header'>3️⃣ Metadata Embedding</div>", unsafe_allow_html=True)
    
    if not hasattr(st.session_state, 'transcription_json') or not st.session_state.transcription_json:
        st.warning("Please complete the transcription step first to generate metadata.")
        return
    
    st.markdown("<div class='info-box'>This step embeds the transcription data (as JSON) into the MP3 file's ID3 tags. You might need to re-upload the original MP3 file if it's not available from the previous step.</div>", unsafe_allow_html=True)
    
    # Use the passed uploaded_file_obj if available, otherwise show uploader
    # This part is tricky as Streamlit's FileUploader state is ephemeral across reruns if not handled carefully
    # For simplicity, we'll always show the uploader here, but pre-fill if 'uploaded_file' is in session state.
    
    # This requires user to re-upload if they navigate away and come back.
    # A more robust solution would store file bytes in session_state if small enough, or path if persisted.
    embedded_file_upload = st.file_uploader("Upload the original MP3 file for metadata embedding:", type=["mp3"], key="embed_mp3_uploader")
    
    if embedded_file_upload and st.button("Embed Metadata", use_container_width=True, key="embed_btn"):
        with st.spinner("Embedding metadata into audio file..."):
            try:
                files = {"mp3_file": (embedded_file_upload.name, embedded_file_upload.getvalue(), "audio/mpeg")}
                data = {"metadata": st.session_state.transcription_json}
                
                response = requests.post(f"{API_BASE_URL}/embed", files=files, data=data)
                
                if response.status_code == 200:
                    st.session_state.embedding_result = response.json()
                    st.markdown(f"""
                    <div class='success-box'>
                    <h4>Metadata embedded successfully!</h4>
                    <p>File saved as: <strong>{st.session_state.embedding_result.get('file_name', 'N/A')}</strong> on the server.</p>
                    <p>You will typically use this server-side file in the next Supabase upload step.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error(f"Error embedding metadata: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"API Connection Error: {str(e)}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")
    
    st.markdown("---")

def supabase_upload_section():
    st.markdown("<div class='step-header'>4️⃣ Supabase Storage & Indexing</div>", unsafe_allow_html=True)
    
    if not hasattr(st.session_state, 'embedding_result'): # Check if embedding step produced a result
        st.warning("Please complete the metadata embedding step first. The embedded file (server-side) is usually the one uploaded here.")
        # return # Optional: block if previous step not done. For now, allow proceeding with manual upload.

    st.markdown("<div class='info-box'>Upload the MP3 file (ideally the one with embedded metadata) to Supabase permanent storage. The file will also be prepared for vector indexing.</div>", unsafe_allow_html=True)
    
    supabase_uploaded_file = st.file_uploader("Upload the MP3 file for Supabase:", type=["mp3"], key="supabase_uploader")
    
    if supabase_uploaded_file and st.button("Upload to Supabase & Index", use_container_width=True, key="supabase_btn"):
        with st.spinner("Uploading to Supabase and preparing for indexing..."):
            try:
                files = {"file": (supabase_uploaded_file.name, supabase_uploaded_file.getvalue(), "audio/mpeg")}
                response = requests.post(f"{API_BASE_URL}/uploadToSupabase", files=files)
                
                if response.status_code == 201:
                    st.session_state.supabase_result = response.json()
                    supabase_data = st.session_state.supabase_result
                    st.markdown(f"""
                    <div class='success-box'>
                    <h4>File uploaded to Supabase successfully!</h4>
                    <p>Permanent URL: <a href="{supabase_data.get('file_url', '#')}" target="_blank">
                    {supabase_data.get('file_url', 'N/A')}</a></p>
                    <p>Indexed in vector database: <strong>{"Yes" if supabase_data.get('indexed', False) else "No/Pending"}</strong></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if 'metadata' in supabase_data and supabase_data['metadata']:
                        with st.expander("View Extracted Metadata from Supabase Upload"):
                            st.json(supabase_data['metadata'])
                else:
                    st.error(f"Error uploading to Supabase: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"API Connection Error: {str(e)}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")
    
    st.markdown("---")

def search_audio_section():
    st.markdown("<div class='step-header'>5️⃣ Semantic Audio Search</div>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class='info-box'>
    Search through indexed audio files using semantic queries. 
    You can use natural language (e.g., "find discussions about project alpha") or include time hints (e.g., "meeting summary 10:00-15:00").
    </div>
    """, unsafe_allow_html=True)

    search_col1, search_col2 = st.columns([4, 1])
    with search_col1:
        search_query = st.text_input("Search Query:", placeholder="e.g., 'marketing strategies for Q4' or 'audio about last week's sync-up'", key="search_query_input")
    with search_col2:
        limit = st.number_input("Results Limit:", min_value=1, max_value=50, value=5, step=1, key="search_limit_input") # Reduced max for typical use

    st.markdown("<h5 style='margin-top: 1rem; margin-bottom: 0.5rem; color: white !important;'>Advanced Search Filters:</h5>", unsafe_allow_html=True)
    opts_col1, opts_col2, opts_col3, opts_col4 = st.columns(4)
    with opts_col1:
        min_confidence = st.slider("Min. Confidence:", 0.0, 1.0, 0.75, step=0.05, help="Minimum relevance score for results (0.0 to 1.0).", key="search_confidence_slider")
    with opts_col2:
        speaker_input = st.number_input("Filter Speaker ID:", min_value=0, value=0, step=1, help="Filter by a specific speaker ID (0 for no filter).", key="search_speaker_input")
        speaker = speaker_input if speaker_input > 0 else None
    with opts_col3:
        use_llm_expansion = st.checkbox("LLM Expansion", value=True, help="Expand query with synonyms and related terms for broader matching.", key="search_llm_checkbox")
    with opts_col4:
        natural_language = st.checkbox("NL Query Mode", value=False, help="Process query as a natural language question for intent understanding.", key="search_nl_checkbox")
    
    if search_query and st.button("Search Audio Library", use_container_width=True, key="search_btn"):
        with st.spinner("Searching audio transcripts..."):
            try:
                params = {
                    "query": search_query, "limit": limit, "min_confidence": min_confidence,
                    "use_llm_expansion": use_llm_expansion, "natural_language": natural_language
                }
                if speaker is not None:
                    params["speaker"] = speaker
                
                response = requests.get(f"{API_BASE_URL}/search", params=params)
                
                if response.status_code == 200:
                    search_results_data = response.json()
                    st.session_state.search_results_data = search_results_data # Store for potential re-display or pagination later

                    st.markdown(f"""
                    <div class='info-box' style='margin-top:1.5rem;'>
                    Found <strong>{search_results_data.get('total', 0)}</strong> potential results for your query.
                    {f"({search_results_data.get('exact_matches', 0)} exact segment matches)" if 'exact_matches' in search_results_data else ""}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display NL analysis if present
                    if natural_language and search_results_data.get('natural_language_analysis'):
                        nl_analysis = search_results_data['natural_language_analysis']
                        analysis_html = f"<div class='highlight'><strong>Understanding your query:</strong><br>"
                        if nl_analysis.get('search_intent'):
                            analysis_html += f"<span style='font-style: italic;'>Intent: {nl_analysis.get('search_intent', '')}</span><br>"
                        if nl_analysis.get('key_terms'):
                            analysis_html += f"<strong>Key terms:</strong> {', '.join(nl_analysis.get('key_terms', []))}"
                        if nl_analysis.get('temporal_references'):
                            analysis_html += f"<br><strong>Time references:</strong> {', '.join(nl_analysis.get('temporal_references', []))}"
                        analysis_html += "</div>"
                        st.markdown(analysis_html, unsafe_allow_html=True)
                    
                    # Display expanded queries
                    elif search_results_data.get('expanded_queries') and len(search_results_data.get('expanded_queries', [])) > 1:
                        expanded = search_results_data['expanded_queries']
                        st.markdown(f"""
                        <div class='highlight'>
                        Query expanded to include: {", ".join(f'"{q}"' for q in expanded if q.lower() != search_query.lower())}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Display detected time range
                    if search_results_data.get('time_range'):
                        time_range = search_results_data['time_range']
                        st.markdown(f"""
                        <div class='highlight'>
                        Detected time range in query: {time_range.get('start_formatted','N/A')} - {time_range.get('end_formatted','N/A')}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Display results
                    if search_results_data.get('results'):
                        exact_matches = [r for r in search_results_data['results'] if r.get('has_exact_match', False)]
                        semantic_matches = [r for r in search_results_data['results'] if not r.get('has_exact_match', False)]
                        
                        if exact_matches:
                            st.markdown("<h4 style='margin-top: 2rem; margin-bottom: 1rem; color: #4CAF50 !important;'>🎯 Exact Matches</h4>", unsafe_allow_html=True)
                            for i, result in enumerate(exact_matches):
                                display_search_result(result, search_results_data, search_query, is_exact=True, index=i)
                        
                        if semantic_matches:
                            st.markdown("<h4 style='margin-top: 2rem; margin-bottom: 1rem; color: #FF9800 !important;'>💡 Semantic Matches</h4>", unsafe_allow_html=True)
                            for i, result in enumerate(semantic_matches):
                                display_search_result(result, search_results_data, search_query, is_exact=False, index=i)
                    else:
                        st.warning("No results found matching your criteria.")
                else:
                    st.error(f"Error during search: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"API Connection Error: {str(e)}")
            except Exception as e:
                st.error(f"An unexpected error occurred during search: {str(e)}")

def display_search_result(result, search_results_data, original_query, is_exact, index):
    """Helper function to display a single search result with refined UI."""
    score_color = "#4CAF50" if is_exact else "#FF9800"
    match_type_label = "Exact Match" if is_exact else "Semantic Match"
    
    expander_title = f"Result #{index + 1}: Score {result['score']:.3f} ({match_type_label})"
    if result.get('matched_query') and result['matched_query'].lower() != original_query.lower():
        expander_title += f" (Matched on: '{result['matched_query']}')"

    with st.expander(expander_title, expanded=(index == 0)): # Expand first result by default
        st.markdown(f"<span style='color: {score_color}; font-weight: 600; font-size: 0.9em;'>{match_type_label.upper()}</span>", unsafe_allow_html=True)

        col_text, col_audio = st.columns([3, 1.5]) # Adjust column ratio for better balance

        with col_text:
            # Text Highlighting
            text_content = result.get('text', 'No text content available.')
            highlight_terms = set()
            
            # Add original query terms (non-stopwords, longer than 2 chars)
            stopwords = {
                "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "by", "for", "with", "about", 
                "to", "from", "in", "out", "on", "off", "is", "are", "was", "were", "be", "been", "has", "had", "do", "does", "did"
            } # Simplified stopwords list
            
            original_query_terms = [term.lower() for term in original_query.lower().split() if term.lower() not in stopwords and len(term) > 2]
            for term in original_query_terms: highlight_terms.add(term)

            if result.get('matched_query'):
                matched_query_terms = [term.lower() for term in result['matched_query'].lower().split() if term.lower() not in stopwords and len(term) > 2]
                for term in matched_query_terms: highlight_terms.add(term)
            
            if result.get('matched_terms'): # From NL analysis
                nl_matched_terms = [term.lower() for term in result.get('matched_terms', []) if term.lower() not in stopwords and len(term) > 2]
                for term in nl_matched_terms: highlight_terms.add(term)

            temp_text = text_content
            for term in sorted(list(highlight_terms), key=len, reverse=True): # Sort by length to match longer phrases first
                try:
                    # Case-insensitive replace for highlighting
                    import re
                    # Escape special characters in term for regex
                    escaped_term = re.escape(term)
                    # Find all occurrences of the term, case-insensitive
                    for match in re.finditer(escaped_term, temp_text, re.IGNORECASE):
                        actual_match = match.group(0) # Get the actual matched string (to preserve case)
                        # Replace only if not already inside a mark tag
                        # This is a simple check and might not be perfectly robust for nested scenarios
                        start_offset = temp_text.rfind("<mark>", 0, match.start())
                        end_offset = temp_text.find("</mark>", match.start())
                        if not (start_offset != -1 and end_offset != -1 and start_offset < match.start() < end_offset):
                             temp_text = temp_text.replace(actual_match, f"<mark>{actual_match}</mark>", 1) # Replace one by one to handle overlaps better
                except Exception: # Fallback if regex fails
                    pass # Continue without this specific term's highlighting

            st.markdown(f"<div class='result-text'>{temp_text}</div>", unsafe_allow_html=True)

            if result.get('matched_terms') and (natural_language_analysis := search_results_data.get('natural_language_analysis')):
                st.markdown(f"""
                <div style='font-size: 0.85em; color: #B0B0B0; margin-top: -5px; margin-bottom:10px;'>
                Matched terms via NL: {", ".join(result['matched_terms'])}
                {"" if not result.get('has_time_match') else " | Includes time reference match"}
                </div>
                """, unsafe_allow_html=True)

            # Metadata Box
            metadata_html = "<div class='metadata-box'>"
            metadata_html += f"<div class='metadata-item'><strong>Time:</strong> {result.get('start_time_formatted', 'N/A')} - {result.get('end_time_formatted', 'N/A')}</div>"
            if result.get('speaker') is not None:
                metadata_html += f"<div class='metadata-item'><strong>Speaker:</strong> {result.get('speaker')}</div>"
            metadata_html += f"<div class='metadata-item'><strong>Confidence:</strong> {result.get('confidence', 0):.3f}</div>"
            if 'nl_score' in result:
                metadata_html += f"<div class='metadata-item'><strong>NL Score:</strong> {result.get('nl_score', 0):.3f}</div>"
            metadata_html += "</div>"
            st.markdown(metadata_html, unsafe_allow_html=True)

        with col_audio:
            if result.get('file_url'):
                st.markdown("<div style='font-weight: 500; margin-bottom: 8px; font-size: 0.95em;'>Listen to Segment:</div>", unsafe_allow_html=True)
                st.audio(result['file_url'], format="audio/mp3", start_time=int(result.get('start_time', 0))) # Use start_time for player

                start_sec = result.get('start_time', 0)
                # end_sec = result.get('end_time') # Not directly usable in simple HTML links for end time
                
                # Create links for navigating in external player supporting time fragments
                exact_timestamp_url = f"{result['file_url']}#t={start_sec}"
                context_start_sec = max(0, start_sec - 5)
                context_timestamp_url = f"{result['file_url']}#t={context_start_sec}"

                link_cols = st.columns(2)
                with link_cols[0]:
                    st.markdown(f"<a href='{context_timestamp_url}' target='_blank' class='action-link'>⏪ Play w/ Context</a>", unsafe_allow_html=True)
                with link_cols[1]:
                    st.markdown(f"<a href='{exact_timestamp_url}' target='_blank' class='action-link'>▶️ Play Exact</a>", unsafe_allow_html=True)
                
                st.markdown(f"<a href=\"{result['file_url']}\" download class='download-link'>💾 Download Full Audio</a>", unsafe_allow_html=True)
            else:
                st.caption("Audio source not available.")

def complete_workflow():
    st.markdown("<div class='step-header' style='margin-top:0;'>Complete VOICERA Workflow</div>", unsafe_allow_html=True)
    st.markdown("<div class='info-box'>This page guides you through the entire workflow from audio upload to search, combining all steps.</div>", unsafe_allow_html=True)
    
    # Persist uploaded_file across sections if possible, or manage its state carefully
    # For this refactor, each section will manage its own file upload if needed.
    # 'st.session_state.uploaded_file_object' could be used to pass it if set in upload_audio_section.

    if 'current_uploaded_file' not in st.session_state:
        st.session_state.current_uploaded_file = None

    # Section 1: Upload
    st.session_state.current_uploaded_file = upload_audio_section() 
    
    # Section 2: Transcribe (uses URL from upload_result)
    transcribe_audio_section() 
    
    # Section 3: Embed (may need the uploaded file again)
    # Pass the file object from upload_audio_section if it's still valid
    embed_metadata_section(st.session_state.current_uploaded_file) 
    
    # Section 4: Supabase Upload (typically uploads the server-side embedded file or a new one)
    supabase_upload_section()
    
    # Section 5: Search
    search_audio_section()

def main():
    # Initialize session state variables if they don't exist
    if 'upload_result' not in st.session_state:
        st.session_state.upload_result = None
    if 'transcription_result' not in st.session_state:
        st.session_state.transcription_result = None
    if 'transcription_json' not in st.session_state:
        st.session_state.transcription_json = None
    if 'embedding_result' not in st.session_state:
        st.session_state.embedding_result = None
    if 'supabase_result' not in st.session_state:
        st.session_state.supabase_result = None
    if 'search_results_data' not in st.session_state:
        st.session_state.search_results_data = None
    if 'current_uploaded_file_for_embedding' not in st.session_state: # For passing file object
        st.session_state.current_uploaded_file_for_embedding = None


    display_header()
    workflow_option = display_sidebar()
    
    # Store the initially uploaded file in session state for other sections if needed
    # This helps if 'Complete Workflow' is not selected initially
    # initial_uploaded_file_placeholder = None

    if workflow_option == "Complete Workflow":
        complete_workflow()
    elif workflow_option == "Upload Audio":
        uploaded_file_obj = upload_audio_section()
        if uploaded_file_obj: # Store it for potential use in other steps if user navigates
             st.session_state.current_uploaded_file_for_embedding = uploaded_file_obj
    elif workflow_option == "Transcribe Audio":
        transcribe_audio_section()
    elif workflow_option == "Embed Metadata":
        # Try to use a file uploaded in the 'Upload Audio' step if available and user is navigating
        file_for_embedding = st.session_state.get('current_uploaded_file_for_embedding', None)
        embed_metadata_section(file_for_embedding) 
    elif workflow_option == "Supabase Upload":
        supabase_upload_section()
    elif workflow_option == "Search Audio":
        search_audio_section()

if __name__ == "__main__":
    main() 