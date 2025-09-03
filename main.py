#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 4.3.2
"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Enhanced Version
Version: 5.1.0
Enhanced with AI features, clean architecture
"""

# ================== IMPORTS ================== #

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter
import statistics

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import numpy as np

# AI imports (optional but recommended)
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================== APP SETUP ================== #

APP_VERSION = "5.1.0"

app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Advanced competitive analysis with AI capabilities"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI setup
openai_client = None
if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "true").lower() == "true"

# ================== MODELS ================== #

class AnalyzeRequest(BaseModel):
    url: str
    use_ai: bool = True
    render_js: bool = False

class AIAnalyzeRequest(BaseModel):
    url: str
    company_name: str
    use_ai: bool = True
    include_swot: bool = True
    include_recommendations: bool = True
    language: str = "fi"

class DeepAnalysisRequest(BaseModel):
    url: str
    company_name: str
    competitors: List[str] = []
    include_positioning: bool = True
    language: str = "fi"

class BatchAnalyzeRequest(BaseModel):
    urls: List[str]
    use_ai: bool = True
    include_comparisons: bool = True

# ================== CACHE ================== #

analysis_cache: Dict[str, Dict[str, Any]] = {}

def cache_key(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode("utf-8")).hexdigest()

def get_cached_analysis(url: str):
    key = cache_key(url)
    cached = analysis_cache.get(key)
    if cached and (datetime.now() - cached['timestamp'] < timedelta(hours=24)):
        return cached['data']
    return None

def save_to_cache(url: str, data: dict):
    key = cache_key(url)
    analysis_cache[key] = {'timestamp': datetime.now(), 'data': data}

# ================== ENHANCED AI ANALYZER CLASS ================== #

class EnhancedAIAnalyzer:
    """Enhanced AI analyzer with multiple analysis capabilities"""
    
    def __init__(self):
        self.openai_client = openai_client
        
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text content"""
        if not TEXTBLOB_AVAILABLE:
            return {
                "available": False,
                "message": "TextBlob not installed"
            }
        
        try:
            blob = TextBlob(text[:5000])
            polarity = float(blob.sentiment.polarity)
            
            return {
                "polarity": polarity,
                "subjectivity": float(blob.sentiment.subjectivity),
                "sentiment_label": self._get_sentiment_label(polarity),
                "confidence": abs(polarity),
                "available": True
            }
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {"available": False, "error": str(e)}
    
    def _get_sentiment_label(self, polarity: float) -> str:
        if polarity > 0.3:
            return "positive"
        elif polarity < -0.3:
            return "negative"
        return "neutral"
    
    def detect_industry(self, content: Dict) -> Dict[str, Any]:
        """Detect industry based on content analysis"""
        industry_keywords = {
            "technology": ["software", "app", "platform", "digital", "cloud", "AI", "data", "tech"],
            "healthcare": ["health", "medical", "patient", "clinic", "doctor", "therapy", "hospital"],
            "finance": ["banking", "investment", "financial", "payment", "insurance", "fintech"],
            "retail": ["shop", "store", "product", "buy", "sale", "customer", "ecommerce"],
            "education": ["learn", "course", "student", "education", "training", "academy", "school"],
            "manufacturing": ["production", "factory", "industrial", "equipment", "supply", "logistics"],
            "hospitality": ["hotel", "restaurant", "travel", "tourism", "booking", "vacation"],
            "real_estate": ["property", "real estate", "apartment", "house", "rent", "housing"],
            "automotive": ["car", "vehicle", "automotive", "driving", "motor", "auto"],
            "media": ["news", "content", "media", "publishing", "entertainment", "broadcast"]
        }
        
        text = f"{content.get('title', '')} {content.get('description', '')} {content.get('text_content', '')}".lower()
        
        industry_scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                industry_scores[industry] = score
        
        if industry_scores:
            primary_industry = max(industry_scores, key=industry_scores.get)
            confidence = industry_scores[primary_industry] / max(sum(industry_scores.values()), 1)
        else:
            primary_industry = "general"
            confidence = 0.0
        
        return {
            "primary_industry": primary_industry,
            "confidence": round(confidence, 2),
            "all_scores": industry_scores,
            "detected_at": datetime.now().isoformat()
        }
    
    def analyze_content_quality(self, data: Dict) -> Dict[str, Any]:
        """Analyze content quality and engagement potential"""
        quality_score = 0
        factors = []
        recommendations = []
        
        # Title analysis
        title = data.get('title', '')
        if title:
            quality_score += 10
            if 30 <= len(title) <= 70:
                quality_score += 5
                factors.append("optimal_title_length")
            else:
                recommendations.append("Optimize title length (30-70 chars)")
        else:
            recommendations.append("Add page title")
        
        # Description analysis
        description = data.get('description', '')
        if description:
            quality_score += 10
            if 120 <= len(description) <= 160:
                quality_score += 5
                factors.append("optimal_description_length")
            else:
                recommendations.append("Optimize meta description (120-160 chars)")
        else:
            recommendations.append("Add meta description")
        
        # Content depth - KORJATTU: käytetään word_count suoraan
        word_count = data.get('word_count', 0)
        if word_count > 2000:
            quality_score += 20
            factors.append("comprehensive_content")
        elif word_count > 1000:
            quality_score += 15
            factors.append("good_content_depth")
        elif word_count > 500:
            quality_score += 10
            factors.append("adequate_content")
        else:
            recommendations.append(f"Increase content depth (current: {word_count} words)")
        
        # Technical factors
        if data.get('smart', {}).get('head_signals', {}).get('canonical'):
            quality_score += 5
            factors.append("has_canonical")
        else:
            recommendations.append("Add canonical URL")
        
        if data.get('smart', {}).get('head_signals', {}).get('og_status', {}).get('has_title'):
            quality_score += 5
            factors.append("og_tags_present")
        else:
            recommendations.append("Add Open Graph tags")
        
        # Technologies
        tech = data.get('smart', {}).get('tech_cro', {})
        if tech.get('analytics_pixels'):
            quality_score += 10
            factors.append("analytics_tracking")
        else:
            recommendations.append("Implement analytics tracking")
        
        if tech.get('cms') or tech.get('framework'):
            quality_score += 10
            factors.append("modern_tech_stack")
        
        # CRO elements
        if tech.get('cta_count', 0) > 3:
            quality_score += 10
            factors.append("good_cro_elements")
        elif tech.get('cta_count', 0) > 0:
            quality_score += 5
            recommendations.append("Add more CTA elements")
        else:
            recommendations.append("Add clear call-to-action buttons")
        
        # Mobile & Security
        if data.get('url', '').startswith('https'):
            quality_score += 5
            factors.append("secure_connection")
        else:
            recommendations.append("Implement HTTPS")
        
        return {
            "quality_score": min(quality_score, 100),
            "factors": factors,
            "grade": self._get_quality_grade(min(quality_score, 100)),
            "recommendations": recommendations[:5],
            "summary": self._get_quality_summary(min(quality_score, 100))
        }
    
    def _get_quality_grade(self, score: int) -> str:
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        return "F"
    
    def _get_quality_summary(self, score: int) -> str:
        if score >= 80:
            return "Excellent digital presence with strong optimization"
        elif score >= 60:
            return "Good foundation with room for improvement"
        elif score >= 40:
            return "Basic digital presence needs enhancement"
        return "Significant improvements needed across multiple areas"
    
    def analyze_competitive_positioning(self, target: Dict, competitors: List[Dict]) -> Dict[str, Any]:
        """Analyze competitive positioning"""
        positioning = {
            "market_position": "unknown",
            "competitive_advantages": [],
            "improvement_areas": [],
            "opportunities": [],
            "threats": [],
            "relative_score": 0,
            "recommendation_priority": []
        }
        
        # Get quality scores
        target_quality = self.analyze_content_quality(target)
        target_score = target_quality['quality_score']
        
        if competitors:
            competitor_scores = []
            for comp in competitors:
                comp_quality = self.analyze_content_quality(comp)
                competitor_scores.append(comp_quality['quality_score'])
            
            avg_competitor_score = statistics.mean(competitor_scores) if competitor_scores else 0
            positioning["relative_score"] = round(target_score - avg_competitor_score, 1)
            
            # Determine market position
            if target_score > avg_competitor_score + 20:
                positioning["market_position"] = "market_leader"
            elif target_score > avg_competitor_score:
                positioning["market_position"] = "above_average"
            elif target_score > avg_competitor_score - 10:
                positioning["market_position"] = "average"
            else:
                positioning["market_position"] = "below_average"
            
            # Competitive advantages
            if target_score > avg_competitor_score:
                positioning["competitive_advantages"].append(
                    f"Superior quality score: {target_score}% vs {avg_competitor_score:.0f}% average"
                )
            
            # Tech advantages
            target_tech = set(target.get('smart', {}).get('tech_cro', {}).get('analytics_pixels', []))
            all_competitor_tech = set()
            for comp in competitors:
                all_competitor_tech.update(comp.get('smart', {}).get('tech_cro', {}).get('analytics_pixels', []))
            
            unique_tech = target_tech - all_competitor_tech
            if unique_tech:
                positioning["competitive_advantages"].append(f"Unique technologies: {', '.join(unique_tech)}")
            
            missing_tech = all_competitor_tech - target_tech
            if missing_tech:
                positioning["opportunities"].append(f"Adopt competitor technologies: {', '.join(missing_tech)}")
        
        # Set recommendations
        if positioning["market_position"] == "below_average":
            positioning["recommendation_priority"] = [
                "Immediate action required to improve competitive position",
                "Focus on quick wins from quality recommendations",
                "Benchmark against top performers"
            ]
        elif positioning["market_position"] == "average":
            positioning["recommendation_priority"] = [
                "Steady improvements to gain competitive edge",
                "Identify unique value propositions"
            ]
        else:
            positioning["recommendation_priority"] = [
                "Maintain leadership position",
                "Continue innovation and optimization"
            ]
        
        return positioning
    
    def extract_keywords(self, text: str, max_keywords: int = 15) -> List[Dict[str, Any]]:
        """Extract and rank keywords from content"""
        # Clean and prepare text
        text = text.lower()
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'been', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'could', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        words = re.findall(r'\b[a-z]+\b', text)
        words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if not words:
            return []
        
        word_freq = Counter(words)
        total_words = len(words)
        
        keywords = []
        for word, count in word_freq.most_common(max_keywords):
            keywords.append({
                "keyword": word,
                "frequency": count,
                "density": round((count / total_words * 100), 2)
            })
        
        return keywords

