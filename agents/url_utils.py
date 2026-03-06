# -*- coding: utf-8 -*-
"""
Lightweight URL utility functions.

Extracted from main.py so that agent modules can use them
without pulling in the full main module (and its heavy dependencies).
"""

from urllib.parse import urlparse


def clean_url(url: str) -> str:
    """Normalize URL: add https:// if missing, strip trailing slash."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip('/')


def get_domain_from_url(url: str) -> str:
    """Extract domain (netloc) from a URL string."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]
