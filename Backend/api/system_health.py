from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from services.auth import requires_role
from services.circuit_breaker import (
    get_all_circuit_breakers,
    reset_all_circuit_breakers,
)
from middleware.rate_limiter import get_rate_limiter
import logging
from services.redis_client import check_redis_health_async, get_async_client
import time

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/system/health", status_code=status.HTTP_200_OK)
async def get_system_health(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
):
    """
    Get comprehensive system health including circuit breakers and rate limiting status
    """
    try:
        # Get all circuit breakers status
        circuit_breakers = get_all_circuit_breakers()
        circuit_status = {}

        for name, breaker in circuit_breakers.items():
            circuit_status[name] = breaker.get_state()

        # Get rate limiter status
        rate_limiter = get_rate_limiter()
        rate_limiter_status = {
            "backend": "Redis" if rate_limiter.redis_client else "In-Memory",
            "cache_size": len(rate_limiter.local_cache)
            if not rate_limiter.redis_client
            else "N/A",
        }

        # Redis health (if available via rate limiter)
        redis_health = {"available": False}
        if getattr(rate_limiter, "redis_client", None):
            try:
                health = await check_redis_health_async(rate_limiter.redis_client)
                redis_health = {"available": True, **health}
            except Exception as e:
                redis_health = {"available": True, "healthy": False, "error": str(e)}

        return {
            "status": "healthy",
            "circuit_breakers": circuit_status,
            "rate_limiter": rate_limiter_status,
            "redis": redis_health,
            "total_circuit_breakers": len(circuit_breakers),
        }

    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving system health: {str(e)}",
        )


@router.get("/system/circuit-breakers", status_code=status.HTTP_200_OK)
async def get_circuit_breakers_status(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
):
    """
    Get detailed status of all circuit breakers
    """
    try:
        circuit_breakers = get_all_circuit_breakers()
        detailed_status = {}

        for name, breaker in circuit_breakers.items():
            detailed_status[name] = breaker.get_state()

        return {
            "circuit_breakers": detailed_status,
            "summary": {
                "total": len(circuit_breakers),
                "open": sum(
                    1 for cb in circuit_breakers.values() if cb.state.value == "open"
                ),
                "closed": sum(
                    1 for cb in circuit_breakers.values() if cb.state.value == "closed"
                ),
                "half_open": sum(
                    1
                    for cb in circuit_breakers.values()
                    if cb.state.value == "half_open"
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error getting circuit breakers status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving circuit breakers status: {str(e)}",
        )


@router.post("/system/circuit-breakers/reset", status_code=status.HTTP_200_OK)
async def reset_circuit_breakers(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
):
    """
    Reset all circuit breakers to CLOSED state
    """
    try:
        await reset_all_circuit_breakers()

        logger.info(
            f"All circuit breakers reset by admin user: {current_user.get('email', 'unknown')}"
        )

        return {
            "status": "success",
            "message": "All circuit breakers have been reset to CLOSED state",
            "reset_by": current_user.get("email", "unknown"),
        }

    except Exception as e:
        logger.error(f"Error resetting circuit breakers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resetting circuit breakers: {str(e)}",
        )


@router.get("/system/rate-limits", status_code=status.HTTP_200_OK)
async def get_rate_limit_info(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
):
    """
    Get rate limiting configuration and current status
    """
    try:
        from middleware.rate_limiter import RateLimitConfig

        config_info = {
            "endpoint_limits": {
                "search_api": RateLimitConfig.SEARCH_API,
                "transcribe_api": RateLimitConfig.TRANSCRIBE_API,
                "upload_api": RateLimitConfig.UPLOAD_API,
                "process_audio_api": RateLimitConfig.PROCESS_AUDIO_API,
                "admin_api": RateLimitConfig.ADMIN_API,
            },
            "user_limits": {
                "user_hourly": RateLimitConfig.USER_HOURLY,
                "guest_hourly": RateLimitConfig.GUEST_HOURLY,
            },
            "ip_limits": {
                "ip_minute": RateLimitConfig.IP_MINUTE,
                "ip_hourly": RateLimitConfig.IP_HOURLY,
            },
        }

        rate_limiter = get_rate_limiter()
        limiter_status = {
            "backend": "Redis" if rate_limiter.redis_client else "In-Memory",
            "local_cache_entries": len(rate_limiter.local_cache)
            if not rate_limiter.redis_client
            else "N/A",
        }

        return {"configuration": config_info, "limiter_status": limiter_status}

    except Exception as e:
        logger.error(f"Error getting rate limit info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving rate limit info: {str(e)}",
        )


@router.get("/system/redis-ping", status_code=status.HTTP_200_OK)
async def redis_ping(
    current_user: Dict[str, Any] = Depends(requires_role("admin")),
):
    """
    Simple Redis ping/pong endpoint to verify connectivity and measure latency.
    Tries the rate limiter's Redis client first, then falls back to creating one
    from REDIS_URL via services.redis_client.get_async_client().
    """
    try:
        rate_limiter = get_rate_limiter()
        client = getattr(rate_limiter, "redis_client", None)
        if client is None:
            client = get_async_client()

        if not client:
            return {
                "available": False,
                "healthy": False,
                "error": "Redis client not configured",
            }

        start = time.perf_counter()
        pong = await client.ping()
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {
            "available": True,
            "healthy": bool(pong),
            "pong": pong,
            "latency_ms": round(latency_ms, 2),
        }
    except Exception as e:
        return {"available": True, "healthy": False, "error": str(e)}
