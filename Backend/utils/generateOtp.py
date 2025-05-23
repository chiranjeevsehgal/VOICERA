# utils/otp_utils.py
import random
import time
from typing import Dict, Optional
from collections import defaultdict

# In-memory storage with email as key and (otp, expiry_time) as value
_otp_storage: Dict[str, tuple[str, float]] = {}
_last_cleanup_time: float = 0.0

def generate_otp(email: str, otp_length: int = 6, expiry_minutes: int = 10) -> str:
    """
    Generates an OTP, stores it with expiry time, and performs cleanup of expired OTPs
    
    Args:
        email: User's email address
        otp_length: Length of OTP to generate (default: 6)
        expiry_minutes: Minutes until OTP expires (default: 10)
    
    Returns:
        The generated OTP string
    """
    # Clean up expired OTPs before generating new one
    _cleanup_expired_otps()
    
    # Generate numeric OTP
    otp = ''.join([str(random.randint(0, 9)) for _ in range(otp_length)])
    
    # Store with expiry time (current time + expiry minutes in seconds)
    expiry_time = time.time() + (expiry_minutes * 60)
    _otp_storage[email] = (otp, expiry_time)
    
    return otp

def verify_otp(email: str, user_provided_otp: str) -> bool:
    """
    Verifies if the provided OTP matches the stored OTP for the email
    
    Args:
        email: User's email address
        user_provided_otp: OTP entered by user
    
    Returns:
        bool: True if valid, False otherwise
    """
    _cleanup_expired_otps()
    
    stored_data = _otp_storage.get(email)
    if not stored_data:
        return False
    
    stored_otp, _ = stored_data
    
    if stored_otp == user_provided_otp:
        return True
        
    return False

def _cleanup_expired_otps():
    """Remove expired OTPs from storage"""
    global _last_cleanup_time
    current_time = time.time()
    
    # Only run cleanup max once per minute to avoid performance hits
    if current_time - _last_cleanup_time < 60:
        return
    
    _last_cleanup_time = current_time
    expired_emails = [
        email for email, (_, expiry) in _otp_storage.items()
        if expiry < current_time
    ]
    
    for email in expired_emails:
        del _otp_storage[email]

def get_stored_otp(email: str) -> Optional[str]:
    """
    Get the active OTP for an email if exists and hasn't expired
    
    Args:
        email: User's email address
    
    Returns:
        str: The OTP if valid, None otherwise
    """
    _cleanup_expired_otps()
    stored_data = _otp_storage.get(email)
    return stored_data[0] if stored_data else None


def delete_otp(email : str):
    # OTP is correct, delete the record
    del _otp_storage[email]
    
    