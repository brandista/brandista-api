#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete Unified Version with Playwright SPA Support
Version: 6.2.0 - Production Ready with SPA Analysis
Author: Brandista Team
Date: 2025
Description: Complete production-ready website analysis with SPA support and configurable scoring system
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
from typing import Dict, List, Optional, Any, Tuple, Literal
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
from pydantic import BaseModel, Field, constr

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

# Playwright for SPA content (optional)
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    Browser = None
    Page = None
    PLAYWRIGHT_AVAILABLE = False

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, but that's fine

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

APP_VERSION = "6.2.0"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """Production-ready website analysis with SPA support and configurable scoring system."""

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

# SPA Settings
SPA_TIMEOUT = int(os.getenv("SPA_TIMEOUT", "30000"))  # 30 seconds
SPA_WAIT_FOR_LOAD = int(os.getenv("SPA_WAIT_FOR_LOAD", "5000"))  # 5 seconds additional wait
SPA_MIN_CONTENT_LENGTH = int(os.getenv("SPA_MIN_CONTENT_LENGTH", "500"))

USER_AGENT = os.getenv("USER_AGENT", 
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# CORS settings - configurable via environment
CORS_ORIGINS = os.getenv("CORS_ORIGINS", 
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,"
    "https://brandista.eu,https://www.brandista.eu,https://fastapi-production-51f9.up.railway.app"
).split(",")

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
logger.info(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
logger.info(f"Scoring weights: {SCORING_CONFIG.weights}")
logger.info(f"CORS origins: {CORS_ORIGINS}")# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title=APP_NAME, 
    version=APP_VERSION, 
    description=APP_DESCRIPTION,
    docs_url="/docs", 
    redoc_url="/redoc", 
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
# MODELS
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
    analysis_type: Literal["basic", "comprehensive", "ai_enhanced"] = Field("comprehensive")
    language: Literal["en"] = Field("en")
    include_ai: bool = Field(True)
    include_social: bool = Field(True)
    force_spa: bool = Field(False, description="Force SPA rendering with Playwright")

class ScoreBreakdown(BaseModel):
    # Backend (weighted points)
    security: int = Field(0, ge=0, le=15)
    seo_basics: int = Field(0, ge=0, le=20)
    content: int = Field(0, ge=0, le=20)
    technical: int = Field(0, ge=0, le=15)
    mobile: int = Field(0, ge=0, le=15)
    social: int = Field(0, ge=0, le=10)
    performance: int = Field(0, ge=0, le=5)

    # Frontend aliases (0-100)
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
    content_freshness: Literal["very_fresh", "fresh", "moderate", "dated", "unknown"] = Field("unknown")
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

class SmartAction(BaseModel):
    title: str
    description: str
    priority: Literal["critical", "high", "medium", "low"]
    effort: Literal["low", "medium", "high"]
    impact: Literal["low", "medium", "high", "critical"]
    estimated_score_increase: int = Field(0, ge=0, le=100)
    category: str = ""
    estimated_time: str = ""

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

# Admin quota models
class QuotaUpdateRequest(BaseModel):
    search_limit: Optional[int] = None  # -1 = unlimited
    grant_extra: Optional[int] = Field(None, ge=1)  # add N to current limit (if finite)
    reset_count: bool = False  # reset user's used count

class UserQuotaView(BaseModel):
    username: str
    role: str
    search_limit: int
    searches_used: int# ============================================================================
# ENHANCED SPA DETECTION AND CONTENT FETCHING
# ============================================================================

# Content cache for SPA results
content_cache: Dict[str, Dict[str, Any]] = {}

def is_spa_site(url: str, html_content: Optional[str] = None) -> bool:
    """
    Enhanced SPA detection using domain hints and HTML markers
    """
    try:
        domain = get_domain_from_url(url).lower()
        
        # Known SPA domains
        spa_domains = [
            'brandista.eu',
            'www.brandista.eu',
            # Add more known SPA domains as needed
        ]
        
        # Check for known SPA domains
        if any(spa_domain in domain for spa_domain in spa_domains):
            return True
        
        # If we have HTML content, check for SPA markers
        if html_content:
            html_lower = html_content.lower()
            
            # React indicators
            react_markers = [
                'data-reactroot',
                'react-root',
                'id="root"',
                'id="app"',
                'react.development.js',
                'react.production.min.js',
                '__react_devtools_global_hook__'
            ]
            
            # Vue indicators  
            vue_markers = [
                'vue.js',
                'vue.min.js',
                'v-if=',
                'v-for=',
                'v-model=',
                '{{ ',
                'new vue(',
                'vue.createapp'
            ]
            
            # Angular indicators
            angular_markers = [
                'ng-app',
                'ng-controller', 
                'angular.js',
                'angular.min.js',
                '[ng-',
                '*ngfor',
                '*ngif'
            ]
            
            # Build tool indicators
            build_markers = [
                '__webpack_require__',
                'webpackjsonp',
                '__next_data__',  # Next.js
                'vite',
                'nuxt'
            ]
            
            # General SPA indicators
            spa_markers = [
                'single page application',
                'spa',
                'client-side routing',
                'history.pushstate',
                'router-outlet',
                'router-view'
            ]
            
            all_markers = react_markers + vue_markers + angular_markers + build_markers + spa_markers
            
            # Check for SPA markers
            spa_marker_count = sum(1 for marker in all_markers if marker in html_lower)
            
            # If we found multiple SPA markers, likely a SPA
            if spa_marker_count >= 2:
                return True
                
            # Special case: minimal HTML with just a div#root or div#app
            if (('id="root"' in html_lower or 'id="app"' in html_lower) and 
                html_content.count('<div') < 5):
                return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error in SPA detection for {url}: {e}")
        return False

async def fetch_spa_content_with_retry(url: str, timeout: int = SPA_TIMEOUT) -> Optional[str]:
    """
    Fetch content from SPA using Playwright with retry logic and content validation
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available for SPA content fetching")
        return None
    
    max_attempts = 2
    
    for attempt in range(max_attempts):
        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-accelerated-2d-canvas',
                        '--no-first-run',
                        '--no-zygote',
                        '--disable-gpu',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                
                try:
                    # Create page
                    page = await browser.new_page(
                        user_agent=USER_AGENT,
                        viewport={'width': 1280, 'height': 720}
                    )
                    
                    # Set timeout
                    page.set_default_timeout(timeout)
                    
                    # Navigate to page
                    logger.info(f"Loading SPA content for: {url} (attempt {attempt + 1})")
                    await page.goto(url, wait_until='networkidle', timeout=timeout)
                    
                    # Wait for additional content to load
                    initial_wait = SPA_WAIT_FOR_LOAD / 1000
                    await asyncio.sleep(initial_wait)
                    
                    # Progressive content checking - wait for meaningful content
                    for wait_round in range(3):
                        content = await page.content()
                        
                        # Check if content is meaningful
                        if len(content) > SPA_MIN_CONTENT_LENGTH:
                            # Additional checks for actual rendered content
                            soup = BeautifulSoup(content, 'html.parser')
                            
                            # Remove script and style tags for content check
                            for script in soup(["script", "style"]):
                                script.decompose()
                            
                            text_content = soup.get_text(strip=True)
                            
                            # If we have substantial text content, we're good
                            if len(text_content) > 200:
                                logger.info(f"SPA content fetched successfully for {url}: {len(content)} chars, {len(text_content)} text chars")
                                return content
                        
                        # Wait a bit more for content to load
                        if wait_round < 2:
                            await asyncio.sleep(2)
                    
                    # Final attempt - return what we have if it meets minimum requirements
                    final_content = await page.content()
                    if len(final_content) >= SPA_MIN_CONTENT_LENGTH:
                        logger.info(f"SPA content fetched (minimal) for {url}: {len(final_content)} chars")
                        return final_content
                    else:
                        logger.warning(f"SPA content too short for {url}: {len(final_content)} chars")
                        
                finally:
                    await browser.close()
                    
        except Exception as e:
            logger.error(f"SPA content fetching attempt {attempt + 1} failed for {url}: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
            else:
                logger.error(f"All SPA attempts failed for {url}")
    
    return None

async def get_website_content_cached(
    url: str, 
    force_spa: bool = False, 
    timeout: int = REQUEST_TIMEOUT
) -> Tuple[Optional[str], bool]:
    """
    Get website content using the most appropriate method with caching.
    Returns (content, used_spa) tuple.
    
    Args:
        url: Website URL
        force_spa: Force SPA rendering even for non-SPA sites
        timeout: Request timeout
    
    Returns:
        Tuple of (HTML content, whether SPA was used)
    """
    # Check cache first
    cache_key = hashlib.md5(f"{url}_spa_{force_spa}".encode()).hexdigest()
    
    if cache_key in content_cache:
        cached_entry = content_cache[cache_key]
        if (datetime.now() - cached_entry['timestamp']).total_seconds() < CACHE_TTL:
            logger.info(f"Content cache hit for {url}")
            return cached_entry['content'], cached_entry['used_spa']
    
    used_spa = False
    content = None
    
    # First, try regular HTTP to get initial content for SPA detection
    initial_response = await fetch_url_with_retries(url, timeout=timeout)
    initial_content = None
    
    if initial_response and initial_response.status_code == 200:
        initial_content = initial_response.text
    
    # Determine if we should use SPA rendering
    should_use_spa = force_spa or (PLAYWRIGHT_AVAILABLE and is_spa_site(url, initial_content))
    
    if should_use_spa:
        logger.info(f"Attempting SPA rendering for {url}")
        spa_content = await fetch_spa_content_with_retry(url, timeout=SPA_TIMEOUT)
        
        if spa_content and len(spa_content) > len(initial_content or ""):
            content = spa_content
            used_spa = True
            logger.info(f"SPA rendering successful for {url}: {len(content)} chars")
        else:
            logger.warning(f"SPA rendering failed or provided less content, falling back to HTTP for {url}")
    
    # Fallback to regular HTTP request if SPA failed or wasn't attempted
    if not content:
        if initial_content:
            content = initial_content
            logger.info(f"Using initial HTTP fetch for {url}: {len(content)} chars")
        else:
            logger.error(f"Both SPA and HTTP fetch failed for {url}")
            return None, False
    
    # Cache the result
    content_cache[cache_key] = {
        'content': content,
        'used_spa': used_spa,
        'timestamp': datetime.now()
    }
    
    # Clean old cache entries
    if len(content_cache) > MAX_CACHE_SIZE:
        oldest_keys = sorted(
            content_cache.keys(),
            key=lambda k: content_cache[k]['timestamp']
        )[:len(content_cache) - MAX_CACHE_SIZE]
        
        for old_key in oldest_keys:
            del content_cache[old_key]
    
    return content, used_spa

# Alias for backward compatibility
async def get_website_content(url: str, force_spa: bool = False, timeout: int = REQUEST_TIMEOUT) -> Tuple[Optional[str], bool]:
    """Backward compatibility alias"""
    return await get_website_content_cached(url, force_spa, timeout)# ============================================================================
# AUTHENTICATION SETUP
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

# Global variables
analysis_cache: Dict[str, Dict[str, Any]] = {}
user_search_counts: Dict[str, int] = {}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ensure_integer_scores(data: Any) -> Any:
    """Ensure all score fields are integers"""
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

def get_cache_key(url: str, analysis_type: str = "basic", force_spa: bool = False) -> str:
    """Generate cache key including SPA flag and config version"""
    config_hash = hashlib.md5(str(SCORING_CONFIG.weights).encode()).hexdigest()[:8]
    spa_suffix = "_spa" if force_spa else ""
    return hashlib.md5(f"{url}_{analysis_type}_{APP_VERSION}_{config_hash}{spa_suffix}".encode()).hexdigest()

def is_cache_valid(timestamp: datetime) -> bool:
    """Check if cache entry is still valid"""
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

async def fetch_url_with_retries(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = MAX_RETRIES) -> Optional[httpx.Response]:
    """Fetch URL with retry logic"""
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

def clean_url(url: str) -> str:
    """Clean and normalize URL"""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip('/')

def get_domain_from_url(url: str) -> str:
    """Extract domain from URL"""
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

# ============================================================================
# AUTH FUNCTIONS
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except InvalidTokenError as e:
        logger.warning(f"JWT error: {e}")
        return None

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[UserInfo]:
    """Get current user from authorization header"""
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
    """Require authenticated user"""
    if not user:
        raise HTTPException(401, "Authentication required")
    return user

async def require_admin(user: UserInfo = Depends(require_user)) -> UserInfo:
    """Require admin user"""
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user

# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

async def cleanup_cache():
    """Clean up old cache entries"""
    if len(analysis_cache) <= MAX_CACHE_SIZE:
        return
    items_to_remove = len(analysis_cache) - MAX_CACHE_SIZE
    sorted_items = sorted(analysis_cache.items(), key=lambda x: x[1]['timestamp'])
    for key, _ in sorted_items[:items_to_remove]:
        del analysis_cache[key]
    logger.info(f"Cache cleanup: removed {items_to_remove} entries")# ============================================================================
# ANALYSIS HELPER FUNCTIONS
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

def get_freshness_label(score: int) -> str:
    if score >= 4: return "very_fresh"
    elif score >= 3: return "fresh"
    elif score >= 2: return "moderate"
    elif score >= 1: return "dated"
    return "unknown"

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
# MAIN ENDPOINTS
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    user = USERS_DB.get(request.username)
    if not user:
        logger.warning(f"Login attempt for non-existent user: {request.username}")
        raise HTTPException(401, "Invalid credentials")
    if not verify_password(request.password, user["hashed_password"]):
        logger.warning(f"Failed login attempt for user: {request.username}")
        raise HTTPException(401, "Invalid credentials")
    access_token = create_access_token(data={"sub": request.username, "role": user["role"]})
    logger.info(f"Successful login for user: {request.username}")
    return TokenResponse(access_token=access_token, role=user["role"])

@app.get("/auth/me", response_model=UserInfo)
async def get_me(user: UserInfo = Depends(require_user)):
    return user

@app.post("/auth/logout")
async def logout():
    return {"message": "Logged out successfully"}

@app.post("/api/v1/analyze")
async def basic_analyze(request: CompetitorAnalysisRequest, user: UserInfo = Depends(require_user)):
    try:
        url = clean_url(request.url)
        _reject_ssrf(url)
        
        # Get website content using SPA-aware fetching
        html_content, used_spa = await get_website_content(
            url, 
            force_spa=request.force_spa, 
            timeout=REQUEST_TIMEOUT
        )
        
        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(400, f"Website returned insufficient content: {url}")
        
        # Basic analysis using enhanced method
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Calculate basic scores
        score = 0
        breakdown = {}
        
        # Security check
        if url.startswith('https://'):
            security_score = 10
            breakdown['security'] = security_score
            score += security_score
        else:
            breakdown['security'] = 0
        
        # Content analysis
        text = extract_clean_text(soup)
        word_count = len(text.split())
        content_score = min(20, max(0, word_count // 100))
        breakdown['content'] = content_score
        score += content_score
        
        # Technical basics
        technical_score = 0
        if detect_analytics_tools(html_content)['has_analytics']:
            technical_score += 5
        if soup.find('meta', attrs={'name': 'viewport'}):
            technical_score += 10
        breakdown['technical'] = technical_score
        score += technical_score
        
        # Social platforms
        platforms = extract_social_platforms(html_content)
        social_score = min(10, len(platforms) * 2)
        breakdown['social'] = social_score
        score += social_score
        
        # SEO basics
        seo_score = 0
        if soup.find('title'):
            seo_score += 8
        if soup.find('meta', attrs={'name': 'description'}):
            seo_score += 8
        if soup.find_all('h1'):
            seo_score += 4
        breakdown['seo_basics'] = seo_score
        score += seo_score
        
        # Mobile and performance
        breakdown['mobile'] = technical_score  # Simplified
        breakdown['performance'] = 5 if len(html_content) < 100000 else 2
        score += breakdown['mobile'] + breakdown['performance']
        
        final_score = max(0, min(100, score))
        sb_with_aliases = create_score_breakdown_with_aliases(breakdown)
        
        return {
            "success": True,
            "company": request.company_name or get_domain_from_url(url),
            "website": url,
            "digital_maturity_score": final_score,
            "social_platforms": len(platforms),
            "score_breakdown": sb_with_aliases,
            "analysis_date": datetime.now().isoformat(),
            "analyzed_by": user.username,
            "scoring_weights": SCORING_CONFIG.weights,
            "used_spa_rendering": used_spa,
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "content_words": word_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Basic analysis error: {e}")
        raise HTTPException(500, "Analysis failed")

@app.get("/")
async def root():
    return {
        "name": APP_NAME, "version": APP_VERSION, "status": "operational",
        "endpoints": {
            "health": "/health", 
            "config": "/config",
            "auth": {"login": "/auth/login", "me": "/auth/me"},
            "analysis": {"comprehensive": "/api/v1/ai-analyze", "basic": "/api/v1/analyze"}
        },
        "features": [
            "JWT authentication with role-based access",
            "Enhanced SPA detection with HTML markers",
            "Playwright SPA rendering with retry logic",
            "Configurable scoring system",
            "Content caching with TTL",
            "Production-ready architecture",
            "AI-powered insights"
        ],
        "scoring_system": {"version": "configurable_v1", "weights": SCORING_CONFIG.weights},
        "spa_support": {
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "auto_detection": True,
            "force_spa_option": True,
            "timeout": SPA_TIMEOUT,
            "min_content_length": SPA_MIN_CONTENT_LENGTH
        },
        "cors": {"allow_origins": CORS_ORIGINS}
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
            "cache_size": len(analysis_cache),
            "content_cache_size": len(content_cache),
            "cache_limit": MAX_CACHE_SIZE, 
            "rate_limiting": RATE_LIMIT_ENABLED
        },
        "scoring": {"weights": SCORING_CONFIG.weights, "configurable": True},
        "spa": {
            "timeout": SPA_TIMEOUT,
            "wait_for_load": SPA_WAIT_FOR_LOAD,
            "auto_detection": True,
            "min_content_length": SPA_MIN_CONTENT_LENGTH
        }
    }

@app.get("/config")
async def get_config():
    """Public configuration endpoint"""
    return {
        "version": APP_VERSION,
        "spa_config": {
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "timeout": SPA_TIMEOUT,
            "wait_for_load": SPA_WAIT_FOR_LOAD,
            "min_content_length": SPA_MIN_CONTENT_LENGTH,
            "auto_detection_enabled": True
        },
        "scoring_version": "configurable_v1",
        "cors_origins": CORS_ORIGINS,
        "rate_limiting": RATE_LIMIT_ENABLED
    }

@app.get("/api/v1/config")
async def get_admin_config(user: UserInfo = Depends(require_admin)):
    """Admin-only detailed configuration"""
    return {
        "weights": SCORING_CONFIG.weights,
        "content_thresholds": SCORING_CONFIG.content_thresholds,
        "technical_thresholds": SCORING_CONFIG.technical_thresholds,
        "seo_thresholds": SCORING_CONFIG.seo_thresholds,
        "version": APP_VERSION,
        "spa_config": {
            "playwright_available": PLAYWRIGHT_AVAILABLE,
            "timeout": SPA_TIMEOUT,
            "wait_for_load": SPA_WAIT_FOR_LOAD,
            "min_content_length": SPA_MIN_CONTENT_LENGTH
        }
    }

@app.post("/api/v1/test-spa")
async def test_spa_content(
    request: dict,
    user: UserInfo = Depends(require_user)
):
    """Test endpoint for SPA content fetching"""
    if not PLAYWRIGHT_AVAILABLE:
        raise HTTPException(400, "Playwright not available for SPA testing")
    
    url = request.get("url")
    if not url:
        raise HTTPException(400, "URL required")
    
    url = clean_url(url)
    _reject_ssrf(url)
    
    try:
        # Test regular HTTP fetch
        response = await fetch_url_with_retries(url)
        http_content = response.text if response and response.status_code == 200 else None
        
        # Test SPA detection
        spa_detected = is_spa_site(url, http_content)
        
        # Test SPA fetch if detected
        spa_content = None
        if spa_detected:
            spa_content = await fetch_spa_content_with_retry(url)
        
        return {
            "url": url,
            "spa_detected": spa_detected,
            "http_fetch": {
                "success": bool(http_content),
                "content_length": len(http_content) if http_content else 0,
                "content_preview": (http_content[:500] + "...") if http_content and len(http_content) > 500 else http_content
            },
            "spa_fetch": {
                "success": bool(spa_content),
                "content_length": len(spa_content) if spa_content else 0,
                "content_preview": (spa_content[:500] + "...") if spa_content and len(spa_content) > 500 else spa_content
            },
            "playwright_available": PLAYWRIGHT_AVAILABLE
        }
    except Exception as e:
        logger.error(f"SPA test error for {url}: {e}")
        raise HTTPException(500, f"SPA test failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} - Production Ready with Enhanced SPA Support")
    logger.info(f"📊 Scoring System: Configurable weights {SCORING_CONFIG.weights}")
    logger.info(f"💾 Cache: TTL={CACHE_TTL}s, Max={MAX_CACHE_SIZE} entries")
    logger.info(f"🛡️ Rate limiting: {'enabled' if RATE_LIMIT_ENABLED else 'disabled'}")
    logger.info(f"🤖 OpenAI: {'available' if openai_client else 'not configured'}")
    logger.info(f"🎭 Playwright: {'available' if PLAYWRIGHT_AVAILABLE else 'not available'}")
    logger.info(f"🌐 CORS origins: {CORS_ORIGINS}")
    logger.info(f"🌐 Starting server on {host}:{port}")
    
    # Security warnings
    if SECRET_KEY.startswith("brandista-key-"):
        logger.warning("⚠️ Using default SECRET_KEY - set SECRET_KEY environment variable in production!")
    
    # SPA configuration info
    if PLAYWRIGHT_AVAILABLE:
        logger.info(f"✅ Enhanced SPA Support enabled - timeout: {SPA_TIMEOUT}ms, wait: {SPA_WAIT_FOR_LOAD}ms, min_length: {SPA_MIN_CONTENT_LENGTH}")
    else:
        logger.warning("⚠️ SPA Support disabled - install playwright for React/Vue analysis")
        logger.info("📦 To enable SPA: pip install playwright && playwright install chromium")
    
    uvicorn.run(
        app, host=host, port=port, reload=reload,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        access_log=True, server_header=False, date_header=False
    )
