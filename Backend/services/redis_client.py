import os
import time
import logging
from typing import Optional, Dict, Any

# Try to import redis (async and sync). Keep optional.
try:
    import redis.asyncio as redis_async  # type: ignore
    ASYNC_AVAILABLE = True
except Exception:  # ImportError or other
    redis_async = None  # type: ignore
    ASYNC_AVAILABLE = False

try:
    import redis as redis_sync  # type: ignore
    SYNC_AVAILABLE = True
except Exception:
    redis_sync = None  # type: ignore
    SYNC_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
DEFAULT_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
DEFAULT_SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))


def _normalized_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url.strip() or None


def get_async_client(url: Optional[str] = None,
                     max_connections: Optional[int] = None,
                     socket_timeout: Optional[float] = None,
                     socket_connect_timeout: Optional[float] = None):
    """
    Return an async Redis client if the async redis package is available and URL is provided.
    Otherwise returns None.
    """
    url = _normalized_url(url) or _normalized_url(os.getenv("REDIS_URL"))
    if not (ASYNC_AVAILABLE and url):
        return None

    try:
        client = redis_async.from_url(
            url,
            decode_responses=True,
            max_connections=max_connections or DEFAULT_MAX_CONNECTIONS,
            socket_timeout=socket_timeout or DEFAULT_SOCKET_TIMEOUT,
            socket_connect_timeout=socket_connect_timeout or DEFAULT_SOCKET_CONNECT_TIMEOUT,
        )
        return client
    except Exception as e:
        logger.warning(f"Failed to create async Redis client: {e}")
        return None


def get_sync_client(url: Optional[str] = None,
                    max_connections: Optional[int] = None,
                    socket_timeout: Optional[float] = None,
                    socket_connect_timeout: Optional[float] = None):
    """
    Return a sync Redis client if the redis package is available and URL is provided.
    Otherwise returns None.
    """
    url = _normalized_url(url) or _normalized_url(os.getenv("REDIS_URL"))
    if not (SYNC_AVAILABLE and url):
        return None

    try:
        pool = redis_sync.ConnectionPool.from_url(
            url,
            max_connections=max_connections or DEFAULT_MAX_CONNECTIONS,
            socket_timeout=socket_timeout or DEFAULT_SOCKET_TIMEOUT,
            socket_connect_timeout=socket_connect_timeout or DEFAULT_SOCKET_CONNECT_TIMEOUT,
            decode_responses=True,
        )
        client = redis_sync.Redis(connection_pool=pool)
        return client
    except Exception as e:
        logger.warning(f"Failed to create sync Redis client: {e}")
        return None


async def check_redis_health_async(client) -> Dict[str, Any]:
    """Ping an async redis client and return health details."""
    try:
        start = time.perf_counter()
        pong = await client.ping()
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {"healthy": bool(pong), "latency_ms": round(latency_ms, 2)}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


def check_redis_health_sync(client) -> Dict[str, Any]:
    """Ping a sync redis client and return health details."""
    try:
        start = time.perf_counter()
        pong = client.ping()
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {"healthy": bool(pong), "latency_ms": round(latency_ms, 2)}
    except Exception as e:
        return {"healthy": False, "error": str(e)}


def is_async_available() -> bool:
    return ASYNC_AVAILABLE


def is_sync_available() -> bool:
    return SYNC_AVAILABLE
