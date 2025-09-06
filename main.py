#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 4.6.0 - Enhanced Scoring System for Better Differentiation
"""

import os
import re
import json
import base64
import hashlib
import logging
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict, Counter
import asyncio
import time

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

# TextBlob for sentiment analysis (optional)
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TextBlob = None
    TEXTBLOB_AVAILABLE = False

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

APP_VERSION = "4.6.0"
CACHE_TTL = 3600  # 1 hour cache
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# App initialization
app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Enhanced Kilpailija-analyysi API with Improved Scoring System"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI client (if available)
openai_client = None
if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Global cache
analysis_cache = {}

# ============ UTILITY FUNCTIONS ============

def ensure_integer_scores(data):
    """Convert all score fields to integers to fix Pydantic validation"""
    if isinstance(data, dict):
        for key, value in data.items():
            if '_score' in key or key == 'score':
                if isinstance(value, (int, float)):
                    data[key] = int(round(value))
            elif isinstance(value, dict):
                ensure_integer_scores(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        ensure_integer_scores(item)
    return data

def get_cache_key(url: str, analysis_type: str = "basic") -> str:
    """Generate cache key for analysis"""
    return hashlib.md5(f"{url}_{analysis_type}".encode()).hexdigest()

def is_cache_valid(timestamp: datetime) -> bool:
    """Check if cached result is still valid"""
    return datetime.now() - timestamp < timedelta(seconds=CACHE_TTL)

async def fetch_url(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[httpx.Response]:
    """Fetch URL with error handling and retries"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response
                elif attempt == MAX_RETRIES - 1:
                    logger.warning(f"Failed to fetch {url}: {response.status_code}")
                    return response
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Error fetching {url}: {str(e)}")
                return None
            await asyncio.sleep(1)  # Wait before retry
    
    return None

# ============ PYDANTIC MODELS (Same as before) ============

class CompetitorAnalysisRequest(BaseModel):
    """Request model for competitor analysis"""
    url: str = Field(..., description="Website URL to analyze")
    company_name: Optional[str] = Field(None, description="Company name")
    analysis_type: str = Field("comprehensive", description="Analysis type")
    language: str = Field("fi", description="Response language (fi/en)")
    include_ai: bool = Field(True, description="Include AI analysis")
    include_social: bool = Field(True, description="Include social media analysis")

class BasicAnalysis(BaseModel):
    """Basic website analysis results"""
    company: str
    website: str
    industry: Optional[str] = None
    digital_maturity_score: int
    social_platforms: int
    technical_score: int = 0
    content_score: int = 0
    seo_score: int = 0

class TechnicalAudit(BaseModel):
    """Technical website audit results"""
    has_ssl: bool = True
    has_mobile_optimization: bool = False
    page_speed_score: int = 0
    has_analytics: bool = False
    has_sitemap: bool = False
    has_robots_txt: bool = False
    meta_tags_score: int = 0

class ContentAnalysis(BaseModel):
    """Content analysis results"""
    word_count: int = 0
    readability_score: int = 0
    keyword_density: Dict[str, float] = {}
    content_freshness: str = "unknown"
    has_blog: bool = False
    content_quality_score: int = 0

class SocialMediaAnalysis(BaseModel):
    """Social media presence analysis"""
    platforms: List[str] = []
    total_followers: int = 0
    engagement_rate: float = 0.0
    posting_frequency: str = "unknown"
    social_score: int = 0

class UXAnalysis(BaseModel):
    """User Experience analysis"""
    navigation_score: int = 0
    visual_design_score: int = 0
    accessibility_score: int = 0
    mobile_ux_score: int = 0
    overall_ux_score: int = 0

class CompetitiveAnalysis(BaseModel):
    """Competitive positioning analysis"""
    market_position: str = "unknown"
    competitive_advantages: List[str] = []
    competitive_threats: List[str] = []
    market_share_estimate: str = "unknown"
    competitive_score: int = 0

class AIAnalysis(BaseModel):
    """AI-powered analysis results"""
    summary: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    recommendations: List[str] = []
    confidence_score: int = 0
    sentiment_score: float = 0.0
    
    # Finnish versions for backward compatibility
    johtopäätökset: str = ""
    vahvuudet: List[str] = []
    heikkoudet: List[str] = []
    mahdollisuudet: List[str] = []
    uhat: List[str] = []
    toimenpidesuositukset: List[str] = []
    strategiset_suositukset: List[str] = []
    quick_wins: List[str] = []
    
class DetailedAnalysis(BaseModel):
    """Detailed analysis container"""
    social_media: SocialMediaAnalysis
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    competitive_analysis: CompetitiveAnalysis

class SmartActions(BaseModel):
    """Smart action recommendations"""
    actions: List[Dict[str, Any]] = []
    priority_matrix: Dict[str, List[str]] = {}

class SmartScores(BaseModel):
    """Smart scoring system"""
    overall: int = 0
    technical: int = 0
    content: int = 0
    social: int = 0
    ux: int = 0
    competitive: int = 0

class EnhancedFeatures(BaseModel):
    """Enhanced analysis features"""
    industry_benchmarking: Dict[str, Any] = {}
    competitor_gaps: List[str] = []
    growth_opportunities: List[str] = []
    risk_assessment: List[str] = []

class AnalysisResponse(BaseModel):
    """Main analysis response model"""
    success: bool
    company_name: str
    analysis_date: str
    basic_analysis: BasicAnalysis
    ai_analysis: AIAnalysis
    detailed_analysis: DetailedAnalysis
    smart: Optional[Dict[str, Any]] = None
    enhanced_features: Optional[EnhancedFeatures] = None

class PDFRequest(BaseModel):
    """PDF generation request"""
    company_name: str
    url: str
    basic_analysis: Dict[str, Any]
    ai_analysis: Dict[str, Any]
    timestamp: str
    language: str = "fi"

# ============ ENHANCED CORE ANALYSIS FUNCTIONS ============

