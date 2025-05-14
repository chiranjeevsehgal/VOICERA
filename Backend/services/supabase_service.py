import os
from supabase import create_client, Client
from dotenv import load_dotenv
import uuid

# Load environment variables
load_dotenv()

# Supabase configuration
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase_bucket = os.getenv("SUPABASE_BUCKET", "audiofiles")

# Initialize Supabase client
supabase: Client = None

def init_supabase():
    """Initialize Supabase client if environment variables are set"""
    global supabase
    if supabase_url and supabase_key:
        try:
            supabase = create_client(supabase_url, supabase_key)
            print(f"Supabase client initialized for bucket: {supabase_bucket}")
            # We don't try to create buckets - they should be created in the dashboard
        except Exception as e:
            print(f"Warning: Failed to initialize Supabase client: {str(e)}")
    else:
        print("Warning: Supabase environment variables not set. Storage functionality disabled.")

# Initialize on module import
init_supabase()

async def upload_file_to_supabase(file_path, file_name=None):
    """
    Upload a file to Supabase storage
    
    Args:
        file_path (str): Path to the file to upload
        file_name (str, optional): Custom filename for the uploaded file
                                  If None, will use the original filename
    
    Returns:
        dict: Response with file URL and metadata
    """
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    if not file_name:
        file_name = os.path.basename(file_path)
    
    # Generate a unique ID to prevent overwriting files with same name
    unique_id = str(uuid.uuid4())[:8]
    base_name, ext = os.path.splitext(file_name)
    unique_file_name = f"{base_name}_{unique_id}{ext}"
    
    # Place files in the 'public' subfolder to match RLS policy
    file_path_in_bucket = f"public/{unique_file_name}"
    
    # Read file contents
    with open(file_path, "rb") as f:
        file_contents = f.read()
    
    # Upload to Supabase
    response = supabase.storage.from_(supabase_bucket).upload(
        path=file_path_in_bucket,
        file=file_contents,
        file_options={"content-type": "audio/mpeg"}
    )
    
    # Generate public URL
    file_url = supabase.storage.from_(supabase_bucket).get_public_url(file_path_in_bucket)
    
    return {
        "success": True,
        "file_name": unique_file_name,
        "file_path": file_path_in_bucket,
        "file_url": file_url
    }

async def list_files_in_bucket():
    """List all files in the storage bucket"""
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    # List files in the 'public' folder to match RLS policy
    response = supabase.storage.from_(supabase_bucket).list("public")
    return response

async def delete_file_from_supabase(file_name):
    """Delete a file from Supabase storage"""
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    # Prepend 'public/' if the path doesn't already include it
    if not file_name.startswith("public/"):
        file_name = f"public/{file_name}"
    
    response = supabase.storage.from_(supabase_bucket).remove([file_name])
    return {
        "success": True,
        "message": f"File {file_name} deleted successfully",
        "response": response
    } 