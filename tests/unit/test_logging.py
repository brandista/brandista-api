# -*- coding: utf-8 -*-
"""
Tests for structured logging module
"""

import pytest
import json
import logging
from io import StringIO
from unittest.mock import patch, MagicMock

from agents.observability.logging import (
    JSONFormatter,
    ConsoleFormatter,
    StructuredLogger,
    SensitiveDataMasker,
    set_correlation_id,
    get_correlation_id,
    set_trace_context,
    get_trace_context,
    set_agent_context,
    get_agent_context,
    set_user_context,
    clear_context,
    with_context,
    with_agent,
    setup_logging,
    get_logger,
    get_agent_logger,
)


@pytest.fixture(autouse=True)
def reset_context():
    """Reset logging context before each test"""
    clear_context()
    yield
    clear_context()


class TestSensitiveDataMasker:
    """Tests for SensitiveDataMasker"""

    def test_mask_api_key(self):
        """API keys are masked"""
        text = 'api_key=sk_live_abc123456789'
        result = SensitiveDataMasker.mask_string(text)
        assert 'abc123456789' not in result
        assert 'MASKED' in result

    def test_mask_token(self):
        """Tokens are masked"""
        text = 'token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"'
        result = SensitiveDataMasker.mask_string(text)
        assert 'eyJhbGci' not in result

    def test_mask_password(self):
        """Passwords are masked"""
        text = 'password=supersecret123'
        result = SensitiveDataMasker.mask_string(text)
        assert 'supersecret123' not in result

    def test_mask_email(self):
        """Email addresses are masked"""
        text = 'Contact: user@example.com for support'
        result = SensitiveDataMasker.mask_string(text)
        assert 'user@example.com' not in result
        assert 'EMAIL' in result

    def test_mask_credit_card(self):
        """Credit card numbers are masked"""
        text = 'Card: 4111-1111-1111-1111'
        result = SensitiveDataMasker.mask_string(text)
        assert '4111' not in result
        assert 'CARD' in result

    def test_mask_finnish_hetu(self):
        """Finnish personal IDs are masked"""
        text = 'Henkilotunnus: 010190-123A'
        result = SensitiveDataMasker.mask_string(text)
        assert '010190' not in result
        assert 'HETU' in result

    def test_mask_phone(self):
        """Phone numbers are masked"""
        text = 'Call +358 40 123 4567'
        result = SensitiveDataMasker.mask_string(text)
        assert '4567' not in result
        assert 'PHONE' in result

    def test_mask_dict_sensitive_key(self):
        """Dictionary with sensitive keys is masked"""
        data = {
            'username': 'john',
            'password': 'secret123',
            'api_key': 'sk_live_abc',
        }
        result = SensitiveDataMasker.mask_dict(data)

        assert result['username'] == 'john'
        assert result['password'] == '***MASKED***'
        assert result['api_key'] == '***MASKED***'

    def test_mask_nested_dict(self):
        """Nested dictionaries are masked"""
        data = {
            'user': {
                'name': 'John',
                'credentials': {
                    'token': 'secret_token',
                }
            }
        }
        result = SensitiveDataMasker.mask_dict(data)

        assert result['user']['name'] == 'John'
        assert result['user']['credentials']['token'] == '***MASKED***'

    def test_mask_list_with_sensitive_data(self):
        """Lists with sensitive data are masked"""
        data = ['normal', 'user@example.com', 'another']
        result = SensitiveDataMasker.mask_list(data)

        assert result[0] == 'normal'
        assert 'EMAIL' in result[1]
        assert result[2] == 'another'

    def test_mask_dict_max_depth(self):
        """Deep nesting is truncated"""
        # Create deeply nested structure
        data = {'level': 0}
        current = data
        for i in range(15):
            current['nested'] = {'level': i + 1}
            current = current['nested']

        result = SensitiveDataMasker.mask_dict(data, max_depth=5)

        # Should have truncation indicator somewhere
        def find_truncated(d, depth=0):
            if depth > 20:
                return False
            if isinstance(d, dict):
                if '__truncated__' in d:
                    return True
                for v in d.values():
                    if find_truncated(v, depth + 1):
                        return True
            return False

        assert find_truncated(result)


