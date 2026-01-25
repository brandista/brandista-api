#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista API Configuration
Centralized configuration management for all settings and environment variables
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

# ============================================================================
# VERSION INFO
# ============================================================================

APP_VERSION = "6.5.0"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = "Production-ready website analysis with configurable scoring system and comprehensive SPA support."

# ============================================================================
# SCORING CONFIGURATION
# ============================================================================

@dataclass
class ScoringConfig:
    """Configurable scoring weights and thresholds"""
    weights: Dict[str, int] = None
    content_thresholds: Dict[str, int] = None
    technical_thresholds: Dict[str, Any] = None
    seo_thresholds: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.weights is None:
            self.weights = {
                'security': 15, 'seo_basics': 20, 'content': 20,
                'technical': 15, 'mobile': 15, 'social': 10, 'performance': 5
            }
        
        if self.content_thresholds is None:
            self.content_thresholds = {
                'excellent': 3000, 'good': 2000, 'fair': 1500, 'basic': 800, 'minimal': 300
            }
        
        if self.technical_thresholds is None:
            self.technical_thresholds = {
                'ssl_score': 20, 'mobile_viewport_score': 15, 'mobile_responsive_score': 5,
                'analytics_score': 10, 'meta_tags_max_score': 15, 'structured_data_multiplier': 2,
                'security_headers': {'csp': 4, 'x_frame_options': 3, 'strict_transport': 3}
            }
        
        if self.seo_thresholds is None:
            self.seo_thresholds = {
                'title_optimal_range': (30, 60), 'title_acceptable_range': (20, 70),
                'meta_desc_optimal_range': (120, 160), 'meta_desc_acceptable_range': (80, 200),
                'h1_optimal_count': 1,
                'scores': {
                    'title_optimal': 5, 'title_acceptable': 3, 'title_basic': 1,
                    'meta_desc_optimal': 5, 'meta_desc_acceptable': 3, 'meta_desc_basic': 1,
                    'canonical': 2, 'hreflang': 1, 'clean_urls': 2
                }
            }

def load_scoring_config() -> ScoringConfig:
    """Load scoring configuration from file or environment"""
    config_file = Path('scoring_config.json')
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return ScoringConfig(**config_data)
        except Exception as e:
            logging.warning(f"Failed to load scoring config: {e}")
    return ScoringConfig()

# Global scoring configuration
SCORING_CONFIG = load_scoring_config()

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

SECRET_KEY = os.getenv("SECRET_KEY", "brandista-key-" + os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# ============================================================================
# PERFORMANCE SETTINGS
# ============================================================================

CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "100"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
DEFAULT_USER_LIMIT = int(os.getenv("DEFAULT_USER_LIMIT", "1"))

# ============================================================================
# SPA & CONTENT FETCH CONFIGURATION
# ============================================================================

SPA_CACHE_TTL = int(os.getenv("SPA_CACHE_TTL", "3600"))
CONTENT_FETCH_MODE = os.getenv("CONTENT_FETCH_MODE", "aggressive")
CAPTURE_XHR = os.getenv("CAPTURE_XHR", "1") == "1"
MAX_XHR_BYTES = int(os.getenv("MAX_XHR_BYTES", "1048576"))
BLOCK_HEAVY_RESOURCES = os.getenv("BLOCK_HEAVY_RESOURCES", "1") == "1"
COOKIE_AUTO_DISMISS = os.getenv("COOKIE_AUTO_DISMISS", "1") == "1"
COOKIE_SELECTORS = os.getenv(
    "COOKIE_SELECTORS",
    "button[aria-label*='accept'],button:has-text('Accept'),button:has-text('Hyväksy')"
)

# SPA Configuration
SPA_MAX_SCROLL_STEPS = int(os.getenv("SPA_MAX_SCROLL_STEPS", "15"))
SPA_SCROLL_PAUSE_MS = int(os.getenv("SPA_SCROLL_PAUSE_MS", "1000"))
SPA_EXTRA_WAIT_MS = int(os.getenv("SPA_EXTRA_WAIT_MS", "5000"))
SPA_WAIT_FOR_SELECTOR = os.getenv("SPA_WAIT_FOR_SELECTOR", "")

# ============================================================================
# PLAYWRIGHT SETTINGS
# ============================================================================

PLAYWRIGHT_ENABLED = os.getenv("PLAYWRIGHT_ENABLED", "false").lower() == "true"
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
PLAYWRIGHT_WAIT_FOR = os.getenv("PLAYWRIGHT_WAIT_FOR", "networkidle")

# ============================================================================
# USER AGENT
# ============================================================================

USER_AGENT = os.getenv("USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ============================================================================
# RATE LIMITING
# ============================================================================

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

# ============================================================================
# EXTERNAL API KEYS
# ============================================================================

# Google Search
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "171a60959e6cb4d76")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Redis
REDIS_URL = os.getenv("REDIS_URL")

# ============================================================================
# CORS SETTINGS
# ============================================================================

ALLOWED_ORIGINS = ["*"]
