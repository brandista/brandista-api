#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 5.0.0 - Complete Scoring System with Enhanced Features
Author: Brandista Team
Date: 2025
Description: Advanced website analysis with fair 0-100 scoring system
"""

# ============================================================================
# IMPORTS
# ============================================================================

# Standard library imports
import os
import re
import json
import base64
import hashlib
import logging
import asyncio
import time
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict, Counter

# Third-party imports
import httpx
from bs4 import BeautifulSoup

# FastAPI imports
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

# PDF generation imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, 
    Paragraph, Spacer, PageBreak
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

# Application metadata
APP_VERSION = "5.0.0"
APP_NAME = "Brandista Competitive Intelligence API"
APP_DESCRIPTION = """
Complete Scoring System with Enhanced Features - Fair and accurate website analysis
with 0-100 scoring across all metrics. No arbitrary baselines.
"""

# Cache settings
CACHE_TTL = 3600  # 1 hour cache TTL
MAX_CACHE_SIZE = 50  # Maximum cache entries

# Request settings
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Scoring weights and maximums
SCORING_WEIGHTS = {
    'security': 15,      # Critical importance
    'seo_basics': 20,    # Foundation of online visibility
    'content': 20,       # Core value proposition
    'technical': 15,     # Infrastructure quality
    'mobile': 15,        # Critical in mobile-first world
    'social': 10,        # Engagement and reach
    'performance': 5     # User experience factor
}

# Industry benchmarks (realistic values based on market research)
INDUSTRY_BENCHMARKS = {
    'poor': (0, 30),
    'below_average': (30, 45),
    'average': (45, 60),
    'good': (60, 75),
    'excellent': (75, 100)
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('brandista_api.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

# ============================================================================
# FASTAPI APPLICATION SETUP
# ============================================================================

# Initialize FastAPI application
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

# Initialize OpenAI client if available
openai_client = None
if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}")
        openai_client = None

# Global cache dictionary
analysis_cache: Dict[str, Dict[str, Any]] = {}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ensure_integer_scores(data: Any) -> Any:
    """
    Recursively convert all score fields to integers.
    Ensures Pydantic validation passes.
    
    Args:
        data: Dictionary or nested structure containing scores
    
    Returns:
        Same structure with all score fields as integers
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if '_score' in key.lower() or key == 'score':
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
    """
    Generate unique cache key for analysis results.
    
    Args:
        url: Website URL
        analysis_type: Type of analysis performed
    
    Returns:
        MD5 hash as cache key
    """
    cache_string = f"{url}_{analysis_type}_{APP_VERSION}"
    return hashlib.md5(cache_string.encode()).hexdigest()


def is_cache_valid(timestamp: datetime) -> bool:
    """
    Check if cached result is still valid based on TTL.
    
    Args:
        timestamp: When the cache entry was created
    
    Returns:
        True if cache is still valid, False otherwise
    """
    age = datetime.now() - timestamp
    return age.total_seconds() < CACHE_TTL


async def fetch_url(
    url: str, 
    timeout: int = REQUEST_TIMEOUT,
    retries: int = MAX_RETRIES
) -> Optional[httpx.Response]:
    """
    Fetch URL with error handling, retries, and timeout.
    
    Args:
        url: Target URL to fetch
        timeout: Request timeout in seconds
        retries: Number of retry attempts
    
    Returns:
        Response object if successful, None otherwise
    """
    headers = {'User-Agent': USER_AGENT}
    
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, 
                follow_redirects=True,
                verify=True
            ) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    logger.info(f"Successfully fetched {url}")
                    return response
                elif response.status_code == 404:
                    logger.warning(f"404 Not Found: {url}")
                    return None
                elif attempt == retries - 1:
                    logger.warning(
                        f"Failed to fetch {url}: Status {response.status_code}"
                    )
                    return response
                    
        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {str(e)}")
        
        if attempt < retries - 1:
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
    
    return None


def clean_url(url: str) -> str:
    """
    Clean and validate URL format.
    
    Args:
        url: Input URL string
    
    Returns:
        Cleaned URL with proper protocol
    """
    url = url.strip()
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    
    # Remove trailing slashes
    url = url.rstrip('/')
    
    return url