async def analyze_basic_metrics(url: str, html_content: str) -> Dict[str, Any]:
    """Analyze basic website metrics with more nuanced scoring"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    score = 0.0
    detailed_scores = {}
    
    # 1. Title tag analysis (0-12 points)
    title = soup.find('title')
    if title:
        title_text = title.get_text().strip()
        title_length = len(title_text)
        if 30 <= title_length <= 60:
            score += 12
            detailed_scores['title'] = 12
        elif 20 <= title_length < 30 or 60 < title_length <= 70:
            score += 8
            detailed_scores['title'] = 8
        elif 10 <= title_length < 20:
            score += 5
            detailed_scores['title'] = 5
        elif title_length > 0:
            score += 2
            detailed_scores['title'] = 2
    
    # 2. Meta description analysis (0-10 points)
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        desc_content = meta_desc.get('content', '').strip()
        desc_length = len(desc_content)
        if 120 <= desc_length <= 160:
            score += 10
            detailed_scores['meta_desc'] = 10
        elif 80 <= desc_length < 120:
            score += 7
            detailed_scores['meta_desc'] = 7
        elif 160 < desc_length <= 200:
            score += 6
            detailed_scores['meta_desc'] = 6
        elif desc_length > 0:
            score += 3
            detailed_scores['meta_desc'] = 3
    
    # 3. Header structure analysis (0-15 points)
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    h3_tags = soup.find_all('h3')
    
    # H1 scoring (0-8 points)
    if len(h1_tags) == 1:
        score += 8
        detailed_scores['h1'] = 8
    elif len(h1_tags) == 2:
        score += 5
        detailed_scores['h1'] = 5
    elif len(h1_tags) > 2:
        score += 2
        detailed_scores['h1'] = 2
    
    # H2/H3 structure (0-7 points)
    if len(h2_tags) >= 3:
        score += 4
        detailed_scores['h2'] = 4
    elif len(h2_tags) >= 1:
        score += 2
        detailed_scores['h2'] = 2
    
    if len(h3_tags) >= 2:
        score += 3
        detailed_scores['h3'] = 3
    elif len(h3_tags) >= 1:
        score += 1
        detailed_scores['h3'] = 1
    
    # 4. Content volume analysis (0-18 points)
    text_content = soup.get_text()
    words = text_content.split()
    word_count = len(words)
    
    if word_count > 3000:
        score += 18
        detailed_scores['content_volume'] = 18
    elif word_count > 2000:
        score += 15
        detailed_scores['content_volume'] = 15
    elif word_count > 1500:
        score += 12
        detailed_scores['content_volume'] = 12
    elif word_count > 1000:
        score += 9
        detailed_scores['content_volume'] = 9
    elif word_count > 500:
        score += 5
        detailed_scores['content_volume'] = 5
    elif word_count > 200:
        score += 2
        detailed_scores['content_volume'] = 2
    
    # 5. Image optimization (0-8 points)
    images = soup.find_all('img')
    if images:
        images_with_alt = [img for img in images if img.get('alt', '').strip()]
        alt_ratio = len(images_with_alt) / len(images)
        img_score = int(alt_ratio * 8)
        score += img_score
        detailed_scores['image_optimization'] = img_score
    
    # 6. Technical basics (0-12 points)
    # Viewport meta tag
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if viewport:
        score += 6
        detailed_scores['viewport'] = 6
    
    # HTTPS
    if url.startswith('https'):
        score += 6
        detailed_scores['https'] = 6
    
    # 7. Analytics & tracking (0-5 points)
    analytics_found = any([
        'google-analytics' in html_content.lower(),
        'gtag' in html_content.lower(),
        'google tagmanager' in html_content.lower(),
        'matomo' in html_content.lower(),
        'plausible' in html_content.lower()
    ])
    if analytics_found:
        score += 5
        detailed_scores['analytics'] = 5
    
    # 8. Social media integration (0-10 points)
    social_platforms = set()
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        if 'facebook.com' in href:
            social_platforms.add('facebook')
        if 'twitter.com' in href or 'x.com' in href:
            social_platforms.add('twitter')
        if 'linkedin.com' in href:
            social_platforms.add('linkedin')
        if 'instagram.com' in href:
            social_platforms.add('instagram')
        if 'youtube.com' in href:
            social_platforms.add('youtube')
        if 'tiktok.com' in href:
            social_platforms.add('tiktok')
    
    social_score = min(len(social_platforms) * 2, 10)
    score += social_score
    detailed_scores['social_media'] = social_score
    
    # 9. Schema markup (0-5 points)
    if soup.find_all(attrs={"itemtype": True}) or '"@context"' in html_content:
        score += 5
        detailed_scores['schema_markup'] = 5
    elif 'schema.org' in html_content.lower():
        score += 3
        detailed_scores['schema_markup'] = 3
    
    # 10. Open Graph tags (0-5 points)
    og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
    if len(og_tags) >= 4:
        score += 5
        detailed_scores['open_graph'] = 5
    elif len(og_tags) >= 2:
        score += 3
        detailed_scores['open_graph'] = 3
    elif len(og_tags) >= 1:
        score += 1
        detailed_scores['open_graph'] = 1
    
    # 11. Performance indicators (0-8 points)
    # Check for common performance issues
    perf_score = 8
    
    # Large inline scripts
    scripts = soup.find_all('script')
    inline_script_size = sum(len(s.string or '') for s in scripts if not s.get('src'))
    if inline_script_size > 50000:
        perf_score -= 3
    elif inline_script_size > 20000:
        perf_score -= 1
    
    # Too many external resources
    external_resources = len(soup.find_all('link', rel='stylesheet')) + len(soup.find_all('script', src=True))
    if external_resources > 30:
        perf_score -= 3
    elif external_resources > 20:
        perf_score -= 1
    
    score += max(0, perf_score)
    detailed_scores['performance'] = max(0, perf_score)
    
    # Final score calculation (cap at 100)
    final_score = int(round(min(score, 100)))
    
    # Log detailed scoring for debugging
    logger.info(f"URL: {url}")
    logger.info(f"Detailed scores: {detailed_scores}")
    logger.info(f"Total score: {final_score}")
    
    return {
        'digital_maturity_score': final_score,
        'social_platforms': len(social_platforms),
        'word_count': word_count,
        'has_ssl': url.startswith('https'),
        'has_analytics': analytics_found,
        'has_mobile_viewport': bool(viewport),
        'title': title.get_text().strip() if title else '',
        'meta_description': meta_desc.get('content', '') if meta_desc else '',
        'h1_count': len(h1_tags),
        'h2_count': len(h2_tags),
        'detailed_scores': detailed_scores  # For debugging
    }

async def analyze_technical_aspects(url: str, html_content: str) -> TechnicalAudit:
    """Analyze technical aspects of the website"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Technical score calculation
    technical_score = 0.0
    
    # SSL
    has_ssl = url.startswith('https')
    if has_ssl:
        technical_score += 20
    
    # Mobile optimization
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    has_mobile = bool(viewport)
    if has_mobile:
        technical_score += 15
    
    # Analytics
    has_analytics = any([
        'google-analytics' in html_content.lower(),
        'gtag' in html_content.lower(),
        'ga(' in html_content.lower(),
        'matomo' in html_content.lower()
    ])
    if has_analytics:
        technical_score += 10
    
    # Meta tags quality
    meta_score = 0.0
    title = soup.find('title')
    if title:
        title_length = len(title.get_text().strip())
        if 30 <= title_length <= 60:
            meta_score += 10
        elif title_length > 10:
            meta_score += 5
    
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        desc_length = len(meta_desc.get('content', ''))
        if 120 <= desc_length <= 160:
            meta_score += 10
        elif desc_length > 50:
            meta_score += 5
    
    technical_score += meta_score
    
    # Page speed estimation (more sophisticated)
    page_speed = 85  # Start with good baseline
    
    # Check various performance factors
    if 'jquery' in html_content.lower():
        page_speed -= 5
    if len(html_content) > 200000:  # Very large page
        page_speed -= 15
    elif len(html_content) > 100000:  # Large page
        page_speed -= 8
    
    # Check for optimization indicators
    if 'webpack' in html_content.lower() or 'vite' in html_content.lower():
        page_speed += 5
    if 'lazy' in html_content.lower():
        page_speed += 3
    
    page_speed = max(20, min(100, page_speed))
    
    return TechnicalAudit(
        has_ssl=has_ssl,
        has_mobile_optimization=has_mobile,
        page_speed_score=int(round(page_speed)),
        has_analytics=has_analytics,
        has_sitemap=False,  # Would need separate check
        has_robots_txt=False,  # Would need separate check
        meta_tags_score=int(round(meta_score))
    )

