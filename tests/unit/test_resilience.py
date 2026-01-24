# -*- coding: utf-8 -*-
"""
Tests for resilience module (circuit breaker and retry)
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch

from agents.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    circuit_breaker,
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_all_circuit_breakers,
)
from agents.resilience.retry import (
    RetryPolicy,
    retry,
    retry_with_backoff,
    ExponentialBackoff,
    ConstantBackoff,
)


@pytest.fixture(autouse=True)
def reset_breakers():
    """Reset circuit breakers before each test"""
    reset_all_circuit_breakers()
    yield
    reset_all_circuit_breakers()


class TestCircuitBreakerBasic:
    """Basic circuit breaker tests"""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in closed state"""
        breaker = CircuitBreaker("test", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available()

    def test_success_keeps_closed(self):
        """Successful calls keep circuit closed"""
        breaker = CircuitBreaker("test", failure_threshold=3)

        breaker._record_success()
        breaker._record_success()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.successful_calls == 2
        assert breaker.stats.consecutive_successes == 2

    def test_failures_below_threshold_keep_closed(self):
        """Failures below threshold keep circuit closed"""
        breaker = CircuitBreaker("test", failure_threshold=3)

        breaker._record_failure(ValueError("test"))
        breaker._record_failure(ValueError("test"))

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.consecutive_failures == 2

    def test_failures_at_threshold_opens_circuit(self):
        """Reaching failure threshold opens circuit"""
        breaker = CircuitBreaker("test", failure_threshold=3)

        for _ in range(3):
            breaker._record_failure(ValueError("test"))

        assert breaker.state == CircuitState.OPEN
        assert not breaker.is_available()

    def test_success_resets_failure_count(self):
        """Success resets consecutive failure count"""
        breaker = CircuitBreaker("test", failure_threshold=3)

        breaker._record_failure(ValueError("test"))
        breaker._record_failure(ValueError("test"))
        breaker._record_success()

        assert breaker.stats.consecutive_failures == 0
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerOpen:
    """Tests for open circuit state"""

    def test_open_circuit_rejects_calls(self):
        """Open circuit rejects calls"""
        breaker = CircuitBreaker("test", failure_threshold=1, timeout=60)

        breaker._record_failure(ValueError("test"))

        assert breaker.state == CircuitState.OPEN
        assert not breaker.is_available()

    @pytest.mark.asyncio
    async def test_open_circuit_raises_exception(self):
        """Open circuit raises CircuitBreakerOpen"""
        breaker = CircuitBreaker("test", failure_threshold=1, timeout=60)

        await breaker._after_call(False, ValueError("test"))

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await breaker._before_call()

        assert exc_info.value.name == "test"

    @pytest.mark.asyncio
    async def test_open_circuit_tracks_rejections(self):
        """Rejected calls are tracked"""
        breaker = CircuitBreaker("test", failure_threshold=1, timeout=60)
        await breaker._after_call(False, ValueError("test"))

        try:
            await breaker._before_call()
        except CircuitBreakerOpen:
            pass

        assert breaker.stats.rejected_calls == 1


class TestCircuitBreakerHalfOpen:
    """Tests for half-open state"""

    def test_timeout_transitions_to_half_open(self):
        """After timeout, circuit transitions to half-open"""
        breaker = CircuitBreaker("test", failure_threshold=1, timeout=0.1)

        breaker._record_failure(ValueError("test"))
        assert breaker.state == CircuitState.OPEN

        time.sleep(0.15)

        # Should be available now
        assert breaker.is_available()

    @pytest.mark.asyncio
    async def test_half_open_success_closes_circuit(self):
        """Success in half-open closes circuit"""
        breaker = CircuitBreaker(
            "test",
            failure_threshold=1,
            success_threshold=2,
            timeout=0.1
        )

        # Open the circuit
        for _ in range(1):
            await breaker._after_call(False, ValueError("test"))

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # First success - still half-open
        await breaker._before_call()
        await breaker._after_call(True)
        assert breaker.state == CircuitState.HALF_OPEN

        # Second success - closes circuit
        await breaker._before_call()
        await breaker._after_call(True)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        """Failure in half-open reopens circuit"""
        breaker = CircuitBreaker("test", failure_threshold=1, timeout=0.1)

        await breaker._after_call(False, ValueError("test"))
        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(0.15)

        await breaker._before_call()
        await breaker._after_call(False, ValueError("test"))

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerDecorator:
    """Tests for decorator usage"""

    @pytest.mark.asyncio
    async def test_async_decorator_success(self):
        """Async decorator works for successful calls"""
        breaker = CircuitBreaker("test")

        @breaker
        async def async_func():
            return "success"

        result = await async_func()
        assert result == "success"
        assert breaker.stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_async_decorator_failure(self):
        """Async decorator records failures"""
        breaker = CircuitBreaker("test", failure_threshold=5)

        @breaker
        async def failing_func():
            raise ValueError("error")

        with pytest.raises(ValueError):
            await failing_func()

        assert breaker.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_async_decorator_opens_circuit(self):
        """Async decorator opens circuit after threshold"""
        breaker = CircuitBreaker("test", failure_threshold=2)

        @breaker
        async def failing_func():
            raise ValueError("error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await failing_func()

        assert breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpen):
            await failing_func()


class TestCircuitBreakerExclusions:
    """Tests for excluded exceptions"""

    def test_excluded_exceptions_not_counted(self):
        """Excluded exceptions don't count as failures"""
        breaker = CircuitBreaker(
            "test",
            failure_threshold=2,
            excluded_exceptions={KeyboardInterrupt}
        )

        breaker._record_failure(KeyboardInterrupt())
        breaker._record_failure(KeyboardInterrupt())

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failed_calls == 0

    def test_non_excluded_exceptions_counted(self):
        """Non-excluded exceptions are counted"""
        breaker = CircuitBreaker(
            "test",
            failure_threshold=2,
            excluded_exceptions={KeyboardInterrupt}
        )

        breaker._record_failure(ValueError("test"))
        breaker._record_failure(ValueError("test"))

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerCallbacks:
    """Tests for state change callbacks"""

    def test_state_change_callback_called(self):
        """Callback is called on state change"""
        callback = MagicMock()
        breaker = CircuitBreaker(
            "test",
            failure_threshold=1,
            on_state_change=callback
        )

        breaker._record_failure(ValueError("test"))

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "test"  # name
        assert args[1] == CircuitState.CLOSED  # old state
        assert args[2] == CircuitState.OPEN  # new state


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry"""

    def test_get_circuit_breaker_creates_new(self):
        """get_circuit_breaker creates new breaker"""
        breaker = get_circuit_breaker("new_breaker", failure_threshold=10)

        assert breaker.name == "new_breaker"
        assert breaker._failure_threshold == 10

    def test_get_circuit_breaker_returns_existing(self):
        """get_circuit_breaker returns existing breaker"""
        breaker1 = get_circuit_breaker("shared")
        breaker2 = get_circuit_breaker("shared")

        assert breaker1 is breaker2

    def test_get_all_circuit_breakers(self):
        """get_all_circuit_breakers returns all breakers"""
        get_circuit_breaker("breaker1")
        get_circuit_breaker("breaker2")

        all_breakers = get_all_circuit_breakers()

        assert "breaker1" in all_breakers
        assert "breaker2" in all_breakers

    def test_reset_all_circuit_breakers(self):
        """reset_all_circuit_breakers resets all"""
        breaker = get_circuit_breaker("to_reset", failure_threshold=1)
        breaker._record_failure(ValueError("test"))

        reset_all_circuit_breakers()

        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerStatus:
    """Tests for status reporting"""

    def test_get_status(self):
        """get_status returns full status"""
        breaker = CircuitBreaker("status_test", failure_threshold=5)
        breaker._record_success()
        breaker._record_failure(ValueError("test"))

        status = breaker.get_status()

        assert status['name'] == "status_test"
        assert status['state'] == "closed"
        assert status['is_available'] is True
        assert status['stats']['successful_calls'] == 1
        assert status['stats']['failed_calls'] == 1

    def test_reset_clears_stats(self):
        """reset clears all stats"""
        breaker = CircuitBreaker("reset_test", failure_threshold=1)
        breaker._record_failure(ValueError("test"))

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failed_calls == 0


# Retry Tests

class TestBackoffStrategies:
    """Tests for backoff strategies"""

    def test_constant_backoff(self):
        """Constant backoff returns same delay"""
        backoff = ConstantBackoff(delay=2.0)

        assert backoff.get_delay(0) == 2.0
        assert backoff.get_delay(1) == 2.0
        assert backoff.get_delay(5) == 2.0

    def test_constant_backoff_with_jitter(self):
        """Constant backoff with jitter varies delay"""
        backoff = ConstantBackoff(delay=2.0, jitter=0.5)

        delays = [backoff.get_delay(0) for _ in range(10)]

        # Should have some variation
        assert min(delays) < max(delays)
        # But within bounds
        assert all(2.0 <= d <= 3.0 for d in delays)

    def test_exponential_backoff(self):
        """Exponential backoff increases delay"""
        backoff = ExponentialBackoff(base_delay=1.0, multiplier=2.0, jitter=0)

        assert backoff.get_delay(0) == 1.0
        assert backoff.get_delay(1) == 2.0
        assert backoff.get_delay(2) == 4.0
        assert backoff.get_delay(3) == 8.0

    def test_exponential_backoff_max_cap(self):
        """Exponential backoff respects max delay"""
        backoff = ExponentialBackoff(
            base_delay=1.0,
            max_delay=5.0,
            multiplier=2.0,
            jitter=0
        )

        assert backoff.get_delay(0) == 1.0
        assert backoff.get_delay(1) == 2.0
        assert backoff.get_delay(2) == 4.0
        assert backoff.get_delay(3) == 5.0  # Capped
        assert backoff.get_delay(10) == 5.0  # Still capped


class TestRetryPolicy:
    """Tests for RetryPolicy"""

    def test_should_retry_within_attempts(self):
        """Should retry within max attempts"""
        policy = RetryPolicy(max_attempts=3)

        assert policy.should_retry(ValueError("test"), 0)
        assert policy.should_retry(ValueError("test"), 1)
        assert policy.should_retry(ValueError("test"), 2)

    def test_should_not_retry_at_max(self):
        """Should not retry at max attempts"""
        policy = RetryPolicy(max_attempts=3)

        assert not policy.should_retry(ValueError("test"), 3)

    def test_retryable_exceptions(self):
        """Only retryable exceptions trigger retry"""
        policy = RetryPolicy(
            max_attempts=3,
            retryable_exceptions={ConnectionError, TimeoutError}
        )

        assert policy.should_retry(ConnectionError(), 0)
        assert policy.should_retry(TimeoutError(), 0)
        assert not policy.should_retry(ValueError(), 0)

    def test_non_retryable_exceptions(self):
        """Non-retryable exceptions don't trigger retry"""
        policy = RetryPolicy(
            max_attempts=3,
            non_retryable_exceptions={ValueError}
        )

        assert not policy.should_retry(ValueError(), 0)
        assert policy.should_retry(ConnectionError(), 0)

    def test_custom_retry_condition(self):
        """Custom retry condition works"""
        policy = RetryPolicy(
            max_attempts=3,
            retry_on=lambda e: "retry" in str(e)
        )

        assert policy.should_retry(ValueError("please retry"), 0)
        assert not policy.should_retry(ValueError("no way"), 0)


class TestRetryDecorator:
    """Tests for retry decorator"""

    @pytest.mark.asyncio
    async def test_async_retry_success(self):
        """Async function succeeds without retry"""
        call_count = 0

        @retry(max_attempts=3)
        async def async_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await async_func()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_failure(self):
        """Async function retries on failure"""
        call_count = 0

        @retry(max_attempts=3, backoff=ConstantBackoff(delay=0.01))
        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "success"

        result = await async_func()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        """Async function raises after max attempts"""
        call_count = 0

        @retry(max_attempts=3, backoff=ConstantBackoff(delay=0.01))
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fail")

        with pytest.raises(ValueError):
            await failing_func()

        assert call_count == 3

    def test_sync_retry_success(self):
        """Sync function succeeds without retry"""
        call_count = 0

        @retry(max_attempts=3)
        def sync_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = sync_func()

        assert result == "success"
        assert call_count == 1

    def test_sync_retry_on_failure(self):
        """Sync function retries on failure"""
        call_count = 0

        @retry(max_attempts=3, backoff=ConstantBackoff(delay=0.01))
        def sync_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = sync_func()

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_respects_retryable_exceptions(self):
        """Retry only on specified exceptions"""
        call_count = 0

        @retry(
            max_attempts=3,
            retryable_exceptions={ConnectionError},
            backoff=ConstantBackoff(delay=0.01)
        )
        async def async_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await async_func()

        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_retry_callback(self):
        """on_retry callback is called"""
        retry_calls = []

        def on_retry(attempt, exc, delay):
            retry_calls.append((attempt, type(exc).__name__))

        call_count = 0

        @retry(
            max_attempts=3,
            backoff=ConstantBackoff(delay=0.01),
            on_retry=on_retry
        )
        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "success"

        await async_func()

        assert len(retry_calls) == 2
        assert retry_calls[0] == (1, "ValueError")
        assert retry_calls[1] == (2, "ValueError")


class TestRetryWithBackoff:
    """Tests for retry_with_backoff convenience decorator"""

    @pytest.mark.asyncio
    async def test_retry_with_backoff_works(self):
        """retry_with_backoff decorator works"""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = await async_func()

        assert result == "success"
        assert call_count == 2
