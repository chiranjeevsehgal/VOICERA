from typing import Dict, Any, Optional
import uuid
import time
from datetime import datetime

# In-memory storage for job tracking
# In production, this should be replaced with Redis or a database
jobs_store = {}

class JobStatus:
    """Status constants for jobs"""
    PENDING = "pending"
    CHECKING_CREDITS = "checking_credits"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    UPLOADING_TO_SUPABASE = "uploading_to_supabase"
    DEDUCTING_CREDITS = "deducting_credits"
    COMPLETED = "completed"
    FAILED = "failed"

def create_job() -> str:
    """Create a new job and return its ID"""
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "id": job_id,
        "status": JobStatus.PENDING,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "progress": 0,  # 0-100
        "result": None,
        "error": None,
        "steps_completed": [],
        "current_step": None,
        "steps_total": 6  # Total number of main steps in the process
    }
    return job_id

def update_job_status(job_id: str, status: str, progress: int = None, 
                      result: Dict[str, Any] = None, error: str = None,
                      current_step: str = None) -> bool:
    """Update a job's status and related information"""
    if job_id not in jobs_store:
        return False
    
    job = jobs_store[job_id]
    
    # Update status
    if status:
        job["status"] = status
        
        # If it's a step status, add to completed steps
        if status not in [JobStatus.PENDING, JobStatus.COMPLETED, JobStatus.FAILED]:
            if current_step and current_step not in job["steps_completed"]:
                job["current_step"] = current_step
    
    # Update progress if provided
    if progress is not None:
        job["progress"] = progress
    
    # Update result if provided
    if result is not None:
        job["result"] = result
    
    # Update error if provided
    if error is not None:
        job["error"] = error
    
    # Mark step as completed when moving to next step
    if current_step and job["current_step"] != current_step:
        if job["current_step"] and job["current_step"] not in job["steps_completed"]:
            job["steps_completed"].append(job["current_step"])
        job["current_step"] = current_step
    
    # Update timestamp
    job["updated_at"] = datetime.utcnow().isoformat()
    
    # Calculate progress percentage based on steps completed
    steps_completed = len(job["steps_completed"])
    if job["status"] == JobStatus.COMPLETED:
        job["progress"] = 100
    elif job["status"] == JobStatus.FAILED:
        # Keep progress as is when failed
        pass
    elif steps_completed > 0:
        # Calculate progress based on completed steps and partial progress in current step
        job["progress"] = min(99, int((steps_completed / job["steps_total"]) * 100))
    
    return True

def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the current status of a job"""
    if job_id not in jobs_store:
        return None
    
    # Return a copy to prevent modifications
    return jobs_store[job_id].copy()

def clean_old_jobs(max_age_seconds: int = 86400):
    """Clean up jobs older than the specified age (default: 24 hours)"""
    current_time = time.time()
    to_delete = []
    
    for job_id, job in jobs_store.items():
        created_time = datetime.fromisoformat(job["created_at"]).timestamp()
        if current_time - created_time > max_age_seconds:
            to_delete.append(job_id)
    
    for job_id in to_delete:
        del jobs_store[job_id]
        
    return len(to_delete)
