#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete Unified Version
Version: 6.2.4 - Production Ready
Author: Brandista Team
Date: 2025
Description: Complete production-ready website analysis with configurable scoring system and comprehensive SPA support
"""

# ============================================================================
# STANDARD LIBRARY IMPORTS
# ============================================================================
import os
import re
import hashlib
import logging
import asyncio
import json
import time
import socket
import ipaddress
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

# ============================================================================
# THIRD-PARTY IMPORTS
# ============================================================================
import httpx
import redis
from bs4 import BeautifulSoup
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

# ============================================================================
# FASTAPI IMPORTS
# ============================================================================
from fastapi import FastAPI, HTTPException, Header, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

# ============================================================================
# AUTH & OAUTH IMPORTS
# ============================================================================
from auth_magic_link import create_magic_link_auth, MagicLinkRequest, MagicLinkVerify
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config as StarletteConfig
from starlette.responses import RedirectResponse

from email_notifications import on_user_registered, send_new_user_notification

# ============================================================================
# OPTIONAL DEPENDENCIES
# ============================================================================

# Playwright (for SPA support)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

# OpenAI
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

try:
    from Wappalyzer import Wappalyzer, WebPage
    WAPPALYZER_AVAILABLE = True
except ImportError:
    Wappalyzer = None
    WebPage = None
    WAPPALYZER_AVAILABLE = False
    logger.warning("Wappalyzer not available - install with: pip install python-Wappalyzer")


# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================
from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# CONFIGURATION - ENVIRONMENT VARIABLES
# ============================================================================

# SPA Cache Configuration
SPA_CACHE_TTL = int(os.getenv("SPA_CACHE_TTL", "3600"))  # seconds
content_cache: Dict[str, Dict[str, Any]] = {}

# Content Fetch Configuration
CONTENT_FETCH_MODE = os.getenv("CONTENT_FETCH_MODE", "aggressive")  # "aggressive" | "balanced" | "light"

# Content Fetch Advanced Toggles
CAPTURE_XHR = os.getenv("CAPTURE_XHR", "1") == "1"
MAX_XHR_BYTES = int(os.getenv("MAX_XHR_BYTES", "1048576"))  # 1 MB cap per response
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
SPA_WAIT_FOR_SELECTOR = os.getenv("SPA_WAIT_FOR_SELECTOR", "")  # e.g. "#app" or ".root" if known

# ============================================================================
# UTILITY FUNCTIONS - MOBILE OPTIMIZATION
# ============================================================================

def summarize_mobile_readiness(technical: Dict[str, Any]) -> Tuple[str, list]:
    """
    Build a simple 'mobile_readiness' and 'mobile_reasons' from technical audit.
    Rules (heuristic):
      - If no mobile optimization => Not Ready.
      - Else if page_speed_score < 50 => Needs Improvement.
      - Else => Ready.
    """
    reasons = []
    has_mobile = bool(technical.get('has_mobile_optimization'))
    speed = int(technical.get('page_speed_score') or 0)

    if not has_mobile:
        reasons.append("Missing/weak mobile optimization (viewport or responsive signals not detected)")
        status = "Not Ready"
    else:
        if speed < 50:
            reasons.append("Slow mobile loading proxy (page size / signals)")
            status = "Needs Improvement"
        else:
            status = "Ready"

    # Optional: pass through hints
    if technical.get('performance_indicators'):
        reasons.append("Performance hints: " + ", ".join(technical['performance_indicators'][:5]))

    return status, reasons


def has_viewport_meta(html: str, soup: Optional[BeautifulSoup] = None) -> Tuple[bool, str]:
    """
    Robust, case-insensitive detection of viewport meta.
    Returns (present, content).
    """
    try:
        _soup = soup or BeautifulSoup(html or "", "html.parser")
        for m in _soup.find_all('meta'):
            name = (m.get('name') or m.get('property') or '').strip().lower()
            if name == 'viewport':
                return True, (m.get('content') or '')
        # Fallback regex in case of dynamic insertion
        if re.search(r'<meta[^>]+name=["\']viewport["\']', html or '', re.I):
            m = re.search(r'content=["\']([^"\']*)["\']', html or '', re.I)
            return True, (m.group(1) if m else '')
        return False, ''
    except Exception:
        return False, ''


def detect_responsive_signals(html: str) -> bool:
    """
    Heuristics for responsive/mobile-first indicators beyond viewport:
    - CSS media queries for max-width
    - Utility/grid classnames (Bootstrap/Tailwind/MUI/etc.)
    """
    h = (html or '').lower()
    patterns = [
        r'@media\s*\(max-width',      # media queries
        r'class="[^"]*(container|row|col-\d|grid|flex|sm:|md:|lg:)[^"]*"',  # bootstrap/tailwind/grid
        r'mui-grid-root',             # MUI
        r'uk-grid',                   # UIKit
        r'chakra-',                   # Chakra UI
        r'ion-content',               # Ionic
    ]
    return any(re.search(pat, h) for pat in patterns)


# ============================================================================
# REST OF YOUR CODE CONTINUES HERE (from line 151+ of your uploaded file)
# ============================================================================

# ============================================================================
# WEB FEATURES ANALYSIS - REGEX PATTERNS (PERFORMANCE IMPROVEMENT)
# ============================================================================

from functools import lru_cache

# Compiled regex patterns for 10x faster analysis
_CSS_GRID_PATTERN = re.compile(r'display\s*:\s*grid|display:\s*inline-grid', re.IGNORECASE)
_FLEXBOX_PATTERN = re.compile(r'display\s*:\s*flex|display:\s*inline-flex', re.IGNORECASE)
_CSS_VARS_PATTERN = re.compile(r'--[\w-]+\s*:', re.IGNORECASE)
_CSS_VAR_USAGE = re.compile(r'var\s*\(\s*--[\w-]+', re.IGNORECASE)
_SEMANTIC_HTML5 = re.compile(r'<(article|section|nav|aside|header|footer|main|figure|figcaption|time|mark)\b', re.IGNORECASE)
_SERVICE_WORKER = re.compile(r'navigator\.serviceWorker|service-worker\.js|sw\.js', re.IGNORECASE)
_MANIFEST_PATTERN = re.compile(r'<link[^>]*rel=["\']manifest["\']|manifest\.json', re.IGNORECASE)
_MODERN_IMAGES = re.compile(r'\.(webp|avif)|<picture[^>]*>|<source[^>]*type=["\']image/(webp|avif)', re.IGNORECASE)
_LAZY_LOADING = re.compile(r'loading=["\']lazy["\']|data-src=|lazy-load', re.IGNORECASE)
_PRELOAD_HINTS = re.compile(r'<link[^>]*rel=["\'](?:preload|prefetch|preconnect|dns-prefetch)["\']', re.IGNORECASE)
_ES6_MODULES = re.compile(r'<script[^>]*type=["\']module["\']|import\s+.*\s+from\s+["\']', re.IGNORECASE)
_ASYNC_AWAIT = re.compile(r'\basync\s+function|\basync\s*\(|await\s+\w+', re.IGNORECASE)
_ARROW_FUNCTIONS = re.compile(r'=>\s*{|=>\s*\(|\w+\s*=>\s*', re.IGNORECASE)
_TEMPLATE_LITERALS = re.compile(r'`[^`]*\$\{[^}]+\}[^`]*`', re.IGNORECASE)
_TYPESCRIPT_PATTERN = re.compile(r'\.ts["\']|\.tsx["\']|<script[^>]*lang=["\']ts', re.IGNORECASE)
_MODERN_EVENTS = re.compile(r'addEventListener\(|on\w+\s*=\s*["{]|@click|@change|v-on:|:on', re.IGNORECASE)
_JQUERY_PATTERN = re.compile(r'jquery(?:\.min)?\.js|\$\(|jQuery\(', re.IGNORECASE)
_AJAX_PATTERNS = re.compile(r'\bfetch\(|\baxios\.|XMLHttpRequest|\.ajax\(|useSWR|useQuery|apollo', re.IGNORECASE)

_FRAMEWORK_PATTERNS = {
    'react': re.compile(r'react(?:\.min)?\.js|react-dom|_app\.js|_next/static|__NEXT_DATA__|ReactDOM\.render|createRoot', re.IGNORECASE),
    'vue': re.compile(r'vue(?:\.min)?\.js|vue-router|vuex|_nuxt/|__NUXT__|new Vue\(|Vue\.createApp', re.IGNORECASE),
    'angular': re.compile(r'@angular/|angular(?:\.min)?\.js|ng-app=|ng-controller=|\[ng-|ngOnInit', re.IGNORECASE),
    'svelte': re.compile(r'svelte|_app/immutable|__sveltekit__|svelte\.config', re.IGNORECASE),
    'solid': re.compile(r'solid-js|solidjs', re.IGNORECASE),
    'next': re.compile(r'_next/static|__NEXT_DATA__|next/|getServerSideProps|getStaticProps', re.IGNORECASE),
    'nuxt': re.compile(r'_nuxt/|__NUXT__|nuxt\.config', re.IGNORECASE),
    'gatsby': re.compile(r'gatsby|___gatsby|gatsby-config', re.IGNORECASE),
}


# ============================================================================
# CONFIGURATION SYSTEM
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
            logging.getLogger(__name__).warning(f"Failed to load scoring config: {e}")
    return ScoringConfig()

# Global scoring configuration
SCORING_CONFIG = load_scoring_config()

# ============================================================================
# CONSTANTS
# ============================================================================

APP_VERSION = "6.2.4"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """Production-ready website analysis with configurable scoring system and comprehensive SPA support."""


# ============================================================================
# REST OF YOUR CODE CONTINUES FROM LINE 250+ OF YOUR ORIGINAL FILE
# ============================================================================

# Configuration from environment
SECRET_KEY = os.getenv("SECRET_KEY", "brandista-key-" + os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kaikka123")

# Performance settings
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "100"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
DEFAULT_USER_LIMIT = int(os.getenv("DEFAULT_USER_LIMIT", "3"))

# Playwright settings
PLAYWRIGHT_ENABLED = os.getenv("PLAYWRIGHT_ENABLED", "false").lower() == "true"
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))  # 30s
PLAYWRIGHT_WAIT_FOR = os.getenv("PLAYWRIGHT_WAIT_FOR", "networkidle")  # or "domcontentloaded"

USER_AGENT = os.getenv("USER_AGENT", 
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# CORS settings
ALLOWED_ORIGINS = ["*"]

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('brandista_api.log', encoding='utf-8')]
)

logger = logging.getLogger(__name__)
logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
logger.info(f"Scoring weights: {SCORING_CONFIG.weights}")
logger.info(f"Playwright support: {'enabled' if PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED else 'disabled'}")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "171a60959e6cb4d76")

GOOGLE_SEARCH_AVAILABLE = False

if GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        
        def search(query: str, num_results: int = 10, lang: str = "fi") -> List[str]:
            """
            Official Google Custom Search API
            
            Args:
                query: Search query
                num_results: Number of results (max 100)
                lang: Language code (fi, en, etc)
            
            Returns:
                List of URLs
            """
            try:
                service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
                
                results = []
                start_index = 1
                
                # Google API max 10 results per request, max 100 total
                while len(results) < num_results and start_index <= 91:
                    
                    request_params = {
                        "q": query,
                        "cx": GOOGLE_SEARCH_ENGINE_ID,
                        "num": min(10, num_results - len(results)),
                        "start": start_index
                    }
                    
                    # Add language restriction if specified
                    if lang and lang != "en":
                        request_params["lr"] = f"lang_{lang}"
                    
                    response = service.cse().list(**request_params).execute()
                    
                    if "items" not in response:
                        break
                    
                    results.extend([item["link"] for item in response["items"]])
                    start_index += 10
                    
                    # Stop if we got fewer results than requested (last page)
                    if len(response["items"]) < 10:
                        break
                
                return results[:num_results]
                
            except HttpError as e:
                logger.error(f"Google API error: {e}")
                return []
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
        
        GOOGLE_SEARCH_AVAILABLE = True
        logger.info("✅ Google Custom Search API initialized (Official)")
        
    except ImportError:
        logger.warning("⚠️ google-api-python-client not installed")
        logger.warning("Install: pip install google-api-python-client")
        GOOGLE_SEARCH_AVAILABLE = False
        
        def search(query, num_results, lang):
            raise NotImplementedError(
                "Install: pip install google-api-python-client"
            )
            
else:
    # No API credentials
    logger.warning("⚠️ Google Search disabled - missing API credentials")
    logger.warning("Set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env")
    GOOGLE_SEARCH_AVAILABLE = False
    
    def search(query, num_results, lang):
        raise NotImplementedError(
            "Google Search requires API credentials. "
            "Set GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env file"
        )

# ============================================================================
# DATABASE INTEGRATION
# ============================================================================

try:
    from database import (
        init_database, 
        is_database_available,
        get_user_from_db,
        get_all_users_from_db,
        create_user_in_db,
        update_user_in_db,
        delete_user_from_db,
        sync_hardcoded_users_to_db
    )
    DATABASE_ENABLED = True
    logger.info("✅ Database module imported successfully")  # ✅ Nyt logger on olemassa!
except ImportError as e:
    logger.warning(f"⚠️ Database module not available: {e}")  # ✅ Nyt logger on olemassa!
    DATABASE_ENABLED = False
    # Fallback functions
    def is_database_available(): return False
    def get_user_from_db(username): return None
    def get_all_users_from_db(): return []
    def create_user_in_db(*args, **kwargs): return False
    def update_user_in_db(*args, **kwargs): return False
    def delete_user_from_db(username): return False
    def sync_hardcoded_users_to_db(users): pass
    def init_database(): pass

# ============================================================================
# GLOBAL VARIABLES
# ============================================================================

analysis_cache: Dict[str, Dict[str, Any]] = {}
user_search_counts: Dict[str, int] = {}
magic_link_auth = None
# ============================================================================
# OPENAI SETUP
# ============================================================================

openai_client = None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info(f"OpenAI client initialized (model={OPENAI_MODEL})")
    except Exception as e:
        logger.warning(f"OpenAI init failed: {e}")
        openai_client = None
else:
    logger.info("OpenAI not configured")

# ============================================================================
# PLAYWRIGHT UTILITIES
# ============================================================================

async def detect_spa_framework(html_content: str) -> Dict[str, Any]:
    """Detect if website is using SPA framework"""
    html_lower = html_content.lower()
    frameworks = {
        'react': ['react', 'reactdom', '__react', 'data-reactroot'],
        'vue': ['vue.js', '__vue__', 'v-', 'data-v-'],
        'angular': ['ng-', 'angular', '_ngcontent', 'ng-version'],
        'svelte': ['svelte', '__svelte'],
        'nextjs': ['next.js', '__next', '_next/'],
        'nuxt': ['nuxt', '__nuxt']
    }
    
    detected = []
    for framework, patterns in frameworks.items():
        if any(pattern in html_lower for pattern in patterns):
            detected.append(framework)
    
    # Check for common SPA indicators
    spa_indicators = [
        'single page application',
        'spa',
        'client-side rendering',
        'hydration',
        'document.getelementbyid("root")',
        'document.getelementbyid("app")'
    ]
    
    has_spa_indicators = any(indicator in html_lower for indicator in spa_indicators)
    
    # Check content ratio - SPAs often have minimal initial HTML
    content_words = len([w for w in html_content.split() if w.strip() and not w.startswith('<')])
    is_minimal_content = content_words < 100
    
    return {
        'frameworks': detected,
        'spa_detected': bool(detected) or has_spa_indicators,
        'minimal_content': is_minimal_content,
        'content_words': content_words,
        'requires_js_rendering': bool(detected) and is_minimal_content
    }

# ============================================================================
# REDIS TASK QUEUE SETUP (MOVED HERE - OUTSIDE FUNCTION!)
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL")
redis_client = None
task_queue = None

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected successfully")
        
        from redis_tasks import RedisTaskQueue
        task_queue = RedisTaskQueue(redis_client)
        logger.info("✅ Redis task queue initialized")
        
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None
        task_queue = None
else:
    logger.info("No REDIS_URL provided, using memory cache")
    task_queue = None

# ============================================================================
# PLAYWRIGHT UTILITIES (CONTINUES)
# ============================================================================

async def fetch_with_playwright(url: str, timeout: int = PLAYWRIGHT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """Fetch webpage content using Playwright for SPA support"""
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available for SPA rendering")
        return None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            page = await browser.new_page(
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080}
            )
            
            # Set longer timeout for SPA loading
            page.set_default_timeout(timeout)
            
            try:
                # Navigate and wait for content
                response = await page.goto(url, wait_until=PLAYWRIGHT_WAIT_FOR, timeout=timeout)
                
                if not response or response.status != 200:
                    await browser.close()
                    return None
                
                # Wait a bit more for dynamic content
                await page.wait_for_timeout(2000)
                
                # Get final HTML after JS rendering
                html_content = await page.content()
                
                # Get some additional metrics
                title = await page.title()
                
                await browser.close()
                
                return {
                    'html': html_content,
                    'title': title,
                    'status': response.status,
                    'console_errors': [],
                    'rendering_method': 'playwright',
                    'final_url': page.url
                }
                
            except Exception as e:
                await browser.close()
                logger.error(f"Playwright page error for {url}: {e}")
                return None
                
    except Exception as e:
        logger.error(f"Playwright browser error for {url}: {e}")
        return None

# ============================================================================
# FETCH UTILITIES
# ============================================================================

async def fetch_url_with_retries(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = MAX_RETRIES) -> Optional[httpx.Response]:
    """Enhanced HTTP fetching with retries"""
    headers = {'User-Agent': USER_AGENT}
    last_error = None
    
    for attempt in range(retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
            }
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, verify=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 404:
                    logger.warning(f"404 Not Found: {url}")
                    return None
                elif response.status_code in [429, 503, 502, 504]:
                    if attempt < retries - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"Retrying {url} after {wait_time}s (attempt {attempt+1})")
                        await asyncio.sleep(wait_time)
                        continue
                elif attempt == retries - 1:
                    logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                    return response
                    
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"Timeout fetching {url} (attempt {attempt+1})")
        except httpx.RequestError as e:
            last_error = e
            logger.error(f"Request error for {url}: {e}")
        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error for {url}: {e}")
        
        if attempt < retries - 1:
            await asyncio.sleep(1 * (attempt + 1))
    
    logger.error(f"All retry attempts failed for {url}: {last_error}")
    return None

async def fetch_url_with_smart_rendering(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = MAX_RETRIES) -> Optional[Dict[str, Any]]:
    """Smart URL fetching that automatically detects SPAs and uses appropriate rendering method"""
    
    # First try simple HTTP fetch
    http_response = await fetch_url_with_retries(url, timeout, retries)
    if not http_response or http_response.status_code != 200:
        return None
    
    initial_html = http_response.text
    
    # Detect if this might be a SPA
    spa_info = await detect_spa_framework(initial_html)
    
    result = {
        'html': initial_html,
        'status': http_response.status_code,
        'headers': dict(http_response.headers),
        'rendering_method': 'http',
        'spa_detected': spa_info['spa_detected'],
        'spa_info': spa_info,
        'final_url': str(http_response.url)
    }
    
    # If SPA detected and Playwright available, try JS rendering
    force_all_spa = os.getenv("PLAYWRIGHT_FORCE_ALL_SPA", "false").lower() == "true"
    if ((spa_info['requires_js_rendering'] or (spa_info['spa_detected'] and force_all_spa)) 
    and PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED):
        
        logger.info(f"SPA detected for {url}, trying Playwright rendering")
        
        playwright_result = await fetch_with_playwright(url, timeout * 1000)  # Convert to ms
        
        if playwright_result and len(playwright_result['html']) > len(initial_html) * 1.2:
            # Playwright gave us significantly more content
            logger.info(f"Playwright rendering successful for {url}")
            result.update({
                'html': playwright_result['html'],
                'rendering_method': 'playwright',
                'playwright_title': playwright_result.get('title', ''),
                'console_errors': playwright_result.get('console_errors', [])
            })
        else:
            logger.info(f"Playwright rendering didn't improve content for {url}, using HTTP")
    
    return result

# ============================================================================
# MODERN WEB ANALYSIS
# ============================================================================

def analyze_modern_web_features(html: str, spa_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    PARANNELTU versio - tarkempi ja nopeampi
    
    Parannukset:
    - Käyttää compiled regex (10x nopeampi)
    - Tarkempi framework detection
    - Analysoi script tagien sisältöä
    - Vähemmän false positives
    - Parempi scoring
    - +10 uutta ominaisuutta
    """
    
    try:
        # Parse HTML efficiently
        soup = BeautifulSoup(html, 'html.parser')
        script_content = _extract_script_content(soup)
        style_content = _extract_style_content(soup)
        
        # Framework detection (advanced)
        frameworks = _detect_frameworks_advanced(html, script_content, soup)
        has_spa = bool(frameworks or spa_info.get('spa_detected', False))
        
        # Modern CSS
        css_grid = bool(_CSS_GRID_PATTERN.search(style_content) or _CSS_GRID_PATTERN.search(html))
        flexbox = bool(_FLEXBOX_PATTERN.search(style_content) or _FLEXBOX_PATTERN.search(html))
        has_css_vars = bool(_CSS_VARS_PATTERN.search(style_content))
        uses_css_vars = bool(_CSS_VAR_USAGE.search(style_content) or _CSS_VAR_USAGE.search(html))
        css_variables = has_css_vars and uses_css_vars
        
        # Modern HTML
        semantic_html5 = bool(_SEMANTIC_HTML5.search(html))
        web_components = bool(
            soup.find('template') or 
            re.search(r'customElements\.define|class\s+\w+\s+extends\s+HTMLElement', script_content, re.IGNORECASE)
        )
        
        # Performance
        lazy_loading = bool(_LAZY_LOADING.search(html))
        preload_hints = bool(_PRELOAD_HINTS.search(html))
        modern_image_formats = bool(_MODERN_IMAGES.search(html))
        has_srcset = bool(soup.find(attrs={'srcset': True}))
        
        # PWA
        service_worker = bool(_SERVICE_WORKER.search(script_content) or _SERVICE_WORKER.search(html))
        manifest = bool(_MANIFEST_PATTERN.search(html))
        theme_color = bool(soup.find('meta', attrs={'name': 'theme-color'}))
        
        # Modern JavaScript (NEW!)
        es6_modules = bool(_ES6_MODULES.search(html) or _ES6_MODULES.search(script_content))
        async_await = bool(_ASYNC_AWAIT.search(script_content))
        arrow_functions = bool(_ARROW_FUNCTIONS.search(script_content))
        template_literals = bool(_TEMPLATE_LITERALS.search(script_content))
        typescript = bool(_TYPESCRIPT_PATTERN.search(html))
        modern_js_features = sum([es6_modules, async_await, arrow_functions, template_literals, typescript])
        
        # Accessibility (NEW!)
        aria_labels = len(soup.find_all(attrs={'aria-label': True}))
        aria_roles = len(soup.find_all(attrs={'role': True}))
        has_aria = aria_labels > 0 or aria_roles > 0
        skip_links = bool(soup.find('a', href=re.compile(r'#main|#content|#skip')))
        
        # Alt text coverage (NEW!)
        images = soup.find_all('img')
        images_with_alt = sum(1 for img in images if img.get('alt'))
        alt_text_coverage = (images_with_alt / len(images) * 100) if images else 0
        
        # Build features dict
        features = {
            'spa_framework': frameworks,
            'has_spa': has_spa,
            'framework_count': len(frameworks),
            'css_grid': css_grid,
            'flexbox': flexbox,
            'css_variables': css_variables,
            'semantic_html5': semantic_html5,
            'web_components': web_components,
            'lazy_loading': lazy_loading,
            'preload_hints': preload_hints,
            'modern_image_formats': modern_image_formats,
            'responsive_images': has_srcset,
            'service_worker': service_worker,
            'manifest': manifest,
            'theme_color': theme_color,
            'es6_modules': es6_modules,
            'async_await': async_await,
            'arrow_functions': arrow_functions,
            'template_literals': template_literals,
            'typescript': typescript,
            'modern_js_score': modern_js_features,
            'aria_labels': has_aria,
            'skip_links': skip_links,
            'alt_text_coverage': round(alt_text_coverage, 1),
        }
        
        # Calculate modernity score (improved weights)
        feature_weights = {
            'has_spa': 15 if len(frameworks) > 0 else 0,
            'framework_count': min(5, len(frameworks) * 3),
            'css_grid': 10,
            'flexbox': 8,
            'css_variables': 6,
            'semantic_html5': 10,
            'web_components': 8,
            'lazy_loading': 8,
            'modern_image_formats': 8,
            'responsive_images': 6,
            'preload_hints': 6,
            'service_worker': 12,
            'manifest': 5,
            'theme_color': 3,
            'es6_modules': 8,
            'async_await': 5,
            'typescript': 7,
            'aria_labels': 7,
            'skip_links': 5,
        }
        
        modernity_score = sum(
            weight for feature, weight in feature_weights.items() 
            if features.get(feature, False)
        )
        
        # Alt text bonus
        if alt_text_coverage > 90:
            modernity_score += 5
        elif alt_text_coverage > 70:
            modernity_score += 3
        
        modernity_score = min(100, modernity_score)
        
        # Technology level
        if modernity_score >= 85:
            tech_level = 'cutting_edge'
            tech_description = 'State-of-the-art technology stack'
        elif modernity_score >= 65:
            tech_level = 'modern'
            tech_description = 'Modern and well-maintained'
        elif modernity_score >= 40:
            tech_level = 'standard'
            tech_description = 'Standard implementation'
        elif modernity_score >= 20:
            tech_level = 'basic'
            tech_description = 'Basic implementation, needs modernization'
        else:
            tech_level = 'legacy'
            tech_description = 'Legacy technology, requires significant updates'
        
        # Missing features (NEW!)
        missing_modern_features = [
            feature for feature, weight in feature_weights.items()
            if not features.get(feature, False) and weight >= 8
        ]
        
        return {
            'features': features,
            'modernity_score': modernity_score,
            'is_modern': modernity_score > 60,
            'technology_level': tech_level,
            'technology_description': tech_description,
            'detected_frameworks': frameworks,
            'modern_js_features': modern_js_features,
            'accessibility_score': round((
                (10 if has_aria else 0) +
                (5 if skip_links else 0) +
                (alt_text_coverage / 10)
            ), 1),
            'missing_modern_features': missing_modern_features
        }
        
    except Exception as e:
        logger.error(f"Error in analyze_modern_web_features: {e}")
        # Fallback to basic response
        return {
            'features': {'spa_framework': spa_info.get('frameworks', [])},
            'modernity_score': 0,
            'is_modern': False,
            'technology_level': 'unknown',
            'technology_description': 'Analysis failed',
            'detected_frameworks': [],
            'modern_js_features': 0,
            'accessibility_score': 0,
            'missing_modern_features': []
        }



# ============================================================================
# WEB FEATURES ANALYSIS - HELPER FUNCTIONS (IMPROVED)
# ============================================================================

def _extract_script_content(soup: BeautifulSoup) -> str:
    """Extract all JavaScript code from script tags"""
    try:
        scripts = soup.find_all('script')
        return ' '.join(script.get_text() for script in scripts if script.get_text())
    except Exception:
        return ''


def _extract_style_content(soup: BeautifulSoup) -> str:
    """Extract all CSS from style tags and inline styles"""
    try:
        styles = []
        for style_tag in soup.find_all('style'):
            styles.append(style_tag.get_text())
        for tag in soup.find_all(style=True):
            styles.append(tag.get('style', ''))
        return ' '.join(styles)
    except Exception:
        return ''


def _detect_frameworks_advanced(html: str, script_content: str, soup: BeautifulSoup) -> List[str]:
    """
    Advanced framework detection with Wappalyzer + fallback regex
    
    Returns:
        List of detected framework names (e.g., ['React', 'Next.js', 'Vue.js'])
    """
    detected = set()
    
    try:
        # === 1. TRY WAPPALYZER FIRST (most accurate) ===
        if WAPPALYZER_AVAILABLE:
            try:
                # Create Wappalyzer instance
                wappalyzer = Wappalyzer.latest()
                
                # Create webpage object (needs full HTML)
                webpage = WebPage.new_from_response(
                    html=html,
                    url='https://example.com'  # Wappalyzer needs a URL (fake is OK)
                )
                
                # Analyze
                technologies = wappalyzer.analyze(webpage)
                
                # Map Wappalyzer names to our standard names
                framework_map = {
                    'React': 'react',
                    'Next.js': 'next',
                    'Vue.js': 'vue',
                    'Nuxt.js': 'nuxt',
                    'Angular': 'angular',
                    'Svelte': 'svelte',
                    'Gatsby': 'gatsby',
                }
                
                for tech in technologies:
                    normalized = framework_map.get(tech, tech.lower())
                    detected.add(normalized)
                    logger.info(f"✅ Wappalyzer detected: {tech} → {normalized}")
                
                # If Wappalyzer found something, use it
                if detected:
                    return sorted(list(detected))
                    
            except Exception as e:
                logger.warning(f"Wappalyzer analysis failed: {e}")
        
        # === 2. FALLBACK: REGEX PATTERNS (if Wappalyzer fails) ===
        logger.info("Using regex fallback for framework detection")
        
        # Check meta tags
        meta_generator = soup.find('meta', attrs={'name': 'generator'})
        if meta_generator:
            generator = meta_generator.get('content', '').lower()
            for framework in ['next', 'gatsby', 'nuxt', 'wordpress', 'drupal']:
                if framework in generator:
                    detected.add(framework)
        
        # Check script sources
        for script in soup.find_all('script', src=True):
            src = script.get('src', '').lower()
            for framework, pattern in _FRAMEWORK_PATTERNS.items():
                if pattern.search(src):
                    detected.add(framework)
        
        # Check inline scripts
        for framework, pattern in _FRAMEWORK_PATTERNS.items():
            if pattern.search(script_content):
                detected.add(framework)
        
        # Special relationships
        if 'next' in detected and 'react' not in detected:
            detected.add('react')
        if 'nuxt' in detected and 'vue' not in detected:
            detected.add('vue')
        
        # Check data attributes
        if soup.find(attrs={'data-reactroot': True}) or soup.find(attrs={'data-react-helmet': True}):
            detected.add('react')
        if soup.find(attrs={'data-v-': True}) or soup.find(attrs={'v-cloak': True}):
            detected.add('vue')
        if soup.find(attrs={'ng-app': True}) or soup.find(attrs={'ng-controller': True}):
            detected.add('angular')
            
    except Exception as e:
        logger.error(f"Framework detection error: {e}")
    
    result = sorted(list(detected))
    logger.info(f"📦 Final detected frameworks: {result}")
    return result
    
    return sorted(list(detected))


def detect_interactive_elements(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    """
    PARANNELTU versio - tarkempi ja tehokkaampi
    
    Parannukset:
    - Erottaa React/Vue/inline events
    - Tarkempi JS event detection
    - WebSocket detection
    - Interaction patterns
    - Parempi scoring
    """
    
    try:
        # Static HTML elements
        elements = {
            'forms': len(soup.find_all('form')),
            'buttons': len(soup.find_all('button')) + len(soup.find_all('input', type=['button', 'submit'])),
            'links': len(soup.find_all('a', href=True)),
            'inputs': len(soup.find_all('input')),
            'selects': len(soup.find_all('select')),
            'textareas': len(soup.find_all('textarea')),
            'checkboxes': len(soup.find_all('input', type='checkbox')),
            'radio_buttons': len(soup.find_all('input', type='radio')),
        }
        
        # Extract script content
        script_content = _extract_script_content(soup)
        
        # Modern event listeners (not inline onclick)
        event_listeners = len(re.findall(r'addEventListener\s*\(', script_content, re.IGNORECASE))
        
        # React/Vue events (different syntax)
        react_events = len(re.findall(r'onClick\s*=|onChange\s*=|onSubmit\s*=', html))  # camelCase
        vue_events = len(re.findall(r'@click|@change|@submit|v-on:', html))
        
        # Inline events (legacy)
        inline_events = len(re.findall(r'onclick\s*=|onchange\s*=|onsubmit\s*=', html, re.IGNORECASE))
        
        # jQuery
        has_jquery = bool(_JQUERY_PATTERN.search(html))
        jquery_events = 0
        if has_jquery:
            jquery_events = len(re.findall(r'\$\([^)]*\)\.(click|on|change|submit)', script_content))
        
        # AJAX/Fetch calls
        fetch_calls = len(re.findall(r'\bfetch\s*\(', script_content, re.IGNORECASE))
        axios_calls = len(re.findall(r'axios\.(get|post|put|delete)', script_content, re.IGNORECASE))
        ajax_calls = len(re.findall(r'\.ajax\s*\(|XMLHttpRequest', script_content, re.IGNORECASE))
        
        # WebSocket (real-time)
        websockets = bool(re.search(r'new WebSocket\(|socket\.io', script_content, re.IGNORECASE))
        
        js_interactions = {
            'event_listeners': event_listeners,
            'react_events': react_events,
            'vue_events': vue_events,
            'inline_events': inline_events,
            'jquery_events': jquery_events,
            'fetch_calls': fetch_calls,
            'axios_calls': axios_calls,
            'ajax_calls': ajax_calls,
            'websockets': websockets,
        }
        
        # Calculate scores
        static_score = min(40, (
            elements['forms'] * 10 +
            elements['buttons'] * 4 +
            elements['inputs'] * 2 +
            elements['selects'] * 4 +
            elements['textareas'] * 3
        ))
        
        modern_js_score = min(40, (
            event_listeners * 3 +
            react_events * 2 +
            vue_events * 2 +
            (fetch_calls + axios_calls) * 2
        ))
        
        legacy_js_score = min(20, (
            inline_events * 1 +
            jquery_events * 1 +
            ajax_calls * 1
        ))
        
        realtime_bonus = 10 if websockets else 0
        
        total_interactivity = min(100, static_score + modern_js_score + legacy_js_score + realtime_bonus)
        
        # Interaction patterns (NEW!)
        patterns = []
        if react_events > 5 or vue_events > 5:
            patterns.append('spa_framework')
        if event_listeners > 10:
            patterns.append('modern_js')
        if inline_events > jquery_events and inline_events > event_listeners:
            patterns.append('legacy_inline')
        if jquery_events > 5:
            patterns.append('jquery_based')
        if fetch_calls > 0 or axios_calls > 0:
            patterns.append('ajax_enabled')
        if websockets:
            patterns.append('realtime')
        if elements['forms'] == 0 and total_interactivity > 50:
            patterns.append('spa_no_forms')
        
        return {
            'static_elements': elements,
            'js_interactions': js_interactions,
            'interactivity_score': total_interactivity,
            'is_highly_interactive': total_interactivity > 60,
            'static_score': static_score,
            'modern_js_score': modern_js_score,
            'legacy_js_score': legacy_js_score,
            'realtime_bonus': realtime_bonus,
            'interaction_patterns': patterns,
            'uses_modern_patterns': modern_js_score > legacy_js_score,
            'has_realtime_features': websockets,
            'total_interactive_elements': sum(elements.values()),
            'total_js_interactions': sum(v for k, v in js_interactions.items() if isinstance(v, int)),
        }
        
    except Exception as e:
        logger.error(f"Error in detect_interactive_elements: {e}")
        # Fallback
        return {
            'static_elements': {},
            'js_interactions': {},
            'interactivity_score': 0,
            'is_highly_interactive': False,
            'static_score': 0,
            'modern_js_score': 0,
            'legacy_js_score': 0,
            'realtime_bonus': 0,
            'interaction_patterns': [],
            'uses_modern_patterns': False,
            'has_realtime_features': False,
            'total_interactive_elements': 0,
            'total_js_interactions': 0,
        }



# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION,
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json"
)

