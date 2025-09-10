from fastapi import Request
from typing import Optional
import os


def get_client_ip(request: Request) -> str:
    """
    Extract the client's IP address from a request.

    Tries multiple methods to get the most accurate client IP:
    1. CF-Connecting-IP / True-Client-IP (CDNs e.g., Cloudflare/Akamai)
    2. Forwarded (RFC 7239) header
    3. X-Forwarded-For header (prefer the first public IP)
    4. X-Real-IP header (used by nginx and similar proxies)
    5. Direct client connection info

    Args:
        request: FastAPI Request object

    Returns:
        str: The client's IP address
    """
    headers = request.headers

    # 0) Optional: trust client-provided header when explicitly enabled (for dev or controlled env)
    if os.getenv("TRUST_CLIENT_IP_HEADER", "false").lower() in {"1", "true", "yes"}:
        client_ip_header = headers.get("X-Client-IP")
        # Optional shared secret to avoid abuse in shared networks
        expected_token = os.getenv("CLIENT_IP_HEADER_TOKEN")
        provided_token = headers.get("X-Client-IP-Token")
        if expected_token:
            if provided_token and provided_token == expected_token and client_ip_header:
                return client_ip_header.strip()
        else:
            if client_ip_header:
                return client_ip_header.strip()

    def _clean(ip: Optional[str]) -> Optional[str]:
        if not ip:
            return None
        return ip.strip().strip("\"[]")

    def _is_private_ipv4(ip: str) -> bool:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            a, b, c, d = [int(p) for p in parts]
        except ValueError:
            return False
        if a == 10:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 127:
            return True
        return False

    def _is_private_or_loopback(ip: str) -> bool:
        ip = ip.lower()
        if ":" in ip:  # rudimentary IPv6 checks
            return ip == "::1" or ip.startswith("fc") or ip.startswith("fd") or ip.startswith("fe80")
        return _is_private_ipv4(ip)

    # 1) CDN-provided real client headers
    for h in ("CF-Connecting-IP", "True-Client-IP"):
        v = _clean(headers.get(h))
        if v:
            return v

    # 2) RFC 7239 Forwarded: for=1.2.3.4, proto=https; by=...
    fwd = headers.get("Forwarded")
    if fwd:
        try:
            # Split by commas for multiple entries, take first 'for'
            first = fwd.split(",")[0]
            for part in first.split(";"):
                part = part.strip()
                if part.lower().startswith("for="):
                    candidate = _clean(part.split("=", 1)[1])
                    # Remove optional quotes and possible obfuscated identifiers
                    if candidate and candidate.lower() != "unknown":
                        # Strip optional IP:port
                        if candidate.startswith("\"") and candidate.endswith("\""):
                            candidate = candidate[1:-1]
                        if candidate.startswith("[") and "]" in candidate:
                            candidate = candidate[1:candidate.index("]")]
                        if candidate and candidate != "unknown":
                            return candidate.split(":")[0]
        except Exception:
            pass

    # 3) X-Forwarded-For: pick first public IP, otherwise first
    xff = headers.get("X-Forwarded-For")
    if xff:
        candidates = [c.strip() for c in xff.split(",") if c.strip()]
        for ip in candidates:
            if not _is_private_or_loopback(ip):
                return ip
        # Fall back to the first if none are public
        if candidates:
            return candidates[0]

    # 4) X-Real-IP
    real_ip = _clean(headers.get("X-Real-IP"))
    if real_ip:
        return real_ip

    # 5) Fallback to direct client
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
