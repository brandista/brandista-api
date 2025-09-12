#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Website Analyzer API - Complete Version 6.1
- JWT auth (guest/user/admin)
- Usage limits and counters
- In-memory cache
- Full analysis (basic, technical, content, UX, social, competitive)
- Optional OpenAI enhancement for AI recommendations (async)
- Frontend-compatible response with legacy score_breakdown mapping
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import re
import json
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# Password hashing and JWT
from passlib.context import CryptContext
import jwt

# Try to load OpenAI client lazily and safely
OPENAI_AVAILABLE = False
AsyncOpenAI = None  # type: ignore
try:
    # Newer SDK
    from openai import AsyncOpenAI as _AsyncOpenAI  # type: ignore
    AsyncOpenAI = _AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    try:
        # Older SDK compatibility
        from openai import AsyncOpenAI as _AsyncOpenAI2  # type: ignore
        AsyncOpenAI = _AsyncOpenAI2
        OPENAI_AVAILABLE = True
    except Exception:
        OPENAI_AVAILABLE = False
        AsyncOpenAI = None  # type: ignore

# ============================================================================
# CONFIG
# ============================================================================

APP_VERSION = "6.1.0"
APP_NAME = "Website Analyzer API"

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Auth and usage
USAGE_LIMITS = {"guest": 3, "user": 10, "admin": float("inf")}
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
openai_client = None
if OPENAI_AVAILABLE and OPENAI_API_KEY:
    try:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)  # type: ignore
    except Exception:
        openai_client = None

# Cache
CACHE_TTL = 3600  # seconds
MAX_CACHE_SIZE = 100
cache_storage: Dict[str, Any] = {}  # key: (data, timestamp)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("website-analyzer")

# ============================================================================
# FASTAPI
# ============================================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Complete analyzer with optional OpenAI enhancement"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# USERS (IN-MEMORY)
# ============================================================================

def _hash(p: str) -> str:
    return pwd_context.hash(p)

users_db: Dict[str, Dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "hashed_password": _hash(os.getenv("ADMIN_PASSWORD", "admin123")),
        "role": "admin",
        "usage_count": 0,
    },
    "user": {
        "username": "user",
        "hashed_password": _hash("user123"),
        "role": "user",
        "usage_count": 0,
    },
    # Special "guest" is tokenizable with empty password via /auth/login
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
    username: str

class AnalysisRequest(BaseModel):
    url: str
    company_name: Optional[str] = None

class ScoreBreakdownLegacy(BaseModel):
    # For frontend compatibility with older naming
    security: int = Field(0, ge=0, le=15)
    seo_basics: int = Field(0, ge=0, le=20)
    content: int = Field(0, ge=0, le=20)
    technical: int = Field(0, ge=0, le=15)
    mobile: int = Field(0, ge=0, le=15)
    social: int = Field(0, ge=0, le=10)
    performance: int = Field(0, ge=0, le=5)

class ScoreBreakdown(BaseModel):
    seo: int = Field(0, ge=0, le=30)
    content: int = Field(0, ge=0, le=25)
    technical: int = Field(0, ge=0, le=20)
    ux: int = Field(0, ge=0, le=15)
    security: int = Field(0, ge=0, le=10)
    total: int = Field(0, ge=0, le=100)

class TechnicalAudit(BaseModel):
    score: int
    issues_found: int
    page_speed: str
    mobile_responsive: bool
    ssl_enabled: bool
    meta_tags_present: bool
    structured_data: bool
    xml_sitemap: Optional[bool] = None
    robots_txt: Optional[bool] = None
    performance_indicators: List[str] = []

class ContentAnalysis(BaseModel):
    score: int
    word_count: int
    reading_time: str
    content_quality: str
    keyword_density: Dict[str, float]
    headings_structure: Dict[str, int]

class UXAnalysis(BaseModel):
    score: int
    navigation_clarity: str
    mobile_friendliness: str
    page_load_time: str
    interactive_elements: int
    accessibility_score: int

class SocialMediaAnalysis(BaseModel):
    score: int
    platforms_found: List[str]
    engagement_indicators: Dict[str, Any]
    social_links: List[str]

class CompetitiveAnalysis(BaseModel):
    market_position: str
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]
    competitive_score: int