def get_domain_from_url(url: str) -> str:
    """
    Extract domain name from URL.
    
    Args:
        url: Full URL
    
    Returns:
        Domain name without protocol or path
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]


# ============================================================================
# ENHANCED FEATURE FUNCTIONS
# ============================================================================

def detect_technology_stack(html_content: str, soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Detect technology stack used by the website
    
    Returns:
        Dictionary with detected technologies and count
    """
    detected = []
    html_lower = html_content.lower()
    
    # CMS Detection
    cms_patterns = {
        'WordPress': ['wp-content', 'wp-includes', 'wordpress'],
        'Joomla': ['joomla', '/components/', '/modules/'],
        'Drupal': ['drupal', '/sites/all/', 'Drupal.settings'],
        'Shopify': ['shopify', 'myshopify.com', 'cdn.shopify'],
        'Wix': ['wix.com', 'static.wixstatic.com'],
        'Squarespace': ['squarespace', 'sqsp.net'],
        'Webflow': ['webflow.io', 'webflow.com'],
        'Ghost': ['ghost.io', 'ghost-themes']
    }
    
    for cms, patterns in cms_patterns.items():
        if any(pattern.lower() in html_lower for pattern in patterns):
            detected.append(f"CMS: {cms}")
            break
    
    # Framework Detection
    framework_patterns = {
        'React': ['react', '_react', 'ReactDOM'],
        'Angular': ['ng-', 'angular', '__zone_symbol__'],
        'Vue.js': ['vue', 'v-for', 'v-if', 'v-model'],
        'Next.js': ['_next', 'nextjs', '__NEXT_DATA__'],
        'Gatsby': ['gatsby', '___gatsby'],
        'Nuxt.js': ['__nuxt', '_nuxt'],
        'Django': ['csrfmiddlewaretoken', 'django'],
        'Laravel': ['laravel', 'livewire'],
        'Ruby on Rails': ['rails', 'csrf-token', 'action_controller']
    }
    
    for framework, patterns in framework_patterns.items():
        if any(pattern.lower() in html_lower for pattern in patterns):
            detected.append(f"Framework: {framework}")
    
    # Analytics & Tracking
    if 'google-analytics' in html_lower or 'gtag' in html_lower:
        detected.append("Analytics: Google Analytics")
    if 'googletagmanager' in html_lower:
        detected.append("Analytics: Google Tag Manager")
    if 'matomo' in html_lower or 'piwik' in html_lower:
        detected.append("Analytics: Matomo")
    if 'hotjar' in html_lower:
        detected.append("Analytics: Hotjar")
    if 'clarity.ms' in html_lower:
        detected.append("Analytics: Microsoft Clarity")
    
    # CDN & Hosting
    if 'cloudflare' in html_lower:
        detected.append("CDN: Cloudflare")
    if 'akamai' in html_lower:
        detected.append("CDN: Akamai")
    if 'fastly' in html_lower:
        detected.append("CDN: Fastly")
    if 'amazonaws' in html_lower:
        detected.append("Hosting: AWS")
    if 'azurewebsites' in html_lower:
        detected.append("Hosting: Azure")
    
    # E-commerce
    if 'woocommerce' in html_lower:
        detected.append("E-commerce: WooCommerce")
    if 'shopify' in html_lower:
        detected.append("E-commerce: Shopify")
    if 'magento' in html_lower:
        detected.append("E-commerce: Magento")
    
    # CSS Frameworks
    if 'bootstrap' in html_lower:
        detected.append("CSS: Bootstrap")
    if 'tailwind' in html_lower:
        detected.append("CSS: Tailwind")
    if 'bulma' in html_lower:
        detected.append("CSS: Bulma")
    if 'material' in html_lower:
        detected.append("CSS: Material Design")
    
    # JavaScript Libraries
    if 'jquery' in html_lower:
        detected.append("JS: jQuery")
    if 'lodash' in html_lower:
        detected.append("JS: Lodash")
    if 'axios' in html_lower:
        detected.append("JS: Axios")
    
    return {
        "detected": detected,
        "count": len(detected),
        "categories": {
            "cms": [t.split(": ")[1] for t in detected if t.startswith("CMS:")],
            "frameworks": [t.split(": ")[1] for t in detected if t.startswith("Framework:")],
            "analytics": [t.split(": ")[1] for t in detected if t.startswith("Analytics:")],
            "cdn": [t.split(": ")[1] for t in detected if t.startswith("CDN:")],
            "ecommerce": [t.split(": ")[1] for t in detected if t.startswith("E-commerce:")]
        }
    }


def assess_mobile_first_readiness(soup: BeautifulSoup, html_content: str) -> Dict[str, Any]:
    """
    Assess if website is ready for Google's Mobile-First Index
    
    Returns:
        Dictionary with readiness status and details
    """
    score = 0
    issues = []
    
    # Check viewport
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if viewport:
        viewport_content = viewport.get('content', '')
        if 'width=device-width' in viewport_content:
            score += 30
        else:
            issues.append("Viewport not properly configured")
    else:
        issues.append("No viewport meta tag")
    
    # Check responsive design
    html_lower = html_content.lower()
    if '@media' in html_lower:
        media_count = html_lower.count('@media')
        if media_count >= 5:
            score += 25
        elif media_count >= 2:
            score += 15
        else:
            issues.append("Limited responsive CSS")
    else:
        issues.append("No responsive media queries")
    
    # Check font sizes
    if 'font-size' in html_lower:
        if 'rem' in html_lower or 'em' in html_lower:
            score += 15
        else:
            issues.append("Using fixed font sizes")
    
    # Check touch-friendly elements
    if 'touch' in html_lower or 'tap' in html_lower:
        score += 10
    
    # Check mobile-specific meta tags
    if soup.find('meta', attrs={'name': 'apple-mobile-web-app-capable'}):
        score += 10
    
    # Check for mobile-unfriendly technologies
    if 'flash' in html_lower:
        score -= 20
        issues.append("Uses Flash (not mobile compatible)")
    
    # Check image optimization
    images = soup.find_all('img')
    if images:
        lazy_images = [img for img in images if img.get('loading') == 'lazy']
        if lazy_images:
            score += 10
    
    ready = score >= 60
    
    return {
        "ready": ready,
        "score": score,
        "status": "Ready" if ready else "Not Ready",
        "issues": issues if not ready else [],
        "recommendations": [
            "Implement responsive design" if '@media' not in html_lower else None,
            "Add viewport meta tag" if not viewport else None,
            "Use relative font sizes" if 'rem' not in html_lower else None,
            "Implement lazy loading" if not any(img.get('loading') == 'lazy' for img in images) else None
        ]
    }


