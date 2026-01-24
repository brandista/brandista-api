# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Retry Policies
Automatic retry with backoff strategies

Version: 3.0.0

Provides:
- Exponential backoff
- Constant delay
- Configurable retry conditions
- Jitter for thundering herd prevention
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, Set, Type, Union

logger = logging.getLogger(__name__)


class BackoffStrategy:
    """Base class for backoff strategies"""

    def get_delay(self, attempt: int) -> float:
        """Get delay for given attempt number (0-indexed)"""
        raise NotImplementedError


class ConstantBackoff(BackoffStrategy):
    """Constant delay between retries"""

    def __init__(self, delay: float = 1.0, jitter: float = 0.0):
        """
        Args:
            delay: Base delay in seconds
            jitter: Random jitter factor (0-1)
        """
        self._delay = delay
        self._jitter = jitter

    def get_delay(self, attempt: int) -> float:
        delay = self._delay
        if self._jitter > 0:
            delay += random.uniform(0, self._delay * self._jitter)
        return delay


class ExponentialBackoff(BackoffStrategy):
    """Exponential backoff with optional jitter"""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: float = 0.1,
    ):
        """
        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay cap
            multiplier: Multiplier for each attempt
            jitter: Random jitter factor (0-1)
        """
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._multiplier = multiplier
        self._jitter = jitter

    def get_delay(self, attempt: int) -> float:
        # Calculate exponential delay
        delay = self._base_delay * (self._multiplier ** attempt)

        # Apply cap
        delay = min(delay, self._max_delay)

        # Add jitter
        if self._jitter > 0:
            jitter_amount = delay * self._jitter
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)


@dataclass
class RetryPolicy:
    """
    Configurable retry policy.

    Defines when and how to retry failed operations.
    """

    max_attempts: int = 3
    backoff: BackoffStrategy = None
    retryable_exceptions: Optional[Set[Type[Exception]]] = None
    non_retryable_exceptions: Optional[Set[Type[Exception]]] = None
    retry_on: Optional[Callable[[Exception], bool]] = None
    on_retry: Optional[Callable[[int, Exception, float], None]] = None

    def __post_init__(self):
        if self.backoff is None:
            self.backoff = ExponentialBackoff()

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if should retry for given exception and attempt"""
        # Check attempt limit
        if attempt >= self.max_attempts:
            return False

        # Check non-retryable exceptions first
        if self.non_retryable_exceptions:
            if type(exception) in self.non_retryable_exceptions:
                return False

        # Check custom retry condition
        if self.retry_on:
            return self.retry_on(exception)

        # Check retryable exceptions
        if self.retryable_exceptions:
            return type(exception) in self.retryable_exceptions

        # Default: retry all exceptions
        return True

    def get_delay(self, attempt: int) -> float:
        """Get delay for given attempt"""
        return self.backoff.get_delay(attempt)


def retry(
    max_attempts: int = 3,
    backoff: Optional[BackoffStrategy] = None,
    retryable_exceptions: Optional[Set[Type[Exception]]] = None,
    non_retryable_exceptions: Optional[Set[Type[Exception]]] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> Callable:
    """
    Decorator for automatic retry with configurable policy.

    Usage:
        @retry(max_attempts=3, retryable_exceptions={ConnectionError})
        async def fetch_data():
            ...
    """
    policy = RetryPolicy(
        max_attempts=max_attempts,
        backoff=backoff or ExponentialBackoff(),
        retryable_exceptions=retryable_exceptions,
        non_retryable_exceptions=non_retryable_exceptions,
        on_retry=on_retry,
    )

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(policy.max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        if not policy.should_retry(e, attempt + 1):
                            raise

                        delay = policy.get_delay(attempt)

                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/"
                            f"{policy.max_attempts}): {e}. Retrying in {delay:.2f}s"
                        )

                        if policy.on_retry:
                            policy.on_retry(attempt + 1, e, delay)

                        await asyncio.sleep(delay)

                # Should not reach here, but just in case
                if last_exception:
                    raise last_exception

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None

                for attempt in range(policy.max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        if not policy.should_retry(e, attempt + 1):
                            raise

                        delay = policy.get_delay(attempt)

                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/"
                            f"{policy.max_attempts}): {e}. Retrying in {delay:.2f}s"
                        )

                        if policy.on_retry:
                            policy.on_retry(attempt + 1, e, delay)

                        time.sleep(delay)

                if last_exception:
                    raise last_exception

            return sync_wrapper

    return decorator


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    multiplier: float = 2.0,
    jitter: float = 0.1,
) -> Callable:
    """
    Convenience decorator with exponential backoff.

    Usage:
        @retry_with_backoff(max_attempts=5, base_delay=2.0)
        async def unreliable_operation():
            ...
    """
    backoff = ExponentialBackoff(
        base_delay=base_delay,
        max_delay=max_delay,
        multiplier=multiplier,
        jitter=jitter,
    )
    return retry(max_attempts=max_attempts, backoff=backoff)


async def retry_async(
    func: Callable,
    *args,
    policy: Optional[RetryPolicy] = None,
    max_attempts: int = 3,
    **kwargs
) -> Any:
    """
    Execute async function with retry.

    Usage:
        result = await retry_async(fetch_data, url, max_attempts=3)
    """
    if policy is None:
        policy = RetryPolicy(max_attempts=max_attempts)

    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if not policy.should_retry(e, attempt + 1):
                raise

            delay = policy.get_delay(attempt)

            logger.warning(
                f"[Retry] {func.__name__} failed (attempt {attempt + 1}/"
                f"{policy.max_attempts}): {e}. Retrying in {delay:.2f}s"
            )

            if policy.on_retry:
                policy.on_retry(attempt + 1, e, delay)

            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
