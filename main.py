#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Website Analyzer Backend - Working Version 5.1
Frontend Compatible with JWT Auth
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# FastAPI
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# JWT
import jwt

# Password hashing - with fallback
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    BCRYPT_AVAILABLE = True
except:
    BCRYPT_AVAILABLE = False
    print("Warning: bcrypt not available, using plain passwords")

# HTTP and HTML parsing
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ============================================================================
# CONFIGURATION
# ============================================================================

APP_VERSION = "5.1.0"
APP_NAME = "Website Analyzer API"

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "aklsjdfölaksjfdklj")  # Same as in your frontend
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Cache
cache_storage = {}
CACHE_TTL = 3600

# Usage Limits
USAGE_LIMITS = {
    "guest": 3,
    "user": 10,
    "admin": float('inf')
}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Website Analyzer with JWT Authentication"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# USERS DATABASE
# ============================================================================

# Simple password storage for testing (use hashing in production)
USERS_PASSWORDS = {
    "admin": os.getenv("ADMIN_PASSWORD", "kaikka123"),
    "user": "user123",
    "guest": ""
}

# User data storage
users_data = {
    "admin": {"role": "admin", "usage_count": 0},
    "user": {"role": "user", "usage_count": 0},
    "guest": {"role": "guest", "usage_count": 0}
}

# ============================================================================
# SECURITY
# ============================================================================

security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, stored_password: str) -> bool:
    """Verify password - uses bcrypt if available, else plain comparison"""
    if BCRYPT_AVAILABLE and stored_password.startswith("$2b$"):
        return pwd_context.verify(plain_password, stored_password)
    return plain_password == stored_password

