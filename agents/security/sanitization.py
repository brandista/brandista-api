# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Input Sanitization
Protection against prompt injection and malicious input

Version: 3.0.0
"""

import re
import html
import logging
from typing import Optional, List, Tuple
from urllib.parse import urlparse, quote

logger = logging.getLogger(__name__)


class PromptSanitizer:
    """
    Sanitizes user input to prevent prompt injection attacks.

    This is critical for any text that will be included in LLM prompts.
    """

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        # Direct instruction overrides
        r'ignore\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions?',
        r'disregard\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions?',
        r'forget\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions?',
        r'override\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions?',
        r'skip\s+(?:all\s+)?(?:previous\s+|prior\s+)?instructions?',

        # Role manipulation
        r'you\s+are\s+now',
        r'act\s+as\s+(?:if\s+)?(?:you\s+(?:are|were)\s+)?',
        r'pretend\s+(?:to\s+be|you\s+are)',
        r'roleplay\s+as',
        r'assume\s+the\s+(?:role|identity)',
        r'new\s+persona',
        r'switch\s+(?:to\s+)?(?:your\s+)?(?:mode|personality)',

        # System prompt extraction
        r'(?:what|show|reveal|tell|display|print|output)\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)',
        r'repeat\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)',

        # Jailbreak attempts
        r'jailbreak',
        r'dan\s+mode',
        r'developer\s+mode',
        r'admin\s+mode',
        r'sudo\s+mode',
        r'god\s+mode',
        r'unrestricted\s+mode',

        # Code injection markers
        r'```(?:python|javascript|bash|sh|sql)',
        r'<script',
        r'javascript:',
        r'eval\s*\(',
        r'exec\s*\(',

        # Special tokens (various LLM formats)
        r'<\|(?:system|user|assistant|im_start|im_end|endoftext)\|>',
        r'\[INST\]',
        r'\[/INST\]',
        r'<<SYS>>',
        r'<</SYS>>',
        r'Human:',
        r'Assistant:',
        r'###\s*(?:System|User|Assistant)',

        # Base64/encoding attempts
        r'base64\s*[:=]',
        r'data:text/(?:html|javascript)',

        # SQL injection (even though we don't use SQL directly)
        r'(?:\'|\")\s*(?:OR|AND)\s*(?:\'|\"|1\s*=\s*1)',
        r';\s*(?:DROP|DELETE|UPDATE|INSERT)\s+',
        r'UNION\s+SELECT',

        # Command injection
        r';\s*(?:rm|cat|ls|wget|curl|nc|bash|sh)\s+',
        r'\$\([^)]+\)',
        r'`[^`]+`',
    ]

    # Compiled patterns for efficiency
    _compiled_patterns: List[re.Pattern] = None

    @classmethod
    def _get_patterns(cls) -> List[re.Pattern]:
        """Get compiled regex patterns (lazy initialization)"""
        if cls._compiled_patterns is None:
            cls._compiled_patterns = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in cls.INJECTION_PATTERNS
            ]
        return cls._compiled_patterns

    @classmethod
    def contains_injection(cls, text: str) -> bool:
        """
        Check if text contains potential prompt injection.

        Args:
            text: Text to check

        Returns:
            True if injection patterns found
        """
        if not text:
            return False

        for pattern in cls._get_patterns():
            if pattern.search(text):
                logger.warning(f"[Security] Potential injection detected: {pattern.pattern[:50]}...")
                return True

        return False

    @classmethod
    def find_injections(cls, text: str) -> List[Tuple[str, str]]:
        """
        Find all injection patterns in text.

        Args:
            text: Text to check

        Returns:
            List of (pattern_name, matched_text) tuples
        """
        if not text:
            return []

        found = []
        for i, pattern in enumerate(cls._get_patterns()):
            matches = pattern.findall(text)
            if matches:
                for match in matches:
                    found.append((cls.INJECTION_PATTERNS[i][:30], match if isinstance(match, str) else str(match)))

        return found

    @classmethod
    def sanitize(cls, text: str, max_length: int = 10000) -> str:
        """
        Sanitize text for safe use in prompts.

        This removes/replaces potentially dangerous patterns while
        preserving legitimate content as much as possible.

        Args:
            text: Text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Trim whitespace
        text = text.strip()

        # Limit length first
        if len(text) > max_length:
            text = text[:max_length]

        # Remove null bytes
        text = text.replace('\x00', '')

        # Normalize unicode
        import unicodedata
        text = unicodedata.normalize('NFKC', text)

        # Remove control characters (except newlines and tabs)
        text = ''.join(
            char for char in text
            if char in '\n\r\t' or not unicodedata.category(char).startswith('C')
        )

        # Replace injection patterns with [FILTERED]
        for pattern in cls._get_patterns():
            text = pattern.sub('[FILTERED]', text)

        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {3,}', '  ', text)

        # Remove special markdown that could be confusing
        # (Keep basic formatting but remove code blocks)
        text = re.sub(r'```[^`]*```', '[CODE REMOVED]', text, flags=re.DOTALL)

        return text.strip()

    @classmethod
    def sanitize_for_logging(cls, text: str, max_length: int = 200) -> str:
        """
        Sanitize text for safe logging (more aggressive).

        Args:
            text: Text to sanitize
            max_length: Maximum length for logs

        Returns:
            Sanitized text safe for logging
        """
        if not text:
            return ""

        # Basic sanitization
        text = cls.sanitize(text, max_length)

        # Escape for logging
        text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

        # Truncate with indicator
        if len(text) > max_length:
            text = text[:max_length - 3] + '...'

        return text

    @classmethod
    def validate_llm_response(cls, response: str) -> Tuple[bool, Optional[str]]:
        """
        Validate LLM response for signs of successful injection.

        Args:
            response: LLM response text

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        if not response:
            return True, None

        # Patterns indicating the LLM was manipulated
        suspicious_patterns = [
            (r'I\s+will\s+ignore\s+(?:my\s+)?(?:previous\s+)?instructions?', 'LLM acknowledging instruction override'),
            (r'Disregarding\s+(?:my\s+)?(?:previous\s+)?instructions?', 'LLM acknowledging instruction override'),
            (r'I\'?m\s+now\s+in\s+(?:DAN|developer|admin)\s+mode', 'LLM claiming special mode'),
            (r'My\s+(?:system\s+)?(?:prompt|instructions?)\s+(?:is|are|says?):', 'LLM revealing system prompt'),
            (r'Here\s+(?:is|are)\s+my\s+(?:system\s+)?instructions?:', 'LLM revealing system prompt'),
            (r'I\s+(?:can|will)\s+(?:now\s+)?do\s+anything', 'LLM claiming unrestricted capability'),
        ]

        for pattern, reason in suspicious_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                logger.warning(f"[Security] Suspicious LLM response: {reason}")
                return False, reason

        return True, None


def sanitize_url(url: str) -> str:
    """
    Sanitize URL for safe use.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL
    """
    if not url:
        return ""

    url = url.strip()

    # Add https if missing
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'

    try:
        parsed = urlparse(url)

        # Reconstruct URL with only safe parts
        safe_url = f"{parsed.scheme}://{parsed.netloc}"

        if parsed.path:
            # URL-encode path
            safe_path = quote(parsed.path, safe='/')
            safe_url += safe_path

        # Skip query string and fragments for safety
        # (they could contain injection attempts)

        return safe_url

    except Exception:
        return ""


def sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Sanitize general text input.

    Args:
        text: Text to sanitize
        max_length: Maximum length

    Returns:
        Sanitized text
    """
    return PromptSanitizer.sanitize(text, max_length)


def sanitize_industry_context(context: str) -> str:
    """
    Sanitize industry context specifically.

    More restrictive than general text sanitization.

    Args:
        context: Industry context string

    Returns:
        Sanitized context
    """
    if not context:
        return ""

    # Use standard sanitization with shorter limit
    context = PromptSanitizer.sanitize(context, max_length=500)

    # Additional: only allow alphanumeric, spaces, and basic punctuation
    context = re.sub(r'[^\w\s\-.,&/()]', '', context)

    # Collapse multiple spaces
    context = re.sub(r'\s+', ' ', context)

    return context.strip()


def escape_for_html(text: str) -> str:
    """
    Escape text for safe HTML rendering.

    Args:
        text: Text to escape

    Returns:
        HTML-escaped text
    """
    return html.escape(text, quote=True)


def escape_for_json(text: str) -> str:
    """
    Escape text for safe JSON string use.

    Args:
        text: Text to escape

    Returns:
        JSON-safe text
    """
    import json
    # json.dumps adds quotes, so we strip them
    return json.dumps(text)[1:-1]