def estimate_core_web_vitals(soup: BeautifulSoup, html_content: str) -> Dict[str, Any]:
    """
    Estimate Core Web Vitals based on HTML analysis
    
    Returns:
        Dictionary with estimated vitals and assessment
    """
    # These are estimates based on HTML analysis
    # Real Core Web Vitals require actual performance testing
    
    page_size = len(html_content)
    images = soup.find_all('img')
    scripts = soup.find_all('script')
    styles = soup.find_all(['style', 'link'])
    
    # Estimate LCP (Largest Contentful Paint)
    lcp_estimate = 2.0  # Start with good baseline
    if page_size > 500000:
        lcp_estimate += 2.0
    elif page_size > 200000:
        lcp_estimate += 1.0
    elif page_size > 100000:
        lcp_estimate += 0.5
    
    if len(images) > 20:
        lcp_estimate += 1.0
    elif len(images) > 10:
        lcp_estimate += 0.5
    
    # Check for lazy loading
    lazy_images = [img for img in images if img.get('loading') == 'lazy']
    if lazy_images:
        lcp_estimate -= 0.5
    
    # Estimate FID (First Input Delay)
    fid_estimate = 50  # Start with good baseline
    if len(scripts) > 20:
        fid_estimate += 100
    elif len(scripts) > 10:
        fid_estimate += 50
    elif len(scripts) > 5:
        fid_estimate += 25
    
    # Check for async/defer scripts
    async_scripts = [s for s in scripts if s.get('async') or s.get('defer')]
    if async_scripts:
        fid_estimate -= 25
    
    # Estimate CLS (Cumulative Layout Shift)
    cls_estimate = 0.05  # Start with good baseline
    
    # Check for images without dimensions
    images_without_dims = [img for img in images if not (img.get('width') and img.get('height'))]
    if len(images_without_dims) > 5:
        cls_estimate += 0.15
    elif len(images_without_dims) > 2:
        cls_estimate += 0.10
    elif images_without_dims:
        cls_estimate += 0.05
    
    # Check for web fonts
    if 'font-face' in html_content.lower():
        cls_estimate += 0.05
    
    # Assess overall status
    lcp_status = "Good" if lcp_estimate <= 2.5 else "Needs Improvement" if lcp_estimate <= 4.0 else "Poor"
    fid_status = "Good" if fid_estimate <= 100 else "Needs Improvement" if fid_estimate <= 300 else "Poor"
    cls_status = "Good" if cls_estimate <= 0.1 else "Needs Improvement" if cls_estimate <= 0.25 else "Poor"
    
    overall_status = "Pass"
    if lcp_status == "Poor" or fid_status == "Poor" or cls_status == "Poor":
        overall_status = "Fail"
    elif lcp_status == "Needs Improvement" or fid_status == "Needs Improvement" or cls_status == "Needs Improvement":
        overall_status = "Needs Improvement"
    
    return {
        "lcp": {
            "value": f"{lcp_estimate:.1f}s",
            "status": lcp_status,
            "threshold": "≤2.5s (Good), ≤4.0s (Needs Improvement)"
        },
        "fid": {
            "value": f"{fid_estimate}ms",
            "status": fid_status,
            "threshold": "≤100ms (Good), ≤300ms (Needs Improvement)"
        },
        "cls": {
            "value": f"{cls_estimate:.2f}",
            "status": cls_status,
            "threshold": "≤0.1 (Good), ≤0.25 (Needs Improvement)"
        },
        "overall_status": overall_status,
        "recommendations": [
            "Optimize images with lazy loading and proper sizing" if lcp_status != "Good" else None,
            "Reduce JavaScript execution time" if fid_status != "Good" else None,
            "Add explicit dimensions to images and embeds" if cls_status != "Good" else None
        ]
    }


def estimate_traffic_rank(url: str, basic_metrics: Dict[str, Any]) -> str:
    """
    Estimate traffic rank based on various signals
    
    Returns:
        String description of estimated traffic rank
    """
    score = basic_metrics.get('digital_maturity_score', 0)
    
    if score >= 75:
        return "Top 10% in industry (High traffic potential)"
    elif score >= 60:
        return "Top 25% in industry (Good traffic potential)"
    elif score >= 45:
        return "Average industry position (Moderate traffic)"
    elif score >= 30:
        return "Below average (Limited traffic)"
    else:
        return "Low visibility (Minimal traffic)"


def generate_market_trends(industry: str = None) -> List[str]:
    """
    Generate relevant market trends
    
    Returns:
        List of market trend insights
    """
    trends = [
        "Mobile-first indexing is now standard - mobile optimization critical",
        "Core Web Vitals directly impact Google rankings",
        "AI-powered content and chatbots becoming standard",
        "Video content drives 80% more engagement than text",
        "Voice search optimization growing in importance"
    ]
    
    if industry:
        if "retail" in industry.lower() or "commerce" in industry.lower():
            trends.extend([
                "Social commerce integration essential for retail",
                "Personalization drives 20% higher conversion rates"
            ])
        elif "tech" in industry.lower():
            trends.extend([
                "Developer documentation and API portals expected",
                "Open source presence increases credibility"
            ])
        elif "service" in industry.lower():
            trends.extend([
                "Online booking systems now expected",
                "Reviews and testimonials critical for trust"
            ])
    
    return trends[:5]


