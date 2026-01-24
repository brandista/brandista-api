# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Structured Logging
JSON-formatted logs with correlation IDs and trace context

Version: 3.0.0

Provides:
- JSON-formatted log output for log aggregation (ELK, Datadog, etc.)
- Automatic correlation ID propagation
- Integration with distributed tracing
- Agent-specific logging context
- Sensitive data masking
"""

import logging
import json
import sys
import time
import uuid
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
from contextvars import ContextVar
from functools import wraps

# Context variables for request-scoped data
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)
_agent_id: ContextVar[Optional[str]] = ContextVar('agent_id', default=None)
_user_id: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_extra_context: ContextVar[Dict[str, Any]] = ContextVar('extra_context', default={})


class SensitiveDataMasker:
    """
    Masks sensitive data in log messages.

    Protects PII, credentials, and other sensitive information.
    """

    # Patterns for sensitive data
    PATTERNS = [
        # API keys and tokens
        (r'(api[_-]?key|token|secret|password|credential)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{8,})["\']?',
         r'\1=***MASKED***'),
        # Email addresses
        (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
         '***EMAIL***'),
        # Credit card numbers (basic pattern)
        (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
         '***CARD***'),
        # Finnish personal ID (henkilotunnus)
        (r'\b\d{6}[-+A]\d{3}[a-zA-Z0-9]\b',
         '***HETU***'),
        # Phone numbers
        (r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
         '***PHONE***'),
        # IP addresses (optional - might be needed for debugging)
        # (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***IP***'),
    ]

    # Keys to always mask in dictionaries
    SENSITIVE_KEYS = {
        'password', 'passwd', 'pwd',
        'secret', 'token', 'api_key', 'apikey',
        'auth', 'authorization', 'bearer',
        'credit_card', 'card_number', 'cvv',
        'ssn', 'social_security', 'henkilotunnus', 'hetu',
        'private_key', 'secret_key',
    }

    _compiled_patterns: List[tuple] = None

    @classmethod
    def _get_patterns(cls) -> List[tuple]:
        """Get compiled regex patterns"""
        if cls._compiled_patterns is None:
            cls._compiled_patterns = [
                (re.compile(pattern, re.IGNORECASE), replacement)
                for pattern, replacement in cls.PATTERNS
            ]
        return cls._compiled_patterns

    @classmethod
    def mask_string(cls, text: str) -> str:
        """Mask sensitive data in a string"""
        if not text:
            return text

        result = text
        for pattern, replacement in cls._get_patterns():
            result = pattern.sub(replacement, result)

        return result

    @classmethod
    def mask_dict(cls, data: Dict[str, Any], depth: int = 0, max_depth: int = 10) -> Dict[str, Any]:
        """
        Mask sensitive data in a dictionary.

        Recursively processes nested structures.
        """
        if depth > max_depth:
            return {"__truncated__": "max depth exceeded"}

        result = {}

        for key, value in data.items():
            # Check if key is sensitive
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in cls.SENSITIVE_KEYS):
                result[key] = "***MASKED***"
            elif isinstance(value, dict):
                result[key] = cls.mask_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = cls.mask_list(value, depth + 1, max_depth)
            elif isinstance(value, str):
                result[key] = cls.mask_string(value)
            else:
                result[key] = value

        return result

    @classmethod
    def mask_list(cls, data: List[Any], depth: int = 0, max_depth: int = 10) -> List[Any]:
        """Mask sensitive data in a list"""
        if depth > max_depth:
            return ["__truncated__"]

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(cls.mask_dict(item, depth + 1, max_depth))
            elif isinstance(item, list):
                result.append(cls.mask_list(item, depth + 1, max_depth))
            elif isinstance(item, str):
                result.append(cls.mask_string(item))
            else:
                result.append(item)

        return result


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter with context enrichment.

    Outputs logs in JSON format suitable for log aggregation systems.
    """

    def __init__(
        self,
        service_name: str = "growth-engine",
        environment: str = "development",
        include_stack_trace: bool = True,
        mask_sensitive: bool = True,
    ):
        super().__init__()
        self._service_name = service_name
        self._environment = environment
        self._include_stack_trace = include_stack_trace
        self._mask_sensitive = mask_sensitive

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Base log structure
        log_entry = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service_name,
            "environment": self._environment,
        }

        # Add context from contextvars
        correlation_id = _correlation_id.get()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        trace_id = _trace_id.get()
        if trace_id:
            log_entry["trace_id"] = trace_id

        span_id = _span_id.get()
        if span_id:
            log_entry["span_id"] = span_id

        agent_id = _agent_id.get()
        if agent_id:
            log_entry["agent_id"] = agent_id

        user_id = _user_id.get()
        if user_id:
            log_entry["user_id"] = user_id

        # Add extra context
        extra_context = _extra_context.get()
        if extra_context:
            log_entry["context"] = extra_context

        # Add source location
        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info and self._include_stack_trace:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": self.formatException(record.exc_info),
            }

        # Add any extra attributes from the log record
        extra_keys = set(record.__dict__.keys()) - {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'message', 'asctime', 'taskName'
        }

        if extra_keys:
            extras = {k: getattr(record, k) for k in extra_keys}
            if self._mask_sensitive:
                extras = SensitiveDataMasker.mask_dict(extras)
            log_entry["extra"] = extras

        # Mask sensitive data in message
        if self._mask_sensitive:
            log_entry["message"] = SensitiveDataMasker.mask_string(log_entry["message"])

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter with colors.

    For development use - shows key context inline.
    """

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self._use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console"""
        # Time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Level with color
        level = record.levelname
        if self._use_colors:
            color = self.COLORS.get(level, '')
            level = f"{color}{level:8}{self.RESET}"
        else:
            level = f"{level:8}"

        # Context prefix
        context_parts = []

        agent_id = _agent_id.get()
        if agent_id:
            context_parts.append(f"[{agent_id}]")

        correlation_id = _correlation_id.get()
        if correlation_id:
            context_parts.append(f"({correlation_id[:8]})")

        context = " ".join(context_parts)
        if context:
            context = f" {context}"

        # Format message
        message = record.getMessage()

        # Add exception if present
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"

        return f"{timestamp} {level}{context} {record.name}: {message}"