# ================== CORE FUNCTIONS ================== #

def extract_head_signals(soup: BeautifulSoup):
    """Extract important signals from HTML head"""
    head = soup.find('head') or soup
    canonical = (head.find('link', rel='canonical') or {}).get('href') if head else None
    og = {m.get('property'): m.get('content') for m in head.find_all('meta') if m.get('property','').startswith('og:')}
    tw = {m.get('name'): m.get('content') for m in head.find_all('meta') if m.get('name','').startswith('twitter:')}
    
    return {
        "canonical": canonical,
        "og_status": {
            "has_title": bool(og.get('og:title')),
            "has_desc": bool(og.get('og:description')),
            "has_image": bool(og.get('og:image'))
        },
        "twitter_status": {
            "has_title": bool(tw.get('twitter:title')),
            "has_desc": bool(tw.get('twitter:description')),
            "has_image": bool(tw.get('twitter:image'))
        }
    }

def detect_tech_and_cro(soup: BeautifulSoup, html_text: str):
    """Detect technologies and CRO elements"""
    lower = html_text.lower()
    
    TECH_HINTS = {
        "cms": [
            ("wordpress", "WordPress"), ("shopify", "Shopify"), 
            ("wix", "Wix"), ("webflow", "Webflow"),
            ("woocommerce", "WooCommerce"), ("squarespace", "Squarespace")
        ],
        "framework": [
            ("__next", "Next.js"), ("nuxt", "Nuxt"),
            ("react", "React"), ("angular", "Angular"),
            ("vue", "Vue.js"), ("svelte", "Svelte")
        ],
        "analytics": [
            ("gtag(", "GA4/gtag"), ("googletagmanager.com", "GTM"),
            ("facebook.net/en_US/fbevents.js", "Meta Pixel"),
            ("clarity.ms", "MS Clarity"), ("hotjar", "Hotjar")
        ]
    }
    
    cms = next((name for key, name in TECH_HINTS["cms"] if key in lower), None)
    framework = next((name for key, name in TECH_HINTS["framework"] if key in lower), None)
    analytics_pixels = [name for key, name in TECH_HINTS["analytics"] if key in lower]
    
    CTA_WORDS = [
        "osta", "tilaa", "varaa", "lataa", "book", "buy", 
        "subscribe", "contact", "get started", "request",
        "pyydä tarjous", "varaa aika", "aloita"
    ]
    
    cta_count = sum(
        1 for el in soup.find_all(["a", "button"]) 
        if any(w in (el.get_text(" ", strip=True) or "").lower() for w in CTA_WORDS)
    )
    
    forms_count = len(soup.find_all("form"))
    
    return {
        "cms": cms,
        "framework": framework,
        "analytics_pixels": sorted(list(set(analytics_pixels))),
        "cta_count": cta_count,
        "forms_count": forms_count
    }

def analyze_content(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Deep content analysis"""
    content_analysis = {
        "headings": {},
        "images": {"total": 0, "with_alt": 0, "without_alt": 0},
        "links": {"internal": 0, "external": 0, "total": 0},
        "text_content": "",
        "services_hints": [],
        "trust_signals": []
    }
    
    # Extract headings
    for i in range(1, 7):
        h_tags = soup.find_all(f'h{i}')
        if h_tags:
            content_analysis["headings"][f'h{i}'] = [
                tag.get_text(strip=True)[:100] for tag in h_tags[:5]
            ]
    
    # Analyze images
    images = soup.find_all('img')
    content_analysis["images"]["total"] = len(images)
    content_analysis["images"]["with_alt"] = len([img for img in images if img.get('alt')])
    content_analysis["images"]["without_alt"] = len(images) - content_analysis["images"]["with_alt"]
    
    # Extract text
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    content_analysis["text_content"] = text[:3000]
    
    # Detect trust signals
    trust_patterns = [
        (r'\d{4,}-\d{4,}', 'Y-tunnus'),
        (r'ISO[ -]?\d{4,}', 'ISO-sertifikaatti'),
        (r'palkinto|award', 'Palkinnot'),
        (r'asiakasta|clients|customers', 'Asiakasreferenssit')
    ]
    
    text_lower = text.lower()
    for pattern, signal_type in trust_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            content_analysis["trust_signals"].append(signal_type)
    
    return content_analysis

async def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 30) -> str:
    """Fetch URL content with retry logic"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except Exception as e:
            if attempt == max_retries - 1:
                raise HTTPException(status_code=500, detail=f"Failed to fetch {url}: {str(e)}")
            await asyncio.sleep(2 ** attempt)

# ================== MAIN ENDPOINTS ================== #

@app.get("/")
def home():
    """API information and status"""
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status": "operational",
        "features": {
            "ai_analysis": TEXTBLOB_AVAILABLE,
            "openai": bool(openai_client),
            "js_render": SMART_JS_RENDER
        },
        "endpoints": [
            "/api/v1/analyze",
            "/api/v2/ai-analyze",
            "/api/v1/deep-analysis",
            "/api/v1/batch-analyze-enhanced",
            "/api/v1/compare-enhanced/{url1}/{url2}"
        ]
    }

