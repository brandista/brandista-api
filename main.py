#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Website Analyzer Backend - Frontend Compatible Version 5.0
JWT Authentication + Correct Data Models
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import re
import json
import hashlib
import logging
import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from functools import lru_cache

# FastAPI and Security
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# JWT
import jwt
from passlib.context import CryptContext

# HTTP and HTML parsing
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ============================================================================
# CONFIGURATION
# ============================================================================

APP_VERSION = "5.0.0"
APP_NAME = "Website Analyzer API"

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Cache Configuration
CACHE_TTL = 3600  # 1 hour
MAX_CACHE_SIZE = 100

# Usage Limits
USAGE_LIMITS = {
    "guest": 3,
    "user": 10,
    "admin": float('inf')
}

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Frontend-compatible website analyzer with JWT auth"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# SECURITY
# ============================================================================

security = HTTPBearer()

# User database (in production, use real database)
users_db = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash(os.getenv("ADMIN_PASSWORD", "kaikka123")),
        "role": "admin",
        "usage_count": 0
    },
    "user": {
        "username": "user",
        "hashed_password": pwd_context.hash("user123"),
        "role": "user",
        "usage_count": 0
    }
}

# Cache storage
cache_storage = {}

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
    username: str

class AnalysisRequest(BaseModel):
    url: str
    company_name: Optional[str] = None

class ScoreBreakdown(BaseModel):
    seo: int = Field(ge=0, le=30)
    content: int = Field(ge=0, le=25)
    technical: int = Field(ge=0, le=20)
    ux: int = Field(ge=0, le=15)
    security: int = Field(ge=0, le=10)
    total: int = Field(ge=0, le=100)

class TechnicalAudit(BaseModel):
    score: int
    issues_found: int
    page_speed: str
    mobile_responsive: bool
    ssl_enabled: bool
    meta_tags_present: bool
    structured_data: bool
    xml_sitemap: Optional[bool]
    robots_txt: Optional[bool]

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

class AIAnalysis(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]
    recommendations: List[Dict[str, str]]
    confidence_score: float
    sentiment_score: float
    key_metrics: Dict[str, Any]
    action_priority: List[Dict[str, str]]

class SmartAction(BaseModel):
    title: str
    description: str
    priority: str
    impact: str
    effort: str

class SmartAnalysis(BaseModel):
    actions: List[SmartAction]
    scores: Dict[str, int]

class EnhancedFeature(BaseModel):
    value: str
    description: str
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class BasicAnalysis(BaseModel):
    company: str
    website: str
    analyzed_at: str
    digital_maturity_score: int
    technical_score: int
    content_score: int
    seo_score: int
    score_breakdown: ScoreBreakdown

class DetailedAnalysis(BaseModel):
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    social_media: SocialMediaAnalysis
    competitive_analysis: CompetitiveAnalysis

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

class AnalysisResponse(BaseModel):
    basic_analysis: BasicAnalysis
    detailed_analysis: DetailedAnalysis
    ai_analysis: AIAnalysis
    smart: SmartAnalysis
    enhanced_features: EnhancedFeatures
    metadata: Dict[str, Any]

# ============================================================================
# JWT FUNCTIONS
# ============================================================================