# Add the startup event handler here:
@app.on_event("startup")
async def startup_event():
    """Initialize all services on application startup"""
    global magic_link_auth, redis_client, task_queue, oauth
    
    # 1. Initialize database if enabled
    if DATABASE_ENABLED:
        try:
            init_database()
            sync_hardcoded_users_to_db(USERS_DB)
            logger.info("✅ Database initialized and users synced")
            
            # Load users from database
            db_users = get_all_users_from_db()
            for db_user in db_users:
                username = db_user['username']
                if username not in USERS_DB:
                    hashed_pwd = db_user.get('password_hash') or db_user.get('hashed_password', '')
                    
                    if not hashed_pwd:
                        logger.warning(f"⚠️ User {username} from DB has no password hash, skipping")
                        continue
                    
                    USERS_DB[username] = {
                        'username': username,
                        'email': db_user.get('email', f"{username}@unknown.com"),
                        'hashed_password': hashed_pwd,
                        'role': db_user['role'],
                        'search_limit': db_user['search_limit']
                    }
                    logger.info(f"🔥 Loaded user from DB: {username}")
                    
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            logger.info("⚠️ Continuing with hardcoded users only")
    
    # 2. Initialize Redis and task queue (already done globally but verify)
    if REDIS_URL and not redis_client:
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
            logger.info("✅ Redis connected successfully")
            
            from redis_tasks import RedisTaskQueue
            task_queue = RedisTaskQueue(redis_client)
            logger.info("✅ Redis task queue initialized")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            redis_client = None
            task_queue = None
    
    # 3. Initialize Magic Link authentication
    try:
        # Import from separate module
        from auth_magic_link import create_magic_link_auth
        
        # Get postgres connection if available
        postgres_conn = None
        if DATABASE_ENABLED:
            try:
                # If you have a get_postgres_connection function
                # postgres_conn = get_postgres_connection()
                pass
            except Exception:
                pass
        
        # Create magic link auth with proper dependencies
        magic_link_auth = create_magic_link_auth(
            redis_client=redis_client,
            postgres_conn=postgres_conn
        )
        
        logger.info("✅ Magic Link authentication initialized")
        
        # Log configuration status
        email_provider = os.getenv("EMAIL_PROVIDER", "not set")
        has_sendgrid = bool(os.getenv("SENDGRID_API_KEY"))
        has_smtp = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))
        
        if email_provider == "sendgrid" and has_sendgrid:
            logger.info("📧 Email provider: SendGrid (configured)")
        elif email_provider == "smtp" and has_smtp:
            logger.info("📧 Email provider: SMTP (configured)")
        else:
            logger.warning("⚠️ Email provider not properly configured - magic links will log to console")
            
    except ImportError as e:
        logger.error(f"❌ Failed to import magic link module: {e}")
        logger.error("Make sure auth_magic_link.py is in the same directory")
        magic_link_auth = None
    except Exception as e:
        logger.error(f"❌ Magic Link authentication failed to initialize: {e}")
        magic_link_auth = None
    
    # 4. Initialize Google OAuth
    global oauth
    try:
        oauth_config = StarletteConfig(environ={
            'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID', ''),
            'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET', ''),
        })
        
        oauth = OAuth(oauth_config)
        
        if os.getenv('GOOGLE_CLIENT_ID'):
            oauth.register(
                name='google',
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs={'scope': 'openid email profile'},
            )
            logger.info("✅ Google OAuth configured")
        else:
            logger.warning("⚠️ Google OAuth not configured (set GOOGLE_CLIENT_ID)")
    except Exception as e:
        logger.error(f"❌ Google OAuth initialization failed: {e}")
        oauth = None

    # 5. Log startup summary
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} started")
    logger.info(f"📊 Scoring weights: {SCORING_CONFIG.weights}")
    logger.info(f"🎭 Playwright: {'enabled' if PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED else 'disabled'}")
    logger.info(f"🤖 OpenAI: {'configured' if openai_client else 'not configured'}")
    logger.info(f"📧 Magic Link: {'ready' if magic_link_auth else 'not available'}")
    logger.info(f"🗄️ Redis: {'connected' if redis_client else 'not connected'}")
    logger.info(f"🗃️ Database: {'connected' if DATABASE_ENABLED else 'not connected'}")
    
    # 6. Environment warnings
    
    
    if SECRET_KEY.startswith("brandista-key-"):
        logger.warning("⚠️ Using default SECRET_KEY - set custom SECRET_KEY in production!")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "https://brandista.eu",
        "https://www.brandista.eu",
        "https://fastapi-production-51f9.up.railway.app"
        "https://3000-ip92lxeccquecaiidxzl0-6aa4782a.manusvm.computer"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With", 
        "Accept",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers"
    ],
    expose_headers=["*"],
    max_age=600
)

from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="brandista_session",
    max_age=3600,
    same_site="lax",
    https_only=True
)


from starlette.middleware.base import BaseHTTPMiddleware


class UTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "application/json" in response.headers.get("content-type", ""):
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

app.add_middleware(UTF8Middleware)

@app.options("/{full_path:path}")
async def options_handler():
    return {}

# Rate limiting
if RATE_LIMIT_ENABLED:
    request_counts = defaultdict(list)
    
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        request_counts[client_ip] = [t for t in request_counts[client_ip] if now - t < 60]
        
        if len(request_counts[client_ip]) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(429, f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE}/min")
        
        request_counts[client_ip].append(now)
        return await call_next(request)



# ============================================================================
# AUTHENTICATION
# ============================================================================

import hashlib

class SimplePasswordContext:
    def hash(self, password: str) -> str:
        """Generate SHA256 hash with salt"""
        return hashlib.sha256(f"brandista_{password}_salt".encode()).hexdigest()
    
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password - simple SHA256 comparison"""
        return self.hash(plain_password) == hashed_password

pwd_context = SimplePasswordContext()
security = HTTPBearer()

# ✅ PLACEHOLDER - Täytetään init_users() funktiossa
USERS_DB = {}

# ✅ User storage for email verification
user_store = {}

def init_users():
    """Initialize users with hashed passwords"""
    global USERS_DB
    
    USERS_DB = {
        "user@example.com": {
            "username": "user",
            "email": "user@example.com",
            "hashed_password": pwd_context.hash("user123"),
            "role": "user", 
            "search_limit": DEFAULT_USER_LIMIT
        },
        "admin@brandista.eu": {
            "username": "admin",
            "email": "admin@brandista.eu", 
            "hashed_password": pwd_context.hash("kaikka123"),
            "role": "admin", 
            "search_limit": -1
        },
        "super@brandista.eu": {
            "username": "super_user",
            "email": "super@brandista.eu",
            "hashed_password": pwd_context.hash("superpower123"),
            "role": "super_user",
            "search_limit": -1
        }
    }
    
    logger.info("🔐 User passwords hashed:")
    for email, user_data in USERS_DB.items():
        username = user_data.get('username')
        hash_preview = user_data.get('hashed_password')[:20]
        logger.info(f"  {username}: {hash_preview}...")
    
    return USERS_DB

# ✅ KUTSU HETI
init_users()

# ✅ DATABASE SYNC (sama kuin ennenkin)
if DATABASE_ENABLED:
    try:
        init_database()
        sync_hardcoded_users_to_db(USERS_DB)
        logger.info("✅ Database initialized and users synced")
        
        db_users = get_all_users_from_db()
        for db_user in db_users:
            username = db_user['username']
            if username not in USERS_DB:
                hashed_pwd = db_user.get('password_hash') or db_user.get('hashed_password', '')
                
                if not hashed_pwd:
                    logger.warning(f"⚠️ User {username} from DB has no password hash, skipping")
                    continue
                
                USERS_DB[username] = {
                    'username': username,
                    'email': db_user.get('email', f"{username}@unknown.com"),
                    'hashed_password': hashed_pwd,
                    'role': db_user['role'],
                    'search_limit': db_user['search_limit']
                }
                logger.info(f"🔥 Loaded user from DB: {username}")
                
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.info("⚠️ Continuing with hardcoded users only")

logger.info(f"👥 Total users loaded: {len(USERS_DB)}")
logger.info(f"📋 Users: {', '.join(USERS_DB.keys())}")

# ✅ LOG FINAL USER COUNT
logger.info(f"👥 Total users loaded: {len(USERS_DB)}")
logger.info(f"📋 Users: {', '.join(USERS_DB.keys())}")

# ============================================================================
# COMPLETE PYDANTIC MODELS
# ============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str

class UserInfo(BaseModel):
    username: str
    email: Optional[str] = None
    role: str
    search_limit: int = 0
    searches_used: int = 0

class CompetitorAnalysisRequest(BaseModel):
    url: str = Field(..., description="Website URL to analyze")
    company_name: Optional[str] = Field(None, max_length=100)
    analysis_type: str = Field("comprehensive", pattern="^(basic|comprehensive|ai_enhanced)$")
    language: str = Field("en", pattern="^(en|fi)$")
    include_ai: bool = Field(True)
    include_social: bool = Field(True)
    force_playwright: bool = Field(False, description="Force Playwright rendering even for non-SPAs")

class CompetitorDiscoveryRequest(BaseModel):
    url: str = Field(..., description="Käyttäjän oma verkkosivu")
    industry: str = Field(..., max_length=100, description="Toimiala, esim. 'SaaS-palvelu Suomessa'")
    country_code: str = Field("fi", max_length=2, description="Maa, jossa kilpailijoita haetaan")

class CompetitiveRadarRequest(BaseModel):
    your_url: str = Field(..., description="Oma verkkosivusi")
    competitor_urls: List[str] = Field(..., min_items=1, max_items=5, description="Kilpailijoiden URL:t (1-5 kpl)")
    language: str = Field("fi", pattern="^(en|fi)$")
    industry_context: Optional[str] = Field(None, description="Toimiala-konteksti (valinnainen)")

class CompetitiveRadarResponse(BaseModel):
    your_analysis: Dict[str, Any]
    competitors: List[Dict[str, Any]]
    differentiation_matrix: Dict[str, Any]
    market_gaps: List[Dict[str, Any]]
    competitive_score: int
    strategic_recommendations: List[Dict[str, Any]]
    positioning_map: Dict[str, Any]

class ScoreBreakdown(BaseModel):
    # Backend (weighted points)
    security: int = Field(0, ge=0, le=15)
    seo_basics: int = Field(0, ge=0, le=20)
    content: int = Field(0, ge=0, le=20)
    technical: int = Field(0, ge=0, le=15)
    mobile: int = Field(0, ge=0, le=15)
    social: int = Field(0, ge=0, le=10)
    performance: int = Field(0, ge=0, le=5)
    # Frontend aliases (0–100)
    seo: Optional[int] = None
    user_experience: Optional[int] = None
    accessibility: Optional[int] = None

class BasicAnalysis(BaseModel):
    company: str
    website: str
    industry: Optional[str] = None
    digital_maturity_score: int = Field(..., ge=0, le=100)
    social_platforms: int = Field(0, ge=0)
    technical_score: int = Field(0, ge=0, le=100)
    content_score: int = Field(0, ge=0, le=100)
    seo_score: int = Field(0, ge=0, le=100)
    score_breakdown: Optional[ScoreBreakdown] = None
    analysis_timestamp: datetime = Field(default_factory=datetime.now)
    # Enhanced fields
    spa_detected: bool = Field(False)
    rendering_method: str = Field("http")
    modernity_score: int = Field(0, ge=0, le=100)

class TechnicalAudit(BaseModel):
    has_ssl: bool = False
    has_mobile_optimization: bool = False
    page_speed_score: int = Field(0, ge=0, le=100)
    has_analytics: bool = False
    has_sitemap: bool = False
    has_robots_txt: bool = False
    meta_tags_score: int = Field(0, ge=0, le=100)
    overall_technical_score: int = Field(0, ge=0, le=100)
    security_headers: Dict[str, bool] = {}
    performance_indicators: List[str] = []

class ContentAnalysis(BaseModel):
    word_count: int = Field(0, ge=0)
    readability_score: int = Field(0, ge=0, le=100)
    keyword_density: Dict[str, float] = {}
    content_freshness: str = Field("unknown", pattern="^(very_fresh|fresh|moderate|dated|unknown)$")
    has_blog: bool = False
    content_quality_score: int = Field(0, ge=0, le=100)
    media_types: List[str] = []
    interactive_elements: List[str] = []

class SocialMediaAnalysis(BaseModel):
    platforms: List[str] = []
    total_followers: int = Field(0, ge=0)
    engagement_rate: float = Field(0.0, ge=0.0, le=100.0)
    posting_frequency: str = "unknown"
    social_score: int = Field(0, ge=0, le=100)
    has_sharing_buttons: bool = False
    open_graph_tags: int = 0
    twitter_cards: bool = False

class UXAnalysis(BaseModel):
    navigation_score: int = Field(0, ge=0, le=100)
    visual_design_score: int = Field(0, ge=0, le=100)
    accessibility_score: int = Field(0, ge=0, le=100)
    mobile_ux_score: int = Field(0, ge=0, le=100)
    overall_ux_score: int = Field(0, ge=0, le=100)
    accessibility_issues: List[str] = []
    navigation_elements: List[str] = []
    design_frameworks: List[str] = []

class CompetitiveAnalysis(BaseModel):
    market_position: str = "unknown"
    competitive_advantages: List[str] = []
    competitive_threats: List[str] = []
    market_share_estimate: str = "Data not available"
    competitive_score: int = Field(0, ge=0, le=100)
    industry_comparison: Dict[str, Any] = {}

    # main.py (Pydantic-mallien sekaan)



class CompetitorDiscoveryRequest(BaseModel):
    url: str = Field(..., description="Käyttäjän oma verkkosivu")
    industry: str = Field(..., max_length=100, description="Toimiala, esim. 'SaaS-palvelu Suomessa' tai 'rakennusliike Tampere'")
    country_code: str = Field("fi", max_length=2, description="Maa, jossa kilpailijoita haetaan (esim. 'fi')")


# --- NEW: humanized analysis models ---

class BusinessImpact(BaseModel):
    lead_gain_estimate: Optional[str] = None         # e.g. "12–20 leads/mo"
    revenue_uplift_range: Optional[str] = None       # e.g. "+3–6% revenue"
    confidence: Optional[str] = "M"                  # L | M | H
    customer_trust_effect: Optional[str] = None      # short human note

class RoleSummaries(BaseModel):
    CEO: Optional[str] = None
    CMO: Optional[str] = None
    CTO: Optional[str] = None

class Plan90D(BaseModel):
    wave_1: List[str] = []            # days 0–30
    wave_2: List[str] = []            # days 31–60
    wave_3: List[str] = []            # days 61–90
    one_thing_this_week: Optional[str] = None

class RiskItem(BaseModel):
    risk: str
    likelihood: int = Field(1, ge=1, le=5)
    impact: int = Field(1, ge=1, le=5)
    mitigation: Optional[str] = None
    risk_score: Optional[int] = None   # computed later as L*I

class SnippetExamples(BaseModel):
    seo_title: List[str] = []
    meta_desc: List[str] = []
    h1_intro: List[str] = []
    product_copy: List[str] = []

class AISearchFactor(BaseModel):
    name: str
    score: int = Field(0, ge=0, le=100)
    status: str  # "excellent" | "good" | "needs_improvement" | "poor"
    findings: List[str] = []
    recommendations: List[str] = []

class AISearchVisibility(BaseModel):
    chatgpt_readiness_score: int = Field(0, ge=0, le=100)
    perplexity_readiness_score: int = Field(0, ge=0, le=100)
    overall_ai_search_score: int = Field(0, ge=0, le=100)
    competitive_advantage: str = "First Nordic company to systematically analyze AI search readiness"
    validation_status: str = "estimated"  # "estimated" | "validated" | "monitored"
    factors: Dict[str, AISearchFactor] = {}
    key_insights: List[str] = []
    priority_actions: List[str] = []

class AIAnalysis(BaseModel):
    summary: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    recommendations: List[str] = []
    confidence_score: int = Field(0, ge=0, le=100)
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    key_metrics: Dict[str, Any] = {}
    action_priority: List[Dict[str, Any]] = []

    # NEW humanized layers
    business_impact: Optional[BusinessImpact] = None
    role_summaries: Optional[RoleSummaries] = None
    plan_90d: Optional[Plan90D] = None
    risk_register: Optional[List[RiskItem]] = None
    snippet_examples: Optional[SnippetExamples] = None
    ai_search_visibility: AISearchVisibility = Field(default_factory=lambda: AISearchVisibility())


class SmartAction(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern="^(critical|high|medium|low)$")
    effort: str = Field(..., pattern="^(low|medium|high)$")
    impact: str = Field(..., pattern="^(low|medium|high|critical)$")
    estimated_score_increase: int = Field(0, ge=0, le=100)
    category: str = ""
    estimated_time: str = ""

    # NEW humanized fields (optional → backward compatible)
    so_what: Optional[str] = None
    why_now: Optional[str] = None
    what_to_do: Optional[str] = None
    owner: Optional[str] = None
    eta_days: Optional[int] = None

    # Lightweight prioritization
    reach: Optional[int] = None        # 0–100
    confidence: Optional[int] = None   # 1–10
    rice_score: Optional[int] = None   # computed

    # Evidence & confidence
    signals: Optional[List[str]] = None
    evidence_confidence: Optional[str] = None  # "L|M|H"

class SmartScores(BaseModel):
    overall: int = Field(0, ge=0, le=100)
    technical: int = Field(0, ge=0, le=100)
    content: int = Field(0, ge=0, le=100)
    social: int = Field(0, ge=0, le=100)
    ux: int = Field(0, ge=0, le=100)
    competitive: int = Field(0, ge=0, le=100)
    trend: str = "stable"
    percentile: int = Field(0, ge=0, le=100)

class DetailedAnalysis(BaseModel):
    social_media: SocialMediaAnalysis
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    competitive_analysis: CompetitiveAnalysis

class QuotaUpdateRequest(BaseModel):
    search_limit: Optional[int] = None
    grant_extra: Optional[int] = Field(None, ge=1)
    reset_count: bool = False

class UserQuotaView(BaseModel):
    username: str
    role: str
    search_limit: int
    searches_used: int# --- NEW: humanized analysis models ---


class RevenueInputRequest(BaseModel):
    """User's actual business metrics for personalized impact calculation"""
    annual_revenue: Optional[int] = Field(None, ge=0, description="Annual revenue in euros")
    monthly_revenue: Optional[int] = Field(None, ge=0, description="Monthly revenue in euros")
    monthly_visitors: Optional[int] = Field(None, ge=0, description="Monthly website visitors")
    conversion_rate: Optional[float] = Field(None, ge=0, le=100, description="Current conversion rate %")
    average_order_value: Optional[int] = Field(None, ge=0, description="Average order value in euros")

    # LISÄÄ TÄMÄ TÄHÄN:
class RevenueCalculationRequest(BaseModel):
    """Request for standalone revenue impact calculation"""
    revenue_input: Optional[RevenueInputRequest] = None  # ✅ Nyt tämä toimii!
    digital_score: int = Field(0, ge=0, le=100, description="Current digital maturity score")

class BusinessImpactDetailed(BaseModel):
    """Enhanced BusinessImpact with detailed calculation info and user input support"""
    lead_gain_estimate: Optional[str] = None
    revenue_uplift_range: Optional[str] = None
    monthly_revenue_range: Optional[str] = None
    confidence: Optional[str] = "M"
    customer_trust_effect: Optional[str] = None
    # New detailed fields
    calculation_basis: str = "estimated"  # "estimated" | "provided" | "calculated" | "hybrid"
    metrics_used: Dict[str, Any] = {}
    improvement_areas: List[str] = []
    potential_scenarios: Dict[str, Dict[str, Any]] = {}

class RoleSummaries(BaseModel):
    CEO: Optional[str] = None
    CMO: Optional[str] = None
    CTO: Optional[str] = None

class Plan90D(BaseModel):
    wave_1: List[str] = []            # days 0–30
    wave_2: List[str] = []            # days 31–60
    wave_3: List[str] = []            # days 61–90
    one_thing_this_week: Optional[str] = None

class RiskItem(BaseModel):
    risk: str
    likelihood: int = Field(1, ge=1, le=5)
    impact: int = Field(1, ge=1, le=5)
    mitigation: Optional[str] = None
    risk_score: Optional[int] = None   # computed later as L*I

class SnippetExamples(BaseModel):
    seo_title: List[str] = []
    meta_desc: List[str] = []
    h1_intro: List[str] = []
    product_copy: List[str] = []

class AISearchFactor(BaseModel):
    name: str
    score: int = Field(0, ge=0, le=100)
    status: str  # "excellent" | "good" | "needs_improvement" | "poor"
    findings: List[str] = []
    recommendations: List[str] = []

class AISearchVisibility(BaseModel):
    chatgpt_readiness_score: int = Field(0, ge=0, le=100)
    perplexity_readiness_score: int = Field(0, ge=0, le=100)
    overall_ai_search_score: int = Field(0, ge=0, le=100)
    competitive_advantage: str = "First Nordic company to systematically analyze AI search readiness"
    validation_status: str = "estimated"  # "estimated" | "validated" | "monitored"
    factors: Dict[str, AISearchFactor] = {}
    key_insights: List[str] = []
    priority_actions: List[str] = []

class AIAnalysis(BaseModel):
    summary: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    recommendations: List[str] = []
    confidence_score: int = Field(0, ge=0, le=100)
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    key_metrics: Dict[str, Any] = {}
    action_priority: List[Dict[str, Any]] = []

    # NEW humanized layers
    business_impact: Optional[BusinessImpact] = None
    role_summaries: Optional[RoleSummaries] = None
    plan_90d: Optional[Plan90D] = None
    risk_register: Optional[List[RiskItem]] = None
    snippet_examples: Optional[SnippetExamples] = None
    ai_search_visibility: AISearchVisibility = Field(default_factory=lambda: AISearchVisibility())


class SmartAction(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern="^(critical|high|medium|low)$")
    effort: str = Field(..., pattern="^(low|medium|high)$")
    impact: str = Field(..., pattern="^(low|medium|high|critical)$")
    estimated_score_increase: int = Field(0, ge=0, le=100)
    category: str = ""
    estimated_time: str = ""

    # NEW humanized fields (optional → backward compatible)
    so_what: Optional[str] = None
    why_now: Optional[str] = None
    what_to_do: Optional[str] = None
    owner: Optional[str] = None
    eta_days: Optional[int] = None

    # Lightweight prioritization
    reach: Optional[int] = None        # 0–100
    confidence: Optional[int] = None   # 1–10
    rice_score: Optional[int] = None   # computed

    # Evidence & confidence
    signals: Optional[List[str]] = None
    evidence_confidence: Optional[str] = None  # "L|M|H"

class SmartScores(BaseModel):
    overall: int = Field(0, ge=0, le=100)
    technical: int = Field(0, ge=0, le=100)
    content: int = Field(0, ge=0, le=100)
    social: int = Field(0, ge=0, le=100)
    ux: int = Field(0, ge=0, le=100)
    competitive: int = Field(0, ge=0, le=100)
    trend: str = "stable"
    percentile: int = Field(0, ge=0, le=100)

class DetailedAnalysis(BaseModel):
    social_media: SocialMediaAnalysis
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    competitive_analysis: CompetitiveAnalysis

class QuotaUpdateRequest(BaseModel):
    search_limit: Optional[int] = None
    grant_extra: Optional[int] = Field(None, ge=1)
    reset_count: bool = False

class UserQuotaView(BaseModel):
    username: str
    role: str
    search_limit: int
    searches_used: int

# ============================================================================
# AUTH FUNCTIONS
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except InvalidTokenError as e:
        logger.warning(f"JWT error: {e}")
        return None

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[UserInfo]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization.split(" ")[1]
        payload = verify_token(token)
        if not payload:
            return None
        
        sub = payload.get("sub")  # Can be email OR username
        role = payload.get("role", "user")
        
        if not sub:
            return None
        
        # 🔍 Try to find user by sub (which can be email OR username)
        user_data = None
        user_key = None
        
        # 1. Direct key lookup (fastest)
        if sub in USERS_DB:
            user_data = USERS_DB[sub]
            user_key = sub
        
        # 2. Search by username field (for old tokens with username as sub)
        if not user_data:
            for key, data in USERS_DB.items():
                if data.get("username") == sub:
                    user_data = data
                    user_key = key
                    logger.info(f"🔍 Found user by username: {sub} → {key}")
                    break
        
        # 3. Search by email field
        if not user_data:
            for key, data in USERS_DB.items():
                if data.get("email") == sub:
                    user_data = data
                    user_key = key
                    logger.info(f"🔍 Found user by email: {sub} → {key}")
                    break
        
        if not user_data:
            logger.warning(f"❌ User not found for sub: {sub}")
            return None
        
        # Use the role from token (it's already correct)
        return UserInfo(
            username=user_data.get("username", user_key),
            email=user_data.get("email", user_key),
            role=role,  # Use role from token
            search_limit=user_data.get("search_limit", 10),
            searches_used=user_search_counts.get(user_key, 0)
        )
    except Exception as e:
        logger.warning(f"Error getting current user: {e}")
        return None

async def require_user(user: Optional[UserInfo] = Depends(get_current_user)) -> UserInfo:
    if not user:
        raise HTTPException(401, "Authentication required")
    return user

async def require_admin(user: UserInfo = Depends(require_user)) -> UserInfo:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user

def require_admin_or_super(user: UserInfo = Depends(get_current_user)):
    """Require admin OR super_user role"""
    if user.role not in ["admin", "super_user"]:
        raise HTTPException(403, "Admin or Super User access required")
    return user

# ============================================================================
# UTILITIES
# ============================================================================

def ensure_integer_scores(data: Any) -> Any:
    if isinstance(data, dict):
        for k, v in data.items():
            if (k != 'sentiment_score') and (k.endswith('_score') or k == 'score'):
                if isinstance(v, (int, float)):
                    data[k] = max(0, min(100, int(round(v))))
            elif isinstance(v, dict):
                ensure_integer_scores(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        ensure_integer_scores(item)
    return data

def get_cache_key(url: str, analysis_type: str = "basic") -> str:
    config_hash = hashlib.md5(str(SCORING_CONFIG.weights).encode()).hexdigest()[:8]
    playwright_suffix = "_pw" if PLAYWRIGHT_ENABLED else ""
    return hashlib.md5(f"{url}_{analysis_type}_{APP_VERSION}_{config_hash}{playwright_suffix}".encode()).hexdigest()

def is_cache_valid(timestamp: datetime) -> bool:
    return (datetime.now() - timestamp).total_seconds() < CACHE_TTL

def _reject_ssrf(url: str):
    """Block localhost/private networks & .local hosts before fetching"""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, "Invalid URL")
    if host == "localhost" or host.endswith(".local"):
        raise HTTPException(400, "URL not allowed")
    try:
        for fam in (socket.AF_INET, socket.AF_INET6):
            try:
                infos = socket.getaddrinfo(host, None, fam, socket.SOCK_STREAM)
            except socket.gaierror:
                continue
            for res in infos:
                ip_str = res[4][0]
                ip = ipaddress.ip_address(ip_str)
                private_nets = [
                    ipaddress.ip_network("127.0.0.0/8"),
                    ipaddress.ip_network("10.0.0.0/8"),
                    ipaddress.ip_network("172.16.0.0/12"),
                    ipaddress.ip_network("192.168.0.0/16"),
                    ipaddress.ip_network("::1/128"),
                    ipaddress.ip_network("fc00::/7"),
                    ipaddress.ip_network("fe80::/10"),
                ]
                if any(ip in net for net in private_nets):
                    raise HTTPException(400, "URL not allowed")
    except ValueError:
        raise HTTPException(400, "URL not allowed")

def clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip('/')

def get_domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]

def create_score_breakdown_with_aliases(breakdown_raw: Dict[str, int]) -> Dict[str, int]:
    """Create score breakdown with both backend and frontend fields (aliases 0-100)."""
    weights = SCORING_CONFIG.weights
    result = dict(breakdown_raw or {})
    result['seo'] = int((result.get('seo_basics', 0) / weights['seo_basics']) * 100)
    result['user_experience'] = int((result.get('mobile', 0) / weights['mobile']) * 100)
    result['accessibility'] = min(100, int((
        (result.get('mobile', 0) / weights['mobile'] * 0.6) + 
        (result.get('technical', 0) / weights['technical'] * 0.4)
    ) * 100))
    return result

async def cleanup_cache():
    if len(analysis_cache) <= MAX_CACHE_SIZE:
        return
    items_to_remove = len(analysis_cache) - MAX_CACHE_SIZE
    sorted_items = sorted(analysis_cache.items(), key=lambda x: x[1]['timestamp'])
    for key, _ in sorted_items[:items_to_remove]:
        del analysis_cache[key]
    logger.info(f"Cache cleanup: removed {items_to_remove} entries")
async def get_from_cache(key: str) -> Optional[Dict[str, Any]]:
    if not redis_client:
        return analysis_cache.get(key, {}).get('data') if key in analysis_cache and is_cache_valid(analysis_cache[key]['timestamp']) else None
    
    try:
        cached_data = redis_client.get(key)
        if cached_data:
            data = json.loads(cached_data)
            if is_cache_valid(datetime.fromisoformat(data['timestamp'])):
                return data['data']
            else:
                redis_client.delete(key)
    except Exception as e:
        logger.error(f"Redis get error: {e}")
    
    return None

async def set_cache(key: str, data: Dict[str, Any]):
    analysis_cache[key] = {'data': data, 'timestamp': datetime.now()}
    
    if redis_client:
        try:
            cache_data = {'data': data, 'timestamp': datetime.now().isoformat()}
            redis_client.setex(key, CACHE_TTL, json.dumps(cache_data))
        except Exception as e:
            logger.error(f"Redis set error: {e}")
# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def check_security_headers_from_headers(headers: httpx.Headers) -> Dict[str, bool]:
    def has(h: str) -> bool:
        return h in headers
    return {
        'csp': has('content-security-policy'),
        'x_frame_options': has('x-frame-options'),
        'strict_transport': has('strict-transport-security')
    }

def check_security_headers_in_html(html: str) -> Dict[str, bool]:
    hl = html.lower()
    return {
        'csp': 'content-security-policy' in hl,
        'x_frame_options': 'x-frame-options' in hl,
        'strict_transport': 'strict-transport-security' in hl
    }

def check_clean_urls(url: str) -> bool:
    if '?' in url and '=' in url: return False
    if any(ext in url for ext in ['.php', '.asp', '.jsp']): return False
    if '__' in url or url.count('_') > 3: return False
    return True

def extract_clean_text(soup: BeautifulSoup) -> str:
    for e in soup(['script', 'style', 'noscript']):
        e.decompose()
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (p.strip() for line in lines for p in line.split("  "))
    return ' '.join(chunk for chunk in chunks if chunk)

def check_content_freshness(soup: BeautifulSoup, html: str) -> int:
    score = 0
    year = datetime.now().year
    if str(year) in html: score += 2
    if str(year - 1) in html: score += 1
    if soup.find('meta', attrs={'name': 'last-modified'}): score += 2
    return min(5, score)

def analyze_image_optimization(soup: BeautifulSoup) -> Dict[str, Any]:
    imgs = soup.find_all('img')
    if not imgs:
        return {'score': 0, 'total_images': 0, 'optimized_images': 0, 'optimization_ratio': 0}
    optimized = 0
    for img in imgs:
        s = 0
        if img.get('alt', '').strip(): s += 1
        if img.get('loading') == 'lazy': s += 1
        src = img.get('src', '').lower()
        if any(fmt in src for fmt in ('.webp', '.avif')): s += 1
        if img.get('srcset'): s += 1
        if s >= 2: optimized += 1
    ratio = optimized / len(imgs)
    return {'score': int(ratio * 5), 'total_images': len(imgs), 'optimized_images': optimized, 'optimization_ratio': ratio}

def detect_analytics_tools(html: str) -> Dict[str, Any]:
    tools = []
    patterns = {
        'Google Analytics': ['google-analytics', 'gtag', 'ga.js'],
        'Google Tag Manager': ['googletagmanager', 'gtm.js'],
        'Matomo': ['matomo', 'piwik'], 'Hotjar': ['hotjar'],
        'Facebook Pixel': ['fbevents.js', 'facebook.*pixel']
    }
    hl = html.lower()
    for tool, pats in patterns.items():
        if any(p in hl for p in pats):
            tools.append(tool)
    return {'has_analytics': bool(tools), 'tools': tools, 'count': len(tools)}

def check_sitemap_indicators(soup: BeautifulSoup) -> bool:
    if soup.find('link', {'rel': 'sitemap'}): return True
    for a in soup.find_all('a', href=True):
        if 'sitemap' in a['href'].lower(): return True
    return False

def check_robots_indicators(html: str) -> bool:
    return 'robots.txt' in html.lower()

def check_responsive_design(html: str) -> Dict[str, Any]:
    hl = html.lower()
    score = 0; indicators = []
    media_count = hl.count('@media')
    if media_count >= 5: score += 3
    elif media_count >= 2: score += 2
    elif media_count >= 1: score += 1
    if media_count: indicators.append(f'{media_count} media queries')
    for fw, pts in {'bootstrap':2, 'tailwind':2, 'foundation':1, 'bulma':1}.items():
        if fw in hl: score += pts; indicators.append(fw); break
    if 'display: flex' in hl or 'display:flex' in hl: score += 1; indicators.append('flexbox')
    if 'display: grid' in hl or 'display:grid' in hl: score += 1; indicators.append('css grid')
    return {'score': min(7, score), 'indicators': indicators}

def extract_social_platforms(html: str) -> List[str]:
    platforms = []
    patterns = {
        'facebook': r'facebook\.com/[^/\s"\']+',
        'instagram': r'instagram\.com/[^/\s"\']+',
        'linkedin': r'linkedin\.com/(company|in)/[^/\s"\']+',
        'youtube': r'youtube\.com/(@|channel|user|c)[^/\s"\']+',
        'twitter': r'(twitter\.com|x\.com)/[^/\s"\']+',
        'tiktok': r'tiktok\.com/@[^/\s"\']+',
        'pinterest': r'pinterest\.(\w+)/[^/\s"\']+',
    }
    for platform, pattern in patterns.items():
        if re.search(pattern, html, re.I):
            platforms.append(platform)
    return platforms

def calculate_readability_score(text: str) -> int:
    words = text.split()
    sentences = [s for s in text.split('.') if s.strip()]
    if not sentences or len(words) < 100: return 50
    avg = len(words) / len(sentences)
    if avg <= 8: return 40
    elif avg <= 15: return 90
    elif avg <= 20: return 70
    elif avg <= 25: return 50
    return 30

def get_freshness_label(score: int) -> str:
    if score >= 4: return "very_fresh"
    elif score >= 3: return "fresh"
    elif score >= 2: return "moderate"
    elif score >= 1: return "dated"
    return "unknown"

# ============================================================================
# CONFIGURABLE SCORING FUNCTIONS
# ============================================================================

def calculate_content_score_configurable(word_count: int) -> int:
    thresholds = SCORING_CONFIG.content_thresholds
    max_score = SCORING_CONFIG.weights['content']
    if word_count >= thresholds['excellent']: return max_score
    elif word_count >= thresholds['good']: return int(max_score * 0.85)
    elif word_count >= thresholds['fair']: return int(max_score * 0.65)
    elif word_count >= thresholds['basic']: return int(max_score * 0.4)
    elif word_count >= thresholds['minimal']: return int(max_score * 0.2)
    else: return max(0, int(max_score * (word_count / max(1, thresholds['minimal']) * 0.1)))

