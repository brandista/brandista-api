#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete Unified Version
Version: 6.1.1 - Production Ready with Playwright Support
Author: Brandista Team
Date: 2025
Description: Complete production-ready website analysis with configurable scoring system and SPA support
"""

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
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import time
import socket
import ipaddress

# Third-party imports
import httpx
from bs4 import BeautifulSoup
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

APP_VERSION = "6.1.1"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """Production-ready website analysis with configurable scoring system and Playwright support."""

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
    if (spa_info['requires_js_rendering'] and 
        PLAYWRIGHT_AVAILABLE and 
        PLAYWRIGHT_ENABLED):
        
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

USERS_DB = {
    "user": {
        "username": "user", "hashed_password": pwd_context.hash("user123"),
        "role": "user", "search_limit": DEFAULT_USER_LIMIT
    },
    "admin": {
        "username": "admin", "hashed_password": pwd_context.hash(ADMIN_PASSWORD),
        "role": "admin", "search_limit": -1
    }
}

# ============================================================================
# PYDANTIC MODELS
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
    language: str = Field("en", pattern="^(en)$")
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
# MAIN ANALYSIS FUNCTIONS
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

# Simplified stub functions for backward compatibility
async def analyze_technical_aspects(url: str, html: str, headers: Optional[httpx.Headers] = None) -> Dict[str, Any]:
    """Simplified technical analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    return {
        'has_ssl': url.startswith('https'),
        'has_mobile_optimization': bool(soup.find('meta', attrs={'name': 'viewport'})),
        'page_speed_score': 75,  # Default reasonable score
        'has_analytics': detect_analytics_tools(html)['has_analytics'],
        'has_sitemap': check_sitemap_indicators(soup),
        'has_robots_txt': check_robots_indicators(html),
        'meta_tags_score': 75,
        'overall_technical_score': 75,
        'security_headers': check_security_headers_from_headers(headers) if headers else {},
        'performance_indicators': []
    }

async def analyze_content_quality(html: str) -> Dict[str, Any]:
    """Simplified content analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    text = extract_clean_text(soup)
    wc = len(text.split())
    return {
        'word_count': wc,
        'readability_score': calculate_readability_score(text),
        'keyword_density': {},
        'content_freshness': get_freshness_label(check_content_freshness(soup, html)),
        'has_blog': bool(soup.find('a', href=re.compile(r'/(blog|news|articles)', re.I))),
        'content_quality_score': min(100, max(20, wc // 30)),
        'media_types': [],
        'interactive_elements': []
    }

async def analyze_ux_elements(html: str) -> Dict[str, Any]:
    """Simplified UX analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    return {
        'navigation_score': 50 if soup.find('nav') else 25,
        'visual_design_score': 50,
        'accessibility_score': 60 if soup.find('html', lang=True) else 30,
        'mobile_ux_score': 50 if soup.find('meta', attrs={'name': 'viewport'}) else 20,
        'overall_ux_score': 45,
        'accessibility_issues': [],
        'navigation_elements': [],
        'design_frameworks': []
    }

async def analyze_social_media_presence(url: str, html: str) -> Dict[str, Any]:
    """Simplified social media analysis"""
    platforms = extract_social_platforms(html)
    soup = BeautifulSoup(html, 'html.parser')
    return {
        'platforms': platforms,
        'total_followers': 0,
        'engagement_rate': 0.0,
        'posting_frequency': "unknown",
        'social_score': min(100, len(platforms) * 20),
        'has_sharing_buttons': 'share' in html.lower(),
        'open_graph_tags': len(soup.find_all('meta', property=re.compile('^og:'))),
        'twitter_cards': bool(soup.find_all('meta', attrs={'name': re.compile('^twitter:')}))
    }

async def analyze_competitive_positioning(url: str, basic: Dict[str, Any]) -> Dict[str, Any]:
    """Simplified competitive analysis"""
    score = basic.get('digital_maturity_score', 0)
    if score >= 75: position = "Digital Leader"
    elif score >= 60: position = "Strong Performer"  
    elif score >= 45: position = "Average Competitor"
    else: position = "Below Average"
    return {
        'market_position': position,
        'competitive_advantages': ["Digital presence established"],
        'competitive_threats': ["Market competition"],
        'market_share_estimate': "Data not available",
        'competitive_score': min(100, score + 10),
        'industry_comparison': {'your_score': score, 'industry_average': 45}
    }

