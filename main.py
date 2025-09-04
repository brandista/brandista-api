import os
import json
import logging
import asyncio
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# Optional imports - gracefully handle if not available
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS4_AVAILABLE = False

# --- Setup logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ====================== Configuration ======================

class Config:
    """Application configuration"""
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    CACHE_TTL = 3600  # 1 hour
    MAX_WORKERS = 3
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 50000
    MIN_WORD_COUNT = 50

# ====================== Pydantic Models ======================

class AnalyzeRequest(BaseModel):
    url: str
    deep_analysis: bool = True
    use_ai: bool = True
    language: str = Field(default="en", pattern="^(en|fi|sv|de|fr|es)$")

class CompetitorAnalysisRequest(BaseModel):
    url: Optional[str] = None
    website: Optional[str] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    market_position: Optional[str] = None
    use_ai: bool = True
    language: Optional[str] = "fi"

# ====================== Simple Cache ======================

class SimpleCache:
    """In-memory cache implementation"""
    def __init__(self):
        self.cache = {}
        self.timestamps = {}
        
    def get(self, key: str) -> Optional[Dict]:
        if key in self.cache:
            # Check if expired
            if datetime.now().timestamp() - self.timestamps[key] < Config.CACHE_TTL:
                return self.cache[key]
            else:
                # Remove expired
                del self.cache[key]
                del self.timestamps[key]
        return None
        
    def set(self, key: str, value: Dict):
        self.cache[key] = value
        self.timestamps[key] = datetime.now().timestamp()
        
    def clear(self):
        self.cache.clear()
        self.timestamps.clear()

# ====================== Analysis Engine ======================