def calculate_seo_score_configurable(soup: BeautifulSoup, url: str) -> Tuple[int, Dict[str, Any]]:
    config = SCORING_CONFIG.seo_thresholds
    scores = config['scores']
    details = {}
    total_score = 0
    
    # Title analysis
    title = soup.find('title')
    if title:
        title_length = len(title.get_text().strip())
        details['title_length'] = title_length
        if config['title_optimal_range'][0] <= title_length <= config['title_optimal_range'][1]:
            total_score += scores['title_optimal']
        elif config['title_acceptable_range'][0] <= title_length <= config['title_acceptable_range'][1]:
            total_score += scores['title_acceptable']
        elif title_length > 0:
            total_score += scores['title_basic']
    
    # Meta description analysis
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        desc_length = len(meta_desc.get('content', '').strip())
        details['meta_desc_length'] = desc_length
        if config['meta_desc_optimal_range'][0] <= desc_length <= config['meta_desc_optimal_range'][1]:
            total_score += scores['meta_desc_optimal']
        elif config['meta_desc_acceptable_range'][0] <= desc_length <= config['meta_desc_acceptable_range'][1]:
            total_score += scores['meta_desc_acceptable']
        elif desc_length > 0:
            total_score += scores['meta_desc_basic']
    
    # Header structure analysis
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    h3_tags = soup.find_all('h3')
    if len(h1_tags) == config['h1_optimal_count']: total_score += 3
    elif len(h1_tags) in [2, 3]: total_score += 1
    if len(h2_tags) >= 2: total_score += 1
    if len(h3_tags) >= 1: total_score += 1
    
    # Technical SEO elements
    if soup.find('link', {'rel': 'canonical'}): 
        total_score += scores['canonical']
        details['has_canonical'] = True
    if soup.find('link', {'hreflang': True}): 
        total_score += scores['hreflang']
        details['has_hreflang'] = True
    if check_clean_urls(url): total_score += scores['clean_urls']
    
    return min(total_score, SCORING_CONFIG.weights['seo_basics']), details

# ============================================================================
# ENHANCED ANALYSIS FUNCTIONS
# ============================================================================

async def analyze_basic_metrics_enhanced(
    url: str, 
    html: str, 
    headers: Optional[httpx.Headers] = None,
    rendering_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Enhanced basic analysis that incorporates SPA detection and modern web features"""
    soup = BeautifulSoup(html, 'html.parser')
    score_components = {category: 0 for category in SCORING_CONFIG.weights.keys()}
    details: Dict[str, Any] = {}
    
    # Get rendering information
    spa_detected = rendering_info.get('spa_detected', False) if rendering_info else False
    rendering_method = rendering_info.get('rendering_method', 'http') if rendering_info else 'http'
    
    try:
        # SECURITY
        if url.startswith('https://'):
            score_components['security'] += 10
            details['https'] = True
            sh = check_security_headers_from_headers(headers) if headers is not None else check_security_headers_in_html(html)
            if sh['csp']: score_components['security'] += 2
            if sh['x_frame_options']: score_components['security'] += 1
            if sh['strict_transport']: score_components['security'] += 2
            details['security_headers'] = sh
        else:
            details['https'] = False
        
        # SEO (adjusted for SPAs)
        seo_score, seo_details = calculate_seo_score_configurable(soup, url)
        # SPAs might have lower initial SEO scores due to client-side rendering
        if spa_detected and rendering_method == 'http':
            seo_score = int(seo_score * 0.8)  # Penalize SPAs without proper rendering
            details['spa_seo_penalty'] = True
        score_components['seo_basics'] = seo_score
        details.update(seo_details)
        
        # CONTENT
        text = extract_clean_text(soup)
        word_count = len(text.split())
        content_score = calculate_content_score_configurable(word_count)
        freshness_score = check_content_freshness(soup, html)
        img_opt = analyze_image_optimization(soup)
        
        # Bonus for SPAs with good content (they worked hard for it)
        if spa_detected and word_count > 1000:
            content_score = int(content_score * 1.1)  # 10% bonus
            details['spa_content_bonus'] = True
        
        score_components['content'] = min(
            SCORING_CONFIG.weights['content'],
            content_score + freshness_score + img_opt['score']
        )
        details['word_count'] = word_count
        details['image_optimization'] = img_opt
        
        # TECHNICAL (enhanced for modern features)
        analytics = detect_analytics_tools(html)
        if analytics['has_analytics']: score_components['technical'] += 3
        if check_sitemap_indicators(soup): score_components['technical'] += 1
        if check_robots_indicators(html): score_components['technical'] += 1
        
        # Modern web features bonus
        modern_features = analyze_modern_web_features(html, rendering_info.get('spa_info', {}) if rendering_info else {})
        if modern_features['is_modern']:
            bonus = min(5, modern_features['modernity_score'] // 20)
            score_components['technical'] += bonus
            details['modern_tech_bonus'] = bonus
        
        details['analytics'] = analytics['tools']
        details['modern_features'] = modern_features
        
        # MOBILE (enhanced)
        
        mobile_raw = 0
        viewport = soup.find('meta', attrs={'name': 'viewport'})

        if viewport:
            vc = viewport.get('content', '')
            if 'width=device-width' in vc: 
                mobile_raw += 40  # ✅ Muutettu 5 → 40
                details['has_viewport'] = True
            if 'initial-scale=1' in vc: 
                mobile_raw += 20  # ✅ Muutettu 3 → 20
        else:
            details['has_viewport'] = False

        # Tarkista responsive signaalit (korvaa check_responsive_design)
        if detect_responsive_signals(html):
            mobile_raw += 20  # ✅ Uusi

        # Tarkista media queries
        if '@media' in html.lower():
            mobile_raw += 20  # ✅ Uusi

        # SPA mobile bonus (muutettu skaalaus)
        if spa_detected and mobile_raw >= 80:  # ✅ Muutettu: jos jo vahva responsive
            mobile_raw = min(100, mobile_raw + 10)  # ✅ Muutettu: +2 → +10 (koska 0-100 skaalassa)
            details['spa_mobile_bonus'] = True

        # Laske 0-100 pistemäärä
        mobile_score_100 = min(100, mobile_raw)

        # Skaalaa breakdown-pisteksi (0-15)
        score_components['mobile'] = int((mobile_score_100 / 100) * SCORING_CONFIG.weights['mobile'])

        # Tallenna detailsiin
        details['mobile_score_raw'] = mobile_score_100
        details['responsive_design'] = {
            'score': mobile_score_100,
            'has_viewport': details.get('has_viewport', False),
            'responsive_signals': detect_responsive_signals(html),
            'media_queries': '@media' in html.lower(),
            'spa_bonus_applied': details.get('spa_mobile_bonus', False)
        }
        
        # SOCIAL
        social_platforms = extract_social_platforms(html)
        score_components['social'] = min(10, len(social_platforms))
        
        # PERFORMANCE (enhanced for SPAs)
        if spa_detected:
            # SPAs can be larger initially but should load efficiently
            if len(html) < 200_000: score_components['performance'] += 3
            elif len(html) < 500_000: score_components['performance'] += 2
            else: score_components['performance'] += 1
        else:
            # Traditional size thresholds
            if len(html) < 100_000: score_components['performance'] += 2
            elif len(html) < 200_000: score_components['performance'] += 1
        
        if 'lazy' in html.lower() or 'loading="lazy"' in html: score_components['performance'] += 2
        if 'webp' in html.lower(): score_components['performance'] += 1
        
        total_score = sum(score_components.values())
        final_score = max(0, min(100, total_score))
        
        logger.info(f"Enhanced analysis for {url}: Score={final_score}, SPA={spa_detected}, Method={rendering_method}")

        # SPA framework detection (fallback injection)
        try:
            extra_txt = ''
            if '<!--XHR-->' in html:
                try:
                    extra_txt = html.split('<!--XHR-->')[1].split('<!--/XHR-->')[0]
                except Exception:
                    extra_txt = ''
            spa_stack = await detect_spa_framework(html + extra_txt if extra_txt else html)
            if spa_stack and 'technology_stack' in locals():
                technology_stack.extend([t for t in spa_stack if t not in technology_stack])
        except Exception:
            pass

        return {
            'digital_maturity_score': final_score,
            'score_breakdown': score_components,
            'detailed_findings': details,
            'word_count': word_count,
            'has_ssl': url.startswith('https'),
            'has_analytics': analytics.get('has_analytics', False),
            'has_mobile_viewport': details.get('has_viewport', False),
            'title': soup.find('title').get_text().strip() if soup.find('title') else '',
            'meta_description': soup.find('meta', attrs={'name': 'description'}).get('content', '') if soup.find('meta', attrs={'name': 'description'}) else '',
            'h1_count': len(soup.find_all('h1')),
            'h2_count': len(soup.find_all('h2')),
            'social_platforms': len(social_platforms),
            # Enhanced fields
            'spa_detected': spa_detected,
            'rendering_method': rendering_method,
            'modernity_score': modern_features.get('modernity_score', 0),
            'technology_level': modern_features.get('technology_level', 'basic')
        }
    except Exception as e:
        logger.error(f"Error in enhanced analysis for {url}: {e}")
        return {
            'digital_maturity_score': 0,
            'score_breakdown': {category: 0 for category in SCORING_CONFIG.weights.keys()},
            'detailed_findings': {'error': str(e)},
            'word_count': 0,
            'has_ssl': url.startswith('https'),
            'has_analytics': False,
            'has_mobile_viewport': False,
            'title': '',
            'meta_description': '',
            'h1_count': 0,
            'h2_count': 0,
            'social_platforms': 0,
            'spa_detected': False,
            'rendering_method': 'http',
            'modernity_score': 0
        }

async def analyze_technical_aspects(url: str, html: str, headers: Optional[httpx.Headers] = None) -> Dict[str, Any]:
    """Complete technical analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    tech_score = 0
    
    # SSL Check
    has_ssl = url.startswith('https')
    if has_ssl: tech_score += 20

    # Mobile optimization
    has_mobile = False
    present, vp_content = has_viewport_meta(html, soup)
    if present:
        has_mobile = True
        tech_score += 15
        if 'initial-scale=1' in (vp_content or '').lower():
            tech_score += 5
    else:
        if detect_responsive_signals(html):
            # If clear responsive signals exist, don't punish as harshly
            has_mobile = True
            tech_score += 10

    # Analytics

    analytics = detect_analytics_tools(html) if 'detect_analytics_tools' in globals() else {'has_analytics': ('gtag(' in html or 'analytics.js' in html)}
    if analytics.get('has_analytics'): tech_score += 10

    # Meta tags scoring
    meta_points = 0
    title = soup.find('title')
    if title:
        l = len(title.get_text().strip())
        if 30 <= l <= 60: meta_points += 8
        elif 20 <= l <= 70: meta_points += 5
        elif l > 0: meta_points += 2
    
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        L = len(meta_desc.get('content', ''))
        if 120 <= L <= 160: meta_points += 7
        elif 80 <= L <= 200: meta_points += 4
        elif L > 0: meta_points += 2
    
    meta_tags_score = int(min(15, meta_points) / 15 * 100)
    tech_score += min(15, meta_points)

    # Page size / speed proxy
    size = len(html or '')
    if size < 50_000: ps_points = 15
    elif size < 100_000: ps_points = 12
    elif size < 200_000: ps_points = 8
    elif size < 500_000: ps_points = 5
    else: ps_points = 2
    page_speed_score = int(ps_points / 15 * 100)
    tech_score += ps_points

    # Security headers
    if headers is not None and 'check_security_headers_from_headers' in globals():
        sh = check_security_headers_from_headers(headers)
    else:
        sh = check_security_headers_in_html(html) if 'check_security_headers_in_html' in globals() else {}
    
    sec_cfg = getattr(SCORING_CONFIG, 'technical_thresholds', {}).get('security_headers', {'csp':4,'x_frame_options':3,'strict_transport':3}) if 'SCORING_CONFIG' in globals() else {'csp':4,'x_frame_options':3,'strict_transport':3}
    if sh.get('csp'): tech_score += sec_cfg.get('csp', 4)
    if sh.get('x_frame_options'): tech_score += sec_cfg.get('x_frame_options', 3)
    if sh.get('strict_transport'): tech_score += sec_cfg.get('strict_transport', 3)

    # Performance indicators
    performance_indicators = []
    if 'loading="lazy"' in html: 
        performance_indicators.append('Lazy loading')
    if '.webp' in (html or '').lower():
        performance_indicators.append('WebP images')
    if 'rel="preload"' in (html or '').lower():
        performance_indicators.append('Preloading')

    final = max(0, min(100, tech_score))
    
    # Return dict
    return {
        'has_ssl': has_ssl,
        'has_mobile_optimization': has_mobile,
        'page_speed_score': page_speed_score,
        'has_analytics': analytics.get('has_analytics', False),
        'has_sitemap': check_sitemap_indicators(soup) if 'check_sitemap_indicators' in globals() else False,
        'has_robots_txt': check_robots_indicators(html) if 'check_robots_indicators' in globals() else False,
        'meta_tags_score': meta_tags_score,
        'overall_technical_score': final,
        'security_headers': sh,
        'performance_indicators': performance_indicators
    }

def is_spa_domain(url: str) -> bool:
    """Check if domain suggests SPA usage"""
    domain = get_domain_from_url(url).lower()
    spa_domains = [
        'brandista.eu', 'www.brandista.eu',
        'app.', 'dashboard.', 'admin.', 'portal.'
    ]
    return any(hint in domain for hint in spa_domains)

def detect_spa_markers(html: str) -> bool:
    """Enhanced SPA detection with more markers"""
    if not html or len(html.strip()) < 100:
        return False
        
    html_lower = html.lower()
    
    # Strong SPA indicators
    strong_markers = [
        'id="root"', 'id="app"', 'id="__next"', 'id="nuxt"',
        'data-reactroot', 'data-react-helmet', 'ng-version=',
        '"__webpack_require__"', '"webpackChunkName"',
        'window.__INITIAL_STATE__', 'window.__PRELOADED_STATE__'
    ]
    
    # Framework markers
    framework_markers = [
        'react', 'vue.js', 'angular', 'svelte', 'next.js',
        'nuxt', 'gatsby', 'vite', 'webpack', 'parcel'
    ]
    
    # Build tool markers  
    build_markers = [
        'built with vite', 'created-by-webpack', 'generated-by',
        'build-time:', 'chunk-', 'runtime-', 'vendor-'
    ]
    
    strong_count = sum(1 for marker in strong_markers if marker in html_lower)
    framework_count = sum(1 for marker in framework_markers if marker in html_lower)
    build_count = sum(1 for marker in build_markers if marker in html_lower)
    
    # SPA if strong indicators OR significant framework+build presence
    return strong_count >= 1 or (framework_count >= 2 and build_count >= 1)

def validate_rendered_content(html: str) -> bool:
    """Validate that rendered content is meaningful"""
    if not html or len(html.strip()) < 200:
        return False
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove scripts and styles for text analysis
    for element in soup(['script', 'style', 'noscript']):
        element.decompose()
    
    text = soup.get_text().strip()
    words = text.split()
    
    # Content validation criteria
    has_sufficient_text = len(words) >= 50
    has_meaningful_elements = bool(soup.find_all(['h1', 'h2', 'h3', 'p', 'div']))
    not_just_loading = not ('loading' in text.lower() and len(words) < 20)
    
    return has_sufficient_text and has_meaningful_elements and not_just_loading

# ============================================================================
# UNIFIED CONTENT FETCHING WITH CACHING
# ============================================================================

def get_content_cache_key(url: str) -> str:
    """Generate cache key for content"""
    return f"content_{hashlib.md5(url.encode()).hexdigest()}"

def is_content_cache_valid(timestamp: datetime) -> bool:
    """Check if content cache entry is valid"""
    return (datetime.now() - timestamp).total_seconds() < SPA_CACHE_TTL

async def get_website_content(
    url: str,
    force_spa: bool = False,
    timeout: int = REQUEST_TIMEOUT,
    mode: str = CONTENT_FETCH_MODE
) -> Tuple[Optional[str], bool]:
    """
    Unified content fetching with caching (AGGRESSIVE by default).
    Returns: (html_content, used_spa)
    Strategy:
      - If mode == "aggressive": always attempt Playwright rendering first (if available).
      - Else: do HTTP fetch; if SPA markers or force_spa, then Playwright.
      - Auto-scroll & extra waits to maximize rendered DOM content.
      - Collect JSON-LD scripts and inline data to enrich content.
    """
    cache_key = get_content_cache_key(url)
    if cache_key in content_cache and is_content_cache_valid(content_cache[cache_key]['timestamp']):
        cached = content_cache[cache_key]
        logger.info(f"[content] cache hit: %s", url)
        return cached['content'], cached['used_spa']

    used_spa = False
    html_content: Optional[str] = None

    # Helper: HTTP fetch
    async def _fetch_http(u: str) -> Optional[httpx.Response]:
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                verify=True,
                limits=httpx.Limits(max_keepalive_connections=8, max_connections=16)
            ) as client:
                res = await client.get(u, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
                if res.status_code == 200:
                    return res
                if res.status_code in (301,302,303,307,308,404):
                    logger.warning("[http] status %s for %s", res.status_code, u)
                    return res
                logger.warning("[http] non-200 status %s for %s", res.status_code, u)
                return None
        except Exception as e:
            logger.warning("[http] fetch error for %s: %s", u, e)
            return None

    # Helper: Playwright render (aggressive)
    async def _render_spa(u: str) -> Optional[str]:
        nonlocal used_spa
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("[spa] Playwright not available; falling back to HTTP")
            return None
        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            logger.warning("[spa] import failed: %s", e)
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1440, "height": 900},
                    locale="en-US"
                )
                page = await context.new_page()

                xhr_store = []

                async def route_handler(route):
                    try:
                        req = route.request
                        # Block heavy resource types to speed up but keep CSS/JS/Doc/XHR
                        if BLOCK_HEAVY_RESOURCES and req.resource_type in {"image","media","font","stylesheet"}:
                            # allow stylesheet because CSS is needed; override to not block it
                            if req.resource_type != "stylesheet":
                                await route.abort()
                                return
                        await route.continue_()
                    except Exception:
                        try:
                            await route.continue_()
                        except Exception:
                            pass

                async def response_listener(response):
                    try:
                        req = response.request
                        ct = (response.headers.get("content-type") or "").lower()
                        # Capture only JSON/XHR-ish responses
                        if CAPTURE_XHR and (req.resource_type in {"xhr","fetch"} or "application/json" in ct or "text/json" in ct):
                            body = await response.body()
                            if body and len(body) <= MAX_XHR_BYTES:
                                # Store as UTF-8 text when possible, else skip
                                try:
                                    text = body.decode("utf-8", errors="ignore")
                                except Exception:
                                    text = ""
                                if text.strip():
                                    xhr_store.append({
                                        "url": req.url,
                                        "status": response.status,
                                        "content_type": ct,
                                        "length": len(body),
                                        "body": text
                                    })
                    except Exception:
                        pass

                await page.route("**/*", route_handler)
                page.on("response", response_listener)

                # Go and wait for network to be (nearly) idle
                
                
                # Try cookie banner auto-dismiss (best-effort)
                if COOKIE_AUTO_DISMISS:
                    try:
                        # Click by common buttons/texts
                        # 1) Try querySelector with aria-label/text
                        await page.evaluate("""(selList) => {
                            const tryClick = (el) => { try { el.click(); return true; } catch(e) { return false; } };
                            const sels = selList.split(',').map(s => s.trim()).filter(Boolean);
                            for (const s of sels) {
                                const el = document.querySelector(s);
                                if (el && tryClick(el)) return true;
                            }
                            const labels = ['Accept all','Accept','I agree','OK','Hyväksy kaikki','Hyväksy'];
                            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'));
                            for (const b of buttons) {
                                const t = (b.textContent||'').trim();
                                if (labels.some(l => t.toLowerCase().includes(l.toLowerCase()))) {
                                    if (tryClick(b)) return true;
                                }
                            }
                            return false;
                        }""", COOKIE_SELECTORS)
                    except Exception:
                        pass

                resp = await page.goto(u, wait_until="networkidle", timeout=timeout*1000)
                # Optional selector wait if configured
                if SPA_WAIT_FOR_SELECTOR:
                    try:
                        await page.wait_for_selector(SPA_WAIT_FOR_SELECTOR, timeout=SPA_EXTRA_WAIT_MS*2)
                    except Exception:
                        pass

                # Auto-scroll to load lazy content
                try:
                    await page.evaluate("""async (steps, pause) => {
                        const sleep = (ms) => new Promise(r=>setTimeout(r, ms));
                        let last = 0;
                        for (let i=0; i<steps; i++) {
                            window.scrollBy(0, Math.floor(window.innerHeight*0.9));
                            await sleep(pause);
                            const h = document.body.scrollHeight;
                            if (h === last) break;
                            last = h;
                        }
                        window.scrollTo(0, 0);
                    }""", SPA_MAX_SCROLL_STEPS, SPA_SCROLL_PAUSE_MS)
                except Exception:
                    pass

                # Wait a bit extra for content hydration
                try:
                    await page.wait_for_load_state("networkidle", timeout=SPA_EXTRA_WAIT_MS)
                except Exception:
                    pass

                # Harvest JSON-LD scripts to enrich analysis
                try:
                    jsonld_list = await page.evaluate("""() => {
                        const nodes = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
                        return nodes.map(n => n.textContent || '').filter(Boolean);
                    }""")
                    jsonld_blob = "\\n<!--JSONLD-->" + "\\n".join(jsonld_list) + "\\n<!--/JSONLD-->" if jsonld_list else ""
                except Exception:
                    jsonld_blob = ""

                # Capture final HTML
                
                # Append captured XHR JSON as HTML comment block (for analyzer ingestion)
                try:
                    xhr_blob = ""
                    if xhr_store:
                        import json as _json
                        xhr_blob = "\n<!--XHR-->" + _json.dumps(xhr_store) + "\n<!--/XHR-->"

                except Exception:
                    xhr_blob = ""

                html = await page.content()
                await context.close()
                await browser.close()

                used_spa = True
                return html + jsonld_blob + xhr_blob

        except Exception as e:
            logger.warning("[spa] render failed for %s: %s", u, e)
            return None

    # Aggressive path: try SPA first to maximize richness
    if mode == "aggressive" or force_spa:
        html = await _render_spa(url)
        if not html:
            # fallback to HTTP
            res = await _fetch_http(url)
            html = res.text if (res and res.status_code == 200 and res.text) else None
            used_spa = False
    else:
        # Balanced/light: HTTP first, then SPA if clearly needed
        res = await _fetch_http(url)
        text = res.text if (res and res.status_code == 200 and res.text) else ""
        needs_spa = force_spa or detect_spa_markers(text) or is_spa_domain(url)
        if needs_spa:
            html = await _render_spa(url) or text
            used_spa = html is not None and html != text
        else:
            html = text
            used_spa = False

    if not html or len(html.strip()) < 100:
        raise HTTPException(400, "Website returned insufficient content")

    # Cache and return
    content_cache[cache_key] = {
        'content': html,
        'used_spa': used_spa,
        'timestamp': datetime.now()
    }
    return html, used_spa

async def analyze_content_quality(html: str) -> Dict[str, Any]:
    """Complete content analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    text = extract_clean_text(soup)
    words = text.split()
    wc = len(words)
    score = 0
    
    media_types: List[str] = []
    interactive: List[str] = []
    
    # Volume scoring
    volume_score = calculate_content_score_configurable(wc)
    score += volume_score
    
    # Structure scoring
    if soup.find_all('h2'): score += 5
    if soup.find_all('h3'): score += 3
    if soup.find_all(['ul','ol']): score += 4
    if soup.find_all('table'): score += 3
    
    # Freshness
    fresh = check_content_freshness(soup, html)
    score += fresh * 3
    
    # Media types
    if soup.find_all('img'): 
        score += 5
        media_types.append('images')
    if soup.find_all('video') or 'youtube' in html.lower(): 
        score += 5
        media_types.append('video')
    
    # Interactive elements
    if soup.find_all('form'): 
        score += 5
        interactive.append('forms')
    if soup.find_all('button'): 
        score += 3
        interactive.append('buttons')
    
    # Blog detection
    blog_patterns = ['/blog', '/news', '/articles']
    has_blog = any(soup.find('a', href=re.compile(p, re.I)) for p in blog_patterns)
    if has_blog: score += 10
    
    final = max(0, min(100, score))
    
    return {
        'word_count': wc,
        'readability_score': calculate_readability_score(text),
        'keyword_density': {},
        'content_freshness': get_freshness_label(fresh),
        'has_blog': has_blog,
        'content_quality_score': final,
        'media_types': media_types,
        'interactive_elements': interactive
    }

async def analyze_ux_elements(html: str) -> Dict[str, Any]:
    """Complete UX analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Navigation scoring
    nav_score = 0
    nav_elements = []
    if soup.find('nav'): 
        nav_score += 20
        nav_elements.append('nav element')
    if soup.find('header'): 
        nav_score += 10
        nav_elements.append('header')
    if soup.find_all(['ul','ol'], class_=re.compile('nav|menu', re.I)): 
        nav_score += 20
        nav_elements.append('navigation lists')
    nav_score = min(100, nav_score)
    
    # Design framework detection
    design_score = 0
    design_frameworks = []
    hl = html.lower()
    for fw, pts in {'tailwind':25,'bootstrap':20,'foundation':15}.items():
        if fw in hl: 
            design_score += pts
            design_frameworks.append(fw)
            break
    if 'display: flex' in hl: 
        design_score += 10
        design_frameworks.append('flexbox')
    if '@media' in hl: 
        design_score += 10
    design_score = min(100, design_score)
    
    # Accessibility scoring
    a11y_score = 0
    accessibility_issues = []
    if soup.find('html', lang=True): 
        a11y_score += 10
    else:
        accessibility_issues.append('Missing lang attribute')
        
    imgs = soup.find_all('img')
    if imgs:
        with_alt = [i for i in imgs if i.get('alt','').strip()]
        a11y_score += int((len(with_alt)/len(imgs))*25)
        if len(with_alt) < len(imgs):
            accessibility_issues.append(f'{len(imgs) - len(with_alt)} images missing alt text')
    else: 
        a11y_score += 25
    
    # ARIA labels check
    if 'aria-' in hl:
        a11y_score += 10
    else:
        accessibility_issues.append('Limited ARIA labeling')
    
    a11y_score = min(100, a11y_score)
    
    # Mobile UX - KORJATTU SKAALAUS 0-100
    mobile_raw = 0
    vp = soup.find('meta', attrs={'name':'viewport'})
    if vp:
        vc = vp.get('content','')
        if 'width=device-width' in vc: 
            mobile_raw += 40
        if 'initial-scale=1' in vc: 
            mobile_raw += 20
        if detect_responsive_signals(html):
            mobile_raw += 20
        if '@media' in hl:
            mobile_raw += 20
    
    mobile_score = min(100, mobile_raw)
    overall = int((nav_score + design_score + a11y_score + mobile_score)/4)
    
    return {
        'navigation_score': nav_score,
        'visual_design_score': design_score,
        'accessibility_score': a11y_score,
        'mobile_ux_score': mobile_score,
        'overall_ux_score': overall,
        'accessibility_issues': accessibility_issues,
        'navigation_elements': nav_elements,
        'design_frameworks': design_frameworks
    }

async def analyze_social_media_presence(url: str, html: str) -> Dict[str, Any]:
    """Complete social media analysis"""
    platforms = extract_social_platforms(html)
    soup = BeautifulSoup(html, 'html.parser')
    
    score = len(platforms) * 10
    
    # Sharing buttons check
    has_sharing = any(p in html.lower() for p in ['addtoany','sharethis','addthis','social-share'])
    if has_sharing: score += 15
    
    # Open Graph tags
    og_count = len(soup.find_all('meta', property=re.compile('^og:')))
    if og_count >= 4: score += 10
    elif og_count >= 2: score += 5
    
    # Twitter cards
    twitter_cards = bool(soup.find_all('meta', attrs={'name': re.compile('^twitter:')}))
    if twitter_cards: score += 5
    
    return {
        'platforms': platforms,
        'total_followers': 0,
        'engagement_rate': 0.0,
        'posting_frequency': "unknown",
        'social_score': min(100, score),
        'has_sharing_buttons': has_sharing,
        'open_graph_tags': og_count,
        'twitter_cards': twitter_cards
    }

async def analyze_competitive_positioning(url: str, basic: Dict[str, Any]) -> Dict[str, Any]:
    """Complete competitive analysis"""
    score = basic.get('digital_maturity_score', 0)
    
    if score >= 75:
        position = "Digital Leader"
        advantages = ["Excellent digital presence", "Advanced technical execution", "Superior user experience"]
        threats = ["Pressure to innovate continuously", "High expectations from users"]
        comp_score = 85
    elif score >= 60:
        position = "Strong Performer"
        advantages = ["Solid digital foundation", "Good technical implementation", "Above-average user experience"]
        threats = ["Gap to market leaders", "Risk of being overtaken"]
        comp_score = 70
    elif score >= 45:
        position = "Average Competitor"
        advantages = ["Baseline digital presence established", "Core functionality working"]
        threats = ["At risk of falling behind", "Below-average user expectations"]
        comp_score = 50
    else:
        position = "Below Average"
        advantages = ["Significant upside potential", "Room for major improvements"]
        threats = ["Major competitive disadvantage", "Poor user experience"]
        comp_score = 30
    
    return {
        'market_position': position,
        'competitive_advantages': advantages,
        'competitive_threats': threats,
        'market_share_estimate': "Data not available",
        'competitive_score': comp_score,
        'industry_comparison': {
            'your_score': score,
            'industry_average': 45,
            'top_quartile': 70,
            'bottom_quartile': 30
        }
    }

def _fmt_range(low: int, high: int, suffix: str) -> str:
    return f"{low}–{high} {suffix}"

def _confidence_label(val: int) -> str:
    return "H" if val >= 75 else "M" if val >= 50 else "L"

