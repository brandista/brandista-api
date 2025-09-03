#!/usr/bin/env python3
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