class AnalysisEngine:
    """Core analysis engine - simplified version"""
    
    def __init__(self):
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        
    async def fetch_page(self, url: str) -> Dict[str, Any]:
        """Fetch webpage content"""
        if not self.session:
            self.session = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            
        try:
            # Add headers to avoid blocking
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = await self.session.get(url, headers=headers)
            response.raise_for_status()
            
            return {
                "html": response.text,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "url": str(response.url)
            }
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch website: {str(e)}")
            
    def analyze_content(self, html: str, url: str) -> Dict[str, Any]:
        """Basic content analysis without BeautifulSoup dependency"""
        
        analysis = {
            "word_count": 0,
            "title": "",
            "description": "",
            "headings": {},
            "links": {"internal": 0, "external": 0, "total": 0},
            "images": {"total": 0, "with_alt": 0},
            "forms": 0,
            "tech_stack": {}
        }
        
        if BS4_AVAILABLE and BeautifulSoup:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract text
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            clean_text = ' '.join(text.split())
            analysis["word_count"] = len(clean_text.split())
            
            # Title
            if soup.title:
                analysis["title"] = soup.title.string or ""
                
            # Meta description
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc:
                analysis["description"] = meta_desc.get("content", "")
                
            # Headings
            for i in range(1, 7):
                analysis["headings"][f"h{i}"] = len(soup.find_all(f"h{i}"))
                
            # Links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('http'):
                    if url in href:
                        analysis["links"]["internal"] += 1
                    else:
                        analysis["links"]["external"] += 1
                else:
                    analysis["links"]["internal"] += 1
            analysis["links"]["total"] = analysis["links"]["internal"] + analysis["links"]["external"]
            
            # Images
            images = soup.find_all('img')
            analysis["images"]["total"] = len(images)
            analysis["images"]["with_alt"] = len([img for img in images if img.get('alt')])
            
            # Forms
            analysis["forms"] = len(soup.find_all('form'))
            
            # Technology detection (basic)
            analysis["tech_stack"] = self._detect_technology_basic(html)
            
        else:
            # Fallback without BeautifulSoup
            # Basic regex parsing
            import re
            
            # Word count
            text = re.sub(r'<[^>]+>', '', html)
            analysis["word_count"] = len(text.split())
            
            # Title
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if title_match:
                analysis["title"] = title_match.group(1)
                
            # Technology detection
            analysis["tech_stack"] = self._detect_technology_basic(html)
            
        return analysis
        
    def _detect_technology_basic(self, html: str) -> Dict[str, Any]:
        """Basic technology detection"""
        tech = {
            "cms": None,
            "frameworks": [],
            "analytics": []
        }
        
        # CMS Detection
        if "wp-content" in html or "wp-includes" in html:
            tech["cms"] = "WordPress"
        elif "sites/all" in html or "sites/default" in html:
            tech["cms"] = "Drupal"
        elif "cdn.shopify" in html:
            tech["cms"] = "Shopify"
        elif "wix" in html.lower():
            tech["cms"] = "Wix"
            
        # Framework Detection
        if "react" in html.lower():
            tech["frameworks"].append("React")
        if "angular" in html.lower():
            tech["frameworks"].append("Angular")
        if "vue" in html.lower():
            tech["frameworks"].append("Vue")
        if "jquery" in html.lower():
            tech["frameworks"].append("jQuery")
        if "bootstrap" in html.lower():
            tech["frameworks"].append("Bootstrap")
            
        # Analytics Detection
        if "google-analytics.com" in html or "gtag" in html:
            tech["analytics"].append("Google Analytics")
        if "googletagmanager.com" in html:
            tech["analytics"].append("Google Tag Manager")
        if "facebook.com/tr" in html:
            tech["analytics"].append("Facebook Pixel")
            
        return tech
        
    def calculate_scores(self, analysis: Dict[str, Any]) -> Dict[str, int]:
        """Calculate quality scores"""
        scores = {}
        
        # SEO Score (0-30)
        seo_score = 0
        if analysis.get("title"):
            seo_score += 10
        if analysis.get("description"):
            seo_score += 10
        if analysis.get("headings", {}).get("h1", 0) >= 1:
            seo_score += 5
        if analysis.get("images", {}).get("with_alt", 0) > 0:
            seo_score += 5
        scores["seo"] = min(seo_score, 30)
        
        # Content Score (0-30)
        content_score = 0
        word_count = analysis.get("word_count", 0)
        if word_count > 300:
            content_score += 10
        if word_count > 1000:
            content_score += 10
        if analysis.get("headings", {}).get("h2", 0) > 2:
            content_score += 5
        if analysis.get("images", {}).get("total", 0) > 2:
            content_score += 5
        scores["content"] = min(content_score, 30)
        
        # Technical Score (0-20)
        tech_score = 0
        tech = analysis.get("tech_stack", {})
        if tech.get("analytics"):
            tech_score += 10
        if tech.get("frameworks"):
            tech_score += 10
        scores["technical"] = min(tech_score, 20)
        
        # CRO Score (0-20)
        cro_score = 0
        if analysis.get("forms", 0) > 0:
            cro_score += 10
        if analysis.get("links", {}).get("internal", 0) > 5:
            cro_score += 10
        scores["cro"] = min(cro_score, 20)
        
        # Total Score
        scores["total"] = sum(scores.values())
        
        return scores
        
    def generate_swot(self, analysis: Dict[str, Any], scores: Dict[str, int]) -> Dict[str, List[str]]:
        """Generate SWOT analysis"""
        swot = {
            "strengths": [],
            "weaknesses": [],
            "opportunities": [],
            "threats": []
        }
        
        # Strengths
        if scores.get("seo", 0) > 15:
            swot["strengths"].append(f"Good SEO foundation ({scores['seo']}/30 points)")
        if analysis.get("word_count", 0) > 1000:
            swot["strengths"].append(f"Rich content ({analysis['word_count']} words)")
        if analysis.get("tech_stack", {}).get("analytics"):
            swot["strengths"].append("Analytics tracking implemented")
        if analysis.get("tech_stack", {}).get("frameworks"):
            swot["strengths"].append(f"Modern frameworks: {', '.join(analysis['tech_stack']['frameworks'][:3])}")
            
        # Weaknesses
        if scores.get("seo", 0) < 15:
            swot["weaknesses"].append("SEO needs improvement")
        if analysis.get("word_count", 0) < 500:
            swot["weaknesses"].append("Limited content depth")
        if not analysis.get("tech_stack", {}).get("analytics"):
            swot["weaknesses"].append("Missing analytics tracking")
        if analysis.get("forms", 0) == 0:
            swot["weaknesses"].append("No forms for lead generation")
            
        # Opportunities
        if scores.get("cro", 0) < 10:
            swot["opportunities"].append("Implement conversion optimization")
        if scores.get("content", 0) < 20:
            swot["opportunities"].append("Expand content depth and quality")
        if not analysis.get("tech_stack", {}).get("cms"):
            swot["opportunities"].append("Implement CMS for easier content management")
        swot["opportunities"].append("Implement A/B testing strategy")
            
        # Threats
        if scores.get("total", 0) < 50:
            swot["threats"].append("Risk of losing to better-optimized competitors")
        if not analysis.get("tech_stack", {}).get("cms"):
            swot["threats"].append("Manual content management may limit scalability")
        swot["threats"].append("Increasing competition in digital space")
        
        # Ensure minimum items
        for key in swot:
            if len(swot[key]) == 0:
                swot[key].append(f"Further analysis needed for {key}")
            elif len(swot[key]) == 1:
                swot[key].append(f"Additional {key} to be identified")
                
        return swot
        
    def generate_recommendations(self, analysis: Dict[str, Any], scores: Dict[str, int]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # SEO recommendations
        if scores.get("seo", 0) < 20:
            recommendations.append({
                "title": "Improve SEO Foundation",
                "description": "Optimize meta tags, headings structure, and implement schema markup",
                "priority": "high",
                "timeline": "1-2 weeks",
                "impact": "high"
            })
            
        # Content recommendations
        if analysis.get("word_count", 0) < 1000:
            recommendations.append({
                "title": "Expand Content Depth",
                "description": "Add more comprehensive content to key pages to improve engagement and SEO",
                "priority": "medium",
                "timeline": "2-4 weeks",
                "impact": "high"
            })
            
        # Analytics recommendations
        if not analysis.get("tech_stack", {}).get("analytics"):
            recommendations.append({
                "title": "Implement Analytics Tracking",
                "description": "Install Google Analytics and Tag Manager for data-driven decisions",
                "priority": "high",
                "timeline": "1 week",
                "impact": "high"
            })
            
        # CRO recommendations
        if analysis.get("forms", 0) == 0:
            recommendations.append({
                "title": "Add Lead Generation Forms",
                "description": "Implement contact forms and newsletter signup to capture leads",
                "priority": "high",
                "timeline": "1 week",
                "impact": "medium"
            })
            
        # Technical recommendations
        if not analysis.get("tech_stack", {}).get("frameworks"):
            recommendations.append({
                "title": "Modernize Technology Stack",
                "description": "Consider implementing modern frameworks for better performance",
                "priority": "low",
                "timeline": "3-6 months",
                "impact": "medium"
            })
            
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return recommendations[:5]

# ====================== OpenAI Integration ======================

class OpenAIAnalyzer:
    """OpenAI integration for enhanced analysis"""
    
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and Config.OPENAI_API_KEY:
            try:
                self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
                
    async def enhance_swot(self, analysis: Dict[str, Any], swot: Dict[str, List[str]], language: str = "en") -> Dict[str, Any]:
        """Enhance SWOT with AI insights"""
        if not self.client:
            return swot
            
        try:
            # Prepare prompt
            if language == "fi":
                system_msg = "Olet digitaalisen markkinoinnin asiantuntija. Anna konkreettisia oivalluksia JSON-muodossa."
                prompt = f"""Analysoi tämä sivustodata ja paranna SWOT-analyysia:

Data: {json.dumps(analysis, ensure_ascii=False)[:2000]}
Nykyinen SWOT: {json.dumps(swot, ensure_ascii=False)}

Palauta JSON:
{{
    "yhteenveto": "2-3 lausetta sivuston tilasta",
    "vahvuudet": ["lista vahvuuksista"],
    "heikkoudet": ["lista heikkouksista"],
    "mahdollisuudet": ["lista mahdollisuuksista"],
    "uhat": ["lista uhista"]
}}"""
            else:
                system_msg = "You are a digital marketing expert. Provide concrete insights in JSON format."
                prompt = f"""Analyze this website data and enhance the SWOT analysis:

Data: {json.dumps(analysis)[:2000]}
Current SWOT: {json.dumps(swot)}

Return JSON:
{{
    "summary": "2-3 sentences about the website state",
    "strengths": ["list of strengths"],
    "weaknesses": ["list of weaknesses"],
    "opportunities": ["list of opportunities"],
    "threats": ["list of threats"]
}}"""
            
            # Call OpenAI
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=1000
            )
            
            # Parse response
            if response.choices:
                ai_response = response.choices[0].message.content
                if ai_response:
                    enhanced = json.loads(ai_response)
                    
                    # Merge with original SWOT
                    if language == "fi":
                        return {
                            "yhteenveto": enhanced.get("yhteenveto", ""),
                            "vahvuudet": enhanced.get("vahvuudet", swot["strengths"]),
                            "heikkoudet": enhanced.get("heikkoudet", swot["weaknesses"]),
                            "mahdollisuudet": enhanced.get("mahdollisuudet", swot["opportunities"]),
                            "uhat": enhanced.get("uhat", swot["threats"])
                        }
                    else:
                        return {
                            "summary": enhanced.get("summary", ""),
                            "strengths": enhanced.get("strengths", swot["strengths"]),
                            "weaknesses": enhanced.get("weaknesses", swot["weaknesses"]),
                            "opportunities": enhanced.get("opportunities", swot["opportunities"]),
                            "threats": enhanced.get("threats", swot["threats"])
                        }
                        
        except Exception as e:
            logger.error(f"OpenAI enhancement failed: {e}")
            
        return swot