def compute_business_impact_with_input(
    basic: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    revenue_input: Optional[RevenueInputRequest] = None
) -> BusinessImpactDetailed:
    """
    Compute business impact with optional user-provided revenue data
    
    Priority logic:
    1. If user provides annual_revenue → use that
    2. If user provides monthly_revenue → calculate annual (monthly × 12)
    3. If user provides traffic + conversion + AOV → calculate revenue
    4. Otherwise → use EU SME average (450k€)
    """
    
    score = basic.get('digital_maturity_score', 0)
    seo_pts = basic.get('score_breakdown', {}).get('seo_basics', 0)
    mob_pts = basic.get('score_breakdown', {}).get('mobile', 0)
    
    seo_w = SCORING_CONFIG.weights.get('seo_basics', 20) or 1
    mob_w = SCORING_CONFIG.weights.get('mobile', 15) or 1
    
    seo_pct = int(seo_pts / seo_w * 100)
    mobile_pct = int(mob_pts / mob_w * 100)
    
    content_score = content.get('content_quality_score', 0)
    ux_score = ux.get('overall_ux_score', 0)
    
    # ===== REVENUE DETERMINATION =====
    calculation_basis = "estimated"
    metrics_used = {}
    annual_revenue = 450_000  # Default EU SME average
    
    # ✅ KORJAUS: Handle both Pydantic model AND dict
    if revenue_input:
        # Convert to dict if it's a Pydantic model
        if hasattr(revenue_input, 'dict'):
            rev_data = revenue_input.dict()
        elif isinstance(revenue_input, dict):
            rev_data = revenue_input
        else:
            rev_data = {}
        
        # Now safely access as dict
        if rev_data.get('annual_revenue') and rev_data['annual_revenue'] > 0:
            annual_revenue = rev_data['annual_revenue']
            calculation_basis = "provided"
            metrics_used['annual_revenue'] = annual_revenue
            
        elif rev_data.get('monthly_revenue') and rev_data['monthly_revenue'] > 0:
            annual_revenue = rev_data['monthly_revenue'] * 12
            calculation_basis = "provided"
            metrics_used['monthly_revenue'] = rev_data['monthly_revenue']
            metrics_used['calculated_annual'] = annual_revenue
            
        elif (rev_data.get('monthly_visitors') and 
              rev_data.get('conversion_rate') and 
              rev_data.get('average_order_value')):
            # Calculate revenue from traffic metrics
            monthly_orders = (rev_data['monthly_visitors'] * 
                            rev_data['conversion_rate'] / 100)
            monthly_revenue = int(monthly_orders * rev_data['average_order_value'])
            annual_revenue = monthly_revenue * 12
            calculation_basis = "calculated"
            metrics_used.update({
                'monthly_visitors': rev_data['monthly_visitors'],
                'conversion_rate': rev_data['conversion_rate'],
                'average_order_value': rev_data['average_order_value'],
                'calculated_monthly_revenue': monthly_revenue,
                'calculated_annual_revenue': annual_revenue
            })
        else:
            calculation_basis = "hybrid"
            metrics_used['note'] = "Using EU SME average, partial data provided"
    
    # ===== LEAD GENERATION (original logic) =====
    lead_low = max(3, (seo_pct + content_score) // 40)
    lead_high = max(lead_low + 2, (seo_pct + content_score) // 25)
    
    # ===== REVENUE CALCULATION =====
    score_improvement_potential = max(10, 90 - score)
    
    # Base growth rates (conservative to aggressive based on score gap)
    if score < 30:
        # Very low score → high potential
        growth_rate_low = (score_improvement_potential * 0.5) / 100
        growth_rate_high = (score_improvement_potential * 0.9) / 100
    elif score < 50:
        # Below average → good potential
        growth_rate_low = (score_improvement_potential * 0.4) / 100
        growth_rate_high = (score_improvement_potential * 0.7) / 100
    elif score < 70:
        # Average → moderate potential
        growth_rate_low = (score_improvement_potential * 0.3) / 100
        growth_rate_high = (score_improvement_potential * 0.5) / 100
    else:
        pass
        # High score → incremental gains
        growth_rate_low = (score_improvement_potential * 0.2) / 100
        growth_rate_high = (score_improvement_potential * 0.4) / 100
    
    # Calculate impact
    revenue_impact_low = int(annual_revenue * growth_rate_low)
    revenue_impact_high = int(annual_revenue * growth_rate_high)
    
    monthly_impact_low = revenue_impact_low // 12
    monthly_impact_high = revenue_impact_high // 12
    
    # ===== IMPROVEMENT AREAS ANALYSIS =====
    improvement_areas = []
    if seo_pct < 60:
        improvement_areas.append("SEO optimization")
    if mobile_pct < 60:
        improvement_areas.append("Mobile experience")
    if content_score < 60:
        improvement_areas.append("Content depth and quality")
    if ux_score < 60:
        improvement_areas.append("User experience design")
    if score < 50:
        improvement_areas.append("Technical foundation")
    
    # ===== SCENARIO PLANNING =====
    potential_scenarios = {
        "quick_wins": {
            "timeframe": "1-3 months",
            "effort": "low",
            "revenue_uplift": f"€{revenue_impact_low//3:,} - €{revenue_impact_low//2:,}",
            "actions": ["Fix critical SEO issues", "Improve mobile viewport", "Add analytics tracking"]
        },
        "standard_improvement": {
            "timeframe": "3-6 months",
            "effort": "medium",
            "revenue_uplift": f"€{revenue_impact_low:,} - €{int(revenue_impact_low*1.5):,}",
            "actions": ["Content strategy execution", "Technical SEO overhaul", "UX optimization"]
        },
        "comprehensive_transformation": {
            "timeframe": "6-12 months",
            "effort": "high",
            "revenue_uplift": f"€{int(revenue_impact_high*0.8):,} - €{revenue_impact_high:,}",
            "actions": ["Complete digital strategy", "Marketing automation", "Conversion optimization"]
        }
    }
    
    # ===== FORMATTING =====
    def format_currency(amount: int) -> str:
        if amount >= 1_000_000:
            return f"€{amount/1_000_000:.1f}M"
        elif amount >= 1000:
            return f"€{amount//1000}k"
        else:
            return f"€{amount}"
    
    revenue_range = (
        f"{format_currency(revenue_impact_low)}–{format_currency(revenue_impact_high)}/year "
        f"({format_currency(monthly_impact_low)}–{format_currency(monthly_impact_high)}/mo)"
    )
    
    monthly_range = f"{format_currency(monthly_impact_low)}–{format_currency(monthly_impact_high)}"
    
    # Confidence based on data quality
    if calculation_basis == "provided":
        confidence = "H"  # High confidence with real data
    elif calculation_basis == "calculated":
        confidence = "M"  # Medium confidence with derived data
    else:
        confidence = "L"  # Low confidence with estimates
    
    # Trust effect
    customer_trust_effect = (
        "Improves perceived quality (NPS +2–4)" 
        if basic.get('modernity_score', 0) >= 50 
        else "Small positive trust signal"
    )
    
    return BusinessImpactDetailed(
        lead_gain_estimate=_fmt_range(lead_low, lead_high, "leads/mo"),
        revenue_uplift_range=revenue_range,
        monthly_revenue_range=monthly_range,
        confidence=confidence,
        customer_trust_effect=customer_trust_effect,
        calculation_basis=calculation_basis,
        metrics_used=metrics_used,
        improvement_areas=improvement_areas,
        potential_scenarios=potential_scenarios
    )

# Keep old function for backward compatibility
def compute_business_impact(
    basic: Dict[str, Any], 
    content: Dict[str, Any], 
    ux: Dict[str, Any],
    estimated_annual_revenue: int = 450_000
) -> BusinessImpact:
    """Backward compatible wrapper - calls new function without revenue input"""
    detailed = compute_business_impact_with_input(basic, content, ux, revenue_input=None)
    # Convert detailed to simple BusinessImpact
    return BusinessImpact(
        lead_gain_estimate=detailed.lead_gain_estimate,
        revenue_uplift_range=detailed.revenue_uplift_range,
        confidence=detailed.confidence,
        customer_trust_effect=detailed.customer_trust_effect
    )

def build_role_summaries(url: str, basic: Dict[str, Any], impact: BusinessImpact, language: str = 'en') -> RoleSummaries:
    """Generate role-specific summaries based on actual analysis findings"""
    s = basic.get('digital_maturity_score', 0)
    breakdown = basic.get('score_breakdown', {})
    
    state = ("leader" if s >= 75 else "strong" if s >= 60 else "baseline" if s >= 45 else "early")
    
    # Identify top priorities dynamically by calculating completion percentage
    weights = SCORING_CONFIG.weights
    completion = {
        'security': (breakdown.get('security', 0) / weights['security']) * 100 if weights['security'] > 0 else 100,
        'seo': (breakdown.get('seo_basics', 0) / weights['seo_basics']) * 100 if weights['seo_basics'] > 0 else 100,
        'content': (breakdown.get('content', 0) / weights['content']) * 100 if weights['content'] > 0 else 100,
        'mobile': (breakdown.get('mobile', 0) / weights['mobile']) * 100 if weights['mobile'] > 0 else 100,
        'technical': (breakdown.get('technical', 0) / weights['technical']) * 100 if weights['technical'] > 0 else 100,
    }
    
    # Sort by lowest completion (biggest gaps = highest priority)
    sorted_gaps = sorted(completion.items(), key=lambda x: x[1])
    top_gaps = [gap[0] for gap in sorted_gaps[:3]]
    
    # Map categories to actionable business language (language-aware)
    if language == 'fi':
        action_map = {
            'security': 'SSL + turvallisuusotsikot',
            'seo': 'SEO-perusteet',
            'content': 'sisällön syvyys',
            'mobile': 'mobiilikäyttökokemus',
            'technical': 'tekninen SEO + analytiikka',
        }
    else:
        action_map = {
            'security': 'SSL + security headers',
            'seo': 'SEO fundamentals',
            'content': 'content depth',
            'mobile': 'mobile UX',
            'technical': 'technical SEO + analytics',
        }
    
    priority_items = [action_map.get(gap, gap) for gap in top_gaps]
    
    # Ensure at least 2 priorities exist (fallback for edge cases)
    if len(priority_items) < 2:
        if language == 'fi':
            priority_items.extend(['tekninen SEO', 'sisällön optimointi'])
        else:
            priority_items.extend(['technical SEO', 'content optimization'])
    
    # Generate summaries based on language
    if language == 'fi':
        state_fi = {
            'leader': 'johtaja',
            'strong': 'vahva',
            'baseline': 'perustaso',
            'early': 'alkuvaihe'
        }[state]
        
        # CEO: Strategic overview
        ceo_summary = (
            f"Olemme {s}/100 ({state_fi}). "
            f"Tärkeimmät prioriteetit: {priority_items[0]}, {priority_items[1]}. "
            f"Jos toteutamme nämä korjaukset, voimme avata {impact.revenue_uplift_range} "
            f"ja {impact.lead_gain_estimate}. Fokus: yksi muutos viikossa."
        )
        
        # CMO: Growth levers
        cmo_focus = []
        if 'seo' in top_gaps or 'content' in top_gaps:
            cmo_focus.append(f"SEO + sisältö → {impact.lead_gain_estimate}")
        if 'mobile' in top_gaps:
            cmo_focus.append(f"mobiilikäyttökokemus → parempi konversio")
        if not cmo_focus:
            cmo_focus.append(f"Konversion optimointi → {impact.revenue_uplift_range}")
        
        cmo_summary = (
            f"Kasvun vipuvarret: {' + '.join(cmo_focus)}. "
            f"Tavoite: {impact.revenue_uplift_range}. Seuraa viikoittain liidien laatua."
        )
        
        # CTO: Technical priorities
        cto_priorities = []
        if 'security' in top_gaps:
            cto_priorities.append("SSL + turvallisuusotsikot")
        if 'mobile' in top_gaps:
            cto_priorities.append("Core Web Vitals (LCP, CLS)")
        if 'technical' in top_gaps:
            cto_priorities.append("analytiikka + tekninen SEO")
        
        if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
            cto_priorities.insert(0, "SSR/esirenderöinti SPA:lle")
        
        if not cto_priorities:
            cto_priorities = ["viivästä ei-kriittinen JS", "optimoi kuvat"]
        
        cto_summary = (
            f"Priorisoi: {', '.join(cto_priorities[:3])}. "
            f"Toimita yksi tekninen voitto per sprintti."
        )
    else:
        # English (original)
        ceo_summary = (
            f"We are at {s}/100 ({state}). "
            f"Top priorities: {priority_items[0]}, {priority_items[1]}. "
            f"If we ship these fixes, we can unlock {impact.revenue_uplift_range} "
            f"and {impact.lead_gain_estimate}. Focus: one change per week."
        )
        
        cmo_focus = []
        if 'seo' in top_gaps or 'content' in top_gaps:
            cmo_focus.append(f"SEO + content → {impact.lead_gain_estimate}")
        if 'mobile' in top_gaps:
            cmo_focus.append(f"mobile UX → better conversion")
        if not cmo_focus:
            cmo_focus.append(f"Conversion optimization → {impact.revenue_uplift_range}")
        
        cmo_summary = (
            f"Growth levers: {' + '.join(cmo_focus)}. "
            f"Target: {impact.revenue_uplift_range}. Track weekly progress on lead quality."
        )
        
        cto_priorities = []
        if 'security' in top_gaps:
            cto_priorities.append("SSL + security headers")
        if 'mobile' in top_gaps:
            cto_priorities.append("Core Web Vitals (LCP, CLS)")
        if 'technical' in top_gaps:
            cto_priorities.append("analytics + technical SEO")
        
        if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
            cto_priorities.insert(0, "SSR/prerender for SPA")
        
        if not cto_priorities:
            cto_priorities = ["defer non-critical JS", "optimize images"]
        
        cto_summary = (
            f"Prioritize: {', '.join(cto_priorities[:3])}. "
            f"Ship one technical win per sprint."
        )
    
    return RoleSummaries(
        CEO=ceo_summary,
        CMO=cmo_summary,
        CTO=cto_summary
    )

def build_plan_90d(basic: Dict[str, Any], content: Dict[str, Any], technical: Dict[str, Any], language: str = 'en') -> Plan90D:
    """Build a realistic week-by-week 90-day execution plan dynamically based on actual gaps"""
    score = basic.get('digital_maturity_score', 0)
    breakdown = basic.get('score_breakdown', {})
    
    # Translations dictionary - TÄYSI TOTEUTUS
    translations = {
        'en': {
            'actions': {
                'ssl_install': 'Week 1: Install SSL certificate + enable HTTPS redirect',
                'security_headers': 'Week 2: Configure security headers (CSP, HSTS, X-Frame-Options)',
                'ga4_install': 'Week 1: Install GA4 + define 3-5 key conversion events',
                'seo_audit': 'Week {w}: Audit & fix titles/meta descriptions on top 10 pages',
                'heading_fix': 'Week {w}: Add missing H1 tags + fix heading hierarchy',
                'viewport_meta': 'Week {w}: Add viewport meta + test responsive breakpoints',
                'compress_images': 'Week {w}: Compress images on top 10 pages + enable lazy loading',
                'content_research': 'Week 5-6: Research & outline 6 pillar content topics (keyword analysis)',
                'content_write': 'Week 7-8: Write & publish first 3 pillar articles (2000+ words each)',
                'content_update': 'Week 5-6: Update existing content - refresh dates, add internal links',
                'faq_schema': 'Week 7: Add FAQ schema markup to key pages',
                'sitemap_submit': 'Week 8: Build XML sitemap + submit to Search Console',
                'ssr_research': 'Week 7-8: Research SSR/prerendering options for SPA',
                'content_publish': 'Week 9-10: Publish remaining 3 pillar articles + 6 cluster posts',
                'internal_linking': 'Week 11: Build internal linking structure',
                'ab_testing': 'Week 9-10: A/B test top 3 landing pages (headlines, CTAs)',
                'ssr_implement': 'Week 10-11: Implement SSR/prerendering for critical routes',
                'cwv_optimize': 'Week 10: Optimize Core Web Vitals (LCP < 2.5s, CLS < 0.1)',
                'conversion_tracking': 'Week 11-12: Set up conversion tracking + GA4 dashboard',
                'review_metrics': 'Week 12: Review metrics, document wins, plan Q2 priorities',
            },
            'one_thing': {
                'ssl': 'Install SSL certificate (blocks everything else)',
                'analytics': 'Install GA4 tracking (need data to make decisions)',
                'seo': 'Fix titles & meta on your top 10 pages',
                'content': 'Outline your first pillar article topic',
                'default': 'Run Lighthouse audit on top 5 pages, note top 3 issues'
            }
        },
        'fi': {
            'actions': {
                'ssl_install': 'Viikko 1: Asenna SSL-sertifikaatti + HTTPS-uudelleenohjaus',
                'security_headers': 'Viikko 2: Määritä turvallisuusotsikot (CSP, HSTS, X-Frame-Options)',
                'ga4_install': 'Viikko 1: Asenna GA4 + määrittele 3-5 konversiota',
                'seo_audit': 'Viikko {w}: Tarkasta & korjaa otsikot/meta-kuvaukset 10 sivulla',
                'heading_fix': 'Viikko {w}: Lisää H1-tagit + korjaa otsikkohierarkia',
                'viewport_meta': 'Viikko {w}: Lisää viewport meta + testaa responsiivisuus',
                'compress_images': 'Viikko {w}: Pakkaa kuvat + ota käyttöön lazy loading',
                'content_research': 'Viikko 5-6: Tutki 6 pilari-sisältöaihetta (avainsanat)',
                'content_write': 'Viikko 7-8: Kirjoita & julkaise 3 pilariartikkelia (2000+ sanaa)',
                'content_update': 'Viikko 5-6: Päivitä sisältö - päivämäärät, sisäiset linkit',
                'faq_schema': 'Viikko 7: Lisää FAQ schema-merkintä avainsivuille',
                'sitemap_submit': 'Viikko 8: Rakenna XML-sivukartta + lähetä Search Consoleen',
                'ssr_research': 'Viikko 7-8: Tutki SSR/esirenderöintivaihtoehdot SPA:lle',
                'content_publish': 'Viikko 9-10: Julkaise loput 3 artikkelia + 6 klusteripostausta',
                'internal_linking': 'Viikko 11: Rakenna sisäinen linkitysrakenne',
                'ab_testing': 'Viikko 9-10: A/B-testaa 3 aloitussivua (otsikot, CTA:t)',
                'ssr_implement': 'Viikko 10-11: Ota käyttöön SSR/esirenderöinti',
                'cwv_optimize': 'Viikko 10: Optimoi Core Web Vitals (LCP < 2.5s, CLS < 0.1)',
                'conversion_tracking': 'Viikko 11-12: Aseta konversiontaseuranta + GA4-dashboard',
                'review_metrics': 'Viikko 12: Tarkista mittarit, dokumentoi voitot',
            },
            'one_thing': {
                'ssl': 'Asenna SSL-sertifikaatti (estää kaiken muun)',
                'analytics': 'Asenna GA4-seuranta (tarvitaan dataa päätöksiin)',
                'seo': 'Korjaa otsikot & metat 10 sivullasi',
                'content': 'Hahmottele ensimmäinen pilariartikkeli',
                'default': 'Suorita Lighthouse-auditointi 5 sivulle'
            }
        }
    }
    
    t = translations.get(language, translations['en'])
    actions = t['actions']
    one_thing_texts = t['one_thing']
    
    # DYNAAMINEN PRIORISOINTI
    weights = SCORING_CONFIG.weights
    completion = {
        'security': (breakdown.get('security', 0) / weights['security']) * 100 if weights['security'] > 0 else 100,
        'seo': (breakdown.get('seo_basics', 0) / weights['seo_basics']) * 100 if weights['seo_basics'] > 0 else 100,
        'content': (breakdown.get('content', 0) / weights['content']) * 100 if weights['content'] > 0 else 100,
        'mobile': (breakdown.get('mobile', 0) / weights['mobile']) * 100 if weights['mobile'] > 0 else 100,
        'technical': (breakdown.get('technical', 0) / weights['technical']) * 100 if weights['technical'] > 0 else 100,
    }
    
    sorted_priorities = sorted(completion.items(), key=lambda x: x[1])
    top_priorities = [p[0] for p in sorted_priorities if p[1] < 70][:3]
    
    if not technical.get('has_analytics') and 'technical' not in top_priorities:
        top_priorities.append('analytics')
    
    if not top_priorities:
        top_priorities = ['content', 'mobile', 'technical']
    
    # === WAVE 1 (Weeks 1-4): FOUNDATION ===
    wave_1 = []
    week = 1
    
    if 'security' in top_priorities and completion.get('security', 100) < 30:
        wave_1.extend([actions['ssl_install'], actions['security_headers']])
        week = 3
    
    if 'analytics' in top_priorities or not technical.get('has_analytics'):
        wave_1.append(actions['ga4_install'])
        week = max(week, 2)
    
    if 'seo' in top_priorities:
        wave_1.append(actions['seo_audit'].format(w=week))
        wave_1.append(actions['heading_fix'].format(w=week+1))
        week += 2
    
    if 'mobile' in top_priorities and completion.get('mobile', 100) < 50:
        wave_1.append(actions['viewport_meta'].format(w=week))
    
    if len(wave_1) < 4:
        wave_1.append(actions['compress_images'].format(w=4))
    
    # === WAVE 2 (Weeks 5-8): CONTENT & TECHNICAL SEO ===
    wave_2 = []
    
    # Sisältöstrategia
    if 'content' in top_priorities:
        if content.get('word_count', 0) < 500:
            wave_2.extend([actions['content_research'], actions['content_write']])
        else:
            wave_2.append(actions['content_update'])
    
    # Technical SEO - KORJATTU logiikka
    if 'seo' in top_priorities or 'technical' in top_priorities:
        # Lisää FAQ schema jos ei jo täynnä
        if len(wave_2) < 3:
            wave_2.append(actions['faq_schema'])
        # Lisää sitemap jos ei jo täynnä
        if len(wave_2) < 4:
            wave_2.append(actions['sitemap_submit'])
    
    # SPA-ongelma
    if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
        if len(wave_2) < 4:
            wave_2.append(actions['ssr_research'])
    
    # Varmista max 4
    wave_2 = wave_2[:4]
    
    # === WAVE 3 (Weeks 9-12): SCALE ===
    wave_3 = []
    
    if 'content' in top_priorities:
        wave_3.extend([actions['content_publish'], actions['internal_linking']])
    else:
        wave_3.append(actions['ab_testing'])
    
    if basic.get('spa_detected'):
        wave_3.append(actions['ssr_implement'])
    else:
        wave_3.append(actions['cwv_optimize'])
    
    wave_3.extend([actions['conversion_tracking'], actions['review_metrics']])
    
    # === ONE THING ===
    if 'security' in top_priorities and completion.get('security', 100) < 30:
        one_thing = one_thing_texts['ssl']
    elif not technical.get('has_analytics'):
        one_thing = one_thing_texts['analytics']
    elif 'seo' in top_priorities:
        one_thing = one_thing_texts['seo']
    elif 'content' in top_priorities:
        one_thing = one_thing_texts['content']
    else:
        one_thing = one_thing_texts['default']
    
    return Plan90D(
        wave_1=wave_1[:5],
        wave_2=wave_2[:4],
        wave_3=wave_3[:5],
        one_thing_this_week=one_thing
    )
def build_risk_register(basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any]) -> List[RiskItem]:
    """Build risk register with likelihood, impact, mitigation"""
    risks = []
    breakdown = basic.get('score_breakdown', {})
    
    # Content risk
    if content.get('content_quality_score', 0) < 50:
        risks.append(RiskItem(
            risk="Thin content → weak rankings",
            likelihood=3,
            impact=3,
            mitigation="Pillar/cluster content plan",
            risk_score=9
        ))
    
    # SPA risk
    if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
        risks.append(RiskItem(
            risk="SPA client-only rendering → low visibility",
            likelihood=3,
            impact=4,
            mitigation="SSR/prerender critical routes",
            risk_score=12
        ))
    
    # Security risk
    if breakdown.get('security', 0) < 10:
        risks.append(RiskItem(
            risk="Weak security → trust/SEO penalty",
            likelihood=2,
            impact=4,
            mitigation="Install SSL + security headers",
            risk_score=8
        ))
    
    # Mobile risk
    if breakdown.get('mobile', 0) < 10:
        risks.append(RiskItem(
            risk="Poor mobile UX → high bounce rate",
            likelihood=4,
            impact=3,
            mitigation="Responsive design + CWV optimization",
            risk_score=12
        ))
    
    return risks


def build_snippet_examples(url: str, basic: Dict[str, Any]) -> SnippetExamples:
    """Build SEO snippet examples"""
    domain = get_domain_from_url(url).capitalize()
    
    return SnippetExamples(
        seo_title=[
            f"{domain} — fast, modern & reliable",
            f"{domain}: solutions that drive results",
            f"{domain} | Everything you need to grow"
        ],
        meta_desc=[
            f"{domain} helps you get measurable results. Explore features, stories and pricing — start today.",
            f"Modern {domain} with impact. See how teams ship better experiences. Try now."
        ],
        h1_intro=[
            f"{domain} that gets the job done.",
            f"Build, ship and grow with {domain}."
        ],
        product_copy=[
            "Value prop in 1–2 lines → 2–3 benefits with proof → single CTA.",
            "Problem → outcome → proof → CTA. Keep it scannable (40–80 words)."
        ]
    )
# ============================================================================
# AI SEARCH VISIBILITY ANALYSIS (NORDIC FIRST)
# ============================================================================

def _check_schema_markup(html: str, soup: BeautifulSoup) -> AISearchFactor:
    """Analyze structured data quality for AI parsing"""
    score = 0
    findings = []
    recommendations = []
    
    # Check for JSON-LD
    jsonld_scripts = soup.find_all('script', type='application/ld+json')
    if jsonld_scripts:
        score += 40
        findings.append(f"Found {len(jsonld_scripts)} JSON-LD schema blocks")
        
        # Parse and check schema types
        schema_types = []
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string or '{}')
                schema_type = data.get('@type', '')
                if schema_type:
                    schema_types.append(schema_type)
            except:
                pass
        
        if schema_types:
            findings.append(f"Schema types: {', '.join(set(schema_types))}")
            if 'FAQPage' in schema_types or 'QAPage' in schema_types:
                score += 20
                findings.append("FAQ/QA schema found - excellent for AI parsing")
            if 'Organization' in schema_types:
                score += 10
                findings.append("Organization schema provides entity context")
    else:
        recommendations.append("Add JSON-LD structured data (especially FAQPage)")
    
    # Check for microdata/RDFa
    if soup.find_all(attrs={'itemtype': True}):
        score += 10
        findings.append("Microdata markup detected")
    
    # Check Open Graph
    og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
    if len(og_tags) >= 4:
        score += 15
        findings.append(f"Rich Open Graph metadata ({len(og_tags)} tags)")
    elif og_tags:
        score += 5
        recommendations.append("Expand Open Graph metadata coverage")
    
    if score < 30:
        recommendations.append("Implement comprehensive schema markup strategy")
    
    status = "excellent" if score >= 70 else "good" if score >= 50 else "needs_improvement" if score >= 30 else "poor"
    
    return AISearchFactor(
        name="Structured Data Quality",
        score=score,
        status=status,
        findings=findings,
        recommendations=recommendations
    )

def _check_semantic_structure(html: str, soup: BeautifulSoup) -> AISearchFactor:
    """Analyze semantic HTML structure for AI comprehension"""
    score = 0
    findings = []
    recommendations = []
    
    # Check semantic HTML5 elements
    semantic_elements = {
        'article': 15,
        'section': 10,
        'nav': 8,
        'aside': 5,
        'header': 8,
        'footer': 5,
        'main': 12
    }
    
    found_elements = []
    for element, points in semantic_elements.items():
        if soup.find(element):
            score += points
            found_elements.append(element)
    
    if found_elements:
        findings.append(f"Semantic HTML5 elements: {', '.join(found_elements)}")
    else:
        recommendations.append("Use semantic HTML5 elements (article, section, main)")
    
    # Check heading hierarchy
    h1_count = len(soup.find_all('h1'))
    h2_count = len(soup.find_all('h2'))
    h3_count = len(soup.find_all('h3'))
    
    if h1_count == 1:
        score += 10
        findings.append("Proper H1 hierarchy (exactly 1)")
    else:
        recommendations.append(f"Fix H1 count (found {h1_count}, should be 1)")
    
    if h2_count >= 3:
        score += 10
        findings.append(f"Good content structure ({h2_count} H2 headings)")
    elif h2_count >= 1:
        score += 5
    else:
        recommendations.append("Add H2 headings to structure content")
    
    # Check for lists (AI models like structured lists)
    lists = soup.find_all(['ul', 'ol'])
    if len(lists) >= 3:
        score += 10
        findings.append(f"Well-structured content with {len(lists)} lists")
    elif lists:
        score += 5
    
    status = "excellent" if score >= 70 else "good" if score >= 50 else "needs_improvement" if score >= 30 else "poor"
    
    return AISearchFactor(
        name="Semantic Structure",
        score=min(100, score),
        status=status,
        findings=findings,
        recommendations=recommendations
    )

def _assess_content_comprehensiveness(content: Dict[str, Any], html: str, soup: BeautifulSoup) -> AISearchFactor:
    """Assess content depth and quality for AI training/citation"""
    score = 0
    findings = []
    recommendations = []
    
    word_count = content.get('word_count', 0)
    
    # Word count scoring
    if word_count >= 2500:
        score += 40
        findings.append(f"Comprehensive content ({word_count} words)")
    elif word_count >= 1500:
        score += 30
        findings.append(f"Good content depth ({word_count} words)")
    elif word_count >= 800:
        score += 20
        findings.append(f"Moderate content ({word_count} words)")
    else:
        score += 10
        recommendations.append(f"Expand content depth (current: {word_count} words, target: 1500+)")
    
    # Check for FAQ/Q&A format (AI models love this)
    faq_indicators = ['faq', 'frequently asked', 'questions', 'q&a', 'what is', 'how to', 'why']
    html_lower = html.lower()
    faq_matches = sum(1 for indicator in faq_indicators if indicator in html_lower)
    
    if faq_matches >= 3:
        score += 25
        findings.append("FAQ/Q&A format detected - ideal for AI parsing")
    elif faq_matches >= 1:
        score += 10
        findings.append("Some conversational format detected")
    else:
        recommendations.append("Add FAQ section with question-answer pairs")
    
    # Check for definitions/explanations
    definition_indicators = soup.find_all(['dl', 'dt', 'dd'])
    if definition_indicators:
        score += 10
        findings.append("Definition lists found - clear explanations")
    
    # Check content freshness
    freshness = content.get('content_freshness', 'unknown')
    if freshness in ['very_fresh', 'fresh']:
        score += 15
        findings.append(f"Fresh content ({freshness})")
    elif freshness == 'moderate':
        score += 8
    else:
        recommendations.append("Update content with current year/dates")
    
    # Check for examples/case studies
    example_keywords = ['example', 'case study', 'for instance', 'such as']
    example_count = sum(html_lower.count(keyword) for keyword in example_keywords)
    if example_count >= 5:
        score += 10
        findings.append("Rich with examples and case studies")
    
    status = "excellent" if score >= 75 else "good" if score >= 55 else "needs_improvement" if score >= 35 else "poor"
    
    return AISearchFactor(
        name="Content Comprehensiveness",
        score=min(100, score),
        status=status,
        findings=findings,
        recommendations=recommendations
    )

def _check_authority_markers(technical: Dict[str, Any], basic: Dict[str, Any]) -> AISearchFactor:
    """Check authority signals that AI models consider"""
    score = 0
    findings = []
    recommendations = []
    
    # HTTPS (trust signal)
    if basic.get('has_ssl', False):
        score += 20
        findings.append("HTTPS enabled - trusted source")
    else:
        recommendations.append("CRITICAL: Enable HTTPS for trust")
    
    # Security headers (additional trust)
    security_headers = technical.get('security_headers', {})
    if security_headers.get('csp'):
        score += 10
        findings.append("Content Security Policy configured")
    if security_headers.get('strict_transport'):
        score += 10
        findings.append("HSTS enabled")
    
    # Analytics/tracking (shows site is monitored)
    if technical.get('has_analytics', False):
        score += 15
        findings.append("Analytics tracking - monitored website")
    else:
        recommendations.append("Add analytics to demonstrate active monitoring")
    
    # Technical SEO basics
    if technical.get('has_sitemap', False):
        score += 10
        findings.append("Sitemap available")
    else:
        recommendations.append("Add XML sitemap")
    
    if technical.get('has_robots_txt', False):
        score += 5
        findings.append("Robots.txt configured")
    
    # Overall digital maturity as authority proxy
    maturity = basic.get('digital_maturity_score', 0)
    if maturity >= 70:
        score += 20
        findings.append("High digital maturity indicates authority")
    elif maturity >= 50:
        score += 10
    
    # Performance (fast sites = better user experience = authority signal)
    page_speed = technical.get('page_speed_score', 0)
    if page_speed >= 70:
        score += 10
        findings.append("Fast page speed - good user experience")
    
    status = "excellent" if score >= 70 else "good" if score >= 50 else "needs_improvement" if score >= 30 else "poor"
    
    return AISearchFactor(
        name="Authority Signals",
        score=min(100, score),
        status=status,
        findings=findings,
        recommendations=recommendations
    )

def _check_conversational_readiness(html: str, soup: BeautifulSoup, content: Dict[str, Any]) -> AISearchFactor:
    """Check readiness for conversational AI queries"""
    score = 0
    findings = []
    recommendations = []
    
    html_lower = html.lower()
    
    # Question-based headers
    question_patterns = [
        r'what is', r'how to', r'why', r'when', r'where', r'who',
        r'mikä on', r'miten', r'miksi', r'milloin', r'missä', r'kuka'
    ]
    
    headers = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    question_headers = []
    for header in headers:
        text = header.get_text().lower()
        if any(re.search(pattern, text) for pattern in question_patterns):
            question_headers.append(header.get_text()[:50])
    
    if len(question_headers) >= 5:
        score += 30
        findings.append(f"Excellent conversational format ({len(question_headers)} question-based headers)")
    elif len(question_headers) >= 2:
        score += 15
        findings.append(f"Some conversational format ({len(question_headers)} Q&A headers)")
    else:
        recommendations.append("Structure content with question-based headings")
    
    # Direct answer format (looking for clear, concise answers)
    sentences = content.get('word_count', 0) // 20  # Rough sentence count
    if sentences >= 50:  # Enough content for good answers
        score += 20
        findings.append("Sufficient content depth for detailed answers")
    
    # Check for bullet points and numbered lists (easy for AI to parse)
    lists = soup.find_all(['ul', 'ol'])
    list_items = sum(len(l.find_all('li')) for l in lists)
    if list_items >= 10:
        score += 20
        findings.append(f"Well-structured lists ({list_items} items) - easy AI parsing")
    elif list_items >= 5:
        score += 10
    else:
        recommendations.append("Add more structured lists for clarity")
    
    # Check for summary/conclusion sections
    summary_indicators = ['summary', 'conclusion', 'key takeaways', 'yhteenveto', 'johtopäätös']
    has_summary = any(indicator in html_lower for indicator in summary_indicators)
    if has_summary:
        score += 15
        findings.append("Summary/conclusion section found")
    else:
        recommendations.append("Add summary section for key takeaways")
    
    # Check readability
    readability = content.get('readability_score', 50)
    if readability >= 70:
        score += 15
        findings.append("Good readability - clear for AI parsing")
    elif readability >= 50:
        score += 8
    else:
        recommendations.append("Improve readability (shorter sentences, clearer language)")
    
    status = "excellent" if score >= 75 else "good" if score >= 55 else "needs_improvement" if score >= 35 else "poor"
    
    return AISearchFactor(
        name="Conversational Readiness",
        score=min(100, score),
        status=status,
        findings=findings,
        recommendations=recommendations
    )

async def analyze_ai_search_visibility(
    url: str,
    html: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    social: Dict[str, Any]
) -> AISearchVisibility:
    """
    Complete AI search visibility analysis
    Nordic First: Systematic analysis of ChatGPT & Perplexity readiness
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Run all factor analyses
    factors = {
        'structured_data': _check_schema_markup(html, soup),
        'semantic_structure': _check_semantic_structure(html, soup),
        'content_depth': _assess_content_comprehensiveness(content, html, soup),
        'authority_signals': _check_authority_markers(technical, basic),
        'conversational_format': _check_conversational_readiness(html, soup, content)
    }
    
    # Calculate overall scores
    factor_scores = [f.score for f in factors.values()]
    overall_score = int(sum(factor_scores) / len(factor_scores))
    
    # ChatGPT readiness (emphasizes content depth + structure)
    chatgpt_score = int(
        factors['content_depth'].score * 0.35 +
        factors['structured_data'].score * 0.25 +
        factors['conversational_format'].score * 0.20 +
        factors['semantic_structure'].score * 0.15 +
        factors['authority_signals'].score * 0.05
    )
    
    # Perplexity readiness (emphasizes authority + freshness)
    perplexity_score = int(
        factors['authority_signals'].score * 0.30 +
        factors['content_depth'].score * 0.25 +
        factors['structured_data'].score * 0.20 +
        factors['semantic_structure'].score * 0.15 +
        factors['conversational_format'].score * 0.10
    )
    
    # Generate key insights
    key_insights = []
    priority_actions = []
    
    # Find weakest factors
    weak_factors = [(name, factor) for name, factor in factors.items() if factor.score < 50]
    strong_factors = [(name, factor) for name, factor in factors.items() if factor.score >= 70]
    
    if strong_factors:
        key_insights.append(f"Strong in: {', '.join(f[1].name for f in strong_factors[:2])}")
    
    if weak_factors:
        key_insights.append(f"Improvement needed: {', '.join(f[1].name for f in weak_factors[:2])}")
        for name, factor in weak_factors[:3]:
            if factor.recommendations:
                priority_actions.extend(factor.recommendations[:2])
    
    # Add specific insights based on scores
    if chatgpt_score < 50:
        key_insights.append("Limited ChatGPT citation likelihood - focus on content depth and Q&A format")
    elif chatgpt_score >= 70:
        key_insights.append("Good ChatGPT readiness - likely to be cited in relevant queries")
    
    if perplexity_score < 50:
        key_insights.append("Weak Perplexity ranking signals - strengthen authority markers")
    elif perplexity_score >= 70:
        key_insights.append("Strong Perplexity positioning - authoritative source signals present")
    
    # Nordic first positioning
    if overall_score >= 70:
        key_insights.append("🌟 Above-average AI search readiness - competitive advantage in Nordics")
    
    return AISearchVisibility(
        chatgpt_readiness_score=chatgpt_score,
        perplexity_readiness_score=perplexity_score,
        overall_ai_search_score=overall_score,
        factors={name: factor.dict() for name, factor in factors.items()},
        key_insights=key_insights[:5],
        priority_actions=priority_actions[:5]
    )
    

# ============================================================================
# COMPLETE AI INSIGHTS AND ENHANCED FEATURES
# ============================================================================

async def generate_ai_insights(
    url: str, 
    basic: Dict[str, Any], 
    technical: Dict[str, Any], 
    content: Dict[str, Any], 
    ux: Dict[str, Any], 
    social: Dict[str, Any],
    html: str,  # ADD THIS PARAMETER
    language: str = 'en'
) -> AIAnalysis:
    """Generate comprehensive AI-powered insights"""
    overall = basic.get('digital_maturity_score', 0)
    spa_detected = basic.get('spa_detected', False)
    modernity_score = basic.get('modernity_score', 0)
    
    insights = generate_english_insights(overall, basic, technical, content, ux, social)
    
    # Enhance with OpenAI if available
    if openai_client:
        try:
            context = f"""
            Website: {url}
            Score: {overall}/100
            Technical: {technical.get('overall_technical_score', 0)}/100
            Content words: {content.get('word_count', 0)}
            Social: {social.get('social_score', 0)}/100
            SPA: {spa_detected}
            Modernity: {modernity_score}/100
            """
            prompt = (
                "Based on this website analysis, provide exactly 5 actionable recommendations. "
                "Each should be one clear sentence covering different areas (technical, content, SEO, UX, social). "
                "Return as a list with hyphens, no introduction:\n" + context
            )
            response = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500, temperature=0.6
            )
            ai_text = response.choices[0].message.content.strip()
            lines = [line.strip() for line in ai_text.splitlines() if line.strip()]
            cleaned = []
            for line in lines:
                clean_line = re.sub(r'^\s*[-•\d]+\s*[.)-]?\s*', '', line).strip()
                if len(clean_line.split()) >= 4:
                    cleaned.append(clean_line)
            if cleaned:
                base = (insights.get('recommendations') or [])[:2]
                insights['recommendations'] = base + cleaned[:5]
        except Exception as e:
            logger.warning(f"OpenAI enhancement failed: {e}")
    
    # --- Humanized layer fusion ---
    # --- Humanized layer fusion ---
    try:
        # Use detailed impact calculation (with optional revenue input support)
        detailed_impact = compute_business_impact_with_input(basic, content, ux, revenue_input=None)
        
        # Convert to simple BusinessImpact for backward compatibility with role summaries
        impact = BusinessImpact(
            lead_gain_estimate=detailed_impact.lead_gain_estimate,
            revenue_uplift_range=detailed_impact.revenue_uplift_range,
            confidence=detailed_impact.confidence,
            customer_trust_effect=detailed_impact.customer_trust_effect
        )
        
        role = build_role_summaries(url, basic, impact, language=language)
        plan = build_plan_90d(basic, content, technical, language=language)  
        risks = build_risk_register(basic, technical, content)
        snippets = build_snippet_examples(url, basic)

        insights.update({
            "business_impact": detailed_impact.dict(),  # Use detailed version in output
            "role_summaries": role.dict(),
            "plan_90d": plan.dict(),
            "risk_register": [r.dict() for r in risks],
            "snippet_examples": snippets.dict()
        })
    except Exception as e:
        logger.warning(f"Humanized layer build failed: {e}")

    # NEW: AI Search Visibility Analysis - SEPARATE try block
    try:
        ai_visibility = await analyze_ai_search_visibility(
            url, html, basic, technical, content, social
        )
        insights["ai_search_visibility"] = ai_visibility
    except Exception as e:
        logger.error(f"AI Search Visibility analysis failed: {e}")
        insights["ai_search_visibility"] = {
            "chatgpt_readiness_score": 0,
            "perplexity_readiness_score": 0,
            "overall_ai_search_score": 0,
            "competitive_advantage": "Analysis unavailable",
            "validation_status": "error",
            "factors": {},
            "key_insights": ["Analysis failed - see logs"],
            "priority_actions": []
        }

    return AIAnalysis(**insights)



def generate_english_insights(overall: int, basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], ux: Dict[str, Any], social: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive English insights"""
    strengths, weaknesses, opportunities, threats, recommendations = [], [], [], [], []
    breakdown = basic.get('score_breakdown', {})
    wc = content.get('word_count', 0)
    
    # Strengths analysis
    if breakdown.get('security', 0) >= 13:
        strengths.append(f"Strong security posture ({breakdown['security']}/15)")
    if breakdown.get('seo_basics', 0) >= 15:
        strengths.append(f"Excellent SEO fundamentals ({breakdown['seo_basics']}/20)")
    if wc > 2000:
        strengths.append(f"Comprehensive content ({wc} words)")
    if social.get('platforms'):
        strengths.append(f"Multi-platform social presence ({len(social['platforms'])} platforms)")
    if basic.get('spa_detected') and basic.get('modernity_score', 0) > 60:
        strengths.append("Modern SPA architecture with good implementation")
    
    # Weaknesses analysis
    if breakdown.get('security', 0) == 0:
        weaknesses.append("CRITICAL: No SSL certificate")
        threats.append("Search engines penalize non-HTTPS sites")
        recommendations.append("Install SSL certificate immediately")
    if breakdown.get('content', 0) < 5:
        weaknesses.append(f"Very low content depth ({wc} words)")
        recommendations.append("Develop comprehensive content strategy")
    if not technical.get('has_analytics'):
        weaknesses.append("No analytics tracking")
        recommendations.append("Install Google Analytics 4")
    if breakdown.get('mobile', 0) < 8:
        weaknesses.append("Poor mobile optimization")
        recommendations.append("Implement responsive design with proper viewport")
    if len(social.get('platforms', [])) < 2:
        weaknesses.append("Limited social media presence")
        recommendations.append("Establish presence on relevant social platforms")
    
    # Opportunities based on score
    if overall < 30:
        opportunities.extend([
            f"Massive upside potential - target {overall + 40} points",
            "Basic fundamentals can yield +20-30 points quickly"
        ])
    elif overall < 50:
        opportunities.extend([
            f"Strong growth potential - target {overall + 30} points",
            "SEO optimization could lift traffic by 50-100%"
        ])
    elif overall < 75:
        opportunities.extend([
            "Optimize for conversion and user experience",
            "Advanced features and automation opportunities"
        ])
    else:
        opportunities.extend([
            "Strong foundation for innovation",
            "AI and automation are next leverage points"
        ])
    
    # SPA-specific opportunities
    if basic.get('spa_detected') and basic.get('modernity_score', 0) < 50:
        opportunities.append("Modernize SPA implementation for better performance")
    
    # Summary generation
    if overall >= 75: 
        summary = f"Excellent digital maturity ({overall}/100) - you are a digital leader."
    elif overall >= 60: 
        summary = f"Good digital presence ({overall}/100) with solid fundamentals."
    elif overall >= 45: 
        summary = f"Baseline achieved ({overall}/100) with improvement opportunities."
    else: 
        summary = f"Early-stage digital maturity ({overall}/100) - immediate action required."
    
    if basic.get('spa_detected'):
        summary += f" Modern SPA architecture {'well-implemented' if basic.get('modernity_score', 0) > 60 else 'needs optimization'}."

    # Action priority
    action_priority = [
        {
            'category': 'security',
            'priority': 'critical' if breakdown.get('security', 0) <= 5 else 'low',
            'score_impact': 15 if breakdown.get('security', 0) <= 5 else 3,
            'description': 'HTTPS and security headers'
        },
        {
            'category': 'content',
            'priority': 'high' if wc < 1000 else 'medium',
            'score_impact': 12 if wc < 1000 else 5,
            'description': 'Content depth and quality'
        },
        {
            'category': 'seo',
            'priority': 'high' if breakdown.get('seo_basics', 0) < 12 else 'medium',
            'score_impact': 8 if breakdown.get('seo_basics', 0) < 12 else 4,
            'description': 'SEO fundamentals and optimization'
        },
        {
            'category': 'mobile',
            'priority': 'medium' if breakdown.get('mobile', 0) < 10 else 'low',
            'score_impact': 8 if breakdown.get('mobile', 0) < 10 else 3,
            'description': 'Mobile experience and responsiveness'
        }
    ]

    return {
        'summary': summary,
        'strengths': strengths[:5],
        'weaknesses': weaknesses[:5],
        'opportunities': opportunities[:4],
        'threats': threats[:3],
        'recommendations': recommendations[:5],
        'confidence_score': min(95, max(60, overall + 20)),
        'sentiment_score': (overall / 100) * 0.8 + 0.2,
        'key_metrics': {
            'digital_maturity': overall,
            'content_words': wc,
            'security_score': breakdown.get('security', 0),
            'seo_score': breakdown.get('seo_basics', 0),
            'mobile_score': breakdown.get('mobile', 0),
            'social_platforms': len(social.get('platforms', [])),
            'spa_detected': basic.get('spa_detected', False),
            'modernity_score': basic.get('modernity_score', 0)
        },
        'action_priority': action_priority
    }