async def analyze_content_quality(html_content: str) -> ContentAnalysis:
    """Analyze content quality and structure"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text_content = soup.get_text()
    
    # Clean up text
    lines = (line.strip() for line in text_content.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text_content = ' '.join(chunk for chunk in chunks if chunk)
    
    # Word count
    words = text_content.split()
    word_count = len(words)
    
    # Sentence analysis for readability
    sentences = [s.strip() for s in text_content.split('.') if s.strip()]
    sentence_count = len(sentences)
    
    if sentence_count > 0:
        avg_words_per_sentence = word_count / sentence_count
        # Flesch Reading Ease approximation
        readability = 206.835 - 1.015 * avg_words_per_sentence
        readability = max(0, min(100, readability))
    else:
        readability = 0
    
    # Content quality score (more nuanced)
    content_score = 0.0
    
    # Content volume scoring
    if word_count > 2500:
        content_score += 35
    elif word_count > 1500:
        content_score += 28
    elif word_count > 1000:
        content_score += 20
    elif word_count > 500:
        content_score += 12
    elif word_count > 200:
        content_score += 5
    
    # Check for blog/news section
    has_blog = bool(soup.find('a', href=re.compile(r'/(blog|news|articles|uutiset|artikkelit)', re.I)))
    if has_blog:
        content_score += 15
    
    # Check for diverse content types
    if soup.find_all('article'):
        content_score += 5
    if soup.find_all('video') or 'youtube' in html_content.lower():
        content_score += 5
    
    # Image optimization
    images = soup.find_all('img')
    if images:
        images_with_alt = [img for img in images if img.get('alt', '').strip()]
        if images_with_alt:
            alt_quality_ratio = len(images_with_alt) / len(images)
            content_score += int(alt_quality_ratio * 10)
    
    # Lists and structure
    if soup.find_all('ul') or soup.find_all('ol'):
        content_score += 5
    
    # Forms (indicating interactivity)
    if soup.find_all('form'):
        content_score += 5
    
    content_score = min(100, content_score)
    
    return ContentAnalysis(
        word_count=word_count,
        readability_score=int(round(readability)),
        keyword_density={},
        content_freshness="unknown",
        has_blog=has_blog,
        content_quality_score=int(round(content_score))
    )

async def analyze_ux_elements(html_content: str) -> UXAnalysis:
    """Analyze user experience elements"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Navigation analysis (more detailed)
    nav_score = 0.0
    
    # Check for various navigation elements
    nav_elements = soup.find_all(['nav', 'header'])
    menu_elements = soup.find_all('ul', class_=re.compile('nav|menu', re.I))
    
    if nav_elements:
        nav_score += 15
    if menu_elements:
        nav_score += 10
    
    # Breadcrumbs
    if soup.find_all(class_=re.compile('breadcrumb', re.I)):
        nav_score += 5
    
    # Search functionality
    search_elements = (
        soup.find_all('input', type='search') + 
        soup.find_all('input', placeholder=re.compile('search|haku|etsi', re.I))
    )
    if search_elements:
        nav_score += 10
    
    # Footer navigation
    footer = soup.find('footer')
    if footer and footer.find_all('a'):
        nav_score += 5
    
    nav_score = min(40, nav_score)
    
    # Visual design indicators
    design_score = 30.0  # Base score
    
    # Modern CSS frameworks/libraries
    css_indicators = {
        'bootstrap': 5,
        'tailwind': 8,
        'bulma': 5,
        'foundation': 5,
        'material': 6,
        'animate': 3
    }
    
    for framework, points in css_indicators.items():
        if framework in html_content.lower():
            design_score += points
            break  # Only count one framework
    
    # Modern web technologies
    if 'flexbox' in html_content.lower() or 'flex:' in html_content.lower():
        design_score += 5
    if 'grid' in html_content.lower() and 'display' in html_content.lower():
        design_score += 5
    if '@media' in html_content.lower():
        design_score += 10
    
    design_score = min(60, design_score)
    
    # Accessibility score
    accessibility_score = 0.0
    
    # Alt tags for images
    images = soup.find_all('img')
    if images:
        images_with_alt = [img for img in images if img.get('alt', '').strip()]
        accessibility_score += (len(images_with_alt) / len(images)) * 20
    
    # Form labels and ARIA
    forms = soup.find_all('form')
    if forms:
        labels = soup.find_all('label')
        if labels:
            accessibility_score += 10
    
    # ARIA attributes
    aria_elements = soup.find_all(attrs={"role": True})
    if aria_elements:
        accessibility_score += 10
    
    # Language attribute
    if soup.find('html', lang=True):
        accessibility_score += 5
    
    # Skip navigation links
    skip_links = soup.find_all('a', href=re.compile('#main|#content|#skip', re.I))
    if skip_links:
        accessibility_score += 5
    
    accessibility_score = min(50, accessibility_score)
    
    # Mobile UX score
    mobile_score = 0.0
    
    # Viewport meta tag
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if viewport:
        viewport_content = viewport.get('content', '')
        if 'width=device-width' in viewport_content:
            mobile_score += 20
        if 'initial-scale=1' in viewport_content:
            mobile_score += 10
    
    # Responsive indicators
    if '@media' in html_content.lower():
        mobile_score += 15
    if 'responsive' in html_content.lower():
        mobile_score += 5
    
    # Touch-friendly elements
    if 'touch' in html_content.lower() or 'swipe' in html_content.lower():
        mobile_score += 5
    
    # Mobile-specific meta tags
    if soup.find('meta', attrs={'name': 'apple-mobile-web-app-capable'}):
        mobile_score += 5
    
    mobile_score = min(60, mobile_score)
    
    # Overall UX calculation
    overall_ux = (nav_score + design_score + accessibility_score + mobile_score) / 4
    
    return UXAnalysis(
        navigation_score=int(round(nav_score)),
        visual_design_score=int(round(design_score)),
        accessibility_score=int(round(accessibility_score)),
        mobile_ux_score=int(round(mobile_score)),
        overall_ux_score=int(round(overall_ux))
    )