# ====================== Main Application ======================

# Initialize components
cache = SimpleCache()
engine = AnalysisEngine()
openai_analyzer = OpenAIAnalyzer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Application started")
    yield
    # Cleanup
    if engine.session:
        await engine.session.aclose()
    engine.executor.shutdown(wait=True)
    cache.clear()
    logger.info("Application shutdown")

# Create FastAPI app
app = FastAPI(
    title="AI Competitor Analysis API",
    version="1.5.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== API Endpoints ======================

@app.post("/api/v1/analyze")
async def analyze_website(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Analyze a website or social media profile"""
    
    # Detect platform from URL if not specified
    platform = req.platform
    if not platform:
        if "instagram.com" in req.url:
            platform = "instagram"
        elif "tiktok.com" in req.url:
            platform = "tiktok"
        elif "linkedin.com" in req.url:
            platform = "linkedin"
        elif "facebook.com" in req.url:
            platform = "facebook"
        else:
            platform = "website"
    
    # Generate cache key
    cache_key = hashlib.md5(f"{req.url}:{req.language}:{platform}".encode()).hexdigest()
    
    # Check cache
    cached = cache.get(cache_key)
    if cached and not req.deep_analysis:
        logger.info(f"Returning cached analysis for {req.url}")
        return cached
        
    try:
        # Route to appropriate analyzer
        if platform in ["instagram", "tiktok"]:
            # Social media analysis
            if platform == "instagram":
                social_data = await engine.social_analyzer.analyze_instagram(req.url)
            else:
                social_data = await engine.social_analyzer.analyze_tiktok(req.url)
            
            # Generate social SWOT
            swot = engine.social_analyzer.generate_social_swot(social_data)
            
            # Enhance with AI if available
            if req.use_ai and openai_analyzer.client:
                swot = await openai_analyzer.enhance_swot(social_data, swot, req.language)
            
            response = {
                "success": True,
                "url": req.url,
                "platform": platform,
                "analysis_date": datetime.now().isoformat(),
                "scores": {
                    "social_presence": 50,  # Default score
                    "total": 50
                },
                "analysis": social_data,
                "swot": swot,
                "recommendations": social_data.get("recommendations", [])
            }
        else:
            # Regular website analysis
            page_data = await engine.fetch_page(req.url)
            analysis = engine.analyze_content(page_data["html"], req.url)
            scores = engine.calculate_scores(analysis)
            swot = engine.generate_swot(analysis, scores)
            
            if req.use_ai and openai_analyzer.client:
                swot = await openai_analyzer.enhance_swot(analysis, swot, req.language)
                
            recommendations = engine.generate_recommendations(analysis, scores)
            
            response = {
                "success": True,
                "url": req.url,
                "platform": "website",
                "analysis_date": datetime.now().isoformat(),
                "scores": scores,
                "analysis": analysis,
                "swot": swot,
                "recommendations": recommendations
            }
        
        # Cache in background
        background_tasks.add_task(cache.set, cache_key, response)
        
        return response
        
    except Exception as e:
        logger.error(f"Analysis failed for {req.url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest, background_tasks: BackgroundTasks):
    """Compatibility endpoint for existing system"""
    
    target_url = req.url or req.website
    if not target_url:
        raise HTTPException(status_code=400, detail="url or website required")
        
    # Run analysis
    analyze_req = AnalyzeRequest(
        url=target_url,
        use_ai=req.use_ai,
        language=req.language or "fi"
    )
    
    result = await analyze_website(analyze_req, background_tasks)
    
    # Format for compatibility
    language = (req.language or "fi").lower()
    
    if language == "fi":
        return {
            "success": result["success"],
            "company_name": req.company_name,
            "analysis_date": result["analysis_date"],
            "basic_analysis": {
                "company": req.company_name,
                "website": target_url,
                "industry": req.industry
            },
            "ai_analysis": {
                "yhteenveto": result.get("swot", {}).get("yhteenveto", "Analyysi suoritettu"),
                "vahvuudet": result.get("swot", {}).get("vahvuudet", result.get("swot", {}).get("strengths", [])),
                "heikkoudet": result.get("swot", {}).get("heikkoudet", result.get("swot", {}).get("weaknesses", [])),
                "mahdollisuudet": result.get("swot", {}).get("mahdollisuudet", result.get("swot", {}).get("opportunities", [])),
                "uhat": result.get("swot", {}).get("uhat", result.get("swot", {}).get("threats", [])),
                "toimenpidesuositukset": [
                    {
                        "otsikko": r["title"],
                        "kuvaus": r["description"],
                        "prioriteetti": r["priority"]
                    }
                    for r in result.get("recommendations", [])
                ]
            },
            "smart": {
                "scores": result.get("scores", {}),
                "tech_cro": result.get("analysis", {}).get("tech_stack", {})
            }
        }
    else:
        return {
            "success": result["success"],
            "company_name": req.company_name,
            "analysis_date": result["analysis_date"],
            "basic_analysis": {
                "company": req.company_name,
                "website": target_url,
                "industry": req.industry
            },
            "ai_analysis": {
                "summary": result.get("swot", {}).get("summary", "Analysis completed"),
                "strengths": result.get("swot", {}).get("strengths", []),
                "weaknesses": result.get("swot", {}).get("weaknesses", []),
                "opportunities": result.get("swot", {}).get("opportunities", []),
                "threats": result.get("swot", {}).get("threats", []),
                "recommendations": result.get("recommendations", [])
            },
            "smart": {
                "scores": result.get("scores", {}),
                "tech_cro": result.get("analysis", {}).get("tech_stack", {})
            }
        }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "api": "operational",
            "openai": "operational" if openai_analyzer.client else "not configured"
        }
    }

@app.get("/")
async def root():
    """API information"""
    return {
        "name": "AI Competitor Analysis API",
        "version": "1.5.0",
        "endpoints": [
            "/api/v1/analyze - Website analysis",
            "/api/v1/ai-analyze - Compatibility endpoint",
            "/health - Health check"
        ],
        "documentation": "/docs"
    }

# ====================== Main Entry Point ======================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )
