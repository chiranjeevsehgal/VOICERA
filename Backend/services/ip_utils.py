from fastapi import Request
from typing import Optional


def get_client_ip(request: Request) -> str:
    """
    Extract the client's IP address from a request.

    Tries multiple methods to get the most accurate client IP:
    1. X-Forwarded-For header (for clients behind proxies/load balancers)
    2. X-Real-IP header (used by nginx and similar proxies)
    3. Direct client connection info

    Args:
        request: FastAPI Request object

    Returns:
        str: The client's IP address
    """
    # Check X-Forwarded-For header first (common for proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; first one is the client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (used by nginx and some other proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Checks for direct client info
    return request.client.host


async def get_ip_for_request(request: Request) -> str:
    """
    Function to get client IP for a route.

    Args:
        request: Request object

    Returns:
        str: The client's IP address
    """
    return get_client_ip(request)
