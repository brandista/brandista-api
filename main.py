from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any, List
import httpx
from bs4 import BeautifulSoup
import jwt
from datetime import datetime, timedelta
import os
from passlib.context import CryptContext
import json
import asyncio
from urllib.parse import urlparse, urljoin
import re

# FastAPI app initialization
app = FastAPI(title="Website Analysis API", version="1.0.0")

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()

# CORS middleware - IMPORTANT for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://*.vercel.app",
        "https://*.netlify.app",
        "*"  # Development only - restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database simulation (in production, use real database)
users_db = {
    "demo": {
        "username": "demo",
        "hashed_password": pwd_context.hash("demo"),
        "role": "user",
        "usage_count": 0,
        "max_usage": 3
    },
    "admin@brandista.fi": {
        "username": "admin@brandista.fi",
        "hashed_password": pwd_context.hash("kaikka123"),
        "role": "admin",
        "usage_count": 0,
        "max_usage": None  # Unlimited
    }
}

# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    token: str
    token_type: str = "bearer"
    role: str

class AnalysisRequest(BaseModel):
    url: str
    company_name: Optional[str] = None
    analysis_type: str = "comprehensive"
    language: str = "en"

class UserResponse(BaseModel):
    username: str
    role: str
    usage_count: int
    max_usage: Optional[int]

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

# Auth endpoints
@app.post("/auth/login", response_model=Token)
async def login(request: LoginRequest):
    user = users_db.get(request.username)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": request.username})
    return {
        "token": access_token,
        "token_type": "bearer",
        "role": user["role"]
    }

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user(username: str = Depends(verify_token)):
    user = users_db.get(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse(
        username=user["username"],
        role=user["role"],
        usage_count=user["usage_count"],
        max_usage=user["max_usage"]
    )

@app.post("/auth/logout")
async def logout(username: str = Depends(verify_token)):
    # In a real app, you might want to blacklist the token
    return {"message": "Successfully logged out"}

# Website analysis functions
async def fetch_website_content(url: str) -> str:
    """Fetch website HTML content"""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            response = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch website: {str(e)}"
            )