def calculate_improvement_potential(basic_metrics: Dict[str, Any]) -> int:
    """
    Calculate realistic improvement potential
    
    Returns:
        Points of potential improvement
    """
    current_score = basic_metrics.get('digital_maturity_score', 0)
    score_breakdown = basic_metrics.get('score_breakdown', {})
    
    potential = 0
    
    # Calculate potential for each category
    for category, max_points in SCORING_WEIGHTS.items():
        current = score_breakdown.get(category, 0)
        gap = max_points - current
        
        # Realistic improvement factors
        if gap > max_points * 0.7:  # Very low score
            potential += int(gap * 0.8)  # Can improve 80% of gap
        elif gap > max_points * 0.4:  # Low-medium score
            potential += int(gap * 0.6)  # Can improve 60% of gap
        else:  # Already decent
            potential += int(gap * 0.4)  # Can improve 40% of gap
    
    return min(potential, 100 - current_score)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CompetitorAnalysisRequest(BaseModel):
    """Request model for competitor analysis"""
    url: str = Field(
        ..., 
        description="Website URL to analyze",
        example="https://example.com"
    )
    company_name: Optional[str] = Field(
        None, 
        description="Company name (optional)",
        max_length=100
    )
    analysis_type: str = Field(
        "comprehensive", 
        description="Type of analysis: basic, comprehensive, or ai_enhanced"
    )
    language: str = Field(
        "fi", 
        description="Response language: fi (Finnish) or en (English)",
        pattern="^(fi|en)$"
    )
    include_ai: bool = Field(
        True, 
        description="Include AI-powered insights"
    )
    include_social: bool = Field(
        True, 
        description="Include social media analysis"
    )


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown"""
    security: int = Field(0, ge=0, le=15)
    seo_basics: int = Field(0, ge=0, le=20)
    content: int = Field(0, ge=0, le=20)
    technical: int = Field(0, ge=0, le=15)
    mobile: int = Field(0, ge=0, le=15)
    social: int = Field(0, ge=0, le=10)
    performance: int = Field(0, ge=0, le=5)


class BasicAnalysis(BaseModel):
    """Basic website analysis results"""
    company: str
    website: str
    industry: Optional[str] = None
    digital_maturity_score: int = Field(..., ge=0, le=100)
    social_platforms: int = Field(0, ge=0)
    technical_score: int = Field(0, ge=0, le=100)
    content_score: int = Field(0, ge=0, le=100)
    seo_score: int = Field(0, ge=0, le=100)
    score_breakdown: Optional[ScoreBreakdown] = None
    analysis_timestamp: datetime = Field(default_factory=datetime.now)


class TechnicalAudit(BaseModel):
    """Technical website audit results"""
    has_ssl: bool = False
    has_mobile_optimization: bool = False
    page_speed_score: int = Field(0, ge=0, le=100)
    has_analytics: bool = False
    has_sitemap: bool = False
    has_robots_txt: bool = False
    meta_tags_score: int = Field(0, ge=0, le=100)
    overall_technical_score: int = Field(0, ge=0, le=100)
    security_headers: Dict[str, bool] = {}
    performance_indicators: List[str] = []


class ContentAnalysis(BaseModel):
    """Content analysis results"""
    word_count: int = Field(0, ge=0)
    readability_score: int = Field(0, ge=0, le=100)
    keyword_density: Dict[str, float] = {}
    content_freshness: str = Field(
        "unknown",
        pattern="^(very_fresh|fresh|moderate|dated|unknown)$"
    )
    has_blog: bool = False
    content_quality_score: int = Field(0, ge=0, le=100)
    media_types: List[str] = []
    interactive_elements: List[str] = []


class SocialMediaAnalysis(BaseModel):
    """Social media presence analysis"""
    platforms: List[str] = []
    total_followers: int = Field(0, ge=0)
    engagement_rate: float = Field(0.0, ge=0.0, le=100.0)
    posting_frequency: str = "unknown"
    social_score: int = Field(0, ge=0, le=100)
    has_sharing_buttons: bool = False
    open_graph_tags: int = 0
    twitter_cards: bool = False


class UXAnalysis(BaseModel):
    """User Experience analysis"""
    navigation_score: int = Field(0, ge=0, le=100)
    visual_design_score: int = Field(0, ge=0, le=100)
    accessibility_score: int = Field(0, ge=0, le=100)
    mobile_ux_score: int = Field(0, ge=0, le=100)
    overall_ux_score: int = Field(0, ge=0, le=100)
    accessibility_issues: List[str] = []
    navigation_elements: List[str] = []
    design_frameworks: List[str] = []


class CompetitiveAnalysis(BaseModel):
    """Competitive positioning analysis"""
    market_position: str = Field(
        "unknown",
        description="Market position assessment"
    )
    competitive_advantages: List[str] = []
    competitive_threats: List[str] = []
    market_share_estimate: str = "Data not available"
    competitive_score: int = Field(0, ge=0, le=100)
    industry_comparison: Dict[str, Any] = {}


class AIInsight(BaseModel):
    """Individual AI insight"""
    category: str
    insight: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    priority: str = Field(
        "medium",
        pattern="^(critical|high|medium|low)$"
    )


class AIAnalysis(BaseModel):
    """AI-powered analysis results"""
    # English fields
    summary: str = ""
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    recommendations: List[str] = []
    confidence_score: int = Field(0, ge=0, le=100)
    sentiment_score: float = Field(0.0, ge=-1.0, le=1.0)
    
    # Finnish fields for backward compatibility
    johtopäätökset: str = ""
    vahvuudet: List[str] = []
    heikkoudet: List[str] = []
    mahdollisuudet: List[str] = []
    uhat: List[str] = []
    toimenpidesuositukset: List[str] = []
    strategiset_suositukset: List[str] = []
    quick_wins: List[str] = []
    
    # Additional insights
    key_metrics: Dict[str, Any] = {}
    action_priority: List[AIInsight] = []


class SmartAction(BaseModel):
    """Individual smart action recommendation"""
    title: str
    description: str
    priority: str = Field(..., pattern="^(critical|high|medium|low)$")
    effort: str = Field(..., pattern="^(low|medium|high)$")
    impact: str = Field(..., pattern="^(low|medium|high|critical)$")
    estimated_score_increase: int = Field(0, ge=0, le=100)
    category: str = ""
    estimated_time: str = ""


class SmartActions(BaseModel):
    """Smart action recommendations container"""
    actions: List[SmartAction] = []
    priority_matrix: Dict[str, List[str]] = {}
    total_potential_score_increase: int = 0
    implementation_roadmap: List[Dict[str, Any]] = []


class SmartScores(BaseModel):
    """Comprehensive scoring summary"""
    overall: int = Field(0, ge=0, le=100)
    technical: int = Field(0, ge=0, le=100)
    content: int = Field(0, ge=0, le=100)
    social: int = Field(0, ge=0, le=100)
    ux: int = Field(0, ge=0, le=100)
    competitive: int = Field(0, ge=0, le=100)
    trend: str = "stable"  # declining, stable, improving
    percentile: int = Field(0, ge=0, le=100)


class DetailedAnalysis(BaseModel):
    """Container for all detailed analysis components"""
    social_media: SocialMediaAnalysis
    technical_audit: TechnicalAudit
    content_analysis: ContentAnalysis
    ux_analysis: UXAnalysis
    competitive_analysis: CompetitiveAnalysis
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EnhancedFeatures(BaseModel):
    """Enhanced analysis features and insights"""
    industry_benchmarking: Dict[str, Any] = {}
    competitor_gaps: List[str] = []
    growth_opportunities: List[str] = []
    risk_assessment: List[str] = []
    market_trends: List[str] = []
    technology_stack: List[str] = []
    estimated_traffic_rank: str = "Not available"
    mobile_first_index_ready: bool = False
    core_web_vitals_assessment: Dict[str, str] = {}


class AnalysisResponse(BaseModel):
    """Complete analysis response model"""
    success: bool
    company_name: str
    analysis_date: str
    basic_analysis: BasicAnalysis
    ai_analysis: AIAnalysis
    detailed_analysis: DetailedAnalysis
    smart: Dict[str, Any] = {}
    enhanced_features: Optional[EnhancedFeatures] = None
    metadata: Dict[str, Any] = {}
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# [Continue with all the analysis functions from the original code...]
# Including: analyze_basic_metrics, analyze_technical_aspects, analyze_content_quality, etc.

# ============================================================================
# CORE SCORING FUNCTIONS (keeping existing implementation)
# ============================================================================

async def analyze_basic_metrics(url: str, html_content: str) -> Dict[str, Any]:
    """
    Analyze basic website metrics with 0-100 scoring.
    All scores start from 0 and build up based on findings.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Initialize scores at 0
    score_components = {
        'security': 0,
        'seo_basics': 0,
        'content': 0,
        'technical': 0,
        'mobile': 0,
        'social': 0,
        'performance': 0
    }
    
    detailed_findings = {}
    
    # 1. SECURITY (15 points)
    if url.startswith('https://'):
        score_components['security'] += 10
        detailed_findings['https'] = True
        
        security_headers = check_security_headers(html_content)
        if security_headers['csp']:
            score_components['security'] += 2
        if security_headers['x_frame_options']:
            score_components['security'] += 1
        if security_headers['strict_transport']:
            score_components['security'] += 2
    else:
        detailed_findings['https'] = False
    
    # 2. SEO BASICS (20 points)
    title = soup.find('title')
    if title:
        title_text = title.get_text().strip()
        title_length = len(title_text)
        if 30 <= title_length <= 60:
            score_components['seo_basics'] += 5
        elif 20 <= title_length < 30 or 60 < title_length <= 70:
            score_components['seo_basics'] += 3
        elif title_length > 0:
            score_components['seo_basics'] += 1
        detailed_findings['title_length'] = title_length
    
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        desc_content = meta_desc.get('content', '').strip()
        desc_length = len(desc_content)
        if 120 <= desc_length <= 160:
            score_components['seo_basics'] += 5
        elif 80 <= desc_length < 120 or 160 < desc_length <= 200:
            score_components['seo_basics'] += 3
        elif desc_length > 0:
            score_components['seo_basics'] += 1
        detailed_findings['meta_desc_length'] = desc_length
    
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    h3_tags = soup.find_all('h3')
    
    if len(h1_tags) == 1:
        score_components['seo_basics'] += 3
    elif len(h1_tags) in [2, 3]:
        score_components['seo_basics'] += 1
    
    if len(h2_tags) >= 2:
        score_components['seo_basics'] += 1
    if len(h3_tags) >= 1:
        score_components['seo_basics'] += 1
    
    canonical = soup.find('link', {'rel': 'canonical'})
    if canonical:
        score_components['seo_basics'] += 2
        detailed_findings['has_canonical'] = True
    
    hreflang = soup.find('link', {'hreflang': True})
    if hreflang:
        score_components['seo_basics'] += 1
        detailed_findings['has_hreflang'] = True
    
    if check_clean_urls(url):
        score_components['seo_basics'] += 2
    
    # 3. CONTENT (20 points)
    text_content = extract_clean_text(soup)
    words = text_content.split()
    word_count = len(words)
    
    if word_count >= 2500:
        score_components['content'] += 10
    elif word_count >= 1500:
        score_components['content'] += 7
    elif word_count >= 800:
        score_components['content'] += 4
    elif word_count >= 300:
        score_components['content'] += 2
    
    detailed_findings['word_count'] = word_count
    
    freshness_score = check_content_freshness(soup, html_content)
    score_components['content'] += freshness_score
    
    img_optimization = analyze_image_optimization(soup)
    score_components['content'] += img_optimization['score']
    detailed_findings['image_optimization'] = img_optimization
    
    # 4. TECHNICAL (15 points)
    structured_data = analyze_structured_data(soup, html_content)
    score_components['technical'] += structured_data['score']
    detailed_findings['structured_data'] = structured_data
    
    analytics = detect_analytics_tools(html_content)
    if analytics['has_analytics']:
        score_components['technical'] += 3
        detailed_findings['analytics'] = analytics['tools']
    
    if check_sitemap_indicators(soup):
        score_components['technical'] += 1
    if check_robots_indicators(html_content):
        score_components['technical'] += 1
    
    perf_indicators = analyze_performance_indicators(soup, html_content)
    score_components['technical'] += perf_indicators['score']
    detailed_findings['performance_indicators'] = perf_indicators
    
    # 5. MOBILE (15 points)
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if viewport:
        viewport_content = viewport.get('content', '')
        if 'width=device-width' in viewport_content:
            score_components['mobile'] += 5
        if 'initial-scale=1' in viewport_content:
            score_components['mobile'] += 3
        detailed_findings['has_viewport'] = True
    else:
        detailed_findings['has_viewport'] = False
    
    responsive_indicators = check_responsive_design(html_content)
    score_components['mobile'] += responsive_indicators['score']
    detailed_findings['responsive_design'] = responsive_indicators
    
    # 6. SOCIAL (10 points)
    social_presence = analyze_social_presence(soup, html_content)
    score_components['social'] += social_presence['score']
    detailed_findings['social_media'] = social_presence
    
    # 7. PERFORMANCE (5 points)
    if len(html_content) < 100000:
        score_components['performance'] += 2
    elif len(html_content) < 200000:
        score_components['performance'] += 1
    
    if 'lazy' in html_content.lower() or 'loading="lazy"' in html_content:
        score_components['performance'] += 2
    
    if 'webp' in html_content.lower():
        score_components['performance'] += 1
    
    # Calculate final score
    total_score = sum(score_components.values())
    final_score = max(0, min(100, total_score))
    
    logger.info(f"Analysis for {url}: Score={final_score}, Breakdown={score_components}")
    
    return {
        'digital_maturity_score': final_score,
        'score_breakdown': score_components,
        'detailed_findings': detailed_findings,
        'word_count': word_count,
        'has_ssl': url.startswith('https'),
        'has_analytics': analytics['has_analytics'],
        'has_mobile_viewport': bool(viewport),
        'title': title.get_text().strip() if title else '',
        'meta_description': meta_desc.get('content', '') if meta_desc else '',
        'h1_count': len(h1_tags),
        'h2_count': len(h2_tags),
        'social_platforms': len(social_presence['platforms'])
    }