@app.post("/api/v1/analyze")
async def analyze_competitor(request: AnalyzeRequest):
    """Basic competitor analysis with optional AI"""
    try:
        # Check cache
        cached = get_cached_analysis(request.url)
        if cached:
            return cached
        
        # Fetch content
        url = request.url if request.url.startswith("http") else f"https://{request.url}"
        html = await fetch_with_retry(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract data
        title = soup.find('title')
        title = title.text.strip() if title else ""
        
        meta_desc = soup.find('meta', {'name': 'description'})
        description = meta_desc.get('content', '') if meta_desc else ""
        
        word_count = len(soup.get_text().split())
        
        # Smart analysis
        head_signals = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, html)
        content_data = analyze_content(soup, url)
        
        result = {
            "success": True,
            "url": url,
            "title": title,
            "description": description,
            "word_count": word_count,
            "smart": {
                "head_signals": head_signals,
                "tech_cro": tech_cro,
                "content_analysis": content_data
            }
        }
        
        # Add AI analysis if requested
        if request.use_ai:
            ai_analyzer = EnhancedAIAnalyzer()
            result["ai_analysis"] = {
                "content_quality": ai_analyzer.analyze_content_quality(result),
                "industry": ai_analyzer.detect_industry(result),
                "keywords": ai_analyzer.extract_keywords(
                    f"{title} {description} {content_data['text_content']}"
                )[:10]
            }
            
            if TEXTBLOB_AVAILABLE:
                result["ai_analysis"]["sentiment"] = ai_analyzer.analyze_sentiment(
                    content_data['text_content']
                )
        
        save_to_cache(request.url, result)
        return result
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/ai-analyze")
async def ai_analyze_enhanced(request: AIAnalyzeRequest):
    """Enhanced AI analysis with SWOT and recommendations"""
    try:
        # First run basic analysis
        basic_result = await analyze_competitor(
            AnalyzeRequest(url=request.url, use_ai=request.use_ai)
        )
        
        ai_analyzer = EnhancedAIAnalyzer()
        
        # Enhanced analysis result
        result = {
            "success": True,
            "company_name": request.company_name,
            "analysis_date": datetime.now().isoformat(),
            "url": request.url,
            "basic_metrics": {
                "title": basic_result["title"],
                "description": basic_result["description"],
                "word_count": basic_result["word_count"],
                "technologies": basic_result["smart"]["tech_cro"]["analytics_pixels"],
                "cms": basic_result["smart"]["tech_cro"]["cms"],
                "framework": basic_result["smart"]["tech_cro"]["framework"]
            }
        }
        
        # AI Analysis
        if request.use_ai and "ai_analysis" in basic_result:
            result["ai_insights"] = {
                "quality": basic_result["ai_analysis"]["content_quality"],
                "industry": basic_result["ai_analysis"]["industry"],
                "keywords": basic_result["ai_analysis"]["keywords"][:5],
                "sentiment": basic_result["ai_analysis"].get("sentiment", {})
            }
        
        # SWOT Analysis
        if request.include_swot:
            result["swot"] = generate_swot_analysis(basic_result, request.language)
        
        # Recommendations
        if request.include_recommendations:
            result["recommendations"] = generate_recommendations(basic_result, request.language)
        
        return result
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/deep-analysis")
async def deep_analysis(request: DeepAnalysisRequest):
    """Deep competitive analysis with positioning"""
    try:
        # Analyze main site
        main_analysis = await analyze_competitor(
            AnalyzeRequest(url=request.url, use_ai=True)
        )
        
        # Analyze competitors
        competitor_analyses = []
        for comp_url in request.competitors[:5]:  # Max 5 competitors
            try:
                comp = await analyze_competitor(
                    AnalyzeRequest(url=comp_url, use_ai=True)
                )
                competitor_analyses.append(comp)
            except:
                continue
        
        # Competitive positioning
        ai_analyzer = EnhancedAIAnalyzer()
        positioning = ai_analyzer.analyze_competitive_positioning(
            main_analysis,
            competitor_analyses
        )
        
        return {
            "success": True,
            "company": request.company_name,
            "target_analysis": main_analysis,
            "competitors_analyzed": len(competitor_analyses),
            "positioning": positioning,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Deep analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/batch-analyze-enhanced")
async def batch_analyze(request: BatchAnalyzeRequest):
    """Analyze multiple URLs with comparisons"""
    try:
        results = []
        
        # Analyze each URL
        for url in request.urls[:10]:  # Max 10
            try:
                analysis = await analyze_competitor(
                    AnalyzeRequest(url=url, use_ai=request.use_ai)
                )
                results.append(analysis)
            except Exception as e:
                results.append({
                    "url": url,
                    "success": False,
                    "error": str(e)
                })
        
        # Generate insights
        successful = [r for r in results if r.get("success")]
        
        batch_insights = {
            "total_analyzed": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "summary": generate_batch_summary(successful)
        }
        
        # Comparisons if requested
        if request.include_comparisons and len(successful) > 1:
            ai_analyzer = EnhancedAIAnalyzer()
            comparisons = []
            
            for i, analysis in enumerate(successful):
                others = [s for j, s in enumerate(successful) if j != i]
                positioning = ai_analyzer.analyze_competitive_positioning(analysis, others)
                comparisons.append({
                    "url": analysis["url"],
                    "positioning": positioning
                })
            
            batch_insights["comparisons"] = comparisons
        
        return {
            "success": True,
            "results": results,
            "insights": batch_insights,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/compare-enhanced/{url1}/{url2}")
async def compare_enhanced(url1: str, url2: str):
    """Enhanced comparison between two competitors"""
    try:
        # Analyze both
        analysis1 = await analyze_competitor(AnalyzeRequest(url=url1, use_ai=True))
        analysis2 = await analyze_competitor(AnalyzeRequest(url=url2, use_ai=True))
        
        ai_analyzer = EnhancedAIAnalyzer()
        
        # Quality comparison
        quality1 = ai_analyzer.analyze_content_quality(analysis1)
        quality2 = ai_analyzer.analyze_content_quality(analysis2)
        
        # Positioning
        pos1 = ai_analyzer.analyze_competitive_positioning(analysis1, [analysis2])
        pos2 = ai_analyzer.analyze_competitive_positioning(analysis2, [analysis1])
        
        # Winner determination
        winner = None
        if quality1["quality_score"] > quality2["quality_score"]:
            winner = {"url": url1, "reason": "Higher quality score"}
        elif quality2["quality_score"] > quality1["quality_score"]:
            winner = {"url": url2, "reason": "Higher quality score"}
        else:
            winner = {"result": "tie", "reason": "Equal quality scores"}
        
        return {
            "success": True,
            "comparison": {
                "site1": {
                    "url": url1,
                    "quality": quality1,
                    "positioning": pos1
                },
                "site2": {
                    "url": url2,
                    "quality": quality2,
                    "positioning": pos2
                },
                "winner": winner,
                "score_difference": abs(quality1["quality_score"] - quality2["quality_score"])
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ================== HELPER FUNCTIONS ================== #

def generate_swot_analysis(data: Dict, language: str = "fi") -> Dict:
    """Generate SWOT analysis from data"""
    swot = {
        "strengths": [],
        "weaknesses": [],
        "opportunities": [],
        "threats": []
    }
    
    # Analyze strengths
    if data.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0) > 70:
        swot["strengths"].append(
            "Korkea laatupisteet digitaalisessa läsnäolossa" if language == "fi" 
            else "High quality digital presence"
        )
    
    tech = data.get("smart", {}).get("tech_cro", {})
    if tech.get("analytics_pixels"):
        swot["strengths"].append(
            f"Analytiikka käytössä: {', '.join(tech['analytics_pixels'])}"
        )
    
    # Analyze weaknesses
    quality = data.get("ai_analysis", {}).get("content_quality", {})
    for rec in quality.get("recommendations", [])[:3]:
        swot["weaknesses"].append(rec)
    
    # Opportunities
    if not tech.get("cms"):
        swot["opportunities"].append(
            "CMS-järjestelmän käyttöönotto" if language == "fi"
            else "Implement CMS system"
        )
    
    # Threats
    if quality.get("quality_score", 0) < 50:
        swot["threats"].append(
            "Kilpailijat voivat ohittaa hakukonenäkyvyydessä" if language == "fi"
            else "Competitors may overtake in search rankings"
        )
    
    return swot

def generate_recommendations(data: Dict, language: str = "fi") -> List[Dict]:
    """Generate actionable recommendations"""
    recommendations = []
    
    quality = data.get("ai_analysis", {}).get("content_quality", {})
    
    # Use quality recommendations
    for i, rec in enumerate(quality.get("recommendations", []), 1):
        recommendations.append({
            "priority": "high" if i <= 2 else "medium",
            "title": rec,
            "timeline": "1-3 months",
            "impact": "high" if "meta" in rec.lower() or "https" in rec.lower() else "medium"
        })
    
    return recommendations[:5]

def generate_batch_summary(analyses: List[Dict]) -> Dict:
    """Generate summary from batch analyses"""
    if not analyses:
        return {}
    
    # Calculate averages
    quality_scores = []
    all_tech = []
    
    for analysis in analyses:
        if "ai_analysis" in analysis:
            score = analysis["ai_analysis"].get("content_quality", {}).get("quality_score", 0)
            quality_scores.append(score)
        
        tech = analysis.get("smart", {}).get("tech_cro", {}).get("analytics_pixels", [])
        all_tech.extend(tech)
    
    return {
        "average_quality": round(statistics.mean(quality_scores), 1) if quality_scores else 0,
        "common_technologies": list(set(all_tech)),
        "best_performer": max(analyses, key=lambda x: x.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0)).get("url") if analyses else None
    }

# ================== ERROR HANDLING ================== #

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

# ================== STARTUP ================== #

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting Brandista API v{APP_VERSION}")
    logger.info(f"AI features: TextBlob={TEXTBLOB_AVAILABLE}, OpenAI={bool(openai_client)}")
    logger.info(f"Cache enabled, JS render: {SMART_JS_RENDER}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

# ================== OSA 1/5 ALKAA: IMPORTIT, SETUP & MODELS ================== #

import os
import re
import json
import base64
import hashlib
import logging
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from functools import lru_cache
from collections import defaultdict

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# System monitoring (optional)
try:
    import psutil  # noqa: F401
    import platform  # noqa: F401
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore

# PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

APP_VERSION = "4.3.2"

# ========== APP INITIALIZATION - TÄMÄ ENNEN KAIKKEA MUUTA! ========== #

app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Kilpailija-analyysi API with AI ja Smart Analyzer"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # kiristä tarvittaessa production-käytössä
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security header middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp

# OpenAI client (optional)
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if (AsyncOpenAI and os.getenv("OPENAI_API_KEY")) else None

# Feature flag: JS render on/off (default ON tässä buildissa)
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "1").lower() in ("1", "true", "yes")

# ========== CACHE HELPERS ========== #

analysis_cache: Dict[str, Dict[str, Any]] = {}

def cache_key(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode("utf-8")).hexdigest()

def get_cached_analysis(url: str):
    """Hae välimuistista jos alle 24h vanha"""
    key = cache_key(url)
    cached = analysis_cache.get(key)
    if cached and (datetime.now() - cached['timestamp'] < timedelta(hours=24)):
        return cached['data']
    return None

def save_to_cache(url: str, data: dict):
    """Tallenna välimuistiin"""
    key = cache_key(url)
    analysis_cache[key] = {'timestamp': datetime.now(), 'data': data}

# ========== PYDANTIC MODELS ========== #

class AnalyzeRequest(BaseModel):
    url: str

class SmartAnalyzeResponse(BaseModel):
    success: bool
    url: str
    title: str
    description: str
    score: int
    insights: Dict[str, Any]
    smart: Dict[str, Any]

class CompetitorAnalysisRequest(BaseModel):
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    strengths: Optional[List[str]] = []
    weaknesses: Optional[List[str]] = []
    market_position: Optional[str] = None
    use_ai: Optional[bool] = True
    url: Optional[str] = None   # voi käyttää samaa kenttää analyysiin
    language: Optional[str] = 'fi'

# ================== OSA 1/5 LOPPUU ================== #
# SEURAAVAKSI: Helper funktiot (OSA 2/5)# ================== OSA 2/5 ALKAA: HELPER FUNCTIONS ================== #

def maybe_scrape_with_javascript(url: str) -> Optional[str]:
    """
    Renderöi JS lazyna. Palauttaa HTML-stringin tai None, jos ei saatavilla/onnistunut.
    """
    if not SMART_JS_RENDER:
        return None
    try:
        # Lazy import, ettei boot kaadu jos deps puuttuu
        from requests_html import HTMLSession  # type: ignore
    except Exception as e:
        print(f"[JS-RENDER] requests_html unavailable: {e}")
        return None

    try:
        session = HTMLSession()
        response = session.get(url, timeout=30)
        # lataa ensimmäisellä ajolla headless Chromiumin
        response.html.render(timeout=20, sleep=2)
        return response.html.html
    except Exception as e:
        print(f"[JS-RENDER] Rendering failed: {e}")
        return None

async def fetch_text(client, url):
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""

async def collect_robots_and_sitemap(base_url):
    from urllib.parse import urljoin
    origin = base_url.split('/', 3)[:3]
    origin = '/'.join(origin) + '/'
    client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    robots_txt = await fetch_text(client, urljoin(origin, 'robots.txt'))
    sitemaps = re.findall(r'(?i)Sitemap:\s*(\S+)', robots_txt) if robots_txt else []
    sitemap_urls = sitemaps or [urljoin(origin, 'sitemap.xml')]
    urls, latest_date = [], None
    for sm in sitemap_urls[:3]:
        xml = await fetch_text(client, sm)
        if not xml:
            continue
        locs = re.findall(r'<loc>(.*?)</loc>', xml)
        dates = re.findall(r'<lastmod>(.*?)</lastmod>', xml)
        urls.extend(locs[:100])
        for d in dates:
            try:
                dt = datetime.fromisoformat(d.replace('Z','+00:00')).date()
                latest_date = max(latest_date, dt) if latest_date else dt
            except Exception:
                pass
    await client.aclose()
    return {
        "sitemap_count": len(sitemap_urls),
        "url_sample_count": len(urls),
        "latest_post_date": str(latest_date) if latest_date else None
    }

def extract_head_signals(soup: BeautifulSoup):
    head = soup.find('head') or soup
    canonical = (head.find('link', rel='canonical') or {}).get('href') if head else None
    hreflangs = [l.get('href') for l in head.find_all('link', rel='alternate') if l.get('hreflang')]
    og = {m.get('property'): m.get('content') for m in head.find_all('meta') if m.get('property','').startswith('og:')}
    tw = {m.get('name'): m.get('content') for m in head.find_all('meta') if (m.get('name','').startswith('twitter:'))}
    jsonld = []
    for tag in head.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '{}')
            jsonld.append(data)
        except Exception:
            pass
    types = []
    for block in jsonld:
        t = block.get('@type')
        if isinstance(t, list): types.extend(t)
        elif t: types.append(t)
    return {
        "canonical": canonical,
        "hreflang_count": len(hreflangs),
        "og_status": {
            "has_title": bool(og.get('og:title')),
            "has_desc": bool(og.get('og:description')),
            "has_image": bool(og.get('og:image'))
        },
        "twitter_status": {
            "has_title": bool(tw.get('twitter:title')),
            "has_desc": bool(tw.get('twitter:description')),
            "has_image": bool(tw.get('twitter:image'))
        },
        "schema_counts": {t: types.count(t) for t in set(types)}
    }

TECH_HINTS = {
    "cms": [("wordpress","WordPress"),("shopify","Shopify"),("wix","Wix"),("webflow","Webflow"),("woocommerce","WooCommerce"),("squarespace","Squarespace")],
    "framework": [("__next","Next.js"),("nuxt","Nuxt"),("vite","Vite"),("astro","Astro"),("sapper","Sapper"),("reactRoot","React")],
    "analytics": [("gtag(","GA4/gtag"),("googletagmanager.com","GTM"),("facebook.net/en_US/fbevents.js","Meta Pixel"),("clarity.ms","MS Clarity"),("hotjar","Hotjar"),("clarity(", "MS Clarity")]
}

def detect_tech_and_cro(soup: BeautifulSoup, html_text: str):
    lower = html_text.lower()
    gen = (soup.find('meta', attrs={'name':'generator'}) or {}).get('content','').lower()
    cms = next((name for key,name in TECH_HINTS["cms"] if key in gen or key in lower), None)
    framework = next((name for key,name in TECH_HINTS["framework"] if key in lower), None)
    analytics_pixels = [name for key,name in TECH_HINTS["analytics"] if key in lower]

    CTA_WORDS = ["osta","tilaa","varaa","lataa","book","buy","subscribe","contact","get started","request a quote","pyydä tarjous","varaa aika","aloita"]
    cta_count = sum(1 for el in soup.find_all(["a","button"]) if any(w in (el.get_text(" ", strip=True) or "").lower() for w in CTA_WORDS))
    forms_count = len(soup.find_all("form"))

    contact_channels = []
    text = soup.get_text(" ", strip=True)
    if re.search(r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b', text, re.I): contact_channels.append("email")
    if re.search(r'\+?\d[\d\s().-]{6,}', text): contact_channels.append("phone")
    if "wa.me/" in lower or "api.whatsapp.com" in lower: contact_channels.append("whatsapp")

    languages = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if re.search(r'/fi(/|$)', href): languages.add('fi')
        if re.search(r'/en(/|$)', href): languages.add('en')
        if re.search(r'/sv(/|$)', href): languages.add('sv')

    return {
        "cms": cms, "framework": framework, "analytics_pixels": sorted(list(set(analytics_pixels))),
        "cta_count": cta_count, "forms_count": forms_count,
        "contact_channels": sorted(list(set(contact_channels))),
        "languages": sorted(list(languages))
    }

def score_and_recommend(head_sig, tech_cro, word_count):
    seo_score = 0
    seo_score += 10 if head_sig['canonical'] else 0
    seo_score += 10 if head_sig['og_status']['has_title'] else 0
    content_score = 15 if word_count > 10000 else 8 if word_count > 5000 else 0
    cro_score = min(15, tech_cro['cta_count']*2) + (5 if tech_cro['forms_count'] > 0 else 0)
    trust_score = 5 if 'Organization' in head_sig['schema_counts'] else 0
    tech_score = 5 if tech_cro['analytics_pixels'] else 0
    total = min(100, seo_score + content_score + cro_score + trust_score + tech_score)

    findings, actions = [], []
    if not head_sig['canonical']:
        findings.append("Canonical puuttuu → riski duplikaateista")
        actions.append({"otsikko":"Lisää canonical","kuvaus":"Aseta kanoninen osoite kaikille sivuille","prioriteetti":"korkea","aikataulu":"heti","mittari":"Canonical löytyy"})
    if not (head_sig['og_status']['has_title'] and head_sig['og_status']['has_desc']):
        findings.append("OG-metat vajaat/puuttuu → heikko jaettavuus")
        actions.append({"otsikko":"OG-perusmetat kuntoon","kuvaus":"og:title & og:description + 1200×630 og:image","prioriteetti":"keskitaso","aikataulu":"1–3kk","mittari":"OG-validi"})
    if content_score == 0:
        findings.append("Sisältö vähäinen → kasvata laadukasta tekstiä")
        actions.append({"otsikko":"Sisältöohjelma","kuvaus":"2–4 artikkelia/kk, FAQ ja case-tarinat","prioriteetti":"korkea","aikataulu":"1–3kk","mittari":"Julkaisutahti"})
    if tech_cro['cta_count'] < 2:
        findings.append("Vähän CTA-elementtejä → heikko ohjaus konversioon")
        actions.append({"otsikko":"Lisää CTA-napit","kuvaus":"Heroon pää-CTA + osioihin toissijaiset","prioriteetti":"korkea","aikataulu":"heti","mittari":"CTA-tiheys"})
    if not tech_cro['analytics_pixels']:
        findings.append("Analytiikka/pikselit puuttuvat → ei seurantaa")
        actions.append({"otsikko":"Asenna analytiikka & pikselit","kuvaus":"GA4, GTM, Meta Pixel, LinkedIn Insight","prioriteetti":"korkea","aikataulu":"heti","mittari":"Tägien läsnäolo"})

    return {
        "scores":{"seo":seo_score,"content":content_score,"cro":cro_score,"trust":trust_score,"tech":tech_score,"total":total},
        "top_findings":findings[:6],
        "actions":actions[:8]
    }

def _find_common_patterns(findings_lists):
    """Tunnista yleisimmät löydökset"""
    all_findings = []
    for findings in findings_lists:
        all_findings.extend(findings)

    patterns = {}
    keywords = ['canonical', 'CTA', 'analytiikka', 'sisältö', 'OG-meta']
    for keyword in keywords:
        count = sum(1 for f in all_findings if keyword.lower() in f.lower())
        if count > 0:
            patterns[keyword] = count
    return patterns

def _analyze_tech_distribution(results):
    """Analysoi teknologiajakauma"""
    tech_dist = {'cms': {}, 'frameworks': {}, 'analytics': {}}
    for r in results:
        if 'smart' in r and 'tech_cro' in r['smart']:
            tech = r['smart']['tech_cro']
            cms = tech.get('cms')
            if cms:
                tech_dist['cms'][cms] = tech_dist['cms'].get(cms, 0) + 1
            fw = tech.get('framework')
            if fw:
                tech_dist['frameworks'][fw] = tech_dist['frameworks'].get(fw, 0) + 1
            for pixel in tech.get('analytics_pixels', []):
                tech_dist['analytics'][pixel] = tech_dist['analytics'].get(pixel, 0) + 1
    return tech_dist

def _generate_improvement_tips(weaker, stronger):
    """Generoi parannusehdotuksia heikommalle"""
    tips = []
    for category in ['seo', 'content', 'cro', 'tech']:
        if weaker['smart']['scores'][category] < stronger['smart']['scores'][category]:
            if category == 'seo':
                tips.append(f"Paranna SEO:ta - kilpailijalla {stronger['smart']['scores'][category]} pistettä vs sinun {weaker['smart']['scores'][category]}")
            elif category == 'content':
                tips.append(f"Lisää sisältöä - kilpailijalla parempi sisältöpisteet")
            elif category == 'cro':
                tips.append(f"Paranna konversiota - lisää CTA-elementtejä")
            elif category == 'tech':
                tips.append(f"Päivitä analytiikka - kilpailijalla parempi seuranta")
    if stronger['smart']['tech_cro'].get('analytics_pixels') and not weaker['smart']['tech_cro'].get('analytics_pixels'):
        tips.append("Asenna analytiikkapikselit (GA4, Meta Pixel)")
    return tips[:5]

# ================== OSA 2/5 LOPPUU ================== #
# SEURAAVAKSI: Content Analysis & SWOT (OSA 3/5)# ================== OSA 3/5 ALKAA: CONTENT ANALYSIS & SWOT GENERATORS ================== #

def analyze_content(soup: BeautifulSoup, url: str):
    """
    Analysoi sivuston sisältöä syvällisemmin
    """
    content_analysis = {
        "headings": {},
        "images": {"total": 0, "with_alt": 0, "without_alt": 0},
        "links": {"internal": 0, "external": 0, "total": 0},
        "text_content": "",
        "services_hints": [],
        "trust_signals": [],
        "content_quality": {}
    }

    # Otsikot
    for i in range(1, 7):
        h_tags = soup.find_all(f'h{i}')
        if h_tags:
            content_analysis["headings"][f'h{i}'] = [tag.get_text(strip=True)[:100] for tag in h_tags[:5]]

    # Kuvat
    images = soup.find_all('img')
    content_analysis["images"]["total"] = len(images)
    content_analysis["images"]["with_alt"] = len([img for img in images if img.get('alt')])
    content_analysis["images"]["without_alt"] = len(images) - content_analysis["images"]["with_alt"]

    # Linkit
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href']
        if href.startswith('http://') or href.startswith('https://'):
            if url in href:
                content_analysis["links"]["internal"] += 1
            else:
                content_analysis["links"]["external"] += 1
        elif not href.startswith('#') and not href.startswith('mailto:'):
            content_analysis["links"]["internal"] += 1
    content_analysis["links"]["total"] = len(links)

    # Teksti
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile('content|main'))
    if main_content:
        text = main_content.get_text(separator=' ', strip=True)
    else:
        text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    content_analysis["text_content"] = text[:3000]

    # Palvelu-/tuotevihjeet
    service_keywords = [
        'palvelu', 'tuote', 'ratkaisu', 'tarjoa', 'toiminta', 'asiantuntija',
        'service', 'product', 'solution', 'offer', 'expert', 'consulting'
    ]
    text_lower = text.lower()
    for keyword in service_keywords:
        if keyword in text_lower:
            sentences = text.split('.')
            for sentence in sentences:
                if keyword in sentence.lower() and len(sentence) < 200:
                    content_analysis["services_hints"].append(sentence.strip())
                    if len(content_analysis["services_hints"]) >= 5:
                        break

    # Luottamussignaalit
    trust_patterns = [
        (r'\d{4,}-\d{4,}', 'Y-tunnus'),
        (r'(?:perustettu|founded|since) \d{4}', 'Perustamisvuosi'),
        (r'ISO[ -]?\d{4,}', 'ISO-sertifikaatti'),
        (r'palkinto|award|voittaja|winner', 'Palkinnot'),
        (r'asiakasta|clients|customers', 'Asiakasreferenssit'),
        (r'henkilö|työntekijä|employees|team', 'Tiimitieto'),
        ('yhteystiedot', 'Yhteystiedot'),
        ('testimo|referenssi|case', 'Asiakastarinat')
    ]
    for pattern, signal_type in trust_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            content_analysis["trust_signals"].append(signal_type)

    # Laatu
    content_analysis["content_quality"] = {
        "text_length": len(text),
        "unique_words": len(set(text.lower().split())),
        "avg_sentence_length": len(text.split()) / max(len(text.split('.')), 1),
        "has_contact_info": bool(re.search(r'@|puh|tel|phone', text_lower)),
        "has_address": bool(re.search(r'\d{5}|finland|suomi|helsinki|tampere|turku|oulu', text_lower))
    }
    return content_analysis

# ========== SWOT GENERATOR FUNCTIONS ========== #

def generate_strengths(data: dict) -> list:
    """Generate strengths based on analysis data"""
    strengths = []
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    tech = smart.get("tech_cro", {})
    
    if scores.get("seo", 0) >= 10:
        strengths.append(f"SEO-optimointi kohtuullisella tasolla ({scores['seo']}/30 pistettä)")
    if scores.get("content", 0) >= 8:
        strengths.append(f"Hyvä sisältömäärä sivustolla ({data.get('insights', {}).get('word_count', 0)} sanaa)")
    if len(tech.get("analytics_pixels", [])) > 0:
        strengths.append(f"Analytiikkatyökalut käytössä ({', '.join(tech['analytics_pixels'])})")
    if tech.get("cms") or tech.get("framework"):
        strengths.append(f"Moderni teknologia-alusta ({tech.get('cms') or tech.get('framework')})")
    if len(tech.get("contact_channels", [])) >= 2:
        strengths.append(f"Useita yhteystietokanavia ({', '.join(tech['contact_channels'])})")
    
    return strengths[:6] if strengths else ["Sivusto on toiminnassa", "Responsiivinen suunnittelu"]

def generate_weaknesses(data: dict) -> list:
    """Generate weaknesses based on analysis data"""
    weaknesses = []
    smart = data.get("smart", {})
    findings = smart.get("top_findings", [])
    
    for finding in findings:
        weaknesses.append(finding)
    
    if not weaknesses:
        scores = smart.get("scores", {})
        if scores.get("seo", 0) < 20:
            weaknesses.append("SEO-optimointi vaatii parannusta")
        if scores.get("content", 0) < 10:
            weaknesses.append("Sisältöä tulisi lisätä")
            
    return weaknesses[:6] if weaknesses else ["Kehityskohteita tunnistettu"]

def generate_opportunities(data: dict) -> list:
    """Generate opportunities based on analysis data"""
    opportunities = []
    smart = data.get("smart", {})
    actions = smart.get("actions", [])
    
    for action in actions[:4]:
        if isinstance(action, dict):
            opportunities.append(action.get("kuvaus", action.get("otsikko", "")))
    
    if not opportunities:
        opportunities = [
            "Sisällöntuotannon tehostaminen",
            "SEO-optimoinnin parantaminen",
            "Konversio-optimointi",
            "Analytiikan hyödyntäminen"
        ]
    
    return opportunities[:5]

def generate_threats(data: dict) -> list:
    """Generate threats based on analysis data"""
    threats = []
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    
    if scores.get("total", 0) < 50:
        threats.append("Kilpailijoiden parempi digitaalinen näkyvyys")
    if not smart.get("tech_cro", {}).get("analytics_pixels"):
        threats.append("Puutteellinen data-analytiikka hidastaa päätöksentekoa")
    if scores.get("cro", 0) < 10:
        threats.append("Heikko konversio-optimointi vähentää liidien määrää")
        
    return threats[:3] if threats else ["Markkinadynamiikan muutokset", "Teknologinen jälkeenjääneisyys"]

def generate_fallback_swot(data: dict, language: str) -> dict:
    """Generate fallback SWOT analysis when AI fails"""
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    
    if language == 'en':
        return {
            "summary": f"Website scored {scores.get('total', 0)}/100 in digital analysis.",
            "strengths": generate_strengths(data),
            "weaknesses": generate_weaknesses(data),
            "opportunities": generate_opportunities(data),
            "threats": generate_threats(data),
            "recommendations": [
                {"title": action.get("otsikko"), "description": action.get("kuvaus"), "priority": action.get("prioriteetti")}
                for action in smart.get("actions", [])[:5]
            ],
            "competitor_profile": {
                "target_audience": ["General audience"],
                "strengths": ["Digital presence"],
                "market_position": "Active in digital channels"
            }
        }
    else:
        return {
            "yhteenveto": f"Sivusto sai {scores.get('total', 0)}/100 pistettä digitaalisessa analyysissä.",
            "vahvuudet": generate_strengths(data),
            "heikkoudet": generate_weaknesses(data),
            "mahdollisuudet": generate_opportunities(data),
            "uhat": generate_threats(data),
            "toimenpidesuositukset": smart.get("actions", [])[:5],
            "kilpailijaprofiili": {
                "kohderyhmat": ["Yleisö"],
                "vahvuusalueet": ["Digitaalinen läsnäolo"],
                "markkina_asema": "Aktiivinen digitaalisissa kanavissa"
            }
        }

# ================== OSA 3/5 LOPPUU ================== #
# SEURAAVAKSI: Main Endpoints (OSA 4/5)# ================== OSA 4/5 ALKAA: MAIN ENDPOINTS ================== #

@app.get("/")
def home():
    return {
        "api":"Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status":"ok",
        "js_render_enabled": SMART_JS_RENDER
    }

@app.get("/health")
def health():
    def can_import(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "openai_configured": bool(openai_client),
        "smart_js_render_flag": SMART_JS_RENDER,
        "deps": {
            "requests_html": can_import("requests_html"),
            "lxml_html_clean": can_import("lxml_html_clean"),
            "pyppeteer": can_import("pyppeteer"),
        }
    }

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"

        # Välimuistin voisi ottaa käyttöön halutessa:
        # cached = get_cached_analysis(url)
        # if cached:
        #     return SmartAnalyzeResponse(**cached)

        # 1) Nopea haku
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
            response.raise_for_status()
            html_text = response.text

        soup = BeautifulSoup(html_text, 'html.parser')
        title_el = soup.find('title')
        meta_desc_el = soup.find('meta', {'name':'description'})
        h1_present = bool(soup.find('h1'))

        # 2) Heuristiikka → kokeile JS-renderiä lazyna
        if SMART_JS_RENDER and (not title_el or not meta_desc_el or not h1_present or soup.find('script', src=False)):
            js_html = maybe_scrape_with_javascript(url)
            if js_html:
                soup = BeautifulSoup(js_html, 'html.parser')

        title = (soup.find('title').text.strip() if soup.find('title') else "")
        description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
        word_count = len(soup.get_text(" ", strip=True))

        head_sig = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, str(soup))
        sitemap_info = await collect_robots_and_sitemap(url)
        content_data = analyze_content(soup, url)
        scores = score_and_recommend(head_sig, tech_cro, word_count)

        smart = {
            "meta": {"title": title or "Ei otsikkoa", "description": description or "Ei kuvausta", "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "content_analysis": content_data,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"],
            "flags": {"js_render_enabled": SMART_JS_RENDER, "cached": False}
        }

        result = SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title or "Ei otsikkoa",
            description=description or "Ei kuvausta",
            score=scores["scores"]["total"],
            insights={"word_count": word_count},
            smart=smart
        )

        # save_to_cache(url, result.dict())
        return result

    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest):
    """
    Enhanced AI analysis endpoint with better error handling and debugging
    """
    try:
        target_url = req.url or req.website
        if not target_url:
            raise HTTPException(status_code=400, detail="url or website required")

        # 1) Run smart analysis first
        logger.info(f"Starting analysis for {target_url}")
        smart_resp = await analyze_competitor(AnalyzeRequest(url=target_url))
        result = smart_resp.dict()

        # 2) Prepare AI enhancement
        ai_full: Dict[str, Any] = {}
        ai_reco: List[Dict[str, Any]] = []

        if openai_client and req.use_ai:
            try:
                content_info = result["smart"].get("content_analysis", {})
                
                # Create comprehensive summary for AI
                summary = {
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "description": result.get("description"),
                    "scores": result["smart"]["scores"],
                    "top_findings": result["smart"]["top_findings"],
                    "actions": result["smart"]["actions"],
                    "tech_cro": result["smart"]["tech_cro"],
                    "head_signals": result["smart"]["head_signals"],
                    "sitemap": result["smart"]["sitemap"],
                    "content_summary": {
                        "headings": content_info.get("headings", {}),
                        "images": content_info.get("images", {}),
                        "links": content_info.get("links", {}),
                        "services_hints": content_info.get("services_hints", []),
                        "trust_signals": content_info.get("trust_signals", []),
                        "content_quality": content_info.get("content_quality", {}),
                        "text_preview": content_info.get("text_content", "")[:1000]
                    }
                }

                language = (req.language or 'fi').lower()
                
                # Enhanced prompts with explicit instructions
                if language == 'en':
                    system_msg = """You are a digital marketing and competitor analysis expert. 
                    You MUST provide concrete, specific insights based on the data provided.
                    Always return valid JSON with all required fields populated."""
                    
                    prompt = f"""Analyze this competitor website data and create a comprehensive JSON analysis.

WEBSITE DATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

You MUST create a JSON object with ALL of the following fields (no empty arrays):

{{
  "summary": "4-6 sentence description of the website's current state, digital presence, and main offerings based on the data",
  "strengths": [
    "At least 4-6 specific strengths based on the scores and technical data",
    "Example: Good SEO score of X/30",
    "Example: Has analytics tracking with Y pixels",
    "Example: Z contact channels available"
  ],
  "weaknesses": [
    "At least 4-6 specific weaknesses based on the findings",
    "Example: Missing canonical tags",
    "Example: Low content score",
    "Example: Few CTA elements"
  ],
  "opportunities": [
    "At least 4-5 improvement opportunities",
    "Example: Add more content to improve content score",
    "Example: Implement missing meta tags"
  ],
  "threats": [
    "At least 2-3 potential risks",
    "Example: Poor mobile optimization",
    "Example: Missing analytics tracking"
  ],
  "recommendations": [
    {{
      "title": "Specific action title",
      "description": "Detailed description",
      "priority": "high/medium/low",
      "timeline": "immediate/1-3 months/3-6 months"
    }}
  ],
  "competitor_profile": {{
    "target_audience": ["audience segment 1", "audience segment 2"],
    "strengths": ["key strength 1", "key strength 2"],
    "market_position": "Description of their market position"
  }}
}}

Base ALL insights on the actual data provided. Return ONLY valid JSON."""

                else:  # Finnish
                    system_msg = """Olet digitaalisen markkinoinnin ja kilpailija-analyysin asiantuntija.
                    SINUN TÄYTYY antaa konkreettisia, spesifisiä oivalluksia datan perusteella.
                    Palauta aina validi JSON kaikilla vaadituilla kentillä täytettyinä."""
                    
                    prompt = f"""Analysoi tämä kilpailijasivuston data ja luo kattava JSON-analyysi.

SIVUSTODATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

SINUN TÄYTYY luoda JSON-objekti, jossa on KAIKKI seuraavat kentät (ei tyhjiä taulukoita):

{{
  "yhteenveto": "4-6 lausetta sivuston nykytilasta, digitaalisesta läsnäolosta ja pääpalveluista datan perusteella",
  "vahvuudet": [
    "Vähintään 4-6 konkreettista vahvuutta pisteiden ja teknisen datan perusteella",
    "Esim: Hyvä SEO-pistemäärä X/30",
    "Esim: Analytiikka käytössä Y pikselillä",
    "Esim: Z yhteystietokanavaa"
  ],
  "heikkoudet": [
    "Vähintään 4-6 konkreettista heikkoutta löydösten perusteella",
    "Esim: Canonical-tagit puuttuvat",
    "Esim: Matala sisältöpistemäärä",
    "Esim: Vähän CTA-elementtejä"
  ],
  "mahdollisuudet": [
    "Vähintään 4-5 kehitysmahdollisuutta",
    "Esim: Lisää sisältöä parantaaksesi sisältöpisteitä",
    "Esim: Toteuta puuttuvat meta-tagit"
  ],
  "uhat": [
    "Vähintään 2-3 potentiaalista riskiä",
    "Esim: Heikko mobiilioptimointi",
    "Esim: Puuttuva analytiikkaseuranta"
  ],
  "toimenpidesuositukset": [
    {{
      "otsikko": "Konkreettinen toimenpiteen otsikko",
      "kuvaus": "Yksityiskohtainen kuvaus",
      "prioriteetti": "korkea/keskitaso/matala",
      "aikataulu": "heti/1-3kk/3-6kk"
    }}
  ],
  "kilpailijaprofiili": {{
    "kohderyhmat": ["kohderyhmä 1", "kohderyhmä 2"],
    "vahvuusalueet": ["keskeinen vahvuus 1", "keskeinen vahvuus 2"],
    "markkina_asema": "Kuvaus markkina-asemasta"
  }}
}}

Perusta KAIKKI oivallukset todelliseen dataan. Palauta VAIN validi JSON."""

                logger.info(f"Calling OpenAI API with model gpt-4o-mini")
                
                # Make the API call with explicit JSON mode
                resp = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    max_tokens=2000,
                )
                
                # Parse the response
                ai_response = resp.choices[0].message.content
                logger.info(f"OpenAI response received, length: {len(ai_response or '')}")
                
                if ai_response:
                    try:
                        parsed = json.loads(ai_response)
                        ai_full = parsed if isinstance(parsed, dict) else {}
                        
                        # Log what we got
                        logger.info(f"Parsed AI response keys: {list(ai_full.keys())}")
                        
                        # Extract recommendations
                        ai_reco = (
                            ai_full.get("toimenpidesuositukset")
                            or ai_full.get("recommendations")
                            or []
                        )
                        
                        # Validate that we got actual content
                        if language == 'fi':
                            if not ai_full.get("vahvuudet") or len(ai_full.get("vahvuudet", [])) == 0:
                                logger.warning("AI returned empty vahvuudet, using fallback")
                                ai_full = generate_fallback_swot(result, language)
                        else:
                            if not ai_full.get("strengths") or len(ai_full.get("strengths", [])) == 0:
                                logger.warning("AI returned empty strengths, using fallback")
                                ai_full = generate_fallback_swot(result, language)
                                
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse AI response: {e}")
                        ai_full = generate_fallback_swot(result, language)
                else:
                    logger.warning("Empty AI response, using fallback")
                    ai_full = generate_fallback_swot(result, language)
                    
            except Exception as e:
                logger.error(f"AI enhancement failed: {str(e)}")
                logger.exception(e)  # This will log the full traceback
                ai_full = generate_fallback_swot(result, req.language or 'fi')
                ai_reco = []
        else:
            logger.info("AI analysis disabled or OpenAI client not configured, using fallback")
            ai_full = generate_fallback_swot(result, req.language or 'fi')

        # 3) Build response with fallbacks for empty fields
        
        # Extract competitor profile
        kilpailijaprofiili = ai_full.get("kilpailijaprofiili") or ai_full.get("competitor_profile") or {}
        if isinstance(kilpailijaprofiili, dict):
            erottautumiskeinot = kilpailijaprofiili.get("vahvuusalueet", kilpailijaprofiili.get("strengths", []))
        else:
            erottautumiskeinot = []

        # Build quick wins list
        quick_wins_list = []
        if ai_reco or result["smart"]["actions"]:
            for a in (ai_reco or result["smart"]["actions"])[:3]:
                if isinstance(a, dict):
                    win = a.get("otsikko", a.get("title", ""))
                else:
                    win = str(a)
                if win:
                    quick_wins_list.append(win)

        # Ensure we have non-empty arrays
        response_data = {
            "success": True,
            "company_name": req.company_name,
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": {
                "company": req.company_name,
                "website": req.website or req.url,
                "industry": req.industry,
                "strengths_count": len(req.strengths or []),
                "weaknesses_count": len(req.weaknesses or []),
                "has_market_position": bool(req.market_position),
            },
            "ai_analysis": {
                "yhteenveto": ai_full.get(
                    "yhteenveto",
                    ai_full.get(
                        "summary",
                        f"Sivusto {req.company_name} sai {result['smart']['scores']['total']}/100 pistettä digitaalisessa analyysissä. "
                        f"Sivustolla on {len(result['smart']['tech_cro'].get('analytics_pixels', []))} analytiikkatyökalua käytössä ja "
                        f"{result['smart']['tech_cro'].get('cta_count', 0)} CTA-elementtiä. "
                        f"Sisältöä on {result.get('insights', {}).get('word_count', 0)} sanaa."
                    )
                ),
                "vahvuudet": ai_full.get("vahvuudet", ai_full.get("strengths", [])) or generate_strengths(result),
                "heikkoudet": ai_full.get("heikkoudet", ai_full.get("weaknesses", [])) or generate_weaknesses(result),
                "mahdollisuudet": ai_full.get("mahdollisuudet", ai_full.get("opportunities", [])) or generate_opportunities(result),
                "uhat": ai_full.get("uhat", ai_full.get("threats", [])) or generate_threats(result),
                "toimenpidesuositukset": ai_reco or result["smart"]["actions"],
                "digitaalinen_jalanjalki": {
                    "arvio": result["smart"]["scores"]["total"] // 10,
                    "sosiaalinen_media": result["smart"]["tech_cro"]["analytics_pixels"],
                    "sisaltostrategia": "Aktiivinen" if len(result["smart"].get("content_analysis", {}).get("services_hints", [])) > 2 else "Kehitettävä"
                },
                "erottautumiskeinot": erottautumiskeinot or ["Tekninen toteutus", "Sisältöstrategia", "Käyttäjäkokemus"],
                "quick_wins": quick_wins_list or ["Lisää meta-tagit", "Paranna CTA-elementtejä", "Asenna analytiikka"]
            },
            "smart": result["smart"]
        }

        logger.info(f"Response prepared successfully for {req.company_name}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI analyze failed completely: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI analyze failed: {str(e)}")

