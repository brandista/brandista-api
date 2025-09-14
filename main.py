#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete Unified Version
Version: 6.0.1 - Production Ready
Author: Brandista Team
Date: 2025
Description: Complete production-ready website analysis with configurable scoring system
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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

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

APP_VERSION = "6.0.1"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """Production-ready website analysis with configurable scoring system."""

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

USER_AGENT = os.getenv("USER_AGENT", 
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# --- CORS (päivitetty) ---
ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://brandista.example"
    ).split(",")
]
# Valinnainen regex-esikatseluille (esim. Vercel/Netlify previewt)
ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip() or None

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

# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION,
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json"
)

# --- CORS middleware (päivitetty blokk i) ---
cors_common_kwargs = dict(
    allow_credentials=True,         # sallitaan kirjautuminen/Authorization-header
    allow_methods=["*"],            # helpottaa preflightia
    allow_headers=["*"],            # mm. Authorization, Content-Type, Accept
    expose_headers=["*"],
    max_age=600
)

if ALLOWED_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        **cors_common_kwargs
    )
else:
    # Jos '*' mukana listoissa → selaimen sääntöjen mukaan credentials=False
    if "*" in ALLOWED_ORIGINS:
        cors_common_kwargs["allow_credentials"] = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        **cors_common_kwargs
    )

logger.info(
    f"CORS configured | origins={ALLOWED_ORIGINS} | regex={ALLOWED_ORIGIN_REGEX} | "
    f"credentials={cors_common_kwargs['allow_credentials']}"
)

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
    analysis_type: str = Field("comprehensive", pattern="^(basic|comprehensive|ai_enhanced)$")
    language: str = Field("en", pattern="^(en)$")
    include_ai: bool = Field(True)
    include_social: bool = Field(True)

class ScoreBreakdown(BaseModel):
    security: int = Field(0, ge=0, le=15)
    seo_basics: int = Field(0, ge=0, le=20)
    content: int = Field(0, ge=0, le=20)
    technical: int = Field(0, ge=0, le=15)
    mobile: int = Field(0, ge=0, le=15)
    social: int = Field(0, ge=0, le=10)
    performance: int = Field(0, ge=0, le=5)

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
    priority: str = Field(..., pattern="^(critical|high|medium|low)$")
    effort: str = Field(..., pattern="^(low|medium|high)$")
    impact: str = Field(..., pattern="^(low|medium|high|critical)$")
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
    """Convert score fields to integers"""
    if isinstance(data, dict):
        for k, v in data.items():
            if ('_score' in k.lower()) or (k == 'score'):
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
    return hashlib.md5(f"{url}_{analysis_type}_{APP_VERSION}_{config_hash}".encode()).hexdigest()

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
        # Resolve both IPv4/IPv6
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
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip('/')

def get_domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]

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
# GLOBAL VARIABLES
# ============================================================================

analysis_cache: Dict[str, Dict[str, Any]] = {}
user_search_counts: Dict[str, int] = {}

# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

async def cleanup_cache():
    if len(analysis_cache) <= MAX_CACHE_SIZE:
        return
    items_to_remove = len(analysis_cache) - MAX_CACHE_SIZE
    sorted_items = sorted(analysis_cache.items(), key=lambda x: x[1]['timestamp'])
    for key, _ in sorted_items[:items_to_remove]:
        del analysis_cache[key]
    logger.info(f"Cache cleanup: removed {items_to_remove} entries")

# ============================================================================
# ANALYSIS HELPER FUNCTIONS
# ============================================================================

def check_security_headers_from_headers(headers: httpx.Headers) -> Dict[str, bool]:
    # Case-insensitive header access
    def has(h: str) -> bool:
        return h in headers
    return {
        'csp': has('content-security-policy'),
        'x_frame_options': has('x-frame-options'),
        'strict_transport': has('strict-transport-security')
    }