# ============================================================================
# AI INSIGHTS AND ENHANCED FEATURES
# ============================================================================

async def generate_ai_insights(url: str, basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], ux: Dict[str, Any], social: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI-powered insights"""
    overall = basic.get('digital_maturity_score', 0)
    spa_detected = basic.get('spa_detected', False)
    modernity_score = basic.get('modernity_score', 0)
    
    # Generate basic insights
    if overall >= 75: 
        summary = f"Excellent digital maturity ({overall}/100) - you are a digital leader."
    elif overall >= 60: 
        summary = f"Good digital presence ({overall}/100) with solid fundamentals."
    elif overall >= 45: 
        summary = f"Baseline achieved ({overall}/100) with improvement opportunities."
    else: 
        summary = f"Early-stage digital maturity ({overall}/100) - immediate action required."
    
    if spa_detected:
        summary += f" Modern SPA architecture {'well-implemented' if modernity_score > 60 else 'needs optimization'}."
    
    return {
        'summary': summary,
        'strengths': ["Digital presence established", "Basic functionality working"],
        'weaknesses': ["Room for improvement in key areas"],
        'opportunities': ["Growth potential exists", "Modern web practices available"],
        'threats': ["Competitive pressure"],
        'recommendations': ["Focus on high-impact improvements", "Consider modern web technologies"],
        'confidence_score': min(95, max(60, overall + 20)),
        'sentiment_score': (overall / 100) * 0.8 + 0.2,
        'key_metrics': {
            'digital_maturity': overall,
            'spa_detected': spa_detected,
            'modernity_score': modernity_score
        },
        'action_priority': []
    }

async def generate_enhanced_features(url: str, basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], social: Dict[str, Any]) -> Dict[str, Any]:
    """Generate enhanced features"""
    score = basic.get('digital_maturity_score', 0)
    spa_detected = basic.get('spa_detected', False)
    modernity_score = basic.get('modernity_score', 0)
    
    return {
        "industry_benchmarking": {
            "name": "Industry Benchmarking",
            "value": f"{score} / 100",
            "description": "Industry comparison with modern web considerations",
            "status": "above_average" if score > 45 else "below_average",
            "details": {
                "your_score": score,
                "industry_average": 45,
                "spa_bonus": 5 if spa_detected and modernity_score > 60 else 0,
                "percentile": min(100, int((score / 45) * 50)) if score <= 45 else min(100, 50 + int(((score - 45) / 55) * 50))
            }
        },
        "technology_stack": {
            "name": "Technology Stack",
            "value": "Modern analysis complete" if spa_detected else "Traditional web technologies",
            "description": "Technology stack analysis with SPA detection",
            "detected": ["SPA Framework"] if spa_detected else ["HTML5", "CSS3"],
            "modernity": "cutting_edge" if modernity_score > 80 else "modern" if modernity_score > 50 else "standard"
        }
    }

def generate_smart_actions(ai_analysis: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate smart actions based on analysis"""
    actions = []
    score = basic.get('digital_maturity_score', 0)
    
    if not basic.get('has_ssl', True):
        actions.append({
            "title": "Enable HTTPS",
            "description": "Install SSL certificate for security and SEO benefits",
            "priority": "critical",
            "effort": "medium",
            "impact": "high",
            "estimated_score_increase": 15,
            "category": "security",
            "estimated_time": "1-2 days"
        })
    
    if content.get('word_count', 0) < 500:
        actions.append({
            "title": "Expand content",
            "description": "Add comprehensive content to improve SEO and user engagement",
            "priority": "high",
            "effort": "high",
            "impact": "high",
            "estimated_score_increase": 12,
            "category": "content",
            "estimated_time": "1-2 weeks"
        })
    
    return actions[:5]