class AIAnalysis(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]
    recommendations: List[str]
    confidence_score: int
    sentiment_score: float
    key_metrics: Dict[str, Any]
    action_priority: List[Dict[str, Any]]

class SmartAction(BaseModel):
    title: str
    description: str
    priority: str
    impact: str
    effort: str
    estimated_score_increase: int = 0
    category: str = "general"
    estimated_time: str = ""

class SmartAnalysis(BaseModel):
    actions: List[SmartAction]
    scores: Dict[str, int]

class BasicAnalysis(BaseModel):
    company: str
    website: str
    analyzed_at: str
    digital_maturity_score: int
    technical_score: int
    content_score: int
    seo_score: int
    score_breakdown: ScoreBreakdown
    score_breakdown_legacy: ScoreBreakdownLegacy

class EnhancedFeature(BaseModel):
    value: Any
    description: str
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class EnhancedFeatures(BaseModel):
    industry_benchmarking: EnhancedFeature
    competitor_gaps: EnhancedFeature
    growth_opportunities: EnhancedFeature
    risk_assessment: EnhancedFeature
    market_trends: EnhancedFeature
    technology_stack: EnhancedFeature
    estimated_traffic_rank: EnhancedFeature
    mobile_first_index_ready: EnhancedFeature
    core_web_vitals_assessment: EnhancedFeature

class DetailedAnalysis(BaseModel):
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    social_media: SocialMediaAnalysis
    competitive_analysis: CompetitiveAnalysis

class AnalysisResponse(BaseModel):
    basic_analysis: BasicAnalysis
    detailed_analysis: DetailedAnalysis
    ai_analysis: AIAnalysis
    smart: SmartAnalysis
    enhanced_features: EnhancedFeatures
    metadata: Dict[str, Any]

# ============================================================================
# AUTH HELPERS
# ============================================================================

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload.update({"exp": expire})
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"username": username, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_current_user_optional(request: Request) -> Dict[str, Any]:
    try:
        auth_header = request.headers.get("Authorization") or ""
        if not auth_header.startswith("Bearer "):
            return {"username": "guest", "role": "guest"}
        token = auth_header.split(" ", 1)[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"username": payload.get("sub", "guest"), "role": payload.get("role", "guest")}
    except Exception:
        return {"username": "guest", "role": "guest"}

def check_and_increment_usage(username: str, role: str) -> None:
    limit = USAGE_LIMITS.get(role, 3)
    if username in users_db:
        used = users_db[username].get("usage_count", 0)
        if used >= limit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Usage limit reached for role {role}.")
        users_db[username]["usage_count"] = used + 1
    # guest is not stored; we do not persist guest usage across processes

# ============================================================================
# CACHE HELPERS
# ============================================================================

def cache_key_for(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()

def cache_get(url: str) -> Optional[Dict[str, Any]]:
    k = cache_key_for(url)
    if k in cache_storage:
        data, ts = cache_storage[k]
        if (datetime.now().timestamp() - ts) < CACHE_TTL:
            return data
        else:
            del cache_storage[k]
    return None

def cache_set(url: str, data: Dict[str, Any]) -> None:
    if len(cache_storage) >= MAX_CACHE_SIZE:
        # Remove oldest
        oldest_k = min(cache_storage.keys(), key=lambda kk: cache_storage[kk][1])
        del cache_storage[oldest_k]
    cache_storage[cache_key_for(url)] = (data, datetime.now().timestamp())

# ============================================================================
# GENERIC HELPERS
# ============================================================================

def ensure_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url

async def fetch_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"Fetch failed for {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not fetch website: {e}")

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def analyze_basic_metrics(html: str, url: str, company: str = "") -> BasicAnalysis:
    soup = BeautifulSoup(html, "html.parser")

    # SEO score (0..30)
    title = soup.find("title")
    title_text = title.get_text().strip() if title else ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc.get("content", "").strip() if meta_desc else ""
    seo_score = 0
    if title_text: seo_score += 10
    if desc: seo_score += 10
    if soup.find("h1"): seo_score += 5
    if soup.find_all("h2"): seo_score += 5
    seo_score = min(seo_score, 30)

    # Content score (0..25)
    text = soup.get_text(separator=" ")
    words = text.split()
    wc = len(words)
    content_score = 0
    if wc > 300: content_score += 10
    if wc > 1000: content_score += 10
    if soup.find_all("img"): content_score += 5
    content_score = min(content_score, 25)

    # Technical score (0..20)
    scripts = soup.find_all("script")
    styles = soup.find_all("link", rel="stylesheet")
    viewport = soup.find("meta", attrs={"name": "viewport"})
    technical_score = 0
    if viewport: technical_score += 10
    if len(scripts) < 10: technical_score += 5
    if len(styles) < 5: technical_score += 5
    technical_score = min(technical_score, 20)

    # UX score (0..15)
    ux_score = 0
    if soup.find("nav"): ux_score += 5
    if soup.find("footer"): ux_score += 5
    if soup.find("form"): ux_score += 5
    ux_score = min(ux_score, 15)

    # Security (0..10)
    security_score = 5 if url.startswith("https://") else 0
    security_score = min(security_score, 10)

    total = seo_score + content_score + technical_score + ux_score + security_score

    # Map to legacy breakdown for backward compatibility
    # Legacy caps: security 15, seo_basics 20, content 20, technical 15, mobile 15, social 10, performance 5
    # Here we approximate from modern scores
    legacy = ScoreBreakdownLegacy(
        security=min(15, 10 if url.startswith("https://") else 0),
        seo_basics=min(20, int(seo_score / 30 * 20)),
        content=min(20, int(content_score / 25 * 20)),
        technical=min(15, int(technical_score / 20 * 15)),
        mobile=15 if viewport else 0,
        social=0,
        performance=min(5, 3 if (len(scripts) < 10 and len(styles) < 5) else 1)
    )

    return BasicAnalysis(
        company=company or (urlparse(url).netloc or url),
        website=url,
        analyzed_at=datetime.now().isoformat(),
        digital_maturity_score=ensure_int(total),
        technical_score=ensure_int(technical_score),
        content_score=ensure_int(content_score),
        seo_score=ensure_int(seo_score),
        score_breakdown=ScoreBreakdown(
            seo=seo_score,
            content=content_score,
            technical=technical_score,
            ux=ux_score,
            security=security_score,
            total=ensure_int(total),
        ),
        score_breakdown_legacy=legacy
    )

def analyze_technical(html: str, url: str) -> TechnicalAudit:
    soup = BeautifulSoup(html, "html.parser")
    issues = 0
    if not soup.find("title"): issues += 1
    if not soup.find("meta", attrs={"name": "description"}): issues += 1
    if not soup.find("meta", attrs={"name": "viewport"}): issues += 1
    if soup.find_all("img", alt=""): issues += 1

    indicators = []
    hl = html.lower()
    if ".min.js" in hl or ".min.css" in hl: indicators.append("minification")
    if any(c in hl for c in ["cdn.", "cloudflare", "akamai", "fastly"]): indicators.append("cdn")
    if any(b in hl for b in ["webpack", "vite", "parcel"]): indicators.append("modern_bundler")

    page_speed = "Fast" if len(soup.find_all("script")) < 10 else "Moderate" if len(soup.find_all("script")) < 20 else "Slow"

    return TechnicalAudit(
        score=max(0, 100 - issues * 10),
        issues_found=issues,
        page_speed=page_speed,
        mobile_responsive=bool(soup.find("meta", attrs={"name": "viewport"})),
        ssl_enabled=url.startswith("https://"),
        meta_tags_present=bool(soup.find("meta", attrs={"name": "description"})),
        structured_data=bool(soup.find("script", type="application/ld+json")),
        performance_indicators=indicators
    )

