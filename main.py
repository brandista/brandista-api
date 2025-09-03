#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API - Complete AI Enhanced Version
Version: 5.0.0
Complete backend with all AI features integrated
"""

# ================== IMPORTS & SETUP ================== #

from fastapi import FastAPI, HTTPException, Response, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union, Literal
import httpx
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, parse_qs
import asyncio
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from io import BytesIO
import base64
from collections import defaultdict, Counter
import time
import hashlib
import os
import logging
from functools import lru_cache
import statistics
import numpy as np
from textblob import TextBlob
import openai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# ================== CONFIGURATION ================== #

APP_VERSION = "5.0.0"
CACHE_TTL = 3600  # 1 hour
MAX_CACHE_SIZE = 100
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW = 60  # seconds
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "true").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Brandista Competitive Intelligence API",
    description="Advanced competitive analysis with AI capabilities",
    version=APP_VERSION
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== MODELS ================== #

class AnalyzeRequest(BaseModel):
    url: str
    render_js: bool = False
    timeout: int = 30
    extract_social: bool = True
    extract_tech: bool = True

class PDFRequest(BaseModel):
    urls: List[str]
    company_name: str = "Target Company"
    include_tech: bool = True
    include_social: bool = True
    include_seo: bool = True
    language: str = "en"

class AIAnalyzeRequest(BaseModel):
    url: str
    company_name: str
    use_ai: bool = True
    render_js: bool = False
    extract_social: bool = True
    extract_tech: bool = True
    include_swot: bool = True
    include_recommendations: bool = True
    language: str = "en"

class DeepAnalysisRequest(BaseModel):
    url: str
    company_name: str
    competitors: List[str] = []
    include_market_research: bool = True
    include_tech_stack: bool = True
    include_content_analysis: bool = True
    include_ai_insights: bool = True
    language: str = "en"

class BatchAnalyzeRequest(BaseModel):
    urls: List[str]
    use_ai: bool = True
    include_comparisons: bool = True
    language: str = "en"

# ================== CACHE & RATE LIMITING ================== #

cache = {}
request_counts = defaultdict(lambda: {"count": 0, "window_start": time.time()})

def get_cache_key(url: str, **kwargs) -> str:
    """Generate cache key from URL and parameters."""
    params_str = json.dumps(kwargs, sort_keys=True)
    return hashlib.md5(f"{url}{params_str}".encode()).hexdigest()

def get_from_cache(key: str) -> Optional[Dict]:
    """Get data from cache if valid."""
    if key in cache:
        entry = cache[key]
        if time.time() - entry["timestamp"] < CACHE_TTL:
            return entry["data"]
        else:
            del cache[key]
    return None

def set_cache(key: str, data: Dict):
    """Set data in cache with timestamp."""
    if len(cache) >= MAX_CACHE_SIZE:
        oldest_key = min(cache.keys(), key=lambda k: cache[k]["timestamp"])
        del cache[oldest_key]
    cache[key] = {"data": data, "timestamp": time.time()}

def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit."""
    current_time = time.time()
    client_data = request_counts[client_ip]
    
    if current_time - client_data["window_start"] > RATE_LIMIT_WINDOW:
        client_data["count"] = 0
        client_data["window_start"] = current_time
    
    if client_data["count"] >= RATE_LIMIT_REQUESTS:
        return False
    
    client_data["count"] += 1
    return True

# ================== ENHANCED AI ANALYZER CLASS ================== #