# ============================================================================
# ENDPOINTS
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
    """Enhanced comprehensive analysis with SPA support"""
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
        cache_key = get_cache_key(url, "ai_comprehensive_v6.1.1_enhanced")
        if cache_key in analysis_cache and is_cache_valid(analysis_cache[cache_key]['timestamp']):
            logger.info(f"Analysis cache hit for {url} (user: {user.username})")
            return analysis_cache[cache_key]['data']

        # Smart website content fetching
        logger.info(f"Starting enhanced analysis for {url}")
        
        # Use smart rendering that detects SPAs automatically
        fetch_result = await fetch_url_with_smart_rendering(url)
        if not fetch_result or fetch_result['status'] != 200:
            raise HTTPException(400, f"Cannot access website: {url}")
        
        html_content = fetch_result['html']
        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(400, "Website returned insufficient content")

        # Create rendering info for enhanced analysis
        rendering_info = {
            'spa_detected': fetch_result.get('spa_detected', False),
            'spa_info': fetch_result.get('spa_info', {}),
            'rendering_method': fetch_result.get('rendering_method', 'http'),
            'final_url': fetch_result.get('final_url', url)
        }

        # Perform enhanced comprehensive analysis
        basic_analysis = await analyze_basic_metrics_enhanced(
            url, html_content, 
            headers=httpx.Headers(fetch_result.get('headers', {})), 
            rendering_info=rendering_info
        )
        
        technical_audit = await analyze_technical_aspects(url, html_content, headers=httpx.Headers(fetch_result.get('headers', {})))
        content_analysis = await analyze_content_quality(html_content)
        ux_analysis = await analyze_ux_elements(html_content)
        social_analysis = await analyze_social_media_presence(url, html_content)
        competitive_analysis = await analyze_competitive_positioning(url, basic_analysis)

       # Create score breakdown with aliases
        sb_with_aliases = create_score_breakdown_with_aliases(basic_analysis.get('score_breakdown', {}))

        # Generate AI insights and features
        ai_analysis = await generate_ai_insights(url, basic_analysis, technical_audit, content_analysis, ux_analysis, social_analysis)
        enhanced_features = await generate_enhanced_features(url, basic_analysis, technical_audit, content_analysis, social_analysis)
        enhanced_features["admin_features_enabled"] = (user.role == "admin")
        smart_actions = generate_smart_actions(ai_analysis, technical_audit, content_analysis, basic_analysis)

        # Construct comprehensive result
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
            "ai_analysis": ai_analysis,
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
                "scoring_version": "configurable_v1_enhanced",
                "analysis_depth": "comprehensive_spa_aware",
                "confidence_level": ai_analysis['confidence_score'],
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
        analysis_cache[cache_key] = {'data': result, 'timestamp': datetime.now()}
        background_tasks.add_task(cleanup_cache)

        # Update user count
        if user.role != "admin":
            user_search_counts[user.username] = user_search_counts.get(user.username, 0) + 1

        logger.info(f"Enhanced analysis complete for {url}: score={basic_analysis['digital_maturity_score']}, SPA={rendering_info['spa_detected']}, method={rendering_info['rendering_method']} (user: {user.username})")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enhanced analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, "Analysis failed due to internal error")

@app.get("/")
async def root():
    return {
        "name": APP_NAME, "version": APP_VERSION, "status": "operational",
        "features": [
            "JWT authentication with role-based access",
            "Configurable scoring system", 
            "SPA detection and smart rendering",
            "Playwright support for modern web apps",
            "AI-powered insights"
        ],
        "capabilities": {
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "playwright_enabled": PLAYWRIGHT_ENABLED,
            "spa_detection": True,
            "modern_web_analysis": True
        }
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
            "cache_size": len(analysis_cache)
        }
    }

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
# MAIN APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} - Production Ready with Enhanced Features")
    logger.info(f"📊 Scoring System: Configurable weights {SCORING_CONFIG.weights}")
    logger.info(f"🎭 Playwright: {'available and enabled' if PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED else 'disabled'}")
    logger.info(f"🕸️  SPA Detection: enabled")
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