def analyze_content(html: str) -> ContentAnalysis:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    words = [w for w in text.split() if w]
    wc = len(words)

    freq: Dict[str, int] = {}
    for w in words:
        wl = re.sub(r"[^a-z0-9]", "", w.lower())
        if len(wl) > 4:
            freq[wl] = freq.get(wl, 0) + 1
    top = dict(sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kd = {k: round(v / max(1, wc) * 100, 2) for k, v in top.items()}

    return ContentAnalysis(
        score=min(100, wc // 50),
        word_count=wc,
        reading_time=f"{max(1, wc // 200)} min",
        content_quality="Good" if wc > 800 else "Needs improvement",
        keyword_density=kd,
        headings_structure={
            "h1": len(soup.find_all("h1")),
            "h2": len(soup.find_all("h2")),
            "h3": len(soup.find_all("h3")),
        }
    )

def analyze_ux(html: str) -> UXAnalysis:
    soup = BeautifulSoup(html, "html.parser")
    interactive = len(soup.find_all("button")) + len(soup.find_all("a")) + len(soup.find_all("form"))
    a11y = 80 if soup.find_all("img", alt=True) else 40
    return UXAnalysis(
        score=min(100, interactive * 3),
        navigation_clarity="Good" if soup.find("nav") else "Poor",
        mobile_friendliness="Yes" if soup.find("meta", attrs={"name": "viewport"}) else "No",
        page_load_time="Fast",
        interactive_elements=interactive,
        accessibility_score=a11y
    )

def analyze_social(html: str) -> SocialMediaAnalysis:
    soup = BeautifulSoup(html, "html.parser")
    hl = html.lower()
    platforms_map = {
        "facebook": "facebook.com",
        "twitter": "twitter.com",
        "linkedin": "linkedin.com",
        "instagram": "instagram.com",
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
        "pinterest": "pinterest."
    }
    platforms = []
    links = []
    for name, dom in platforms_map.items():
        if dom in hl:
            platforms.append(name)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if dom in href.lower():
                    links.append(href)
            links = links[:5]
    score = min(100, len(platforms) * 15)
    return SocialMediaAnalysis(
        score=score,
        platforms_found=platforms,
        engagement_indicators={"sharing_buttons": len(platforms), "follow_links": len(links)},
        social_links=links
    )

def analyze_competitive(total_score: int) -> CompetitiveAnalysis:
    if total_score >= 75:
        pos = "Market Leader"
        strengths = ["Strong digital presence", "Robust technical foundation"]
        weaknesses = ["Maintain innovation pace"]
        comp_score = 85
    elif total_score >= 55:
        pos = "Competitive"
        strengths = ["Solid baseline"]
        weaknesses = ["Gaps vs. leaders"]
        comp_score = 65
    elif total_score >= 40:
        pos = "Needs Improvement"
        strengths = ["Foundations in place"]
        weaknesses = ["Content and SEO need work", "UX improvements required"]
        comp_score = 45
    else:
        pos = "Falling Behind"
        strengths = ["High upside potential"]
        weaknesses = ["Weak technical and content depth"]
        comp_score = 25
    return CompetitiveAnalysis(
        market_position=pos,
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=["Mobile optimization", "Content marketing", "SEO improvements"],
        threats=["Competitor advancement", "Algorithm changes", "Rising UX expectations"],
        competitive_score=comp_score
    )

def generate_ai_from_rules(basic: BasicAnalysis, tech: TechnicalAudit, content: ContentAnalysis,
                           ux: UXAnalysis, social: SocialMediaAnalysis) -> AIAnalysis:
    total = basic.digital_maturity_score
    strengths: List[str] = []
    weaknesses: List[str] = []
    if total >= 60:
        strengths.append("Strong digital foundation")
    if tech.mobile_responsive:
        strengths.append("Mobile responsive")
    if tech.ssl_enabled:
        strengths.append("HTTPS enabled")

    if total < 45:
        weaknesses.append("Overall maturity is low")
    if not tech.structured_data:
        weaknesses.append("Missing structured data")
    if content.word_count < 600:
        weaknesses.append("Content depth is limited")
    if not tech.meta_tags_present:
        weaknesses.append("Missing meta description")

    recs = [
        "Implement structured data (JSON-LD) for key pages",
        "Expand core landing page content to 1000+ words",
        "Reduce JavaScript execution time and defer non-critical scripts",
        "Improve internal linking to raise topical authority",
        "Add alt text to all images and audit accessibility"
    ]

    action_priority = [
        {"title": "Fix technical SEO basics", "urgency": "high", "effort": "low"},
        {"title": "Expand content depth", "urgency": "high", "effort": "medium"},
        {"title": "Optimize performance", "urgency": "medium", "effort": "medium"},
        {"title": "Enhance UX and accessibility", "urgency": "medium", "effort": "low"},
    ]

    return AIAnalysis(
        summary=f"Website scores {total}/100 indicating {'strong' if total >= 60 else 'moderate' if total >= 45 else 'weak'} digital maturity.",
        strengths=strengths or ["Basic presence established"],
        weaknesses=weaknesses or ["Room for improvement"],
        opportunities=["SEO optimization", "Content expansion", "Performance tuning"],
        threats=["Competitors improving quickly", "Search algorithm changes"],
        recommendations=recs,
        confidence_score=min(95, max(60, total + 15)),
        sentiment_score=0.7 if total >= 55 else 0.4,
        key_metrics={
            "overall_score": total,
            "tech_score": tech.score,
            "content_words": content.word_count,
            "social_platforms": len(social.platforms_found),
        },
        action_priority=action_priority
    )

async def generate_openai_recommendations(context: str) -> List[str]:
    """Ask OpenAI for 5 concise, high-impact recommendations. Safe fallback."""
    if not openai_client:
        return []
    try:
        # Newer SDK chat interface
        resp = await openai_client.chat.completions.create(  # type: ignore
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": (
                "You are a website audit assistant. Based on the context, produce exactly 5 different, high-impact, "
                "one-sentence recommendations in imperative voice. No numbering. No intro or outro.\n\n"
                f"CONTEXT:\n{context}"
            )}],
            max_tokens=400,
            temperature=0.6,
        )
        raw = resp.choices[0].message.content.strip()  # type: ignore
        lines = [re.sub(r"^\s*[-•\d\.\)]\s*", "", ln).strip() for ln in raw.splitlines() if ln.strip()]
        uniq: List[str] = []
        for ln in lines:
            if len(ln.split()) >= 4 and ln not in uniq:
                uniq.append(ln)
            if len(uniq) == 5:
                break
        return uniq
    except Exception as e:
        logger.warning(f"OpenAI enhancement failed: {e}")
        return []

