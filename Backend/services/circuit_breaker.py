import asyncio
import time
from enum import Enum
from typing import Callable, Any, Dict, Optional
from dataclasses import dataclass
import logging
import json
from services.redis_client import get_sync_client
logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    timeout: float = 30.0
    expected_exception: tuple = (Exception,)

class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and blocking requests"""
    pass

class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance

    States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Blocking all requests, service assumed down
    - HALF_OPEN: Testing recovery with limited requests
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_success_time = 0.0
        self.lock = asyncio.Lock()
        self.stats = {'total_requests': 0, 'successful_requests': 0, 'failed_requests': 0, 'circuit_opens': 0, 'circuit_closes': 0}
        try:
            self._redis = get_sync_client()
        except Exception:
            self._redis = None

    def _redis_enabled(self) -> bool:
        return getattr(self, '_redis', None) is not None

    def _rkey(self) -> str:
        return f'cb:{self.name}'

    def _persist_state(self, reason: str='update') -> None:
        if not self._redis_enabled():
            return
        try:
            payload = {'name': self.name, 'state': self.state.value, 'failure_count': self.failure_count, 'success_count': self.success_count, 'last_failure_time': self.last_failure_time, 'last_success_time': self.last_success_time, 'stats_total_requests': self.stats.get('total_requests', 0), 'stats_successful_requests': self.stats.get('successful_requests', 0), 'stats_failed_requests': self.stats.get('failed_requests', 0), 'stats_circuit_opens': self.stats.get('circuit_opens', 0), 'stats_circuit_closes': self.stats.get('circuit_closes', 0), 'updated_at': int(time.time()), 'reason': reason}
            self._redis.hset(self._rkey(), mapping=payload)
            self._redis.expire(self._rkey(), 86400)
            try:
                self._redis.publish('cb:events', json.dumps({'breaker': self.name, 'state': self.state.value, 'reason': reason, 'ts': int(time.time())}))
            except Exception:
                pass
        except Exception:
            pass

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection

        Args:
            func: The async function to call
            *args, **kwargs: Arguments to pass to func

        Returns:
            Result of function call

        Raises:
            CircuitBreakerError: If circuit is open
            Original exception: If function fails and circuit allows it
        """
        self.stats['total_requests'] += 1
        async with self.lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN for recovery test")
                else:
                    logger.warning(f"Circuit breaker '{self.name}' is OPEN, blocking request")
                    raise CircuitBreakerError(f"Circuit breaker '{self.name}' is open")
            if self.state == CircuitState.HALF_OPEN:
                pass
        try:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
            await self._on_success()
            return result
        except asyncio.TimeoutError as e:
            logger.error(f"Circuit breaker '{self.name}' - request timeout after {self.config.timeout}s")
            await self._on_failure()
            raise e
        except self.config.expected_exception as e:
            logger.warning(f"Circuit breaker '{self.name}' - expected failure: {str(e)}")
            await self._on_failure()
            raise e

    async def _on_success(self):
        """Handle successful request"""
        async with self.lock:
            self.stats['successful_requests'] += 1
            self.last_success_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(f"Circuit breaker '{self.name}' - success {self.success_count}/{self.config.success_threshold} in HALF_OPEN")
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.stats['circuit_closes'] += 1
                    logger.info(f"Circuit breaker '{self.name}' closed - service recovered")
                    self._persist_state(reason='closed')
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0
                self._persist_state(reason='success')

    async def _on_failure(self):
        """Handle failed request"""
        async with self.lock:
            self.stats['failed_requests'] += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.warning(f"Circuit breaker '{self.name}' - failure {self.failure_count}/{self.config.failure_threshold}")
            if self.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN] and self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                self.stats['circuit_opens'] += 1
                logger.error(f"Circuit breaker '{self.name}' opened after {self.failure_count} failures")
                self._persist_state(reason='opened')
            else:
                self._persist_state(reason='failure')

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state and statistics"""
        return {'name': self.name, 'state': self.state.value, 'failure_count': self.failure_count, 'success_count': self.success_count, 'last_failure_time': self.last_failure_time, 'last_success_time': self.last_success_time, 'config': {'failure_threshold': self.config.failure_threshold, 'recovery_timeout': self.config.recovery_timeout, 'success_threshold': self.config.success_threshold, 'timeout': self.config.timeout}, 'stats': self.stats.copy()}

    async def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        async with self.lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")
            self._persist_state(reason='manual_reset')
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig]=None) -> CircuitBreaker:
    """
    Get or create a circuit breaker instance

    Args:
        name: Unique identifier for the circuit breaker
        config: Configuration for the circuit breaker (only used on first creation)

    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig()
        _circuit_breakers[name] = CircuitBreaker(name, config)
        logger.info(f"Created new circuit breaker '{name}' with config: {config}")
    return _circuit_breakers[name]

def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers"""
    return _circuit_breakers.copy()

async def reset_all_circuit_breakers():
    """Reset all circuit breakers to CLOSED state"""
    for breaker in _circuit_breakers.values():
        await breaker.reset()

class ServiceCircuitBreakers:
    """Pre-configured circuit breakers for external services"""

    @staticmethod
    def get_gemini_breaker() -> CircuitBreaker:
        """Circuit breaker for Gemini AI API"""
        return get_circuit_breaker('gemini_api', CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0, success_threshold=2, timeout=60.0, expected_exception=(Exception,)))

    @staticmethod
    def get_deepgram_breaker() -> CircuitBreaker:
        """Circuit breaker for Deepgram transcription API"""
        return get_circuit_breaker('deepgram_api', CircuitBreakerConfig(failure_threshold=3, recovery_timeout=60.0, success_threshold=2, timeout=120.0, expected_exception=(Exception,)))

    @staticmethod
    def get_pinecone_breaker() -> CircuitBreaker:
        """Circuit breaker for Pinecone vector database"""
        return get_circuit_breaker('pinecone_api', CircuitBreakerConfig(failure_threshold=2, recovery_timeout=20.0, success_threshold=1, timeout=30.0, expected_exception=(Exception,)))

    @staticmethod
    def get_mongodb_breaker() -> CircuitBreaker:
        """Circuit breaker for MongoDB operations"""
        return get_circuit_breaker('mongodb', CircuitBreakerConfig(failure_threshold=2, recovery_timeout=10.0, success_threshold=1, timeout=15.0, expected_exception=(Exception,)))

def circuit_breaker_decorator(name: str, config: Optional[CircuitBreakerConfig]=None):
    """
    Decorator to add circuit breaker protection to async functions

    Usage:
        @circuit_breaker_decorator("my_service")
        async def call_external_api():
            # API call logic here
            pass
    """

    def decorator(func: Callable):
        breaker = get_circuit_breaker(name, config)

        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator