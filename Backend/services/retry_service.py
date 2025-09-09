import asyncio
import random
from typing import Callable, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class RetryConfig:
    """Configuration for retry behavior"""
    def __init__(
        self, 
        max_attempts: int = 3, 
        base_delay: float = 1.0, 
        max_delay: float = 60.0, 
        jitter: bool = True,
        backoff_multiplier: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.backoff_multiplier = backoff_multiplier

async def async_retry_with_backoff(
    func: Callable,
    config: RetryConfig,
    exceptions: tuple = (Exception,),
    *args,
    **kwargs
) -> Any:
    """
    Async retry with exponential backoff and jitter
    
    Args:
        func: The async function to retry
        config: Retry configuration
        exceptions: Tuple of exceptions to retry on
        *args, **kwargs: Arguments to pass to func
        
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry succeeded for {func.__name__} on attempt {attempt + 1}")
            return result
            
        except exceptions as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                logger.error(f"All {config.max_attempts} retry attempts failed for {func.__name__}: {str(e)}")
                raise e
            
            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.backoff_multiplier ** attempt), 
                config.max_delay
            )
            
            # Add jitter to prevent thundering herd
            if config.jitter:
                delay *= (0.5 + random.random())
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed for {func.__name__}, "
                f"retrying in {delay:.2f}s: {str(e)}"
            )
            await asyncio.sleep(delay)
    
    # This shouldn't be reached, but just in case
    if last_exception:
        raise last_exception

def retry_decorator(
    config: RetryConfig = None, 
    exceptions: tuple = (Exception,)
):
    """
    Decorator for automatic retry with exponential backoff
    
    Args:
        config: RetryConfig instance, defaults to RetryConfig()
        exceptions: Tuple of exceptions to retry on
        
    Usage:
        @retry_decorator(
            config=RetryConfig(max_attempts=3, base_delay=1.0),
            exceptions=(RequestException, ConnectionError)
        )
        async def my_api_call():
            # API call logic here
            pass
    """
    if config is None:
        config = RetryConfig()
        
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await async_retry_with_backoff(func, config, exceptions, *args, **kwargs)
        return wrapper
    return decorator

# Pre-configured retry configs for common scenarios
class CommonRetryConfigs:
    """Pre-configured retry settings for common use cases"""
    
    # For external API calls (Gemini, Deepgram, etc.)
    EXTERNAL_API = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        jitter=True
    )
    
    # For database operations
    DATABASE = RetryConfig(
        max_attempts=2,
        base_delay=0.5,
        max_delay=5.0,
        jitter=True
    )
    
    # For file operations
    FILE_OPERATIONS = RetryConfig(
        max_attempts=3,
        base_delay=0.2,
        max_delay=2.0,
        jitter=False
    )
    
    # For network downloads
    NETWORK_DOWNLOAD = RetryConfig(
        max_attempts=4,
        base_delay=2.0,
        max_delay=60.0,
        jitter=True
    )

def sync_retry_with_backoff(
    func: Callable,
    config: RetryConfig,
    exceptions: tuple = (Exception,),
    *args,
    **kwargs
) -> Any:
    """
    Synchronous retry with exponential backoff
    
    Args:
        func: The function to retry
        config: Retry configuration
        exceptions: Tuple of exceptions to retry on
        *args, **kwargs: Arguments to pass to func
        
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all retries fail
    """
    import time
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            result = func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Retry succeeded for {func.__name__} on attempt {attempt + 1}")
            return result
            
        except exceptions as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                logger.error(f"All {config.max_attempts} retry attempts failed for {func.__name__}: {str(e)}")
                raise e
            
            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.backoff_multiplier ** attempt), 
                config.max_delay
            )
            
            # Add jitter to prevent thundering herd
            if config.jitter:
                delay *= (0.5 + random.random())
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed for {func.__name__}, "
                f"retrying in {delay:.2f}s: {str(e)}"
            )
            time.sleep(delay)
    
    # This shouldn't be reached, but just in case
    if last_exception:
        raise last_exception