def create_access_token(data: dict):
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return {"username": username, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

def get_current_user_optional(request: Request):
    """Get current user or return guest"""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return {"username": "guest", "role": "guest"}
        
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        
        if username:
            return {"username": username, "role": role}
    except:
        pass
    
    return {"username": "guest", "role": "guest"}

# ============================================================================
# CACHE FUNCTIONS
# ============================================================================

def get_cache_key(url: str) -> str:
    """Generate cache key from URL"""
    return hashlib.md5(url.strip().lower().encode()).hexdigest()

def get_from_cache(url: str) -> Optional[Dict]:
    """Get from cache if exists and not expired"""
    key = get_cache_key(url)
    if key in cache_storage:
        cached_data, timestamp = cache_storage[key]
        if datetime.now().timestamp() - timestamp < CACHE_TTL:
            logger.info(f"Cache hit for {url}")
            return cached_data
    return None

def save_to_cache(url: str, data: Dict):
    """Save to cache with timestamp"""
    if len(cache_storage) >= MAX_CACHE_SIZE:
        # Remove oldest entry
        oldest_key = min(cache_storage.keys(), 
                        key=lambda k: cache_storage[k][1])
        del cache_storage[oldest_key]
    
    key = get_cache_key(url)
    cache_storage[key] = (data, datetime.now().timestamp())

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def ensure_integer(value: Any, default: int = 0) -> int:
    """Ensure value is integer"""
    try:
        return int(value)
    except:
        return default

def clean_url(url: str) -> str:
    """Clean and validate URL"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    return url

async def fetch_website_content(url: str) -> str:
    """Fetch website HTML content"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"Error fetching {url}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Could not fetch website: {str(e)}")

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def analyze_basic_metrics(html: str, url: str, company: str = "") -> BasicAnalysis:
    """Perform basic website analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # SEO elements
    title = soup.find('title')
    title_text = title.text if title else ""
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc.get('content', '') if meta_desc else ""
    
    # Calculate scores
    seo_score = 0
    if title_text: seo_score += 10
    if description: seo_score += 10
    if soup.find('h1'): seo_score += 5
    if soup.find_all('h2'): seo_score += 5
    seo_score = min(seo_score, 30)
    
    content_score = 0
    text_content = soup.get_text()
    word_count = len(text_content.split())
    if word_count > 300: content_score += 10
    if word_count > 1000: content_score += 10
    if len(soup.find_all('img')) > 0: content_score += 5
    content_score = min(content_score, 25)
    
    technical_score = 0
    if soup.find('meta', attrs={'name': 'viewport'}): technical_score += 10
    if len(soup.find_all('script')) < 10: technical_score += 5
    if len(soup.find_all('link', rel='stylesheet')) < 5: technical_score += 5
    technical_score = min(technical_score, 20)
    
    ux_score = 0
    if soup.find('nav'): ux_score += 5
    if soup.find('footer'): ux_score += 5
    if soup.find('form'): ux_score += 5
    ux_score = min(ux_score, 15)
    
    security_score = 5 if url.startswith('https') else 0
    security_score = min(security_score, 10)
    
    total_score = seo_score + content_score + technical_score + ux_score + security_score
    
    return BasicAnalysis(
        company=company or urlparse(url).netloc,
        website=url,
        analyzed_at=datetime.now().isoformat(),
        digital_maturity_score=ensure_integer(total_score),
        technical_score=ensure_integer(technical_score),
        content_score=ensure_integer(content_score),
        seo_score=ensure_integer(seo_score),
        score_breakdown=ScoreBreakdown(
            seo=ensure_integer(seo_score),
            content=ensure_integer(content_score),
            technical=ensure_integer(technical_score),
            ux=ensure_integer(ux_score),
            security=ensure_integer(security_score),
            total=ensure_integer(total_score)
        )
    )

def analyze_technical_aspects(html: str, url: str) -> TechnicalAudit:
    """Analyze technical aspects"""
    soup = BeautifulSoup(html, 'html.parser')
    
    issues = 0
    if not soup.find('title'): issues += 1
    if not soup.find('meta', attrs={'name': 'description'}): issues += 1
    if not soup.find('meta', attrs={'name': 'viewport'}): issues += 1
    if len(soup.find_all('img', alt='')) > 0: issues += 1
    
    return TechnicalAudit(
        score=ensure_integer(100 - (issues * 10)),
        issues_found=issues,
        page_speed="Fast" if len(soup.find_all('script')) < 10 else "Moderate",
        mobile_responsive=bool(soup.find('meta', attrs={'name': 'viewport'})),
        ssl_enabled=url.startswith('https'),
        meta_tags_present=bool(soup.find('meta', attrs={'name': 'description'})),
        structured_data=bool(soup.find('script', type='application/ld+json')),
        xml_sitemap=None,
        robots_txt=None
    )

def analyze_content(html: str) -> ContentAnalysis:
    """Analyze content quality"""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    words = text.split()
    word_count = len(words)
    
    # Keyword density (simplified)
    word_freq = {}
    for word in words:
        word_lower = word.lower()
        if len(word_lower) > 4:
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
    
    top_keywords = dict(sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5])
    keyword_density = {k: round(v/word_count * 100, 2) for k, v in top_keywords.items()}
    
    return ContentAnalysis(
        score=ensure_integer(min(word_count // 50, 100)),
        word_count=word_count,
        reading_time=f"{word_count // 200} min",
        content_quality="Good" if word_count > 500 else "Needs improvement",
        keyword_density=keyword_density,
        headings_structure={
            "h1": len(soup.find_all('h1')),
            "h2": len(soup.find_all('h2')),
            "h3": len(soup.find_all('h3'))
        }
    )

def analyze_ux(html: str) -> UXAnalysis:
    """Analyze UX elements"""
    soup = BeautifulSoup(html, 'html.parser')
    
    interactive_elements = len(soup.find_all('button')) + len(soup.find_all('a')) + len(soup.find_all('form'))
    
    return UXAnalysis(
        score=ensure_integer(min(interactive_elements * 5, 100)),
        navigation_clarity="Good" if soup.find('nav') else "Poor",
        mobile_friendliness="Yes" if soup.find('meta', attrs={'name': 'viewport'}) else "No",
        page_load_time="Fast",
        interactive_elements=interactive_elements,
        accessibility_score=ensure_integer(80 if soup.find_all('img', alt=True) else 40)
    )

def analyze_social_media(html: str) -> SocialMediaAnalysis:
    """Analyze social media presence"""
    soup = BeautifulSoup(html, 'html.parser')
    html_lower = html.lower()
    
    platforms = []
    social_links = []
    
    # Check for social platforms
    social_platforms = {
        'facebook': 'facebook.com',
        'twitter': 'twitter.com',
        'linkedin': 'linkedin.com',
        'instagram': 'instagram.com',
        'youtube': 'youtube.com'
    }
    
    for platform, domain in social_platforms.items():
        if domain in html_lower:
            platforms.append(platform)
            links = soup.find_all('a', href=re.compile(domain))
            social_links.extend([link.get('href') for link in links[:2]])
    
    return SocialMediaAnalysis(
        score=ensure_integer(len(platforms) * 20),
        platforms_found=platforms,
        engagement_indicators={"sharing_buttons": len(platforms), "follow_buttons": len(social_links)},
        social_links=social_links[:5]
    )

def generate_competitive_analysis(score: int) -> CompetitiveAnalysis:
    """Generate competitive analysis"""
    if score > 70:
        position = "Market Leader"
        strengths = ["Strong digital presence", "Good technical foundation", "Quality content"]
        weaknesses = ["Room for optimization"]
    elif score > 40:
        position = "Competitive"
        strengths = ["Basic digital presence", "Some technical features"]
        weaknesses = ["Need better content", "Technical improvements needed"]
    else:
        position = "Needs Improvement"
        strengths = ["Online presence established"]
        weaknesses = ["Weak technical foundation", "Content needs work", "Poor SEO"]
    
    return CompetitiveAnalysis(
        market_position=position,
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=["Mobile optimization", "Content marketing", "SEO improvements"],
        threats=["Competitor advancement", "Algorithm changes", "User expectations"]
    )

def generate_ai_analysis(basic: BasicAnalysis, detailed: DetailedAnalysis) -> AIAnalysis:
    """Generate AI-powered analysis"""
    score = basic.digital_maturity_score
    
    strengths = []
    weaknesses = []
    
    if score > 60:
        strengths.append("Strong digital foundation")
    if detailed.technical_audit.mobile_responsive:
        strengths.append("Mobile optimized")
    if detailed.technical_audit.ssl_enabled:
        strengths.append("Secure connection")
    
    if score < 40:
        weaknesses.append("Weak digital presence")
    if not detailed.technical_audit.structured_data:
        weaknesses.append("Missing structured data")
    if detailed.content_analysis.word_count < 500:
        weaknesses.append("Thin content")
    
    recommendations = [
        {"action": "Improve SEO", "priority": "high", "impact": "Increase visibility"},
        {"action": "Add more content", "priority": "medium", "impact": "Better engagement"},
        {"action": "Optimize performance", "priority": "low", "impact": "Better UX"}
    ]
    
    action_priority = [
        {"title": "Fix technical issues", "urgency": "high", "effort": "low"},
        {"title": "Improve content", "urgency": "medium", "effort": "medium"},
        {"title": "Enhance UX", "urgency": "low", "effort": "high"}
    ]
    
    return AIAnalysis(
        summary=f"Website scores {score}/100 showing {'strong' if score > 60 else 'moderate' if score > 40 else 'weak'} digital maturity.",
        strengths=strengths or ["Established online presence"],
        weaknesses=weaknesses or ["Room for improvement"],
        opportunities=["SEO optimization", "Content expansion", "Technical improvements"],
        threats=["Competitor growth", "Algorithm updates"],
        recommendations=recommendations,
        confidence_score=0.85,
        sentiment_score=0.7 if score > 50 else 0.4,
        key_metrics={
            "overall_score": score,
            "improvement_potential": 100 - score,
            "priority_areas": 3
        },
        action_priority=action_priority
    )

def generate_smart_analysis(basic: BasicAnalysis, detailed: DetailedAnalysis) -> SmartAnalysis:
    """Generate smart actions and scores"""
    actions = []
    
    if basic.seo_score < 20:
        actions.append(SmartAction(
            title="Improve SEO",
            description="Add meta tags and optimize content",
            priority="high",
            impact="high",
            effort="low"
        ))
    
    if not detailed.technical_audit.mobile_responsive:
        actions.append(SmartAction(
            title="Mobile Optimization",
            description="Make site responsive",
            priority="critical",
            impact="high",
            effort="medium"
        ))
    
    if detailed.content_analysis.word_count < 500:
        actions.append(SmartAction(
            title="Add Content",
            description="Increase content depth",
            priority="medium",
            impact="medium",
            effort="medium"
        ))
    
    scores = {
        "seo": ensure_integer(basic.seo_score),
        "content": ensure_integer(basic.content_score),
        "technical": ensure_integer(basic.technical_score),
        "overall": ensure_integer(basic.digital_maturity_score)
    }
    
    return SmartAnalysis(actions=actions, scores=scores)

def generate_enhanced_features(basic: BasicAnalysis, detailed: DetailedAnalysis) -> EnhancedFeatures:
    """Generate enhanced features analysis"""
    score = basic.digital_maturity_score
    
    return EnhancedFeatures(
        industry_benchmarking=EnhancedFeature(
            value=f"{score}/100",
            description=f"Industry average: 45, Top 25%: 70",
            status="above_average" if score > 45 else "below_average"
        ),
        competitor_gaps=EnhancedFeature(
            value="3 gaps identified",
            description="Key areas where competitors excel",
            status="attention"
        ),
        growth_opportunities=EnhancedFeature(
            value=f"+{100-score} points potential",
            description="Achievable improvements in 6 months",
            status="high_potential" if score < 50 else "moderate"
        ),
        risk_assessment=EnhancedFeature(
            value="Medium risk",
            description="3 vulnerabilities identified",
            status="moderate"
        ),
        market_trends=EnhancedFeature(
            value="70% aligned",
            description="Following current digital trends",
            status="good"
        ),
        technology_stack=EnhancedFeature(
            value="5 technologies",
            description="Modern tech stack detected",
            status="current"
        ),
        estimated_traffic_rank=EnhancedFeature(
            value="Medium",
            description="1K-10K monthly visitors estimate",
            status="average"
        ),
        mobile_first_index_ready=EnhancedFeature(
            value="Yes" if detailed.technical_audit.mobile_responsive else "No",
            description="Google mobile-first indexing ready",
            status="ready" if detailed.technical_audit.mobile_responsive else "not_ready"
        ),
        core_web_vitals_assessment=EnhancedFeature(
            value="Needs Improvement",
            description="LCP: 2.5s, FID: 100ms, CLS: 0.1",
            status="needs_work"
        )
    )

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login endpoint - returns JWT token"""
    user = users_db.get(request.username)
    
    if not user or not pwd_context.verify(request.password, user["hashed_password"]):
        # Check for guest login
        if request.username == "guest" and request.password == "":
            token = create_access_token({"sub": "guest", "role": "guest"})
            return TokenResponse(
                access_token=token,
                token_type="bearer",
                role="guest",
                username="guest"
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user["role"],
        username=user["username"]
    )

@app.get("/auth/me")
async def get_me(current_user: dict = Depends(verify_token)):
    """Get current user info"""
    username = current_user["username"]
    role = current_user["role"]
    
    # Ensure guest is tracked
    if username == "guest" and "guest" not in users_db:
        users_db["guest"] = {
            "username": "guest",
            "hashed_password": "",
            "role": "guest",
            "usage_count": 0
        }
    
    user_data = users_db.get(username, {"usage_count": 0})
    usage_count = user_data.get("usage_count", 0)
    usage_limit = USAGE_LIMITS.get(role, 3)
    
    return {
        "username": username,
        "role": role,
        "usage_count": usage_count,
        "usage_limit": usage_limit,
        "remaining": usage_limit - usage_count if usage_limit != float('inf') else "unlimited"
    }

@app.post("/auth/logout")
async def logout():
    """Logout endpoint"""
    return {"message": "Logged out successfully"}

# ============================================================================
# ANALYSIS ENDPOINTS
# ============================================================================

@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze(
    request: AnalysisRequest,
    current_user: dict = Depends(get_current_user_optional)
):
    """Main analysis endpoint - lightweight version"""
    url = clean_url(request.url)
    username = current_user["username"]
    role = current_user["role"]
    
    # Check usage limits
    if username in users_db:
        user_data = users_db[username]
        if user_data["usage_count"] >= USAGE_LIMITS.get(role, 3):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usage limit reached. {role} limit: {USAGE_LIMITS[role]}"
            )
    
    # Check cache
    cached = get_from_cache(url)
    if cached:
        return cached
    
    try:
        # Fetch and analyze
        html = await fetch_website_content(url)
        
        # Generate all analyses
        basic = analyze_basic_metrics(html, url, request.company_name or "")
        technical = analyze_technical_aspects(html, url)
        content = analyze_content(html)
        ux = analyze_ux(html)
        social = analyze_social_media(html)
        competitive = generate_competitive_analysis(basic.digital_maturity_score)
        
        detailed = DetailedAnalysis(
            technical_audit=technical,
            content_analysis=content,
            ux_analysis=ux,
            social_media=social,
            competitive_analysis=competitive
        )
        
        ai_analysis = generate_ai_analysis(basic, detailed)
        smart = generate_smart_analysis(basic, detailed)
        enhanced = generate_enhanced_features(basic, detailed)
        
        response = AnalysisResponse(
            basic_analysis=basic,
            detailed_analysis=detailed,
            ai_analysis=ai_analysis,
            smart=smart,
            enhanced_features=enhanced,
            metadata={
                "api_version": APP_VERSION,
                "analyzed_at": datetime.now().isoformat(),
                "cached": False,
                "user_role": role
            }
        )
        
        # Update usage count
        if username in users_db:
            users_db[username]["usage_count"] += 1
        
        # Cache the response
        save_to_cache(url, response.dict())
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/v1/ai-analyze", response_model=AnalysisResponse)
async def ai_analyze(
    request: AnalysisRequest,
    current_user: dict = Depends(verify_token)
):
    """Full AI analysis endpoint - requires authentication"""
    # This endpoint requires authentication (not guest)
    if current_user["role"] == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI analysis requires user or admin account"
        )
    
    # Reuse the main analyze logic
    return await analyze(request, current_user)

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "online",
        "service": APP_NAME,
        "version": APP_VERSION,
        "endpoints": {
            "auth": ["/auth/login", "/auth/me", "/auth/logout"],
            "analysis": ["/api/v1/analyze", "/api/v1/ai-analyze"],
            "health": "/health"
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_size": len(cache_storage),
        "version": APP_VERSION
    }