@app.get("/api/v1/test-openai")
async def test_openai():
    """Test OpenAI API connection"""
    if not openai_client:
        return {
            "status": "error",
            "message": "OpenAI client not configured",
            "api_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "client_exists": False
        }

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a test bot."},
                {"role": "user", "content": "Reply with just 'OK' if you work."}
            ],
            max_tokens=10
        )
        return {
            "status": "success",
            "message": "OpenAI API works!",
            "response": response.choices[0].message.content,
            "model": "gpt-4o-mini"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"OpenAI API error: {str(e)}",
            "error_type": type(e).__name__
        }

@app.post("/api/v1/batch-analyze")
async def batch_analyze_competitors(urls: List[str]):
    """Analysoi useita kilpailijoita kerralla"""
    results = []
    for url in urls[:10]:  # Max 10 kerralla
        try:
            result = await analyze_competitor(AnalyzeRequest(url=url))
            results.append(result.dict())
        except Exception as e:
            results.append({"success": False, "url": url, "error": str(e)})

    successful = [r for r in results if r.get('success')]
    avg_score = sum(r.get('score', 0) for r in successful) / len(successful) if successful else 0

    return {
        "success": True,
        "analyzed_count": len(results),
        "successful_count": len(successful),
        "average_score": round(avg_score, 1),
        "results": results,
        "summary": {
            "best_performer": max(successful, key=lambda x: x.get('score', 0)) if successful else None,
            "common_weaknesses": _find_common_patterns([r['smart']['top_findings'] for r in successful if 'smart' in r]),
            "tech_stack_distribution": _analyze_tech_distribution(successful)
        }
    }