class TestJSONFormatter:
    """Tests for JSONFormatter"""

    def test_basic_format(self):
        """Basic log is formatted as JSON"""
        formatter = JSONFormatter(service_name='test', mask_sensitive=False)
        record = logging.LogRecord(
            name='test.logger',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data['level'] == 'INFO'
        assert data['message'] == 'Test message'
        assert data['service'] == 'test'
        assert data['logger'] == 'test.logger'
        assert '@timestamp' in data

    def test_format_with_correlation_id(self):
        """Correlation ID is included in log"""
        formatter = JSONFormatter()
        set_correlation_id('corr-123')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data['correlation_id'] == 'corr-123'

    def test_format_with_agent_context(self):
        """Agent context is included in log"""
        formatter = JSONFormatter()
        set_agent_context('scout')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data['agent_id'] == 'scout'

    def test_format_with_trace_context(self):
        """Trace context is included in log"""
        formatter = JSONFormatter()
        set_trace_context('trace-abc', 'span-xyz')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data['trace_id'] == 'trace-abc'
        assert data['span_id'] == 'span-xyz'

    def test_format_with_exception(self):
        """Exception info is included in log"""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name='test',
            level=logging.ERROR,
            pathname='/test.py',
            lineno=10,
            msg='Error occurred',
            args=(),
            exc_info=exc_info
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert 'exception' in data
        assert data['exception']['type'] == 'ValueError'
        assert 'Test error' in data['exception']['message']

    def test_format_masks_sensitive_data(self):
        """Sensitive data in message is masked"""
        formatter = JSONFormatter(mask_sensitive=True)

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='User email: user@example.com',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert 'user@example.com' not in data['message']
        assert 'EMAIL' in data['message']

    def test_format_includes_source_location(self):
        """Source location is included"""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/path/to/test.py',
            lineno=42,
            msg='Test',
            args=(),
            exc_info=None
        )
        record.funcName = 'test_function'

        result = formatter.format(record)
        data = json.loads(result)

        assert data['source']['file'] == '/path/to/test.py'
        assert data['source']['line'] == 42
        assert data['source']['function'] == 'test_function'


class TestConsoleFormatter:
    """Tests for ConsoleFormatter"""

    def test_basic_format(self):
        """Basic log is formatted for console"""
        formatter = ConsoleFormatter(use_colors=False)

        record = logging.LogRecord(
            name='test.logger',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)

        assert 'INFO' in result
        assert 'Test message' in result
        assert 'test.logger' in result

    def test_format_with_agent_context(self):
        """Agent context shown in console output"""
        formatter = ConsoleFormatter(use_colors=False)
        set_agent_context('scout')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)

        assert '[scout]' in result

    def test_format_with_correlation_id(self):
        """Correlation ID shown in console output"""
        formatter = ConsoleFormatter(use_colors=False)
        set_correlation_id('abc123def456')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='/test.py',
            lineno=10,
            msg='Test',
            args=(),
            exc_info=None
        )

        result = formatter.format(record)

        # Should show truncated correlation ID
        assert '(abc123de)' in result


class TestContextManagement:
    """Tests for context management functions"""

    def test_set_and_get_correlation_id(self):
        """Correlation ID can be set and retrieved"""
        cid = set_correlation_id('test-123')

        assert cid == 'test-123'
        assert get_correlation_id() == 'test-123'

    def test_auto_generate_correlation_id(self):
        """Correlation ID is auto-generated if not provided"""
        cid = set_correlation_id()

        assert cid is not None
        assert len(cid) == 16
        assert get_correlation_id() == cid

    def test_set_and_get_trace_context(self):
        """Trace context can be set and retrieved"""
        set_trace_context('trace-abc', 'span-xyz')

        context = get_trace_context()
        assert context['trace_id'] == 'trace-abc'
        assert context['span_id'] == 'span-xyz'

    def test_set_and_get_agent_context(self):
        """Agent context can be set and retrieved"""
        set_agent_context('analyst')

        assert get_agent_context() == 'analyst'

    def test_clear_context(self):
        """Clear removes all context"""
        set_correlation_id('test')
        set_agent_context('scout')
        set_trace_context('trace', 'span')

        clear_context()

        assert get_correlation_id() is None
        assert get_agent_context() is None
        assert get_trace_context()['trace_id'] is None