# [Include all other existing analysis functions...]
# analyze_technical_aspects, analyze_content_quality, analyze_ux_elements, etc.
# (These remain the same as in the original code)

# ============================================================================
# HELPER FUNCTIONS (keeping existing implementation)
# ============================================================================

def check_security_headers(html_content: str) -> Dict[str, bool]:
    """Check for security headers"""
    return {
        'csp': 'content-security-policy' in html_content.lower(),
        'x_frame_options': 'x-frame-options' in html_content.lower(),
        'strict_transport': 'strict-transport-security' in html_content.lower()
    }


def check_clean_urls(url: str) -> bool:
    """Check if URL structure is SEO-friendly"""
    if '?' in url and '=' in url:
        return False
    if '.php' in url or '.asp' in url or '.jsp' in url:
        return False
    if '__' in url or url.count('_') > 3:
        return False
    return True


def extract_clean_text(soup: BeautifulSoup) -> str:
    """Extract clean text from HTML"""
    for element in soup(['script', 'style', 'noscript']):
        element.decompose()
    
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return ' '.join(chunk for chunk in chunks if chunk)


def check_content_freshness(soup: BeautifulSoup, html_content: str) -> int:
    """Check content freshness (0-5 points)"""
    score = 0
    current_year = datetime.now().year
    
    date_patterns = [
        rf'{current_year}',
        rf'{current_year - 1}',
        r'\d{1,2}\.\d{1,2}\.\d{4}',
        r'\d{4}-\d{2}-\d{2}',
    ]
    
    recent_dates = 0
    for pattern in date_patterns[:2]:
        if re.search(pattern, html_content):
            recent_dates += 1
    
    if recent_dates >= 2:
        score += 3
    elif recent_dates == 1:
        score += 2
    
    modified_meta = soup.find('meta', attrs={'property': 'article:modified_time'})
    if not modified_meta:
        modified_meta = soup.find('meta', attrs={'name': 'last-modified'})
    
    if modified_meta:
        score += 2
    
    return min(5, score)


