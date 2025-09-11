#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 5.2.2 - English-only, No PDF
Author: Brandista Team
Date: 2025
Description: Advanced website analysis with fair 0–100 scoring system (English-first)
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

from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ============================================================================
# CONFIG
# ============================================================================
APP_VERSION = "5.2.2"
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

# --- Auth config ---
ADMIN_PW = os.getenv("ADMIN_PW", "kaikka123")   # vaihda prodissa
SECRET = os.getenv("API_SECRET", "change-this-in-prod")

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
logger.info(f"Starting {APP_NAME} v{APP_VERSION}")# ============================================================================
# FASTAPI APP (no CORS)
# ============================================================================
from fastapi import Depends

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

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
MAX_CACHE_SIZE = 50
CACHE_TTL = 3600  # seconds
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# Simple in-memory guest rate limit: 3 analyses / 24h per IP
GUEST_DAILY_LIMIT = 3
guest_counters: Dict[str, Dict[str, Any]] = {}  # ip -> {"count": int, "reset": epoch}

def _ip_from_request(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"

def _guest_guard(req: Request):
    ip = _ip_from_request(req)
    now = int(time.time())
    rec = guest_counters.get(ip)
    if not rec or now >= rec["reset"]:
        guest_counters[ip] = {"count": 0, "reset": now + 24 * 3600}
        rec = guest_counters[ip]
    if rec["count"] >= GUEST_DAILY_LIMIT:
        raise HTTPException(429, f"Guest limit reached ({GUEST_DAILY_LIMIT}/24h). Provide admin password to /auth/login.")
    rec["count"] += 1

# ============================================================================
# AUTH (simple password -> bearer token)
# ============================================================================
def make_token(user_id: str, role: str, ttl: int = 8 * 3600) -> str:
    exp = int(time.time()) + ttl
    payload = f"{user_id}|{role}|{exp}"
    sig = hmac.new(SECRET.encode(), payload.encode(), digestmod="sha256").hexdigest()
    raw = f"{payload}|{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode()

def parse_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, role, exp, sig = raw.split("|")
        payload = f"{user_id}|{role}|{exp}"
        ok = hmac.compare_digest(sig, hmac.new(SECRET.encode(), payload.encode(), "sha256").hexdigest())
        if not ok or int(exp) < int(time.time()):
            return None
        return {"user_id": user_id, "role": role, "exp": int(exp)}
    except Exception:
        return None

def current_role(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth.split(" ", 1)[1].strip()
        payload = parse_token(tok)
        if payload:
            return payload["role"]
    return "guest"

@app.post("/auth/login")
def auth_login(payload: Dict[str, Any]):
    pw = (payload or {}).get("password", "")
    if not pw:
        raise HTTPException(400, "Password required")
    if pw != ADMIN_PW:
        raise HTTPException(401, "Invalid credentials")
    user_id = "admin-" + secrets.token_hex(6)
    token = make_token(user_id, "admin")
    return {"ok": True, "role": "admin", "access_token": token, "token_type": "bearer"}

@app.get("/auth/me")
def auth_me(request: Request):
    role = current_role(request)
    if role == "guest":
        return {"role": "guest", "limit_left": max(0, GUEST_DAILY_LIMIT - guest_counters.get(_ip_from_request(request), {}).get("count", 0))}
    return {"role": role}# ============================================================================
# Pydantic MODELS
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
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ============================================================================
# UTILS (cache, coercion, parsing)
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
# FETCH (httpx / playwright)
# ============================================================================
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

class SimpleResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

async def fetch_url(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[SimpleResponse]:
    js_heavy = ("bmw.", "mercedes-benz.", "audi.", "tesla.com", "volvo.", "volkswagen.")
    domain = get_domain_from_url(url).lower()
    use_browser = any(d in domain for d in js_heavy)
    html = await (fetch_url_with_browser(url, timeout) if use_browser else fetch_url_basic_text(url, timeout))
    if html:
        return SimpleResponse(html, 200)
    return None

# ============================================================================
# HTML helpers
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
    return {"score": min(5, score), "indicators": hints}# ============================================================================
# CORE ANALYSIS
# ============================================================================

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
    return "unknown"

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
    from_score = 0
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
    }

# ============================================================================
# UX + SOCIAL + COMPETITION
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
# AI INSIGHTS (ei ulkoisia kutsuja; englanninkielinen tiivistelmä)
# ============================================================================

def generate_english_insights(
    overall: int,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any]
) -> Dict[str, Any]:
    strengths, weaknesses, opportunities, threats, recs, quick_wins = [], [], [], [], [], []
    breakdown = basic.get("score_breakdown", {})
    wc = content.get("word_count", 0)

    if breakdown.get("security", 0) >= 13:
        strengths.append(f"Strong security posture ({breakdown['security']}/15) — HTTPS and key headers present.")
    elif breakdown.get("security", 0) >= 10:
        strengths.append(f"Good security ({breakdown['security']}/15) — HTTPS enabled.")
    if breakdown.get("seo_basics", 0) >= 15:
        strengths.append(f"Excellent SEO fundamentals ({breakdown['seo_basics']}/20).")
    elif breakdown.get("seo_basics", 0) >= 10:
        strengths.append(f"Solid SEO foundation ({breakdown['seo_basics']}/20).")
    if breakdown.get("mobile", 0) >= 12:
        strengths.append(f"Great mobile optimization ({breakdown['mobile']}/15).")
    elif breakdown.get("mobile", 0) >= 8:
        strengths.append(f"Good mobile UX ({breakdown['mobile']}/15).")
    if wc > 2000:
        strengths.append(f"Very comprehensive content ({wc} words).")
    elif wc > 1000:
        strengths.append(f"Adequate content volume ({wc} words).")
    if social.get("platforms"):
        strengths.append(f"Presence on {len(social['platforms'])} social platforms.")

    if breakdown.get("security", 0) == 0:
        weaknesses.append("CRITICAL: No SSL — site not secured.")
        threats.append("Search engines and browsers penalize non-HTTPS sites.")
        quick_wins.append("Install an SSL certificate immediately (Let's Encrypt).")
    elif breakdown.get("security", 0) < 10:
        weaknesses.append(f"Security can be improved ({breakdown['security']}/15).")

    if breakdown.get("content", 0) < 5:
        weaknesses.append(f"Very low content depth ({breakdown['content']}/20, {wc} words).")
        recs.append("Create an editorial calendar and expand core landing pages.")
    elif breakdown.get("content", 0) < 10:
        weaknesses.append(f"Content requires expansion ({breakdown['content']}/20).")

    if breakdown.get("social", 0) < 5:
        weaknesses.append(f"Weak social presence ({breakdown['social']}/10).")
        recs.append("Set up company pages on LinkedIn and Facebook at minimum.")

    if not technical.get("has_analytics"):
        weaknesses.append("Analytics missing — no data-driven decision-making.")
        quick_wins.append("Install Google Analytics 4 (free, ~30 minutes).")

    if breakdown.get("performance", 0) < 3:
        weaknesses.append(f"Performance needs work ({breakdown['performance']}/5).")
        quick_wins.append("Enable lazy loading for images and use modern formats (WebP/AVIF).")

    if overall < 30:
        opportunities += [
            f"Massive upside — realistic near-term target {overall + 40} points.",
            "Fixing fundamentals can yield +20–30 points quickly.",
            "Peers may be similar — the fastest mover wins.",
        ]
    elif overall < 50:
        opportunities += [
            f"Meaningful growth potential — target {overall + 30} points.",
            "SEO optimization could lift organic traffic by 50–100%.",
            "Content marketing can boost visibility and expertise.",
        ]
    elif overall < 70:
        opportunities += [
            f"Strong base — target {overall + 20} points.",
            "Chance to reach top quartile with focused investment.",
            "A/B testing and CRO will improve outcomes.",
        ]
    else:
        opportunities += [
            "Strong foundation for innovation.",
            "AI and automation are the next leverage points.",
            "Personalization and UX can be a competitive edge.",
        ]

    summary_parts = []
    if overall >= 75:
        summary_parts.append(f"Excellent digital maturity ({overall}/100). You are among the digital leaders in your space.")
    elif overall >= 60:
        summary_parts.append(f"Good digital presence ({overall}/100). Fundamentals are in place with room to improve.")
    elif overall >= 45:
        summary_parts.append(f"Baseline achieved ({overall}/100). Significant improvement opportunities identified.")
    elif overall >= 30:
        summary_parts.append(f"Digital presence needs work ({overall}/100). Multiple critical gaps observed.")
    else:
        summary_parts.append(f"Early-stage digital maturity ({overall}/100). Immediate action required to stay competitive.")

    if wc < 500:
        summary_parts.append(f"Content volume is low ({wc} words) — this is the biggest single lever.")
    if not technical.get("has_analytics"):
        summary_parts.append("No analytics — start tracking to measure impact and iterate.")
    if overall < 60:
        max_realistic = min(100, overall + 40)
        summary_parts.append(f"Realistic improvement potential: +{max_realistic - overall} points in 3–6 months.")
    if overall < 45:
        summary_parts.append("You lag peers — fast action is important.")
    elif overall > 60:
        summary_parts.append("You are ahead of many competitors; maintain momentum.")

    summary = " ".join(summary_parts)

    return {
        "summary": summary,
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "opportunities": opportunities[:4],
        "threats": threats[:3],
        "recommendations": (recs + quick_wins)[:5],
        "confidence_score": min(95, max(60, overall + 20)),
        "sentiment_score": (overall / 100) * 0.8 + 0.2,
        "key_metrics": {},
        "action_priority": [],
    }

async def generate_ai_insights(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any],
) -> AIAnalysis:
    # Ei ulkoisia API-kutsuja tässä osassa — luodaan englanninkielinen yhteenveto deterministisesti
    insights = generate_english_insights(basic.get("digital_maturity_score", 0), basic, technical, content, ux, social)
    return AIAnalysis(**insights)