class EnhancedAIAnalyzer:
    """Enhanced AI analyzer with multiple analysis capabilities."""
    
    def __init__(self):
        self.openai_client = openai.Client(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text content."""
        try:
            blob = TextBlob(text[:5000])  # Limit text length
            
            return {
                "polarity": float(blob.sentiment.polarity),
                "subjectivity": float(blob.sentiment.subjectivity),
                "sentiment_label": self._get_sentiment_label(blob.sentiment.polarity),
                "confidence": abs(blob.sentiment.polarity)
            }
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {
                "polarity": 0,
                "subjectivity": 0,
                "sentiment_label": "neutral",
                "confidence": 0
            }
    
    def _get_sentiment_label(self, polarity: float) -> str:
        """Convert polarity score to label."""
        if polarity > 0.3:
            return "positive"
        elif polarity < -0.3:
            return "negative"
        else:
            return "neutral"
    
    def detect_industry(self, content: Dict) -> Dict[str, Any]:
        """Detect industry based on content analysis."""
        industry_keywords = {
            "technology": ["software", "app", "platform", "digital", "cloud", "AI", "data"],
            "healthcare": ["health", "medical", "patient", "clinic", "doctor", "therapy"],
            "finance": ["banking", "investment", "financial", "payment", "insurance"],
            "retail": ["shop", "store", "product", "buy", "sale", "customer"],
            "education": ["learn", "course", "student", "education", "training", "academy"],
            "manufacturing": ["production", "factory", "industrial", "equipment", "supply"],
            "hospitality": ["hotel", "restaurant", "travel", "tourism", "booking"],
            "real_estate": ["property", "real estate", "apartment", "house", "rent"],
            "automotive": ["car", "vehicle", "automotive", "driving", "motor"],
            "media": ["news", "content", "media", "publishing", "entertainment"]
        }
        
        text = f"{content.get('title', '')} {content.get('description', '')} {' '.join(content.get('headings', []))}".lower()
        
        industry_scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                industry_scores[industry] = score
        
        if industry_scores:
            primary_industry = max(industry_scores, key=industry_scores.get)
            confidence = industry_scores[primary_industry] / sum(industry_scores.values())
        else:
            primary_industry = "general"
            confidence = 0.0
        
        return {
            "primary_industry": primary_industry,
            "confidence": confidence,
            "all_scores": industry_scores,
            "detected_at": datetime.now().isoformat()
        }
    
    def analyze_content_quality(self, content: Dict) -> Dict[str, Any]:
        """Analyze content quality and engagement potential."""
        quality_score = 0
        factors = []
        
        # Check title
        if content.get('title'):
            quality_score += 10
            if len(content['title']) > 30 and len(content['title']) < 70:
                quality_score += 5
                factors.append("optimal_title_length")
        
        # Check description
        if content.get('description'):
            quality_score += 10
            if len(content['description']) > 120 and len(content['description']) < 160:
                quality_score += 5
                factors.append("optimal_description_length")
        
        # Check images
        images = content.get('images', [])
        if images:
            quality_score += 15
            factors.append("has_images")
            if len(images) > 5:
                quality_score += 5
                factors.append("rich_media")
        
        # Check headings structure
        headings = content.get('headings', [])
        if headings:
            quality_score += 10
            factors.append("structured_content")
            if len(headings) > 5:
                quality_score += 10
                factors.append("comprehensive_structure")
        
        # Check social signals
        social = content.get('social_signals', {})
        if any(social.values()):
            quality_score += 10
            factors.append("social_presence")
        
        # Check tech stack
        tech = content.get('technologies', [])
        if len(tech) > 3:
            quality_score += 10
            factors.append("modern_tech_stack")
        
        # Check SSL
        if content.get('url', '').startswith('https'):
            quality_score += 5
            factors.append("secure_connection")
        
        # Check mobile optimization
        viewport = content.get('viewport')
        if viewport:
            quality_score += 10
            factors.append("mobile_optimized")
        
        return {
            "quality_score": min(quality_score, 100),
            "factors": factors,
            "grade": self._get_quality_grade(quality_score),
            "recommendations": self._get_quality_recommendations(factors, quality_score)
        }
    
    def _get_quality_grade(self, score: int) -> str:
        """Convert quality score to grade."""
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
        else:
            return "F"
    
    def _get_quality_recommendations(self, factors: List[str], score: int) -> List[str]:
        """Generate quality improvement recommendations."""
        recommendations = []
        
        if "optimal_title_length" not in factors:
            recommendations.append("Optimize title length (30-70 characters)")
        if "optimal_description_length" not in factors:
            recommendations.append("Optimize meta description (120-160 characters)")
        if "has_images" not in factors:
            recommendations.append("Add relevant images to improve engagement")
        if "structured_content" not in factors:
            recommendations.append("Use heading tags for better content structure")
        if "social_presence" not in factors:
            recommendations.append("Implement social media integration")
        if "mobile_optimized" not in factors:
            recommendations.append("Ensure mobile optimization")
        if score < 70:
            recommendations.append("Consider comprehensive content audit")
        
        return recommendations[:5]  # Return top 5 recommendations
    
    def analyze_competitive_positioning(self, target: Dict, competitors: List[Dict]) -> Dict[str, Any]:
        """Analyze competitive positioning."""
        positioning = {
            "target_strengths": [],
            "target_weaknesses": [],
            "opportunities": [],
            "threats": [],
            "competitive_advantage": [],
            "improvement_areas": []
        }
        
        # Analyze target vs competitors
        target_quality = self.analyze_content_quality(target)
        target_score = target_quality['quality_score']
        
        competitor_scores = []
        for comp in competitors:
            comp_quality = self.analyze_content_quality(comp)
            competitor_scores.append(comp_quality['quality_score'])
        
        avg_competitor_score = statistics.mean(competitor_scores) if competitor_scores else 0
        
        # Determine positioning
        if target_score > avg_competitor_score:
            positioning["competitive_advantage"].append(f"Quality score {target_score:.0f}% vs avg {avg_competitor_score:.0f}%")
            positioning["target_strengths"].append("Superior content quality")
        else:
            positioning["improvement_areas"].append(f"Quality gap: -{avg_competitor_score - target_score:.0f}%")
            positioning["target_weaknesses"].append("Below average content quality")
        
        # Tech analysis
        target_tech = set(target.get('technologies', []))
        all_competitor_tech = set()
        for comp in competitors:
            all_competitor_tech.update(comp.get('technologies', []))
        
        unique_tech = target_tech - all_competitor_tech
        missing_tech = all_competitor_tech - target_tech
        
        if unique_tech:
            positioning["target_strengths"].append(f"Unique technologies: {', '.join(list(unique_tech)[:3])}")
        if missing_tech:
            positioning["opportunities"].append(f"Consider adopting: {', '.join(list(missing_tech)[:3])}")
        
        # Social signals comparison
        target_social = sum(target.get('social_signals', {}).values())
        competitor_social = [sum(c.get('social_signals', {}).values()) for c in competitors]
        avg_competitor_social = statistics.mean(competitor_social) if competitor_social else 0
        
        if target_social > avg_competitor_social:
            positioning["target_strengths"].append("Strong social media presence")
        else:
            positioning["opportunities"].append("Enhance social media engagement")
        
        return positioning
    
    def extract_keywords(self, content: Dict, max_keywords: int = 10) -> List[Dict[str, Any]]:
        """Extract and rank keywords from content."""
        text = f"{content.get('title', '')} {content.get('description', '')} {' '.join(content.get('headings', []))}".lower()
        
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'could'}
        
        words = re.findall(r'\b[a-z]+\b', text)
        words = [w for w in words if w not in stop_words and len(w) > 2]
        
        word_freq = Counter(words)
        
        keywords = []
        for word, count in word_freq.most_common(max_keywords):
            keywords.append({
                "keyword": word,
                "frequency": count,
                "density": (count / len(words) * 100) if words else 0
            })
        
        return keywords

# ================== CORE ANALYSIS FUNCTIONS ================== #

async def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 30, render_js: bool = False) -> str:
    """Fetch URL content with retry logic and optional JS rendering."""
    
    # Check if JS rendering needed
    if render_js or (SMART_JS_RENDER and should_use_js_rendering(url)):
        return await fetch_with_selenium(url, timeout)
    
    # Standard HTTP fetch
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

def should_use_js_rendering(url: str) -> bool:
    """Determine if URL needs JS rendering based on patterns."""
    js_patterns = [
        'react', 'angular', 'vue', 'next', 'nuxt',
        'vercel', 'netlify', 'gatsby', 'spa',
        '.app', 'dashboard', 'portal', 'admin'
    ]
    
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in js_patterns)

async def fetch_with_selenium(url: str, timeout: int = 30) -> str:
    """Fetch content using Selenium for JS-heavy sites."""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(timeout)
        
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            await asyncio.sleep(2)  # Wait for dynamic content
            html = driver.page_source
            return html
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Selenium fetch failed for {url}: {e}")
        # Fallback to regular fetch
        return await fetch_with_retry(url, render_js=False)

def extract_head_signals(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract important signals from HTML head."""
    signals = {
        "title": "",
        "description": "",
        "keywords": [],
        "og_data": {},
        "twitter_data": {},
        "structured_data": [],
        "canonical": "",
        "lang": "",
        "viewport": "",
        "robots": ""
    }
    
    # Title
    title_tag = soup.find('title')
    if title_tag:
        signals['title'] = title_tag.get_text(strip=True)
    
    # Meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        property = meta.get('property', '').lower()
        content = meta.get('content', '')
        
        if name == 'description':
            signals['description'] = content
        elif name == 'keywords':
            signals['keywords'] = [k.strip() for k in content.split(',')]
        elif name == 'viewport':
            signals['viewport'] = content
        elif name == 'robots':
            signals['robots'] = content
        elif property.startswith('og:'):
            signals['og_data'][property] = content
        elif name.startswith('twitter:'):
            signals['twitter_data'][name] = content
    
    # Canonical URL
    canonical = soup.find('link', {'rel': 'canonical'})
    if canonical:
        signals['canonical'] = canonical.get('href', '')
    
    # Language
    html_tag = soup.find('html')
    if html_tag:
        signals['lang'] = html_tag.get('lang', '')
    
    # Structured data
    for script in soup.find_all('script', {'type': 'application/ld+json'}):
        try:
            data = json.loads(script.string)
            signals['structured_data'].append(data)
        except:
            pass
    
    return signals

def extract_social_signals(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract social media signals and links."""
    social = {
        "facebook": None,
        "twitter": None,
        "linkedin": None,
        "instagram": None,
        "youtube": None,
        "tiktok": None,
        "pinterest": None,
        "github": None
    }
    
    social_patterns = {
        "facebook": r"facebook\.com/[\w\-\.]+",
        "twitter": r"twitter\.com/[\w\-\.]+|x\.com/[\w\-\.]+",
        "linkedin": r"linkedin\.com/(?:company|in)/[\w\-\.]+",
        "instagram": r"instagram\.com/[\w\-\.]+",
        "youtube": r"youtube\.com/(?:c|channel|user)/[\w\-\.]+",
        "tiktok": r"tiktok\.com/@[\w\-\.]+",
        "pinterest": r"pinterest\.com/[\w\-\.]+",
        "github": r"github\.com/[\w\-\.]+"
    }
    
    all_links = soup.find_all('a', href=True)
    
    for link in all_links:
        href = link['href']
        for platform, pattern in social_patterns.items():
            if re.search(pattern, href, re.IGNORECASE):
                social[platform] = href
                break
    
    return social

def detect_tech_and_cro(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    """Detect technologies and CRO elements."""
    tech_signals = {
        "technologies": [],
        "analytics": [],
        "cro_elements": [],
        "frameworks": [],
        "cms": None,
        "ecommerce": None,
        "performance": {}
    }
    
    # Technology detection patterns
    tech_patterns = {
        "React": [r"react", r"_react", r"React\."],
        "Vue": [r"vue", r"Vue\."],
        "Angular": [r"angular", r"ng-"],
        "jQuery": [r"jquery", r"jQuery"],
        "Bootstrap": [r"bootstrap"],
        "Tailwind": [r"tailwind"],
        "WordPress": [r"wp-content", r"wp-includes"],
        "Shopify": [r"shopify", r"myshopify"],
        "Webflow": [r"webflow"],
        "Next.js": [r"next", r"_next"],
        "Gatsby": [r"gatsby"],
        "Nuxt": [r"nuxt", r"_nuxt"]
    }
    
    # Check patterns
    html_lower = html.lower()
    for tech, patterns in tech_patterns.items():
        for pattern in patterns:
            if re.search(pattern, html_lower):
                tech_signals["technologies"].append(tech)
                break
    
    # Analytics detection
    analytics_patterns = {
        "Google Analytics": [r"google-analytics", r"gtag", r"ga\("],
        "Google Tag Manager": [r"googletagmanager"],
        "Facebook Pixel": [r"fbevents", r"facebook.*pixel"],
        "Hotjar": [r"hotjar"],
        "Segment": [r"segment", r"analytics\.js"],
        "Mixpanel": [r"mixpanel"],
        "Heap": [r"heap"],
        "Amplitude": [r"amplitude"]
    }
    
    for analytics, patterns in analytics_patterns.items():
        for pattern in patterns:
            if re.search(pattern, html_lower):
                tech_signals["analytics"].append(analytics)
                break
    
    # CRO elements detection
    cro_elements = {
        "forms": len(soup.find_all('form')),
        "buttons": len(soup.find_all('button')),
        "cta_buttons": len(soup.find_all('a', class_=re.compile(r'btn|button|cta', re.I))),
        "modals": len(soup.find_all(class_=re.compile(r'modal|popup|overlay', re.I))),
        "testimonials": len(soup.find_all(class_=re.compile(r'testimonial|review|rating', re.I))),
        "pricing": bool(soup.find(class_=re.compile(r'pricing|price|plan', re.I))),
        "chat_widget": bool(re.search(r'intercom|crisp|drift|zendesk|tawk', html_lower))
    }
    
    tech_signals["cro_elements"] = cro_elements
    
    # CMS detection
    if "WordPress" in tech_signals["technologies"]:
        tech_signals["cms"] = "WordPress"
    elif "Webflow" in tech_signals["technologies"]:
        tech_signals["cms"] = "Webflow"
    elif re.search(r'drupal', html_lower):
        tech_signals["cms"] = "Drupal"
    elif re.search(r'joomla', html_lower):
        tech_signals["cms"] = "Joomla"
    
    # E-commerce detection
    if "Shopify" in tech_signals["technologies"]:
        tech_signals["ecommerce"] = "Shopify"
    elif re.search(r'woocommerce', html_lower):
        tech_signals["ecommerce"] = "WooCommerce"
    elif re.search(r'magento', html_lower):
        tech_signals["ecommerce"] = "Magento"
    elif re.search(r'bigcommerce', html_lower):
        tech_signals["ecommerce"] = "BigCommerce"
    
    return tech_signals

def analyze_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze page content structure and elements."""
    content = {
        "headings": [],
        "images": [],
        "links": {
            "internal": [],
            "external": []
        },
        "forms": [],
        "videos": [],
        "word_count": 0,
        "text_content": ""
    }
    
    # Extract headings
    for i in range(1, 7):
        for heading in soup.find_all(f'h{i}'):
            text = heading.get_text(strip=True)
            if text:
                content["headings"].append({
                    "level": i,
                    "text": text[:200]  # Limit length
                })
    
    # Extract images
    for img in soup.find_all('img')[:20]:  # Limit to 20 images
        src = img.get('src', '')
        alt = img.get('alt', '')
        if src:
            content["images"].append({
                "src": src,
                "alt": alt[:100]  # Limit alt text length
            })
    
    # Extract links
    base_domain = None
    for link in soup.find_all('a', href=True)[:50]:  # Limit to 50 links
        href = link['href']
        text = link.get_text(strip=True)[:50]
        
        if href.startswith('http'):
            parsed = urlparse(href)
            if not base_domain:
                base_domain = parsed.netloc
            
            if parsed.netloc == base_domain:
                content["links"]["internal"].append({
                    "url": href,
                    "text": text
                })
            else:
                content["links"]["external"].append({
                    "url": href,
                    "text": text
                })
    
    # Extract forms
    for form in soup.find_all('form')[:5]:  # Limit to 5 forms
        form_data = {
            "action": form.get('action', ''),
            "method": form.get('method', 'get'),
            "inputs": len(form.find_all(['input', 'textarea', 'select']))
        }
        content["forms"].append(form_data)
    
    # Extract videos
    for video in soup.find_all(['video', 'iframe']):
        if video.name == 'iframe':
            src = video.get('src', '')
            if 'youtube' in src or 'vimeo' in src:
                content["videos"].append(src)
        else:
            content["videos"].append("embedded_video")
    
    # Get text content and word count
    text = soup.get_text()
    content["text_content"] = ' '.join(text.split())[:1000]  # First 1000 chars
    content["word_count"] = len(text.split())
    
    return content

async def analyze_competitor_enhanced(url: str, render_js: bool = False, use_ai: bool = True) -> Dict[str, Any]:
    """Enhanced competitor analysis with AI capabilities."""
    try:
        # Check cache
        cache_key = get_cache_key(url, render_js=render_js, use_ai=use_ai)
        cached = get_from_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for {url}")
            return cached
        
        # Fetch content
        html = await fetch_with_retry(url, render_js=render_js)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Basic analysis
        result = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "head_signals": extract_head_signals(soup),
            "social_signals": extract_social_signals(soup, url),
            "technologies": detect_tech_and_cro(soup, html),
            "content": analyze_content(soup),
            "performance": {
                "page_size": len(html),
                "load_time": "N/A",
                "requests": "N/A"
            }
        }
        
        # AI enhancement if enabled
        if use_ai:
            ai_analyzer = EnhancedAIAnalyzer()
            
            # Add AI analysis
            result["ai_analysis"] = {
                "sentiment": ai_analyzer.analyze_sentiment(result["content"]["text_content"]),
                "industry": ai_analyzer.detect_industry(result),
                "content_quality": ai_analyzer.analyze_content_quality(result),
                "keywords": ai_analyzer.extract_keywords(result)
            }
        
        # Cache result
        set_cache(cache_key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ================== AI HELPER FUNCTIONS ================== #

def enhanced_ai_analysis(data: Dict, language: str = "en") -> Dict[str, Any]:
    """Perform enhanced AI analysis on competitor data."""
    ai_analyzer = EnhancedAIAnalyzer()
    
    analysis = {
        "summary": generate_ai_summary(data, language),
        "strengths": [],
        "weaknesses": [],
        "opportunities": [],
        "threats": [],
        "recommendations": [],
        "competitive_score": 0,
        "market_position": "unknown"
    }
    
    # Analyze quality
    quality = ai_analyzer.analyze_content_quality(data)
    analysis["competitive_score"] = quality["quality_score"]
    
    # Determine market position
    if quality["quality_score"] >= 80:
        analysis["market_position"] = "leader"
    elif quality["quality_score"] >= 60:
        analysis["market_position"] = "challenger"
    elif quality["quality_score"] >= 40:
        analysis["market_position"] = "follower"
    else:
        analysis["market_position"] = "nicher"
    
    # Analyze strengths
    if data.get("head_signals", {}).get("title"):
        analysis["strengths"].append("SEO optimized title")
    if len(data.get("technologies", {}).get("technologies", [])) > 5:
        analysis["strengths"].append("Modern technology stack")
    if data.get("social_signals"):
        active_social = [k for k, v in data["social_signals"].items() if v]
        if len(active_social) > 3:
            analysis["strengths"].append(f"Strong social presence ({len(active_social)} platforms)")
    
    # Analyze weaknesses
    if not data.get("head_signals", {}).get("description"):
        analysis["weaknesses"].append("Missing meta description")
    if data.get("content", {}).get("word_count", 0) < 300:
        analysis["weaknesses"].append("Thin content")
    if not data.get("technologies", {}).get("analytics"):
        analysis["weaknesses"].append("No analytics tracking detected")
    
    # Generate recommendations
    analysis["recommendations"] = generate_ai_recommendations(data, language)
    
    return analysis

def generate_ai_summary(data: Dict, language: str = "en") -> str:
    """Generate AI summary of the analysis."""
    title = data.get("head_signals", {}).get("title", "Unknown")
    tech_count = len(data.get("technologies", {}).get("technologies", []))
    word_count = data.get("content", {}).get("word_count", 0)
    
    if language == "fi":
        return f"Sivusto '{title}' käyttää {tech_count} teknologiaa ja sisältää {word_count} sanaa sisältöä."
    else:
        return f"The site '{title}' uses {tech_count} technologies and contains {word_count} words of content."

def generate_ai_recommendations(data: Dict, language: str = "en") -> List[str]:
    """Generate AI-powered recommendations."""
    recommendations = []
    
    # SEO recommendations
    if not data.get("head_signals", {}).get("description"):
        rec = "Add meta description for better SEO" if language == "en" else "Lisää meta-kuvaus paremman SEO:n vuoksi"
        recommendations.append(rec)
    
    # Content recommendations
    word_count = data.get("content", {}).get("word_count", 0)
    if word_count < 500:
        rec = "Increase content depth (current: {} words, recommended: 1000+)".format(word_count) if language == "en" else "Lisää sisällön syvyyttä (nykyinen: {} sanaa, suositus: 1000+)".format(word_count)
        recommendations.append(rec)
    
    # Technology recommendations
    if not data.get("technologies", {}).get("analytics"):
        rec = "Implement analytics tracking" if language == "en" else "Ota käyttöön analytiikkaseuranta"
        recommendations.append(rec)
    
    # Social recommendations
    social = data.get("social_signals", {})
    if not social.get("facebook") and not social.get("instagram"):
        rec = "Add social media presence" if language == "en" else "Lisää sosiaalisen median läsnäolo"
        recommendations.append(rec)
    
    # Performance recommendations
    page_size = data.get("performance", {}).get("page_size", 0)
    if page_size > 3000000:  # 3MB
        rec = "Optimize page size for faster loading" if language == "en" else "Optimoi sivun koko nopeampaa latautumista varten"
        recommendations.append(rec)
    
    return recommendations[:5]  # Return top 5 recommendations

def generate_enhanced_swot(data: Dict, competitors: List[Dict] = None) -> Dict[str, List[str]]:
    """Generate enhanced SWOT analysis."""
    ai_analyzer = EnhancedAIAnalyzer()
    
    swot = {
        "strengths": [],
        "weaknesses": [],
        "opportunities": [],
        "threats": []
    }
    
    # Analyze content quality
    quality = ai_analyzer.analyze_content_quality(data)
    
    # Strengths
    if quality["quality_score"] > 70:
        swot["strengths"].append(f"High content quality score: {quality['quality_score']}%")
    
    tech = data.get("technologies", {}).get("technologies", [])
    if len(tech) > 5:
        swot["strengths"].append(f"Robust technology stack with {len(tech)} technologies")
    
    if data.get("technologies", {}).get("ecommerce"):
        swot["strengths"].append(f"E-commerce enabled with {data['technologies']['ecommerce']}")
    
    # Weaknesses
    if quality["quality_score"] < 50:
        swot["weaknesses"].append(f"Low content quality score: {quality['quality_score']}%")
    
    if not data.get("head_signals", {}).get("viewport"):
        swot["weaknesses"].append("No mobile optimization detected")
    
    if data.get("content", {}).get("word_count", 0) < 500:
        swot["weaknesses"].append("Insufficient content depth")
    
    # Opportunities
    missing_social = [k for k, v in data.get("social_signals", {}).items() if not v]
    if missing_social:
        swot["opportunities"].append(f"Expand to {len(missing_social)} additional social platforms")
    
    if not data.get("technologies", {}).get("analytics"):
        swot["opportunities"].append("Implement analytics for data-driven decisions")
    
    # Threats
    if competitors:
        competitor_quality_scores = [ai_analyzer.analyze_content_quality(c)["quality_score"] for c in competitors]
        avg_competitor_score = sum(competitor_quality_scores) / len(competitor_quality_scores)
        
        if quality["quality_score"] < avg_competitor_score:
            swot["threats"].append(f"Below average quality vs competitors ({quality['quality_score']}% vs {avg_competitor_score:.0f}%)")
    
    if not data.get("url", "").startswith("https"):
        swot["threats"].append("Security: No HTTPS implementation")
    
    return swot

def calculate_ai_confidence(data: Dict) -> float:
    """Calculate confidence score for AI analysis."""
    confidence = 0.0
    factors = 0
    
    # Check data completeness
    if data.get("head_signals", {}).get("title"):
        confidence += 0.15
        factors += 1
    
    if data.get("head_signals", {}).get("description"):
        confidence += 0.15
        factors += 1
    
    if data.get("content", {}).get("word_count", 0) > 100:
        confidence += 0.20
        factors += 1
    
    if data.get("technologies", {}).get("technologies"):
        confidence += 0.15
        factors += 1
    
    if data.get("social_signals"):
        confidence += 0.10
        factors += 1
    
    if data.get("content", {}).get("headings"):
        confidence += 0.15
        factors += 1
    
    if data.get("content", {}).get("images"):
        confidence += 0.10
        factors += 1
    
    return min(confidence, 1.0)

async def get_openai_strategic_insights(data: Dict, language: str = "en") -> Dict[str, Any]:
    """Get strategic insights using OpenAI if available."""
    if not OPENAI_API_KEY:
        return {
            "available": False,
            "message": "OpenAI API key not configured"
        }
    
    try:
        ai_analyzer = EnhancedAIAnalyzer()
        
        # Prepare context
        context = {
            "url": data.get("url"),
            "title": data.get("head_signals", {}).get("title"),
            "description": data.get("head_signals", {}).get("description"),
            "technologies": data.get("technologies", {}).get("technologies", []),
            "word_count": data.get("content", {}).get("word_count"),
            "quality_score": ai_analyzer.analyze_content_quality(data).get("quality_score")
        }
        
        # Create prompt
        prompt = f"""Analyze this website and provide strategic insights:
        URL: {context['url']}
        Title: {context['title']}
        Technologies: {', '.join(context['technologies'])}
        Quality Score: {context['quality_score']}%
        
        Provide:
        1. Market positioning assessment
        2. Key competitive advantages
        3. Strategic recommendations
        4. Growth opportunities
        
        Language: {language}
        Format: JSON with keys: positioning, advantages, recommendations, opportunities
        """
        
        response = ai_analyzer.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a strategic business analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Parse response
        insights = json.loads(response.choices[0].message.content)
        
        return {
            "available": True,
            "insights": insights,
            "confidence": 0.85
        }
        
    except Exception as e:
        logger.error(f"OpenAI analysis error: {e}")
        return {
            "available": False,
            "message": f"Analysis failed: {str(e)}"
        }

def generate_batch_recommendations(analyses: List[Dict]) -> Dict[str, Any]:
    """Generate recommendations from batch analysis."""
    recommendations = {
        "common_strengths": [],
        "common_weaknesses": [],
        "industry_trends": [],
        "best_practices": [],
        "action_items": []
    }
    
    if not analyses:
        return recommendations
    
    # Analyze common patterns
    all_tech = []
    all_analytics = []
    quality_scores = []
    
    for analysis in analyses:
        all_tech.extend(analysis.get("technologies", {}).get("technologies", []))
        all_analytics.extend(analysis.get("technologies", {}).get("analytics", []))
        
        if "ai_analysis" in analysis:
            quality = analysis["ai_analysis"].get("content_quality", {})
            if quality.get("quality_score"):
                quality_scores.append(quality["quality_score"])
    
    # Find common technologies
    tech_counter = Counter(all_tech)
    common_tech = [tech for tech, count in tech_counter.most_common(3) if count > len(analyses) * 0.5]
    
    if common_tech:
        recommendations["industry_trends"].append(f"Common technologies: {', '.join(common_tech)}")
    
    # Analyze quality scores
    if quality_scores:
        avg_quality = sum(quality_scores) / len(quality_scores)
        recommendations["best_practices"].append(f"Average quality score: {avg_quality:.0f}%")
        
        if avg_quality < 60:
            recommendations["action_items"].append("Industry-wide opportunity for quality improvement")
    
    # Common weaknesses
    missing_analytics = sum(1 for a in analyses if not a.get("technologies", {}).get("analytics"))
    if missing_analytics > len(analyses) * 0.3:
        recommendations["common_weaknesses"].append("Lack of analytics implementation")
    
    return recommendations

def generate_visual_summary(data: Dict) -> Dict[str, Any]:
    """Generate data for visual summary charts."""
    summary = {
        "quality_metrics": {},
        "technology_distribution": {},
        "social_presence": {},
        "content_metrics": {},
        "performance_indicators": []
    }
    
    # Quality metrics
    if "ai_analysis" in data:
        quality = data["ai_analysis"].get("content_quality", {})
        summary["quality_metrics"] = {
            "score": quality.get("quality_score", 0),
            "grade": quality.get("grade", "N/A"),
            "factors": len(quality.get("factors", []))
        }
    
    # Technology distribution
    tech = data.get("technologies", {})
    summary["technology_distribution"] = {
        "total": len(tech.get("technologies", [])),
        "analytics": len(tech.get("analytics", [])),
        "has_cms": bool(tech.get("cms")),
        "has_ecommerce": bool(tech.get("ecommerce"))
    }
    
    # Social presence
    social = data.get("social_signals", {})
    summary["social_presence"] = {
        "platforms": sum(1 for v in social.values() if v),
        "coverage": (sum(1 for v in social.values() if v) / len(social) * 100) if social else 0
    }
    
    # Content metrics
    content = data.get("content", {})
    summary["content_metrics"] = {
        "word_count": content.get("word_count", 0),
        "images": len(content.get("images", [])),
        "headings": len(content.get("headings", [])),
        "forms": len(content.get("forms", [])),
        "videos": len(content.get("videos", []))
    }
    
    # Performance indicators
    indicators = []
    
    # SEO indicator
    seo_score = 0
    if data.get("head_signals", {}).get("title"):
        seo_score += 25
    if data.get("head_signals", {}).get("description"):
        seo_score += 25
    if data.get("head_signals", {}).get("canonical"):
        seo_score += 25
    if data.get("url", "").startswith("https"):
        seo_score += 25
    
    indicators.append({
        "name": "SEO Health",
        "value": seo_score,
        "max": 100
    })
    
    # Content depth
    word_count = content.get("word_count", 0)
    content_score = min(100, (word_count / 1000) * 100)
    indicators.append({
        "name": "Content Depth",
        "value": content_score,
        "max": 100
    })
    
    # Tech sophistication
    tech_score = min(100, len(tech.get("technologies", [])) * 10)
    indicators.append({
        "name": "Tech Stack",
        "value": tech_score,
        "max": 100
    })
    
    summary["performance_indicators"] = indicators
    
    return summary

# ================== PDF GENERATION ================== #

def create_competitive_analysis_pdf(analyses: List[Dict], company_name: str = "Target Company") -> BytesIO:
    """Create comprehensive PDF report from analyses."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=12
    )
    
    # Title
    story.append(Paragraph(f"Competitive Intelligence Report", title_style))
    story.append(Paragraph(f"{company_name}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(PageBreak())
    
    # Executive Summary
    story.append(Paragraph("Executive Summary", heading_style))
    
    summary_data = [
        ["Metric", "Value"],
        ["Sites Analyzed", str(len(analyses))],
        ["Average Quality Score", f"{sum(a.get('ai_analysis', {}).get('content_quality', {}).get('quality_score', 0) for a in analyses) / len(analyses):.0f}%" if analyses else "N/A"],
        ["Total Technologies", str(sum(len(a.get('technologies', {}).get('technologies', [])) for a in analyses))],
        ["Report Date", datetime.now().strftime('%Y-%m-%d')]
    ]
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(summary_table)
    story.append(PageBreak())
    
    # Individual Site Analysis
    for idx, analysis in enumerate(analyses, 1):
        story.append(Paragraph(f"Site Analysis #{idx}", heading_style))
        story.append(Paragraph(f"URL: {analysis.get('url', 'N/A')}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
        
        # Basic Info
        head_signals = analysis.get('head_signals', {})
        basic_data = [
            ["Property", "Value"],
            ["Title", head_signals.get('title', 'N/A')[:50]],
            ["Description", head_signals.get('description', 'N/A')[:100]],
            ["Language", head_signals.get('lang', 'N/A')],
            ["Word Count", str(analysis.get('content', {}).get('word_count', 0))]
        ]
        
        basic_table = Table(basic_data)
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(basic_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Technologies
        tech = analysis.get('technologies', {}).get('technologies', [])
        if tech:
            story.append(Paragraph("Technologies Detected:", styles['Heading2']))
            tech_text = ", ".join(tech)
            story.append(Paragraph(tech_text, styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # AI Analysis if available
        if 'ai_analysis' in analysis:
            ai = analysis['ai_analysis']
            
            # Quality Score
            quality = ai.get('content_quality', {})
            if quality:
                story.append(Paragraph(f"Quality Score: {quality.get('quality_score', 0)}% ({quality.get('grade', 'N/A')})", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
            
            # Keywords
            keywords = ai.get('keywords', [])
            if keywords:
                story.append(Paragraph("Top Keywords:", styles['Heading2']))
                kw_text = ", ".join([kw['keyword'] for kw in keywords[:5]])
                story.append(Paragraph(kw_text, styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
        
        if idx < len(analyses):
            story.append(PageBreak())
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

# ================== API ENDPOINTS ================== #

@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "name": "Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status": "operational",
        "ai_features": "enabled",
        "endpoints": {
            "analyze": "/api/v1/analyze",
            "ai_analyze": "/api/v2/ai-analyze",
            "deep_analysis": "/api/v1/deep-analysis",
            "batch_analyze": "/api/v1/batch-analyze-enhanced",
            "compare": "/api/v1/compare-enhanced/{url1}/{url2}",
            "generate_pdf": "/api/v1/generate-pdf"
        }
    }

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": APP_VERSION,
        "cache_size": len(cache),
        "ai_enabled": bool(OPENAI_API_KEY)
    }

@app.post("/api/v1/analyze")
async def analyze_endpoint(request: AnalyzeRequest):
    """Enhanced analyze endpoint with AI capabilities."""
    try:
        result = await analyze_competitor_enhanced(
            url=request.url,
            render_js=request.render_js,
            use_ai=True  # Always use AI for v1 endpoint
        )
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/ai-analyze")
async def ai_analyze_endpoint(request: AIAnalyzeRequest):
    """Advanced AI analysis endpoint."""
    try:
        # Perform base analysis
        analysis = await analyze_competitor_enhanced(
            url=request.url,
            render_js=request.render_js,
            use_ai=request.use_ai
        )
        
        # Add enhanced AI analysis
        if request.use_ai:
            analysis["enhanced_analysis"] = enhanced_ai_analysis(analysis, request.language)
            
            # Add SWOT if requested
            if request.include_swot:
                analysis["swot"] = generate_enhanced_swot(analysis)
            
            # Add recommendations if requested
            if request.include_recommendations:
                analysis["recommendations"] = generate_ai_recommendations(analysis, request.language)
            
            # Add confidence score
            analysis["ai_confidence"] = calculate_ai_confidence(analysis)
            
            # Try to get OpenAI insights
            if OPENAI_API_KEY:
                openai_insights = await get_openai_strategic_insights(analysis, request.language)
                if openai_insights.get("available"):
                    analysis["strategic_insights"] = openai_insights["insights"]
        
        # Add visual summary
        analysis["visual_summary"] = generate_visual_summary(analysis)
        
        return JSONResponse(content=analysis)
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/deep-analysis")
async def deep_analysis_endpoint(request: DeepAnalysisRequest):
    """Perform deep competitive analysis."""
    try:
        # Analyze main site
        main_analysis = await analyze_competitor_enhanced(
            url=request.url,
            render_js=True,
            use_ai=True
        )
        
        # Analyze competitors
        competitor_analyses = []
        for comp_url in request.competitors[:5]:  # Limit to 5 competitors
            try:
                comp_analysis = await analyze_competitor_enhanced(
                    url=comp_url,
                    render_js=False,
                    use_ai=True
                )
                competitor_analyses.append(comp_analysis)
            except Exception as e:
                logger.error(f"Error analyzing competitor {comp_url}: {e}")
        
        # Perform competitive positioning
        ai_analyzer = EnhancedAIAnalyzer()
        positioning = ai_analyzer.analyze_competitive_positioning(
            main_analysis,
            competitor_analyses
        )
        
        # Generate comprehensive report
        report = {
            "target": {
                "url": request.url,
                "company": request.company_name,
                "analysis": main_analysis
            },
            "competitors": competitor_analyses,
            "positioning": positioning,
            "swot": generate_enhanced_swot(main_analysis, competitor_analyses),
            "recommendations": generate_ai_recommendations(main_analysis, request.language),
            "batch_insights": generate_batch_recommendations(competitor_analyses),
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(content=comparison)
        
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/generate-pdf")
async def generate_pdf_endpoint(request: PDFRequest):
    """Generate PDF report from multiple URLs."""
    try:
        analyses = []
        
        for url in request.urls[:10]:  # Limit to 10 URLs
            try:
                analysis = await analyze_competitor_enhanced(
                    url=url,
                    render_js=False,
                    use_ai=True
                )
                analyses.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing {url} for PDF: {e}")
        
        if not analyses:
            raise HTTPException(status_code=400, detail="No valid analyses to generate PDF")
        
        # Generate PDF
        pdf_buffer = create_competitive_analysis_pdf(analyses, request.company_name)
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=competitive_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ================== MIDDLEWARE ================== #

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    client_ip = request.client.host
    
    # Skip rate limiting for health checks
    if request.url.path in ["/", "/health"]:
        return await call_next(request)
    
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Maximum {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds"
            }
        )
    
    response = await call_next(request)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )

# ================== STARTUP & SHUTDOWN ================== #

@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info(f"Starting Brandista Competitive Intelligence API v{APP_VERSION}")
    logger.info(f"AI features: {'Enabled' if OPENAI_API_KEY else 'Limited (no OpenAI key)'}")
    logger.info(f"Smart JS rendering: {SMART_JS_RENDER}")
    logger.info(f"Cache TTL: {CACHE_TTL} seconds")
    logger.info(f"Rate limit: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Brandista Competitive Intelligence API")
    logger.info(f"Cache size at shutdown: {len(cache)} entries")

# ================== UTILITY ENDPOINTS ================== #

@app.get("/api/v1/cache-status")
def cache_status():
    """Get cache status information."""
    return {
        "cache_size": len(cache),
        "max_cache_size": MAX_CACHE_SIZE,
        "cache_ttl": CACHE_TTL,
        "entries": list(cache.keys())[:10]  # Show first 10 keys
    }

@app.post("/api/v1/clear-cache")
def clear_cache():
    """Clear the cache."""
    global cache
    old_size = len(cache)
    cache = {}
    
    return {
        "message": "Cache cleared",
        "entries_removed": old_size,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/supported-features")
def supported_features():
    """Get list of supported features."""
    return {
        "core_features": [
            "URL analysis",
            "Technology detection",
            "Social signals extraction",
            "Content analysis",
            "SEO analysis"
        ],
        "ai_features": [
            "Sentiment analysis",
            "Industry detection",
            "Content quality scoring",
            "Competitive positioning",
            "Keyword extraction",
            "SWOT analysis",
            "Strategic recommendations"
        ],
        "advanced_features": [
            "JavaScript rendering",
            "Batch analysis",
            "Comparative analysis",
            "PDF report generation",
            "OpenAI insights" if OPENAI_API_KEY else "OpenAI insights (disabled - no API key)"
        ],
        "languages_supported": ["en", "fi"],
        "max_batch_size": 10,
        "max_competitors": 5,
        "cache_enabled": True,
        "rate_limiting": {
            "enabled": True,
            "limit": RATE_LIMIT_REQUESTS,
            "window": RATE_LIMIT_WINDOW
        }
    }

@app.get("/api/v1/analyze-quick/{url:path}")
async def quick_analyze(url: str):
    """Quick analysis endpoint for simple GET requests."""
    try:
        # Basic analysis without JS rendering for speed
        result = await analyze_competitor_enhanced(
            url=url,
            render_js=False,
            use_ai=True
        )
        
        # Return simplified result
        return {
            "url": url,
            "title": result.get("head_signals", {}).get("title"),
            "description": result.get("head_signals", {}).get("description"),
            "quality_score": result.get("ai_analysis", {}).get("content_quality", {}).get("quality_score"),
            "technologies": result.get("technologies", {}).get("technologies", []),
            "word_count": result.get("content", {}).get("word_count"),
            "timestamp": result.get("timestamp")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== MAIN ENTRY POINT ================== #

if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
        
        return JSONResponse(content=report)
        
    except Exception as e:
        logger.error(f"Deep analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/batch-analyze-enhanced")
async def batch_analyze_enhanced_endpoint(request: BatchAnalyzeRequest):
    """Analyze multiple URLs with AI enhancement."""
    try:
        analyses = []
        
        for url in request.urls[:10]:  # Limit to 10 URLs
            try:
                analysis = await analyze_competitor_enhanced(
                    url=url,
                    render_js=False,
                    use_ai=request.use_ai
                )
                analyses.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing {url}: {e}")
                analyses.append({
                    "url": url,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
        
        # Generate batch insights
        batch_insights = generate_batch_recommendations(analyses)
        
        # Compare if requested
        comparisons = {}
        if request.include_comparisons and len(analyses) > 1:
            ai_analyzer = EnhancedAIAnalyzer()
            for i, analysis in enumerate(analyses):
                if "error" not in analysis:
                    other_analyses = [a for j, a in enumerate(analyses) if j != i and "error" not in a]
                    comparisons[analysis["url"]] = ai_analyzer.analyze_competitive_positioning(
                        analysis,
                        other_analyses
                    )
        
        result = {
            "analyses": analyses,
            "batch_insights": batch_insights,
            "comparisons": comparisons,
            "summary": {
                "total_analyzed": len(analyses),
                "successful": sum(1 for a in analyses if "error" not in a),
                "failed": sum(1 for a in analyses if "error" in a),
                "average_quality": sum(a.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0) for a in analyses if "error" not in a) / max(1, sum(1 for a in analyses if "error" not in a))
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/compare-enhanced/{url1}/{url2}")
async def compare_enhanced_endpoint(url1: str, url2: str):
    """Enhanced comparison between two URLs."""
    try:
        # Analyze both URLs
        analysis1 = await analyze_competitor_enhanced(url1, use_ai=True)
        analysis2 = await analyze_competitor_enhanced(url2, use_ai=True)
        
        # Perform comparison
        ai_analyzer = EnhancedAIAnalyzer()
        
        comparison = {
            "url1": {
                "url": url1,
                "analysis": analysis1,
                "positioning": ai_analyzer.analyze_competitive_positioning(analysis1, [analysis2])
            },
            "url2": {
                "url": url2,
                "analysis": analysis2,
                "positioning": ai_analyzer.analyze_competitive_positioning(analysis2, [analysis1])
            },
            "comparison_summary": {
                "quality_difference": analysis1.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0) - 
                                    analysis2.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0),
                "tech_overlap": list(set(analysis1.get("technologies", {}).get("technologies", [])) & 
                                   set(analysis2.get("technologies", {}).get("technologies", []))),
                "unique_tech_url1": list(set(analysis1.get("technologies", {}).get("technologies", [])) - 
                                       set(analysis2.get("technologies", {}).get("technologies", []))),
                "unique_tech_url2": list(set(analysis2.get("technologies", {}).get("technologies", [])) - 
                                       set(analysis1.get("technologies", {}).get("technologies", [])))
            },
            "winner": url1 if analysis1.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0) > 
                             analysis2.get("ai_analysis", {}).get("content_quality", {}).get("quality_score", 0) else url2,
            "timestamp": datetime.now().isoformat()
        }
        