async def analyze_social_media_presence(url: str, html_content: str) -> SocialMediaAnalysis:
    """Analyze social media presence and links"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    platforms = []
    social_links = {}
    
    # Enhanced social media detection
    social_patterns = {
        'facebook': r'facebook\.com/[^/\s"\']+',
        'twitter': r'(twitter\.com|x\.com)/[^/\s"\']+',
        'instagram': r'instagram\.com/[^/\s"\']+',
        'linkedin': r'linkedin\.com/(company|in)/[^/\s"\']+',
        'youtube': r'youtube\.com/(channel|user|c|@)[^/\s"\']+',
        'tiktok': r'tiktok\.com/@[^/\s"\']+',
        'pinterest': r'pinterest\.(com|fi)/[^/\s"\']+',
        'snapchat': r'snapchat\.com/add/[^/\s"\']+',
    }
    
    for platform, pattern in social_patterns.items():
        matches = re.findall(pattern, html_content, re.I)
        if matches:
            platforms.append(platform)
            social_links[platform] = matches[0]
    
    # Social media score (more granular)
    social_score = 0
    
    # Platform presence scoring
    platform_scores = {
        'facebook': 12,
        'instagram': 12,
        'linkedin': 10,
        'twitter': 8,
        'youtube': 10,
        'tiktok': 8,
        'pinterest': 5,
        'snapchat': 5
    }
    
    for platform in platforms:
        social_score += platform_scores.get(platform, 5)
    
    # Check for social sharing buttons
    share_indicators = [
        'share', 'social', 'facebook-share', 'twitter-share',
        'linkedin-share', 'whatsapp-share'
    ]
    
    for indicator in share_indicators:
        if indicator in html_content.lower():
            social_score += 2
            break
    
    # Open Graph tags (indicates social optimization)
    og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
    if og_tags:
        social_score += min(len(og_tags) * 2, 10)
    
    # Twitter Cards
    twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
    if twitter_tags:
        social_score += 5
    
    social_score = min(100, social_score)
    
    return SocialMediaAnalysis(
        platforms=platforms,
        total_followers=0,  # Would need API access
        engagement_rate=0.0,  # Would need API access
        posting_frequency="unknown",  # Would need API access
        social_score=int(round(social_score))
    )

# ============ AI ANALYSIS FUNCTIONS (Keep same as before) ============

async def generate_ai_insights(url: str, basic_metrics: Dict[str, Any], 
                             technical: TechnicalAudit, content: ContentAnalysis, 
                             ux: UXAnalysis, social: SocialMediaAnalysis, 
                             language: str = "fi") -> AIAnalysis:
    """Generate comprehensive AI-powered insights"""
    
    # Calculate overall scores for context
    overall_score = basic_metrics.get('digital_maturity_score', 0)
    
    # Default insights based on scores and analysis
    insights = generate_rule_based_insights(
        overall_score, basic_metrics, technical, content, ux, social, language
    )
    
    # If OpenAI is available, enhance with GPT analysis
    if openai_client:
        try:
            enhanced_insights = await generate_openai_insights(
                url, basic_metrics, technical, content, ux, social, language
            )
            # Merge insights
            insights.update(enhanced_insights)
        except Exception as e:
            logger.warning(f"OpenAI analysis failed: {str(e)}")
    
    return AIAnalysis(**insights)

def generate_rule_based_insights(overall_score: int, basic_metrics: Dict[str, Any],
                                technical: TechnicalAudit, content: ContentAnalysis,
                                ux: UXAnalysis, social: SocialMediaAnalysis,
                                language: str) -> Dict[str, Any]:
    """Generate insights using rule-based logic"""
    
    if language == "fi":
        return generate_finnish_insights(overall_score, basic_metrics, technical, content, ux, social)
    else:
        return generate_english_insights(overall_score, basic_metrics, technical, content, ux, social)

def generate_finnish_insights(overall_score: int, basic_metrics: Dict[str, Any],
                            technical: TechnicalAudit, content: ContentAnalysis,
                            ux: UXAnalysis, social: SocialMediaAnalysis) -> Dict[str, Any]:
    """Generate Finnish language insights with comprehensive summary"""
    
    vahvuudet = []
    heikkoudet = []
    mahdollisuudet = []
    uhat = []
    toimenpidesuositukset = []
    quick_wins = []
    
    # Analyze strengths based on actual scores
    if technical.has_ssl:
        vahvuudet.append("HTTPS-suojaus käytössä, mikä parantaa turvallisuutta ja SEO-sijoitusta")
    
    if technical.has_mobile_optimization:
        vahvuudet.append("Mobiilioptiminti toteutettu, mikä palvelee mobiiliyrittäjiä")
    
    if content.word_count > 1000:
        vahvuudet.append(f"Runsaasti sisältöä ({content.word_count} sanaa), mikä tukee SEO-tavoitteita")
    
    if social.social_score > 40:
        vahvuudet.append("Erinomainen sosiaalisen median läsnäolo eri alustoilla")
    elif social.social_score > 20:
        vahvuudet.append("Hyvä sosiaalisen median läsnäolo")
    
    if ux.overall_ux_score > 60:
        vahvuudet.append("Käyttökokemus on kilpailukykyinen")
    
    # Analyze weaknesses
    if not technical.has_analytics:
        heikkoudet.append("Analytiikkatyökalut puuttuvat - vaikea mitata sivuston suorituskykyä")
        quick_wins.append("Asenna Google Analytics seurantaa varten")
    
    if content.word_count < 500:
        heikkoudet.append("Vähän sisältöä, mikä voi haitata hakukoneoptimointia")
        toimenpidesuositukset.append("Tuota enemmän laadukasta sisältöä säännöllisesti")
    
    if social.social_score < 20:
        heikkoudet.append("Heikko sosiaalisen median läsnäolo")
        mahdollisuudet.append("Paranna sosiaalisen median strategiaa ja aktiivisuutta")
    
    if ux.accessibility_score < 40:
        heikkoudet.append("Saavutettavuuspuutteita, jotka voivat sulkea käyttäjiä pois")
        toimenpidesuositukset.append("Paranna saavutettavuutta alt-teksteillä ja selkeämmällä navigoinnilla")
    
    # Opportunities based on actual score
    if overall_score < 40:
        mahdollisuudet.extend([
            "Merkittävä potentiaali parantaa digitaalista läsnäoloa",
            "Kilpailijaetu saavutettavissa nopeilla parannuksilla",
            "SEO-optimointi voi tuoda lisää orgaanista liikennettä"
        ])
    elif overall_score < 60:
        mahdollisuudet.extend([
            "Kohtuullinen pohja, josta rakentaa vahvempi digitaalinen läsnäolo",
            "Sisältömarkkinointi voi nostaa asiantuntija-asemaa",
            "Teknisillä parannuksilla voidaan parantaa käyttäjäkokemusta"
        ])
    elif overall_score < 80:
        mahdollisuudet.extend([
            "Hyvä pohja digitaalisen markkinoinnin tehostamiseen",
            "Mahdollisuus nousta alan johtavaksi toimijaksi",
            "Datan hyödyntäminen asiakaskokemuksen parantamiseen"
        ])
    else:
        mahdollisuudet.extend([
            "Vahva digitaalinen perusta - keskity innovaatioon",
            "Mahdollisuus toimia alan digitaalisena edelläkävijänä",
            "AI ja automaation hyödyntäminen kilpailuedun kasvattamiseen"
        ])
    
    # Threats
    if not technical.has_ssl:
        uhat.append("Turvallisuuspuutteet voivat vaikuttaa luottamukseen ja SEO-sijoitukseen")
    
    if overall_score < 40:
        uhat.append("Riski jäädä kilpailijoista jälkeen digitaalisen markkinoinnin osalta")
    
    if social.social_score < 15:
        uhat.append("Kilpailijat voivat kaapata asiakkaita paremmalla sosiaalisen median läsnäololla")
    
    # Generate comprehensive summary
    summary_parts = []
    
    # Digital maturity assessment with more granular levels
    if overall_score >= 80:
        summary_parts.append(f"Yrityksen digitaalinen kypsyys on erinomaisella tasolla ({overall_score}/100), mikä asettaa sen alan kärkijoukkoon.")
    elif overall_score >= 60:
        summary_parts.append(f"Yrityksen digitaalinen kypsyys on hyvällä tasolla ({overall_score}/100) ja tarjoaa vahvan pohjan jatkokehitykselle.")
    elif overall_score >= 40:
        summary_parts.append(f"Yrityksen digitaalinen kypsyys on keskitasoa ({overall_score}/100) ja kaipaa kohennettuja parannuksia.")
    else:
        summary_parts.append(f"Yrityksen digitaalinen kypsyys ({overall_score}/100) jää merkittävästi alan standardeista.")
    
    # Technical analysis
    if technical.has_ssl and technical.has_mobile_optimization:
        summary_parts.append("Tekninen toteutus on modernilla tasolla HTTPS-suojauksella ja mobiilioptiminnilla.")
    elif technical.has_ssl:
        summary_parts.append("HTTPS-suojaus on kunnossa, mutta mobiilioptimointia tulisi parantaa.")
    else:
        summary_parts.append("Tekniset perusasiat kaipaavat huomiota, erityisesti turvallisuus ja mobiilioptiminti.")
    
    # Content assessment
    if content.word_count > 1500:
        summary_parts.append(f"Sivustolla on runsaasti sisältöä ({content.word_count} sanaa), mikä tukee hakukonesijoitusta.")
    elif content.word_count > 800:
        summary_parts.append(f"Sisältömäärä ({content.word_count} sanaa) on kohtuullinen, mutta lisäsisällöstä olisi hyötyä.")
    else:
        summary_parts.append(f"Sisältömäärä ({content.word_count} sanaa) on vähäinen ja rajoittaa hakukonenäkyvyyttä.")
    
    # Social media presence
    if social.social_score > 40:
        summary_parts.append(f"Sosiaalisen median läsnäolo on erinomaista {len(social.platforms)} alustalla.")
    elif social.social_score > 20:
        summary_parts.append(f"Sosiaalisen median hyödyntäminen on kohtuullista {len(social.platforms)} alustalla.")
    else:
        summary_parts.append("Sosiaalisen median potentiaali on suurelta osin hyödyntämättä.")
    
    # UX evaluation
    if ux.overall_ux_score > 60:
        summary_parts.append("Käyttökokemus on kilpailukykyisellä tasolla.")
    else:
        summary_parts.append("Käyttökokemusta tulisi parantaa navigoinnin ja saavutettavuuden osalta.")
    
    # Strategic conclusion
    if overall_score >= 70:
        summary_parts.append("Yritys on vahvassa asemassa ja voi keskittyä innovatiivisiin ratkaisuihin.")
    elif overall_score >= 50:
        summary_parts.append("Kohdennetuilla parannuksilla yritys voi nousta kilpailijoita edelle.")
    else:
        summary_parts.append("Systemaattinen digitaalisen läsnäolon kehittäminen on välttämätöntä.")
    
    comprehensive_summary = " ".join(summary_parts)
    
    # Quick wins based on missing basics
    if not basic_metrics.get('meta_description'):
        quick_wins.append("Lisää meta-kuvaukset sivuille")
    
    if basic_metrics.get('h1_count', 0) == 0:
        quick_wins.append("Lisää H1-otsikot sivuille")
    
    if not technical.has_mobile_optimization:
        quick_wins.append("Lisää viewport meta-tagi mobiilioptimointia varten")
    
    return {
        'summary': comprehensive_summary,
        'strengths': vahvuudet[:4],
        'weaknesses': heikkoudet[:4],
        'opportunities': mahdollisuudet[:4], 
        'threats': uhat[:3],
        'recommendations': toimenpidesuositukset[:5],
        'confidence_score': int(min(95, max(60, overall_score + 20))),
        'sentiment_score': 0.6 if overall_score > 50 else 0.4,
        
        # Finnish versions
        'johtopäätökset': comprehensive_summary,
        'vahvuudet': vahvuudet[:4],
        'heikkoudet': heikkoudet[:4],
        'mahdollisuudet': mahdollisuudet[:4],
        'uhat': uhat[:3],
        'toimenpidesuositukset': toimenpidesuositukset[:5],
        'strategiset_suositukset': toimenpidesuositukset[:3],
        'quick_wins': quick_wins[:3]
    }

def generate_english_insights(overall_score: int, basic_metrics: Dict[str, Any],
                            technical: TechnicalAudit, content: ContentAnalysis,
                            ux: UXAnalysis, social: SocialMediaAnalysis) -> Dict[str, Any]:
    """Generate English language insights with comprehensive summary"""
    
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []
    recommendations = []
    quick_wins = []
    
    # Similar logic as Finnish but in English
    # [Keep the same structure as generate_finnish_insights but with English text]
    
    # Analyze strengths
    if technical.has_ssl:
        strengths.append("HTTPS security implemented, improving trust and SEO ranking")
    
    if technical.has_mobile_optimization:
        strengths.append("Mobile optimization in place, serving mobile users effectively")
    
    if content.word_count > 1000:
        strengths.append(f"Rich content ({content.word_count} words) supporting SEO goals")
    
    if social.social_score > 40:
        strengths.append("Excellent social media presence across platforms")
    elif social.social_score > 20:
        strengths.append("Good social media presence")
    
    if ux.overall_ux_score > 60:
        strengths.append("User experience meets competitive standards")
    
    # Analyze weaknesses
    if not technical.has_analytics:
        weaknesses.append("Missing analytics tools - difficult to measure performance")
        quick_wins.append("Install Google Analytics for tracking")
    
    if content.word_count < 500:
        weaknesses.append("Limited content may hurt search engine optimization")
        recommendations.append("Create more quality content regularly")
    
    if social.social_score < 20:
        weaknesses.append("Weak social media presence")
        opportunities.append("Enhance social media strategy and activity")
    
    if ux.accessibility_score < 40:
        weaknesses.append("Accessibility issues may exclude users")
        recommendations.append("Improve accessibility with alt texts and clearer navigation")
    
    # Opportunities based on score
    if overall_score < 40:
        opportunities.extend([
            "Significant potential to improve digital presence",
            "Competitive advantage achievable through quick improvements",
            "SEO optimization can drive more organic traffic"
        ])
    elif overall_score < 60:
        opportunities.extend([
            "Moderate foundation to build stronger digital presence",
            "Content marketing can boost thought leadership",
            "Technical improvements can enhance user experience"
        ])
    elif overall_score < 80:
        opportunities.extend([
            "Strong foundation for enhanced digital marketing",
            "Opportunity to become industry leader",
            "Data utilization for improved customer experience"
        ])
    else:
        opportunities.extend([
            "Strong digital foundation - focus on innovation",
            "Opportunity to be digital pioneer in the industry",
            "AI and automation for competitive advantage"
        ])
    
    # Threats
    if not technical.has_ssl:
        threats.append("Security gaps may affect trust and SEO ranking")
    
    if overall_score < 40:
        threats.append("Risk of falling behind competitors in digital marketing")
    
    if social.social_score < 15:
        threats.append("Competitors may capture customers with better social media presence")
    
    # Generate comprehensive summary
    summary_parts = []
    
    # Digital maturity assessment
    if overall_score >= 80:
        summary_parts.append(f"The company's digital maturity is at an excellent level ({overall_score}/100), positioning it among industry leaders.")
    elif overall_score >= 60:
        summary_parts.append(f"The company's digital maturity is at a good level ({overall_score}/100) and provides a solid foundation for growth.")
    elif overall_score >= 40:
        summary_parts.append(f"The company's digital maturity is average ({overall_score}/100) and needs targeted improvements.")
    else:
        summary_parts.append(f"The company's digital maturity ({overall_score}/100) falls significantly below industry standards.")
    
    # Technical analysis
    if technical.has_ssl and technical.has_mobile_optimization:
        summary_parts.append("Technical implementation is modern with HTTPS security and mobile optimization in place.")
    elif technical.has_ssl:
        summary_parts.append("HTTPS security is properly implemented, but mobile optimization needs attention.")
    else:
        summary_parts.append("Technical fundamentals require attention, particularly security and mobile optimization.")
    
    # Content assessment
    if content.word_count > 1500:
        summary_parts.append(f"The website features substantial content ({content.word_count} words), supporting SEO efforts.")
    elif content.word_count > 800:
        summary_parts.append(f"Content volume ({content.word_count} words) is reasonable but could benefit from expansion.")
    else:
        summary_parts.append(f"Content volume ({content.word_count} words) is limited and restricts search visibility.")
    
    # Social media presence
    if social.social_score > 40:
        summary_parts.append(f"Social media presence is excellent across {len(social.platforms)} platforms.")
    elif social.social_score > 20:
        summary_parts.append(f"Social media utilization is moderate across {len(social.platforms)} platforms.")
    else:
        summary_parts.append("Social media potential is largely untapped.")
    
    # UX evaluation
    if ux.overall_ux_score > 60:
        summary_parts.append("User experience is competitive.")
    else:
        summary_parts.append("User experience should be improved in navigation and accessibility.")
    
    # Strategic conclusion
    if overall_score >= 70:
        summary_parts.append("The company is well-positioned and can focus on innovative solutions.")
    elif overall_score >= 50:
        summary_parts.append("With targeted improvements, the company can surpass competitors.")
    else:
        summary_parts.append("Systematic development of digital presence is essential.")
    
    comprehensive_summary = " ".join(summary_parts)
    
    # Quick wins
    if not basic_metrics.get('meta_description'):
        quick_wins.append("Add meta descriptions to pages")
    
    if basic_metrics.get('h1_count', 0) == 0:
        quick_wins.append("Add H1 headings to pages")
    
    if not technical.has_mobile_optimization:
        quick_wins.append("Add viewport meta tag for mobile optimization")
    
    return {
        'summary': comprehensive_summary,
        'strengths': strengths[:4],
        'weaknesses': weaknesses[:4], 
        'opportunities': opportunities[:4],
        'threats': threats[:3],
        'recommendations': recommendations[:5],
        'confidence_score': int(min(95, max(60, overall_score + 20))),
        'sentiment_score': 0.6 if overall_score > 50 else 0.4,
        
        # Finnish versions for compatibility
        'johtopäätökset': comprehensive_summary,
        'vahvuudet': strengths[:4],
        'heikkoudet': weaknesses[:4],
        'mahdollisuudet': opportunities[:4],
        'uhat': threats[:3],
        'toimenpidesuositukset': recommendations[:5],
        'strategiset_suositukset': recommendations[:3],
        'quick_wins': quick_wins[:3]
    }

async def generate_openai_insights(url: str, basic_metrics: Dict[str, Any],
                                 technical: TechnicalAudit, content: ContentAnalysis,
                                 ux: UXAnalysis, social: SocialMediaAnalysis,
                                 language: str) -> Dict[str, Any]:
    """Generate enhanced insights using OpenAI GPT"""
    
    if not openai_client:
        return {}
    
    # Prepare context for GPT
    context = f"""
    Website: {url}
    Digital Maturity Score: {basic_metrics.get('digital_maturity_score', 0)}/100
    Technical Score: {technical.page_speed_score}/100
    Content Words: {content.word_count}
    Social Platforms: {len(social.platforms)}
    UX Score: {ux.overall_ux_score}/100
    """
    
    try:
        if language == "fi":
            prompt = f"""Analysoi tämä verkkosivu ja anna strategisia suosituksia:
            
            {context}
            
            Anna:
            1. Lyhyt yhteenveto (max 200 sanaa)
            2. 3 tärkeintä strategista suositusta
            3. 2 nopeaa voittoa (quick wins)
            
            Vastaa suomeksi ja ole käytännönläheinen."""
        else:
            prompt = f"""Analyze this website and provide strategic recommendations:
            
            {context}
            
            Provide:
            1. Brief summary (max 200 words)
            2. 3 key strategic recommendations  
            3. 2 quick wins
            
            Be practical and actionable."""
        
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Parse the response (simplified)
        lines = ai_response.split('\n')
        summary_lines = [line for line in lines if line.strip() and not line.startswith(('1.', '2.', '3.'))]
        enhanced_summary = ' '.join(summary_lines[:3]) if summary_lines else ""
        
        return {
            'enhanced_summary': enhanced_summary,
            'ai_confidence': 85
        }
        
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return {}

async def analyze_competitive_positioning(url: str, basic_metrics: Dict[str, Any]) -> CompetitiveAnalysis:
    """Analyze competitive positioning based on metrics"""
    
    score = basic_metrics.get('digital_maturity_score', 0)
    
    # More granular positioning
    if score >= 85:
        position = "Market Leader"
        advantages = ["Industry-leading digital presence", "Advanced technical implementation", "Superior user experience"]
        threats = ["Maintaining competitive edge", "Emerging disruptors"]
    elif score >= 70:
        position = "Strong Challenger"
        advantages = ["Solid digital foundation", "Strong growth potential", "Competitive features"]
        threats = ["Gap to market leaders", "Need for continuous innovation"]
    elif score >= 55:
        position = "Average Performer"
        advantages = ["Established presence", "Room for improvement", "Quick wins available"]
        threats = ["Risk of falling behind", "Competitive pressure"]
    elif score >= 40:
        position = "Underperformer"
        advantages = ["Significant improvement potential", "Low-hanging fruit opportunities"]
        threats = ["Competitive disadvantage", "Customer churn risk"]
    else:
        position = "Laggard"
        advantages = ["Opportunity for transformation"]
        threats = ["Major competitive disadvantage", "Risk of market irrelevance"]
    
    competitive_score = int(min(100, score + 10))
    
    return CompetitiveAnalysis(
        market_position=position,
        competitive_advantages=advantages,
        competitive_threats=threats,
        market_share_estimate="Unknown",
        competitive_score=competitive_score
    )

# ============ API ENDPOINTS (Keep mostly the same) ============

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "basic_analysis": "/api/v1/analyze",
            "ai_analysis": "/api/v1/ai-analyze", 
            "pdf_generation": "/api/v1/generate-pdf-base64"
        },
        "features": [
            "Website analysis with enhanced scoring",
            "AI-powered insights", 
            "Social media analysis",
            "UX evaluation",
            "Competitive positioning",
            "PDF report generation"
        ],
        "changelog": "v4.6.0 - Improved scoring system for better differentiation"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "openai_available": bool(openai_client),
        "cache_size": len(analysis_cache)
    }

@app.post("/api/v1/ai-analyze")
async def ai_analyze(request: CompetitorAnalysisRequest):
    """Main AI-powered analysis endpoint with enhanced scoring"""
    try:
        # Validate URL
        if not request.url.startswith(('http://', 'https://')):
            request.url = f"https://{request.url}"
        
        # Check cache
        cache_key = get_cache_key(request.url, "ai_comprehensive")
        if cache_key in analysis_cache:
            cached_result = analysis_cache[cache_key]
            if is_cache_valid(cached_result['timestamp']):
                logger.info(f"Returning cached analysis for {request.url}")
                return cached_result['data']
        
        # Fetch website content
        response = await fetch_url(request.url)
        if not response or response.status_code != 200:
            raise HTTPException(
                status_code=400, 
                detail=f"Could not fetch website: {request.url}"
            )
        
        html_content = response.text
        
        # Perform all analyses with enhanced scoring
        basic_metrics = await analyze_basic_metrics(request.url, html_content)
        technical_audit = await analyze_technical_aspects(request.url, html_content)
        content_analysis = await analyze_content_quality(html_content)
        ux_analysis = await analyze_ux_elements(html_content)
        social_analysis = await analyze_social_media_presence(request.url, html_content)
        competitive_analysis = await analyze_competitive_positioning(request.url, basic_metrics)
        
        # Generate AI insights
        ai_analysis = await generate_ai_insights(
            request.url, basic_metrics, technical_audit, content_analysis,
            ux_analysis, social_analysis, request.language
        )
        
        # Build comprehensive response
        result = {
            "success": True,
            "company_name": request.company_name or basic_metrics.get('title', 'Unknown'),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": BasicAnalysis(
                company=request.company_name or basic_metrics.get('title', 'Unknown'),
                website=request.url,
                industry=None,
                digital_maturity_score=basic_metrics['digital_maturity_score'],
                social_platforms=basic_metrics['social_platforms'],
                technical_score=technical_audit.page_speed_score,
                content_score=content_analysis.content_quality_score,
                seo_score=int(round((basic_metrics['digital_maturity_score'] + content_analysis.content_quality_score) / 2))
            ).dict(),
            "ai_analysis": ai_analysis.dict(),
            "detailed_analysis": DetailedAnalysis(
                social_media=social_analysis,
                technical_audit=technical_audit,
                content_analysis=content_analysis,
                ux_analysis=ux_analysis,
                competitive_analysis=competitive_analysis
            ).dict(),
            "smart": {
                "actions": generate_smart_actions(ai_analysis, technical_audit, content_analysis),
                "scores": SmartScores(
                    overall=basic_metrics['digital_maturity_score'],
                    technical=technical_audit.page_speed_score,
                    content=content_analysis.content_quality_score,
                    social=social_analysis.social_score,
                    ux=ux_analysis.overall_ux_score,
                    competitive=competitive_analysis.competitive_score
                ).dict()
            },
            "enhanced_features": EnhancedFeatures(
                industry_benchmarking={
                    "industry_average": 55,  # Updated to be more realistic
                    "top_quartile": 75,
                    "your_position": basic_metrics['digital_maturity_score']
                },
                competitor_gaps=generate_competitor_gaps(basic_metrics, competitive_analysis),
                growth_opportunities=ai_analysis.opportunities[:3],
                risk_assessment=ai_analysis.threats[:2]
            ).dict()
        }
        
        # Ensure all scores are integers
        result = ensure_integer_scores(result)
        
        # Cache the result
        analysis_cache[cache_key] = {
            'data': result,
            'timestamp': datetime.now()
        }
        
        # Clean old cache entries
        if len(analysis_cache) > 50:
            oldest_key = min(analysis_cache.keys(), 
                           key=lambda k: analysis_cache[k]['timestamp'])
            del analysis_cache[oldest_key]
        
        logger.info(f"Completed AI analysis for {request.url} with score {basic_metrics['digital_maturity_score']}")
        return result
        
    except Exception as e:
        logger.error(f"AI analysis error for {request.url}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Analyysi epäonnistui: {str(e)}"
        )

@app.post("/api/v1/analyze")
async def basic_analyze(request: CompetitorAnalysisRequest):
    """Basic analysis endpoint for backward compatibility"""
    try:
        # Validate URL
        if not request.url.startswith(('http://', 'https://')):
            request.url = f"https://{request.url}"
        
        # Fetch website
        response = await fetch_url(request.url)
        if not response or response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch website")
        
        # Basic analysis with enhanced scoring
        basic_metrics = await analyze_basic_metrics(request.url, response.text)
        
        result = {
            "success": True,
            "company": request.company_name or "Unknown",
            "website": request.url,
            "industry": None,
            "digital_maturity_score": basic_metrics['digital_maturity_score'],
            "social_platforms": basic_metrics['social_platforms'],
            "analysis_date": datetime.now().isoformat(),
            "detailed_scores": basic_metrics.get('detailed_scores', {})
        }
        
        # Ensure integers
        result = ensure_integer_scores(result)
        
        return result
        
    except Exception as e:
        logger.error(f"Basic analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_report(request: PDFRequest):
   """Generate PDF report and return as base64"""
   try:
       # Generate PDF in memory
       buffer = BytesIO()
       
       # Create PDF document
       doc = SimpleDocTemplate(
           buffer,
           pagesize=A4,
           rightMargin=2*cm,
           leftMargin=2*cm,
           topMargin=2*cm,
           bottomMargin=2*cm
       )
       
       # Styles
       styles = getSampleStyleSheet()
       title_style = ParagraphStyle(
           'CustomTitle',
           parent=styles['Heading1'],
           fontSize=24,
           textColor=colors.HexColor('#1f2937'),
           alignment=TA_CENTER,
           spaceAfter=30
       )
       
       heading_style = ParagraphStyle(
           'CustomHeading',
           parent=styles['Heading2'],
           fontSize=16,
           textColor=colors.HexColor('#374151'),
           spaceBefore=20,
           spaceAfter=10
       )
       
       normal_style = ParagraphStyle(
           'CustomNormal',
           parent=styles['Normal'],
           fontSize=11,
           textColor=colors.HexColor('#4b5563'),
           alignment=TA_JUSTIFY,
           spaceAfter=12
       )
       
       # Build story
       story = []
       
       # Title
       if request.language == "fi":
           title_text = f"Kilpailija-analyysi: {request.company_name}"
           date_text = f"Analysoitu: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
       else:
           title_text = f"Competitive Analysis: {request.company_name}"
           date_text = f"Analyzed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
           
       story.append(Paragraph(title_text, title_style))
       story.append(Paragraph(date_text, normal_style))
       story.append(Spacer(1, 20))
       
       # Basic info
       basic_info = request.basic_analysis
       if request.language == "fi":
           story.append(Paragraph("Yhteenveto", heading_style))
           summary_text = f"""
           Verkkosivusto: {request.url}<br/>
           Digitaalinen kypsyys: {basic_info.get('digital_maturity_score', 0)}/100<br/>
           Sosiaalisen median alustat: {basic_info.get('social_platforms', 0)}<br/>
           Analyysin ajankohta: {request.timestamp}
           """
       else:
           story.append(Paragraph("Summary", heading_style))
           summary_text = f"""
           Website: {request.url}<br/>
           Digital Maturity: {basic_info.get('digital_maturity_score', 0)}/100<br/>
           Social Platforms: {basic_info.get('social_platforms', 0)}<br/>
           Analysis Date: {request.timestamp}
           """
       
       story.append(Paragraph(summary_text, normal_style))
       story.append(Spacer(1, 20))
       
       # AI Analysis
       ai_analysis = request.ai_analysis
       if ai_analysis:
           if request.language == "fi":
               story.append(Paragraph("AI-analyysin tulokset", heading_style))
               
               if ai_analysis.get('johtopäätökset'):
                   story.append(Paragraph("Johtopäätökset", heading_style))
                   story.append(Paragraph(ai_analysis['johtopäätökset'], normal_style))
               
               # SWOT sections
               swot_sections = [
                   ('vahvuudet', 'Vahvuudet'),
                   ('heikkoudet', 'Heikkoudet'), 
                   ('mahdollisuudet', 'Mahdollisuudet'),
                   ('uhat', 'Uhat')
               ]
           else:
               story.append(Paragraph("AI Analysis Results", heading_style))
               
               if ai_analysis.get('summary'):
                   story.append(Paragraph("Summary", heading_style))
                   story.append(Paragraph(ai_analysis['summary'], normal_style))
               
               # SWOT sections
               swot_sections = [
                   ('strengths', 'Strengths'),
                   ('weaknesses', 'Weaknesses'),
                   ('opportunities', 'Opportunities'), 
                   ('threats', 'Threats')
               ]
           
           for key, title in swot_sections:
               items = ai_analysis.get(key, [])
               if items:
                   story.append(Paragraph(title, heading_style))
                   for item in items[:3]:  # Limit to 3 items
                       story.append(Paragraph(f"• {item}", normal_style))
           
           # Recommendations
           recommendations = ai_analysis.get('toimenpidesuositukset' if request.language == 'fi' else 'recommendations', [])
           if recommendations:
               rec_title = "Toimenpidesuositukset" if request.language == 'fi' else "Recommendations"
               story.append(Paragraph(rec_title, heading_style))
               for rec in recommendations[:5]:  # Limit to 5
                   story.append(Paragraph(f"• {rec}", normal_style))
       
       # Build PDF
       doc.build(story)
       
       # Get PDF data
       pdf_data = buffer.getvalue()
       buffer.close()
       
       # Convert to base64
       pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
       
       # Generate filename
       safe_company = re.sub(r'[^\w\-_\.]', '_', request.company_name)
       filename = f"analyysi_{safe_company}_{datetime.now().strftime('%Y%m%d')}.pdf"
       
       return {
           "success": True,
           "pdf_base64": pdf_base64,
           "filename": filename,
           "size_bytes": len(pdf_data)
       }
       
   except Exception as e:
       logger.error(f"PDF generation error: {str(e)}")
       raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# ============ HELPER FUNCTIONS FOR ENDPOINTS ============

def generate_smart_actions(ai_analysis: AIAnalysis, technical: TechnicalAudit, 
                         content: ContentAnalysis) -> List[Dict[str, Any]]:
   """Generate smart action recommendations"""
   actions = []
   
   # Priority actions based on analysis
   if not technical.has_analytics:
       actions.append({
           "title": "Asenna analytiikka",
           "description": "Lisää Google Analytics seurantaa varten",
           "priority": "high",
           "effort": "low",
           "impact": "high"
       })
   
   if content.word_count < 500:
       actions.append({
           "title": "Lisää sisältöä",
           "description": "Tuota enemmän laadukasta sisältöä säännöllisesti",
           "priority": "medium", 
           "effort": "high",
           "impact": "high"
       })
   
   if technical.meta_tags_score < 5:
       actions.append({
           "title": "Optimoi meta-tagit",
           "description": "Lisää title ja description -tagit kaikille sivuille",
           "priority": "high",
           "effort": "low", 
           "impact": "medium"
       })
   
   if not technical.has_mobile_optimization:
       actions.append({
           "title": "Mobiilioptiminti",
           "description": "Lisää viewport meta-tagi ja responsiivinen suunnittelu",
           "priority": "high",
           "effort": "medium",
           "impact": "high"
       })
   
   return actions[:5]  # Limit to 5 actions

def generate_competitor_gaps(basic_metrics: Dict[str, Any], 
                          competitive: CompetitiveAnalysis) -> List[str]:
   """Generate competitor gap analysis"""
   gaps = []
   score = basic_metrics.get('digital_maturity_score', 0)
   
   if score < 40:
       gaps.extend([
           "Digitaalinen läsnäolo merkittävästi kilpailijoita heikompi",
           "SEO-optimointi jää kilpailijoista jälkeen",
           "Sosiaalisen median hyödyntäminen vajavaista"
       ])
   elif score < 60:
       gaps.extend([
           "Tekninen toteutus kaipaa parannusta kilpailijoihin nähden",
           "Sisältöstrategia voisi olla vahvempi",
           "Käyttäjäkokemus jää kilpailijoiden tasosta"
       ])
   elif score < 75:
       gaps.extend([
           "Pieniä eroja kilpailijoihin teknisessä toteutuksessa",
           "Mahdollisuus erottua sisältöstrategialla"
       ])
   
   return gaps[:3]

# ============ ADDITIONAL HELPER ENDPOINTS ============

@app.get("/api/v1/test-openai")
async def test_openai():
   """Test OpenAI connection"""
   if not openai_client:
       return {"available": False, "reason": "No API key or library not installed"}
   
   try:
       response = await openai_client.chat.completions.create(
           model="gpt-3.5-turbo",
           messages=[{"role": "user", "content": "Test"}],
           max_tokens=10
       )
       return {"available": True, "status": "working"}
   except Exception as e:
       return {"available": False, "error": str(e)}

@app.get("/api/v1/cache-stats")
async def get_cache_stats():
   """Get cache statistics"""
   return {
       "cache_size": len(analysis_cache),
       "cache_entries": list(analysis_cache.keys())[:10],  # Show first 10
       "cache_ttl_seconds": CACHE_TTL
   }

@app.post("/api/v1/clear-cache")
async def clear_cache():
   """Clear analysis cache"""
   global analysis_cache
   cache_size = len(analysis_cache)
   analysis_cache = {}
   return {
       "success": True,
       "cleared_entries": cache_size,
       "message": f"Cleared {cache_size} cache entries"
   }

# ============ ERROR HANDLERS ============

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
   """Custom 404 handler"""
   return JSONResponse(
       status_code=404,
       content={
           "error": "Endpoint not found",
           "available_endpoints": [
               "/",
               "/health", 
               "/api/v1/ai-analyze",
               "/api/v1/analyze",
               "/api/v1/generate-pdf-base64"
           ]
       }
   )

@app.exception_handler(500) 
async def internal_error_handler(request: Request, exc):
   """Custom 500 handler"""
   logger.error(f"Internal server error: {str(exc)}")
   return JSONResponse(
       status_code=500,
       content={
           "error": "Internal server error",
           "message": "An unexpected error occurred. Please try again."
       }
   )

# ============ STARTUP AND SHUTDOWN EVENTS ============

@app.on_event("startup")
async def startup_event():
   """Initialize application on startup"""
   logger.info(f"Starting Brandista Competitive Intelligence API v{APP_VERSION}")
   logger.info(f"OpenAI available: {bool(openai_client)}")
   logger.info("API ready with enhanced scoring system")

@app.on_event("shutdown")
async def shutdown_event():
   """Cleanup on shutdown"""
   logger.info("Shutting down Brandista API")
   global analysis_cache
   analysis_cache = {}
   logger.info("Cleanup completed")

# ============ MAIN SERVER CONFIGURATION ============

if __name__ == "__main__":
   import uvicorn
   
   # Configuration
   port = int(os.getenv("PORT", 8000))
   host = "0.0.0.0"  # Railway requires binding to 0.0.0.0
   
   logger.info(f"Brandista Competitive Intelligence API v{APP_VERSION}")
   logger.info(f"Starting server on {host}:{port}")
   logger.info(f"OpenAI integration: {'Enabled' if openai_client else 'Disabled'}")
   
   # Development vs Production settings
   if os.getenv("RAILWAY_ENVIRONMENT"):
       # Production on Railway
       logger.info("Running in Railway production environment")
       uvicorn.run(
           app,
           host=host,
           port=port,
           log_level="info",
           access_log=True
       )
   else:
       # Local development
       logger.info("Running in local development environment")
       uvicorn.run(
           "main:app",  # Module:app for auto-reload
           host=host,
           port=port,
           reload=True,
           log_level="debug",
           access_log=True
       )