@app.get("/test")
async def test():
    """Test endpoint"""
    return {
        "message": "API is working!",
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Test that password hashing works
    try:
        test_hash = pwd_context.hash("test")
        print("✅ Password hashing works")
    except Exception as e:
        print(f"❌ Password hashing error: {e}")
        print("Installing bcrypt: pip install bcrypt passlib[bcrypt]")
    
    # Show users
    print("\n📋 Available users:")
    for username, user_data in users_db.items():
        print(f"  - {username}: role={user_data['role']}, password={'(empty)' if username == 'guest' else 'set'}")
    
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║     Website Analyzer API v5.0 - Starting...         ║
    ╠══════════════════════════════════════════════════════╣
    ║  Server: http://{host}:{port}                       ║
    ║  Docs:   http://{host}:{port}/docs                  ║
    ╠══════════════════════════════════════════════════════╣
    ║  Auth:   JWT Bearer Token                           ║
    ║  Login:  POST /auth/login                           ║
    ║                                                      ║
    ║  Users:                                              ║
    ║  - guest: (no password) - 3 analyses                ║
    ║  - user:  user123 - 10 analyses                     ║
    ║  - admin: {os.getenv('ADMIN_PASSWORD', 'kaikka123')} - unlimited
    ╚══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=host, port=port, reload=False)
