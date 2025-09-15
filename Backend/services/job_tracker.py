from typing import Dict, Any, Optional
import uuid
import time
from datetime import datetime
jobs_store = {}

class JobStatus:
    """Status constants for jobs"""
    PENDING = 'pending'
    CHECKING_CREDITS = 'checking_credits'
    UPLOADING = 'uploading'
    TRANSCRIBING = 'transcribing'
    EMBEDDING = 'embedding'
    INDEXING = 'indexing'
    UPLOADING_TO_SUPABASE = 'uploading_to_supabase'
    DEDUCTING_CREDITS = 'deducting_credits'
    COMPLETED = 'completed'
    FAILED = 'failed'

def create_job() -> str:
    """Create a new job and return its ID"""
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {'id': job_id, 'status': JobStatus.PENDING, 'created_at': datetime.utcnow().isoformat(), 'updated_at': datetime.utcnow().isoformat(), 'progress': 0, 'result': None, 'error': None, 'steps_completed': [], 'current_step': None, 'steps_total': 6}
    return job_id

def update_job_status(job_id: str, status: str, progress: int=None, result: Dict[str, Any]=None, error: str=None, current_step: str=None) -> bool:
    """Update a job's status and related information"""
    if job_id not in jobs_store:
        return False
    job = jobs_store[job_id]
    if status:
        job['status'] = status
        if status not in [JobStatus.PENDING, JobStatus.COMPLETED, JobStatus.FAILED]:
            if current_step and current_step not in job['steps_completed']:
                job['current_step'] = current_step
    if progress is not None:
        job['progress'] = progress
    if result is not None:
        job['result'] = result
    if error is not None:
        job['error'] = error
    if current_step and job['current_step'] != current_step:
        if job['current_step'] and job['current_step'] not in job['steps_completed']:
            job['steps_completed'].append(job['current_step'])
        job['current_step'] = current_step
    job['updated_at'] = datetime.utcnow().isoformat()
    steps_completed = len(job['steps_completed'])
    if job['status'] == JobStatus.COMPLETED:
        job['progress'] = 100
    elif job['status'] == JobStatus.FAILED:
        pass
    elif steps_completed > 0:
        job['progress'] = min(99, int(steps_completed / job['steps_total'] * 100))
    return True

def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the current status of a job"""
    if job_id not in jobs_store:
        return None
    return jobs_store[job_id].copy()

def clean_old_jobs(max_age_seconds: int=86400):
    """Clean up jobs older than the specified age (default: 24 hours)"""
    current_time = time.time()
    to_delete = []
    for job_id, job in jobs_store.items():
        created_time = datetime.fromisoformat(job['created_at']).timestamp()
        if current_time - created_time > max_age_seconds:
            to_delete.append(job_id)
    for job_id in to_delete:
        del jobs_store[job_id]
    return len(to_delete)