@app.get("/api/v1/compare/{url1}/{url2}")
async def compare_competitors(url1: str, url2: str):
    """Vertaa kahta kilpailijaa keskenään"""
    try:
        result1 = await analyze_competitor(AnalyzeRequest(url=url1))
        result2 = await analyze_competitor(AnalyzeRequest(url=url2))
        r1 = result1.dict()
        r2 = result2.dict()

        comparison = {
            "competitor1": {"url": url1, "score": r1['score'], "title": r1['title']},
            "competitor2": {"url": url2, "score": r2['score'], "title": r2['title']},
            "winner": url1 if r1['score'] > r2['score'] else url2,
            "score_difference": abs(r1['score'] - r2['score']),
            "detailed_comparison": {
                "seo": {"competitor1": r1['smart']['scores']['seo'], "competitor2": r2['smart']['scores']['seo'],
                        "winner": 1 if r1['smart']['scores']['seo'] > r2['smart']['scores']['seo'] else 2},
                "content": {"competitor1": r1['smart']['scores']['content'], "competitor2": r2['smart']['scores']['content'],
                            "winner": 1 if r1['smart']['scores']['content'] > r2['smart']['scores']['content'] else 2},
                "cro": {"competitor1": r1['smart']['scores']['cro'], "competitor2": r2['smart']['scores']['cro'],
                        "winner": 1 if r1['smart']['scores']['cro'] > r2['smart']['scores']['cro'] else 2},
                "tech": {"competitor1": r1['smart']['scores']['tech'], "competitor2": r2['smart']['scores']['tech'],
                         "winner": 1 if r1['smart']['scores']['tech'] > r2['smart']['scores']['tech'] else 2}
            },
            "tech_comparison": {
                "competitor1": {"cms": r1['smart']['tech_cro'].get('cms'),
                                "framework": r1['smart']['tech_cro'].get('framework'),
                                "analytics": r1['smart']['tech_cro'].get('analytics_pixels', [])},
                "competitor2": {"cms": r2['smart']['tech_cro'].get('cms'),
                                "framework": r2['smart']['tech_cro'].get('framework'),
                                "analytics": r2['smart']['tech_cro'].get('analytics_pixels', [])}
            },
            "recommendations": {
                "for_weaker": _generate_improvement_tips(
                    r1 if r1['score'] < r2['score'] else r2,
                    r2 if r1['score'] < r2['score'] else r1
                )
            }
        }
        return comparison

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vertailu epäonnistui: {str(e)}")

