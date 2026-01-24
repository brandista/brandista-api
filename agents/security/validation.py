# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Input Validation
Pydantic schemas for API input validation

Version: 3.0.0
"""

import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, model_validator, HttpUrl


class ValidationError(Exception):
    """Custom validation error with details"""
    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        self.message = message
        self.field = field
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': 'validation_error',
            'message': self.message,
            'field': self.field,
            'details': self.details
        }


class AnalysisInputSchema(BaseModel):
    """
    Validated input for analysis requests.

    All user input should pass through this schema before being used.
    """

    url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        description="URL to analyze"
    )

    competitor_urls: List[str] = Field(
        default_factory=list,
        max_length=10,  # Max 10 competitors
        description="Optional competitor URLs"
    )

    language: str = Field(
        default="fi",
        description="Analysis language (fi or en)"
    )

    industry_context: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional industry context"
    )

    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="User ID for context tracking"
    )

    revenue_input: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional revenue data"
    )

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate and normalize URL"""
        v = v.strip()

        # Add https if missing
        if not v.startswith(('http://', 'https://')):
            v = f'https://{v}'

        # Parse URL
        try:
            parsed = urlparse(v)
        except Exception:
            raise ValueError('Invalid URL format')

        # Check scheme
        if parsed.scheme not in ('http', 'https'):
            raise ValueError('URL must use http or https')

        # Check hostname exists
        if not parsed.hostname:
            raise ValueError('URL must have a valid hostname')

        # Check for localhost/internal IPs (SSRF protection)
        hostname = parsed.hostname.lower()
        blocked_patterns = [
            'localhost',
            '127.0.0.1',
            '0.0.0.0',
            '169.254.',  # Link-local
            '10.',       # Private
            '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.',
            '192.168.',  # Private
            '[::1]',     # IPv6 localhost
            'metadata.google',  # Cloud metadata
            '169.254.169.254',  # AWS metadata
        ]

        for pattern in blocked_patterns:
            if hostname.startswith(pattern) or hostname == pattern.rstrip('.'):
                raise ValueError(f'URL cannot point to internal/local addresses')

        # Check for valid TLD (basic check)
        if '.' not in hostname:
            raise ValueError('URL must have a valid domain with TLD')

        return v

    @field_validator('competitor_urls')
    @classmethod
    def validate_competitor_urls(cls, v: List[str]) -> List[str]:
        """Validate competitor URLs"""
        validated = []

        for url in v:
            url = url.strip()
            if not url:
                continue

            # Add https if missing
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'

            try:
                parsed = urlparse(url)
                if parsed.hostname:
                    validated.append(url)
            except Exception:
                continue  # Skip invalid URLs silently

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for url in validated:
            normalized = urlparse(url).netloc.lower()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(url)

        return unique[:10]  # Max 10 competitors

    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language code"""
        v = v.strip().lower()
        allowed = {'fi', 'en', 'sv'}

        if v not in allowed:
            raise ValueError(f'Language must be one of: {", ".join(allowed)}')

        return v

    @field_validator('industry_context')
    @classmethod
    def validate_industry_context(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize industry context"""
        if v is None:
            return None

        v = v.strip()
        if not v:
            return None

        # Check for prompt injection patterns
        from .sanitization import PromptSanitizer

        if PromptSanitizer.contains_injection(v):
            raise ValueError('Industry context contains invalid characters or patterns')

        # Sanitize
        v = PromptSanitizer.sanitize(v)

        # Limit length
        return v[:500]

    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate user ID format"""
        if v is None:
            return None

        v = v.strip()
        if not v:
            return None

        # Only allow alphanumeric, dash, underscore
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('User ID can only contain letters, numbers, dash and underscore')

        return v[:100]

    @field_validator('revenue_input')
    @classmethod
    def validate_revenue_input(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate revenue input structure"""
        if v is None:
            return None

        # Only allow specific keys
        allowed_keys = {'annual_revenue', 'monthly_revenue', 'currency', 'source'}

        filtered = {}
        for key, value in v.items():
            if key in allowed_keys:
                # Validate numeric values
                if key in ('annual_revenue', 'monthly_revenue'):
                    try:
                        filtered[key] = max(0, min(int(value), 10_000_000_000))  # Max 10B
                    except (ValueError, TypeError):
                        continue
                elif key == 'currency':
                    if isinstance(value, str) and len(value) <= 3:
                        filtered[key] = value.upper()
                elif key == 'source':
                    if isinstance(value, str) and len(value) <= 50:
                        filtered[key] = value

        return filtered if filtered else None

    @model_validator(mode='after')
    def validate_url_not_in_competitors(self):
        """Ensure main URL is not in competitor list"""
        if not self.competitor_urls:
            return self

        main_domain = urlparse(self.url).netloc.lower()

        # Filter out main domain from competitors
        self.competitor_urls = [
            url for url in self.competitor_urls
            if urlparse(url).netloc.lower() != main_domain
        ]

        return self


def validate_analysis_input(data: Dict[str, Any]) -> AnalysisInputSchema:
    """
    Validate analysis input data.

    Args:
        data: Raw input data from API request

    Returns:
        Validated AnalysisInputSchema

    Raises:
        ValidationError: If validation fails
    """
    try:
        return AnalysisInputSchema(**data)
    except Exception as e:
        # Convert Pydantic errors to our ValidationError
        if hasattr(e, 'errors'):
            errors = e.errors()
            if errors:
                first_error = errors[0]
                field = '.'.join(str(loc) for loc in first_error.get('loc', []))
                message = first_error.get('msg', str(e))
                raise ValidationError(message=message, field=field, details={'errors': errors})

        raise ValidationError(message=str(e))
