#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete Unified Version
Version: 6.2.0 - Merged Baseline (analysis + robustness)
Author: Brandista Team
Date: 2025
Description: Complete production-ready website analysis with configurable scoring system and comprehensive SPA support
"""

# MERGE NOTE:
# This file is a merged baseline built from main.py (analysis-rich)
# and main_fixed.py (usability/error tolerance). Version bumped to 6.2.0-merged.
# Subsequent passes can selectively port retry logic or other utilities.


# ============================================================================
# IMPORTS
# ============================================================================

import os
import re
import hashlib
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
SPA_CACHE_TTL = int(os.getenv("SPA_CACHE_TTL", "3600"))  # seconds
content_cache: Dict[str, Dict[str, Any]] = {}
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import time
import socket
import ipaddress
import redis
import json

# ===== Content Fetch Config (Aggressive defaults) =====
CONTENT_FETCH_MODE = os.getenv("CONTENT_FETCH_MODE", "aggressive")  # "aggressive" | "balanced" | "light"

# ===== Content Fetch Advanced Toggles =====
CAPTURE_XHR = os.getenv("CAPTURE_XHR", "1") == "1"
MAX_XHR_BYTES = int(os.getenv("MAX_XHR_BYTES", "1048576"))  # 1 MB cap per response
BLOCK_HEAVY_RESOURCES = os.getenv("BLOCK_HEAVY_RESOURCES", "1") == "1"
COOKIE_AUTO_DISMISS = os.getenv("COOKIE_AUTO_DISMISS", "1") == "1"
COOKIE_SELECTORS = os.getenv(
    "COOKIE_SELECTORS",
    "button[aria-label*='accept'],button:has-text('Accept'),button:has-text('Hyväksy')"
)

SPA_MAX_SCROLL_STEPS = int(os.getenv("SPA_MAX_SCROLL_STEPS", "15"))  
SPA_SCROLL_PAUSE_MS = int(os.getenv("SPA_SCROLL_PAUSE_MS", "1000"))  
SPA_EXTRA_WAIT_MS = int(os.getenv("SPA_EXTRA_WAIT_MS", "5000"))      
SPA_WAIT_FOR_SELECTOR = os.getenv("SPA_WAIT_FOR_SELECTOR", "")  # e.g. "#app" or ".root" if known

# Third-party imports


import httpx
from bs4 import BeautifulSoup


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

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from passlib.context import CryptContext

# FastAPI imports
from fastapi import FastAPI, HTTPException, Header, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

# Playwright imports (optional for SPA support)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

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

APP_VERSION = "6.2.0-merged"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """Production-ready website analysis with configurable scoring system and comprehensive SPA support."""

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

# ============================================================================
# GLOBAL VARIABLES
# ============================================================================

analysis_cache: Dict[str, Dict[str, Any]] = {}
user_search_counts: Dict[str, int] = {}

# Redis setup
REDIS_URL = os.getenv("REDIS_URL")
redis_client = None

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_client = None
else:
    logger.info("No REDIS_URL provided, using memory cache")
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
    """Analyze modern web development features"""
    html_lower = html.lower()
    
    features = {
        # Modern JS frameworks
        'spa_framework': spa_info.get('frameworks', []),
        'has_spa': spa_info.get('spa_detected', False),
        
        # Modern CSS
        'css_grid': 'display: grid' in html_lower or 'display:grid' in html_lower,
        'flexbox': 'display: flex' in html_lower or 'display:flex' in html_lower,
        'css_variables': '--' in html and 'var(' in html_lower,
        
        # Modern HTML
        'semantic_html5': bool(re.search(r'<(article|section|nav|aside|header|footer|main)', html_lower)),
        'web_components': 'custom-element' in html_lower or 'shadow-dom' in html_lower,
        
        # Performance features
        'lazy_loading': 'loading="lazy"' in html_lower,
        'preload_hints': 'rel="preload"' in html_lower or 'rel="prefetch"' in html_lower,
        'modern_image_formats': any(fmt in html_lower for fmt in ['.webp', '.avif', 'picture>']),
        
        # PWA features
        'service_worker': 'service-worker' in html_lower or 'serviceworker' in html_lower,
        'manifest': 'manifest.json' in html_lower or 'rel="manifest"' in html_lower,
        
        # Accessibility
        'aria_labels': 'aria-' in html_lower,
        'skip_links': 'skip' in html_lower and 'main' in html_lower,
    }
    
    # Calculate modernity score
    feature_weights = {
        'spa_framework': 15 if features['spa_framework'] else 0,
        'css_grid': 10,
        'flexbox': 8,
        'semantic_html5': 10,
        'lazy_loading': 8,
        'modern_image_formats': 8,
        'service_worker': 12,
        'manifest': 5,
        'aria_labels': 7,
        'css_variables': 5,
        'preload_hints': 6
    }
    
    modernity_score = sum(weight for feature, weight in feature_weights.items() 
                         if features.get(feature, False))
    
    return {
        'features': features,
        'modernity_score': min(100, modernity_score),
        'is_modern': modernity_score > 50,
        'technology_level': (
            'cutting_edge' if modernity_score > 80 else
            'modern' if modernity_score > 60 else
            'standard' if modernity_score > 30 else
            'basic'
        )
    }

def detect_interactive_elements(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    """Enhanced detection of interactive elements including JS-powered ones"""
    elements = {
        'forms': len(soup.find_all('form')),
        'buttons': len(soup.find_all('button')) + len(soup.find_all('input', type='button')),
        'links': len(soup.find_all('a', href=True)),
        'inputs': len(soup.find_all('input')),
        'selects': len(soup.find_all('select')),
        'textareas': len(soup.find_all('textarea'))
    }
    
    # Detect JS-powered interactive elements
    html_lower = html.lower()
    js_interactions = {
        'onclick_events': html_lower.count('onclick'),
        'event_listeners': html_lower.count('addeventlistener'),
        'jquery_events': html_lower.count('.click(') + html_lower.count('.on('),
        'react_events': html_lower.count('onclick=') + html_lower.count('onchange='),
        'ajax_calls': html_lower.count('ajax') + html_lower.count('fetch(') + html_lower.count('axios')
    }
    
    # Calculate interactivity score
    static_score = min(50, (elements['forms'] * 10 + elements['buttons'] * 5 + 
                           elements['inputs'] * 3 + elements['selects'] * 5))
    js_score = min(50, sum(min(10, count) for count in js_interactions.values()))
    
    total_interactivity = static_score + js_score
    
    return {
        'static_elements': elements,
        'js_interactions': js_interactions,
        'interactivity_score': min(100, total_interactivity),
        'is_highly_interactive': total_interactivity > 60
    }

# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION,
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json"
)

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
        return hashlib.sha256(f"brandista_{password}_salt".encode()).hexdigest()
    
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        # Handle both old bcrypt and new sha256 hashes
        if hashed_password.startswith("$2b$"):
            # Old bcrypt hash - use hardcoded check
            if plain_password == "user123" and "KIXxPfAK3nukvPR9N2Yfme" in hashed_password:
                return True
            if plain_password == "kaikka123" and "8HJxqX4X.0qysVqbHrFene" in hashed_password:
                return True
            return False
        else:
            # New sha256 hash
            return self.hash(plain_password) == hashed_password

pwd_context = SimplePasswordContext()
security = HTTPBearer()

USERS_DB = {
    "user": {
        "username": "user", 
        "hashed_password": pwd_context.hash("user123"),
        "role": "user", 
        "search_limit": DEFAULT_USER_LIMIT
    },
    "admin": {
        "username": "admin", 
        "hashed_password": pwd_context.hash("kaikka123"),
        "role": "admin", 
        "search_limit": -1
    }
}

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
        username = payload.get("sub")
        role = payload.get("role", "user")
        if not username or username not in USERS_DB:
            return None
        user_data = USERS_DB[username]
        return UserInfo(
            username=username, role=role,
            search_limit=user_data["search_limit"],
            searches_used=user_search_counts.get(username, 0)
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
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport:
            vc = viewport.get('content', '')
            if 'width=device-width' in vc: score_components['mobile'] += 5
            if 'initial-scale=1' in vc: score_components['mobile'] += 3
            details['has_viewport'] = True
        else:
            details['has_viewport'] = False
        
        resp = check_responsive_design(html)
        score_components['mobile'] += resp['score']
        
        # SPA mobile bonus (they often have good responsive design)
        if spa_detected and resp['score'] >= 5:
            score_components['mobile'] = min(SCORING_CONFIG.weights['mobile'], score_components['mobile'] + 2)
            details['spa_mobile_bonus'] = True
        
        details['responsive_design'] = resp
        
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

def compute_business_impact(
    basic: Dict[str, Any], 
    content: Dict[str, Any], 
    ux: Dict[str, Any],
    estimated_annual_revenue: int = 450_000  # €450k = EU SME keskiarvo
) -> BusinessImpact:
    """
    Compute realistic business impact with actual revenue estimation.
    
    Args:
        estimated_annual_revenue: Company's estimated annual revenue (default 450k€ EU SME average)
    
    Returns:
        BusinessImpact with realistic lead and revenue projections
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

    # LEAD GENERATION (säilytetään alkuperäinen)
    lead_low = max(3, (seo_pct + content_score) // 40)
    lead_high = max(lead_low + 2, (seo_pct + content_score) // 25)

    # REVENUE CALCULATION (korjattu realistisiksi arvoiksi)
    # Digitaalisten parannusten vaikutus: 0.4-0.7% per 10 pistettä parannusta
    score_improvement_potential = max(10, 90 - score)
    
    # Kasvuprosentti: 4-7% per 10 pisteen parannus
    growth_rate_low = (score_improvement_potential * 0.4) / 100
    growth_rate_high = (score_improvement_potential * 0.7) / 100
    
    # Euromääräinen vuotuinen arvio
    revenue_impact_low = int(estimated_annual_revenue * growth_rate_low)
    revenue_impact_high = int(estimated_annual_revenue * growth_rate_high)
    
    # Kuukausittainen breakdown
    monthly_low = revenue_impact_low // 12
    monthly_high = revenue_impact_high // 12

    # Format revenue range nicely
    def format_currency(amount: int) -> str:
        if amount >= 1_000_000:
            return f"€{amount/1_000_000:.1f}M"
        elif amount >= 1000:
            return f"€{amount//1000}k"
        else:
            return f"€{amount}"

    revenue_range = (
        f"{format_currency(revenue_impact_low)}–{format_currency(revenue_impact_high)}/year "
        f"({format_currency(monthly_low)}–{format_currency(monthly_high)}/mo)"
    )

    return BusinessImpact(
        lead_gain_estimate=_fmt_range(lead_low, lead_high, "leads/mo"),
        revenue_uplift_range=revenue_range,
        confidence=_confidence_label(score),
        customer_trust_effect=(
            "Improves perceived quality (NPS +2–4)" 
            if basic.get('modernity_score', 0) >= 50 
            else "Small positive trust signal"
        )
    )

def build_role_summaries(url: str, basic: Dict[str, Any], impact: BusinessImpact) -> RoleSummaries:
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
    
    # Map categories to actionable business language
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
        priority_items.extend(['technical SEO', 'content optimization'])
    
    # CEO: Strategic overview with top 2 priorities
    ceo_summary = (
        f"We are at {s}/100 ({state}). "
        f"Top priorities: {priority_items[0]}, {priority_items[1]}. "
        f"If we ship these fixes, we can unlock {impact.revenue_uplift_range} "
        f"and {impact.lead_gain_estimate}. Focus: one change per week."
    )
    
    # CMO: Growth levers based on actual gaps
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
    
    # CTO: Technical priorities based on gaps and SPA detection
    cto_priorities = []
    if 'security' in top_gaps:
        cto_priorities.append("SSL + security headers")
    if 'mobile' in top_gaps:
        cto_priorities.append("Core Web Vitals (LCP, CLS)")
    if 'technical' in top_gaps:
        cto_priorities.append("analytics + technical SEO")
    
    # Add SPA-specific recommendation if applicable
    if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
        cto_priorities.insert(0, "SSR/prerender for SPA")
    
    # Fallback if no major gaps
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
    try:
        impact = compute_business_impact(basic, content, ux)
        role = build_role_summaries(url, basic, impact)
        plan = build_plan_90d(basic, content, technical, language=language)  
        risks = build_risk_register(basic, technical, content)
        snippets = build_snippet_examples(url, basic)
        
        # NEW: AI Search Visibility Analysis
        ai_visibility = await analyze_ai_search_visibility(
            url, html, basic, technical, content, social
        )

        insights.update({
            "business_impact": impact.dict(),
            "role_summaries": role.dict(),
            "plan_90d": plan.dict(),
            "risk_register": [r.dict() for r in risks],
            "snippet_examples": snippets.dict(),
            "ai_search_visibility": ai_visibility.dict()  # NEW
        })
    except Exception as e:
        logger.warning(f"Humanized layer build failed: {e}")

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

        core_web_vitals_assessment = {
            "name": "Core Web Vitals",
            "value": "Pass" if passed else "Needs improvement",
            "description": "Website performance metrics",
            "status": cwv_status,
            "score": ps,
            "grade": cwv_grade,
            "metrics": {
                "lcp_ms": 2400 if passed else 3500,
                "tbt_ms": 100 if passed else 180,
                "cls": 0.08 if passed else 0.18
            },
            "recommendations": [
                "Optimize hero images (modern formats, compression)",
                "Defer non-critical JS and enable lazy-loading",
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

        # 10. AI Search Visibility - Placeholder (data comes from ai_analysis)
        ai_search_visibility = {
            "name": "AI Search Visibility",
            "value": "Analysis in progress",
            "description": "ChatGPT & Perplexity readiness - see AI Analysis section",
            "note": "Full analysis available in ai_analysis.ai_search_visibility"
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
            "ai_search_visibility": ai_search_visibility  # ← LISÄTTY
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
    user = USERS_DB.get(request.username)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(401, "Invalid credentials")
    access_token = create_access_token(data={"sub": request.username, "role": user["role"]})
    return TokenResponse(access_token=access_token, role=user["role"])

@app.get("/auth/me", response_model=UserInfo)
async def get_me(user: UserInfo = Depends(require_user)):
    return user

@app.post("/api/v1/ai-analyze")
async def ai_analyze_comprehensive(
    request: CompetitorAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: UserInfo = Depends(require_user)
):
    """Complete comprehensive analysis with full SPA support"""
    try:
        # Quota check
        if user.role != "admin":
            user_limit = USERS_DB.get(user.username, {}).get("search_limit", DEFAULT_USER_LIMIT)
            current_count = user_search_counts.get(user.username, 0)
            if user_limit > 0 and current_count >= user_limit:
                raise HTTPException(403, f"Search limit reached ({user_limit} searches)")

        url = clean_url(request.url)
        _reject_ssrf(url)

        # Check analysis cache
        cache_key = get_cache_key(url, "ai_comprehensive_v6.1.1_complete")
        cached_result = await get_from_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {url} (user: {user.username})")
            return cached_result

        # Smart website content fetching
        logger.info(f"Starting complete comprehensive analysis for {url}")
        
        # Use smart rendering that detects SPAs automatically
        html_content, used_spa = await get_website_content(url, force_spa=getattr(request, 'force_spa', False))
        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(400, "Website returned insufficient content")

        # Create rendering info for enhanced analysis
        rendering_info = {
            'spa_detected': bool(used_spa),
            'spa_info': {'spa_detected': bool(used_spa)},
            'rendering_method': 'playwright' if used_spa else 'http',
            'final_url': url
        }

        # Perform complete comprehensive analysis
        basic_analysis = await analyze_basic_metrics_enhanced(
            url, html_content,
            headers=httpx.Headers({}),
            rendering_info=rendering_info
        )
        
        technical_audit = await analyze_technical_aspects(url, html_content, headers=httpx.Headers({}))
        mobile_readiness, mobile_reasons = summarize_mobile_readiness(technical_audit)
        content_analysis = await analyze_content_quality(html_content)
        ux_analysis = await analyze_ux_elements(html_content)
        social_analysis = await analyze_social_media_presence(url, html_content)
        competitive_analysis = await analyze_competitive_positioning(url, basic_analysis)

        # Create score breakdown with aliases
        sb_with_aliases = create_score_breakdown_with_aliases(basic_analysis.get('score_breakdown', {}))

        # Generate AI insights and features
        ai_analysis = await generate_ai_insights( url, basic_analysis, technical_audit, content_analysis, ux_analysis, social_analysis, html_content,  # ADD THIS language=request.language)
        enhanced_features = await generate_enhanced_features(url, basic_analysis, technical_audit, content_analysis, social_analysis)
        enhanced_features["admin_features_enabled"] = (user.role == "admin")
        smart_actions = generate_smart_actions(ai_analysis, technical_audit, content_analysis, basic_analysis)

        # Add humanized layers with language support
        try:
            impact = compute_business_impact(basic_analysis, content_analysis, ux_analysis)
            role = build_role_summaries(url, basic_analysis, impact)
            plan = build_plan_90d(basic_analysis, content_analysis, technical_audit, language=request.language)
            risks = build_risk_register(basic_analysis, technical_audit, content_analysis)
            snippets = build_snippet_examples(url, basic_analysis)

            # Update ai_analysis with humanized layers
            ai_analysis.business_impact = impact
            ai_analysis.role_summaries = role
            ai_analysis.plan_90d = plan
            ai_analysis.risk_register = risks
            ai_analysis.snippet_examples = snippets
        except Exception as e:
            logger.warning(f"Humanized layer build failed: {e}")
        
        # Construct complete result
        result = {
            "success": True,
            "company_name": request.company_name or get_domain_from_url(url),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": {
                "company": request.company_name or get_domain_from_url(url),
                "website": url,
                "digital_maturity_score": basic_analysis['digital_maturity_score'],
                "social_platforms": basic_analysis.get('social_platforms', 0),
                "technical_score": technical_audit.get('overall_technical_score', 0),
                "content_score": content_analysis.get('content_quality_score', 0),
                "seo_score": int((basic_analysis.get('score_breakdown', {}).get('seo_basics', 0) / SCORING_CONFIG.weights['seo_basics']) * 100),
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
                "competitive_analysis": competitive_analysis
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
                "analyzed_by": user.username,
                "user_role": user.role,
                "rendering_method": rendering_info['rendering_method'],
                "spa_detected": rendering_info['spa_detected'],
                "playwright_available": PLAYWRIGHT_AVAILABLE,
                "scoring_weights": SCORING_CONFIG.weights,
                "content_words": content_analysis.get('word_count', 0),
                "modernity_score": basic_analysis.get('modernity_score', 0)
            }
        }

        # Ensure all scores are integers
        result = ensure_integer_scores(result)
        
        # Cache result
        await set_cache(cache_key, result)
        background_tasks.add_task(cleanup_cache)

        # Update user count
        if user.role != "admin":
            user_search_counts[user.username] = user_search_counts.get(user.username, 0) + 1

        logger.info(f"Complete analysis finished for {url}: score={basic_analysis['digital_maturity_score']}, SPA={rendering_info['spa_detected']}, method={rendering_info['rendering_method']} (user: {user.username})")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, "Analysis failed due to internal error")

@app.post("/api/v1/analyze")
async def basic_analyze(request: CompetitorAnalysisRequest, user: UserInfo = Depends(require_user)):
    """Basic analysis endpoint"""
    try:
        url = clean_url(request.url)
        _reject_ssrf(url)

        # Fetch content (balanced: HTTP first, SPA if needed)
        html_content, used_spa = await get_website_content(url, force_spa=False)

        rendering_info = {
            'spa_detected': bool(used_spa),
            'spa_info': {'spa_detected': bool(used_spa)},
            'rendering_method': 'playwright' if used_spa else 'http',
            'final_url': url
        }

        basic_analysis = await analyze_basic_metrics_enhanced(
            url, html_content,
            headers=httpx.Headers({}),
            rendering_info=rendering_info
        )

        sb_with_aliases = create_score_breakdown_with_aliases(basic_analysis.get('score_breakdown', {}))
        # Compute mobile readiness (best effort)
        try:
            technical_proxy = {
                'has_mobile_optimization': basic_analysis.get('has_mobile_optimization'),
                'page_speed_score': basic_analysis.get('page_speed_score', 0),
                'performance_indicators': basic_analysis.get('performance_indicators', [])
            }
            mobile_readiness, mobile_reasons = summarize_mobile_readiness(technical_proxy)
        except Exception:
            mobile_readiness, mobile_reasons = 'Unknown', []


        return {
            'mobile_readiness': mobile_readiness,
            'mobile_reasons': mobile_reasons,
            "success": True,
            "company": request.company_name or "",
            "website": url,
            "digital_maturity_score": basic_analysis.get('digital_maturity_score', 0),
            "social_platforms": basic_analysis.get('social_platforms', 0),
            "score_breakdown": sb_with_aliases,
            "analysis_date": datetime.now().isoformat(),
            "analyzed_by": user.username,
            "spa_detected": bool(used_spa),
            "rendering_method": 'playwright' if used_spa else 'http',
            "modernity_score": basic_analysis.get('modernity_score', 0),
            "scoring_weights": SCORING_CONFIG.weights
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Basic analysis error: {e}", exc_info=True)
        raise HTTPException(500, "Analysis failed due to internal error")

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
    if payload.search_limit is not None:
        USERS_DB[username]["search_limit"] = int(payload.search_limit)
    if payload.grant_extra is not None:
        cur = USERS_DB[username]["search_limit"]
        if cur != -1:
            USERS_DB[username]["search_limit"] = cur + int(payload.grant_extra)
    if payload.reset_count:
        user_search_counts[username] = 0
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
    role: str = Field("user", pattern="^(user|admin)$")
    search_limit: int = Field(3, ge=-1)

@app.post("/admin/users", response_model=UserQuotaView)
async def admin_create_user(payload: UserCreateRequest, user: UserInfo = Depends(require_admin)):
    """Create a new user (admin only)"""
    if payload.username in USERS_DB:
        raise HTTPException(400, f"User '{payload.username}' already exists")
    
    USERS_DB[payload.username] = {
        "username": payload.username,
        "hashed_password": pwd_context.hash(payload.password),
        "role": payload.role,
        "search_limit": payload.search_limit
    }
    
    logger.info(f"Admin {user.username} created user: {payload.username} (role={payload.role}, limit={payload.search_limit})")
    
    return UserQuotaView(
        username=payload.username,
        role=payload.role,
        search_limit=payload.search_limit,
        searches_used=0
    )

@app.delete("/admin/users/{username}")
async def admin_delete_user(username: str, user: UserInfo = Depends(require_admin)):
    """Delete a user (admin only)"""
    if username not in USERS_DB:
        raise HTTPException(404, "User not found")
    
    if username == "admin":
        raise HTTPException(403, "Cannot delete admin user")
    
    if username == user.username:
        raise HTTPException(403, "Cannot delete yourself")
    
    del USERS_DB[username]
    user_search_counts.pop(username, None)
    
    logger.info(f"Admin {user.username} deleted user: {username}")
    
    return {"ok": True, "message": f"User '{username}' deleted successfully"}

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
    logger.info(f"🔧 Enhanced Features: 9 complete features implemented")
    logger.info(f"🤖 OpenAI: {'available' if openai_client else 'not configured'}")
    logger.info(f"🌐 Starting server on {host}:{port}")
    
    if SECRET_KEY.startswith("brandista-key-"):
        logger.warning("⚠️  Using default SECRET_KEY - set SECRET_KEY environment variable in production!")
    if PLAYWRIGHT_AVAILABLE and not PLAYWRIGHT_ENABLED:
        logger.info("📝 Playwright available but disabled - set PLAYWRIGHT_ENABLED=true to enable SPA rendering")
    
    uvicorn.run(
        app, host=host, port=port, reload=reload,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        access_log=True, server_header=False, date_header=False
    )