def generate_smart_actions(basic: BasicAnalysis, tech: TechnicalAudit, content: ContentAnalysis) -> SmartAnalysis:
    actions: List[SmartAction] = []
    # SEO
    if basic.seo_score < 25:
        gap = 30 - basic.seo_score
        actions.append(SmartAction(
            title="Fix critical SEO basics",
            description="Titles, meta descriptions, headings, and canonical where relevant.",
            priority="high", impact="high", effort="low",
            estimated_score_increase=min(10, gap), category="seo", estimated_time="1-3 days"
        ))
    # Mobile
    if not tech.mobile_responsive:
        actions.append(SmartAction(
            title="Implement proper viewport and responsive layout",
            description="Add viewport meta and responsive breakpoints; test across devices.",
            priority="critical", impact="high", effort="medium",
            estimated_score_increase=8, category="mobile", estimated_time="2-5 days"
        ))
    # Content
    if content.word_count < 800:
        actions.append(SmartAction(
            title="Increase content depth",
            description="Expand key pages to 1000-1500 words with media and internal links.",
            priority="high", impact="high", effort="medium",
            estimated_score_increase=10, category="content", estimated_time="1-2 weeks"
        ))
    scores = {
        "overall": basic.digital_maturity_score,
        "technical": tech.score,
        "content": content.score,
        "seo": basic.seo_score,
    }
    return SmartAnalysis(actions=actions[:15], scores=scores)

