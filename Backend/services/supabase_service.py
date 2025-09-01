import os
from supabase import create_client, Client
from dotenv import load_dotenv
import uuid
from datetime import datetime
from models.user_uploads import UserUploadCreate
from bson import ObjectId
import json
from services.database import users_collection  # Add this import

# Load environment variables
load_dotenv()

# Supabase configuration
supabase_url = os.getenv("SUPABASE_URL")
# Prefer service role key on the server to bypass RLS
supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_key = supabase_service_role_key or os.getenv("SUPABASE_KEY")
supabase_bucket = os.getenv("SUPABASE_BUCKET", "audiofiles")
# Optional specialized buckets (fallback to SUPABASE_BUCKET if not set)
supabase_bucket_original = os.getenv("SUPABASE_BUCKET_ORIGINAL", supabase_bucket)
supabase_bucket_embedded = os.getenv("SUPABASE_BUCKET_EMBEDDED", supabase_bucket)

# Initialize Supabase client
supabase: Client = None

def init_supabase():
    """Initialize Supabase client if environment variables are set"""
    global supabase
    if supabase_url and supabase_key:
        try:
            supabase = create_client(supabase_url, supabase_key)
            key_mode = "service-role" if supabase_service_role_key else "standard"
            print(f"Supabase client initialized ({key_mode} key). Default bucket: {supabase_bucket}; original: {supabase_bucket_original}; embedded: {supabase_bucket_embedded}")
            # We don't try to create buckets - they should be created in the dashboard
        except Exception as e:
            print(f"Warning: Failed to initialize Supabase client: {str(e)}")
    else:
        print("Warning: Supabase environment variables not set. Storage functionality disabled.")

# Initialize on module import
init_supabase()

async def upload_file_to_supabase(file_path, file_name=None, user_id=None, bucket_name: str = None):
    """
    Upload a file to Supabase storage and track user ownership
    
    Args:
        file_path (str): Path to the file to upload
        file_name (str, optional): Custom filename for the uploaded file
        user_id (str/ObjectId, optional): ID of the user uploading the file
    
    Returns:
        dict: Response with file URL and metadata
    """
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    print(f"[DEBUG] Starting upload process with user_id: {user_id}, type: {type(user_id)}")
    
    if not file_name:
        file_name = os.path.basename(file_path)
    
    # Generate a unique ID to prevent overwriting files with same name
    unique_id = str(uuid.uuid4())[:8]
    base_name, ext = os.path.splitext(file_name)
    unique_file_name = f"{base_name}_{unique_id}{ext}"
    
    # Place files in the 'public' subfolder to match RLS policy
    file_path_in_bucket = f"public/{unique_file_name}"
    # Select bucket
    selected_bucket = bucket_name or supabase_bucket
    
    try:
        # Read file contents
        with open(file_path, "rb") as f:
            file_contents = f.read()
        
        print(f"[DEBUG] File read successfully: {file_path}")
        
        # Upload to Supabase
        response = supabase.storage.from_(selected_bucket).upload(
            path=file_path_in_bucket,
            file=file_contents,
            file_options={"content-type": "audio/mpeg"}
        )
        
        print(f"[DEBUG] Storage upload response: {response}")
        
        # Generate public URL
        file_url = supabase.storage.from_(selected_bucket).get_public_url(file_path_in_bucket)
        
        result = {
            "success": True,
            "file_name": unique_file_name,
            "file_path": file_path_in_bucket,
            "file_url": file_url,
            "bucket": selected_bucket
        }

        # If user_id is provided, track the upload in the database
        if user_id:
            print(f"[DEBUG] Processing user_id: {user_id}, type: {type(user_id)}")
            
            # Convert MongoDB ObjectId to string if needed
            if isinstance(user_id, ObjectId):
                user_id = str(user_id)
            elif isinstance(user_id, dict) and '_id' in user_id:
                user_id = str(user_id['_id'])
            
            try:
                upload_data = {
                    "user_id": user_id,
                    "file_name": unique_file_name,
                    "file_path": file_path_in_bucket,
                    "file_url": file_url,
                    "metadata": {}
                }
                
                print(f"[DEBUG] Attempting to insert user_upload data: {json.dumps(upload_data, default=str)}")
                
                # Insert into user_uploads table
                db_response = supabase.table("user_uploads").insert(upload_data).execute()
                print(f"[DEBUG] Database insert response: {json.dumps(db_response.data if db_response.data else 'No data', default=str)}")
                
                if db_response.data:
                    result["user_upload"] = db_response.data[0]
                    print("[DEBUG] Successfully recorded user upload")
                else:
                    print("[DEBUG] Warning: No data returned from user_uploads insert")
                    result["user_upload_warning"] = "No data returned from insert"
            except Exception as e:
                print(f"[DEBUG] Failed to record user upload: {str(e)}")
                result["user_upload_error"] = str(e)

        return result
        
    except Exception as e:
        print(f"[DEBUG] Upload failed with error: {str(e)}")
        raise ValueError(f"Failed to upload file: {str(e)}")

async def list_files_in_bucket(user_id=None, bucket_name: str = None, folder: str = "public"):
    """
    List files in the storage bucket with user information
    
    Args:
        user_id (str, optional): If provided, only list files uploaded by this user
    """
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    try:
        selected_bucket = bucket_name or supabase_bucket
        # Get storage files
        storage_files = supabase.storage.from_(selected_bucket).list(folder)
        
        # Get user upload records
        query = supabase.table("user_uploads").select("*")
        if user_id:
            # Convert ObjectId to string if needed
            if isinstance(user_id, ObjectId):
                user_id = str(user_id)
            elif isinstance(user_id, dict) and '_id' in user_id:
                user_id = str(user_id['_id'])
            query = query.eq("user_id", user_id)
        
        user_uploads = query.execute()
        
        # Create a mapping of file_name to user data
        user_upload_map = {}
        if user_uploads.data:
            for upload in user_uploads.data:
                # Get user details from MongoDB
                try:
                    user_obj_id = ObjectId(upload["user_id"])
                    user = await users_collection.find_one({"_id": user_obj_id})
                    if user:
                        # Add user details to the upload data
                        upload["user_details"] = {
                            "email": user.get("email"),
                            "full_name": user.get("full_name"),
                            # Add any other user fields you want to include
                        }
                except Exception as e:
                    print(f"[DEBUG] Failed to get user details for {upload['user_id']}: {str(e)}")
                    upload["user_details"] = {"error": "User not found"}
                
                user_upload_map[upload["file_name"]] = upload
        
        # Combine storage files with user data
        enriched_files = []
        for file in storage_files:
            file_data = dict(file)  # Create a new dict to avoid modifying the original
            if file["name"] in user_upload_map:
                file_data["user_data"] = user_upload_map[file["name"]]
            enriched_files.append(file_data)
        
        return enriched_files
        
    except Exception as e:
        print(f"[DEBUG] Error listing files: {str(e)}")
        return []

async def delete_file_from_supabase(file_name, bucket_name: str = None):
    """Delete a file from Supabase storage"""
    if not supabase:
        raise ValueError("Supabase client not initialized. Check your environment variables.")
    
    # Prepend 'public/' if the path doesn't already include it
    if not file_name.startswith("public/"):
        file_name = f"public/{file_name}"
    
    selected_bucket = bucket_name or supabase_bucket
    response = supabase.storage.from_(selected_bucket).remove([file_name])
    return {
        "success": True,
        "message": f"File {file_name} deleted successfully",
        "response": response
    }