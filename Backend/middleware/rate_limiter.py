import time
import os
from typing import Dict, Optional, Tuple, List
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Try to import Redis, but make it optional
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    logger.warning("Redis not available, using in-memory rate limiting")


class RateLimiter:
    """
    Rate limiter with sliding window algorithm
    Supports both Redis-backed and in-memory storage
    """

    def __init__(self, redis_client: Optional[object] = None):
        self.redis_client = redis_client if REDIS_AVAILABLE else None
        self.local_cache: Dict[str, Dict] = {}  # Fallback when Redis unavailable
        self.cleanup_interval = 300  # Clean local cache every 5 minutes
        self.last_cleanup = time.time()
        self.excluded_ips = self._load_excluded_ips()

    def _load_excluded_ips(self) -> List[str]:
        """
        Load excluded IPs from environment variable EXCLUDED_IPS
        Expected format: "IP1,IP2,IP3"
        
        Returns:
            List of IP addresses to exclude from rate limiting
        """
        excluded_ips_str = os.getenv("EXCLUDED_IPS", "")
        logger.info(f"Environment EXCLUDED_IPS value: '{excluded_ips_str}'")
        
        if not excluded_ips_str:
            logger.warning("No EXCLUDED_IPS environment variable found or it's empty")
            return []
        
        # Split by comma and strip whitespace
        excluded_ips = [ip.strip() for ip in excluded_ips_str.split(",") if ip.strip()]
        logger.info(f"Loaded {len(excluded_ips)} excluded IPs from environment: {excluded_ips}")
        return excluded_ips
    
    def _is_ip_excluded(self, ip: str) -> bool:
        """
        Check if an IP address is in the excluded list
        
        Args:
            ip: IP address to check
            
        Returns:
            True if IP should be excluded from rate limiting
        """
        return ip in self.excluded_ips
    
    def _extract_ip_from_key(self, key: str) -> Optional[str]:
        """
        Extract IP address from rate limit key
        Assumes key format like "ip:192.168.1.1" or similar
        
        Args:
            key: Rate limit key
            
        Returns:
            IP address if found, None otherwise
        """
        if ":" in key:
            parts = key.split(":")
            # Look for IP-like pattern in the key parts
            for part in parts:
                if self._looks_like_ip(part):
                    return part
        return None
    
    def _looks_like_ip(self, text: str) -> bool:
        """
        Simple check if text looks like an IP address
        
        Args:
            text: Text to check
            
        Returns:
            True if text appears to be an IP address
        """
        parts = text.split(".")
        if len(parts) != 4:
            return False
        
        try:
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            return True
        except ValueError:
            return False

    async def is_allowed(
        self, key: str, limit: int, window_seconds: int, identifier: str = "request"
    ) -> Tuple[bool, dict]:
        """
        Check if request is allowed using sliding window algorithm
        IPs in EXCLUDED_IPS environment variable will bypass rate limiting

        Args:
            key: Unique identifier for the rate limit (e.g., "ip:192.168.1.1")
            limit: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
            identifier: Description of what's being limited

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        # Check if this IP is excluded from rate limiting
        ip = self._extract_ip_from_key(key)
        logger.debug(f"Rate limit check - Key: '{key}', Extracted IP: '{ip}', Excluded IPs: {self.excluded_ips}")
        
        if ip and self._is_ip_excluded(ip):
            logger.info(f"IP {ip} is excluded from rate limiting - allowing unlimited access")
            return True, {
                "allowed": True,
                "limit": "unlimited",
                "remaining": "unlimited",
                "reset_time": None,
                "excluded": True,
                "window_seconds": window_seconds,
            }
        elif ip:
            logger.debug(f"IP {ip} is NOT in excluded list, applying rate limiting")
        
        current_time = time.time()
        window_start = current_time - window_seconds

        try:
            if self.redis_client:
                return await self._check_redis_limit(
                    key, limit, window_seconds, current_time, window_start
                )
            else:
                return await self._check_local_limit(
                    key, limit, window_seconds, current_time, window_start
                )
        except Exception as e:
            logger.error(f"Rate limiting check failed for {key}: {str(e)}")
            # Fallback to allow request if rate limiting fails
            return True, {
                "allowed": True,
                "limit": limit,
                "remaining": limit - 1,
                "reset_time": int(current_time + window_seconds),
                "error": f"Rate limiting check failed: {str(e)}",
            }

    async def _check_redis_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        current_time: float,
        window_start: float,
    ) -> Tuple[bool, dict]:
        """Check rate limit using Redis sorted sets"""
        try:
            pipe = self.redis_client.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current requests in window
            pipe.zcard(key)
            # Add current request timestamp
            pipe.zadd(key, {str(current_time): current_time})
            # Set expiration for cleanup
            pipe.expire(key, window_seconds + 1)

            results = await pipe.execute()
            current_requests = results[1]

            if current_requests < limit:
                return True, {
                    "allowed": True,
                    "limit": limit,
                    "remaining": limit - current_requests - 1,
                    "reset_time": int(current_time + window_seconds),
                    "window_seconds": window_seconds,
                }
            else:
                # Remove the request we just added since it's not allowed
                await self.redis_client.zrem(key, str(current_time))

                return False, {
                    "allowed": False,
                    "limit": limit,
                    "remaining": 0,
                    "reset_time": int(current_time + window_seconds),
                    "retry_after": window_seconds,
                    "window_seconds": window_seconds,
                }
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {str(e)}")
            # Fall back to local cache
            return await self._check_local_limit(
                key, limit, window_seconds, current_time, window_start
            )

    async def _check_local_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        current_time: float,
        window_start: float,
    ) -> Tuple[bool, dict]:
        """Check rate limit using local memory cache"""
        # Periodic cleanup of old entries
        if current_time - self.last_cleanup > self.cleanup_interval:
            await self._cleanup_local_cache()
            self.last_cleanup = current_time

        if key not in self.local_cache:
            self.local_cache[key] = {"requests": []}

        # Remove old requests outside the window
        self.local_cache[key]["requests"] = [
            req_time
            for req_time in self.local_cache[key]["requests"]
            if req_time > window_start
        ]

        current_requests = len(self.local_cache[key]["requests"])

        if current_requests < limit:
            self.local_cache[key]["requests"].append(current_time)
            return True, {
                "allowed": True,
                "limit": limit,
                "remaining": limit - current_requests - 1,
                "reset_time": int(current_time + window_seconds),
                "window_seconds": window_seconds,
            }
        else:
            return False, {
                "allowed": False,
                "limit": limit,
                "remaining": 0,
                "reset_time": int(current_time + window_seconds),
                "retry_after": window_seconds,
                "window_seconds": window_seconds,
            }

    async def _cleanup_local_cache(self):
        """Clean up expired entries from local cache"""
        current_time = time.time()
        keys_to_remove = []

        for key, data in self.local_cache.items():
            # Remove requests older than 1 hour
            data["requests"] = [
                req_time
                for req_time in data["requests"]
                if current_time - req_time < 3600
            ]

            # If no recent requests, mark key for removal
            if not data["requests"]:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.local_cache[key]

        logger.debug(f"Cleaned up {len(keys_to_remove)} expired rate limit entries")


# Rate limiting configurations
class RateLimitConfig:
    """Rate limiting configurations for different endpoints and user types"""

    # Per-endpoint limits (requests per minute)
    SEARCH_API = {"limit": 30, "window": 60}
    GENERATE_ANSWER_API = {"limit": 20, "window": 60}
    TRANSCRIBE_API = {"limit": 10, "window": 60}
    UPLOAD_API = {"limit": 5, "window": 60}
    PROCESS_AUDIO_API = {"limit": 3, "window": 60}

    # Per-user limits (requests per hour)
    USER_HOURLY = {"limit": 1000, "window": 3600}
    GUEST_HOURLY = {"limit": 100, "window": 3600}

    # Per-IP limits
    IP_MINUTE = {"limit": 100, "window": 60}
    IP_HOURLY = {"limit": 1000, "window": 3600}

    # Admin endpoints (more restrictive)
    ADMIN_API = {"limit": 50, "window": 60}


# Initialize global rate limiter
rate_limiter = None


def initialize_rate_limiter(redis_url: Optional[str] = None):
    """Initialize the global rate limiter with optional Redis support"""
    global rate_limiter

    redis_client = None
    if redis_url and REDIS_AVAILABLE:
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info("Rate limiter initialized with Redis backend")
        except Exception as e:
            logger.warning(
                f"Failed to connect to Redis, using in-memory rate limiting: {str(e)}"
            )

    rate_limiter = RateLimiter(redis_client)
    return rate_limiter


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance"""
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = RateLimiter()
    return rate_limiter


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, considering proxies"""
    # Check for forwarded headers (common in production behind proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client IP
    return request.client.host


def get_user_id(request: Request) -> Optional[str]:
    """Extract user ID from request state (set by auth middleware)"""
    return getattr(request.state, "user_id", None)


def get_user_role(request: Request) -> Optional[str]:
    """Extract user role from request state (set by auth middleware)"""
    return getattr(request.state, "user_role", "guest")


def get_endpoint_config(path: str) -> dict:
    """Get rate limit configuration for a specific endpoint"""
    # Map endpoints to their rate limit configs
    endpoint_configs = {
        "/search": RateLimitConfig.SEARCH_API,
        "/generate-answer": RateLimitConfig.GENERATE_ANSWER_API,
        "/search-and-answer": RateLimitConfig.GENERATE_ANSWER_API,
        "/transcribe": RateLimitConfig.TRANSCRIBE_API,
        "/upload": RateLimitConfig.UPLOAD_API,
        "/process_audio": RateLimitConfig.PROCESS_AUDIO_API,
        "/process_audio_bulk": RateLimitConfig.PROCESS_AUDIO_API,
    }

    # Check for admin endpoints
    if path.startswith("/admin"):
        return RateLimitConfig.ADMIN_API

    # Check exact matches first
    if path in endpoint_configs:
        return endpoint_configs[path]

    # Check for partial matches
    for endpoint, config in endpoint_configs.items():
        if path.startswith(endpoint):
            return config

    # Default rate limit for other endpoints
    return {"limit": 60, "window": 60}


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware for rate limiting"""

    # Skip rate limiting for health checks and static files
    if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)

    limiter = get_rate_limiter()
    client_ip = get_client_ip(request)
    user_id = get_user_id(request)
    user_role = get_user_role(request)
    endpoint = request.url.path

    try:
        # 1. Check IP-based rate limit (primary protection)
        ip_allowed, ip_info = await limiter.is_allowed(
            f"ip:{client_ip}",
            RateLimitConfig.IP_MINUTE["limit"],
            RateLimitConfig.IP_MINUTE["window"],
            "IP per minute",
        )

        if not ip_allowed:
            logger.warning(f"IP rate limit exceeded for {client_ip} on {endpoint}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "type": "ip_limit",
                    "message": f"Too many requests from IP {client_ip}",
                    **{k: v for k, v in ip_info.items() if k != "allowed"},
                },
                headers=_get_rate_limit_headers(ip_info),
            )

        # 2. Check user-based rate limit (if authenticated)
        if user_id:
            user_limit_config = (
                RateLimitConfig.GUEST_HOURLY
                if user_role == "guest"
                else RateLimitConfig.USER_HOURLY
            )
            user_allowed, user_info = await limiter.is_allowed(
                f"user:{user_id}",
                user_limit_config["limit"],
                user_limit_config["window"],
                "User per hour",
            )

            if not user_allowed:
                logger.warning(
                    f"User rate limit exceeded for user {user_id} on {endpoint}"
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "User rate limit exceeded",
                        "type": "user_limit",
                        "message": f"Too many requests for user",
                        **{k: v for k, v in user_info.items() if k != "allowed"},
                    },
                    headers=_get_rate_limit_headers(user_info),
                )

        # 3. Check endpoint-specific rate limit
        endpoint_config = get_endpoint_config(endpoint)
        endpoint_key = (
            f"endpoint:{client_ip}:{endpoint}"
            if not user_id
            else f"endpoint:{user_id}:{endpoint}"
        )

        endpoint_allowed, endpoint_info = await limiter.is_allowed(
            endpoint_key,
            endpoint_config["limit"],
            endpoint_config["window"],
            f"Endpoint {endpoint}",
        )

        if not endpoint_allowed:
            logger.warning(f"Endpoint rate limit exceeded for {endpoint_key}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Endpoint rate limit exceeded",
                    "type": "endpoint_limit",
                    "message": f"Too many requests to {endpoint}",
                    **{k: v for k, v in endpoint_info.items() if k != "allowed"},
                },
                headers=_get_rate_limit_headers(endpoint_info),
            )

        # All rate limits passed, process the request
        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers.update(
            _get_rate_limit_headers(ip_info, prefix="X-RateLimit-IP")
        )
        if user_id:
            response.headers.update(
                _get_rate_limit_headers(endpoint_info, prefix="X-RateLimit-Endpoint")
            )

        return response

    except Exception as e:
        logger.error(f"Rate limiting middleware error: {str(e)}")
        # If rate limiting fails, allow the request to proceed
        return await call_next(request)


def _get_rate_limit_headers(rate_info: dict, prefix: str = "X-RateLimit") -> dict:
    """Generate rate limit headers for HTTP response"""
    headers = {}

    if "limit" in rate_info:
        headers[f"{prefix}-Limit"] = str(rate_info["limit"])
    if "remaining" in rate_info:
        headers[f"{prefix}-Remaining"] = str(rate_info["remaining"])
    if "reset_time" in rate_info:
        headers[f"{prefix}-Reset"] = str(rate_info["reset_time"])
    if "retry_after" in rate_info:
        headers["Retry-After"] = str(int(rate_info["retry_after"]))

    return headers


class RateLimitDecorator:
    """Decorator for applying rate limits to specific functions"""

    def __init__(self, limit: int, window: int, key_func: callable = None):
        self.limit = limit
        self.window = window
        self.key_func = key_func or (lambda *args, **kwargs: "default")

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            key = self.key_func(*args, **kwargs)

            allowed, info = await limiter.is_allowed(key, self.limit, self.window)

            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for " + func.__name__,
                    headers=_get_rate_limit_headers(info),
                )

            return await func(*args, **kwargs)

        return wrapper