def generate_enhanced_features(basic: BasicAnalysis, tech: TechnicalAudit, content: ContentAnalysis,
                               ux: UXAnalysis, social: SocialMediaAnalysis) -> EnhancedFeatures:
    score = basic.digital_maturity_score
    # Simple tech stack hints
    tech_hints = tech.performance_indicators or []
    detected = []
    for h in tech_hints:
        if h == "cdn":
            detected.append("CDN")
        if h == "modern_bundler":
            detected.append("Modern Bundler")
        if h == "minification":
            detected.append("Minification")

    # Traffic estimate
    if score >= 75:
        traffic = ("High", "10K-50K monthly visitors", "medium")
    elif score >= 55:
        traffic = ("Medium-High", "5K-10K monthly visitors", "medium")
    elif score >= 40:
        traffic = ("Medium", "1K-5K monthly visitors", "low")
    else:
        traffic = ("Low-Medium", "<1K monthly visitors", "low")

    # Mobile readiness
    mobile_status = "ready" if tech.mobile_responsive else "not_ready"

    # Core Web Vitals estimate (rough)
    lcp = "2.5s"
    fid = "100ms"
    cls = "0.12"
    cwv_status = "Needs Improvement"

    return EnhancedFeatures(
        industry_benchmarking=EnhancedFeature(
            value=f"{score}/100",
            description="Industry avg: 45, Top 25%: 70",
            status="above_average" if score > 45 else "below_average",
            details={
                "score": score,
                "industry_average": 45,
                "top_25": 70,
                "top_10": 85,
            }
        ),
        competitor_gaps=EnhancedFeature(
            value="Key gaps detected",
            description="Technical SEO, content depth, performance",
            status="attention",
            details={"areas": ["technical_seo", "content_depth", "performance"]}
        ),
        growth_opportunities=EnhancedFeature(
            value=f"+{max(0, 100 - score)} points",
            description="Realistic improvement potential in 3-6 months",
            status="high_potential" if score < 50 else "moderate"
        ),
        risk_assessment=EnhancedFeature(
            value="Medium",
            description="Performance and SEO risks present",
            status="medium",
            details={"risks": ["missing structured data", "limited content depth", "possible JS bloat"]}
        ),
        market_trends=EnhancedFeature(
            value="Mobile-first, CWV, AI content",
            description="Alignment with current trends varies",
            status="partially_aligned" if score < 60 else "aligned"
        ),
        technology_stack=EnhancedFeature(
            value=f"{len(detected)} technologies",
            description=", ".join(detected) if detected else "Signals not conclusive",
            status="current" if detected else "unknown",
            details={"detected": detected}
        ),
        estimated_traffic_rank=EnhancedFeature(
            value=traffic[0],
            description=traffic[1],
            status="estimate",
            details={"confidence": traffic[2]}
        ),
        mobile_first_index_ready=EnhancedFeature(
            value="Yes" if tech.mobile_responsive else "No",
            description="Google Mobile-First readiness",
            status=mobile_status
        ),
        core_web_vitals_assessment=EnhancedFeature(
            value=cwv_status,
            description=f"LCP: {lcp}, FID: {fid}, CLS: {cls}",
            status="needs_work"
        )
    )

# ============================================================================
# ENDPOINT IMPLEMENTATIONS
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    username = (payload.username or "").lower()
    password = payload.password or ""
    if username == "guest" and password == "":
        token = create_access_token({"sub": "guest", "role": "guest"})
        return TokenResponse(access_token=token, role="guest", username="guest")
    user = users_db.get(username)
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return TokenResponse(access_token=token, role=user["role"], username=user["username"])

@app.get("/auth/me")
async def auth_me(current: Dict[str, Any] = Depends(verify_token)):
    username = current.get("username", "guest")
    role = current.get("role", "guest")
    usage = users_db.get(username, {}).get("usage_count", 0) if username in users_db else 0
    limit = USAGE_LIMITS.get(role, 3)
    remaining = "unlimited" if limit == float("inf") else max(0, int(limit - usage))
    return {"username": username, "role": role, "usage_count": usage, "usage_limit": limit, "remaining": remaining}

@app.post("/auth/logout")
async def logout():
    return {"message": "Logged out"}

@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze_endpoint(req: AnalysisRequest, current: Dict[str, Any] = Depends(get_current_user_optional)):
    url = clean_url(req.url)
    username = current.get("username", "guest")
    role = current.get("role", "guest")

    # usage check
    if username in users_db:
        check_and_increment_usage(username, role)

    # cache
    cached = cache_get(url)
    if cached:
        return cached

    # fetch and analyze
    html = await fetch_html(url)
    basic = analyze_basic_metrics(html, url, req.company_name or "")
    tech = analyze_technical(html, url)
    content = analyze_content(html)
    ux = analyze_ux(html)
    social = analyze_social(html)
    competitive = analyze_competitive(basic.digital_maturity_score)

    detailed = DetailedAnalysis(
        technical_audit=tech,
        content_analysis=content,
        ux_analysis=ux,
        social_media=social,
        competitive_analysis=competitive
    )

    ai = generate_ai_from_rules(basic, tech, content, ux, social)
    smart = generate_smart_actions(basic, tech, content)
    enhanced = generate_enhanced_features(basic, tech, content, ux, social)

    response = AnalysisResponse(
        basic_analysis=basic,
        detailed_analysis=detailed,
        ai_analysis=ai,
        smart=smart,
        enhanced_features=enhanced,
        metadata={
            "api_version": APP_VERSION,
            "analyzed_at": datetime.now().isoformat(),
            "openai_used": False,
            "cached": False,
            "user_role": role
        }
    )

    data = json.loads(response.json())
    cache_set(url, data)
    return data