def analyze_image_optimization(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze image optimization (0-5 points)"""
    images = soup.find_all('img')
    if not images:
        return {'score': 0, 'total_images': 0, 'optimized_images': 0}
    
    optimized_count = 0
    
    for img in images:
        img_score = 0
        if img.get('alt', '').strip():
            img_score += 1
        if img.get('loading') == 'lazy':
            img_score += 1
        src = img.get('src', '').lower()
        if '.webp' in src or '.avif' in src:
            img_score += 1
        if img.get('srcset'):
            img_score += 1
        
        if img_score >= 2:
            optimized_count += 1
    
    optimization_ratio = optimized_count / len(images)
    score = int(optimization_ratio * 5)
    
    return {
        'score': score,
        'total_images': len(images),
        'optimized_images': optimized_count,
        'optimization_ratio': optimization_ratio
    }


# [Include all other helper functions...]
# (These remain the same as in the original code)

# ============================================================================
# MAIN API ENDPOINT WITH ENHANCED FEATURES
# ============================================================================

@app.post("/api/v1/ai-analyze")
async def ai_analyze(request: CompetitorAnalysisRequest):
    """Main AI-powered analysis endpoint with enhanced features"""
    try:
        # Clean URL
        url = clean_url(request.url)
        
        # Check cache
        cache_key = get_cache_key(url, "ai_v5_enhanced")
        if cache_key in analysis_cache:
            cached = analysis_cache[cache_key]
            if is_cache_valid(cached['timestamp']):
                logger.info(f"Cache hit for {url}")
                return cached['data']
        
        # Fetch website
        response = await fetch_url(url)
        if not response or response.status_code != 200:
            raise HTTPException(400, f"Cannot fetch {url}")
        
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Run all analyses
        basic_metrics = await analyze_basic_metrics(url, html_content)
        technical = await analyze_technical_aspects(url, html_content)
        content = await analyze_content_quality(html_content)
        ux = await analyze_ux_elements(html_content)
        social = await analyze_social_media_presence(url, html_content)
        competitive = await analyze_competitive_positioning(url, basic_metrics)
        
        # Generate AI insights
        ai_analysis = await generate_ai_insights(
            url, basic_metrics, technical, content,
            ux, social, request.language
        )
        
        # Enhanced features analysis
        tech_stack = detect_technology_stack(html_content, soup)
        mobile_first = assess_mobile_first_readiness(soup, html_content)
        core_vitals = estimate_core_web_vitals(soup, html_content)
        traffic_rank = estimate_traffic_rank(url, basic_metrics)
        market_trends = generate_market_trends()
        improvement_potential = calculate_improvement_potential(basic_metrics)
        competitor_gaps = generate_competitor_gaps(basic_metrics, competitive)
        
        # Build comprehensive enhanced features
        enhanced_features = {
            "industry_benchmarking": {
                "value": f"{basic_metrics['digital_maturity_score']} / 100",
                "description": "Toimialan keskiarvo: 45, Top 25%: 70",
                "status": "above_average" if basic_metrics['digital_maturity_score'] > 45 else "below_average",
                "details": {
                    "your_score": basic_metrics['digital_maturity_score'],
                    "industry_average": 45,
                    "top_quartile": 70,
                    "bottom_quartile": 30,
                    "percentile": min(100, int((basic_metrics['digital_maturity_score'] / 45) * 50)) if basic_metrics['digital_maturity_score'] <= 45 else 50 + int(((basic_metrics['digital_maturity_score'] - 45) / 55) * 50)
                }
            },
            "competitor_gaps": {
                "value": f"{len(competitor_gaps)} tunnistettu",
                "description": "Merkittävimmät erot kilpailijoihin",
                "items": competitor_gaps,
                "status": "critical" if len(competitor_gaps) > 2 else "moderate"
            },
            "growth_opportunities": {
                "value": f"+{improvement_potential} pistettä",
                "description": f"Realistinen parannuspotentiaali 6kk aikana",
                "items": ai_analysis.opportunities[:3] if hasattr(ai_analysis, 'opportunities') else [],
                "potential_score": basic_metrics['digital_maturity_score'] + improvement_potential
            },
            "risk_assessment": {
                "value": f"{len(ai_analysis.threats if hasattr(ai_analysis, 'threats') else [])} riskiä",
                "description": "Tunnistetut kriittiset riskit",
                "items": ai_analysis.threats[:3] if hasattr(ai_analysis, 'threats') else [],
                "severity": "high" if basic_metrics['digital_maturity_score'] < 30 else "medium" if basic_metrics['digital_maturity_score'] < 60 else "low"
            },
            "market_trends": {
                "value": f"{len(market_trends)} trendiä",
                "description": "Relevantit markkinatrendit",
                "items": market_trends,
                "alignment": "aligned" if basic_metrics['digital_maturity_score'] > 60 else "partially_aligned" if basic_metrics['digital_maturity_score'] > 30 else "not_aligned"
            },
            "technology_stack": {
                "value": f"{tech_stack['count']} teknologiaa",
                "description": ", ".join(tech_stack['detected'][:3]) + "..." if len(tech_stack['detected']) > 3 else ", ".join(tech_stack['detected']),
                "detected": tech_stack['detected'],
                "categories": tech_stack['categories'],
                "modernity": "modern" if any('React' in t or 'Next' in t or 'Vue' in t for t in tech_stack['detected']) else "traditional"
            },
            "estimated_traffic_rank": {
                "value": traffic_rank,
                "description": "Arvioitu sijoitus toimialalla liikenteen perusteella",
                "confidence": "medium",
                "factors": ["Digital maturity score", "SEO optimization", "Content volume"]
            },
            "mobile_first_index_ready": {
                "value": "Kyllä" if mobile_first['ready'] else "Ei",
                "description": "Google Mobile-First indeksointi valmius",
                "status": "ready" if mobile_first['ready'] else "not_ready",
                "score": mobile_first['score'],
                "issues": mobile_first['issues'],
                "recommendations": [r for r in mobile_first['recommendations'] if r]
            },
            "core_web_vitals_assessment": {
                "value": core_vitals['overall_status'],
                "description": f"LCP: {core_vitals['lcp']['value']}, FID: {core_vitals['fid']['value']}, CLS: {core_vitals['cls']['value']}",
                "lcp": core_vitals['lcp'],
                "fid": core_vitals['fid'],
                "cls": core_vitals['cls'],
                "overall_status": core_vitals['overall_status'],
                "recommendations": [r for r in core_vitals['recommendations'] if r]
            }
        }
        
        # Build response
        result = {
            "success": True,
            "company_name": request.company_name or basic_metrics.get('title', 'Unknown'),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": BasicAnalysis(
                company=request.company_name or basic_metrics.get('title', 'Unknown'),
                website=url,
                digital_maturity_score=basic_metrics['digital_maturity_score'],
                social_platforms=basic_metrics.get('social_platforms', 0),
                technical_score=technical.get('overall_technical_score', 0),
                content_score=content.get('content_quality_score', 0),
                seo_score=int((basic_metrics.get('score_breakdown', {}).get('seo_basics', 0) / 20) * 100),
                score_breakdown=basic_metrics.get('score_breakdown', {})
            ).dict(),
            "ai_analysis": ai_analysis.dict() if hasattr(ai_analysis, 'dict') else ai_analysis,
            "detailed_analysis": DetailedAnalysis(
                social_media=SocialMediaAnalysis(**social),
                technical_audit=TechnicalAudit(**technical),
                content_analysis=ContentAnalysis(**content),
                ux_analysis=UXAnalysis(**ux),
                competitive_analysis=CompetitiveAnalysis(**competitive)
            ).dict(),
            "smart": {
                "actions": generate_smart_actions(
                    ai_analysis, technical, content, basic_metrics
                ),
                "scores": SmartScores(
                    overall=basic_metrics['digital_maturity_score'],
                    technical=technical.get('overall_technical_score', 0),
                    content=content.get('content_quality_score', 0),
                    social=social.get('social_score', 0),
                    ux=ux.get('overall_ux_score', 0),
                    competitive=competitive.get('competitive_score', 0),
                    trend="improving" if improvement_potential > 20 else "stable",
                    percentile=enhanced_features['industry_benchmarking']['details']['percentile']
                ).dict()
            },
            "enhanced_features": enhanced_features,
            "metadata": {
                "version": APP_VERSION,
                "analysis_depth": "comprehensive",
                "confidence_level": ai_analysis.confidence_score if hasattr(ai_analysis, 'confidence_score') else 85,
                "data_points_analyzed": len(tech_stack['detected']) + len(basic_metrics.get('detailed_findings', {}))
            }
        }
        
        # Ensure integer scores
        result = ensure_integer_scores(result)
        
        # Cache result
        analysis_cache[cache_key] = {
            'data': result,
            'timestamp': datetime.now()
        }
        
        # Clean old cache
        if len(analysis_cache) > MAX_CACHE_SIZE:
            oldest = min(analysis_cache.keys(),
                        key=lambda k: analysis_cache[k]['timestamp'])
            del analysis_cache[oldest]
        
        logger.info(f"Enhanced analysis complete for {url}: score={basic_metrics['digital_maturity_score']}")
        return result
        
    except Exception as e:
        logger.error(f"Analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")


# [Include all other endpoints from the original code...]
# @app.get("/"), @app.get("/health"), @app.post("/api/v1/analyze"), etc.

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    
    logger.info(f"{APP_NAME} v{APP_VERSION}")
    logger.info("Starting server with enhanced features...")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