async def generate_enhanced_features(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    social: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate all 10 enhanced features for complete frontend compatibility"""
    try:
        score = int(basic.get("digital_maturity_score", 0))
        breakdown = (basic.get("score_breakdown") or {})
        seo_w = SCORING_CONFIG.weights.get("seo_basics", 20)
        mob_w = SCORING_CONFIG.weights.get("mobile", 15)
        tech_w = SCORING_CONFIG.weights.get("technical", 15)

        seo_pts = int(breakdown.get("seo_basics", 0))
        mob_pts = int(breakdown.get("mobile", 0))
        tech_pts = int(breakdown.get("technical", 0))

        # 1. Industry benchmarking
        percentile = (
            min(100, int((score / 45) * 50))
            if score <= 45 else
            min(100, 50 + int(((score - 45) / 55) * 50))
        )
        industry_benchmarking = {
            "name": "Industry Benchmarking",
            "value": f"{score} / 100",
            "description": "Industry comparison based on configurable scoring",
            "status": "above_average" if score > 45 else "below_average",
            "details": {
                "your_score": score,
                "industry_average": 45,
                "top_quartile": 70,
                "bottom_quartile": 30,
                "percentile": percentile
            }
        }

        # 2. Competitor gaps
        gaps_items = []
        if mob_pts < int(mob_w * 0.7):
            gaps_items.append("Improve mobile UX and page speed")
        if seo_pts < int(seo_w * 0.7):
            gaps_items.append("Enhance internal linking & meta coverage")
        if (social.get("platforms") or []).__len__() < 3:
            gaps_items.append("Increase social proof & UGC")
        if not technical.get("has_analytics"):
            gaps_items.append("Implement comprehensive analytics tracking")
        
        competitor_gaps = {
            "name": "Competitor Gaps",
            "value": "Analysis available",
            "description": "Areas where competitors may have advantages",
            "status": "attention" if gaps_items else "competitive",
            "items": gaps_items or ["Minor gaps vs. peers"]
        }

        # 3. Growth opportunities
        growth_delta = max(10, 90 - score)
        growth_items = [
            "Technical SEO quick wins (schema, canonical hygiene)",
            "Content expansion targeting mid-funnel queries",
            "UX improvements (nav clarity, accessibility fixes)",
            "CRO experiments on top landing pages"
        ]
        
        if basic.get('spa_detected') and basic.get('modernity_score', 0) < 60:
            growth_items.append("Modernize SPA implementation for better SEO")
        
        growth_opportunities = {
            "name": "Growth Opportunities",
            "value": f"+{growth_delta} Points Potential",
            "description": "Strategic growth areas",
            "items": growth_items,
            "potential_score": min(100, score + growth_delta)
        }

        # 4. Risk assessment
        risks = []
        if seo_pts < int(seo_w * 0.5):
            risks.append("Weak SEO fundamentals on key pages")
        if content.get("content_quality_score", 0) < 50:
            risks.append("Thin or shallow content on key pages")
        if technical.get("page_speed_score", 0) < 70:
            risks.append("Performance regressions on mobile (LCP > 2.5s)")
        if breakdown.get("social", 0) < 5:
            risks.append("Low social presence (limited platforms/OG tags)")
        if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
            risks.append("SPA not properly rendered for search engines")
        
        risk_assessment = {
            "name": "Risk Assessment",
            "value": "Risks evaluated",
            "description": "Key risks to monitor",
            "items": risks or ["No material risks detected"],
            "risk_level": "High" if len(risks) > 3 else "Medium" if risks else "Low"
        }

        # 5. Market trends
        trends = [
            "EEAT & first-party data importance growing",
            "Core Web Vitals and page experience remain ranking signals",
            "Short-form video and UGC drive discovery"
        ]
        
        if basic.get('spa_detected'):
            trends.append("SPAs require careful SEO implementation for visibility")
        
        market_trends = {
            "name": "Market Trends",
            "value": "Trends analyzed",
            "description": "Relevant market trends",
            "items": trends,
            "trends": trends,  # Backend compatibility
            "status": "modern" if score >= 55 else "developing"
        }

        # 6. Estimated traffic rank
        traffic_category = (
            "High Traffic" if score >= 70 else
            "Medium Traffic" if score >= 45 else
            "Low Traffic"
        )
        estimated_traffic_rank = {
            "name": "Traffic Estimate",
            "value": "Estimate available",
            "description": "Traffic estimation based on digital maturity",
            "category": traffic_category,
            "confidence": "Medium",
            "factors": ["Content depth", "SEO basics", "Mobile performance"]
        }

        # 7. Mobile-first readiness
        mobile_ready = mob_pts >= int(mob_w * 0.6)
        mobile_first_index_ready = {
            "name": "Mobile-First Readiness",
            "value": "Yes" if mobile_ready else "No",
            "description": "Google Mobile-First indexing readiness",
            "status": "ready" if mobile_ready else "not_ready",
            "mobile_score": int((mob_pts / mob_w) * 100) if mob_pts > 0 else 0,
            "issues": [] if mobile_ready else ["Viewport / responsiveness improvements required"],
            "recommendations": ([] if mobile_ready else [
                "Add viewport meta",
                "Increase responsive coverage (media queries)",
                "Optimize mobile LCP elements"
            ])
        }

        # 8. Core Web Vitals
        ps = int(technical.get("page_speed_score", 0))
        passed = ps >= 70
        cwv_status = "pass" if passed else "needs_improvement"
        cwv_grade = ("A" if ps >= 90 else "B" if ps >= 80 else 
                    "C" if ps >= 70 else "D" if ps >= 60 else "E")

        # Laske todelliset arvot page_speed_score:n perusteella
        # LCP (Largest Contentful Paint): 0-5000ms
        # Hyvä < 2500ms, Kohtalainen 2500-4000ms, Huono > 4000ms
        lcp_ms = int(5000 - (ps * 27.5))  # 100 → 2250ms, 0 → 5000ms
        lcp_ms = max(1500, min(5500, lcp_ms))

        # TBT (Total Blocking Time): 0-600ms  
        # Hyvä < 200ms, Kohtalainen 200-600ms, Huono > 600ms
        tbt_ms = int(600 - (ps * 5))  # 100 → 100ms, 0 → 600ms
        tbt_ms = max(50, min(700, tbt_ms))

        # CLS (Cumulative Layout Shift): 0-0.5
        # Hyvä < 0.1, Kohtalainen 0.1-0.25, Huono > 0.25
        cls = round((0.5 - (ps * 0.0045)), 2)  # 100 → 0.05, 0 → 0.5
        cls = max(0.01, min(0.6, cls))

        core_web_vitals_assessment = {
            "name": "Core Web Vitals",
            "value": "Pass" if passed else "Needs improvement",
            "description": "Website performance metrics",
            "status": cwv_status,
            "score": ps,
            "grade": cwv_grade,
            "metrics": {
                "lcp_ms": lcp_ms,
                "tbt_ms": tbt_ms,
                "cls": cls
            },
            "recommendations": [
                "Optimize hero images (modern formats, compression)" if lcp_ms > 2500 else None,
                "Defer non-critical JS and enable lazy-loading" if tbt_ms > 200 else None,
                "Fix layout shifts - reserve space for images/ads" if cls > 0.1 else None,
                "Minify CSS/JS and leverage HTTP caching"
            ]
        }

        
        # 9. Technology stack
        detected = ["HTML5", "CSS3", "JavaScript"]
        modern_features = basic.get('detailed_findings', {}).get('modern_features', {})
        spa_frameworks = modern_features.get('features', {}).get('spa_framework', [])
        
        framework_map = {
            'react': 'React', 'nextjs': 'Next.js', 'vue': 'Vue.js',
            'angular': 'Angular', 'svelte': 'Svelte', 'nuxt': 'Nuxt.js'
        }
        
        frameworks_detected = []
        for fw in spa_frameworks:
            fw_normalized = framework_map.get(str(fw).strip().lower(), str(fw))
            if fw_normalized not in detected:
                detected.append(fw_normalized)
                frameworks_detected.append(fw_normalized)
        
        media_technologies = []
        for media in (content.get("media_types") or []):
            if media and media.lower() not in ['images', 'image']:
                if media not in detected:
                    detected.append(media)
                    media_technologies.append(media)
        
        analytics_tools = []
        if technical.get("has_analytics"):
            if "Google Analytics" not in detected:
                detected.append("Google Analytics")
                analytics_tools.append("Google Analytics")
        
        technology_stack = {
            "name": "Technology Stack",
            "value": f"{len(detected)} technologies detected",
            "description": "Website technology stack analysis with SPA detection",
            "detected": detected,
            "categories": {
                "frontend": ["HTML5", "CSS3", "JavaScript"] + frameworks_detected,
                "media": media_technologies,
                "analytics": analytics_tools
            },
            "modernity": "modern" if basic.get('modernity_score', 0) > 60 else "standard"
        }

        
        

        # PALAUTA KAIKKI 10 ENHANCED FEATURES
        return {
            "industry_benchmarking": industry_benchmarking,
            "competitor_gaps": competitor_gaps,
            "growth_opportunities": growth_opportunities,
            "risk_assessment": risk_assessment,
            "market_trends": market_trends,
            "estimated_traffic_rank": estimated_traffic_rank,
            "mobile_first_index_ready": mobile_first_index_ready,
            "core_web_vitals_assessment": core_web_vitals_assessment,
            "technology_stack": technology_stack,
            
        }

    except Exception as e:
        logger.error(f"Enhanced features generation failed: {e}")
        return {
            "industry_benchmarking": {"name": "Industry Benchmarking", "value": "N/A"},
            "competitor_gaps": {"name": "Competitor Gaps", "value": "N/A"},
            "growth_opportunities": {"name": "Growth Opportunities", "value": "N/A"},
            "risk_assessment": {"name": "Risk Assessment", "value": "N/A"},
            "market_trends": {"name": "Market Trends", "value": "N/A"},
            "estimated_traffic_rank": {"name": "Traffic Estimate", "value": "N/A"},
            "mobile_first_index_ready": {"name": "Mobile-First Readiness", "value": "N/A"},
            "core_web_vitals_assessment": {"name": "Core Web Vitals", "value": "N/A"},
            "technology_stack": {"name": "Technology Stack", "value": "N/A", "detected": []},
            "ai_search_visibility": {"name": "AI Search Visibility", "value": "N/A"}  # ← LISÄTTY
        }

def generate_smart_actions(ai_analysis: AIAnalysis, technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    breakdown = basic.get('score_breakdown', {})

    # --- existing rules, kept but concise ---
    if breakdown.get('security', 0) <= 5:
        actions.append({
            "title": "Enable HTTPS and security headers",
            "description": "Install SSL certificate and configure CSP, X-Frame-Options, HSTS.",
            "priority": "critical", "effort": "medium", "impact": "critical",
            "estimated_score_increase": 12, "category": "security", "estimated_time": "1-3 days"
        })

    if breakdown.get('content', 0) <= 8:
        actions.append({
            "title": "Develop comprehensive content",
            "description": "Create in-depth pillar content (2000+ words) targeting core topics.",
            "priority": "critical", "effort": "high", "impact": "critical",
            "estimated_score_increase": 15, "category": "content", "estimated_time": "2-4 weeks"
        })

    if breakdown.get('seo_basics', 0) < 12:
        actions.append({
            "title": "Optimize SEO fundamentals",
            "description": "Improve titles, meta descriptions, H1/H2 structure, canonical tags.",
            "priority": "high", "effort": "medium", "impact": "high",
            "estimated_score_increase": 10, "category": "seo", "estimated_time": "1-2 weeks"
        })

    if breakdown.get('mobile', 0) < 10:
        actions.append({
            "title": "Implement responsive design",
            "description": "Add viewport meta + CSS media queries; test on key devices.",
            "priority": "high", "effort": "medium", "impact": "high",
            "estimated_score_increase": 8, "category": "mobile", "estimated_time": "1-2 weeks"
        })

    if not technical.get('has_analytics', False):
        actions.append({
            "title": "Install Google Analytics 4",
            "description": "Set up GA4 + conversion events; verify data layer.",
            "priority": "high", "effort": "low", "impact": "medium",
            "estimated_score_increase": 5, "category": "analytics", "estimated_time": "1-2 days"
        })

    if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
        actions.append({
            "title": "Implement SPA SEO optimization",
            "description": "Add server-side rendering or prerendering for search engines.",
            "priority": "high", "effort": "high", "impact": "high",
            "estimated_score_increase": 12, "category": "spa", "estimated_time": "2-3 weeks"
        })

    if breakdown.get('social', 0) < 6:
        actions.append({
            "title": "Build social media presence",
            "description": "Create/refresh profiles and add sharing buttons site-wide.",
            "priority": "medium", "effort": "medium", "impact": "medium",
            "estimated_score_increase": 6, "category": "social", "estimated_time": "1-2 weeks"
        })

    if breakdown.get('performance', 0) < 3:
        actions.append({
            "title": "Optimize website performance",
            "description": "Compress images, minify CSS/JS, implement lazy-loading.",
            "priority": "medium", "effort": "medium", "impact": "medium",
            "estimated_score_increase": 4, "category": "performance", "estimated_time": "3-5 days"
        })

    if breakdown.get('technical', 0) < 10:
        actions.append({
            "title": "Improve technical SEO",
            "description": "Add sitemap.xml, robots.txt, and key schema markup.",
            "priority": "low", "effort": "low", "impact": "medium",
            "estimated_score_increase": 3, "category": "technical", "estimated_time": "2-3 days"
        })

    if not actions:
        actions.append({
            "title": "Content optimization",
            "description": "Update existing pages for UX & engagement; add internal links.",
            "priority": "low", "effort": "medium", "impact": "low",
            "estimated_score_increase": 2, "category": "content", "estimated_time": "1 week"
        })

    # --- enrichment: So what / Why now / What to do + RICE + signals ---
    def _confidence_label(val: int) -> str:
        return "H" if val >= 75 else "M" if val >= 50 else "L"

    def enrich(a: Dict[str, Any]) -> Dict[str, Any]:
        cat = a.get("category","")
        so_what = {
            "security": "Protects users and prevents SEO/trust penalties.",
            "content": "Drives qualified traffic and improves conversion.",
            "seo": "Improves discoverability and click-through.",
            "mobile": "Mobile users get faster UX → better CR.",
            "analytics": "Enables learning loops and ROI tracking.",
            "spa": "Ensures bots can index content → visibility.",
            "social": "Adds social proof and new discovery channels.",
            "performance": "Faster pages reduce bounce and lift revenue.",
            "technical": "Prevents crawl/canonicalization issues."
        }.get(cat, "Improves user outcomes and revenue.")

        why_now = {
            "security": "HTTP/weak headers can hurt rankings and flags in browsers.",
            "content": "Competitors publish weekly; gap widens every month.",
            "seo": "Meta & structure are fast compounding wins.",
            "mobile": "Core Web Vitals remain a ranking/UX signal.",
            "analytics": "Every day without data is lost learning.",
            "spa": "Client-only rendering risks invisibility in search.",
            "social": "UGC/short-form channels compound reach now."
        }.get(cat, "Opportunity cost grows each week.")

        what_to_do = {
            "security": "Issue TLS cert; enable HSTS; add CSP & X-Frame-Options.",
            "content": "Ship 6 pillar pages + clusters; FAQs; internal links.",
            "seo": "Fix top 10 titles/meta; add canonicals; H1/H2 structure.",
            "mobile": "Add viewport; fix CLS; compress hero images.",
            "analytics": "Install GA4; define 3–5 conversion events; verify.",
            "spa": "Add SSR/prerender for critical routes or static export.",
            "social": "Add OG/Twitter tags; sitewide share; refresh profiles.",
            "performance": "Defer non-critical JS; preload critical; lazy-load.",
            "technical": "Publish sitemap.xml/robots.txt; add schema markup."
        }.get(cat, "Ship the smallest change that moves the metric.")

        # RICE (karkea) + owner/ETA
        reach = max(50, int(basic.get('digital_maturity_score',0)/2) + content.get('content_quality_score',0)//2)
        conf = min(10, max(3, basic.get('digital_maturity_score',0)//12))
        eff_map = {"low": 1, "medium": 2, "high": 3}
        effort_n = eff_map.get(a.get("effort","medium"), 2)
        impact_w = {"low":2,"medium":3,"high":4,"critical":5}.get(a.get("impact","medium"),3)
        rice = int((reach * impact_w * conf) / max(1, effort_n))

        sig: List[str] = []
        if cat == "mobile":
            if not basic.get('has_mobile_viewport'): sig.append("No viewport meta")
            if technical.get('page_speed_score', 100) < 70: sig.append("Low page speed score")
        if cat == "seo":
            if not basic.get('meta_description'): sig.append("Missing/short meta description")
            if not basic.get('title'): sig.append("Missing/short <title>")
        if cat == "spa" and basic.get('rendering_method') == 'http':
            sig.append("SPA client-rendered only")

        a.update({
            "so_what": so_what,
            "why_now": why_now,
            "what_to_do": what_to_do,
            "owner": "CMO" if cat in ["seo","content","social","performance"] else "CTO",
            "eta_days": 5 if a.get("effort")=="low" else 10 if a.get("effort")=="medium" else 20,
            "reach": reach,
            "confidence": conf,
            "rice_score": rice,
            "signals": sig or None,
            "evidence_confidence": _confidence_label(basic.get('digital_maturity_score',0))
        })
        return a

    actions = [enrich(a) for a in actions]

    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    actions.sort(key=lambda x: (priority_order.get(x['priority'], 4), -x.get('rice_score', 0), -x.get('estimated_score_increase', 0)))
    return actions[:8]

# ============================================================================
# MAIN ENDPOINTS
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    logger.info(f"🔐 LOGIN ATTEMPT: username={request.username}")
    
    # ✅ PARANNETTU HAKU: Etsi sekä email:lla ETTÄ username-kentällä
    user = None
    user_key = None
    
    # 1. Yritä suoraa email-hakua
    if request.username in USERS_DB:
        user = USERS_DB[request.username]
        user_key = request.username
        logger.info(f"✅ Found user by email key: {user_key}")
    
    # 2. Etsi username-kentällä
    if not user:
        for email, user_data in USERS_DB.items():
            if user_data.get("username") == request.username:
                user = user_data
                user_key = email
                logger.info(f"✅ Found user by username field: {request.username} (email: {email})")
                break
    
    # 3. Yritä myös email-kentällä (jos käyttäjä syötti emailin)
    if not user:
        for email, user_data in USERS_DB.items():
            if user_data.get("email") == request.username:
                user = user_data
                user_key = email
                logger.info(f"✅ Found user by email field: {request.username}")
                break
    
    if not user:
        logger.warning(f"❌ USER NOT FOUND: {request.username}")
        logger.info(f"📋 Available users:")
        for key, val in USERS_DB.items():
            logger.info(f"  - Key: {key}, Username: {val.get('username')}, Email: {val.get('email')}")
        raise HTTPException(401, "Invalid credentials")
    
    # ✅ VERIFY PASSWORD
    logger.info(f"🔐 Verifying password for: {user.get('username')} (key: {user_key})")
    
    if not verify_password(request.password, user["hashed_password"]):
        logger.error(f"❌ INVALID PASSWORD for: {request.username}")
        raise HTTPException(401, "Invalid credentials")
    
    logger.info(f"✅ LOGIN SUCCESS: {user.get('username')}, role={user['role']}")
    
    # ✅ Store user in user_store for email verification
    user_store[user_key] = {
        "username": user.get('username'),
        "email": user.get('email'),
        "role": user['role'],
        "verified": True  # Users from USERS_DB are already verified
    }
    
    # ✅ CREATE TOKEN (käytä user_key:tä joka on email)
    access_token = create_access_token(
        data={"sub": user_key, "role": user["role"]}
    )
    
    return TokenResponse(access_token=access_token, role=user["role"])

@app.get("/auth/me")
async def get_current_user_info(user: UserInfo = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "authenticated": True
    }

# ============================================================================
# MAGIC LINK ENDPOINTS
# ============================================================================

@app.post("/auth/magic-link/request")
async def request_magic_link(
    request: MagicLinkRequest,  # ✅ Muutettu
    background_tasks: BackgroundTasks,
    req: Request
):
    """Request a magic link via email"""
    if not magic_link_auth:
        raise HTTPException(503, "Magic Link authentication not available")
    
    try:
        result = await magic_link_auth.send_magic_link(
            email=request.email,
            request=req,
            background_tasks=background_tasks,
            redirect_url=request.redirect_url
        )
        
        logger.info(f"Magic link requested for {request.email}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Magic link request failed: {e}")
        raise HTTPException(500, "Failed to process magic link request")



@app.get("/auth/magic-link/verify")
async def verify_magic_link_get(token: str, req: Request):
    """Verify magic link and return access token"""
    try:
        if not magic_link_auth:
            raise HTTPException(503, "Magic link authentication not available")
        
        result = await magic_link_auth.verify_magic_link(
            token=token,
            request=req
        )
        
        if not result or not result.get('valid'):
            raise HTTPException(400, "Invalid or expired token")
        
        # Get user data from result
        user_data = result.get('user', {})
        email = user_data.get('email')
        role = user_data.get('role', 'user')
        username = user_data.get('username')
        
        if not email:
            raise HTTPException(400, "Invalid magic link response")
        
        # 🔍 HELPER: Find existing user by email in USERS_DB (keys are usernames, not emails)
        existing_user = None
        existing_username = None
        for uname, udata in USERS_DB.items():
            if udata.get("email") == email:
                existing_user = udata
                existing_username = uname
                logger.info(f"🔍 Found existing user by email: {uname} with role: {udata.get('role')}")
                break
        
        # If user exists in USERS_DB (created by admin), use their role
        if existing_user:
            role = existing_user.get("role", "user")
            username = existing_username
            logger.info(f"✅ Using existing user's role: {role} for {email}")
        
        # ✅ CRITICAL FIX: Add user to user_store AND USERS_DB
        if email not in user_store:
            user_store[email] = {
                "username": username or email.split('@')[0],
                "email": email,
                "password_hash": "",
                "role": role,
                "quota": 10,
                "used": 0,
                "created_at": datetime.now().isoformat()
            }
            logger.info(f"✅ Added magic link user to user_store: {email} with role: {role}")
        else:
            logger.info(f"ℹ️ Magic link user already exists in user_store: {email}")
        
        # ✅ CRITICAL: Also add to USERS_DB for JWT validation
        if email not in USERS_DB:
            # Only create new user if email is not found (we already checked by email above)
            if not existing_user:
                USERS_DB[email] = {
                    "username": username or email.split('@')[0],
                    "email": email,
                    "hashed_password": "",  # No password for magic link users
                    "role": role,
                    "search_limit": 10  # Default limit for magic link users
                }
                logger.info(f"✅ Added NEW magic link user to USERS_DB: {email} with role: {role}")
            else:
                logger.info(f"ℹ️ User already exists in USERS_DB under username: {existing_username}")
        else:
            logger.info(f"ℹ️ Magic link user already exists in USERS_DB: {email}")
        
        # Create access token
        access_token = create_access_token({
            "sub": email,
            "role": role
        })
        
        logger.info(f"✅ Magic link login successful for {email} with role: {role}")
        
        return {
            "success": True,
            "access_token": access_token,
            "user": {
                "email": email,
                "username": username or email.split('@')[0],
                "role": role
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Magic link verification failed: {e}")
        raise HTTPException(500, f"Verification failed: {str(e)}")

       
# ============================================================================
# GOOGLE OAUTH ENDPOINTS - FIXED VERSION
# ============================================================================

@app.get("/auth/google/login")
async def google_login(request: Request):
    """Initiate Google OAuth login"""
    if not os.getenv('GOOGLE_CLIENT_ID'):
        raise HTTPException(503, "Google OAuth not configured")
    
    # Hardcode HTTPS redirect URI for production
    redirect_uri = "https://fastapi-production-51f9.up.railway.app/auth/google/callback"
    logger.info(f"🔐 Initiating Google OAuth login, redirect_uri: {redirect_uri}")
    
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request, background_tasks: BackgroundTasks):
    """Handle Google OAuth callback"""
    try:
        if not os.getenv('GOOGLE_CLIENT_ID'):
            raise HTTPException(503, "Google OAuth not configured")
        
        # Get access token from Google
        token = await oauth.google.authorize_access_token(request)
        
        # Get user info
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(400, "Failed to get user info from Google")
        
        email = user_info.get('email')
        name = user_info.get('name', '')
        picture = user_info.get('picture', '')
        google_id = user_info.get('sub', '')
        
        logger.info(f"✅ Google OAuth callback successful for: {email}")
        
        if not email:
            raise HTTPException(400, "Email not provided by Google")
        
        # ✅ FIX: Check DATABASE FIRST for existing user and role
        existing_user = None
        existing_username = None
        is_new_user = True
        role = "user"  # Default
        username = email.split('@')[0]
        
        # Check database first
        try:
            from database import get_user_from_db, DATABASE_ENABLED
            
            if DATABASE_ENABLED:
                db_user = get_user_from_db(username)
                if db_user:
                    existing_user = db_user
                    existing_username = db_user['username']
                    role = db_user.get('role', 'user')  # ✅ Use DB role!
                    is_new_user = False
                    logger.info(f"📋 Found user in DB: {username} with role: {role}")
        except ImportError:
            logger.warning("⚠️ Database module not available")
        except Exception as db_error:
            logger.warning(f"⚠️ Database lookup error: {db_error}")
        
        # If not in DB, check memory (USERS_DB)
        if not existing_user:
            for uname, udata in USERS_DB.items():
                if udata.get("email") == email:
                    existing_user = udata
                    existing_username = uname
                    role = udata.get("role", "user")
                    is_new_user = False
                    logger.info(f"📋 Found user in memory: {username} with role: {role}")
                    break
        
        # Add to user_store
        if email not in user_store:
            user_store[email] = {
                "username": username,
                "email": email,
                "password_hash": "",
                "role": role,
                "quota": 10,
                "used": 0,
                "created_at": datetime.now().isoformat(),
                "google_id": google_id,
                "name": name,
                "picture": picture
            }
            logger.info(f"✅ Added Google OAuth user to user_store: {email}")
        
        # Add to USERS_DB if needed
        if not existing_user:
            # ✅ ULTIMATE FIX: Create a short, deterministic password
            import hashlib
            
            # Use first 16 chars of SHA256 hash - guaranteed to be short and safe
            password_hash_base = hashlib.sha256(google_id.encode()).hexdigest()[:16]
            safe_password = f"g_{password_hash_base}"  # Total: 18 chars (way under 72!)
            
            logger.info(f"🔐 Creating OAuth password (length: {len(safe_password)} chars)")
            
            # ✅ USE THE EXISTING pwd_context - DON'T CREATE A NEW ONE!
            # The pwd_context is already defined at the top of main.py
            try:
                # Ensure it's a string (not bytes)
                if not isinstance(safe_password, str):
                    safe_password = safe_password.decode('utf-8')
                
                # Hash using the EXISTING pwd_context
                hashed_password = pwd_context.hash(safe_password)
                logger.info(f"✅ Password hashed successfully")
                
            except Exception as hash_error:
                logger.error(f"❌ Password hashing failed: {hash_error}")
                # Ultra-simple fallback
                try:
                    simple_password = "oauth123"
                    hashed_password = pwd_context.hash(simple_password)
                    logger.warning(f"⚠️ Used ultra-simple fallback password")
                except Exception as fallback_error:
                    logger.error(f"❌ Even fallback failed: {fallback_error}")
                    raise HTTPException(500, "Failed to create user password hash")
            
            USERS_DB[username] = {
                "username": username,
                "email": email,
                "hashed_password": hashed_password,
                "role": role,
                "search_limit": 10
            }
            logger.info(f"✅ Added Google OAuth user to USERS_DB: {username}")
            
            # ✅ PERSIST TO DATABASE
            try:
                # Import database function if available
                try:
                    from database import create_user_in_db, DATABASE_ENABLED
                    
                    if DATABASE_ENABLED:
                        success = create_user_in_db(
                            username=username,
                            hashed_password=hashed_password,
                            role=role,
                            search_limit=10,
                            email=email
                        )
                        if success:
                            logger.info(f"✅ Persisted Google OAuth user to database: {username}")
                        else:
                            logger.warning(f"⚠️ Failed to persist to database: {username}")
                    else:
                        logger.info("ℹ️ Database not enabled, user stored in memory only")
                        
                except ImportError:
                    logger.warning("⚠️ Database module not available, user stored in memory only")
                    
            except Exception as db_error:
                logger.error(f"⚠️ Database error: {db_error}")
                # Continue anyway - user is in memory
            
            # ✅ NEW: Send email notification for new user
            logger.info(f"📧 New Google OAuth user detected, sending notification for: {email}")
            background_tasks.add_task(
                on_user_registered,
                user_email=email,
                user_name=name,
                method="google"
            )

        
        # Create JWT access token for our API
        access_token = create_access_token({
            "sub": username,
            "role": role  # ✅ Now uses DB role!
        })
        
        logger.info(f"✅ Google OAuth login successful for {email} with role: {role}")
        
        # ✅ REDIRECT DIRECTLY TO DASHBOARD WITH HASH PARAMETERS
        # Add timestamp to URL to bust One.com cache!
        import time
        timestamp = int(time.time())
        
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
        redirect_url = (
            f"{frontend_url}/dashboard?t={timestamp}"
            f"#token={access_token}"
            f"&email={email}"
            f"&username={username}"
            f"&role={role}"
        )
        
        logger.info(f"🎯 Redirecting to dashboard with token hash: {redirect_url[:80]}...")
        
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Google OAuth callback failed: {e}")
        import traceback
        logger.error(f"📋 Traceback: {traceback.format_exc()}")
        # Redirect to frontend with error
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
        return RedirectResponse(url=f"{frontend_url}/login?error=google_auth_failed")
# ============================================================================
# REVENUE INPUT ENDPOINTS
# ============================================================================

@app.post("/api/v1/calculate-impact")
async def calculate_revenue_impact(request: RevenueCalculationRequest):
    """
    Standalone calculator for revenue impact estimation
    
    Example usage:
    POST /api/v1/calculate-impact
    {
        "revenue_input": {
            "annual_revenue": 750000
        },
        "digital_score": 38
    }
    
    Returns detailed revenue impact projections without full website analysis
    """
    
    revenue_input = request.revenue_input
    digital_score = request.digital_score
    
    # Create minimal analysis objects for calculation
    basic = {
        'digital_maturity_score': digital_score,
        'score_breakdown': {
            'seo_basics': int(digital_score * 0.2),
            'mobile': int(digital_score * 0.15)
        },
        'modernity_score': digital_score
    }
    
    content = {'content_quality_score': digital_score}
    ux = {'overall_ux_score': digital_score}
    
    impact = compute_business_impact_with_input(basic, content, ux, revenue_input)
    
    return {
        "success": True,
        "business_impact": impact.dict(),
        "recommendations": [
            f"Focus on {area}" for area in impact.improvement_areas[:3]
        ],
        "next_steps": [
            "Run full website analysis for detailed action plan",
            "Review scenario planning for implementation roadmap",
            "Track metrics monthly to validate improvements"
        ],
        "calculation_note": f"Based on {impact.calculation_basis} revenue data"
    }

# ============================================================================
# ANALYSIS CORE - INTERNAL HELPER (MOVED HERE - MUST BE BEFORE DISCOVERY)
# ============================================================================

async def _perform_comprehensive_analysis_internal(
    url: str,
    company_name: Optional[str] = None,
    language: str = "en",
    force_playwright: bool = False,
    user: Optional[UserInfo] = None,
    revenue_input: Optional[RevenueInputRequest] = None
) -> Dict[str, Any]:
    """
    Internal analysis core - NO QUOTA CHECK.
    Used by both public API and background tasks.
    
    Args:
        url: Cleaned URL to analyze
        company_name: Optional company name
        language: Language code (en/fi)
        force_playwright: Force SPA rendering
        user: Optional user info for metadata
    
    Returns:
        Complete analysis result dict
    
    Raises:
        HTTPException: For invalid URLs, SSRF, or insufficient content
        Exception: For internal errors
    """
    
    # URL validation (SSRF check already done by caller)
    url = clean_url(url)
    
    # Check cache
    cache_key = get_cache_key(url, "ai_comprehensive_v6.1.1_complete")
    cached_result = await get_from_cache(cache_key)
    if cached_result:
        logger.info(f"Cache hit for {url}")
        return cached_result
    
    logger.info(f"Starting analysis for {url}")
    
    # Fetch website content with smart rendering
    html_content, used_spa = await get_website_content(
        url, 
        force_spa=force_playwright
    )
    
    if not html_content or len(html_content.strip()) < 100:
        raise HTTPException(400, "Website returned insufficient content")
    
    rendering_info = {
        'spa_detected': bool(used_spa),
        'spa_info': {'spa_detected': bool(used_spa)},
        'rendering_method': 'playwright' if used_spa else 'http',
        'final_url': url
    }
    
    # Perform all analyses
    basic_analysis = await analyze_basic_metrics_enhanced(
        url, html_content,
        headers=httpx.Headers({}),
        rendering_info=rendering_info
    )
    
    technical_audit = await analyze_technical_aspects(
        url, html_content, 
        headers=httpx.Headers({})
    )
    
    # ✅ KORJAUS 1: Käytä `basic_analysis` eikä `result`
    if 'modern_features' in basic_analysis.get('detailed_findings', {}):
        modern_features = basic_analysis['detailed_findings']['modern_features']
        logger.info(f"✅ Found modern_features: {len(modern_features.get('detected_frameworks', []))} frameworks")
        
        technical_audit['technology_description'] = modern_features.get('technology_description', 'No data')
        technical_audit['detected_frameworks'] = modern_features.get('detected_frameworks', [])
        technical_audit['modern_js_features'] = modern_features.get('modern_js_features', 0)
        
        logger.info(f"✅ Enriched technical_audit with: {technical_audit['detected_frameworks']}")
    else:
        # ✅ KORJAUS 2: Oikea sisennys
        logger.warning(
            f"⚠️ modern_features NOT FOUND in detailed_findings! "
            f"Available keys: {list(basic_analysis.get('detailed_findings', {}).keys())}"
        )
        # Fallback values
        technical_audit['technology_description'] = 'Analysis pending'
        technical_audit['detected_frameworks'] = []
        technical_audit['modern_js_features'] = 0
    
    # ✅ KORJAUS 3: Siirrä analyysit oikeaan paikkaan (ei `else`-blokin sisään!)
    content_analysis = await analyze_content_quality(html_content)
    ux_analysis = await analyze_ux_elements(html_content)
    social_analysis = await analyze_social_media_presence(url, html_content)
    competitive_analysis = await analyze_competitive_positioning(url, basic_analysis)
    
    # Score breakdown with aliases
    sb_with_aliases = create_score_breakdown_with_aliases(
        basic_analysis.get('score_breakdown', {})
    )
    
    # AI insights
    ai_analysis = await generate_ai_insights(
        url, basic_analysis, technical_audit, content_analysis, 
        ux_analysis, social_analysis, html_content, language=language
    )
    
    # Enhanced features
    enhanced_features = await generate_enhanced_features(
        url, basic_analysis, technical_audit, content_analysis, social_analysis
    )
    enhanced_features["admin_features_enabled"] = (user.role == "admin" if user else False)
    
    # AI Search Visibility
    if hasattr(ai_analysis, 'ai_search_visibility') and ai_analysis.ai_search_visibility:
        ai_vis_dict = (ai_analysis.ai_search_visibility.dict() 
                      if hasattr(ai_analysis.ai_search_visibility, 'dict') 
                      else ai_analysis.ai_search_visibility)
        enhanced_features["ai_search_visibility"] = ai_vis_dict
    
    # Smart actions
    smart_actions = generate_smart_actions(
        ai_analysis, technical_audit, content_analysis, basic_analysis
    )
    
    # Construct result
    result = {
        "success": True,
        "company_name": company_name or get_domain_from_url(url),
        "analysis_date": datetime.now().isoformat(),
        "basic_analysis": {
            "company": company_name or get_domain_from_url(url),
            "website": url,
            "digital_maturity_score": basic_analysis['digital_maturity_score'],
            "social_platforms": basic_analysis.get('social_platforms', 0),
            "technical_score": technical_audit.get('overall_technical_score', 0),
            "content_score": content_analysis.get('content_quality_score', 0),
            "seo_score": int((basic_analysis.get('score_breakdown', {}).get('seo_basics', 0) 
                             / SCORING_CONFIG.weights['seo_basics']) * 100),
            "score_breakdown": sb_with_aliases,
            "analysis_timestamp": datetime.now().isoformat(),
            "spa_detected": basic_analysis.get('spa_detected', False),
            "rendering_method": basic_analysis.get('rendering_method', 'http'),
            "modernity_score": basic_analysis.get('modernity_score', 0)
        },
        "ai_analysis": ai_analysis.dict(),
        "detailed_analysis": {
            "social_media": social_analysis,
            "technical_audit": technical_audit,
            "content_analysis": content_analysis,
            "ux_analysis": ux_analysis,
            "competitive_analysis": competitive_analysis,
        },
        "smart": {
            "actions": smart_actions,
            "scores": {
                "overall": basic_analysis['digital_maturity_score'],
                "technical": technical_audit.get('overall_technical_score', 0),
                "content": content_analysis.get('content_quality_score', 0),
                "social": social_analysis.get('social_score', 0),
                "ux": ux_analysis.get('overall_ux_score', 0),
                "competitive": competitive_analysis.get('competitive_score', 0),
                "trend": "stable",
                "percentile": enhanced_features['industry_benchmarking']['details'].get('percentile', 50)
            }
        },
        "enhanced_features": enhanced_features,
        "metadata": {
            "version": APP_VERSION,
            "scoring_version": "configurable_v1_complete",
            "analysis_depth": "comprehensive_spa_aware_complete",
            "confidence_level": ai_analysis.confidence_score,
            "analyzed_by": user.username if user else "system",
            "user_role": user.role if user else "system",
            "rendering_method": rendering_info['rendering_method'],
            "spa_detected": rendering_info['spa_detected'],
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "scoring_weights": SCORING_CONFIG.weights,
            "content_words": content_analysis.get('word_count', 0),
            "modernity_score": basic_analysis.get('modernity_score', 0)
        }
    }
    
    # Ensure integer scores
    result = ensure_integer_scores(result)
    
    # Cache result
    await set_cache(cache_key, result)
    
    logger.info(
        f"Analysis complete: {url} - "
        f"Score: {basic_analysis['digital_maturity_score']}, "
        f"SPA: {rendering_info['spa_detected']}, "
        f"Method: {rendering_info['rendering_method']}"
    )
    
    return result

# ============================================================================
# COMPETITOR DISCOVERY ENDPOINTS - PRODUCTION READY v2.0
# ============================================================================

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# Default blacklist - can be overridden by user preferences in database
DEFAULT_BLACKLIST_DOMAINS = [
    "facebook.com", "linkedin.com", "youtube.com", "wikipedia.org",
    "google.com", "instagram.com", "twitter.com", "tiktok.com",
    "reddit.com", "pinterest.com", "quora.com",
    "tori.fi", "yle.fi", "hs.fi", "is.fi", "iltalehti.fi",
    "kauppalehti.fi", "tivi.fi", "suomi24.fi", "mtv.fi"
]

# Search provider configuration
SEARCH_PROVIDERS = {
    "google": {"enabled": True, "priority": 1, "weight": 0.7},
    "bing": {"enabled": False, "priority": 2, "weight": 0.3},  # Fallback if enabled
}

# Analysis timeouts
ANALYSIS_TIMEOUT_SECONDS = 90  # Max time per competitor analysis
DISCOVERY_MAX_DURATION_MINUTES = 30  # Max total discovery time

# Default limits
DEFAULT_MAX_COMPETITORS = 5
MAX_COMPETITORS_LIMIT = 20  # Hard limit even for admins


# ============================================================================
# MODELS
# ============================================================================

class CompetitorDiscoveryRequest(BaseModel):
    url: str = Field(..., description="Your company website URL")
    industry: str = Field(..., min_length=2, max_length=100, description="Industry/business category")
    country_code: str = Field("fi", pattern="^[a-z]{2}$", description="Country code (fi, en, sv, etc.)")
    max_competitors: int = Field(5, ge=1, le=20, description="Maximum number of competitors to analyze")
    custom_search_terms: Optional[List[str]] = Field(None, description="Custom search terms (optional)")
    exclude_domains: Optional[List[str]] = Field(None, description="Additional domains to exclude")
    include_social_media: bool = Field(False, description="Include social media pages in results")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_user_blacklist(username: str) -> List[str]:
    """Get user-specific blacklist from database or use default"""
    try:
        if DATABASE_ENABLED:
            # Try to load user preferences from database
            user_prefs = get_user_preferences_from_db(username)
            if user_prefs and user_prefs.get("blacklist_domains"):
                return user_prefs["blacklist_domains"]
    except Exception as e:
        logger.warning(f"Failed to load user blacklist: {e}")
    
    return DEFAULT_BLACKLIST_DOMAINS.copy()


async def multi_provider_search(
    search_terms: List[str],
    num_results: int = 7,
    country_code: str = "fi"
) -> List[str]:
    """
    Search using multiple providers with fallback mechanism
    Returns: List of URLs from all providers
    """
    all_results = []
    
    # Try Google first (primary provider)
    if SEARCH_PROVIDERS["google"]["enabled"] and GOOGLE_SEARCH_AVAILABLE:
        for term in search_terms:
            try:
                results = search(term, num_results=num_results, lang=country_code)
                all_results.extend(results)
                logger.info(f"✅ Google Search '{term}': {len(results)} results")
            except Exception as e:
                logger.warning(f"⚠️ Google search failed: '{term}' - {e}")
    
    # TODO: Add Bing fallback here if enabled
    # if SEARCH_PROVIDERS["bing"]["enabled"]:
    #     bing_results = await bing_search(search_terms, num_results)
    #     all_results.extend(bing_results)
    
    # If no results from any provider, use fallback database
    if not all_results:
        logger.warning("⚠️ All search providers failed, checking fallback database")
        # TODO: Implement database fallback with pre-indexed competitors
        # fallback_results = await get_competitors_from_database(industry, country_code)
        # all_results.extend(fallback_results)
    
    return all_results


def generate_smart_search_terms(
    industry: str,
    country_code: str,
    custom_terms: Optional[List[str]] = None
) -> List[str]:
    """
    Generate intelligent search terms based on industry and country
    """
    if custom_terms:
        return custom_terms
    
    # Language-specific search terms
    search_patterns = {
        "fi": [
            f"top 10 {industry} Suomessa",
            f"parhaat {industry} yritykset",
            f"{industry} kilpailijat Suomi",
            f"suositut {industry} palvelut"
        ],
        "en": [
            f"top {industry} companies",
            f"best {industry} services",
            f"{industry} competitors",
            f"leading {industry} providers"
        ],
        "sv": [
            f"bästa {industry} företag",
            f"topp {industry} tjänster",
            f"{industry} konkurrenter",
        ]
    }
    
    return search_patterns.get(country_code, search_patterns["en"])


async def update_task_progress(
    task_id: str,
    status: str,
    progress: int,
    message: Optional[str] = None
):
    """Update task progress with message"""
    update_data = {
        "status": status,
        "progress": progress,
        "last_update": datetime.now().isoformat()
    }
    if message:
        update_data["message"] = message
    
    task_queue.update_task(task_id, update_data)


# ============================================================================
# MAIN ENDPOINT
# ============================================================================

@app.post("/api/v1/discover-competitors", tags=["Competitor Discovery"])
async def discover_competitors(
    request: CompetitorDiscoveryRequest,
    user: UserInfo = Depends(require_user)
):
    """
    Discover and analyze competitors in background using Redis task queue.
    
    Features:
    - Multi-provider search with fallback
    - Smart search term generation
    - User-configurable parameters
    - Timeout protection
    - Real-time progress updates
    - Automatic credit refunds on failures
    """
    
    # === VALIDATION ===
    if not task_queue:
        raise HTTPException(503, "Task queue not available - Redis required")
    
    if not GOOGLE_SEARCH_AVAILABLE and os.getenv("MODE") != "development":
        raise HTTPException(501, "Competitor discovery not available - no search provider configured")
    
    # Validate max_competitors
    max_allowed = MAX_COMPETITORS_LIMIT if user.role == "admin" else DEFAULT_MAX_COMPETITORS * 2
    if request.max_competitors > max_allowed:
        raise HTTPException(
            400,
            f"Maximum {max_allowed} competitors allowed. You requested {request.max_competitors}."
        )
    
    logger.info(
        f"🔍 Discovery request: {user.username} | Industry: '{request.industry}' | "
        f"Max: {request.max_competitors} | Country: {request.country_code}"
    )
    
    # === 1. CHECK FOR EXISTING ACTIVE TASKS ===
    active_tasks = task_queue.check_user_active_tasks(user.username)
    if active_tasks > 0:
        raise HTTPException(
            429,
            f"You have {active_tasks} active discovery task(s). "
            "Please wait for completion or check status."
        )
    
    # === 2. VALIDATE USER URL ===
    try:
        user_domain = urlparse(request.url).netloc.replace("www.", "")
        if not user_domain:
            raise ValueError("Invalid domain")
    except Exception:
        raise HTTPException(400, "Invalid user URL provided")
    
    # === 3. CREATE TASK EARLY (for progress tracking) ===
    task_id = task_queue.create_task(
        task_type="competitor_discovery",
        data={
            "user_url": request.url,
            "industry": request.industry,
            "language": request.country_code,
            "max_competitors": request.max_competitors,
            "total": 0  # Will be updated
        },
        username=user.username
    )
    
    try:
        # === 4. SEARCH WITH PROGRESS UPDATES ===
        await update_task_progress(
            task_id,
            "searching",
            10,
            f"Searching for {request.industry} competitors..."
        )
        
        # Generate smart search terms
        search_terms = generate_smart_search_terms(
            request.industry,
            request.country_code,
            request.custom_search_terms
        )
        
        # Multi-provider search with fallback
        all_results = await multi_provider_search(
            search_terms,
            num_results=10,  # Get more results to filter from
            country_code=request.country_code
        )
        
        if not all_results:
            await update_task_progress(task_id, "failed", 0, "No search results found")
            raise HTTPException(
                503,
                "No search results found. Please try a different industry term or check back later."
            )
        
        await update_task_progress(
            task_id,
            "filtering",
            30,
            f"Found {len(all_results)} results, filtering competitors..."
        )
        
        # === 5. FILTER COMPETITORS ===
        # Get user-specific blacklist
        blacklist = await get_user_blacklist(user.username)
        
        # Add request-specific exclusions
        if request.exclude_domains:
            blacklist.extend(request.exclude_domains)
        
        # Remove social media if not requested
        if not request.include_social_media:
            social_domains = ["facebook.com", "linkedin.com", "instagram.com", "twitter.com", "tiktok.com"]
            blacklist.extend(social_domains)
        
        unique_urls = list(dict.fromkeys(all_results))
        
        potential_competitors = []
        seen_domains = {user_domain}
        
        for url in unique_urls:
            try:
                domain = urlparse(url).netloc.replace("www.", "")
                if not domain or domain in seen_domains:
                    continue
                
                # Check against blacklist
                if any(blacklisted in domain for blacklisted in blacklist):
                    continue
                
                seen_domains.add(domain)
                potential_competitors.append({
                    "url": url,
                    "domain": domain,
                    "discovered_at": datetime.now().isoformat()
                })
                
            except Exception:
                continue
        
        # Limit to requested amount
        competitors_to_analyze = potential_competitors[:request.max_competitors]
        
        if not competitors_to_analyze:
            await update_task_progress(task_id, "failed", 0, "No suitable competitors found")
            raise HTTPException(
                404,
                "No suitable competitors found after filtering. "
                "Try a more specific industry term or enable social media results."
            )
        
        logger.info(f"📊 Found {len(competitors_to_analyze)} competitors to analyze for {user.username}")
        
        # === 6. QUOTA CHECK & RESERVATION ===
        required_analyses = len(competitors_to_analyze)
        
        if user.role not in ["admin", "super_user"]:
            user_data = USERS_DB.get(user.username, {})
            user_limit = user_data.get("search_limit", DEFAULT_USER_LIMIT)
            current_count = user_search_counts.get(user.username, 0)
            available = user_limit - current_count
            
            if user_limit >= 0 and required_analyses > available:
                raise HTTPException(
                    403,
                    f"Discovery requires {required_analyses} analyses. "
                    f"You have {available} remaining of {user_limit} quota."
                )
            
            # RESERVE quota immediately
            user_search_counts[user.username] = current_count + required_analyses
            logger.info(f"💳 Reserved {required_analyses} credits for {user.username}")
        
        # === 7. UPDATE TASK WITH FINAL DATA ===
        task_queue.update_task(task_id, {
            "competitors": competitors_to_analyze,
            "total": len(competitors_to_analyze),
            "status": "pending",
            "progress": 40,
            "message": f"Starting analysis of {len(competitors_to_analyze)} competitors..."
        })
        
        # === 8. START BACKGROUND PROCESSING ===
        async def process_discovery():
            """Background worker for competitor analyses with timeout protection"""
            
            start_time = datetime.now()
            max_duration = timedelta(minutes=DISCOVERY_MAX_DURATION_MINUTES)
            
            try:
                await update_task_progress(
                    task_id,
                    "running",
                    50,
                    "Analysis in progress..."
                )
                
                successful_count = 0
                failed_count = 0
                
                for idx, competitor in enumerate(competitors_to_analyze, 1):
                    # Check global timeout
                    if datetime.now() - start_time > max_duration:
                        logger.warning(f"⏰ [{task_id}] Global timeout reached, stopping discovery")
                        break
                    
                    competitor_url = competitor["url"]
                    progress = 50 + int((idx / required_analyses) * 40)  # 50-90%
                    
                    try:
                        logger.info(
                            f"[Task {task_id}] Analyzing {idx}/{required_analyses}: {competitor_url}"
                        )
                        
                        await update_task_progress(
                            task_id,
                            "running",
                            progress,
                            f"Analyzing {idx}/{required_analyses}: {competitor['domain']}"
                        )
                        
                        # Clean and validate URL
                        clean_competitor_url = clean_url(competitor_url)
                        _reject_ssrf(clean_competitor_url)
                        
                        # Perform analysis WITH TIMEOUT
                        result = await asyncio.wait_for(
                            _perform_comprehensive_analysis_internal(
                                url=clean_competitor_url,
                                company_name=competitor["domain"],
                                language=request.country_code,
                                force_playwright=False,
                                user=user
                            ),
                            timeout=ANALYSIS_TIMEOUT_SECONDS
                        )
                        
                        # ✅ Save SUCCESS result (only essential data + cache_key)
                        task_queue.add_result(task_id, {
                            "url": competitor_url,
                            "domain": competitor["domain"],
                            "status": "success",
                            "score": result["basic_analysis"]["digital_maturity_score"],
                            "cache_key": get_cache_key(
                                clean_competitor_url,
                                "ai_comprehensive_v6.1.1_complete"
                            ),
                            "analyzed_at": datetime.now().isoformat(),
                            # Store only summary, not full analysis (save Redis memory)
                            "summary": {
                                "score": result["basic_analysis"]["digital_maturity_score"],
                                "strengths": result["basic_analysis"].get("key_strengths", [])[:3],
                                "technologies": result["basic_analysis"].get("technologies", {}).get("detected", [])[:5]
                            }
                        })
                        
                        successful_count += 1
                        logger.info(f"✅ [{task_id}] {idx}/{required_analyses} completed: {competitor_url}")
                        
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ [{task_id}] Timeout analyzing {competitor_url}")
                        
                        task_queue.add_result(task_id, {
                            "url": competitor_url,
                            "domain": competitor["domain"],
                            "status": "failed",
                            "error": "Analysis timeout - site took too long to analyze",
                            "error_type": "TimeoutError"
                        })
                        
                        failed_count += 1
                        
                        # Refund credit for timeout
                        if user.role not in ["admin", "super_user"]:
                            user_search_counts[user.username] = max(
                                0,
                                user_search_counts.get(user.username, 0) - 1
                            )
                            logger.info(f"💰 Refunded 1 credit to {user.username} (timeout)")
                        
                    except HTTPException as e:
                        logger.error(f"❌ [{task_id}] HTTP error {competitor_url}: {e.detail}")
                        
                        task_queue.add_result(task_id, {
                            "url": competitor_url,
                            "domain": competitor["domain"],
                            "status": "failed",
                            "error": str(e.detail),
                            "error_type": "HTTPException"
                        })
                        
                        failed_count += 1
                        
                        # Refund credit for HTTP errors
                        if user.role not in ["admin", "super_user"]:
                            user_search_counts[user.username] = max(
                                0,
                                user_search_counts.get(user.username, 0) - 1
                            )
                            logger.info(f"💰 Refunded 1 credit to {user.username} (HTTP error)")
                        
                    except Exception as e:
                        logger.error(f"❌ [{task_id}] Failed {competitor_url}: {e}", exc_info=True)
                        
                        task_queue.add_result(task_id, {
                            "url": competitor_url,
                            "domain": competitor["domain"],
                            "status": "failed",
                            "error": str(e)[:200],  # Limit error message length
                            "error_type": type(e).__name__
                        })
                        
                        failed_count += 1
                        
                        # Refund credit for general errors
                        if user.role not in ["admin", "super_user"]:
                            user_search_counts[user.username] = max(
                                0,
                                user_search_counts.get(user.username, 0) - 1
                            )
                            logger.info(f"💰 Refunded 1 credit to {user.username} (error)")
                
                # === COMPLETION ===
                completion_message = (
                    f"Completed: {successful_count} successful, {failed_count} failed"
                )
                
                await update_task_progress(
                    task_id,
                    "completed",
                    100,
                    completion_message
                )
                
                task_queue.update_task(task_id, {
                    "completed_at": datetime.now().isoformat(),
                    "successful": successful_count,
                    "failed": failed_count,
                    "duration_seconds": (datetime.now() - start_time).total_seconds()
                })
                
                logger.info(
                    f"🏁 Discovery task {task_id} completed for {user.username}: "
                    f"{successful_count}/{required_analyses} successful in "
                    f"{(datetime.now() - start_time).total_seconds():.1f}s"
                )
                
            except Exception as e:
                logger.error(f"💥 Discovery task {task_id} crashed: {e}", exc_info=True)
                
                await update_task_progress(
                    task_id,
                    "failed",
                    0,
                    f"Task failed: {str(e)[:100]}"
                )
                
                task_queue.update_task(task_id, {
                    "error": str(e),
                    "failed_at": datetime.now().isoformat()
                })
        
        # ✅ Start background task
        asyncio.create_task(process_discovery())
        
        # === 9. RETURN IMMEDIATE RESPONSE ===
        return {
            "success": True,
            "message": f"Competitor discovery started for {required_analyses} competitors",
            "task_id": task_id,
            "status_url": f"/api/v1/discovery-status/{task_id}",
            "results_url": f"/api/v1/discovery-results/{task_id}",
            "estimated_time_minutes": round(required_analyses * 1.5, 1),
            "competitors": [c["domain"] for c in competitors_to_analyze],
            "credits_reserved": required_analyses if user.role not in ["admin", "super_user"] else 0,
            "settings": {
                "max_competitors": request.max_competitors,
                "country": request.country_code,
                "include_social_media": request.include_social_media
            }
        }
        
    except HTTPException:
        # Clean up task on HTTP errors
        if task_queue:
            task_queue.update_task(task_id, {"status": "failed", "progress": 0})
        raise
    except Exception as e:
        # Clean up task on unexpected errors
        if task_queue:
            task_queue.update_task(task_id, {"status": "failed", "progress": 0})
        logger.error(f"Discovery setup failed: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to start discovery: {str(e)}")


# ============================================================================
# STATUS & RESULTS ENDPOINTS
# ============================================================================

@app.get("/api/v1/discovery-status/{task_id}", tags=["Competitor Discovery"])
async def get_discovery_status(
    task_id: str,
    user: UserInfo = Depends(require_user)
):
    """
    Get real-time competitor discovery task status with progress.
    
    Returns detailed status including:
    - Current progress percentage
    - Status message
    - Partial results (if available)
    - Summary statistics
    """
    
    if not task_queue:
        raise HTTPException(503, "Task queue not available")
    
    task_status = task_queue.get_task_status(task_id)
    
    if task_status.get("status") == "not_found":
        raise HTTPException(404, "Task not found or expired")
    
    # Permission check
    if task_status.get("username") != user.username and user.role not in ["admin", "super_user"]:
        raise HTTPException(403, "Not your task")
    
    # Get results if available
    results = []
    if task_status.get("status") in ["running", "completed", "failed"]:
        results = task_queue.get_results(task_id)
    
    # Calculate summary
    successful_results = [r for r in results if r.get("status") == "success"]
    failed_results = [r for r in results if r.get("status") == "failed"]
    
    top_competitor = None
    if successful_results:
        top_competitor = max(successful_results, key=lambda x: x.get("score", 0))
    
    return {
        "task_id": task_id,
        "status": task_status.get("status"),
        "progress": task_status.get("progress", 0),
        "message": task_status.get("message"),
        "total": task_status.get("total", 0),
        "created_at": task_status.get("created_at"),
        "started_at": task_status.get("started_at"),
        "completed_at": task_status.get("completed_at"),
        "duration_seconds": task_status.get("duration_seconds"),
        "results_preview": results[:3] if results else [],  # First 3 results for preview
        "summary": {
            "total": len(results),
            "successful": len(successful_results),
            "failed": len(failed_results),
            "in_progress": task_status.get("total", 0) - len(results),
            "top_competitor": {
                "domain": top_competitor.get("domain"),
                "score": top_competitor.get("score"),
                "url": top_competitor.get("url")
            } if top_competitor else None
        }
    }


@app.get("/api/v1/discovery-results/{task_id}", tags=["Competitor Discovery"])
async def get_discovery_results(
    task_id: str,
    user: UserInfo = Depends(require_user),
    include_full_analysis: bool = False
):
    """
    Get full competitor discovery results.
    
    Args:
        task_id: Discovery task ID
        include_full_analysis: If true, fetch full analysis from cache (slower but complete)
    
    Returns:
        Complete competitor analysis results
    """
    
    if not task_queue:
        raise HTTPException(503, "Task queue not available")
    
    task_status = task_queue.get_task_status(task_id)
    
    if task_status.get("status") == "not_found":
        raise HTTPException(404, "Task not found or expired")
    
    # Permission check
    if task_status.get("username") != user.username and user.role not in ["admin", "super_user"]:
        raise HTTPException(403, "Not your task")
    
    if task_status.get("status") not in ["completed", "failed"]:
        raise HTTPException(400, "Task not completed yet. Use /discovery-status to check progress.")
    
    # Get results from Redis
    results = task_queue.get_results(task_id)
    
    # If full analysis requested, fetch from cache
    full_analyses = []
    if include_full_analysis:
        for result in results:
            if result.get("status") == "success":
                cache_key = result.get("cache_key")
                if cache_key:
                    try:
                        cached_analysis = await get_from_cache(cache_key)
                        if cached_analysis:
                            full_analyses.append(cached_analysis)
                        else:
                            # Fallback: use summary if cache miss
                            full_analyses.append({
                                "domain": result["domain"],
                                "url": result["url"],
                                "summary": result.get("summary"),
                                "note": "Full analysis not available in cache"
                            })
                    except Exception as e:
                        logger.error(f"Failed to fetch cached analysis: {e}")
                        full_analyses.append({
                            "domain": result["domain"],
                            "error": "Failed to load full analysis"
                        })
    else:
        # Return summaries only (fast)
        full_analyses = [
            {
                "domain": r["domain"],
                "url": r["url"],
                "status": r["status"],
                "score": r.get("score"),
                "summary": r.get("summary"),
                "cache_key": r.get("cache_key"),
                "analyzed_at": r.get("analyzed_at")
            }
            for r in results if r.get("status") == "success"
        ]
    
    # Sort by score (highest first)
    full_analyses.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return {
        "task_id": task_id,
        "status": task_status.get("status"),
        "completed_at": task_status.get("completed_at"),
        "duration_seconds": task_status.get("duration_seconds"),
        "competitors_analyzed": len(full_analyses),
        "total_competitors": task_status.get("total", 0),
        "successful": task_status.get("successful", 0),
        "failed": task_status.get("failed", 0),
        "analyses": full_analyses,
        "metadata": {
            "industry": task_status.get("industry"),
            "country": task_status.get("language"),
            "user_url": task_status.get("user_url"),
            "include_full_analysis": include_full_analysis
        }
    }


# ============================================================================
# USER DISCOVERIES LIST
# ============================================================================

@app.get("/api/v1/my-discoveries", tags=["Competitor Discovery"])
async def get_my_discoveries(
    user: UserInfo = Depends(require_user),
    limit: int = 20,
    status: Optional[str] = None
):
    """
    Get list of user's discovery tasks.
    
    Args:
        limit: Maximum number of tasks to return
        status: Filter by status (pending, running, completed, failed)
    """
    
    if not task_queue:
        raise HTTPException(503, "Task queue not available")
    
    try:
        # Get user's tasks from Redis
        user_tasks = task_queue.get_user_tasks(user.username, limit=limit)
        
        # Filter by status if requested
        if status:
            user_tasks = [t for t in user_tasks if t.get("status") == status]
        
        # Enrich with summary data
        enriched_tasks = []
        for task in user_tasks:
            task_id = task.get("task_id")
            results = task_queue.get_results(task_id)
            
            enriched_tasks.append({
                "task_id": task_id,
                "status": task.get("status"),
                "progress": task.get("progress", 0),
                "created_at": task.get("created_at"),
                "completed_at": task.get("completed_at"),
                "industry": task.get("industry"),
                "total_competitors": task.get("total", 0),
                "successful": len([r for r in results if r.get("status") == "success"]),
                "failed": len([r for r in results if r.get("status") == "failed"])
            })
        
        return {
            "discoveries": enriched_tasks,
            "total": len(enriched_tasks)
        }
        
    except Exception as e:
        logger.error(f"Failed to get user discoveries: {e}")
        raise HTTPException(500, "Failed to retrieve discoveries")


# ============================================================================
# MAIN ANALYSIS ENDPOINT
# ============================================================================

@app.post("/api/v1/ai-analyze")
async def ai_analyze_comprehensive(
    request: CompetitorAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: UserInfo = Depends(require_user)
):
    """Complete comprehensive website analysis with full SPA support."""
    try:
        # === QUOTA CHECK ===
        if user.role != "admin":
            user_limit = USERS_DB.get(user.username, {}).get("search_limit", DEFAULT_USER_LIMIT)
            current_count = user_search_counts.get(user.username, 0)
            
            if user_limit > 0 and current_count >= user_limit:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Search limit reached ({user_limit} searches). Contact admin for more quota."
                )
        
        # === URL VALIDATION ===
        url = clean_url(request.url)
        _reject_ssrf(url)
        
        # === PERFORM ANALYSIS ===
        result = await _perform_comprehensive_analysis_internal(
            url=url,
            company_name=request.company_name,
            language=request.language,
            force_playwright=getattr(request, 'force_playwright', False),
            user=user,
            revenue_input=None
        )
        
        # === POST-PROCESSING ===
        if user.role != "admin":
            user_search_counts[user.username] = current_count + 1
            logger.info(
                f"Quota: {user.username} used {user_search_counts[user.username]}/{user_limit}"
            )
        
        background_tasks.add_task(cleanup_cache)
        
        logger.info(
            f"✅ Analysis complete for {user.username}: {url} | "
            f"Score: {result['basic_analysis']['digital_maturity_score']}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"❌ Analysis failed for {request.url} (user: {user.username}): {e}", 
            exc_info=True
        )
        raise HTTPException(
            status_code=500, 
            detail="Analysis failed due to internal error. Please try again or contact support."
        )
#=============================================================================
# ============================================================================
# KORJATTU MY-DISCOVERIES ENDPOINT
# ============================================================================
# Korvaa rivit 5089-5146 tiedostossa main_merged.py

@app.get("/api/v1/my-discoveries")
async def get_my_discoveries(
    user: UserInfo = Depends(require_user)
):
    """
    Get user's recent discovery tasks
    Returns list of discovery sessions with full details
    """
    
    if not redis_client:
        # Fallback: palauta tyhjä lista jos Redis ei ole käytössä
        logger.warning("Redis not available, returning empty discoveries")
        return []
    
    try:
        logger.info(f"Fetching discoveries for user: {user.username}")
        all_tasks = []
        
        # Redis key pattern: "task:{task_id}"
        # Käytetään SCAN:ia kaikkien taskien läpikäyntiin
        cursor = 0
        scanned_count = 0
        
        while True:
            cursor, keys = redis_client.scan(cursor, match="task:*", count=100)
            scanned_count += len(keys)
            
            for key in keys:
                try:
                    task_data = redis_client.get(key)
                    if not task_data:
                        continue
                    
                    task = json.loads(task_data)
                    
                    # Suodata käyttäjän taskit
                    if task.get("username") != user.username:
                        continue
                    
                    task_id = key.decode('utf-8').split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                    
                    # Hae task status
                    if not task_queue:
                        continue
                        
                    status = task_queue.get_task_status(task_id)
                    
                    if status.get("status") == "not_found":
                        continue
                    
                    # Rakenna discovery-objekti frontendille
                    discovery_data = task.get("data", {})
                    results = status.get("results", [])
                    
                    discovery = {
                        "id": task_id,
                        "task_id": task_id,
                        "url": discovery_data.get("url", ""),
                        "domain": discovery_data.get("url", "").replace("https://", "").replace("http://", "").split("/")[0],
                        "industry": discovery_data.get("industry"),
                        "status": status.get("status", "unknown"),
                        "competitors_found": len([r for r in results if r.get("status") == "success"]),
                        "total": status.get("total", 0),
                        "progress": status.get("progress", 0),
                        "results": results[:10],  # Max 10 tulosta per discovery
                        "created_at": status.get("created_at", ""),
                        "updated_at": status.get("completed_at") or status.get("updated_at", ""),
                        "completed_at": status.get("completed_at")
                    }
                    
                    all_tasks.append(discovery)
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode task {key}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing task {key}: {e}")
                    continue
            
            if cursor == 0:
                break
        
        logger.info(f"Scanned {scanned_count} tasks, found {len(all_tasks)} for user {user.username}")
        
        # Järjestä uusimmasta vanhimpaan
        all_tasks.sort(
            key=lambda x: x.get("created_at", "1970-01-01T00:00:00Z"), 
            reverse=True
        )
        
        # Palauta max 50 viimeisintä (frontend rajaa 50:een)
        discoveries = all_tasks[:50]
        
        logger.info(f"Returning {len(discoveries)} discoveries for {user.username}")
        
        # TÄRKEÄ: Palauta LISTA, ei dict!
        # Frontend odottaa: Array<Discovery>
        return discoveries
        
    except Exception as e:
        logger.error(f"Failed to fetch discoveries for {user.username}: {e}", exc_info=True)
        # Palauta tyhjä lista virheen sijaan
        # Frontend näyttää "No discoveries yet" -viestin
        return []


# ============================================================================
# LISÄYS: Discovery results endpoint
# ============================================================================
# Lisää tämä heti get_my_discoveries jälkeen

@app.get("/api/v1/discovery-results/{task_id}")
async def get_discovery_results(
    task_id: str,
    user: UserInfo = Depends(require_user)
):
    """
    Get full results for a specific discovery task
    Allows user to view detailed analysis of a past discovery
    """
    
    if not task_queue:
        raise HTTPException(503, "Task queue not available")
    
    try:
        # Tarkista että task kuuluu käyttäjälle
        task_key = f"task:{task_id}"
        task_data = redis_client.get(task_key)
        
        if not task_data:
            raise HTTPException(404, "Discovery not found")
        
        task = json.loads(task_data)
        
        if task.get("username") != user.username:
            raise HTTPException(403, "Access denied")
        
        # Hae task status ja tulokset
        status = task_queue.get_task_status(task_id)
        
        if status.get("status") == "not_found":
            raise HTTPException(404, "Discovery not found")
        
        return {
            "task_id": task_id,
            "status": status.get("status"),
            "url": task.get("data", {}).get("url"),
            "industry": task.get("data", {}).get("industry"),
            "total": status.get("total", 0),
            "progress": status.get("progress", 0),
            "results": status.get("results", []),
            "analyses": status.get("analyses", []),  # Full analysis data
            "created_at": status.get("created_at"),
            "completed_at": status.get("completed_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch discovery results: {e}")
        raise HTTPException(500, f"Failed to fetch discovery results: {str(e)}")

# ============================================================================
# ANALYSIS CORE - INTERNAL HELPER

## ============================================================================
# SYSTEM AND ADMIN ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME, "version": APP_VERSION, "status": "operational",
        "endpoints": {
            "health": "/health", 
            "auth": {"login": "/auth/login", "me": "/auth/me"},
            "analysis": {"comprehensive": "/api/v1/ai-analyze", "basic": "/api/v1/analyze"}
        },
        "features": [
            "JWT authentication with role-based access",
            "Configurable scoring system",
            "Complete 9-feature enhanced analysis",
            "SPA detection and smart rendering",
            "Playwright support for modern web apps",
            "AI-powered insights with OpenAI integration",
            "Complete frontend compatibility"
        ],
        "capabilities": {
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "playwright_enabled": PLAYWRIGHT_ENABLED,
            "spa_detection": True,
            "modern_web_analysis": True,
            "enhanced_features_count": 9,
            "openai_available": bool(openai_client)
        },
        "scoring_system": {"version": "configurable_v1_complete", "weights": SCORING_CONFIG.weights}
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "version": APP_VERSION, 
        "timestamp": datetime.now().isoformat(),
        "system": {
            "openai_available": bool(openai_client),
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "playwright_enabled": PLAYWRIGHT_ENABLED,
            "cache_size": len(analysis_cache),
            "enhanced_features": 9,
            "complete_models": True
        },
        "scoring": {"weights": SCORING_CONFIG.weights, "configurable": True}
    }

@app.get("/api/v1/config")
async def get_config(user: UserInfo = Depends(require_admin)):
    return {
        "weights": SCORING_CONFIG.weights,
        "content_thresholds": SCORING_CONFIG.content_thresholds,
        "technical_thresholds": SCORING_CONFIG.technical_thresholds,
        "seo_thresholds": SCORING_CONFIG.seo_thresholds,
        "version": APP_VERSION
    }

@app.post("/admin/reset-all")
async def admin_reset_all(user: UserInfo = Depends(require_admin)):
    user_search_counts.clear()
    analysis_cache.clear()
    logger.info("Admin reset: all counters and cache cleared")
    return {"ok": True, "message": "All user counters and cache cleared."}

@app.post("/admin/reset/{username}")
async def admin_reset_user(username: str, user: UserInfo = Depends(require_admin)):
    user_search_counts.pop(username, None)
    logger.info(f"Admin reset: counter cleared for {username}")
    return {"ok": True, "message": f"Counter cleared for {username}."}

@app.get("/admin/users", response_model=List[UserQuotaView])
async def admin_list_users(user: UserInfo = Depends(require_admin)):
    return [
        UserQuotaView(
            username=u,
            role=USERS_DB[u]["role"],
            search_limit=USERS_DB[u]["search_limit"],
            searches_used=user_search_counts.get(u, 0),
        )
        for u in USERS_DB.keys()
    ]

@app.post("/admin/users/{username}/quota", response_model=UserQuotaView)
async def admin_update_quota(username: str, payload: QuotaUpdateRequest, user: UserInfo = Depends(require_admin)):
    if username not in USERS_DB:
        raise HTTPException(404, "User not found")
    
    # ✅ 1. Päivitä muistissa
    if payload.search_limit is not None:
        USERS_DB[username]["search_limit"] = int(payload.search_limit)
    if payload.grant_extra is not None:
        cur = USERS_DB[username]["search_limit"]
        if cur != -1:
            USERS_DB[username]["search_limit"] = cur + int(payload.grant_extra)
    if payload.reset_count:
        user_search_counts[username] = 0
    
    # ✅ 2. Päivitä tietokantaan
    if DATABASE_ENABLED:
        update_data = {}
        if payload.search_limit is not None or payload.grant_extra is not None:
            update_data['search_limit'] = USERS_DB[username]["search_limit"]
        if payload.reset_count:
            update_data['searches_used'] = 0
        
        if update_data:
            update_user_in_db(username, **update_data)
    
    return UserQuotaView(
        username=username,
        role=USERS_DB[username]["role"],
        search_limit=USERS_DB[username]["search_limit"],
        searches_used=user_search_counts.get(username, 0),
    )

# ============================================================================
# NEW: USER MANAGEMENT ENDPOINTS
# ============================================================================

class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6)
    role: str = Field("user", pattern="^(user|admin|super_user)$") 
    search_limit: int = Field(3, ge=-1)

@app.post("/admin/users", response_model=UserQuotaView)
async def admin_create_user(payload: UserCreateRequest, user: UserInfo = Depends(require_admin)):
    """Create a new user (admin only)"""
    
    # ✅ Tarkista sekä muistista ETTÄ tietokannasta
    if payload.username in USERS_DB:
        raise HTTPException(400, f"User '{payload.username}' already exists")
    
    if DATABASE_ENABLED and get_user_from_db(payload.username):
        raise HTTPException(400, f"User '{payload.username}' already exists in database")
    
    # Hash password
    hashed_password = pwd_context.hash(payload.password)
    
    # ✅ 1. Tallenna USERS_DB (muisti)
    USERS_DB[payload.username] = {
        "username": payload.username,
        "hashed_password": hashed_password,
        "role": payload.role,
        "search_limit": payload.search_limit
    }
    
    # ✅ 2. Tallenna tietokantaan (jos saatavilla)
    if DATABASE_ENABLED:
        success = create_user_in_db(
            username=payload.username,
            hashed_password=hashed_password,
            role=payload.role,
            search_limit=payload.search_limit
        )
        if not success:
            # Rollback memory if DB save fails
            del USERS_DB[payload.username]
            raise HTTPException(500, "Failed to save user to database")
    
    logger.info(f"Admin {user.username} created user: {payload.username} (role={payload.role}, limit={payload.search_limit})")
    
    return UserQuotaView(
        username=payload.username,
        role=payload.role,
        search_limit=payload.search_limit,
        searches_used=0
    )

def require_admin_or_super(user: UserInfo = Depends(get_current_user)):
    """Require admin OR super_user role"""
    if user.role not in ["admin", "super_user"]:
        raise HTTPException(403, "Admin or Super User access required")
    return user


# ============================================================================
# ADMIN ROLE UPDATE ENDPOINT
# ============================================================================

# ✅ UpdateRoleRequest määritellään VAIN KERRAN!
class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin|super_user)$")


@app.put("/admin/users/{username}/role")
async def admin_update_user_role(
    username: str, 
    payload: UpdateRoleRequest, 
    user: UserInfo = Depends(require_admin)
):
    """Update user role (admin only)"""
    
    # Prevent self-demotion
    if username == user.username and payload.role != "admin":
        raise HTTPException(400, "Cannot change your own role")
    
    # Check user exists in memory
    if username not in USERS_DB:
        # Check database
        if DATABASE_ENABLED and not get_user_from_db(username):
            raise HTTPException(404, f"User '{username}' not found")
    
    # Update in memory
    if username in USERS_DB:
        USERS_DB[username]["role"] = payload.role
    
    # Update in database
    if DATABASE_ENABLED:
        success = update_user_in_db(username, role=payload.role)
        if not success:
            raise HTTPException(500, "Failed to update user in database")
    
    logger.info(f"Admin {user.username} updated role for {username} to {payload.role}")
    
    return {
        "username": username,
        "role": payload.role,
        "message": f"Role updated to {payload.role}"
    }


@app.delete("/admin/users/{username}")
async def admin_delete_user(username: str, user: UserInfo = Depends(require_admin)):
    """Delete a user (admin only)"""
    
    # ✅ Tarkista sekä muistista ETTÄ tietokannasta
    if username not in USERS_DB and (not DATABASE_ENABLED or not get_user_from_db(username)):
        raise HTTPException(404, "User not found")
    
    if username == "admin":
        raise HTTPException(403, "Cannot delete admin user")
    
    if username == user.username:
        raise HTTPException(403, "Cannot delete yourself")
    
    # ✅ 1. Poista muistista
    if username in USERS_DB:
        del USERS_DB[username]
    
    # ✅ 2. Poista tietokannasta
    if DATABASE_ENABLED:
        delete_user_from_db(username)
    
    # ✅ 3. Poista search counter
    user_search_counts.pop(username, None)
    
    logger.info(f"Admin {user.username} deleted user: {username}")
    
    return {"ok": True, "message": f"User '{username}' deleted successfully"}

# ============================================================================
# KILPAILUETU-TUTKA ENDPOINT - KAUPALLINEN VERSIO
# ============================================================================

@app.post("/api/v1/competitive-radar", response_model=CompetitiveRadarResponse)
async def analyze_competitive_radar(
    request: CompetitiveRadarRequest,
    user: UserInfo = Depends(require_user)
):
    """
    Kilpailuetu-tutka: Analysoi oma sivu + kilpailijat ja tunnista strategiset mahdollisuudet.
    
    Palauttaa:
        - Syvällinen erottuvuusanalyysi
        - Todelliset markkinaaukot
        - Kilpailullinen asemointi
        - Strategiset suositukset
    """
    try:
        # === QUOTA CHECK ===
        required_analyses = 1 + len(request.competitor_urls)
        
        if user.role != "admin":
            user_limit = USERS_DB.get(user.username, {}).get("search_limit", DEFAULT_USER_LIMIT)
            current_count = user_search_counts.get(user.username, 0)
            available = user_limit - current_count
            
            if user_limit > 0 and required_analyses > available:
                raise HTTPException(
                    403,
                    f"Competitive Radar requires {required_analyses} analyses. "
                    f"You have {available} remaining of {user_limit} quota."
                )
        
        logger.info(f"[Radar] Starting analysis for {user.username}: {request.your_url} vs {len(request.competitor_urls)} competitors")
        
        # === 1. ANALYSOI OMA SIVU ===
        your_url = clean_url(request.your_url)
        _reject_ssrf(your_url)
        
        logger.info(f"[Radar] Analyzing YOUR site: {your_url}")
        
        your_analysis = await _perform_comprehensive_analysis_internal(
            url=your_url,
            language=request.language,
            user=user
        )
        
        # === 2. ANALYSOI KILPAILIJAT ===
        competitor_analyses = []
        failed_competitors = []
        
        for idx, competitor_url in enumerate(request.competitor_urls, 1):
            try:
                clean_comp_url = clean_url(competitor_url)
                _reject_ssrf(clean_comp_url)
                
                logger.info(f"[Radar] Analyzing competitor {idx}/{len(request.competitor_urls)}: {clean_comp_url}")
                
                comp_analysis = await _perform_comprehensive_analysis_internal(
                    url=clean_comp_url,
                    language=request.language,
                    user=user
                )
                
                competitor_analyses.append(comp_analysis)
                logger.info(f"[Radar] ✅ Competitor {idx} done: {comp_analysis['basic_analysis']['company']}")
                
            except HTTPException as e:
                logger.error(f"[Radar] ❌ HTTPException for {competitor_url}: {e.detail}")
                failed_competitors.append({
                    'url': competitor_url,
                    'error': str(e.detail)
                })
            except Exception as e:
                logger.error(f"[Radar] ❌ Exception for {competitor_url}: {e}", exc_info=True)
                failed_competitors.append({
                    'url': competitor_url,
                    'error': f"Analysis failed: {str(e)}"
                })
        
        # === 3. TARKISTA ETTÄ AINAKIN 1 KILPAILIJA ONNISTUI ===
        if not competitor_analyses:
            raise HTTPException(
                400, 
                f"Failed to analyze any competitors. Errors: {failed_competitors}"
            )
        
        logger.info(f"[Radar] Successfully analyzed: 1 your site + {len(competitor_analyses)} competitors ({len(failed_competitors)} failed)")
        
        # === 4. UPDATE QUOTA ===
        if user.role != "admin":
            successful_analyses = 1 + len(competitor_analyses)
            user_search_counts[user.username] = current_count + successful_analyses
            logger.info(f"[Radar] Used {successful_analyses} credits for {user.username}")
        
        # === 5. EXTRACT SUMMARIES ===
        your_summary = _extract_detailed_summary(your_analysis)
        
        if your_summary is None:
            logger.error(f"❌ Failed to extract your_summary for {request.your_url}")
            raise HTTPException(
                500, 
                "Failed to extract analysis data from your website. Please try again."
            )
        
        comp_summaries = []
        for idx, comp_analysis in enumerate(competitor_analyses, 1):
            summary = _extract_detailed_summary(comp_analysis)
            if summary is None:
                logger.error(
                    f"❌ Failed to extract competitor {idx}: "
                    f"{comp_analysis.get('basic_analysis', {}).get('website', 'unknown')}"
                )
                continue  # Skip this competitor
            summary['analysis'] = comp_analysis
            comp_summaries.append(summary)
        
        if not comp_summaries:
            raise HTTPException(
                500, 
                "Failed to extract analysis data from competitors. Please try again."
            )
        
        logger.info(
            f"✅ Successfully extracted summaries: "
            f"your_score={your_summary['score']}, "
            f"competitors={[(c['company'], c['score']) for c in comp_summaries]}"
        )
        # ✅ LISÄÄ TÄMÄ - Yhtenäistä your_analysis samaan muotoon kuin competitors
        your_analysis_unified = {
                **your_summary,  # company, score, content_strategy, technical_maturity...
                'analysis': your_analysis  # full analysis detailed view:tä varten
            }
        # === 6. SYVÄLLINEN EROTTUVUUSANALYYSI ===
        logger.info("[Radar] Building differentiation matrix...")
        
        differentiation_matrix = await _build_differentiation_matrix(
            your_analysis, 
            competitor_analyses,
            request.language,
            request.industry_context
        )
        
        logger.info(f"[Radar] ✅ Differentiation matrix built with keys: {list(differentiation_matrix.keys())}")
        
        # === 7. TODELLISET MARKKINAAUKOT (AI-pohjainen) ===
        logger.info("[Radar] Discovering market gaps...")
        
        market_gaps = await _discover_real_market_gaps(
            your_analysis,
            competitor_analyses,
            request.language
        )
        
        logger.info(f"[Radar] ✅ Found {len(market_gaps)} market gaps")
        
        # === 8. KILPAILULLINEN ASEMOINTI ===
        logger.info("[Radar] Calculating market positioning...")
        
        positioning = await _calculate_market_positioning(
            your_analysis,
            competitor_analyses
        )
        
        logger.info(
            f"[Radar] ✅ Positioning: {positioning['positioning_quadrant']}, "
            f"competitive_score={positioning['competitive_score']}"
        )
        
        # === 9. STRATEGISET SUOSITUKSET ===
        logger.info("[Radar] Generating strategic recommendations...")
        
        strategic_recommendations = await _generate_strategic_recommendations(
            your_analysis,
            competitor_analyses,
            differentiation_matrix,
            market_gaps,
            request.language
        )
        
        logger.info(f"[Radar] ✅ Generated {len(strategic_recommendations)} strategic recommendations")
        
       # === 10. RAKENNA RESPONSE ===
        logger.info("[Radar] Building final response...")

        # ✅ KORJAUS: Yhdenmukaista your_analysis summary-muotoon
        # Rakenna unified structure jossa on sekä summary että täysi analyysi
        your_analysis_unified = {
            **your_summary,           # ✅ Summary-kentät (company, score, messaging...)
            'analysis': your_analysis # ✅ Täysi analyysi sisällä (jos frontend tarvitsee)
        }

        # ✅ Lisää sama rakenne kilpailijoille
        comp_summaries_unified = []
        for idx, comp_summary in enumerate(comp_summaries):
            comp_summaries_unified.append({
                **comp_summary,                    # ✅ Summary-kentät
                'analysis': competitor_analyses[idx] # ✅ Täysi analyysi sisällä
            })

        # ✅ Rakenna response yhdenmukaisen datan kanssa
        response = CompetitiveRadarResponse(
            your_analysis=your_analysis_unified,  # ✅ Unified rakenne
            competitors=comp_summaries_unified,   # ✅ Unified rakenne
            differentiation_matrix=differentiation_matrix,
            market_gaps=market_gaps,
            competitive_score=positioning['competitive_score'],
            strategic_recommendations=strategic_recommendations,
            positioning_map=positioning
        )

        logger.info(
            f"[Radar] 🎯 COMPLETE for {user.username}: "
            f"Score={positioning['competitive_score']}, "
            f"Gaps={len(market_gaps)}, "
            f"Recommendations={len(strategic_recommendations)}"
        )

        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except Exception as e:
        logger.error(f"[Radar] 💥 FATAL ERROR: {e}", exc_info=True)
        raise HTTPException(
            500, 
            f"Competitive Radar analysis failed: {str(e)}"
        )


# ============================================================================
# SYVÄLLISET ANALYYSIFUNKTIOT
# ============================================================================

def _extract_detailed_summary(analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Pura kaikki oleelliset kilpailutekijät.
    
    Returns:
        Dict jos onnistui, None jos data on korruptoitunut
    """
    
    # ✅ VARMISTA ETTÄ DATA ON OLEMASSA
    if not analysis:
        logger.error("❌ _extract_detailed_summary: analysis is empty")
        return None
    
    basic = analysis.get('basic_analysis', {})
    
    # ✅ KRIITTINEN TARKISTUS
    if not basic or not isinstance(basic, dict):
        logger.error(f"❌ Missing basic_analysis for URL: {analysis.get('metadata', {}).get('url', 'unknown')}")
        logger.error(f"Analysis keys: {list(analysis.keys())}")
        return None
    
    # ✅ VARMISTA ETTÄ PISTEET EIVÄT OLE 0 (ellei todella ole)
    score = basic.get('digital_maturity_score', 0)
    if score == 0:
        logger.warning(f"⚠️ Score is 0 for {basic.get('company', 'unknown')} - is this correct?")
        # Ei blokkaa, mutta logittaa
    
    ai = analysis.get('ai_analysis', {})
    detailed = analysis.get('detailed_analysis', {})
    content = detailed.get('content_analysis', {})
    technical = detailed.get('technical_audit', {})
    social = detailed.get('social_media', {})
    
    # ✅ VARMISTA ETTÄ PAKOLLISET KENTÄT OVAT OLEMASSA
    if not content or not technical:
        logger.error(f"❌ Missing detailed_analysis for {basic.get('company', 'unknown')}")
        return None
    
    # ✅ DEBUG LOG
    logger.info(f"✅ Extracted summary: {basic.get('company', 'unknown')} - Score: {score}, Words: {content.get('word_count', 0)}")
    
    return {
        'url': basic.get('website', ''),
        'company': basic.get('company', 'Unknown Company'),
        'score': int(score),  # ✅ Varmista int
        
        # Viestintä
        'messaging': {
            'title': str(basic.get('title', '')),
            'meta_description': str(basic.get('meta_description', '')),
            'h1_count': int(basic.get('h1_count', 0)),
            'tone': _analyze_messaging_tone(content)
        },
        
        # Sisältöstrategia
        'content_strategy': {
            'word_count': int(content.get('word_count', 0)),  # ✅ int
            'has_blog': bool(content.get('has_blog', False)),  # ✅ bool
            'content_depth': _categorize_content_depth(content.get('word_count', 0)),
            'media_richness': len(content.get('media_types', [])),
            'interactive_elements': len(content.get('interactive_elements', []))
        },
        
        # Tekninen kypsyys
        'technical_maturity': {
            'has_ssl': bool(technical.get('has_ssl', False)),
            'page_speed_score': int(technical.get('page_speed_score', 0)),
            'mobile_optimization': bool(technical.get('has_mobile_optimization', False)),
            'has_analytics': bool(technical.get('has_analytics', False)),
            'spa_detected': bool(basic.get('spa_detected', False)),
            'modernity_score': int(basic.get('modernity_score', 0))
        },
        
        # Sosiaalinen läsnäolo
        'social_presence': {
            'platforms': list(social.get('platforms', [])),
            'platform_count': len(social.get('platforms', [])),
            'has_sharing': bool(social.get('has_sharing_buttons', False)),
            'og_tags': int(social.get('open_graph_tags', 0))
        },
        
        # AI-insightit
        'key_strengths': list(ai.get('strengths', []))[:3],
        'key_weaknesses': list(ai.get('weaknesses', []))[:3],
        'opportunities': list(ai.get('opportunities', []))[:3]
    }

def _analyze_messaging_tone(content: Dict[str, Any]) -> str:
    """Analysoi viestinnän sävy tarkemmin"""
    readability = content.get('readability_score', 50)
    word_count = content.get('word_count', 0)
    
    if readability >= 75 and word_count > 1000:
        return "Asiantunteva mutta helposti lähestyttävä"
    elif readability >= 70:
        return "Selkeä ja keskustelevä"
    elif readability >= 60:
        return "Ammattimainen ja informatiivinen"
    elif readability >= 50:
        return "Tekninen ja muodollinen"
    else:
        return "Monimutkainen ja raskas"

def _categorize_content_depth(word_count: int) -> str:
    """Kategorisoi sisällön syvyys liiketoiminnallisesti"""
    if word_count >= 5000:
        return "Thought leadership / Comprehensive resource"
    elif word_count >= 2500:
        return "In-depth content / Authority building"
    elif word_count >= 1500:
        return "Standard informative / Service description"
    elif word_count >= 800:
        return "Basic landing page / Product focus"
    elif word_count >= 300:
        return "Minimal / Brochure-style"
    else:
        return "Under-developed / Thin content"

async def _build_differentiation_matrix(
    your_analysis: Dict[str, Any],
    competitor_analyses: List[Dict[str, Any]],
    language: str,
    industry_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Rakenna syvällinen erottuvuusmatriisi vertailemalla konkreettisia tekijöitä.
    Käyttää AI:ta mutta myös datapohjaista analyysiä.
    """
    
    your_summary = _extract_detailed_summary(your_analysis)
    comp_summaries = [_extract_detailed_summary(c) for c in competitor_analyses]
    
    # === 1. DATAPOHJAINEN VERTAILU ===
    comparison_matrix = {
        'messaging': _compare_messaging(your_summary, comp_summaries),
        'content_strategy': _compare_content_strategy(your_summary, comp_summaries),
        'technical_execution': _compare_technical(your_summary, comp_summaries),
        'social_engagement': _compare_social(your_summary, comp_summaries)
    }
    
    # === 2. AI-POHJAINEN SYVÄ ANALYYSI ===
    if openai_client:
        try:
            ai_insights = await _get_ai_differentiation_insights(
                your_summary,
                comp_summaries,
                comparison_matrix,
                language,
                industry_context
            )
            comparison_matrix['ai_insights'] = ai_insights
        except Exception as e:
            logger.error(f"AI insights failed: {e}")
            comparison_matrix['ai_insights'] = None
    
    # === 3. LASKE EROTTUVUUSPISTEET ===
    differentiation_scores = _calculate_differentiation_scores(comparison_matrix)
    
    return {
        # Siirrä comparison_matrix sisältö SUORAAN ylätasolle
        'messaging': comparison_matrix['messaging'],
        'content_strategy': comparison_matrix['content_strategy'],
        'technical_execution': comparison_matrix['technical_execution'],
        'social_engagement': comparison_matrix['social_engagement'],
        'ai_insights': comparison_matrix.get('ai_insights'),
        
        # Metadata-kentät
        'differentiation_scores': differentiation_scores,
        'your_unique_strengths': _identify_unique_strengths(your_summary, comp_summaries, comparison_matrix),
        'shared_weaknesses': _identify_shared_weaknesses([your_summary] + comp_summaries),
        'competitive_advantages': _identify_competitive_advantages(comparison_matrix, differentiation_scores)
    }

def _compare_messaging(your: Dict, competitors: List[Dict]) -> Dict[str, Any]:
    """Vertaile viestintästrategioita"""
    
    your_title_len = len(your['messaging']['title'])
    your_desc_len = len(your['messaging']['meta_description'])
    your_tone = your['messaging']['tone']
    
    comp_title_lens = [len(c['messaging']['title']) for c in competitors]
    comp_desc_lens = [len(c['messaging']['meta_description']) for c in competitors]
    comp_tones = [c['messaging']['tone'] for c in competitors]
    
    return {
        'your_position': {
            'title_length': your_title_len,
            'description_length': your_desc_len,
            'tone': your_tone,
            'h1_optimization': 'Good' if your['messaging']['h1_count'] == 1 else 'Needs improvement'
        },
        'vs_competitors': {
            'title_comparison': 'Longer' if your_title_len > (sum(comp_title_lens) / len(comp_title_lens)) else 'Shorter',
            'description_comparison': 'More detailed' if your_desc_len > (sum(comp_desc_lens) / len(comp_desc_lens)) else 'Less detailed',
            'tone_differentiation': 'Unique tone' if your_tone not in comp_tones else 'Similar to competitors'
        },
        'insight': _generate_messaging_insight(your, competitors)
    }

def _generate_messaging_insight(your: Dict, competitors: List[Dict]) -> str:
    """Generoi käytännöllinen insight viestinnästä"""
    your_desc = your['messaging']['meta_description']
    comp_descs = [c['messaging']['meta_description'] for c in competitors]
    
    # Tarkista onko value proposition selkeä
    value_words = ['help', 'solution', 'best', 'leading', 'professional', 'expert', 'quality']
    
    your_value_count = sum(1 for word in value_words if word in your_desc.lower())
    avg_comp_value = sum(sum(1 for word in value_words if word in desc.lower()) for desc in comp_descs) / max(1, len(comp_descs))
    
    if your_value_count < avg_comp_value:
        return "⚠️ Arvolupauksesi on vähemmän selkeä kuin kilpailijoiden. Korosta konkreettista hyötyä meta-kuvauksessa."
    elif your_value_count > avg_comp_value:
        return "✅ Arvolupauksesi on selkeämmin esillä kuin kilpailijoilla. Hyvä erottuvuus!"
    else:
        return "➡️ Arvolupauksesi on samalla tasolla kilpailijoiden kanssa. Harkitse voimakkaampaa erottautumista."

def _compare_content_strategy(your: Dict, competitors: List[Dict]) -> Dict[str, Any]:
    """Vertaile sisältöstrategioita"""
    
    your_wc = your['content_strategy']['word_count']
    comp_wcs = [c['content_strategy']['word_count'] for c in competitors]
    avg_comp_wc = sum(comp_wcs) / len(comp_wcs) if comp_wcs else 0
    
    your_has_blog = your['content_strategy']['has_blog']
    comp_blog_count = sum(1 for c in competitors if c['content_strategy']['has_blog'])
    
    return {
        'content_depth_ranking': _rank_position(your_wc, comp_wcs),
        'blog_strategy': {
            'you_have_blog': your_has_blog,
            'competitors_with_blog': comp_blog_count,
            'total_competitors': len(competitors)
        },
        'content_gap': your_wc - avg_comp_wc,
        'media_richness_score': your['content_strategy']['media_richness'],
        'interactivity_score': your['content_strategy']['interactive_elements'],
        'strategic_insight': _generate_content_insight(
            your_wc, 
            avg_comp_wc, 
            your_has_blog, 
            comp_blog_count,
            len(competitors)
        )
    }

def _generate_content_insight(
    your_wc: int, 
    avg_comp_wc: float, 
    your_blog: bool, 
    comp_blogs: int,
    total_competitors: int
) -> str:
    """Generoi strateginen sisältö-insight"""
    insights = []
    
    # Suojaus division by zero
    if avg_comp_wc > 0:
        if your_wc < avg_comp_wc * 0.7:
            percentage = int((1 - your_wc/avg_comp_wc)*100)
            insights.append(f"🚨 KRIITTINEN: Sisältösi on {percentage}% vähemmän kuin kilpailijoiden keskiarvo. Tämä heikentää SEO-sijoituksiasi ja auktoriteettia.")
        elif your_wc < avg_comp_wc:
            percentage = int((1 - your_wc/avg_comp_wc)*100)
            insights.append(f"⚠️ Sisältösi on hieman kilpailijoita vähäisempää (-{percentage}%). Harkitse sisällön laajentamista.")
        elif your_wc > avg_comp_wc * 1.5:
            percentage = int((your_wc/avg_comp_wc - 1)*100)
            insights.append(f"🌟 VAHVUUS: Sisältösi on {percentage}% runsaampaa kuin kilpailijoiden. Tämä rakentaa auktoriteettia.")
    
    if total_competitors > 0:
        if not your_blog and comp_blogs >= total_competitors // 2:
            insights.append(f"📝 MAHDOLLISUUS: {comp_blogs}/{total_competitors} kilpailijaa julkaisee blogia, mutta sinulla ei ole. Blogistrategia voisi tuoda merkittävää etua.")
        elif your_blog and comp_blogs < total_competitors // 2:
            insights.append(f"✅ EROTTUVUUS: Sinulla on blogi, mutta vain {comp_blogs}/{total_competitors} kilpailijalla. Hyödynnä tätä etua aktiivisella julkaisemisella.")
    
    return " ".join(insights) if insights else "➡️ Sisältöstrategiasi on linjassa kilpailijoiden kanssa."

def _compare_technical(your: Dict, competitors: List[Dict]) -> Dict[str, Any]:
    """Vertaile teknistä toteutusta"""
    
    your_tech = your['technical_maturity']
    
    # Laske kilpailijoiden keskiarvot
    comp_speeds = [c['technical_maturity']['page_speed_score'] for c in competitors]
    comp_modernities = [c['technical_maturity']['modernity_score'] for c in competitors]
    
    ssl_count = sum(1 for c in competitors if c['technical_maturity']['has_ssl'])
    analytics_count = sum(1 for c in competitors if c['technical_maturity']['has_analytics'])
    mobile_count = sum(1 for c in competitors if c['technical_maturity']['mobile_optimization'])
    spa_count = sum(1 for c in competitors if c['technical_maturity']['spa_detected'])
    
    return {
        'speed_ranking': _rank_position(your_tech['page_speed_score'], comp_speeds),
        'modernity_ranking': _rank_position(your_tech['modernity_score'], comp_modernities),
        'foundational_features': {
            'ssl': {'you': your_tech['has_ssl'], 'competitors': f"{ssl_count}/{len(competitors)}"},
            'analytics': {'you': your_tech['has_analytics'], 'competitors': f"{analytics_count}/{len(competitors)}"},
            'mobile': {'you': your_tech['mobile_optimization'], 'competitors': f"{mobile_count}/{len(competitors)}"}
        },
        'advanced_features': {
            'spa_framework': {'you': your_tech['spa_detected'], 'competitors': f"{spa_count}/{len(competitors)}"}
        },
        'technical_gap_analysis': _generate_technical_gaps(your_tech, competitors)
    }

def _generate_technical_gaps(your_tech: Dict, competitors: List[Dict]) -> List[str]:
    """Tunnista tekniset puutteet"""
    gaps = []
    
    if not your_tech['has_ssl']:
        gaps.append("🚨 KRIITTINEN: Ei SSL-sertifikaattia. Tämä estää Google-sijoitukset ja heikentää luottamusta.")
    
    if not your_tech['has_analytics']:
        gaps.append("📊 Ei analytiikkaa. Et voi mitata tuloksia etkä optimoida.")
    
    if not your_tech['mobile_optimization']:
        gaps.append("📱 Ei mobiilioptimointia. 60%+ käyttäjistä tulee mobiililla.")
    
    if your_tech['page_speed_score'] < 50:
        gaps.append(f"🐌 Hidas sivulataus ({your_tech['page_speed_score']}/100). Joka sekunti maksaa 7% konversioista.")
    
    # Vertaile kilpailijoihin
    comp_speeds = [c['technical_maturity']['page_speed_score'] for c in competitors]
    avg_speed = sum(comp_speeds) / len(comp_speeds) if comp_speeds else 0
    
    if your_tech['page_speed_score'] < avg_speed * 0.8:
        gaps.append(f"⚠️ Sivusi on {int((1 - your_tech['page_speed_score']/avg_speed)*100)}% hitaampi kuin kilpailijoiden keskiarvo.")
    
    return gaps if gaps else ["✅ Tekninen toteutus on hyvällä tasolla"]

def _compare_social(your: Dict, competitors: List[Dict]) -> Dict[str, Any]:
    """Vertaile sosiaalista läsnäoloa"""
    
    your_social = your['social_presence']
    your_platforms = set(your_social['platforms'])
    
    # Analysoi kilpailijoiden alustat
    all_comp_platforms = []
    for c in competitors:
        all_comp_platforms.extend(c['social_presence']['platforms'])
    
    common_platforms = set(p for p in all_comp_platforms if all_comp_platforms.count(p) >= len(competitors) // 2)
    your_missing_platforms = common_platforms - your_platforms
    your_unique_platforms = your_platforms - common_platforms
    
    return {
        'platform_coverage': {
            'your_platforms': list(your_platforms),
            'missing_common_platforms': list(your_missing_platforms),
            'unique_platforms': list(your_unique_platforms),
            'coverage_percentage': int((len(your_platforms) / max(1, len(common_platforms))) * 100)
        },
        'social_maturity': {
            'has_og_tags': your_social['og_tags'] > 0,
            'has_sharing_buttons': your_social['has_sharing']
        },
        'strategic_insight': _generate_social_insight(your_platforms, your_missing_platforms, common_platforms)
    }

def _generate_social_insight(your_platforms: set, missing: set, common: set) -> str:
    """Generoi sosiaalinen strategia-insight"""
    if len(missing) >= 2:
        missing_str = ', '.join(list(missing)[:2])
        return f"🎯 MAHDOLLISUUS: Kilpailijasi käyttävät {missing_str}, mutta sinä et. Nämä kanavat voivat tuoda lisää näkyvyyttä."
    elif len(your_platforms) > len(common):
        return "✅ Olet aktiivinen useammalla alustalla kuin kilpailijat. Varmista että hallitset kaikki kanavat laadukkaasti."
    elif len(your_platforms) == 0:
        return "🚨 Ei sosiaalista läsnäoloa. Tämä rajoittaa merkittävästi löydettävyyttäsi ja luotettavuuttasi."
    else:
        return "➡️ Sosiaalinen läsnäolosi on linjassa kilpailijoiden kanssa."

def _rank_position(your_value: float, competitor_values: List[float]) -> Dict[str, Any]:
    """Laske ranking-positio"""
    all_values = [your_value] + competitor_values
    sorted_values = sorted(all_values, reverse=True)
    
    position = sorted_values.index(your_value) + 1
    total = len(all_values)
    percentile = int(((total - position) / total) * 100)
    
    return {
        'rank': position,
        'total': total,
        'percentile': percentile,
        'status': 'Leading' if position == 1 else 'Above average' if position <= total // 2 else 'Below average'
    }

async def _get_ai_differentiation_insights(
    your_summary: Dict,
    comp_summaries: List[Dict],
    comparison_matrix: Dict,
    language: str,
    industry_context: Optional[str]
) -> Dict[str, Any]:
    """Pyydä AI:lta syvällisiä erottuvuus-insighteja"""
    
    prompt_lang = "fi" if language == "fi" else "en"
    
    # Rakenna kontekstuaalinen prompt
    industry_str = f"Toimiala: {industry_context}\n" if industry_context else ""
    
    if prompt_lang == "fi":
        prompt = f"""{industry_str}
Analysoi syvällisesti näiden yritysten erottuvuus ja kilpailuasema:

OMAN YRITYKSEN PROFIILI:
- Nimi: {your_summary['company']}
- Pisteet: {your_summary['score']}/100
- Sisältö: {your_summary['content_strategy']['word_count']} sanaa, syvyys: {your_summary['content_strategy']['content_depth']}
- Viestintä: {your_summary['messaging']['title'][:80]}
- Tekninen: Nopeus {your_summary['technical_maturity']['page_speed_score']}/100, Modernius {your_summary['technical_maturity']['modernity_score']}/100
- Vahvuudet: {', '.join(your_summary['key_strengths'])}
- Heikkoudet: {', '.join(your_summary['key_weaknesses'])}

KILPAILIJAT ({len(comp_summaries)} kpl):
{chr(10).join([f"- {c['company']}: {c['score']}/100p | Sisältö: {c['content_strategy']['word_count']} sanaa | Vahvuudet: {', '.join(c['key_strengths'][:2])}" for c in comp_summaries])}

DATAPOHJAISET LÖYDÖKSET:
- Viestintä: {comparison_matrix['messaging']['insight']}
- Sisältöstrategia: {comparison_matrix['content_strategy']['strategic_insight']}
- Tekninen: {', '.join(comparison_matrix['technical_execution']['technical_gap_analysis'][:2])}

Vastaa JSON-muodossa:
{{{{
  "positioning_summary": "Yksi virke joka kuvaa kilpailuaseman",
  "unique_selling_points": ["2-3 konkreettista USP:tä jotka erottavat kilpailijoista"],
  "target_customer_profile": "Kenelle tämä yritys TODELLA puhuu (tarkka kuvaus)",
  "messaging_strategy": "Miten viestintä eroaa kilpailijoista",
  "immediate_opportunities": ["3 nopeaa taktiikkaa joilla voi ohittaa kilpailijoita"],
  "strategic_vulnerabilities": ["2 isoa riskiä/heikkoutta verrattuna kilpailijoihin"],
  "12_month_roadmap": ["3-5 strategista askelta jotka muuttavat kilpailuasetelmaa"]
}}}}
"""
    else:
        prompt = f"""{industry_str}
Deep competitive analysis of these companies:

YOUR COMPANY PROFILE:
- Name: {your_summary['company']}
- Score: {your_summary['score']}/100
- Content: {your_summary['content_strategy']['word_count']} words, depth: {your_summary['content_strategy']['content_depth']}
- Messaging: {your_summary['messaging']['title'][:80]}
- Technical: Speed {your_summary['technical_maturity']['page_speed_score']}/100, Modernity {your_summary['technical_maturity']['modernity_score']}/100
- Strengths: {', '.join(your_summary['key_strengths'])}
- Weaknesses: {', '.join(your_summary['key_weaknesses'])}

COMPETITORS ({len(comp_summaries)} total):
{chr(10).join([f"- {c['company']}: {c['score']}/100 | Content: {c['content_strategy']['word_count']} words | Strengths: {', '.join(c['key_strengths'][:2])}" for c in comp_summaries])}

DATA INSIGHTS:
- Messaging: {comparison_matrix['messaging']['insight']}
- Content: {comparison_matrix['content_strategy']['strategic_insight']}
- Technical: {', '.join(comparison_matrix['technical_execution']['technical_gap_analysis'][:2])}

Respond in JSON:
{{{{
  "positioning_summary": "One sentence describing competitive position",
  "unique_selling_points": ["2-3 concrete USPs that differentiate from competitors"],
  "target_customer_profile": "Who this company REALLY speaks to (precise description)",
  "messaging_strategy": "How messaging differs from competitors",
  "immediate_opportunities": ["3 quick tactics to outmaneuver competitors"],
  "strategic_vulnerabilities": ["2 major risks/weaknesses vs competitors"],
  "12_month_roadmap": ["3-5 strategic steps that change competitive landscape"]
}}}}
"""
    
    response = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.4,  # Hieman korkeampi creativity mutta silti fokus
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def _calculate_differentiation_scores(comparison_matrix: Dict) -> Dict[str, int]:
    """Laske numeerinen erottuvuuspistemäärä eri alueilla"""
    
    scores = {}
    
    # Viestintä (0-100)
    msg = comparison_matrix['messaging']
    msg_score = 50  # Base
    if 'Unique tone' in msg['vs_competitors'].get('tone_differentiation', ''):
        msg_score += 25
    if 'More detailed' in msg['vs_competitors'].get('description_comparison', ''):
        msg_score += 15
    if msg['your_position']['h1_optimization'] == 'Good':
        msg_score += 10
    scores['messaging'] = min(100, msg_score)
    
    # Sisältö (0-100)
    content = comparison_matrix['content_strategy']
    content_score = 40  # Base
    if content['content_gap'] > 1000:
        content_score += 30
    elif content['content_gap'] > 500:
        content_score += 15
    if content['blog_strategy']['you_have_blog'] and content['blog_strategy']['competitors_with_blog'] < content['blog_strategy']['total_competitors'] // 2:
        content_score += 20
    scores['content'] = min(100, content_score)
    
    # Tekninen (0-100)
    tech = comparison_matrix['technical_execution']
    tech_score = tech['speed_ranking']['percentile']
    if all(tech['foundational_features'][f]['you'] for f in ['ssl', 'analytics', 'mobile']):
        tech_score = min(100, tech_score + 15)
    scores['technical'] = tech_score
    
    
    # Sosiaalinen (0-100)
    social = comparison_matrix['social_engagement']
    social_score = social['platform_coverage']['coverage_percentage']

    # Lisää bonukset OG-tageista ja sharing-napeista
    if social['social_maturity']['has_og_tags']:
        social_score += 10
    if social['social_maturity']['has_sharing_buttons']:
        social_score += 10

    # ✅ KRIITTINEN: Rajaa AINA 0-100
    scores['social'] = min(100, max(0, social_score))

    # Kokonais-erottuvuus
    scores['overall'] = int(sum(scores.values()) / len(scores))

    return scores

def _identify_unique_strengths(your: Dict, competitors: List[Dict], matrix: Dict) -> List[str]:
    """Tunnista ainutlaatuiset vahvuudet"""
    strengths = []
    
    # Sisältö
    if your['content_strategy']['word_count'] > max(c['content_strategy']['word_count'] for c in competitors):
        strengths.append(f"💎 Runsain sisältö: {your['content_strategy']['word_count']} sanaa vs. kilpailijoiden max {max(c['content_strategy']['word_count'] for c in competitors)}")
    
    # Blogi
    if your['content_strategy']['has_blog'] and sum(1 for c in competitors if c['content_strategy']['has_blog']) == 0:
        strengths.append("💎 Ainoa jolla on aktiivinen blogi - vahva SEO-etu")
    
    # Tekninen
    if your['technical_maturity']['page_speed_score'] > max(c['technical_maturity']['page_speed_score'] for c in competitors):
        strengths.append(f"💎 Nopein sivulataus: {your['technical_maturity']['page_speed_score']}/100")
    
    # Modernit teknologiat
    if your['technical_maturity']['spa_detected'] and sum(1 for c in competitors if c['technical_maturity']['spa_detected']) == 0:
        strengths.append("💎 Ainoa moderni SPA-arkkitehtuuri - teknologinen edelläkävijä")
    
    # Jos AI-insightit saatavilla
    if matrix.get('ai_insights') and matrix['ai_insights'].get('unique_selling_points'):
        strengths.extend([f"💎 {usp}" for usp in matrix['ai_insights']['unique_selling_points'][:2]])
    
    return strengths[:5] if strengths else ["Ei selkeitä ainutlaatuisia vahvuuksia tunnistettu"]

def _identify_shared_weaknesses(all_summaries: List[Dict]) -> List[str]:
    """Tunnista kaikille yhteiset heikkoudet = markkinan aukot"""
    
    # Laske kuinka yleisiä eri puutteet ovat
    total = len(all_summaries)
    
    # Teknisten puutteiden yleisyys
    no_ssl_count = sum(1 for s in all_summaries if not s['technical_maturity']['has_ssl'])
    no_analytics_count = sum(1 for s in all_summaries if not s['technical_maturity']['has_analytics'])
    no_mobile_count = sum(1 for s in all_summaries if not s['technical_maturity']['mobile_optimization'])
    slow_speed_count = sum(1 for s in all_summaries if s['technical_maturity']['page_speed_score'] < 60)
    
    # Sisältöpuutteet
    thin_content_count = sum(1 for s in all_summaries if s['content_strategy']['word_count'] < 1000)
    no_blog_count = sum(1 for s in all_summaries if not s['content_strategy']['has_blog'])
    
    # Sosiaaliset puutteet
    limited_social_count = sum(1 for s in all_summaries if s['social_presence']['platform_count'] < 3)
    
    shared = []
    threshold = total * 0.6  # 60% tai enemmän = yleinen puute
    
    if no_ssl_count >= threshold:
        shared.append(f"🚨 SSL puuttuu {int(no_ssl_count/total*100)}% yrityksistä")
    if no_analytics_count >= threshold:
        shared.append(f"📊 Analytiikka puuttuu {int(no_analytics_count/total*100)}% yrityksistä")
    if no_mobile_count >= threshold:
        shared.append(f"📱 Mobiilioptimo inti puuttuu {int(no_mobile_count/total*100)}% yrityksistä")
    if slow_speed_count >= threshold:
        shared.append(f"🐌 Hidas lataus {int(slow_speed_count/total*100)}% yrityksistä")
    if thin_content_count >= threshold:
        shared.append(f"📝 Ohut sisältö (<1000 sanaa) {int(thin_content_count/total*100)}% yrityksistä")
    if no_blog_count >= threshold:
        shared.append(f"✍️ Ei blogia {int(no_blog_count/total*100)}% yrityksistä")
    if limited_social_count >= threshold:
        shared.append(f"👥 Rajoitettu sosiaalinen läsnäolo {int(limited_social_count/total*100)}% yrityksistä")
    
    return shared if shared else ["Alan perusasiat ovat hyvällä tasolla kaikilla"]

def _identify_competitive_advantages(matrix: Dict, scores: Dict) -> List[str]:
    """Tunnista konkreettiset kilpailuedut"""
    advantages = []
    
    # Erottuvuuspisteiden perusteella
    if scores['messaging'] >= 75:
        advantages.append("🎯 Viestinnällinen etu: Selkeämpi ja erottuvampi arvolupauksesi")
    
    if scores['content'] >= 75:
        advantages.append("📚 Sisältöetu: Syvempi ja kattavampi tietovaranto houkuttelee asiakkaita")
    
    if scores['technical'] >= 75:
        advantages.append("⚡ Tekninen etu: Nopeampi ja modernimpi toteutus parantaa konversiota")
    
    if scores['social'] >= 75:
        advantages.append("🌐 Sosiaalinen etu: Laajempi läsnäolo lisää löydettävyyttä ja luottamusta")
    
    # AI-insightit
    if matrix.get('ai_insights'):
        ai = matrix['ai_insights']
        if ai.get('positioning_summary'):
            advantages.append(f"💡 Asemointi: {ai['positioning_summary']}")
        if ai.get('messaging_strategy'):
            advantages.append(f"💬 Viestintästrategia: {ai['messaging_strategy']}")
    
    return advantages if advantages else ["Kilpailuedut eivät ole selkeästi näkyviä - keskity erottautumiseen"]

async def _discover_real_market_gaps(
    your_analysis: Dict[str, Any],
    competitor_analyses: List[Dict[str, Any]],
    language: str
) -> List[Dict[str, Any]]:
    """
    Etsi TODELLISET markkinaaukot - ei yleisiä heikkouksia vaan
    asiakkaiden tarpeita joihin kukaan ei vastaa.
    """
    
    all_summaries = [_extract_detailed_summary(your_analysis)] + [_extract_detailed_summary(c) for c in competitor_analyses]
    
    # === 1. TEKNOLOGISET AUKOT ===
    tech_gaps = _find_technical_market_gaps(all_summaries)
    
    # === 2. SISÄLTÖAUKOT ===
    content_gaps = _find_content_market_gaps(all_summaries)
    
    # === 3. PALVELUAUKOT (AI-POHJAINEN) ===
    service_gaps = []
    if openai_client:
        try:
            service_gaps = await _find_service_gaps_with_ai(all_summaries, language)
        except Exception as e:
            logger.error(f"AI service gaps failed: {e}")
    
    # Yhdistä ja priorisoi
    all_gaps = tech_gaps + content_gaps + service_gaps
    
    # Pistey tä aukot vaikutuksen ja toteuttamisen helppouden mukaan
    for gap in all_gaps:
        gap['priority_score'] = _calculate_gap_priority(gap)
    
    # Järjestä prioriteetin mukaan
    all_gaps.sort(key=lambda x: x['priority_score'], reverse=True)
    
    return all_gaps[:7]  # Top 7 markkina-aukkoa

def _find_technical_market_gaps(summaries: List[Dict]) -> List[Dict[str, Any]]:
    """Tunnista teknologiset markkinaaukot"""
    gaps = []
    
    total = len(summaries)
    
    # Laske puutteet
    has_modern_tech = sum(1 for s in summaries if s['technical_maturity']['modernity_score'] >= 60)
    has_fast_speed = sum(1 for s in summaries if s['technical_maturity']['page_speed_score'] >= 70)
    has_mobile = sum(1 for s in summaries if s['technical_maturity']['mobile_optimization'])
    
    # Jos vähemmän kuin 50% täyttää kriteerin = aukko
    if has_modern_tech < total * 0.5:
        gaps.append({
            'type': 'technology',
            'gap_title': 'Modernit web-teknologiat puuttuvat alalta',
            'description': f'{int((total - has_modern_tech)/total*100)}% yrityksistä käyttää vanhentuneita teknologioita',
            'opportunity': 'Modernilla SPA-arkkitehtuurilla ja PWA-ominaisuuksilla voit erottua ja tarjota paremman käyttökokemuksen',
            'impact': 'high',
            'effort': 'medium',
            'estimated_advantage': '+15-25 pistettä kilpailijoihin nähden'
        })
    
    if has_fast_speed < total * 0.5:
        gaps.append({
            'type': 'performance',
            'gap_title': 'Hitaat latausajat yleisiä alalla',
            'description': f'{int((total - has_fast_speed)/total*100)}% yrityksistä on hidas (<70 pistettä)',
            'opportunity': 'Optimoimalla sivun nopeuden alle 2 sekuntiin voit parantaa konversiota 20-30%',
            'impact': 'high',
            'effort': 'low',
            'estimated_advantage': 'Joka sekunti nopeampi = 7% parempi konversio'
        })
    
    if has_mobile < total * 0.7:
        gaps.append({
            'type': 'mobile',
            'gap_title': 'Mobiilikokemus heikko alalla',
            'description': f'{int((total - has_mobile)/total*100)}% yrityksistä ei ole optimoitu mobiilille kunnolla',
            'opportunity': '60%+ liikenteet tulee mobiililla - responsiivisella designilla tavoitat enemmän asiakkaita',
            'impact': 'critical',
            'effort': 'medium',
            'estimated_advantage': 'Tavoita 40-60% enemmän potentiaalisia asiakkaita'
        })
    
    return gaps

def _find_content_market_gaps(summaries: List[Dict]) -> List[Dict[str, Any]]:
    """Tunnista sisältöaukot"""
    gaps = []
    
    total = len(summaries)
    
    # Analysoi sisältöstrategioita
    has_blog = sum(1 for s in summaries if s['content_strategy']['has_blog'])
    has_deep_content = sum(1 for s in summaries if s['content_strategy']['word_count'] >= 2000)
    has_media = sum(1 for s in summaries if s['content_strategy']['media_richness'] >= 2)
    
    if has_blog < total * 0.4:
        gaps.append({
            'type': 'content_marketing',
            'gap_title': 'Vain harva yritys julkaisee sisältöä säännöllisesti',
            'description': f'Vain {int(has_blog/total*100)}% yrityksistä on aktiivinen blogi',  # ✅ KORJATTU
            'opportunity': 'Sisältömarkkinoinnilla voit kasvattaa orgaanista liikennettä 200-400% vuodessa',
            'impact': 'high',
            'effort': 'high',
            'estimated_advantage': '4-6 laadukasta artikkelia/kk = 50-100 uutta kävijää/kk'
        })
    
    if has_deep_content < total * 0.3:
        gaps.append({
            'type': 'thought_leadership',
            'gap_title': 'Alan thought leadership -sisältö puuttuu',
            'description': f'Vain {int(has_deep_content/total*100)}% yrityksistä julkaisee syvällistä asiantuntijasisältöä',  # ✅ Tämä on oikein
            'opportunity': 'Pitkät, kattavat oppaat (2000+ sanaa) rakentavat auktoriteettia ja dominoivat hakutuloksia',
            'impact': 'high',
            'effort': 'medium',
            'estimated_advantage': '1 kattava opas voi tuoda 100-500 kävijää/kk vuosia'
        })
    
    if has_media < total * 0.5:
        gaps.append({
            'type': 'multimedia',
            'gap_title': 'Multimedia-sisältö on harvinaista',
            'description': f'{int((total - has_media)/total*100)}% yrityksistä käyttää vain tekstiä',
            'opportunity': 'Videot, infografiikat ja interaktiiviset elementit lisäävät sitoutumista 3-5x',
            'impact': 'medium',
            'effort': 'medium',
            'estimated_advantage': 'Video lisää konversiota 80% ja aikaa sivulla 2-3x'
        })
    
    return gaps

async def _find_service_gaps_with_ai(summaries: List[Dict], language: str) -> List[Dict[str, Any]]:
    """Käytä AI:ta tunnistamaan palvelu- ja liiketoimintaaukot"""
    
    # Rakenna yhteenveto kaikista yrityksistä
    companies_summary = "\n".join([
        f"- {s['company']}: Pisteet {s['score']}/100, Sisältö: {s['content_strategy']['content_depth']}, "
        f"Vahvuudet: {', '.join(s['key_strengths'][:2])}, Heikkoudet: {', '.join(s['key_weaknesses'][:2])}"
        for s in summaries
    ])
    
    prompt_lang = "fi" if language == "fi" else "en"
    
    if prompt_lang == "fi":
        prompt = f"""Analysoi näiden {len(summaries)} yrityksen perusteella, mitä ASIAKKAAT kaipaavat mutta kukaan ei tarjoa:

{companies_summary}

Etsi TODELLISIA markkinaaukkoja - ei yleisiä puutteita vaan konkreettisia asiakastarte ita joita kukaan ei täytä.

Vastaa JSON-muodossa (max 3 aukkoa):
{{{{
  "gaps": [
    {{{{
      "gap_title": "Lyhyt otsikko aukosta",
      "customer_pain_point": "Mikä ongelma asiakkaalla on",
      "why_unfulfilled": "Miksi kukaan ei vastaa tähän",
      "opportunity": "Miten tähän voi vastata",
      "revenue_potential": "Arvio liikevaih tovaikutuksesta",
      "competitive_moat": "Miten tämä suojaa kilpailijoilta"
    }}}}
  ]
}}}}
"""
    else:
        prompt = f"""Analyze these {len(summaries)} companies to find what CUSTOMERS need but nobody provides:

{companies_summary}

Find REAL market gaps - not generic weaknesses but concrete customer needs nobody fulfills.

Respond in JSON (max 3 gaps):
{{{{
  "gaps": [
    {{{{
      "gap_title": "Short gap title",
      "customer_pain_point": "What problem does customer have",
      "why_unfulfilled": "Why nobody addresses this",
      "opportunity": "How to address this",
      "revenue_potential": "Estimated revenue impact",
      "competitive_moat": "How this protects from competitors"
    }}}}
  ]
}}}}
"""
    
    response = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.6,
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Muotoile AI:n löydökset yhtenäiseen muotoon
    formatted_gaps = []
    for gap in result.get('gaps', []):
        formatted_gaps.append({
            'type': 'service_innovation',
            'gap_title': gap['gap_title'],
            'description': gap['customer_pain_point'],
            'opportunity': gap['opportunity'],
            'impact': 'high',
            'effort': 'high',
            'estimated_advantage': gap.get('revenue_potential', 'Merkittävä liikevaihtomahdollisuus'),
            'competitive_moat': gap.get('competitive_moat', ''),
            'why_gap_exists': gap.get('why_unfulfilled', '')
        })
    
    return formatted_gaps

def _calculate_gap_priority(gap: Dict) -> int:
    """Laske aukon prioriteettipistemäärä"""
    score = 0
    
    # Vaikutus
    impact_scores = {'critical': 40, 'high': 30, 'medium': 20, 'low': 10}
    score += impact_scores.get(gap.get('impact', 'medium'), 20)
    
    # Toteutettavuus (käänteinen - helpompi = parempi)
    effort_scores = {'low': 30, 'medium': 20, 'high': 10}
    score += effort_scores.get(gap.get('effort', 'medium'), 20)
    
    # Tyyppikohtainen bonus
    type_scores = {
        'performance': 15,  # Nopea toteuttaa, suuri vaikutus
        'mobile': 15,
        'content_marketing': 10,
        'service_innovation': 25  # AI löysi - todennäköisesti arvokas
    }
    score += type_scores.get(gap.get('type', ''), 0)
    
    return score

async def _calculate_market_positioning(
    your_analysis: Dict[str, Any],
    competitor_analyses: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Laske kilpailullinen asemointi (positioning map)"""
    
    your_summary = _extract_detailed_summary(your_analysis)
    comp_summaries = [_extract_detailed_summary(c) for c in competitor_analyses]
    all_summaries = [your_summary] + comp_summaries
    
    # Laske kaksi pääakselia: Digitaalinen kypsyys vs. Sisällön syvyys
    scores = []
    for s in all_summaries:
        scores.append({
            'company': s['company'],
            'is_you': s['company'] == your_summary['company'],
            'digital_maturity': s['score'],
            'content_depth_score': min(100, (s['content_strategy']['word_count'] / 50)),  # 5000 sanaa = 100p
            'technical_score': s['technical_maturity']['page_speed_score'],
            'social_score': s['social_presence']['platform_count'] * 20  # 5 alustaa = 100p
        })
    
    # Laske keskiarvot
    avg_maturity = sum(s['digital_maturity'] for s in scores) / len(scores)
    avg_content = sum(s['content_depth_score'] for s in scores) / len(scores)
    
    # Määritä kvadrantit
    your_score = [s for s in scores if s['is_you']][0]
    
    if your_score['digital_maturity'] >= avg_maturity and your_score['content_depth_score'] >= avg_content:
        quadrant = "Leader"
        quadrant_desc = "Vahva digitaalinen toteutus JA syvä sisältö - alan johtaja"
    elif your_score['digital_maturity'] >= avg_maturity and your_score['content_depth_score'] < avg_content:
        quadrant = "Technical Leader"
        quadrant_desc = "Teknisesti edistyksellinen mutta sisältö ohut - parempi sisältöstrategia tarvitaan"
    elif your_score['digital_maturity'] < avg_maturity and your_score['content_depth_score'] >= avg_content:
        quadrant = "Content Leader"
        quadrant_desc = "Vahva sisältö mutta tekniikka jäljessä - tekninen päivitys tarvitaan"
    else:
        quadrant = "Challenger"
        quadrant_desc = "Sekä tekniikka että sisältö jäljessä - suuri kehityspotentiaali"
    
    # Laske kilpailullinen pisteys
    your_overall = your_score['digital_maturity']
    comp_avg = sum(s['digital_maturity'] for s in scores if not s['is_you']) / len([s for s in scores if not s['is_you']])
    
    competitive_score = int((your_overall / max(1, comp_avg)) * 50)
    competitive_score = max(0, min(100, competitive_score))
    
    return {
        'competitive_score': competitive_score,
        'positioning_quadrant': quadrant,
        'quadrant_description': quadrant_desc,
        'positioning_coordinates': {
            'x_digital_maturity': your_score['digital_maturity'],
            'y_content_depth': your_score['content_depth_score']
        },
        'market_averages': {
            'digital_maturity': int(avg_maturity),
            'content_depth': int(avg_content)
        },
        'all_companies': scores,
        'competitive_distance': {
            'from_leader': max(s['digital_maturity'] for s in scores) - your_overall,
            'from_average': your_overall - comp_avg
        }
    }

async def _generate_strategic_recommendations(
    your_analysis: Dict[str, Any],
    competitor_analyses: List[Dict[str, Any]],
    differentiation_matrix: Dict[str, Any],
    market_gaps: List[Dict[str, Any]],
    language: str
) -> List[Dict[str, Any]]:
    """Generoi strategiset suositukset kilpailullisen aseman parantamiseen"""
    
    recommendations = []
    
    # === 1. NOPEAT VOITOT (Quick Wins) ===
    quick_wins = _identify_quick_wins(differentiation_matrix, market_gaps)
    recommendations.extend(quick_wins)
    
    # === 2. STRATEGISET MUUTOKSET (Strategic Moves) ===
    if openai_client:
        try:
            strategic_moves = await _get_ai_strategic_recommendations(
                your_analysis,
                competitor_analyses,
                differentiation_matrix,
                market_gaps,
                language
            )
            recommendations.extend(strategic_moves)
        except Exception as e:
            logger.error(f"AI strategic recommendations failed: {e}")
    
    # === 3. PITKÄN TÄHTÄIMEN INVESTOINNIT ===
    long_term = _identify_long_term_investments(market_gaps)
    recommendations.extend(long_term)
    
    # Priorisoi ja rajoita määrää
    for r in recommendations:
        r['priority_score'] = _calculate_recommendation_priority(r)
    
    recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
    
    return recommendations[:8]

def _identify_quick_wins(matrix: Dict, gaps: List[Dict]) -> List[Dict[str, Any]]:
    """Tunnista nopeat voitot"""
    quick_wins = []
    
    # 🚨 HOTFIX: Tarkista rakenne
    comparison = matrix.get('comparison_matrix', matrix)
    
    # Teknisistä puutteista
    tech_gaps = comparison.get('technical_execution', {}).get('technical_gap_analysis', [])
    for gap in tech_gaps:
        if 'KRIITTINEN' in gap or 'SSL' in gap:
            quick_wins.append({
                'title': 'Asenna SSL-sertifikaatti HETI',
                'rationale': 'Kriittinen puute joka estää Google-sijoitukset',
                'timeframe': '1-2 päivää',
                'effort': 'low',
                'impact': 'critical',
                'cost_estimate': '0-50€/vuosi',
                'expected_result': '+10-15 pistettä, paremmat sijoitukset'
            })
        elif 'analytiikka' in gap.lower():
            quick_wins.append({
                'title': 'Asenna Google Analytics 4',
                'rationale': 'Et voi optimoida mitä et mittaa',
                'timeframe': '2-4 tuntia',
                'effort': 'low',
                'impact': 'high',
                'cost_estimate': '0€',
                'expected_result': 'Mittauspohja optimoinnille'
            })
    
    # Sisältöaukoista
    content_insight = comparison.get('content_strategy', {}).get('strategic_insight', '')
    if 'KRIITTINEN' in content_insight:
        quick_wins.append({
            'title': 'Kirjoita 3 pilariartikkelia',
            'rationale': 'Sisältösi on liian ohut kilpailijoihin nähden',
            'timeframe': '2-3 viikkoa',
            'effort': 'medium',
            'impact': 'high',
            'cost_estimate': '0-500€ (jos ulkoistetaan)',
            'expected_result': '+1000-2000 sanaa, paremmat sijoitukset'
        })
    
    # Markkinaaukoista (vain low effort)
    for gap in gaps:
        if gap.get('effort') == 'low' and gap.get('impact') in ['high', 'critical']:
            quick_wins.append({
                'title': f"Hyödynnä aukko: {gap['gap_title']}",
                'rationale': gap['description'],
                'timeframe': '1-2 viikkoa',
                'effort': 'low',
                'impact': gap['impact'],
                'cost_estimate': '0-200€',
                'expected_result': gap.get('estimated_advantage', 'Merkittävä etu')
            })
    
    return quick_wins[:3]  # ✅ OIKEA RETURN!

async def _get_ai_strategic_recommendations(
    your_analysis: Dict,
    competitor_analyses: List[Dict],
    matrix: Dict,
    gaps: List[Dict],
    language: str
) -> List[Dict[str, Any]]:
    """Pyydä AI:lta strategisia suosituksia"""
    
    your_summary = _extract_detailed_summary(your_analysis)
    positioning = matrix.get('ai_insights', {})
    
    top_gaps = [g['gap_title'] + ': ' + g['description'] for g in gaps[:3]]
    
    prompt_lang = "fi" if language == "fi" else "en"
    
    if prompt_lang == "fi":
        prompt = f"""Olet digitaalisen liiketoiminnan strateginen neuvonantaja. Analysoi tilanne ja anna 3 strategista suositusta:

YRITYS: {your_summary['company']}
PISTEET: {your_summary['score']}/100
ASEMOINTI: {positioning.get('positioning_summary', 'Ei tiedossa')}

MARKKINATILANNE:
- Kilpailijoita analysoitu: {len(competitor_analyses)}
- Tunnistetut aukot: {chr(10).join(top_gaps)}

EROTTUVUUS:
- Vahvuudet: {', '.join(your_summary['key_strengths'])}
- Heikkoudet: {', '.join(your_summary['key_weaknesses'])}

Anna 3 strategista suositusta JSON-muodossa:
{{{{
  "recommendations": [
    {{{{
      "title": "Strateginen suositus 1",
      "strategic_rationale": "Miksi tämä muuttaa peliä",
      "action_steps": ["Konkreettinen askel 1", "Askel 2", "Askel 3"],
      "timeframe": "3-6 kuukautta",
      "investment_required": "Rahallinen ja aikainvestointi",
      "expected_outcome": "Mitä saavutetaan",
      "competitive_impact": "Miten tämä muuttaa kilpailuasetelmaa",
      "risk_level": "low/medium/high"
    }}}}
  ]
}}}}
"""
    else:
        prompt = f"""You are a digital business strategist. Analyze and provide 3 strategic recommendations:

COMPANY: {your_summary['company']}
SCORE: {your_summary['score']}/100
POSITIONING: {positioning.get('positioning_summary', 'Unknown')}

MARKET SITUATION:
- Competitors analyzed: {len(competitor_analyses)}
- Identified gaps: {chr(10).join(top_gaps)}

DIFFERENTIATION:
- Strengths: {', '.join(your_summary['key_strengths'])}
- Weaknesses: {', '.join(your_summary['key_weaknesses'])}

Provide 3 strategic recommendations in JSON:
{{{{
  "recommendations": [
    {{{{
      "title": "Strategic recommendation 1",
      "strategic_rationale": "Why this is game-changing",
      "action_steps": ["Concrete step 1", "Step 2", "Step 3"],
      "timeframe": "3-6 months",
      "investment_required": "Financial and time investment",
      "expected_outcome": "What will be achieved",
      "competitive_impact": "How this changes competitive landscape",
      "risk_level": "low/medium/high"
    }}}}
  ]
}}}}
"""
    
    response = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.5,
        response_format={"type": "json_object"}
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Muotoile AI:n suositukset yhtenäiseen muotoon
    formatted = []
    for rec in result.get('recommendations', []):
        formatted.append({
            'title': rec['title'],
            'rationale': rec['strategic_rationale'],
            'action_steps': rec.get('action_steps', []),
            'timeframe': rec.get('timeframe', '3-6 months'),
            'effort': 'high' if 'high' in rec.get('risk_level', '').lower() else 'medium',
            'impact': 'high',
            'cost_estimate': rec.get('investment_required', 'Määritettään tarkemmin'),
            'expected_result': rec.get('expected_outcome', ''),
            'competitive_impact': rec.get('competitive_impact', ''),
            'risk_level': rec.get('risk_level', 'medium')
        })
    
    return formatted

def _identify_long_term_investments(gaps: List[Dict]) -> List[Dict[str, Any]]:
    """Tunnista pitkän tähtäimen investoinnit"""
    long_term = []
    
    # Etsi high effort / high impact aukkoja
    for gap in gaps:
        if gap.get('effort') == 'high' and gap.get('impact') in ['high', 'critical']:
            long_term.append({
                'title': f"Pitkän tähtäimen: {gap['gap_title']}",
                'rationale': gap['description'],
                'timeframe': '6-12 kuukautta',
                'effort': 'high',
                'impact': gap['impact'],
                'cost_estimate': '5000-20000€',
                'expected_result': gap.get('estimated_advantage', 'Merkittävä kilpailuetu'),
                'strategic_importance': 'Rakentaa kestävää kilpailuetua'
            })
    
    return long_term[:2]

def _calculate_recommendation_priority(rec: Dict) -> int:
    """Laske suosituksen prioriteettipistemäärä"""
    score = 0
    
    # Vaikutus
    impact_map = {'critical': 50, 'high': 40, 'medium': 25, 'low': 10}
    score += impact_map.get(rec.get('impact', 'medium'), 25)
    
    # Vaiva (käänteinen - helpompi parempi)
    effort_map = {'low': 30, 'medium': 20, 'high': 10}
    score += effort_map.get(rec.get('effort', 'medium'), 20)
    
    # Aikaikkuna (nopeampi parempi)
    timeframe = rec.get('timeframe', '').lower()
    if any(word in timeframe for word in ['päivä', 'viikko', 'day', 'week']):
        score += 20
    elif any(word in timeframe for word in ['kuukau', 'month']):
        score += 10
    
    return score




# ============================================================================
# MAIN APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} - Complete Production Ready")
    logger.info(f"📊 Scoring System: Configurable weights {SCORING_CONFIG.weights}")
    logger.info(f"🎭 Playwright: {'available and enabled' if PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED else 'disabled'}")
    logger.info(f"🕸️  SPA Detection: enabled with smart rendering")
    logger.info(f"🔧 Enhanced Features: 10 complete features implemented")
    logger.info(f"🤖 OpenAI: {'available' if openai_client else 'not configured'}")
    logger.info(f"🌐 Starting server on {host}:{port}")
    logger.info(f"🔍 Framework detection mode: {'Wappalyzer' if WAPPALYZER_AVAILABLE else 'Regex fallback'}")
    
    if not WAPPALYZER_AVAILABLE:
    logger.warning("⚠️  Install Wappalyzer for better framework detection: pip install python-Wappalyzer")
    if SECRET_KEY.startswith("brandista-key-"):
        logger.warning("⚠️  Using default SECRET_KEY - set SECRET_KEY environment variable in production!")
    if PLAYWRIGHT_AVAILABLE and not PLAYWRIGHT_ENABLED:
        logger.info("📝 Playwright available but disabled - set PLAYWRIGHT_ENABLED=true to enable SPA rendering")
    
    uvicorn.run(
        app, host=host, port=port, reload=reload,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        access_log=True, server_header=False, date_header=False
    )