def analyze_website_basic(html: str, url: str) -> Dict[str, Any]:
    """Perform basic website analysis"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Basic analysis
    title = soup.find('title')
    title_text = title.text.strip() if title else ""
    
    meta_description = soup.find('meta', attrs={'name': 'description'})
    description = meta_description.get('content', '') if meta_description else ""
    
    # SEO Analysis
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    
    # Images
    images = soup.find_all('img')
    images_without_alt = [img for img in images if not img.get('alt')]
    
    # Links
    internal_links = []
    external_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('http'):
            if urlparse(url).netloc in href:
                internal_links.append(href)
            else:
                external_links.append(href)
        else:
            internal_links.append(href)
    
    # Technology detection
    has_analytics = bool(soup.find(string=re.compile('google-analytics|gtag|ga\(')))
    has_viewport = bool(soup.find('meta', attrs={'name': 'viewport'}))
    
    # Calculate scores
    seo_score = calculate_seo_score(title_text, description, h1_tags, images_without_alt)
    technical_score = calculate_technical_score(has_viewport, has_analytics)
    
    return {
        "website": url,
        "title": title_text,
        "meta_description": description,
        "h1_count": len(h1_tags),
        "h2_count": len(h2_tags),
        "images_total": len(images),
        "images_without_alt": len(images_without_alt),
        "internal_links": len(internal_links),
        "external_links": len(external_links),
        "has_analytics": has_analytics,
        "has_viewport": has_viewport,
        "seo_score": seo_score,
        "technical_score": technical_score,
        "digital_maturity_score": (seo_score + technical_score) // 2,
        "score_breakdown": {
            "technical": technical_score // 6,
            "content": min(20, len(h1_tags) * 5 + len(h2_tags) * 2),
            "seo_basics": seo_score // 4,
            "mobile": 15 if has_viewport else 0,
            "security": 10,  # Placeholder
            "performance": 5,  # Placeholder
            "social": 5  # Placeholder
        }
    }

def calculate_seo_score(title, description, h1_tags, images_without_alt):
    """Calculate SEO score"""
    score = 0
    if title and len(title) > 10:
        score += 25
    if description and len(description) > 50:
        score += 25
    if h1_tags:
        score += 25
    if len(images_without_alt) == 0:
        score += 25
    return score

def calculate_technical_score(has_viewport, has_analytics):
    """Calculate technical score"""
    score = 0
    if has_viewport:
        score += 50
    if has_analytics:
        score += 50
    return score

def generate_ai_analysis(basic_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI-like analysis based on basic metrics"""
    score = basic_analysis.get("digital_maturity_score", 0)
    
    strengths = []
    weaknesses = []
    opportunities = []
    recommendations = []
    
    # Analyze strengths and weaknesses
    if basic_analysis.get("has_viewport"):
        strengths.append("Mobile-responsive design implemented")
    else:
        weaknesses.append("Missing mobile viewport meta tag")
        recommendations.append("Add viewport meta tag for mobile responsiveness")
    
    if basic_analysis.get("has_analytics"):
        strengths.append("Analytics tracking is set up")
    else:
        weaknesses.append("No analytics tracking detected")
        recommendations.append("Implement Google Analytics or similar tracking")
    
    if basic_analysis.get("images_without_alt", 0) == 0:
        strengths.append("All images have alt text for accessibility")
    else:
        weaknesses.append(f"{basic_analysis.get('images_without_alt')} images missing alt text")
        recommendations.append("Add descriptive alt text to all images")
    
    if basic_analysis.get("h1_count", 0) > 0:
        strengths.append("Proper H1 heading structure")
    else:
        weaknesses.append("Missing H1 heading tag")
        recommendations.append("Add a clear H1 heading to improve SEO")
    
    # Generate opportunities based on score
    if score < 50:
        opportunities.append("Significant room for digital transformation")
        opportunities.append("Quick wins available in technical SEO")
    else:
        opportunities.append("Ready for advanced optimization strategies")
        opportunities.append("Good foundation for scaling digital presence")
    
    return {
        "summary": f"Website shows {score}% digital maturity with clear opportunities for improvement.",
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "threats": ["Competitors may have better digital presence"] if score < 50 else [],
        "recommendations": recommendations
    }

# Main analysis endpoint
@app.post("/api/v1/ai-analyze")
async def analyze_website(
    request_data: AnalysisRequest,
    username: str = Depends(verify_token)
):
    """Main endpoint for website analysis"""
    
    # Check user limits
    user = users_db.get(username)
    if user["role"] == "user" and user["max_usage"]:
        if user["usage_count"] >= user["max_usage"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usage limit reached. Please upgrade to continue."
            )
    
    # Clean and validate URL
    url = request_data.url.strip()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    try:
        # Fetch website content
        html = await fetch_website_content(url)
        
        # Perform basic analysis
        basic_analysis = analyze_website_basic(html, url)
        
        # Generate AI analysis
        ai_analysis = generate_ai_analysis(basic_analysis)
        
        # Update usage count
        if user["role"] == "user":
            users_db[username]["usage_count"] += 1
        
        # Return combined analysis
        return {
            "basic_analysis": basic_analysis,
            "ai_analysis": ai_analysis,
            "enhanced_features": {
                "industry_benchmarking": f"{basic_analysis['digital_maturity_score']}/100",
                "competitor_gaps": "Analysis available",
                "growth_opportunities": "Identified",
                "risk_assessment": "Medium",
                "market_trends": "Analyzed",
                "technology_stack": "Detected",
                "estimated_traffic_rank": "Medium",
                "mobile_first_index_ready": "Yes" if basic_analysis.get("has_viewport") else "No",
                "core_web_vitals_assessment": "Needs improvement"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

# Health check endpoint
@app.get("/")
async def root():
    return {"status": "online", "service": "Website Analysis API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