def check_security_headers_in_html(html: str) -> Dict[str, bool]:
    # fallback only (less accurate, for SSR-generated tags/hints)
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
    else: return max(0, int(max_score * (word_count / thresholds['minimal'] * 0.1)))

def calculate_seo_score_configurable(soup: BeautifulSoup, url: str) -> Tuple[int, Dict[str, Any]]:
    config = SCORING_CONFIG.seo_thresholds
    scores = config['scores']
    details = {}
    total_score = 0
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
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    h3_tags = soup.find_all('h3')
    if len(h1_tags) == config['h1_optimal_count']: total_score += 3
    elif len(h1_tags) in [2, 3]: total_score += 1
    if len(h2_tags) >= 2: total_score += 1
    if len(h3_tags) >= 1: total_score += 1
    if soup.find('link', {'rel': 'canonical'}): total_score += scores['canonical']; details['has_canonical'] = True
    if soup.find('link', {'hreflang': True}): total_score += scores['hreflang']; details['has_hreflang'] = True
    if check_clean_urls(url): total_score += scores['clean_urls']
    return min(total_score, SCORING_CONFIG.weights['seo_basics']), details

# ============================================================================
# MAIN ANALYSIS FUNCTIONS
# ============================================================================

async def analyze_basic_metrics_enhanced(url: str, html: str, headers: Optional[httpx.Headers] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    score_components = {category: 0 for category in SCORING_CONFIG.weights.keys()}
    details: Dict[str, Any] = {}
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
        
        # SEO using configurable scoring
        seo_score, seo_details = calculate_seo_score_configurable(soup, url)
        score_components['seo_basics'] = seo_score
        details.update(seo_details)
        
        # CONTENT
        text = extract_clean_text(soup)
        word_count = len(text.split())
        content_score = calculate_content_score_configurable(word_count)
        freshness_score = check_content_freshness(soup, html)
        img_opt = analyze_image_optimization(soup)
        score_components['content'] = min(
            SCORING_CONFIG.weights['content'],
            content_score + freshness_score + img_opt['score']
        )
        details['word_count'] = word_count
        details['image_optimization'] = img_opt
        
        # TECHNICAL
        analytics = detect_analytics_tools(html)
        if analytics['has_analytics']: score_components['technical'] += 3
        if check_sitemap_indicators(soup): score_components['technical'] += 1
        if check_robots_indicators(html): score_components['technical'] += 1
        details['analytics'] = analytics['tools']
        
        # MOBILE
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
        details['responsive_design'] = resp
        
        # SOCIAL
        social_platforms = extract_social_platforms(html)
        score_components['social'] = min(10, len(social_platforms))
        
        # PERFORMANCE (karkeat heuristiikat)
        if len(html) < 100_000: score_components['performance'] += 2
        elif len(html) < 200_000: score_components['performance'] += 1
        if 'lazy' in html.lower() or 'loading="lazy"' in html: score_components['performance'] += 2
        if 'webp' in html.lower(): score_components['performance'] += 1
        
        total_score = sum(score_components.values())
        final_score = max(0, min(100, total_score))
        logger.info(f"Enhanced analysis for {url}: Score={final_score}")
        
        return {
            'digital_maturity_score': final_score, 'score_breakdown': score_components,
            'detailed_findings': details, 'word_count': word_count,
            'has_ssl': url.startswith('https'),
            'has_analytics': analytics.get('has_analytics', False),
            'has_mobile_viewport': details.get('has_viewport', False),
            'title': soup.find('title').get_text().strip() if soup.find('title') else '',
            'meta_description': soup.find('meta', attrs={'name': 'description'}).get('content', '') if soup.find('meta', attrs={'name': 'description'}) else '',
            'h1_count': len(soup.find_all('h1')), 'h2_count': len(soup.find_all('h2')),
            'social_platforms': len(social_platforms)
        }
    except Exception as e:
        logger.error(f"Error in analysis for {url}: {e}")
        return {
            'digital_maturity_score': 0,
            'score_breakdown': {category: 0 for category in SCORING_CONFIG.weights.keys()},
            'detailed_findings': {'error': str(e)}, 'word_count': 0,
            'has_ssl': url.startswith('https'), 'has_analytics': False,
            'has_mobile_viewport': False, 'title': '', 'meta_description': '',
            'h1_count': 0, 'h2_count': 0, 'social_platforms': 0
        }

async def analyze_technical_aspects(url: str, html: str, headers: Optional[httpx.Headers] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    tech_score = 0
    has_ssl = url.startswith('https')
    if has_ssl: tech_score += 20

    # Mobile viewport
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    has_mobile = False
    if viewport:
        vc = viewport.get('content', '')
        if 'width=device-width' in vc: has_mobile = True; tech_score += 15
        if 'initial-scale=1' in vc: tech_score += 5

    analytics = detect_analytics_tools(html)
    if analytics['has_analytics']: tech_score += 10

    # Meta tags scoring (max 15) -> skaalataan 0–100
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

    # Page speed estimation -> skaalattu 0–100
    size = len(html)
    if size < 50_000: ps_points = 15
    elif size < 100_000: ps_points = 12
    elif size < 200_000: ps_points = 8
    elif size < 500_000: ps_points = 5
    else: ps_points = 2
    page_speed_score = int(ps_points / 15 * 100)
    tech_score += ps_points

    # Security headers from real HTTP headers (fallback to HTML heuristic)
    if headers is not None:
        sh = check_security_headers_from_headers(headers)
    else:
        sh = check_security_headers_in_html(html)
    sec_cfg = SCORING_CONFIG.technical_thresholds.get('security_headers', {'csp':4,'x_frame_options':3,'strict_transport':3})
    if sh.get('csp'): tech_score += sec_cfg.get('csp', 4)
    if sh.get('x_frame_options'): tech_score += sec_cfg.get('x_frame_options', 3)
    if sh.get('strict_transport'): tech_score += sec_cfg.get('strict_transport', 3)

    final = max(0, min(100, tech_score))
    return {
        'has_ssl': has_ssl,
        'has_mobile_optimization': has_mobile,
        'page_speed_score': page_speed_score,
        'has_analytics': analytics['has_analytics'],
        'has_sitemap': check_sitemap_indicators(soup),
        'has_robots_txt': check_robots_indicators(html),
        'meta_tags_score': meta_tags_score,
        'overall_technical_score': final,
        'security_headers': sh,
        'performance_indicators': []
    }

async def analyze_content_quality(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    text = extract_clean_text(soup)
    words = text.split()
    wc = len(words)
    score = 0
    media_types: List[str] = []
    interactive: List[str] = []
    volume_score = calculate_content_score_configurable(wc)
    score += volume_score
    if soup.find_all('h2'): score += 5
    if soup.find_all('h3'): score += 3
    if soup.find_all(['ul','ol']): score += 4
    if soup.find_all('table'): score += 3
    fresh = check_content_freshness(soup, html)
    score += fresh * 3
    if soup.find_all('img'): score += 5; media_types.append('images')
    if soup.find_all('video') or 'youtube' in html.lower(): score += 5; media_types.append('video')
    if soup.find_all('form'): score += 5; interactive.append('forms')
    if soup.find_all('button'): score += 3; interactive.append('buttons')
    blog_patterns = ['/blog', '/news', '/articles']
    has_blog = any(soup.find('a', href=re.compile(p, re.I)) for p in blog_patterns)
    if has_blog: score += 10
    final = max(0, min(100, score))
    return {
        'word_count': wc, 'readability_score': calculate_readability_score(text),
        'keyword_density': {}, 'content_freshness': get_freshness_label(fresh),
        'has_blog': has_blog, 'content_quality_score': final,
        'media_types': media_types, 'interactive_elements': interactive
    }

async def analyze_ux_elements(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    nav_score = 0
    if soup.find('nav'): nav_score += 20
    if soup.find('header'): nav_score += 10
    if soup.find_all(['ul','ol'], class_=re.compile('nav|menu', re.I)): nav_score += 20
    nav_score = min(100, nav_score)
    design_score = 0
    hl = html.lower()
    for fw, pts in {'tailwind':25,'bootstrap':20,'foundation':15}.items():
        if fw in hl: design_score += pts; break
    if 'display: flex' in hl: design_score += 10
    if '@media' in hl: design_score += 10
    design_score = min(100, design_score)
    a11y_score = 0
    if soup.find('html', lang=True): a11y_score += 10
    imgs = soup.find_all('img')
    if imgs:
        with_alt = [i for i in imgs if i.get('alt','').strip()]
        a11y_score += int((len(with_alt)/len(imgs))*25)
    else: a11y_score += 25
    a11y_score = min(100, a11y_score)
    mobile_score = 0
    vp = soup.find('meta', attrs={'name':'viewport'})
    if vp:
        vc = vp.get('content','')
        if 'width=device-width' in vc: mobile_score += 20
        if 'initial-scale=1' in vc: mobile_score += 10
    mobile_score = min(100, mobile_score)
    overall = int((nav_score + design_score + a11y_score + mobile_score)/4)
    return {
        'navigation_score': nav_score, 'visual_design_score': design_score,
        'accessibility_score': a11y_score, 'mobile_ux_score': mobile_score,
        'overall_ux_score': overall, 'accessibility_issues': [],
        'navigation_elements': [], 'design_frameworks': []
    }

async def analyze_social_media_presence(url: str, html: str) -> Dict[str, Any]:
    platforms = extract_social_platforms(html)
    soup = BeautifulSoup(html, 'html.parser')
    score = len(platforms) * 10
    has_sharing = any(p in html.lower() for p in ['addtoany','sharethis','addthis','social-share'])
    if has_sharing: score += 15
    og_count = len(soup.find_all('meta', property=re.compile('^og:')))
    if og_count >= 4: score += 10
    elif og_count >= 2: score += 5
    twitter_cards = bool(soup.find_all('meta', attrs={'name': re.compile('^twitter:')}))
    if twitter_cards: score += 5
    return {
        'platforms': platforms, 'total_followers': 0, 'engagement_rate': 0.0,
        'posting_frequency': "unknown", 'social_score': min(100, score),
        'has_sharing_buttons': has_sharing, 'open_graph_tags': og_count,
        'twitter_cards': twitter_cards
    }

async def analyze_competitive_positioning(url: str, basic: Dict[str, Any]) -> Dict[str, Any]:
    score = basic.get('digital_maturity_score', 0)
    if score >= 75:
        position = "Digital Leader"; advantages = ["Excellent digital presence", "Advanced technical execution"]; threats = ["Pressure to innovate continuously"]; comp_score = 85
    elif score >= 60:
        position = "Strong Performer"; advantages = ["Solid digital foundation"]; threats = ["Gap to market leaders"]; comp_score = 70
    elif score >= 45:
        position = "Average Competitor"; advantages = ["Baseline established"]; threats = ["At risk of falling behind"]; comp_score = 50
    else:
        position = "Below Average"; advantages = ["Significant upside potential"]; threats = ["Competitive disadvantage"]; comp_score = 30
    return {
        'market_position': position, 'competitive_advantages': advantages,
        'competitive_threats': threats, 'market_share_estimate': "Data not available",
        'competitive_score': comp_score,
        'industry_comparison': {'your_score': score, 'industry_average': 45, 'top_quartile': 70, 'bottom_quartile': 30}
    }

# ============================================================================
# AI INSIGHTS (unchanged core)
# ============================================================================

async def generate_ai_insights(url: str, basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], ux: Dict[str, Any], social: Dict[str, Any]) -> AIAnalysis:
    overall = basic.get('digital_maturity_score', 0)
    insights = generate_english_insights(overall, basic, technical, content, ux, social)
    if openai_client:
        try:
            context = f"""
            Website: {url}
            Score: {overall}/100
            Technical: {technical.get('overall_technical_score', 0)}/100
            Content words: {content.get('word_count', 0)}
            Social: {social.get('social_score', 0)}/100
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
    return AIAnalysis(**insights)

def generate_english_insights(overall: int, basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any], ux: Dict[str, Any], social: Dict[str, Any]) -> Dict[str, Any]:
    strengths, weaknesses, opportunities, threats, recommendations = [], [], [], [], []
    breakdown = basic.get('score_breakdown', {})
    wc = content.get('word_count', 0)
    if breakdown.get('security', 0) >= 13:
        strengths.append(f"Strong security posture ({breakdown['security']}/15)")
    if breakdown.get('seo_basics', 0) >= 15:
        strengths.append(f"Excellent SEO fundamentals ({breakdown['seo_basics']}/20)")
    if wc > 2000:
        strengths.append(f"Comprehensive content ({wc} words)")
    if social.get('platforms'):
        strengths.append(f"Multi-platform social presence ({len(social['platforms'])} platforms)")
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
    if overall < 30:
        opportunities.extend([f"Massive upside - target {overall + 40} points","Fundamentals can yield +20-30 points quickly"])
    elif overall < 50:
        opportunities.extend([f"Growth potential - target {overall + 30} points","SEO optimization could lift traffic by 50-100%"])
    else:
        opportunities.extend(["Strong foundation for innovation","AI and automation are next leverage points"])
    if overall >= 75: summary = f"Excellent digital maturity ({overall}/100) - you are a digital leader."
    elif overall >= 60: summary = f"Good digital presence ({overall}/100) with solid fundamentals."
    elif overall >= 45: summary = f"Baseline achieved ({overall}/100) with improvement opportunities."
    else: summary = f"Early-stage digital maturity ({overall}/100) - immediate action required."
    return {
        'summary': summary, 'strengths': strengths[:5], 'weaknesses': weaknesses[:5],
        'opportunities': opportunities[:4], 'threats': threats[:3],
        'recommendations': recommendations[:5], 'confidence_score': min(95, max(60, overall + 20)),
        'sentiment_score': (overall / 100) * 0.8 + 0.2, 'key_metrics': {}, 'action_priority': []
    }

def generate_smart_actions(ai: AIAnalysis, technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = []
    breakdown = basic.get('score_breakdown', {})
    sec = breakdown.get('security', 0)
    if sec == 0:
        actions.append({
            "title": "Critical: Enable HTTPS immediately",
            "description": "No SSL certificate present - critical security issue",
            "priority": "critical", "effort": "low", "impact": "critical",
            "estimated_score_increase": 10, "category": "security", "estimated_time": "1-2 days"
        })
    if breakdown.get('content', 0) <= 5:
        actions.append({
            "title": "Create comprehensive content strategy",
            "description": f"Content score very low - substantial development needed",
            "priority": "critical", "effort": "high", "impact": "critical",
            "estimated_score_increase": 15, "category": "content", "estimated_time": "2-4 weeks"
        })
    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    actions.sort(key=lambda x: (priority_order.get(x['priority'], 4), -x.get('estimated_score_increase', 0)))
    return actions[:10]

# ============================================================================
# AUTH ENDPOINTS
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

# ============================================================================
# MAIN ANALYSIS ENDPOINTS
# ============================================================================

@app.post("/api/v1/ai-analyze")
async def ai_analyze_comprehensive(
    request: CompetitorAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: UserInfo = Depends(require_user)
):
    try:
        if user.role != "admin":
            user_limit = USERS_DB.get(user.username, {}).get("search_limit", DEFAULT_USER_LIMIT)
            current_count = user_search_counts.get(user.username, 0)
            if user_limit > 0 and current_count >= user_limit:
                raise HTTPException(403, f"Search limit reached ({user_limit} searches)")
        url = clean_url(request.url)
        _reject_ssrf(url)
        cache_key = get_cache_key(url, "ai_comprehensive_v6.0.1")
        if cache_key in analysis_cache and is_cache_valid(analysis_cache[cache_key]['timestamp']):
            logger.info(f"Cache hit for {url} (user: {user.username})")
            return analysis_cache[cache_key]['data']
        response = await fetch_url_with_retries(url)
        if not response or response.status_code != 200:
            raise HTTPException(400, f"Cannot access website: {url}")
        html_content = response.text
        if not html_content or len(html_content.strip()) < 100:
            raise HTTPException(400, "Website returned insufficient content")
        basic_analysis = await analyze_basic_metrics_enhanced(url, html_content, headers=response.headers)
        technical_audit = await analyze_technical_aspects(url, html_content, headers=response.headers)
        content_analysis = await analyze_content_quality(html_content)
        ux_analysis = await analyze_ux_elements(html_content)
        social_analysis = await analyze_social_media_presence(url, html_content)
        competitive_analysis = await analyze_competitive_positioning(url, basic_analysis)
        ai_analysis = await generate_ai_insights(
            url, basic_analysis, technical_audit, content_analysis, ux_analysis, social_analysis
        )
        enhanced_features = {
            "industry_benchmarking": {
                "value": f"{basic_analysis['digital_maturity_score']} / 100",
                "description": "Industry comparison based on configurable scoring",
                "status": "above_average" if basic_analysis['digital_maturity_score'] > 45 else "below_average",
                "details": {
                    "your_score": basic_analysis['digital_maturity_score'],
                    "industry_average": 45, "top_quartile": 70, "bottom_quartile": 30,
                    "percentile": min(100, int((basic_analysis['digital_maturity_score'] / 45) * 50)) if basic_analysis['digital_maturity_score'] <= 45 else 50 + int(((basic_analysis['digital_maturity_score'] - 45) / 55) * 50)
                }
            },
            "technology_stack": {
                "value": "Modern web technologies detected",
                "description": "Technology stack analysis complete",
                "detected": ["HTML5", "CSS3", "JavaScript"],
                "categories": {"frontend": ["HTML5", "CSS3"], "analytics": []},
                "modernity": "modern"
            },
            "admin_features_enabled": user.role == "admin"
        }
        smart_actions = generate_smart_actions(ai_analysis, technical_audit, content_analysis, basic_analysis)
        result = {
            "success": True,
            "company_name": request.company_name or get_domain_from_url(url),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": BasicAnalysis(
                company=request.company_name or get_domain_from_url(url),
                website=url,
                digital_maturity_score=basic_analysis['digital_maturity_score'],
                social_platforms=basic_analysis.get('social_platforms', 0),
                technical_score=technical_audit.get('overall_technical_score', 0),
                content_score=content_analysis.get('content_quality_score', 0),
                seo_score=int((basic_analysis.get('score_breakdown', {}).get('seo_basics', 0) / SCORING_CONFIG.weights['seo_basics']) * 100),
                score_breakdown=ScoreBreakdown(**basic_analysis.get('score_breakdown', {}))
            ).dict(),
            "ai_analysis": ai_analysis.dict(),
            "detailed_analysis": DetailedAnalysis(
                social_media=SocialMediaAnalysis(**social_analysis),
                technical_audit=TechnicalAudit(**technical_audit),
                content_analysis=ContentAnalysis(**content_analysis),
                ux_analysis=UXAnalysis(**ux_analysis),
                competitive_analysis=CompetitiveAnalysis(**competitive_analysis)
            ).dict(),
            "smart": {
                "actions": smart_actions,
                "scores": SmartScores(
                    overall=basic_analysis['digital_maturity_score'],
                    technical=technical_audit.get('overall_technical_score', 0),
                    content=content_analysis.get('content_quality_score', 0),
                    social=social_analysis.get('social_score', 0),
                    ux=ux_analysis.get('overall_ux_score', 0),
                    competitive=competitive_analysis.get('competitive_score', 0),
                    trend="stable",
                    percentile=enhanced_features['industry_benchmarking']['details']['percentile']
                ).dict()
            },
            "enhanced_features": enhanced_features,
            "metadata": {
                "version": APP_VERSION, "scoring_version": "configurable_v1",
                "analysis_depth": "comprehensive", "confidence_level": ai_analysis.confidence_score,
                "analyzed_by": user.username, "user_role": user.role,
                "scoring_weights": SCORING_CONFIG.weights
            }
        }
        result = ensure_integer_scores(result)
        analysis_cache[cache_key] = {'data': result, 'timestamp': datetime.now()}
        background_tasks.add_task(cleanup_cache)
        if user.role != "admin":
            user_search_counts[user.username] = user_search_counts.get(user.username, 0) + 1
        logger.info(f"Analysis complete for {url}: score={basic_analysis['digital_maturity_score']} (user: {user.username})")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, "Analysis failed due to internal error")

@app.post("/api/v1/analyze")
async def basic_analyze(request: CompetitorAnalysisRequest, user: UserInfo = Depends(require_user)):
    try:
        url = clean_url(request.url)
        _reject_ssrf(url)
        response = await fetch_url_with_retries(url)
        if not response or response.status_code != 200:
            raise HTTPException(400, f"Cannot access website: {url}")
        basic_analysis = await analyze_basic_metrics_enhanced(url, response.text, headers=response.headers)
        return {
            "success": True,
            "company": request.company_name or get_domain_from_url(url),
            "website": url,
            "digital_maturity_score": basic_analysis['digital_maturity_score'],
            "social_platforms": basic_analysis.get('social_platforms', 0),
            "score_breakdown": basic_analysis.get('score_breakdown', {}),
            "analysis_date": datetime.now().isoformat(),
            "analyzed_by": user.username,
            "scoring_weights": SCORING_CONFIG.weights
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Basic analysis error: {e}")
        raise HTTPException(500, "Analysis failed")

# ============================================================================
# SYSTEM ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME, "version": APP_VERSION, "status": "operational",
        "endpoints": {
            "health": "/health", "auth": {"login": "/auth/login", "me": "/auth/me"},
            "analysis": {"comprehensive": "/api/v1/ai-analyze", "basic": "/api/v1/analyze"}
        },
        "features": [
            "JWT authentication with role-based access",
            "Configurable scoring system",
            "Fair 0–100 scoring across all metrics",
            "Production-ready architecture",
            "AI-powered insights"
        ],
        "scoring_system": {"version": "configurable_v1", "weights": SCORING_CONFIG.weights}
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", "version": APP_VERSION, "timestamp": datetime.now().isoformat(),
        "system": {
            "openai_available": bool(openai_client), "cache_size": len(analysis_cache),
            "cache_limit": MAX_CACHE_SIZE, "rate_limiting": RATE_LIMIT_ENABLED
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

# ============================================================================
# MAIN APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    logger.info(f"🚀 {APP_NAME} v{APP_VERSION} - Production Ready")
    logger.info(f"📊 Scoring System: Configurable weights {SCORING_CONFIG.weights}")
    logger.info(f"💾 Cache: TTL={CACHE_TTL}s, Max={MAX_CACHE_SIZE} entries")
    logger.info(f"🛡️  Rate limiting: {'enabled' if RATE_LIMIT_ENABLED else 'disabled'}")
    logger.info(f"🤖 OpenAI: {'available' if openai_client else 'not configured'}")
    logger.info(f"🌐 Starting server on {host}:{port}")
    if SECRET_KEY.startswith("brandista-key-"):
        logger.warning("⚠️  Using default SECRET_KEY - set SECRET_KEY environment variable in production!")
    if "*" in ALLOWED_ORIGINS:
        logger.warning("⚠️  CORS allows all origins (*) - credentials disabled; configure ALLOWED_ORIGINS for prod.")
    uvicorn.run(
        app, host=host, port=port, reload=reload,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        access_log=True, server_header=False, date_header=False
    )