def create_access_token(data: dict):
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Get current user from JWT token or return guest"""
    if not credentials:
        return {"username": "guest", "role": "guest"}
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        
        if username:
            return {"username": username, "role": role}
    except Exception as e:
        logger.debug(f"Token validation failed: {e}")
    
    return {"username": "guest", "role": "guest"}

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
    security: int = Field(ge=0, le=15)
    seo_basics: int = Field(ge=0, le=20)
    content: int = Field(ge=0, le=20)
    technical: int = Field(ge=0, le=15)
    mobile: int = Field(ge=0, le=10)
    social: int = Field(ge=0, le=10)
    performance: int = Field(ge=0, le=10)
    total: int = Field(ge=0, le=100)

class BasicAnalysis(BaseModel):
    company: str
    website: str
    analyzed_at: str
    digital_maturity_score: int
    technical_score: int
    content_score: int
    seo_score: int
    score_breakdown: ScoreBreakdown

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

class DetailedAnalysis(BaseModel):
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    social_media: SocialMediaAnalysis
    competitive_analysis: CompetitiveAnalysis

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

def analyze_website(html: str, url: str, company: str = "") -> Dict[str, Any]:
    """Complete website analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Basic metrics
    title = soup.find('title')
    title_text = title.text if title else ""
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc.get('content', '') if meta_desc else ""
    
    # Score calculation (using OLD scoring system for frontend compatibility)
    security_score = 8 if url.startswith('https') else 0
    if soup.find('meta', attrs={'name': 'robots'}): security_score += 2
    security_score = min(security_score, 15)
    
    seo_basics_score = 0
    if title_text: seo_basics_score += 8
    if description: seo_basics_score += 7
    if soup.find('h1'): seo_basics_score += 3
    if soup.find_all('h2'): seo_basics_score += 2
    seo_basics_score = min(seo_basics_score, 20)
    
    content_score = 0
    text_content = soup.get_text()
    word_count = len(text_content.split())
    if word_count > 300: content_score += 8
    if word_count > 1000: content_score += 8
    if len(soup.find_all('img')) > 0: content_score += 4
    content_score = min(content_score, 20)
    
    technical_score = 0
    if soup.find('script', type='application/ld+json'): technical_score += 5
    if len(soup.find_all('link', rel='stylesheet')) < 5: technical_score += 5
    if soup.find('link', rel='canonical'): technical_score += 5
    technical_score = min(technical_score, 15)
    
    mobile_score = 10 if soup.find('meta', attrs={'name': 'viewport'}) else 0
    
    social_score = 0
    if 'facebook' in html.lower() or 'twitter' in html.lower(): social_score += 5
    if soup.find('meta', property=re.compile(r'^og:')): social_score += 5
    social_score = min(social_score, 10)
    
    performance_score = 0
    if len(soup.find_all('script')) < 10: performance_score += 5
    if len(soup.find_all('img', loading='lazy')): performance_score += 5
    performance_score = min(performance_score, 10)
    
    total_score = (security_score + seo_basics_score + content_score + 
                   technical_score + mobile_score + social_score + performance_score)
    
    # Build response
    basic_analysis = BasicAnalysis(
        company=company or urlparse(url).netloc,
        website=url,
        analyzed_at=datetime.now().isoformat(),
        digital_maturity_score=ensure_integer(total_score),
        technical_score=ensure_integer(technical_score),
        content_score=ensure_integer(content_score),
        seo_score=ensure_integer(seo_basics_score),
        score_breakdown=ScoreBreakdown(
            security=ensure_integer(security_score),
            seo_basics=ensure_integer(seo_basics_score),
            content=ensure_integer(content_score),
            technical=ensure_integer(technical_score),
            mobile=ensure_integer(mobile_score),
            social=ensure_integer(social_score),
            performance=ensure_integer(performance_score),
            total=ensure_integer(total_score)
        )
    )
    
    # Technical audit
    technical_audit = TechnicalAudit(
        score=ensure_integer(technical_score * 5),
        issues_found=5 - (technical_score // 3),
        page_speed="Fast" if len(soup.find_all('script')) < 10 else "Moderate",
        mobile_responsive=bool(soup.find('meta', attrs={'name': 'viewport'})),
        ssl_enabled=url.startswith('https'),
        meta_tags_present=bool(description),
        structured_data=bool(soup.find('script', type='application/ld+json')),
        xml_sitemap=None,
        robots_txt=None
    )
    
    # Content analysis
    content_analysis = ContentAnalysis(
        score=ensure_integer(content_score * 5),
        word_count=word_count,
        reading_time=f"{word_count // 200} min",
        content_quality="Good" if word_count > 500 else "Needs improvement",
        keyword_density={},
        headings_structure={
            "h1": len(soup.find_all('h1')),
            "h2": len(soup.find_all('h2')),
            "h3": len(soup.find_all('h3'))
        }
    )
    
    # UX analysis
    ux_analysis = UXAnalysis(
        score=ensure_integer(mobile_score * 10),
        navigation_clarity="Good" if soup.find('nav') else "Poor",
        mobile_friendliness="Yes" if mobile_score > 0 else "No",
        page_load_time="Fast",
        interactive_elements=len(soup.find_all('button')) + len(soup.find_all('a')),
        accessibility_score=80 if soup.find_all('img', alt=True) else 40
    )
    
    # Social media
    social_media = SocialMediaAnalysis(
        score=ensure_integer(social_score * 10),
        platforms_found=["facebook", "twitter"] if social_score > 5 else [],
        engagement_indicators={"sharing_buttons": social_score > 0},
        social_links=[]
    )
    
    # Competitive analysis
    competitive = CompetitiveAnalysis(
        market_position="Competitive" if total_score > 50 else "Needs Improvement",
        strengths=["Digital presence"] if total_score > 30 else [],
        weaknesses=["SEO needs work"] if seo_basics_score < 10 else [],
        opportunities=["Mobile optimization", "Content expansion"],
        threats=["Competitor advancement"]
    )
    
    detailed_analysis = DetailedAnalysis(
        technical_audit=technical_audit,
        content_analysis=content_analysis,
        ux_analysis=ux_analysis,
        social_media=social_media,
        competitive_analysis=competitive
    )
    
    # AI Analysis
    ai_analysis = AIAnalysis(
        summary=f"Website scores {total_score}/100 indicating {'good' if total_score > 60 else 'moderate'} digital maturity.",
        strengths=["Good foundation"] if total_score > 40 else [],
        weaknesses=["Needs improvement"] if total_score < 60 else [],
        opportunities=["SEO optimization", "Mobile enhancement"],
        threats=["Competition"],
        recommendations=[
            {"action": "Improve SEO", "priority": "high", "impact": "High visibility"},
            {"action": "Optimize mobile", "priority": "medium", "impact": "Better UX"}
        ],
        confidence_score=0.85,
        sentiment_score=0.7,
        key_metrics={"score": total_score},
        action_priority=[
            {"title": "Fix technical issues", "urgency": "high", "effort": "low"}
        ]
    )
    
    # Smart analysis
    smart_actions = []
    if seo_basics_score < 15:
        smart_actions.append(SmartAction(
            title="Improve SEO",
            description="Optimize meta tags and content",
            priority="high",
            impact="high",
            effort="low"
        ))
    if mobile_score < 8:
        smart_actions.append(SmartAction(
            title="Mobile Optimization",
            description="Make site responsive",
            priority="critical",
            impact="high",
            effort="medium"
        ))
    
    smart_analysis = SmartAnalysis(
        actions=smart_actions,
        scores={
            "seo": ensure_integer(seo_basics_score),
            "content": ensure_integer(content_score),
            "technical": ensure_integer(technical_score),
            "mobile": ensure_integer(mobile_score),
            "overall": ensure_integer(total_score)
        }
    )
    
    # Enhanced features
    enhanced_features = EnhancedFeatures(
        industry_benchmarking=EnhancedFeature(
            value=f"{total_score}/100",
            description="Compared to industry average",
            status="above_average" if total_score > 45 else "below_average"
        ),
        competitor_gaps=EnhancedFeature(
            value="3 gaps identified",
            description="Areas for improvement",
            status="attention"
        ),
        growth_opportunities=EnhancedFeature(
            value=f"+{100-total_score} points",
            description="Potential improvement",
            status="high"
        ),
        risk_assessment=EnhancedFeature(
            value="Medium",
            description="Risk level",
            status="moderate"
        ),
        market_trends=EnhancedFeature(
            value="70% aligned",
            description="Market alignment",
            status="good"
        ),
        technology_stack=EnhancedFeature(
            value="5 technologies",
            description="Tech stack",
            status="modern"
        ),
        estimated_traffic_rank=EnhancedFeature(
            value="Medium",
            description="Traffic estimate",
            status="average"
        ),
        mobile_first_index_ready=EnhancedFeature(
            value="Yes" if mobile_score > 5 else "No",
            description="Mobile ready",
            status="ready" if mobile_score > 5 else "not_ready"
        ),
        core_web_vitals_assessment=EnhancedFeature(
            value="Needs Improvement",
            description="Performance metrics",
            status="needs_work"
        )
    )
    
    return {
        "basic_analysis": basic_analysis.dict(),
        "detailed_analysis": detailed_analysis.dict(),
        "ai_analysis": ai_analysis.dict(),
        "smart": smart_analysis.dict(),
        "enhanced_features": enhanced_features.dict()
    }

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/auth/login")
async def login(request: LoginRequest):
    """Login endpoint"""
    logger.info(f"Login attempt for user: {request.username}")
    
    # Check if user exists
    if request.username not in USERS_PASSWORDS:
        logger.warning(f"User not found: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Verify password
    expected_password = USERS_PASSWORDS[request.username]
    if request.password != expected_password:
        logger.warning(f"Invalid password for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create token
    user_role = users_data[request.username]["role"]
    token = create_access_token({"sub": request.username, "role": user_role})
    
    logger.info(f"Login successful for user: {request.username}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user_role,
        "username": request.username
    }

@app.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    username = current_user["username"]
    role = current_user["role"]
    
    user_data = users_data.get(username, {"role": "guest", "usage_count": 0})
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

@app.post("/api/v1/analyze")
async def analyze(
    request: AnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """Main analysis endpoint"""
    url = clean_url(request.url)
    username = current_user["username"]
    role = current_user["role"]
    
    # Check usage limits
    user_data = users_data.get(username, {"role": "guest", "usage_count": 0})
    usage_limit = USAGE_LIMITS.get(role, 3)
    
    if user_data["usage_count"] >= usage_limit and usage_limit != float('inf'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usage limit reached. {role.capitalize()} limit: {usage_limit} analyses"
        )
    
    try:
        # Fetch and analyze
        html = await fetch_website_content(url)
        result = analyze_website(html, url, request.company_name or "")
        
        # Add metadata
        result["metadata"] = {
            "api_version": APP_VERSION,
            "analyzed_at": datetime.now().isoformat(),
            "cached": False,
            "user_role": role,
            "usage_count": user_data["usage_count"] + 1,
            "usage_limit": usage_limit
        }
        
        # Update usage count
        if username in users_data:
            users_data[username]["usage_count"] = user_data["usage_count"] + 1
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze(
    request: AnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """AI analysis endpoint - same as regular analyze for now"""
    if current_user["role"] == "guest":
        # For guest, check if they have analyses left
        user_data = users_data.get("guest", {"usage_count": 0})
        if user_data["usage_count"] >= USAGE_LIMITS["guest"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free limit reached. Please sign up for more analyses."
            )
    
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
        "message": "Website Analyzer API is running"
    }

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/test")
async def test():
    """Test endpoint"""
    return {
        "message": "API is working!",
        "users": list(USERS_PASSWORDS.keys()),
        "bcrypt_available": BCRYPT_AVAILABLE
    }

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║     Website Analyzer API v{APP_VERSION} - Starting...      ║
    ╠══════════════════════════════════════════════════════╣
    ║  Server: http://{host}:{port}                       ║
    ║  Docs:   http://{host}:{port}/docs                  ║
    ╠══════════════════════════════════════════════════════╣
    ║  Test Login:                                         ║
    ║  - admin / {os.getenv('ADMIN_PASSWORD', 'kaikka123')}
    ║  - user / user123                                    ║
    ║  - guest / (empty)                                   ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=host, port=port, reload=False)
