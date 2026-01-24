# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Circuit Breaker Pattern
Prevents cascading failures in distributed agent systems

Version: 3.0.0

The circuit breaker has three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, requests fail fast
- HALF_OPEN: Testing if service recovered

This protects:
- LLM API calls (rate limits, outages)
- External APIs (YTJ, web scraping)
- Inter-agent communication
- Database/Redis connections
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union
from contextlib import contextmanager, asynccontextmanager

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open"""

    def __init__(self, name: str, until: datetime):
        self.name = name
        self.until = until
        super().__init__(f"Circuit breaker '{name}' is open until {until}")


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    state_changes: int = 0
    time_in_open: float = 0.0
    time_in_half_open: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'rejected_calls': self.rejected_calls,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
            'consecutive_failures': self.consecutive_failures,
            'consecutive_successes': self.consecutive_successes,
            'state_changes': self.state_changes,
            'success_rate': self.success_rate,
        }

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls


class CircuitBreaker:
    """
    Circuit breaker for protecting external calls.

    Usage:
        breaker = CircuitBreaker("llm_api", failure_threshold=5)

        async with breaker:
            result = await call_llm()

        # Or as decorator
        @breaker
        async def call_llm():
            ...
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_max_calls: int = 3,
        excluded_exceptions: Optional[Set[Type[Exception]]] = None,
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], None]] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Unique name for this breaker
            failure_threshold: Failures before opening circuit
            success_threshold: Successes in half-open before closing
            timeout: Seconds before trying half-open
            half_open_max_calls: Max concurrent calls in half-open
            excluded_exceptions: Exceptions that don't count as failures
            on_state_change: Callback when state changes
        """
        self.name = name
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._timeout = timeout
        self._half_open_max_calls = half_open_max_calls
        self._excluded_exceptions = excluded_exceptions or set()
        self._on_state_change = on_state_change

        # State
        self._state = CircuitState.CLOSED
        self._last_state_change = time.time()
        self._last_failure_time: Optional[float] = None

        # Counters
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0

        # Thread safety
        self._lock = asyncio.Lock()

        logger.info(f"[CircuitBreaker] Created '{name}' (threshold={failure_threshold})")

    @property
    def state(self) -> CircuitState:
        """Get current state"""
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get statistics"""
        return self._stats

    def is_available(self) -> bool:
        """Check if circuit breaker allows calls"""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if timeout elapsed
            if self._should_attempt_reset():
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._half_open_max_calls

        return False

    def _should_attempt_reset(self) -> bool:
        """Check if we should try half-open"""
        if self._state != CircuitState.OPEN:
            return False

        if self._last_failure_time is None:
            return True

        elapsed = time.time() - self._last_failure_time
        return elapsed >= self._timeout

    def _change_state(self, new_state: CircuitState):
        """Change circuit state"""
        if new_state == self._state:
            return

        old_state = self._state
        now = time.time()

        # Track time in states
        elapsed = now - self._last_state_change
        if old_state == CircuitState.OPEN:
            self._stats.time_in_open += elapsed
        elif old_state == CircuitState.HALF_OPEN:
            self._stats.time_in_half_open += elapsed

        self._state = new_state
        self._last_state_change = now
        self._stats.state_changes += 1

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

        logger.info(f"[CircuitBreaker] '{self.name}': {old_state.value} -> {new_state.value}")

        if self._on_state_change:
            try:
                self._on_state_change(self.name, old_state, new_state)
            except Exception as e:
                logger.error(f"[CircuitBreaker] State change callback error: {e}")

    def _record_success(self):
        """Record successful call"""
        self._stats.total_calls += 1
        self._stats.successful_calls += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self._success_threshold:
                self._change_state(CircuitState.CLOSED)

    def _record_failure(self, exception: Exception):
        """Record failed call"""
        # Check if exception is excluded
        if type(exception) in self._excluded_exceptions:
            logger.debug(f"[CircuitBreaker] '{self.name}': Excluded exception {type(exception)}")
            return

        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.time()
        self._last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self._failure_threshold:
                self._change_state(CircuitState.OPEN)

        elif self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self._change_state(CircuitState.OPEN)

    def _record_rejection(self):
        """Record rejected call"""
        self._stats.rejected_calls += 1

    async def _before_call(self):
        """Called before executing protected code"""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._change_state(CircuitState.HALF_OPEN)
                else:
                    self._record_rejection()
                    until = datetime.fromtimestamp(
                        self._last_failure_time + self._timeout
                    )
                    raise CircuitBreakerOpen(self.name, until)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    self._record_rejection()
                    raise CircuitBreakerOpen(
                        self.name,
                        datetime.fromtimestamp(time.time() + 1)
                    )
                self._half_open_calls += 1

    async def _after_call(self, success: bool, exception: Optional[Exception] = None):
        """Called after executing protected code"""
        async with self._lock:
            if success:
                self._record_success()
            else:
                self._record_failure(exception)

    @asynccontextmanager
    async def __aenter__(self):
        """Async context manager entry"""
        await self._before_call()
        try:
            yield self
        except Exception as e:
            await self._after_call(False, e)
            raise
        else:
            await self._after_call(True)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - handled in __aenter__"""
        pass

    @contextmanager
    def __enter__(self):
        """Sync context manager entry"""
        # Run async in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't use await, do sync check
            if self._state == CircuitState.OPEN and not self._should_attempt_reset():
                self._record_rejection()
                until = datetime.fromtimestamp(
                    (self._last_failure_time or time.time()) + self._timeout
                )
                raise CircuitBreakerOpen(self.name, until)
        else:
            loop.run_until_complete(self._before_call())

        try:
            yield self
        except Exception as e:
            if loop.is_running():
                self._record_failure(e)
            else:
                loop.run_until_complete(self._after_call(False, e))
            raise
        else:
            if loop.is_running():
                self._record_success()
            else:
                loop.run_until_complete(self._after_call(True))

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit - handled in __enter__"""
        pass

    def __call__(self, func: Callable) -> Callable:
        """Use as decorator"""
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                await self._before_call()
                try:
                    result = await func(*args, **kwargs)
                    await self._after_call(True)
                    return result
                except Exception as e:
                    await self._after_call(False, e)
                    raise

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self:
                    return func(*args, **kwargs)

            return sync_wrapper

    def reset(self):
        """Reset circuit breaker to closed state"""
        self._state = CircuitState.CLOSED
        self._last_state_change = time.time()
        self._last_failure_time = None
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0
        logger.info(f"[CircuitBreaker] '{self.name}': Reset to CLOSED")

    def force_open(self):
        """Force circuit to open state"""
        self._change_state(CircuitState.OPEN)
        self._last_failure_time = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Get full status"""
        return {
            'name': self.name,
            'state': self._state.value,
            'is_available': self.is_available(),
            'failure_threshold': self._failure_threshold,
            'success_threshold': self._success_threshold,
            'timeout': self._timeout,
            'stats': self._stats.to_dict(),
            'time_until_retry': self._get_time_until_retry(),
        }

    def _get_time_until_retry(self) -> Optional[float]:
        """Get seconds until retry is allowed"""
        if self._state != CircuitState.OPEN:
            return None

        if self._last_failure_time is None:
            return 0

        remaining = (self._last_failure_time + self._timeout) - time.time()
        return max(0, remaining)


# Global registry of circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: float = 60.0,
    **kwargs
) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.

    Creates a new breaker if one doesn't exist with the given name.
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
            **kwargs
        )
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers"""
    return _circuit_breakers.copy()


def reset_all_circuit_breakers():
    """Reset all circuit breakers"""
    for breaker in _circuit_breakers.values():
        breaker.reset()


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: float = 60.0,
    **kwargs
) -> Callable:
    """
    Decorator to apply circuit breaker to a function.

    Usage:
        @circuit_breaker("llm_api")
        async def call_llm():
            ...
    """
    breaker = get_circuit_breaker(
        name,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        **kwargs
    )
    return breaker