class TestDecorators:
    """Tests for logging decorators"""

    def test_with_context_decorator(self):
        """with_context decorator adds context"""
        @with_context(operation='test_op')
        def my_function():
            from agents.observability.logging import _extra_context
            return _extra_context.get()

        result = my_function()

        assert result['operation'] == 'test_op'

    def test_with_agent_decorator(self):
        """with_agent decorator sets agent context"""
        @with_agent('scout')
        def agent_function():
            return get_agent_context()

        result = agent_function()

        assert result == 'scout'

    def test_with_agent_restores_previous(self):
        """with_agent restores previous agent after function"""
        set_agent_context('analyst')

        @with_agent('scout')
        def agent_function():
            return get_agent_context()

        inner_result = agent_function()
        outer_result = get_agent_context()

        assert inner_result == 'scout'
        assert outer_result == 'analyst'

    @pytest.mark.asyncio
    async def test_with_agent_async(self):
        """with_agent works with async functions"""
        @with_agent('async_agent')
        async def async_function():
            return get_agent_context()

        result = await async_function()

        assert result == 'async_agent'

    @pytest.mark.asyncio
    async def test_with_context_async(self):
        """with_context works with async functions"""
        @with_context(async_op='test')
        async def async_function():
            from agents.observability.logging import _extra_context
            return _extra_context.get()

        result = await async_function()

        assert result['async_op'] == 'test'


class TestStructuredLogger:
    """Tests for StructuredLogger"""

    def test_logger_debug(self, caplog):
        """Logger debug method works"""
        logger = StructuredLogger('test')

        with caplog.at_level(logging.DEBUG):
            logger.debug('Debug message')

        assert 'Debug message' in caplog.text

    def test_logger_info(self, caplog):
        """Logger info method works"""
        logger = StructuredLogger('test')

        with caplog.at_level(logging.INFO):
            logger.info('Info message')

        assert 'Info message' in caplog.text

    def test_logger_warning(self, caplog):
        """Logger warning method works"""
        logger = StructuredLogger('test')

        with caplog.at_level(logging.WARNING):
            logger.warning('Warning message')

        assert 'Warning message' in caplog.text

    def test_logger_error(self, caplog):
        """Logger error method works"""
        logger = StructuredLogger('test')

        with caplog.at_level(logging.ERROR):
            logger.error('Error message')

        assert 'Error message' in caplog.text

    def test_logger_exception(self, caplog):
        """Logger exception method includes traceback"""
        logger = StructuredLogger('test')

        with caplog.at_level(logging.ERROR):
            try:
                raise ValueError("Test")
            except ValueError:
                logger.exception('Exception occurred')

        assert 'Exception occurred' in caplog.text


class TestSetupLogging:
    """Tests for setup_logging function"""

    def test_setup_console_logging(self):
        """Setup configures console logging"""
        root = setup_logging(
            level=logging.INFO,
            json_output=False,
            service_name='test'
        )

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, ConsoleFormatter)

    def test_setup_json_logging(self):
        """Setup configures JSON logging"""
        root = setup_logging(
            level=logging.INFO,
            json_output=True,
            service_name='test'
        )

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)


class TestGetLogger:
    """Tests for get_logger functions"""

    def test_get_logger(self):
        """get_logger returns StructuredLogger"""
        logger = get_logger('test.module')

        assert isinstance(logger, StructuredLogger)

    def test_get_agent_logger(self):
        """get_agent_logger sets agent context"""
        logger = get_agent_logger('guardian')

        assert isinstance(logger, StructuredLogger)
        assert get_agent_context() == 'guardian'
