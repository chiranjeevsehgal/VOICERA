from fastapi import APIRouter, Request, Depends
from services.ip_utils import get_client_ip, get_ip_for_request

router = APIRouter()

@router.get("/ip-info")
async def get_ip_info(request: Request):
    """
    Endpoint for detailed IP detection.
    Returns client IP and request headers for debugging.
    """
    ip_address = get_client_ip(request)
    
    # Get all request headers
    headers = {key: value for key, value in request.headers.items()}
    
    return {
        "ip_address": ip_address,
        "request_headers": headers
    }

@router.get("/ip")
async def get_ip_info_dependency(client_ip: str = Depends(get_ip_for_request)):
    """
    Endpoint for IP detection.
    """
    return {
        "ip_address": client_ip
    }