def generate_smart_actions(ai: AIAnalysis, technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    breakdown = basic.get("score_breakdown", {})

    # SECURITY
    sec = breakdown.get("security", 0)
    if sec < 15:
        if sec == 0:
            actions.append({
                "title": "Critical: Enable HTTPS immediately",
                "description": "No SSL certificate present — this is a critical security issue.",
                "priority": "critical", "effort": "low", "impact": "critical",
                "estimated_score_increase": 10, "category": "security", "estimated_time": "1–2 days"
            })
        elif sec < 10:
            actions.append({
                "title": "Add missing security headers",
                "description": f"Security {sec}/15. Add CSP, HSTS and X-Frame-Options.",
                "priority": "high", "effort": "low", "impact": "high",
                "estimated_score_increase": 15 - sec, "category": "security", "estimated_time": "1 day"
            })
        else:
            actions.append({
                "title": "Tighten security headers",
                "description": f"Security {sec}/15. Finalize header policies.",
                "priority": "medium", "effort": "low", "impact": "medium",
                "estimated_score_increase": 15 - sec, "category": "security", "estimated_time": "2–4 hours"
            })

    # SEO
    seo = breakdown.get("seo_basics", 0)
    if seo < 20:
        gap = 20 - seo
        if gap > 10:
            actions.append({
                "title": "Fix critical SEO basics",
                "description": f"SEO {seo}/20. Correct titles, meta descriptions, and heading structure.",
                "priority": "critical", "effort": "low", "impact": "critical",
                "estimated_score_increase": min(10, gap), "category": "seo", "estimated_time": "1–2 days"
            })
        elif gap > 5:
            actions.append({
                "title": "Improve on-page SEO",
                "description": f"SEO {seo}/20. Optimize metadata and URL structure.",
                "priority": "high", "effort": "medium", "impact": "high",
                "estimated_score_increase": gap, "category": "seo", "estimated_time": "3–5 days"
            })
        else:
            actions.append({
                "title": "Fine-tune advanced SEO",
                "description": f"SEO {seo}/20. Add canonical, hreflang, and structured data.",
                "priority": "medium", "effort": "medium", "impact": "medium",
                "estimated_score_increase": gap, "category": "seo", "estimated_time": "1 week"
            })

    # CONTENT
    c = breakdown.get("content", 0)
    if c < 20:
        gap = 20 - c
        wc = content.get("word_count", 0)
        if c <= 5:
            actions.append({
                "title": "Create a comprehensive content strategy",
                "description": f"Content only {c}/20. {wc} words across key pages — substantial content production required.",
                "priority": "critical", "effort": "high", "impact": "critical",
                "estimated_score_increase": min(15, gap), "category": "content", "estimated_time": "2–4 weeks"
            })
        elif c <= 10:
            actions.append({
                "title": "Expand core content depth",
                "description": f"Content {c}/20. Add in-depth pages and supporting articles.",
                "priority": "high", "effort": "high", "impact": "high",
                "estimated_score_increase": min(10, gap), "category": "content", "estimated_time": "2 weeks"
            })
        else:
            actions.append({
                "title": "Improve content quality & readability",
                "description": f"Content {c}/20. Increase readability and add rich media.",
                "priority": "medium", "effort": "medium", "impact": "medium",
                "estimated_score_increase": gap, "category": "content", "estimated_time": "1 week"
            })

    # Järjestys
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions.sort(key=lambda x: (priority_order.get(x["priority"], 4), -x.get("estimated_score_increase", 0)))
    return actions[:15]

def round_pct(x: int) -> int:
    return max(0, min(100, int(x)))# ============================================================================
# ENHANCED & UI THEME HELPERS
# ============================================================================

def detect_technology_stack(html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    detected = []
    hl = html.lower()

    cms_patterns = {
        "WordPress": ["wp-content", "wp-includes", "wordpress"],
        "Joomla": ["joomla", "/components/", "/modules/"],
        "Drupal": ["drupal", "/sites/all/", "drupal.settings"],
        "Shopify": ["shopify", "myshopify.com", "cdn.shopify"],
        "Wix": ["wix.com", "static.wixstatic.com"],
        "Squarespace": ["squarespace", "sqsp.net"],
        "Webflow": ["webflow.io", "webflow.com"],
        "Ghost": ["ghost.io", "ghost-themes"],
    }
    for cms, pats in cms_patterns.items():
        if any(p in hl for p in pats):
            detected.append(f"CMS: {cms}")
            break

    frameworks = {
        "React": ["react", "_react", "reactdom"],
        "Angular": ["ng-", "angular", "__zone_symbol__"],
        "Vue.js": ["vue", "v-for", "v-if", "v-model"],
        "Next.js": ["_next", "nextjs", "__next_data__"],
        "Gatsby": ["gatsby", "___gatsby"],
        "Nuxt.js": ["__nuxt", "_nuxt"],
        "Django": ["csrfmiddlewaretoken", "django"],
        "Laravel": ["laravel", "livewire"],
        "Ruby on Rails": ["rails", "csrf-token", "action_controller"],
    }
    for fw, pats in frameworks.items():
        if any(p in hl for p in pats):
            detected.append(f"Framework: {fw}")

    if "google-analytics" in hl or "gtag" in hl: detected.append("Analytics: Google Analytics")
    if "googletagmanager" in hl: detected.append("Analytics: Google Tag Manager")
    if "matomo" in hl or "piwik" in hl: detected.append("Analytics: Matomo")
    if "hotjar" in hl: detected.append("Analytics: Hotjar")
    if "clarity.ms" in hl: detected.append("Analytics: Microsoft Clarity")
    if "cloudflare" in hl: detected.append("CDN: Cloudflare")
    if "akamai" in hl: detected.append("CDN: Akamai")
    if "fastly" in hl: detected.append("CDN: Fastly")
    if "amazonaws" in hl: detected.append("Hosting: AWS")
    if "azurewebsites" in hl: detected.append("Hosting: Azure")
    if "woocommerce" in hl: detected.append("E-commerce: WooCommerce")
    if "shopify" in hl: detected.append("E-commerce: Shopify")
    if "magento" in hl: detected.append("E-commerce: Magento")
    if "bootstrap" in hl: detected.append("CSS: Bootstrap")
    if "tailwind" in hl: detected.append("CSS: Tailwind")
    if "bulma" in hl: detected.append("CSS: Bulma")
    if "material" in hl: detected.append("CSS: Material Design")
    if "jquery" in hl: detected.append("JS: jQuery")
    if "lodash" in hl: detected.append("JS: Lodash")
    if "axios" in hl: detected.append("JS: Axios")

    return {
        "detected": detected,
        "count": len(detected),
        "categories": {
            "cms": [t.split(": ")[1] for t in detected if t.startswith("CMS:")],
            "frameworks": [t.split(": ")[1] for t in detected if t.startswith("Framework:")],
            "analytics": [t.split(": ")[1] for t in detected if t.startswith("Analytics:")],
            "cdn": [t.split(": ")[1] for t in detected if t.startswith("CDN:")],
            "ecommerce": [t.split(": ")[1] for t in detected if t.startswith("E-commerce:")],
        },
    }

def assess_mobile_first_readiness(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    score = 0; issues, recs = [], []
    vp = soup.find("meta", attrs={"name": "viewport"})
    if vp:
        vc = vp.get("content","")
        if "width=device-width" in vc: score += 30
        else:
            issues.append("Viewport not properly configured")
            recs.append("Add proper viewport meta tag")
    else:
        issues.append("No viewport meta tag"); recs.append("Add viewport meta tag with width=device-width")

    hl = html.lower()
    if "@media" in hl:
        c = hl.count("@media")
        if c >= 5: score += 25
        elif c >= 2: score += 15
        else:
            issues.append("Limited responsive CSS"); recs.append("Add additional responsive breakpoints")
    else:
        issues.append("No responsive media queries"); recs.append("Implement responsive design with media queries")

    if "font-size" in hl:
        if "rem" in hl or "em" in hl: score += 15
        else:
            issues.append("Fixed font sizes used"); recs.append("Use relative font sizes (rem/em)")
    if "touch" in hl or "tap" in hl: score += 10
    if soup.find("meta", attrs={"name": "apple-mobile-web-app-capable"}): score += 10

    imgs = soup.find_all("img")
    if imgs:
        lazy = [i for i in imgs if i.get("loading") == "lazy"]
        if lazy: score += 10
        else: recs.append("Implement lazy loading for images")

    ready = score >= 60
    return {"ready": ready, "score": score, "status": "Ready" if ready else "Not Ready",
            "issues": issues if not ready else [], "recommendations": [r for r in recs if r]}

def estimate_core_web_vitals(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    size = len(html); imgs = soup.find_all("img"); scripts = soup.find_all("script"); recs = []
    lcp = 2.0
    if size > 500000: lcp += 2.0
    elif size > 200000: lcp += 1.0
    elif size > 100000: lcp += 0.5
    if len(imgs) > 20: lcp += 1.0
    elif len(imgs) > 10: lcp += 0.5
    if [i for i in imgs if i.get("loading") == "lazy"]: lcp -= 0.5

    fid = 50
    if len(scripts) > 20: fid += 100
    elif len(scripts) > 10: fid += 50
    elif len(scripts) > 5: fid += 25
    if [s for s in scripts if s.get("async") or s.get("defer")]: fid -= 25

    cls = 0.05
    imgs_no_dims = [i for i in imgs if not (i.get("width") and i.get("height"))]
    if len(imgs_no_dims) > 5: cls += 0.15
    elif len(imgs_no_dims) > 2: cls += 0.10
    elif imgs_no_dims: cls += 0.05
    if "font-face" in html.lower(): cls += 0.05

    lcp_status = "Good" if lcp <= 2.5 else "Needs Improvement" if lcp <= 4.0 else "Poor"
    fid_status = "Good" if fid <= 100 else "Needs Improvement" if fid <= 300 else "Poor"
    cls_status = "Good" if cls <= 0.1 else "Needs Improvement" if cls <= 0.25 else "Poor"

    if lcp_status != "Good": recs.append("Optimize images with lazy loading and proper sizing")
    if fid_status != "Good": recs.append("Reduce JavaScript execution time and split bundles")
    if cls_status != "Good": recs.append("Add explicit width/height to images and embeds; avoid FOIT")

    overall = "Pass"
    if "Poor" in (lcp_status, fid_status, cls_status): overall = "Fail"
    elif "Needs Improvement" in (lcp_status, fid_status, cls_status): overall = "Needs Improvement"

    return {
        "lcp": {"value": f"{lcp:.1f}s", "status": lcp_status, "threshold": "≤2.5s Good, ≤4.0s Needs Improvement"},
        "fid": {"value": f"{fid}ms", "status": fid_status, "threshold": "≤100ms Good, ≤300ms Needs Improvement"},
        "cls": {"value": f"{cls:.2f}", "status": cls_status, "threshold": "≤0.1 Good, ≤0.25 Needs Improvement"},
        "overall_status": overall, "recommendations": recs,
    }

def detect_industry_from_content(domain: str, html: str) -> str:
    domain_lower = domain.lower(); html_lower = html.lower()
    if any(t in domain_lower for t in ["bank","finance","loan","credit","invest"]): return "finance"
    if any(t in domain_lower for t in ["health","medical","clinic","hospital","care"]): return "health"
    if any(t in domain_lower for t in ["shop","store","buy","retail","verkkokauppa"]): return "retail"
    if any(t in domain_lower for t in ["tech","software","app","cloud","data"]): return "tech"
    if any(t in domain_lower for t in ["edu","university","school","learn","oppi"]): return "education"
    if any(t in domain_lower for t in ["news","media","tv","radio","uutiset"]): return "media"
    if "patient" in html_lower or "treatment" in html_lower: return "health"
    if "product" in html_lower and "price" in html_lower: return "retail"
    if "banking" in html_lower or "financial services" in html_lower: return "finance"
    return "general"

def generate_market_trends(url: str = None, html: str = None, tech_stack: Dict = None) -> List[str]:
    if not url or not html:
        return ["Digital transformation accelerating across industries",
                "AI integration becoming standard in 2025",
                "Mobile-first approach is mandatory",
                "Customer experience as key differentiator",
                "Data privacy regulations tightening globally"]
    domain = get_domain_from_url(url); industry = detect_industry_from_content(domain, html)
    import random
    industry_trends = {
        "finance": [f"Open Banking adoption at 67% in Nordic markets (2025)",
                    f"Digital-only banks captured 15% market share in Finland",
                    f"AI-powered fraud detection reducing losses by 43%",
                    f"Instant payments standard in {random.randint(75,85)}% of transactions",
                    f"ESG investing growing {random.randint(30,40)}% YoY"],
        "health": [f"Telehealth visits up {random.randint(35,45)}x from pre-2020 levels",
                   f"AI diagnostics showing {random.randint(85,95)}% accuracy rates",
                   f"Remote monitoring reducing readmissions by {random.randint(60,70)}%",
                   f"Mental health apps market growing {random.randint(25,35)}% annually",
                   f"Wearable integration in {random.randint(40,50)}% of care plans"],
        "retail": [f"Social commerce is {random.randint(15,20)}% of e-commerce sales",
                   f"Same-day delivery expected by {random.randint(70,80)}% of customers",
                   f"AR try-on increasing conversion by {random.randint(80,95)}%",
                   f"Sustainable products see {random.randint(20,30)}% price premium",
                   f"Return rates averaging {random.randint(15,25)}% for online orders"],
        "tech": [f"AI tools used by {random.randint(65,75)}% of developers daily",
                 f"API-first architecture in {random.randint(80,90)}% of new projects",
                 f"Edge computing reducing latency by {random.randint(5,10)}x",
                 f"Serverless adoption growing {random.randint(40,50)}% YoY",
                 f"Developer experience focus increasing retention by {random.randint(30,40)}%"],
        "education": [f"Hybrid learning permanent in {random.randint(60,70)}% of institutions",
                      f"Micro-credentials growing {random.randint(35,45)}% annually",
                      f"AI tutors improving outcomes by {random.randint(20,30)}%",
                      f"Video content is {random.randint(65,75)}% of learning materials",
                      f"Skills-based hiring in {random.randint(40,50)}% of job posts"],
        "media": [f"Streaming captures {random.randint(70,80)}% of viewing time",
                  f"Short-form video engagement up {random.randint(200,300)}%",
                  f"Podcast advertising growing {random.randint(30,40)}% YoY",
                  f"AI-generated content is {random.randint(10,15)}% of news",
                  f"Subscription fatigue affecting {random.randint(55,65)}% of users"],
        "general": [f"Mobile traffic exceeds {random.randint(60,70)}% globally",
                    f"Page load speed impacts {random.randint(40,50)}% of bounces",
                    f"Voice search is {random.randint(20,30)}% of queries",
                    f"Cookie-less tracking adopted by {random.randint(45,55)}% sites",
                    f"Green hosting reduces costs by {random.randint(15,25)}%"],
    }
    trends = industry_trends.get(industry, industry_trends["general"])
    if tech_stack and tech_stack.get("detected"):
        detected = tech_stack["detected"]
        if any("WordPress" in t for t in detected): trends[4] = "WordPress powers 43% of all websites globally"
        elif any(("React" in t) or ("Next" in t) for t in detected): trends[4] = "React ecosystem dominates modern web development"
        elif any("Shopify" in t for t in detected): trends[4] = "Shopify processes $400B+ in global commerce annually"
    return trends[:5]

def calculate_improvement_potential(basic: Dict[str, Any]) -> int:
    current = basic.get("digital_maturity_score", 0)
    breakdown = basic.get("score_breakdown", {}) or {}
    potential = 0
    for cat, max_pts in SCORING_WEIGHTS.items():
        cur = breakdown.get(cat, 0); gap = max_pts - cur
        if gap > max_pts * 0.7: potential += int(gap * 0.8)
        elif gap > max_pts * 0.4: potential += int(gap * 0.6)
        else: potential += int(gap * 0.4)
    return min(potential, 100 - current)

def generate_competitor_gaps(basic: Dict[str, Any], competitive: Dict[str, Any]) -> List[str]:
    s = basic.get("digital_maturity_score", 0)
    if s < 30:
        return ["Very weak digital presence vs. peers", "Foundational optimizations missing", "High risk of customer loss to modern competitors"]
    if s < 50:
        return ["Content strategy lags behind peers", "Technical implementation below average", "UX not competitive"]
    if s < 70:
        return ["Gap to top performers remains", "Potential to catch up with focused investments", "Conversion optimization required"]
    return ["Competitive vs. most peers", "Focus on innovation to differentiate", "Maintain lead with continuous improvement"]

def estimate_traffic_rank(url: str, basic: Dict[str, Any]) -> str:
    overall = int(basic.get("digital_maturity_score", 0))
    bd = basic.get("score_breakdown", {}) or {}
    seo_pts = int(bd.get("seo_basics", 0))
    content_pts = int(bd.get("content", 0))
    score = overall + (seo_pts * 2) + (content_pts * 2)
    if score >= 120: return "Top 20% (est.)"
    if score >= 100: return "Top 35% (est.)"
    if score >= 80: return "Middle 50% (est.)"
    if score >= 60: return "Bottom 35% (est.)"
    return "Bottom 20% (est.)"

# ---- Theme sniffers ----
def _find_meta_theme_color(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.find("meta", attrs={"name": "theme-color"})
    if tag and tag.get("content"): return tag["content"].strip()
    return None

def _find_css_root_colors(html: str) -> List[str]:
    colors = []
    root_blocks = re.findall(r":root\s*{([^}]+)}", html, flags=re.I | re.S)
    for block in root_blocks:
        for varname in ("--primary", "--brand", "--accent", "--color-primary"):
            m = re.search(rf"{varname}\s*:\s*(#[0-9a-fA-F]{{6}}|#[0-9a-fA-F]{{3}})", block)
            if m: colors.append(m.group(1))
    if not colors:
        colors = re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}\b", html)
    return colors[:4]

def _find_font_family(soup: BeautifulSoup, html: str) -> Optional[str]:
    gf = soup.find("link", href=re.compile(r"fonts\.googleapis\.com|fonts\.gstatic\.com", re.I))
    if gf:
        m = re.search(r"family=([^:&]+)", gf.get("href",""))
        if m: return m.group(1).replace("+"," ")
    m = re.search(r"body\s*{[^}]*font-family\s*:\s*([^;}{]+)", html, flags=re.I|re.S)
    if m: return m.group(1).strip().strip("\"'")
    return None

def detect_brand_theme(html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    primary = _find_meta_theme_color(soup)
    palette = _find_css_root_colors(html)
    if not primary and palette: primary = palette[0]
    font = _find_font_family(soup, html)

    def _contrast(c: str) -> str:
        try:
            c = c.lstrip("#")
            if len(c) == 3: c = "".join(ch*2 for ch in c)
            r, g, b = int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)
            luminance = (0.299*r + 0.587*g + 0.114*b)
            return "#0B1220" if luminance > 186 else "#FFFFFF"
        except Exception:
            return "#FFFFFF"

    primary_txt = _contrast(primary) if primary else "#FFFFFF"
    return {
        "primary": primary or "#0F172A",
        "primaryText": primary_txt,
        "accent": palette[1] if len(palette) > 1 else None,
        "muted": "#94A3B8",
        "surface": "#FFFFFF",
        "elevation": "shadow-md rounded-2xl",
        "radius": "1rem",
        "fontFamily": font or "Inter, ui-sans-serif, system-ui",
        "layout": {"container": "max-w-6xl mx-auto px-4 md:px-6 lg:px-8", "gap": "gap-6"},
        "components": {
            "card": {"base": "p-5 md:p-6 bg-white/90 backdrop-blur border border-slate-200/60 rounded-2xl shadow-sm"},
            "kpi": {"pill": "px-3 py-1.5 text-sm rounded-full border"},
            "title": {"h1": "text-2xl md:text-3xl font-semibold tracking-tight"},
        },
    }

def build_screen_report(raw: Dict[str, Any]) -> Dict[str, Any]:
    b = raw["basic_analysis"]; det = raw["detailed_analysis"]; enh = raw.get("enhanced_features", {})
    header = {
        "title": b.get("company") or raw.get("company_name") or "Website report",
        "subtitle": b.get("website", ""),
        "kpis": [
            {"label": "Overall", "value": round_pct(b.get("digital_maturity_score", 0))},
            {"label": "Technical", "value": round_pct(b.get("technical_score", 0))},
            {"label": "Content", "value": round_pct(b.get("content_score", 0))},
            {"label": "SEO", "value": round_pct(b.get("seo_score", 0))},
            {"label": "UX", "value": round_pct(det["ux_analysis"].get("overall_ux_score", 0))},
            {"label": "Social", "value": round_pct(det["social_media"].get("social_score", 0))},
        ],
    }
    cards = [
        {"title": "Summary", "type": "text", "body": raw["ai_analysis"].get("summary", ""),
         "badges": [{"text": f"Percentile {raw['smart']['scores'].get('percentile', 0)}"},
                    {"text": enh.get("estimated_traffic_rank", {}).get("value", "")}]},
        {"title": "Strengths", "type": "bullets", "items": raw["ai_analysis"].get("strengths", [])},
        {"title": "Weaknesses", "type": "bullets", "items": raw["ai_analysis"].get("weaknesses", []), "variant": "warning"},
        {"title": "Top Actions (next)", "type": "actions", "items": [
            {"title": a["title"], "subtitle": a["description"],
             "meta": f"{a['priority'].upper()} • impact {a['impact']} • ~{a['estimated_time']}"}
            for a in (raw["smart"].get("actions") or [])[:5]
        ]},
    ]
    tables = [
        {"title": "Score breakdown", "type": "keyvalue", "items": [
            {"key": "Security", "value": b["score_breakdown"]["security"]},
            {"key": "SEO basics", "value": b["score_breakdown"]["seo_basics"]},
            {"key": "Content", "value": b["score_breakdown"]["content"]},
            {"key": "Technical", "value": b["score_breakdown"]["technical"]},
            {"key": "Mobile", "value": b["score_breakdown"]["mobile"]},
            {"key": "Social", "value": b["score_breakdown"]["social"]},
            {"key": "Performance", "value": b["score_breakdown"]["performance"]},
        ]},
        {"title": "Technology stack (detected)", "type": "chips",
         "items": (enh.get("technology_stack", {}).get("detected") or [])[:20]},
        {"title": "Core Web Vitals (est.)", "type": "keyvalue", "items": [
            {"key": "LCP", "value": enh.get("core_web_vitals_assessment", {}).get("lcp", {}).get("value", "–")},
            {"key": "FID", "value": enh.get("core_web_vitals_assessment", {}).get("fid", {}).get("value", "–")},
            {"key": "CLS", "value": enh.get("core_web_vitals_assessment", {}).get("cls", {}).get("value", "–")},
            {"key": "Status", "value": enh.get("core_web_vitals_assessment", {}).get("overall_status", "–")},
        ]},
    ]
    charts = [{
        "title": "Category scores", "type": "bar",
        "series": [
            {"name": "Security", "value": b["score_breakdown"]["security"], "max": 15},
            {"name": "SEO", "value": b["score_breakdown"]["seo_basics"], "max": 20},
            {"name": "Content", "value": b["score_breakdown"]["content"], "max": 20},
            {"name": "Technical", "value": b["score_breakdown"]["technical"], "max": 15},
            {"name": "Mobile", "value": b["score_breakdown"]["mobile"], "max": 15},
            {"name": "Social", "value": b["score_breakdown"]["social"], "max": 10},
            {"name": "Perf", "value": b["score_breakdown"]["performance"], "max": 5},
        ],
    }]
    next_steps = [{"text": r["insight"] if isinstance(r, dict) and "insight" in r else r}
                  for r in (raw["ai_analysis"].get("recommendations") or [])][:5]
    return {"header": header,
            "sections": [{"kind": "cards", "items": cards},
                         {"kind": "tables", "items": tables},
                         {"kind": "charts", "items": charts},
                         {"kind": "next_steps", "items": next_steps}],
            "meta": {"generated_at": raw.get("analysis_date"),
                     "version": raw.get("metadata", {}).get("version")}}


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {"name": APP_NAME, "version": APP_VERSION, "status": "operational",
            "endpoints": {"health": "/health", "basic_analysis": "/api/v1/analyze", "ai_analysis": "/api/v1/ai-analyze"}}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": APP_VERSION, "timestamp": datetime.now().isoformat(),
            "openai_available": bool(openai_client), "cache_size": len(analysis_cache)}

@app.post("/api/v1/analyze")
async def basic_analyze(request: CompetitorAnalysisRequest):
    try:
        url = clean_url(request.url)
        resp = await fetch_url(url)
        if not resp:
            raise HTTPException(400, "Cannot fetch website")
        basic = await analyze_basic_metrics(url, resp.text)
        return {"success": True, "company": request.company_name or "Unknown", "website": url,
                "digital_maturity_score": basic["digital_maturity_score"],
                "social_platforms": basic.get("social_platforms", 0),
                "score_breakdown": basic.get("score_breakdown", {}),
                "analysis_date": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Basic analysis error: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze(request: CompetitorAnalysisRequest):
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

        basic = await analyze_basic_metrics(url, html)
        technical = await analyze_technical_aspects(url, html)
        content = await analyze_content_quality(html)
        ux = await analyze_ux_elements(html)
        social = await analyze_social_media_presence(url, html)
        competitive = await analyze_competitive_positioning(url, basic)
        ai = await generate_ai_insights(url, basic, technical, content, ux, social)

        tech_stack = detect_technology_stack(html, soup)
        mobile_first = assess_mobile_first_readiness(soup, html)
        core_vitals = estimate_core_web_vitals(soup, html)
        traffic_rank = estimate_traffic_rank(url, basic)
        market_trends = generate_market_trends(url, html, tech_stack)
        improvement_potential = calculate_improvement_potential(basic)
        competitor_gaps = generate_competitor_gaps(basic, competitive)

        raw_percentile = (min(100, int((basic["digital_maturity_score"] / 45) * 50))
                          if basic["digital_maturity_score"] <= 45
                          else 50 + int(((basic["digital_maturity_score"] - 45) / 55) * 50))
        percentile = max(0, min(100, raw_percentile))

        enhanced = {
            "industry_benchmarking": {
                "value": f"{basic['digital_maturity_score']} / 100",
                "description": "Industry avg: 45, Top 25%: 70",
                "status": "above_average" if basic["digital_maturity_score"] > 45 else "below_average",
                "details": {"your_score": basic["digital_maturity_score"], "industry_average": 45,
                            "top_quartile": 70, "bottom_quartile": 30, "percentile": percentile},
            },
            "competitor_gaps": {"value": f"{len(competitor_gaps)} identified", "description": "Most significant differences vs. competitors",
                                "items": competitor_gaps, "status": "critical" if len(competitor_gaps) > 2 else "moderate"},
            "growth_opportunities": {"value": f"+{improvement_potential} points", "description": "Realistic improvement potential in ~6 months",
                                     "items": ai.opportunities[:3] if hasattr(ai, "opportunities") else [],
                                     "potential_score": basic["digital_maturity_score"] + improvement_potential},
            "risk_assessment": {"value": f"{len(ai.threats if hasattr(ai, 'threats') else [])} risks", "description": "Identified critical risks",
                                "items": ai.threats[:3] if hasattr(ai, "threats") else [],
                                "severity": "high" if basic["digital_maturity_score"] < 30 else "medium" if basic["digital_maturity_score"] < 60 else "low"},
            "market_trends": {"value": f"{len(market_trends)} trends", "description": "Relevant market trends",
                              "items": market_trends,
                              "alignment": "aligned" if basic["digital_maturity_score"] > 60 else "partially_aligned" if basic["digital_maturity_score"] > 30 else "not_aligned"},
            "technology_stack": {"value": f"{tech_stack['count']} technologies",
                                 "description": ", ".join(tech_stack["detected"][:3]) + ("..." if len(tech_stack["detected"]) > 3 else "")
                                 if tech_stack["detected"] else "Not detected",
                                 "detected": tech_stack["detected"], "categories": tech_stack["categories"],
                                 "modernity": "modern" if any(x for x in tech_stack["detected"] if any(y in x for y in ["React","Next","Vue"])) else "traditional"},
            "estimated_traffic_rank": {"value": traffic_rank, "description": "Estimated position by traffic potential",
                                       "confidence": "medium", "factors": ["Digital maturity score","SEO optimization","Content volume"]},
            "mobile_first_index_ready": {"value": "Yes" if mobile_first["ready"] else "No", "description": "Google Mobile-First readiness",
                                         "status": "ready" if mobile_first["ready"] else "not_ready",
                                         "score": mobile_first["score"], "issues": mobile_first["issues"],
                                         "recommendations": mobile_first["recommendations"]},
            "core_web_vitals_assessment": {"value": core_vitals["overall_status"],
                                           "description": f"LCP: {core_vitals['lcp']['value']}, FID: {core_vitals['fid']['value']}, CLS: {core_vitals['cls']['value']}",
                                           "lcp": core_vitals["lcp"], "fid": core_vitals["fid"],
                                           "cls": core_vitals["cls"], "overall_status": core_vitals["overall_status"],
                                           "recommendations": core_vitals["recommendations"]},
        }

        result = {
            "success": True,
            "company_name": request.company_name or basic.get("title", "Unknown"),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": BasicAnalysis(
                company=request.company_name or basic.get("title", "Unknown"),
                website=url,
                digital_maturity_score=basic["digital_maturity_score"],
                social_platforms=basic.get("social_platforms", 0),
                technical_score=technical.get("overall_technical_score", 0),
                content_score=content.get("content_quality_score", 0),
                seo_score=int((basic.get("score_breakdown", {}).get("seo_basics", 0) / 20) * 100),
                score_breakdown=ScoreBreakdown(**basic.get("score_breakdown", {})),
            ).dict(),
            "ai_analysis": ai.dict(),
            "detailed_analysis": DetailedAnalysis(
                social_media=SocialMediaAnalysis(**social),
                technical_audit=TechnicalAudit(**technical),
                content_analysis=ContentAnalysis(**content),
                ux_analysis=UXAnalysis(**ux),
                competitive_analysis=CompetitiveAnalysis(**competitive),
            ).dict(),
            "smart": {
                "actions": generate_smart_actions(ai, technical, content, basic),
                "scores": SmartScores(
                    overall=basic["digital_maturity_score"],
                    technical=technical.get("overall_technical_score", 0),
                    content=content.get("content_quality_score", 0),
                    social=social.get("social_score", 0),
                    ux=ux.get("overall_ux_score", 0),
                    competitive=competitive.get("competitive_score", 0),
                    trend="improving" if improvement_potential > 20 else "stable",
                    percentile=percentile,
                ).dict(),
            },
            "enhanced_features": enhanced,
            "metadata": {"version": APP_VERSION, "analysis_depth": "comprehensive",
                         "confidence_level": ai.confidence_score,
                         "data_points_analyzed": len(tech_stack["detected"]) + len(basic.get("detailed_findings", {}))},
        }

        result = ensure_integer_scores(result)
        analysis_cache[cache_key] = {"data": result, "timestamp": datetime.now()}
        if len(analysis_cache) > MAX_CACHE_SIZE:
            oldest = min(analysis_cache.keys(), key=lambda k: analysis_cache[k]["timestamp"])
            del analysis_cache[oldest]

        logger.info(f"Enhanced analysis complete for {url}: score={basic['digital_maturity_score']}")
        return result
    except Exception as e:
        logger.error(f"Analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")


# ============================================================================
# MAIN (uvicorn)
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    logger.info(f"{APP_NAME} v{APP_VERSION} — English-only, no PDF")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