@app.get("/api/v1/docs")
def api_documentation():
    """API-dokumentaatio"""
    return {
        "version": APP_VERSION,
        "endpoints": {
            "/api/v1/analyze": {"method": "POST", "description": "Analysoi yksittäinen kilpailijan sivusto"},
            "/api/v1/ai-analyze": {"method": "POST", "description": "Analysoi AI-rikastuksella"},
            "/api/v1/batch-analyze": {"method": "POST", "description": "Analysoi max 10 URL:ia kerralla"},
            "/api/v1/compare/{url1}/{url2}": {"method": "GET", "description": "Vertaa kahta kilpailijaa"},
            "/api/v1/generate-pdf": {"method": "POST", "description": "Luo PDF-raportti"},
            "/api/v1/generate-pdf-base64": {"method": "POST", "description": "Luo PDF base64-muodossa"},
            "/api/v1/test-openai": {"method": "GET", "description": "Testaa OpenAI-yhteys"},
            "/health": {"method": "GET", "description": "Tarkista API:n tila"}
        }
    }

# ================== OSA 4/5 LOPPUU ================== #
# SEURAAVAKSI: Rate Limiting, PDF Generation & Error Handling (OSA 5/5)# ================== OSA 5/5 ALKAA: RATE LIMITING, PDF GENERATION & ERROR HANDLING ================== #