class StructuredLogger:
    """
    Wrapper for structured logging with context management.

    Provides convenience methods for logging with additional context.
    """

    def __init__(self, name: str, base_logger: Optional[logging.Logger] = None):
        self._logger = base_logger or logging.getLogger(name)
        self._name = name

    def _log(self, level: int, msg: str, *args, **kwargs):
        """Internal log method with extra handling"""
        extra = kwargs.pop('extra', {})

        # Add any additional kwargs to extra
        for key in list(kwargs.keys()):
            if key not in ('exc_info', 'stack_info', 'stacklevel'):
                extra[key] = kwargs.pop(key)

        self._logger.log(level, msg, *args, extra=extra, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message"""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message"""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message"""
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message"""
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback"""
        kwargs['exc_info'] = True
        self._log(logging.ERROR, msg, *args, **kwargs)

    def with_context(self, **context) -> 'StructuredLogger':
        """Create logger with additional context"""
        # This returns the same logger but sets context
        current = _extra_context.get() or {}
        _extra_context.set({**current, **context})
        return self


# Context management functions

def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """
    Set correlation ID for current context.

    If not provided, generates a new UUID.
    """
    if correlation_id is None:
        correlation_id = uuid.uuid4().hex[:16]
    _correlation_id.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID"""
    return _correlation_id.get()


def set_trace_context(trace_id: str, span_id: Optional[str] = None):
    """Set trace context from distributed tracing"""
    _trace_id.set(trace_id)
    if span_id:
        _span_id.set(span_id)


def get_trace_context() -> Dict[str, Optional[str]]:
    """Get current trace context"""
    return {
        'trace_id': _trace_id.get(),
        'span_id': _span_id.get(),
    }


def set_agent_context(agent_id: str):
    """Set current agent ID"""
    _agent_id.set(agent_id)


def get_agent_context() -> Optional[str]:
    """Get current agent ID"""
    return _agent_id.get()


def set_user_context(user_id: str):
    """Set current user ID"""
    _user_id.set(user_id)


def clear_context():
    """Clear all context variables"""
    _correlation_id.set(None)
    _trace_id.set(None)
    _span_id.set(None)
    _agent_id.set(None)
    _user_id.set(None)
    _extra_context.set({})


def with_context(**context):
    """
    Decorator to add logging context to a function.

    Usage:
        @with_context(operation="analysis")
        def analyze():
            logger.info("Starting analysis")
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current = _extra_context.get() or {}
            _extra_context.set({**current, **context})
            try:
                return func(*args, **kwargs)
            finally:
                _extra_context.set(current)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            current = _extra_context.get() or {}
            _extra_context.set({**current, **context})
            try:
                return await func(*args, **kwargs)
            finally:
                _extra_context.set(current)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def with_agent(agent_id: str):
    """
    Decorator to set agent context for a function.

    Usage:
        @with_agent("scout")
        def scout_operation():
            logger.info("Scout doing work")
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            previous = _agent_id.get()
            _agent_id.set(agent_id)
            try:
                return func(*args, **kwargs)
            finally:
                _agent_id.set(previous)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            previous = _agent_id.get()
            _agent_id.set(agent_id)
            try:
                return await func(*args, **kwargs)
            finally:
                _agent_id.set(previous)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# Logging setup functions

def setup_logging(
    level: int = logging.INFO,
    json_output: bool = False,
    service_name: str = "growth-engine",
    environment: str = "development",
    mask_sensitive: bool = True,
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Logging level
        json_output: Use JSON format (for production)
        service_name: Service name for logs
        environment: Environment name
        mask_sensitive: Mask sensitive data

    Returns:
        Root logger
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Set formatter
    if json_output:
        formatter = JSONFormatter(
            service_name=service_name,
            environment=environment,
            mask_sensitive=mask_sensitive,
        )
    else:
        formatter = ConsoleFormatter(use_colors=True)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    return root_logger


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger by name"""
    return StructuredLogger(name)


# Agent-specific loggers

def get_agent_logger(agent_id: str) -> StructuredLogger:
    """Get logger for a specific agent"""
    logger = StructuredLogger(f"agent.{agent_id}")
    set_agent_context(agent_id)
    return logger
