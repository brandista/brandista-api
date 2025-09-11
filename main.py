#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 5.2.3 - Fixed for React Frontend
"""

from __future__ import annotations

# ============================================================================
# IMPORTS
# ============================================================================
import os
import re
import hashlib
import logging
import asyncio
import random
import secrets
import time
import base64
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ============================================================================
# CONFIG
# ============================================================================
APP_VERSION = "5.2.3"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """
Complete scoring system with enhanced features — fair and accurate website analysis
with 0–100 scoring across all metrics. No arbitrary baselines. English-only output.
"""

CACHE_TTL = 3600
MAX_CACHE_SIZE = 50
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fi,en-US;q=0.7,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}

SCORING_WEIGHTS = {
    "security": 15,
    "seo_basics": 20,
    "content": 20,
    "technical": 15,
    "mobile": 15,
    "social": 10,
    "performance": 5,
}

# Auth config
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
TOKEN_EXPIRE_HOURS = 24

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("brandista_api.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)
logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

# ============================================================================
# FASTAPI APP
# ============================================================================
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware - CRITICAL FOR FRONTEND
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: ["https://your-frontend-domain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# OPTIONAL DEPENDENCIES
# ============================================================================
# Playwright (optional, JS-heavy sites)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

openai_client = None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info(f"OpenAI client initialized (model={OPENAI_MODEL})")
    except Exception as e:
        logger.warning(f"OpenAI init failed: {e}")
        openai_client = None

# ============================================================================
# GLOBAL STATE
# ============================================================================
analysis_cache: Dict[str, Dict[str, Any]] = {}

# ============================================================================
# AUTH MODELS
# ============================================================================
class LoginRequest(BaseModel):
    password: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    role: str
    token_type: str = "bearer"

class UserInfo(BaseModel):
    role: str

# ============================================================================
# AUTH FUNCTIONS
# ============================================================================
def create_token(user_id: str, role: str, expire_hours: int = TOKEN_EXPIRE_HOURS) -> str:
    """Create a simple signed token"""
    expire = int(time.time()) + (expire_hours * 3600)
    payload = f"{user_id}|{role}|{expire}"
    signature = hmac.new(
        SECRET_KEY.encode(), 
        payload.encode(), 
        digestmod="sha256"
    ).hexdigest()
    token_str = f"{payload}|{signature}"
    return base64.urlsafe_b64encode(token_str.encode()).decode()

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode token"""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split("|")
        if len(parts) != 4:
            return None
        
        user_id, role, expire, signature = parts
        payload = f"{user_id}|{role}|{expire}"
        
        expected_sig = hmac.new(
            SECRET_KEY.encode(), 
            payload.encode(), 
            digestmod="sha256"
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        if int(expire) < int(time.time()):
            return None
        
        return {"user_id": user_id, "role": role, "exp": int(expire)}
    except Exception:
        return None

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Get current user from request headers"""
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.split(" ", 1)[1]
    return verify_token(token)

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================
@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest = LoginRequest()):
    """Handle user and admin login"""
    
    # Admin login with password
    if request.password:
        if request.password == ADMIN_PASSWORD:
            user_id = f"admin-{secrets.token_hex(6)}"
            token = create_token(user_id, "admin")
            logger.info("Admin login successful")
            return TokenResponse(
                access_token=token,
                role="admin",
                token_type="bearer"
            )
        else:
            logger.warning("Failed admin login attempt")
            raise HTTPException(401, "Invalid admin password")
    
    # User login without password
    user_id = f"user-{secrets.token_hex(6)}"
    token = create_token(user_id, "user")
    logger.info("User login successful")
    return TokenResponse(
        access_token=token,
        role="user",
        token_type="bearer"
    )

@app.get("/auth/me", response_model=UserInfo)
async def get_me(request: Request):
    """Get current user info"""
    user = get_current_user(request)
    
    if not user:
        raise HTTPException(401, "Not authenticated")
    
    return UserInfo(role=user.get("role", "user"))

@app.post("/auth/logout")
async def logout():
    """Logout endpoint (token invalidation happens client-side)"""
    return {"message": "Logged out successfully"}# ============================================================================
# PYDANTIC MODELS
# ============================================================================
class CompetitorAnalysisRequest(BaseModel):
    url: str = Field(..., description="Website URL to analyze", example="https://example.com")
    company_name: Optional[str] = Field(None, max_length=120)
    analysis_type: str = Field("comprehensive", description="basic | comprehensive")
    language: str = Field("en", pattern=r"^(en)$")
    include_ai: bool = True
    include_social: bool = True

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
    digital_maturity_score: int = Field(..., ge=0, le=100)
    social_platforms: int = 0
    technical_score: int = 0
    content_score: int = 0
    seo_score: int = 0
    score_breakdown: ScoreBreakdown
    analysis_timestamp: datetime = Field(default_factory=datetime.now)

class TechnicalAudit(BaseModel):
    has_ssl: bool = False
    has_mobile_optimization: bool = False
    page_speed_score: int = 0
    has_analytics: bool = False
    has_sitemap: bool = False
    has_robots_txt: bool = False
    meta_tags_score: int = 0
    overall_technical_score: int = 0
    security_headers: Dict[str, bool] = Field(default_factory=dict)
    performance_indicators: List[str] = Field(default_factory=list)

class ContentAnalysis(BaseModel):
    word_count: int = 0
    readability_score: int = 0
    keyword_density: Dict[str, float] = Field(default_factory=dict)
    content_freshness: str = Field("unknown", pattern=r"^(very_fresh|fresh|moderate|dated|unknown)$")
    has_blog: bool = False
    content_quality_score: int = 0
    media_types: List[str] = Field(default_factory=list)
    interactive_elements: List[str] = Field(default_factory=list)

class SocialMediaAnalysis(BaseModel):
    platforms: List[str] = Field(default_factory=list)
    total_followers: int = 0
    engagement_rate: float = 0.0
    posting_frequency: str = "unknown"
    social_score: int = 0
    has_sharing_buttons: bool = False
    open_graph_tags: int = 0
    twitter_cards: bool = False

class UXAnalysis(BaseModel):
    navigation_score: int = 0
    visual_design_score: int = 0
    accessibility_score: int = 0
    mobile_ux_score: int = 0
    overall_ux_score: int = 0
    accessibility_issues: List[str] = Field(default_factory=list)
    navigation_elements: List[str] = Field(default_factory=list)
    design_frameworks: List[str] = Field(default_factory=list)

class CompetitiveAnalysis(BaseModel):
    market_position: str = "unknown"
    competitive_advantages: List[str] = Field(default_factory=list)
    competitive_threats: List[str] = Field(default_factory=list)
    market_share_estimate: str = "Data not available"
    competitive_score: int = 0
    industry_comparison: Dict[str, Any] = Field(default_factory=dict)

class AIInsight(BaseModel):
    category: str
    insight: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    priority: str = Field("medium", pattern=r"^(critical|high|medium|low)$")

class AIAnalysis(BaseModel):
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    threats: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    confidence_score: int = 0
    sentiment_score: float = 0.0
    key_metrics: Dict[str, Any] = Field(default_factory=dict)
    action_priority: List[AIInsight] = Field(default_factory=list)

class SmartAction(BaseModel):
    title: str
    description: str
    priority: str = Field(..., pattern=r"^(critical|high|medium|low)$")
    effort: str = Field(..., pattern=r"^(low|medium|high)$")
    impact: str = Field(..., pattern=r"^(low|medium|high|critical)$")
    estimated_score_increase: int = Field(0, ge=0, le=100)
    category: str = ""
    estimated_time: str = ""

class SmartScores(BaseModel):
    overall: int = 0
    technical: int = 0
    content: int = 0
    social: int = 0
    ux: int = 0
    competitive: int = 0
    trend: str = "stable"
    percentile: int = 0

class DetailedAnalysis(BaseModel):
    social_media: SocialMediaAnalysis
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    competitive_analysis: CompetitiveAnalysis

class EnhancedFeatures(BaseModel):
    industry_benchmarking: Dict[str, Any] = Field(default_factory=dict)
    competitor_gaps: Dict[str, Any] = Field(default_factory=dict)
    growth_opportunities: Dict[str, Any] = Field(default_factory=dict)
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)
    market_trends: Dict[str, Any] = Field(default_factory=dict)
    technology_stack: Dict[str, Any] = Field(default_factory=dict)
    estimated_traffic_rank: Dict[str, Any] = Field(default_factory=dict)
    mobile_first_index_ready: Dict[str, Any] = Field(default_factory=dict)
    core_web_vitals_assessment: Dict[str, Any] = Field(default_factory=dict)

class AnalysisResponse(BaseModel):
    success: bool
    company_name: str
    analysis_date: str
    basic_analysis: BasicAnalysis
    ai_analysis: AIAnalysis
    detailed_analysis: DetailedAnalysis
    smart: Dict[str, Any] = Field(default_factory=dict)
    enhanced_features: Optional[EnhancedFeatures] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def ensure_integer_scores(data: Any) -> Any:
    if isinstance(data, dict):
        for k, v in list(data.items()):
            if isinstance(v, (int, float)) and (k == "score" or k.endswith("_score")):
                data[k] = int(round(v))
            elif isinstance(v, dict):
                ensure_integer_scores(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        ensure_integer_scores(item)
    return data

def get_cache_key(url: str, analysis_type: str = "basic") -> str:
    return hashlib.md5(f"{url}_{analysis_type}_{APP_VERSION}".encode()).hexdigest()

def is_cache_valid(ts: datetime) -> bool:
    return (datetime.now() - ts).total_seconds() < CACHE_TTL

def get_domain_from_url(url: str) -> str:
    p = urlparse(url)
    return p.netloc or p.path.split("/")[0]

def clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")

# ============================================================================
# FETCH FUNCTIONS
# ============================================================================
class SimpleResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

async def fetch_url_basic_text(url: str, timeout: int = REQUEST_TIMEOUT, retries: int = MAX_RETRIES) -> Optional[str]:
    for attempt in range(retries):
        try:
            if attempt:
                await asyncio.sleep(min(6, 2 ** attempt) + random.uniform(0, 0.4))
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                r = await client.get(url, headers=DEFAULT_HEADERS)
                if r.status_code == 200:
                    return r.text
                if r.status_code in (403, 429) and attempt < retries - 1:
                    continue
                if r.status_code == 404:
                    return None
        except Exception as e:
            logger.warning(f"fetch attempt {attempt+1} failed for {url}: {e}")
    return None

async def fetch_url_with_browser(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    if not PLAYWRIGHT_AVAILABLE:
        return await fetch_url_basic_text(url, timeout)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page()
            await page.set_extra_http_headers(DEFAULT_HEADERS)
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            await page.wait_for_timeout(1200)
            html = await page.content()
            await browser.close()
            return html
    except Exception as e:
        logger.warning(f"browser fetch failed for {url}: {e}")
        return await fetch_url_basic_text(url, timeout)

async def fetch_url(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[SimpleResponse]:
    js_heavy = ("bmw.", "mercedes-benz.", "audi.", "tesla.com", "volvo.", "volkswagen.")
    domain = get_domain_from_url(url).lower()
    use_browser = any(d in domain for d in js_heavy)
    html = await (fetch_url_with_browser(url, timeout) if use_browser else fetch_url_basic_text(url, timeout))
    if html:
        return SimpleResponse(html, 200)
    return None

# ============================================================================
# HTML HELPERS
# ============================================================================
def extract_clean_text(soup: BeautifulSoup) -> str:
    for e in soup(["script", "style", "noscript"]):
        e.decompose()
    text = soup.get_text(" ")
    lines = (line.strip() for line in text.splitlines())
    chunks = (p.strip() for line in lines for p in line.split("  "))
    return " ".join(c for c in chunks if c)

def check_clean_urls(url: str) -> bool:
    if "?" in url and "=" in url:
        return False
    if any(ext in url for ext in [".php", ".asp", ".jsp"]):
        return False
    if "__" in url or url.count("_") > 3:
        return False
    return True

def check_security_headers(html: str) -> Dict[str, bool]:
    hl = html.lower()
    return {
        "csp": "content-security-policy" in hl,
        "x_frame_options": "x-frame-options" in hl,
        "strict_transport": "strict-transport-security" in hl,
    }

def check_content_freshness(soup: BeautifulSoup, html: str) -> int:
    score = 0
    year = datetime.now().year
    pats = [rf"{year}", rf"{year-1}", r"\d{4}-\d{2}-\d{2}", r"\d{1,2}\.\d{1,2}\.\d{4}"]
    recent = 0
    for ptn in pats[:2]:
        if re.search(ptn, html):
            recent += 1
    score += 3 if recent >= 2 else 2 if recent == 1 else 0
    mod = soup.find("meta", attrs={"property": "article:modified_time"}) or soup.find("meta", attrs={"name": "last-modified"})
    if mod:
        score += 2
    return min(5, score)

def analyze_image_optimization(soup: BeautifulSoup) -> Dict[str, Any]:
    imgs = soup.find_all("img")
    if not imgs:
        return {"score": 0, "total_images": 0, "optimized_images": 0, "optimization_ratio": 0}
    optimized = 0
    for img in imgs:
        s = 0
        if img.get("alt", "").strip():
            s += 1
        if img.get("loading") == "lazy":
            s += 1
        src = img.get("src", "").lower()
        if any(fmt in src for fmt in (".webp", ".avif")):
            s += 1
        if img.get("srcset"):
            s += 1
        if s >= 2:
            optimized += 1
    ratio = optimized / len(imgs)
    return {"score": int(ratio * 5), "total_images": len(imgs), "optimized_images": optimized, "optimization_ratio": ratio}

def analyze_structured_data(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    score = 0
    types = []
    if soup.find_all("script", type="application/ld+json"):
        score += 3
        types.append("JSON-LD")
        if len(soup.find_all("script", type="application/ld+json")) > 1:
            score += 1
    if soup.find_all(attrs={"itemscope": True}):
        score += 1
        types.append("Microdata")
    if soup.find_all(attrs={"typeof": True}):
        score += 1
        types.append("RDFa")
    if len(soup.find_all("meta", property=re.compile("^og:"))) >= 4:
        score += 1
        types.append("Open Graph")
    return {"score": min(5, score), "types": types, "has_structured_data": bool(types)}

def detect_analytics_tools(html: str) -> Dict[str, Any]:
    tools = []
    pats = {
        "Google Analytics": ["google-analytics", "gtag", "ga.js"],
        "Google Tag Manager": ["googletagmanager", "gtm.js"],
        "Matomo": ["matomo", "piwik"],
        "Plausible": ["plausible"],
        "Hotjar": ["hotjar"],
        "Facebook Pixel": ["fbevents.js", "facebook.*pixel"],
        "Microsoft Clarity": ["clarity.ms"],
    }
    hl = html.lower()
    for tool, arr in pats.items():
        if any(p in hl for p in arr):
            tools.append(tool)
    return {"has_analytics": bool(tools), "tools": tools, "count": len(tools)}

def check_sitemap_indicators(soup: BeautifulSoup) -> bool:
    if soup.find("link", {"rel": "sitemap"}):
        return True
    for a in soup.find_all("a", href=True):
        if "sitemap" in a["href"].lower():
            return True
    return False

def check_robots_indicators(html: str) -> bool:
    return "robots.txt" in html.lower()

def analyze_performance_indicators(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    score = 0
    hints = []
    hl = html.lower()
    if ".min.js" in hl or ".min.css" in hl:
        score += 1; hints.append("minification")
    if any(c in hl for c in ["cdn.", "cloudflare", "akamai", "fastly"]):
        score += 1; hints.append("CDN")
    if any(b in hl for b in ["webpack", "vite", "parcel"]):
        score += 1; hints.append("modern_bundler")
    if soup.find("link", {"rel": "preconnect"}):
        score += 1; hints.append("preconnect")
    if soup.find("link", {"rel": re.compile("^pre(load|fetch)$")}):
        score += 1; hints.append("prefetch/preload")
    return {"score": min(5, score), "indicators": hints}

def check_responsive_design(html: str) -> Dict[str, Any]:
    hl = html.lower()
    score = 0
    indicators = []
    if '@media' in hl:
        c = hl.count('@media')
        if c >= 5:
            score += 3
        elif c >= 2:
            score += 2
        else:
            score += 1
        indicators.append(f'{c} media queries')
    for fw, pts in {'bootstrap': 2, 'tailwind': 2, 'foundation': 1, 'bulma': 1}.items():
        if fw in hl:
            score += pts
            indicators.append(fw)
            break
    if 'display: flex' in hl or 'display:flex' in hl:
        score += 1
        indicators.append('flexbox')
    if 'display: grid' in hl or 'display:grid' in hl:
        score += 1
        indicators.append('css grid')
    return {'score': min(7, score), 'indicators': indicators}

def estimate_page_speed(soup: BeautifulSoup, html: str) -> int:
    score = 0
    size = len(html)
    if size < 50_000: score += 5
    elif size < 100_000: score += 4
    elif size < 200_000: score += 2
    elif size < 500_000: score += 1
    if ".min.js" in html or ".min.css" in html: score += 2
    if "lazy" in html.lower(): score += 2
    if any(x in html.lower() for x in ["webpack", "vite"]): score += 1
    if any(p in html.lower() for p in ["cdn.", "cloudflare", "akamai"]): score += 3
    if soup.find("link", {"rel": "preconnect"}): score += 1
    if soup.find("link", {"rel": "preload"}): score += 1
    return min(15, score)

def calculate_readability_score(text: str) -> int:
    words = text.split()
    sentences = [s for s in text.split(".") if s.strip()]
    if not sentences or len(words) < 100:
        return 50
    avg = len(words) / len(sentences)
    if avg <= 8: return 40
    if avg <= 15: return 90
    if avg <= 20: return 70
    if avg <= 25: return 50
    return 30

def get_freshness_label(score: int) -> str:
    if score >= 4: return "very_fresh"
    if score >= 3: return "fresh"
    if score >= 2: return "moderate"
    if score >= 1: return "dated"
    return "unknown"# ============================================================================
# CORE ANALYSIS FUNCTIONS
# ============================================================================
async def analyze_basic_metrics(url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    score_components = {
        "security": 0, "seo_basics": 0, "content": 0,
        "technical": 0, "mobile": 0, "social": 0, "performance": 0
    }
    details: Dict[str, Any] = {}

    # SECURITY (15)
    if url.startswith("https://"):
        score_components["security"] += 10
        details["https"] = True
        sh = check_security_headers(html)
        if sh["csp"]: score_components["security"] += 2
        if sh["x_frame_options"]: score_components["security"] += 1
        if sh["strict_transport"]: score_components["security"] += 2
    else:
        details["https"] = False

    # SEO BASICS (20)
    title = soup.find("title")
    if title:
        t = title.get_text().strip(); L = len(t)
        if 30 <= L <= 60: score_components["seo_basics"] += 5
        elif 20 <= L < 30 or 60 < L <= 70: score_components["seo_basics"] += 3
        elif L > 0: score_components["seo_basics"] += 1
        details["title_length"] = L
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        d = meta_desc.get("content", "").strip(); l2 = len(d)
        if 120 <= l2 <= 160: score_components["seo_basics"] += 5
        elif 80 <= l2 < 120 or 160 < l2 <= 200: score_components["seo_basics"] += 3
        elif l2 > 0: score_components["seo_basics"] += 1
        details["meta_desc_length"] = l2
    h1_tags = soup.find_all("h1")
    h2_tags = soup.find_all("h2")
    h3_tags = soup.find_all("h3")
    if len(h1_tags) == 1: score_components["seo_basics"] += 3
    elif len(h1_tags) in [2, 3]: score_components["seo_basics"] += 1
    if len(h2_tags) >= 2: score_components["seo_basics"] += 1
    if len(h3_tags) >= 1: score_components["seo_basics"] += 1
    if soup.find("link", {"rel": "canonical"}):
        score_components["seo_basics"] += 2; details["has_canonical"] = True
    if soup.find("link", {"hreflang": True}):
        score_components["seo_basics"] += 1; details["has_hreflang"] = True
    if check_clean_urls(url): score_components["seo_basics"] += 2

    # CONTENT (20)
    text = extract_clean_text(soup)
    wc = len(text.split())
    if wc >= 2500: score_components["content"] += 10
    elif wc >= 1500: score_components["content"] += 7
    elif wc >= 800: score_components["content"] += 4
    elif wc >= 300: score_components["content"] += 2
    details["word_count"] = wc
    freshness = check_content_freshness(soup, html)
    score_components["content"] += freshness
    img_opt = analyze_image_optimization(soup)
    score_components["content"] += img_opt["score"]
    details["image_optimization"] = img_opt

    # TECHNICAL (15)
    sd = analyze_structured_data(soup, html)
    score_components["technical"] += sd["score"]; details["structured_data"] = sd
    analytics = detect_analytics_tools(html)
    if analytics["has_analytics"]:
        score_components["technical"] += 3; details["analytics"] = analytics["tools"]
    if check_sitemap_indicators(soup): score_components["technical"] += 1
    if check_robots_indicators(html): score_components["technical"] += 1
    perf = analyze_performance_indicators(soup, html)
    score_components["technical"] += perf["score"]; details["performance_indicators"] = perf

    # MOBILE (15)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport:
        vc = viewport.get("content", "")
        if "width=device-width" in vc: score_components["mobile"] += 5
        if "initial-scale=1" in vc: score_components["mobile"] += 3
        details["has_viewport"] = True
    else:
        details["has_viewport"] = False
    resp = check_responsive_design(html)
    score_components["mobile"] += resp["score"]; details["responsive_design"] = resp

    # SOCIAL (10)
    platforms = [p for p in ["facebook","instagram","linkedin","youtube","twitter","x.com","tiktok","pinterest"]
                 if re.search(p, html, re.I)]
    score_components["social"] += min(10, len(platforms))
    details["social_media"] = {"platforms": platforms, "score": min(10, len(platforms))}

    # PERFORMANCE (5)
    if len(html) < 100_000: score_components["performance"] += 2
    elif len(html) < 200_000: score_components["performance"] += 1
    if 'lazy' in html.lower() or 'loading="lazy"' in html: score_components["performance"] += 2
    if "webp" in html.lower(): score_components["performance"] += 1

    total = sum(score_components.values())
    final_score = max(0, min(100, total))

    return {
        "digital_maturity_score": final_score,
        "score_breakdown": score_components,
        "detailed_findings": details,
        "word_count": wc,
        "has_ssl": url.startswith("https"),
        "has_analytics": analytics.get("has_analytics", False),
        "has_mobile_viewport": bool(viewport),
        "title": title.get_text().strip() if title else "",
        "meta_description": meta_desc.get("content","") if meta_desc else "",
        "h1_count": len(h1_tags), "h2_count": len(h2_tags),
        "social_platforms": len(platforms),
    }

async def analyze_technical_aspects(url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    tech_score = 0

    # SSL (20)
    has_ssl = url.startswith("https")
    if has_ssl: tech_score += 20

    # Mobile (20)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    has_mobile = False
    if viewport:
        vc = viewport.get("content","")
        if "width=device-width" in vc:
            has_mobile = True; tech_score += 15
        if "initial-scale=1" in vc: tech_score += 5

    # Analytics (10)
    analytics = detect_analytics_tools(html)
    if analytics["has_analytics"]: tech_score += 10

    # Meta (15)
    meta_score = 0
    title = soup.find("title")
    if title:
        L = len(title.get_text().strip())
        if 30 <= L <= 60: meta_score += 8
        elif 20 <= L < 30 or 60 < L <= 70: meta_score += 5
        elif L > 0: meta_score += 2
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        dL = len(meta_desc.get("content",""))
        if 120 <= dL <= 160: meta_score += 7
        elif 80 <= dL < 120 or 160 < dL <= 200: meta_score += 4
        elif dL > 0: meta_score += 2
    tech_score += meta_score

    # Page speed (15)
    ps = estimate_page_speed(soup, html)
    tech_score += ps

    # Structured data (10)
    sd = analyze_structured_data(soup, html)
    tech_score += sd["score"] * 2

    # Security headers (10)
    sh = check_security_headers(html)
    if sh["csp"]: tech_score += 4
    if sh["x_frame_options"]: tech_score += 3
    if sh["strict_transport"]: tech_score += 3

    final = max(0, min(100, tech_score))
    return {
        "has_ssl": has_ssl,
        "has_mobile_optimization": has_mobile,
        "page_speed_score": int(ps * (100/15)),
        "has_analytics": analytics["has_analytics"],
        "has_sitemap": check_sitemap_indicators(soup),
        "has_robots_txt": check_robots_indicators(html),
        "meta_tags_score": int(meta_score * (100/15)),
        "overall_technical_score": final,
        "security_headers": sh,
        "performance_indicators": analyze_performance_indicators(soup, html)["indicators"],
    }

async def analyze_content_quality(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = extract_clean_text(soup)
    wc = len(text.split())
    score = 0
    media_types: List[str] = []
    interactive: List[str] = []

    # Volume (30)
    if wc >= 3000: score += 30
    elif wc >= 2000: score += 25
    elif wc >= 1500: score += 20
    elif wc >= 1000: score += 15
    elif wc >= 500: score += 8
    elif wc >= 200: score += 3

    # Structure (15)
    if soup.find_all("h2"): score += 5
    if soup.find_all("h3"): score += 3
    if soup.find_all(["ul","ol"]): score += 4
    if soup.find_all("table"): score += 3

    # Freshness (15)
    fresh = check_content_freshness(soup, html)
    score += fresh * 3

    # Media (15)
    if soup.find_all("img"): score += 5; media_types.append("images")
    if soup.find_all("video") or "youtube" in html.lower(): score += 5; media_types.append("video")
    if soup.find_all("audio") or "podcast" in html.lower(): score += 5; media_types.append("audio")

    # Interactivity (10)
    if soup.find_all("form"): score += 5; interactive.append("forms")
    if soup.find_all("button"): score += 3; interactive.append("buttons")
    if soup.find_all("input", {"type":"search"}): score += 2; interactive.append("search")

    # Blog (10)
    blog_patterns = ["/blog", "/news", "/articles", "/insights"]
    has_blog = any(soup.find("a", href=re.compile(p, re.I)) for p in blog_patterns)
    if has_blog: score += 10

    # Readability (5)
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    if sentences and wc > 100:
        avg = wc / len(sentences)
        if 10 <= avg <= 20: score += 5
        elif 8 <= avg < 10 or 20 < avg <= 25: score += 3
        elif avg < 30: score += 1

    final = max(0, min(100, score))
    return {
        "word_count": wc,
        "readability_score": calculate_readability_score(text),
        "keyword_density": {},
        "content_freshness": get_freshness_label(fresh),
        "has_blog": has_blog,
        "content_quality_score": final,
        "media_types": media_types,
        "interactive_elements": interactive,
    }# ============================================================================
# UX + SOCIAL + COMPETITIVE ANALYSIS
# ============================================================================
def calculate_navigation_score(soup: BeautifulSoup) -> int:
    score = 0
    if soup.find("nav"): score += 20
    if soup.find("header"): score += 10
    if soup.find_all(["ul","ol"], class_=re.compile("nav|menu", re.I)): score += 20
    if soup.find(class_=re.compile("breadcrumb", re.I)): score += 15
    if soup.find("input", type="search") or soup.find("input", placeholder=re.compile("search", re.I)): score += 15
    if (footer := soup.find("footer")) and footer.find_all("a"): score += 10
    if soup.find("a", href=re.compile("sitemap", re.I)): score += 10
    return min(100, score)

def calculate_design_score(soup: BeautifulSoup, html: str) -> int:
    score = 0; hl = html.lower()
    for fw, pts in {"tailwind": 25, "bootstrap": 20, "material": 20, "bulma": 15, "foundation": 15}.items():
        if fw in hl: score += pts; break
    if "display: flex" in hl or "display:flex" in hl: score += 10
    if "display: grid" in hl or "display:grid" in hl: score += 10
    if "@media" in hl: score += 10
    if "transition" in hl or "animation" in hl: score += 10
    if "transform" in hl: score += 5
    if "--" in hl and ":root" in hl: score += 10
    if any(x in hl for x in ["fontawesome","material-icons","feather"]): score += 10
    if "dark-mode" in hl or "dark-theme" in hl: score += 10
    return min(100, score)

def calculate_accessibility_score(soup: BeautifulSoup) -> int:
    score = 0
    if soup.find("html", lang=True): score += 10
    imgs = soup.find_all("img")
    if imgs:
        with_alt = [i for i in imgs if i.get("alt","").strip()]
        score += int((len(with_alt) / len(imgs)) * 25)
    else:
        score += 25
    forms = soup.find_all("form")
    if forms:
        labels = soup.find_all("label")
        inputs = soup.find_all(["input","select","textarea"])
        if labels and inputs:
            score += int(min(1, len(labels) / len(inputs)) * 20)
    else:
        score += 20
    if soup.find_all(attrs={"role": True}): score += 10
    if soup.find_all(attrs={"aria-label": True}): score += 5
    if soup.find_all(attrs={"aria-describedby": True}): score += 5
    semantic = ["main","article","section","aside","nav","header","footer"]
    score += min(15, sum(1 for t in semantic if soup.find(t)) * 3)
    if soup.find("a", href=re.compile("#main|#content|#skip", re.I)): score += 10
    return min(100, score)

def calculate_mobile_ux_score(soup: BeautifulSoup, html: str) -> int:
    score = 0; hl = html.lower()
    vp = soup.find("meta", attrs={"name": "viewport"})
    if vp:
        vc = vp.get("content","")
        if "width=device-width" in vc: score += 20
        if "initial-scale=1" in vc: score += 10
    c = hl.count("@media")
    if c >= 5: score += 30
    elif c >= 3: score += 20
    elif c >= 1: score += 10
    if "touch" in hl or "swipe" in hl: score += 15
    if soup.find("meta", attrs={"name":"apple-mobile-web-app-capable"}): score += 5
    if soup.find("meta", attrs={"name":"mobile-web-app-capable"}): score += 5
    if "font-size" in hl:
        if "rem" in hl or "em" in hl: score += 10
        if "clamp" in hl or "vw" in hl: score += 5
    return min(100, score)

async def analyze_ux_elements(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    nav = calculate_navigation_score(soup)
    design = calculate_design_score(soup, html)
    a11y = calculate_accessibility_score(soup)
    mobile = calculate_mobile_ux_score(soup, html)
    overall = int((nav + design + a11y + mobile) / 4)

    nav_elements = []
    if soup.find("nav"): nav_elements.append("main_navigation")
    if soup.find(class_=re.compile("breadcrumb", re.I)): nav_elements.append("breadcrumbs")
    if soup.find("input", type="search"): nav_elements.append("search")
    if soup.find("footer"): nav_elements.append("footer_navigation")

    frameworks = []
    hl = html.lower()
    if "bootstrap" in hl: frameworks.append("Bootstrap")
    if "tailwind" in hl: frameworks.append("Tailwind")
    if "material" in hl: frameworks.append("Material Design")

    issues = []
    if not soup.find("html", lang=True): issues.append("Missing language attribute")
    imgs = soup.find_all("img")
    if imgs:
        no_alt = [img for img in imgs if not img.get("alt","").strip()]
        if no_alt: issues.append(f"{len(no_alt)} images missing alt text")
    if not soup.find("a", href=re.compile("#main|#content|#skip", re.I)):
        issues.append("No skip navigation link")

    return {
        "navigation_score": nav,
        "visual_design_score": design,
        "accessibility_score": a11y,
        "mobile_ux_score": mobile,
        "overall_ux_score": overall,
        "accessibility_issues": issues,
        "navigation_elements": nav_elements,
        "design_frameworks": frameworks,
    }

async def analyze_social_media_presence(url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    score = 0
    platforms: List[str] = []
    weights = {"facebook":15,"instagram":15,"linkedin":12,"youtube":12,"twitter/x":10,"tiktok":10,"pinterest":5,"snapchat":3}
    patterns = {
        "facebook": r"facebook\.com/[^/\s\"']+",
        "instagram": r"instagram\.com/[^/\s\"']+",
        "linkedin": r"linkedin\.com/(company|in)/[^/\s\"']+",
        "youtube": r"youtube\.com/(@|channel|user|c)[^/\s\"']+",
        "twitter/x": r"(twitter\.com|x\.com)/[^/\s\"']+",
        "tiktok": r"tiktok\.com/@[^/\s\"']+",
        "pinterest": r"pinterest\.\w+/[^/\s\"']+",
        "snapchat": r"snapchat\.com/add/[^/\s\"']+",
    }
    for platform, pat in patterns.items():
        if re.search(pat, html, re.I):
            platforms.append(platform); score += weights.get(platform, 5)
    has_sharing = any(p in html.lower() for p in ["addtoany","sharethis","addthis","social-share"])
    if has_sharing: score += 15
    og_count = len(soup.find_all("meta", property=re.compile("^og:")))
    if og_count >= 4: score += 10
    elif og_count >= 2: score += 5
    twitter_cards = bool(soup.find_all("meta", attrs={"name": re.compile("^twitter:")}))
    if twitter_cards: score += 5
    return {
        "platforms": platforms,
        "total_followers": 0,
        "engagement_rate": 0.0,
        "posting_frequency": "unknown",
        "social_score": min(100, score),
        "has_sharing_buttons": has_sharing,
        "open_graph_tags": og_count,
        "twitter_cards": twitter_cards,
    }

async def analyze_competitive_positioning(url: str, basic: Dict[str, Any]) -> Dict[str, Any]:
    score = basic.get("digital_maturity_score", 0)
    if score >= 75:
        position = "Digital Leader"
        advantages = ["Excellent digital presence", "Advanced technical execution", "Competitive user experience"]
        threats = ["Fast-followers copying features", "Pressure to innovate continuously"]
        comp_score = 85
    elif score >= 60:
        position = "Strong Performer"
        advantages = ["Solid digital foundation", "Good growth potential"]
        threats = ["Gap to market leaders", "Need for ongoing improvements"]
        comp_score = 70
    elif score >= 45:
        position = "Average Competitor"
        advantages = ["Baseline established", "Clear areas to improve"]
        threats = ["At risk of falling behind", "Increasing competitive pressure"]
        comp_score = 50
    elif score >= 30:
        position = "Below Average"
        advantages = ["Significant upside potential"]
        threats = ["Clear competitive disadvantage", "Risk of losing customers"]
        comp_score = 30
    else:
        position = "Digital Laggard"
        advantages = ["Opportunity for a major leap"]
        threats = ["Critical competitive handicap", "Threat to business continuity"]
        comp_score = 15

    return {
        "market_position": position,
        "competitive_advantages": advantages,
        "competitive_threats": threats,
        "market_share_estimate": "Data not available",
        "competitive_score": comp_score,
        "industry_comparison": {
            "your_score": score,
            "industry_average": 45,
            "top_quartile": 70,
            "bottom_quartile": 30,
        },
    }

# ============================================================================
# AI & ENHANCED FEATURES (Kopioi kaikki nämä funktiot alkuperäisestä)
# ============================================================================
def generate_english_insights(
    overall: int,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any]
) -> Dict[str, Any]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    # Tämä on pitkä funktio, kopioi se suoraan alkuperäisestä
    pass

async def generate_ai_insights(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any],
) -> AIAnalysis:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def generate_smart_actions(ai: AIAnalysis, technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def detect_technology_stack(html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def assess_mobile_first_readiness(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def estimate_core_web_vitals(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def detect_industry_from_content(domain: str, html: str) -> str:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def generate_market_trends(url: str = None, html: str = None, tech_stack: Dict = None) -> List[str]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def calculate_improvement_potential(basic: Dict[str, Any]) -> int:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def generate_competitor_gaps(basic: Dict[str, Any], competitive: Dict[str, Any]) -> List[str]:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

def estimate_traffic_rank(url: str, basic: Dict[str, Any]) -> str:
    # [KOPIOI ALKUPERÄISESTÄ KOODISTA]
    pass

# ============================================================================
# MAIN API ENDPOINTS
# ============================================================================
@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "login": "/auth/login",
            "me": "/auth/me",
            "logout": "/auth/logout",
            "basic_analysis": "/api/v1/analyze",
            "ai_analysis": "/api/v1/ai-analyze"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "openai_available": bool(openai_client),
        "cache_size": len(analysis_cache)
    }

@app.post("/api/v1/analyze")
async def basic_analyze(
    request: CompetitorAnalysisRequest,
    req: Request
):
    """Basic website analysis with authentication"""
    
    # Check authentication
    user = get_current_user(req)
    if not user:
        raise HTTPException(401, "Authentication required")
    
    try:
        url = clean_url(request.url)
        resp = await fetch_url(url)
        if not resp:
            raise HTTPException(400, "Cannot fetch website")
        
        basic = await analyze_basic_metrics(url, resp.text)
        
        return {
            "success": True,
            "company": request.company_name or "Unknown",
            "website": url,
            "digital_maturity_score": basic["digital_maturity_score"],
            "social_platforms": basic.get("social_platforms", 0),
            "score_breakdown": basic.get("score_breakdown", {}),
            "analysis_date": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Basic analysis error: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze(
    request: CompetitorAnalysisRequest,
    req: Request
):
    """AI-powered website analysis with authentication"""
    
    # Check authentication
    user = get_current_user(req)
    if not user:
        raise HTTPException(401, "Authentication required")
    
    user_role = user.get("role", "user")
    logger.info(f"Analysis requested by {user_role} for {request.url}")
    
    try:
        url = clean_url(request.url)
        cache_key = get_cache_key(url, "ai_v5_enhanced_enonly")
        
        if cache_key in analysis_cache and is_cache_valid(analysis_cache[cache_key]["timestamp"]):
            logger.info(f"Cache hit for {url}")
            return analysis_cache[cache_key]["data"]

        resp = await fetch_url(url)
        if not resp or resp.status_code != 200:
            raise HTTPException(400, f"Cannot fetch {url}")

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Run all analyses
        basic = await analyze_basic_metrics(url, html)
        technical = await analyze_technical_aspects(url, html)
        content = await analyze_content_quality(html)
        ux = await analyze_ux_elements(html)
        social = await analyze_social_media_presence(url, html)
        competitive = await analyze_competitive_positioning(url, basic)
        ai = await generate_ai_insights(url, basic, technical, content, ux, social)

        # [KOPIOI LOPUT ai_analyze FUNKTIOSTA ALKUPERÄISESTÄ KOODISTA]
        # Enhanced features, result building, etc.
        
    except Exception as e:
        logger.error(f"Analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    logger.info(f"{APP_NAME} v{APP_VERSION} starting on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