# ---------- Rate limiting ----------
request_counts: Dict[str, List[datetime]] = defaultdict(list)

def check_rate_limit(ip: str, limit: int = 100) -> bool:
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    request_counts[ip] = [t for t in request_counts[ip] if t > hour_ago]
    if len(request_counts[ip]) >= limit:
        return False
    request_counts[ip].append(now)
    return True

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    ip = request.headers.get("X-Forwarded-For", request.client.host) if request.client else "unknown"
    if request.url.path.startswith("/api/v1/"):
        limits = {
            "/api/v1/batch-analyze": 10,
            "/api/v1/ai-analyze": 50,
            "/api/v1/analyze": 100
        }
        limit = next((v for k, v in limits.items() if request.url.path.startswith(k)), 100)
        if not check_rate_limit(ip, limit):
            return JSONResponse(status_code=429, content={"detail": f"Rate limit exceeded. Max {limit} requests/hour"})
    return await call_next(request)

# ---------- Global error handler ----------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    error_id = hashlib.md5(f"{datetime.now()}{str(exc)}".encode()).hexdigest()[:8]
    print(f"ERROR {error_id}: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Sisäinen virhe",
            "error_id": error_id,
            "message": "Jotain meni pieleen. Ota yhteyttä tukeen virhekoodilla."
        }
    )