@app.post("/api/v1/ai-analyze", response_model=AnalysisResponse)
async def ai_analyze_endpoint(req: AnalysisRequest, current: Dict[str, Any] = Depends(verify_token)):
    # This endpoint requires authenticated user (not guest)
    if current.get("role") == "guest":
        raise HTTPException(status_code=403, detail="AI analysis requires user or admin account")

    url = clean_url(req.url)
    username = current.get("username", "user")
    role = current.get("role", "user")

    # usage check
    check_and_increment_usage(username, role)

    # fetch and analyze
    html = await fetch_html(url)
    basic = analyze_basic_metrics(html, url, req.company_name or "")
    tech = analyze_technical(html, url)
    content = analyze_content(html)
    ux = analyze_ux(html)
    social = analyze_social(html)
    competitive = analyze_competitive(basic.digital_maturity_score)

    detailed = DetailedAnalysis(
        technical_audit=tech,
        content_analysis=content,
        ux_analysis=ux,
        social_media=social,
        competitive_analysis=competitive
    )

    # Rule-based AI first
    ai = generate_ai_from_rules(basic, tech, content, ux, social)

    # Optional OpenAI enhancement: prepend context and merge top 5 suggestions
    context = (
        f"URL: {url}\n"
        f"Score: {basic.digital_maturity_score}/100\n"
        f"Technical: {tech.score}/100, Mobile: {tech.mobile_responsive}\n"
        f"Content words: {content.word_count}\n"
        f"Social platforms: {len(social.platforms_found)}\n"
        f"UX score: {ux.score}/100\n"
    )
    extra_recs = await generate_openai_recommendations(context)
    if extra_recs:
        # Combine: keep first 2 rule-based + 3 from OpenAI to keep it concise
        merged = (ai.recommendations or [])[:2] + extra_recs[:3]
        ai.recommendations = merged
        ai.confidence_score = min(99, ai.confidence_score + 5)

    smart = generate_smart_actions(basic, tech, content)
    enhanced = generate_enhanced_features(basic, tech, content, ux, social)

    resp = AnalysisResponse(
        basic_analysis=basic,
        detailed_analysis=detailed,
        ai_analysis=ai,
        smart=smart,
        enhanced_features=enhanced,
        metadata={
            "api_version": APP_VERSION,
            "analyzed_at": datetime.now().isoformat(),
            "openai_used": bool(extra_recs),
            "cached": False,
            "user_role": role
        }
    )
    return json.loads(resp.json())

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": APP_NAME,
        "version": APP_VERSION,
        "openai_available": bool(openai_client),
        "endpoints": {
            "auth": ["/auth/login", "/auth/me", "/auth/logout"],
            "analysis": ["/api/v1/analyze", "/api/v1/ai-analyze"],
            "health": "/health",
            "test": "/test"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_size": len(cache_storage),
        "version": APP_VERSION
    }

@app.get("/test")
async def test():
    return {"message": "API is working!", "timestamp": datetime.now().isoformat()}

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"""
========================================================
  {APP_NAME} v{APP_VERSION} - Starting
  Server: http://{host}:{port}
  Docs:   http://{host}:{port}/docs
  Health: http://{host}:{port}/health

  Auth:
    - guest: POST /auth/login with {{ "username":"guest", "password":"" }}
    - user:  username "user", password "user123"
    - admin: username "admin", password from env ADMIN_PASSWORD
  OpenAI:
    - OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}
    - Model: {OPENAI_MODEL}
========================================================
""")
    uvicorn.run(app, host=host, port=port, log_level="info")