# ========== PDF GENERATION (stream) ==========
@app.post("/api/v1/generate-pdf")
async def generate_pdf_report(analysis_data: Dict[str, Any]):
    """Generoi PDF-raportti AI-analyysista (stream)"""
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24,
                                     textColor=colors.HexColor('#1a1a1a'), spaceAfter=30,
                                     alignment=TA_CENTER, fontName='Helvetica-Bold')
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16,
                                       textColor=colors.HexColor('#2563eb'), spaceAfter=12,
                                       spaceBefore=20, fontName='Helvetica-Bold')
        subheading_style = ParagraphStyle('CustomSubHeading', parent=styles['Heading3'], fontSize=13,
                                          textColor=colors.HexColor('#475569'), spaceAfter=8,
                                          spaceBefore=12, fontName='Helvetica-Bold')
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11,
                                      textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=8)

        story = []
        company_name = analysis_data.get('company_name', 'Kilpailija')
        story.append(Paragraph(f"Kilpailija-analyysi: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))

        story.append(Paragraph("Perustiedot", heading_style))
        basic_info = analysis_data.get('basic_analysis', {})
        basic_data = [
            ['Yritys:', company_name],
            ['Verkkosivusto:', basic_info.get('website', 'Ei tiedossa')],
            ['Toimiala:', basic_info.get('industry', 'Ei määritelty')],
            ['Analyysipäivä:', analysis_data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))]
        ]
        basic_table = Table(basic_data, colWidths=[5*cm, 12*cm])
        basic_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#334155')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 20))

        ai_analysis = analysis_data.get('ai_analysis', {})
        if ai_analysis:
            if ai_analysis.get('yhteenveto'):
                story.append(Paragraph("Yhteenveto", heading_style))
                story.append(Paragraph(ai_analysis['yhteenveto'], normal_style))
                story.append(Spacer(1, 20))

            story.append(Paragraph("SWOT-analyysi", heading_style))
            if ai_analysis.get('vahvuudet'):
                story.append(Paragraph("Vahvuudet", subheading_style))
                for v in ai_analysis['vahvuudet']:
                    story.append(Paragraph(f"• {v}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('heikkoudet'):
                story.append(Paragraph("Heikkoudet", subheading_style))
                for w in ai_analysis['heikkoudet']:
                    story.append(Paragraph(f"• {w}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('mahdollisuudet'):
                story.append(Paragraph("Mahdollisuudet", subheading_style))
                for o in ai_analysis['mahdollisuudet']:
                    story.append(Paragraph(f"• {o}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('uhat'):
                story.append(Paragraph("Uhat", subheading_style))
                for t in ai_analysis['uhat']:
                    story.append(Paragraph(f"• {t}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('digitaalinen_jalanjalki'):
                story.append(Paragraph("Digitaalinen jalanjälki", heading_style))
                digi = ai_analysis['digitaalinen_jalanjalki']
                if digi.get('arvio'):
                    story.append(Paragraph(f"<b>Arvio:</b> {digi['arvio']}/10", normal_style))
                if digi.get('sosiaalinen_media'):
                    story.append(Paragraph("<b>Aktiiviset kanavat:</b>", normal_style))
                    for ch in digi['sosiaalinen_media']:
                        story.append(Paragraph(f"• {ch}", normal_style))
                if digi.get('sisaltostrategia'):
                    story.append(Paragraph(f"<b>Sisältöstrategia:</b> {digi['sisaltostrategia']}", normal_style))
                story.append(Spacer(1, 20))

            # Toimenpiteet
            if ai_analysis.get('toimenpidesuositukset'):
                story.append(PageBreak())
                story.append(Paragraph("Toimenpidesuositukset", heading_style))
                for idx, rec in enumerate(ai_analysis['toimenpidesuositukset'], 1):
                    title = rec.get('otsikko', f'Toimenpide {idx}') if isinstance(rec, dict) else f'Toimenpide {idx}'
                    story.append(Paragraph(f"{idx}. {title}", subheading_style))
                    if isinstance(rec, dict):
                        if rec.get('kuvaus'):
                            story.append(Paragraph(rec['kuvaus'], normal_style))
                        details = []
                        if rec.get('prioriteetti'):
                            p = rec['prioriteetti']
                            color = '#dc2626' if p == 'korkea' else '#f59e0b' if p == 'keskitaso' else '#10b981'
                            details.append(f"<font color='{color}'><b>Prioriteetti:</b> {p}</font>")
                        if rec.get('aikataulu'):
                            details.append(f"<b>Aikataulu:</b> {rec['aikataulu']}")
                        if details:
                            story.append(Paragraph(" | ".join(details), normal_style))
                    story.append(Spacer(1, 15))

            # Erottautumiskeinot
            methods = ai_analysis.get('erottautumiskeinot', [])
            if methods:
                story.append(Paragraph("Erottautumiskeinot", heading_style))
                if isinstance(methods, str):
                    items = [m.strip() for m in methods.split(',')] if ',' in methods else [methods]
                else:
                    items = methods
                for m in items:
                    story.append(Paragraph(f"• {m}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('quick_wins'):
                story.append(Paragraph("Nopeat voitot", heading_style))
                for win in ai_analysis.get('quick_wins', []):
                    story.append(Paragraph(f"✓ {win}", normal_style))

        doc.build(story)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=kilpailija_analyysi_{(company_name or 'raportti').replace(' ','_')}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-generointi epäonnistui: {str(e)}")

# ========== PDF GENERATION (base64) ==========
@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti base64-muodossa (fi/en).
    """
    try:
        language = analysis_data.get('language', 'fi')
        translations = {
            'fi': {'title':'Kilpailija-analyysi','basic_info':'Perustiedot','company':'Yritys','website':'Verkkosivusto','industry':'Toimiala','analysis_date':'Analyysipäivä','not_known':'Ei tiedossa','not_defined':'Ei määritelty','summary':'Yhteenveto','swot_analysis':'SWOT-analyysi','strengths':'Vahvuudet','weaknesses':'Heikkoudet','opportunities':'Mahdollisuudet','threats':'Uhat','digital_footprint':'Digitaalinen jalanjälki','score':'Arvio','active_channels':'Aktiiviset kanavat','content_strategy':'Sisältöstrategia','recommendations':'Toimenpidesuositukset','action':'Toimenpide','priority':'Prioriteetti','timeline':'Aikataulu','differentiation':'Erottautumiskeinot','quick_wins':'Nopeat voitot','high':'korkea','medium':'keskitaso','low':'matala'},
            'en': {'title':'Competitor Analysis','basic_info':'Basic Information','company':'Company','website':'Website','industry':'Industry','analysis_date':'Analysis Date','not_known':'Not known','not_defined':'Not defined','summary':'Summary','swot_analysis':'SWOT Analysis','strengths':'Strengths','weaknesses':'Weaknesses','opportunities':'Opportunities','threats':'Threats','digital_footprint':'Digital Footprint','score':'Score','active_channels':'Active Channels','content_strategy':'Content Strategy','recommendations':'Recommendations','action':'Action','priority':'Priority','timeline':'Timeline','differentiation':'Differentiation','quick_wins':'Quick Wins','high':'high','medium':'medium','low':'low'}
        }
        t = translations.get(language, translations['fi'])

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#1a1a1a'), spaceAfter=30, alignment=TA_CENTER, fontName='Helvetica-Bold')
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor('#2563eb'), spaceAfter=12, spaceBefore=20, fontName='Helvetica-Bold')
        subheading_style = ParagraphStyle('CustomSubHeading', parent=styles['Heading3'], fontSize=13, textColor=colors.HexColor('#475569'), spaceAfter=8, spaceBefore=12, fontName='Helvetica-Bold')
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=8)

        story = []
        company_name = analysis_data.get('company_name', 'Unknown')
        story.append(Paragraph(f"{t['title']}: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))

        story.append(Paragraph(t['basic_info'], heading_style))
        basic_info = analysis_data.get('basic_analysis', {})
        basic_data = [
            [f"{t['company']}:", company_name],
            [f"{t['website']}:", analysis_data.get('url', basic_info.get('website', t['not_known']))],
            [f"{t['industry']}:", basic_info.get('industry', t['not_defined'])],
            [f"{t['analysis_date']}:", analysis_data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))]
        ]
        basic_table = Table(basic_data, colWidths=[5*cm, 12*cm])
        basic_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#334155')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 20))

        ai_analysis = analysis_data.get('ai_analysis', {})
        if ai_analysis:
            if ai_analysis.get('yhteenveto') or ai_analysis.get('summary'):
                story.append(Paragraph(t['summary'], heading_style))
                story.append(Paragraph(ai_analysis.get('yhteenveto', ai_analysis.get('summary','')), normal_style))
                story.append(Spacer(1, 20))

            story.append(Paragraph(t['swot_analysis'], heading_style))
            for key, label in [('vahvuudet', t['strengths']), ('heikkoudet', t['weaknesses']), ('mahdollisuudet', t['opportunities']), ('uhat', t['threats'])]:
                items = ai_analysis.get(key, ai_analysis.get({'vahvuudet':'strengths','heikkoudet':'weaknesses','mahdollisuudet':'opportunities','uhat':'threats'}[key], []))
                if items:
                    story.append(Paragraph(label, subheading_style))
                    for it in items:
                        story.append(Paragraph(f"• {it}", normal_style))
                    story.append(Spacer(1, 10))

            digi = ai_analysis.get('digitaalinen_jalanjalki', ai_analysis.get('digital_footprint', {}))
            if digi:
                story.append(Paragraph(t['digital_footprint'], heading_style))
                if digi.get('arvio') or digi.get('score'):
                    score = digi.get('arvio', digi.get('score', 0))
                    story.append(Paragraph(f"<b>{t['score']}:</b> {score}/10", normal_style))
                if digi.get('sosiaalinen_media') or digi.get('social_media'):
                    story.append(Paragraph(f"<b>{t['active_channels']}:</b>", normal_style))
                    for ch in digi.get('sosiaalinen_media', digi.get('social_media', [])):
                        story.append(Paragraph(f"• {ch}", normal_style))
                if digi.get('sisaltostrategia') or digi.get('content_strategy'):
                    story.append(Paragraph(f"<b>{t['content_strategy']}:</b> {digi.get('sisaltostrategia', digi.get('content_strategy',''))}", normal_style))
                story.append(Spacer(1, 20))

            recs = ai_analysis.get('toimenpidesuositukset', ai_analysis.get('recommendations', []))
            if recs:
                story.append(PageBreak())
                story.append(Paragraph(t['recommendations'], heading_style))
                for idx, rec in enumerate(recs, 1):
                    if isinstance(rec, dict):
                        title = rec.get('otsikko', rec.get('title', f"{t['action']} {idx}"))
                        story.append(Paragraph(f"{idx}. {title}", subheading_style))
                        if rec.get('kuvaus') or rec.get('description'):
                            story.append(Paragraph(rec.get('kuvaus', rec.get('description','')), normal_style))
                        details = []
                        p = rec.get('prioriteetti', rec.get('priority'))
                        if p:
                            color = '#dc2626' if p in ['korkea','high'] else '#f59e0b' if p in ['keskitaso','medium'] else '#10b981'
                            ptext = {'high':t['high'], 'medium':t['medium'], 'low':t['low']}.get(p, p)
                            details.append(f"<font color='{color}'><b>{t['priority']}:</b> {ptext}</font>")
                        tl = rec.get('aikataulu', rec.get('timeline'))
                        if tl:
                            details.append(f"<b>{t['timeline']}:</b> {tl}")
                        if details:
                            story.append(Paragraph(" | ".join(details), normal_style))
                    else:
                        story.append(Paragraph(f"{idx}. {rec}", normal_style))
                    story.append(Spacer(1, 15))

        methods = ai_analysis.get('erottautumiskeinot', ai_analysis.get('differentiation', []))
        if methods:
            story.append(Paragraph(t['differentiation'], heading_style))
            for m in (methods if isinstance(methods, list) else [methods]):
                story.append(Paragraph(f"• {m}", normal_style))
            story.append(Spacer(1, 20))

        if ai_analysis.get('quick_wins'):
            story.append(Paragraph(t['quick_wins'], heading_style))
            for win in ai_analysis.get('quick_wins', []):
                story.append(Paragraph(f"✓ {win}", normal_style))

        doc.build(story)
        buffer.seek(0)
        pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        lang_suffix = 'en' if language == 'en' else 'fi'
        safe_company_name = company_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filename = f"competitor_analysis_{safe_company_name}_{timestamp}_{lang_suffix}.pdf"
        return {"success": True, "pdf_base64": pdf_base64, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# ================== OSA 5/5 LOPPUU - KOKO main.py VALMIS! ================== #
# TÄÄ ON TIEDOSTON LOPPU - EI MITÄÄN TÄMÄN JÄLKEEN!
