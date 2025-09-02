"""
Advanced Competitive Intelligence API - Premium Edition
Version: 5.0.0
Author: Brandista AI Team
Description: Huippuluokan kilpailija-analyysityökalu AI-pohjaisilla näkemyksillä
"""

# ==================== OSA 1/6 ALKAA ====================
# IMPORTS JA KONFIGURAATIO

import os
import re
import json
import base64
import hashlib
import logging
import asyncio
import pickle
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from functools import lru_cache, wraps
from collections import defaultdict, Counter
from urllib.parse import urlparse, urljoin
from enum import Enum

import httpx
import numpy as np
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Advanced imports
try:
    import validators
    import ipaddress
    VALIDATORS_AVAILABLE = True
except ImportError:
    VALIDATORS_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import spacy
    from textstat import flesch_reading_ease, flesch_kincaid_grade
    NLP_AVAILABLE = True
    nlp = None  # Lazy load
except ImportError:
    NLP_AVAILABLE = False

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    VISUALIZATION_AVAILABLE = True
    sns.set_theme()
except ImportError:
    VISUALIZATION_AVAILABLE = False

# Database
try:
    from sqlalchemy import create_engine, Column, String, JSON, DateTime, Float, Integer, Boolean, Text
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.dialects.postgresql import UUID
    import uuid
    DB_AVAILABLE = True
    Base = declarative_base()
except ImportError:
    DB_AVAILABLE = False
    Base = None

# PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('competitive_intel.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

APP_VERSION = "5.0.0"
APP_NAME = "Brandista Competitive Intelligence API Premium"

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/competitive_intel")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "false").lower() == "true"
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "1").lower() in ("1", "true", "yes")
LIGHTHOUSE_ENABLED = os.getenv("LIGHTHOUSE_ENABLED", "false").lower() == "true"

# Performance settings
MAX_CONCURRENT_ANALYSES = 10
CACHE_TTL = 86400  # 24 hours
MAX_URL_DEPTH = 100
REQUEST_TIMEOUT = 30
JS_RENDER_TIMEOUT = 20

# ==================== PROMETHEUS METRICS ====================

# Metrics
analysis_counter = Counter('competitor_analysis_total', 'Total analyses performed')
analysis_duration = Histogram('competitor_analysis_duration_seconds', 'Analysis duration')
cache_hits = Counter('cache_hits_total', 'Cache hit count')
cache_misses = Counter('cache_misses_total', 'Cache miss count')
ai_requests = Counter('ai_requests_total', 'AI API requests', ['provider', 'model'])
error_counter = Counter('errors_total', 'Total errors', ['error_type'])
active_analyses = Gauge('active_analyses', 'Currently running analyses')

# ==================== DATABASE MODELS ====================

if DB_AVAILABLE:
    class CompetitorAnalysis(Base):
        __tablename__ = 'competitor_analyses'
        
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        url = Column(String, nullable=False, index=True)
        company_name = Column(String, nullable=True)
        analysis_data = Column(JSON, nullable=False)
        scores = Column(JSON, nullable=False)
        ai_insights = Column(JSON, nullable=True)
        created_at = Column(DateTime, default=datetime.now(datetime.timezone.utc), index=True)
        updated_at = Column(DateTime, default=datetime.now(datetime.timezone.utc), onupdate=datetime.now(datetime.timezone.utc))
        language = Column(String, default='fi')
        version = Column(String, default=APP_VERSION)
        
    class CompetitorTracking(Base):
        __tablename__ = 'competitor_tracking'
        
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        url = Column(String, nullable=False, index=True)
        check_date = Column(DateTime, default=datetime.now(datetime.timezone.utc), index=True)
        changes_detected = Column(JSON, nullable=True)
        score_change = Column(Float, nullable=True)
        alert_sent = Column(Boolean, default=False)
        
    class AnalysisReport(Base):
        __tablename__ = 'analysis_reports'
        
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        report_type = Column(String, nullable=False)  # 'single', 'comparison', 'batch'
        report_data = Column(JSON, nullable=False)
        pdf_url = Column(String, nullable=True)
        created_at = Column(DateTime, default=datetime.now(datetime.timezone.utc))
        created_by = Column(String, nullable=True)

# ==================== PYDANTIC MODELS ====================

class AnalysisLevel(str, Enum):
    BASIC = "basic"
    STANDARD = "standard"
    ADVANCED = "advanced"
    PREMIUM = "premium"

class AnalyzeRequest(BaseModel):
    url: str
    level: AnalysisLevel = AnalysisLevel.STANDARD
    include_ai: bool = True
    include_lighthouse: bool = False
    include_competitors: bool = False
    track_changes: bool = False
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        if VALIDATORS_AVAILABLE and not validators.url(v):
            raise ValueError('Invalid URL format')
        return v

class CompetitorProfile(BaseModel):
    url: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    key_products: List[str] = []
    target_markets: List[str] = []

class AIInsights(BaseModel):
    summary: str = Field(description="Executive summary")
    strengths: List[str] = Field(description="Key strengths")
    weaknesses: List[str] = Field(description="Key weaknesses")
    opportunities: List[str] = Field(description="Market opportunities")
    threats: List[str] = Field(description="Potential threats")
    market_position: str = Field(description="Market positioning analysis")
    competitive_advantages: List[str] = Field(description="Unique competitive advantages")
    improvement_recommendations: List[Dict[str, Any]] = Field(description="Prioritized recommendations")
    estimated_traffic: Dict[str, float] = Field(description="Traffic source estimates")
    technology_score: int = Field(ge=1, le=10, description="Technology maturity score")
    content_strategy: str = Field(description="Content strategy assessment")
    user_experience_score: int = Field(ge=1, le=10, description="UX score")

class SmartAnalysisResponse(BaseModel):
    success: bool
    url: str
    company_name: Optional[str]
    analysis_date: datetime
    level: AnalysisLevel
    scores: Dict[str, Any]
    technical_analysis: Dict[str, Any]
    content_analysis: Dict[str, Any]
    seo_analysis: Dict[str, Any]
    performance_metrics: Optional[Dict[str, Any]]
    ai_insights: Optional[AIInsights]
    competitor_comparison: Optional[Dict[str, Any]]
    tracking_enabled: bool
    report_id: Optional[str]
    
class BatchAnalysisRequest(BaseModel):
    urls: List[str] = Field(max_length=20)
    level: AnalysisLevel = AnalysisLevel.STANDARD
    generate_report: bool = True
    compare_all: bool = False

class WebhookConfig(BaseModel):
    url: str
    events: List[str] = ['analysis_complete', 'significant_change_detected']
    secret: Optional[str] = None
    
# ==================== OSA 1/6 LOPPUU ====================

# ==================== OSA 2/6 ALKAA ====================
# CACHE, SECURITY JA UTILITY FUNKTIOT

# ==================== REDIS CACHE ====================

class RedisCache:
    """Advanced Redis cache with compression and TTL"""
    
    def __init__(self):
        self.client = None
        if REDIS_AVAILABLE:
            try:
                self.client = redis.from_url(REDIS_URL, decode_responses=False)
                self.client.ping()
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.error(f"Redis initialization failed: {e}")
                self.client = None
    
    async def get(self, key: str) -> Optional[Dict]:
        """Get cached data with metrics"""
        if not self.client:
            cache_misses.inc()
            return None
        
        try:
            data = self.client.get(f"ci:{key}")
            if data:
                cache_hits.inc()
                return pickle.loads(data)
            cache_misses.inc()
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            cache_misses.inc()
            return None
    
    async def set(self, key: str, value: Dict, ttl: int = CACHE_TTL) -> bool:
        """Set cache with compression"""
        if not self.client:
            return False
        
        try:
            compressed = pickle.dumps(value)
            self.client.setex(f"ci:{key}", ttl, compressed)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete cache entry"""
        if not self.client:
            return False
        
        try:
            self.client.delete(f"ci:{key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def get_pattern(self, pattern: str) -> List[str]:
        """Get all keys matching pattern"""
        if not self.client:
            return []
        
        try:
            keys = self.client.keys(f"ci:{pattern}")
            return [k.decode('utf-8').replace('ci:', '') for k in keys]
        except Exception as e:
            logger.error(f"Cache pattern error: {e}")
            return []

# Initialize cache
cache = RedisCache()

# ==================== SECURITY ====================

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify JWT token for protected endpoints"""
    if not ENABLE_AUTH:
        return "anonymous"
    
    token = credentials.credentials
    try:
        # Here you would verify JWT token
        # For now, simple check
        if token != SECRET_KEY:
            raise HTTPException(status_code=403, detail="Invalid authentication")
        return "authenticated_user"
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))

async def get_current_user(token: Optional[str] = Depends(verify_token)) -> str:
    """Get current user from token"""
    return token if ENABLE_AUTH else "anonymous"

# ==================== URL VALIDATION ====================

def validate_and_sanitize_url(url: str) -> str:
    """Advanced URL validation with security checks"""
    
    # Basic format check
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    # Parse URL
    parsed = urlparse(url)
    
    # Security checks
    if not parsed.netloc:
        raise ValueError("Invalid URL: No domain found")
    
    # Check for localhost and private IPs
    hostname = parsed.hostname
    if hostname in ['localhost', '127.0.0.1', '0.0.0.0']:
        raise ValueError("Local URLs not allowed")
    
    # Check for private IP ranges (SSRF protection)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_reserved or ip.is_loopback:
            raise ValueError("Private IP addresses not allowed")
    except ValueError:
        # Not an IP address, probably a domain - that's fine
        pass
    
    # Check for suspicious patterns
    suspicious_patterns = [
        r'\.\./',  # Directory traversal
        r'<script',  # XSS attempts
        r'javascript:',  # JS protocol
        r'data:',  # Data protocol
        r'file:',  # File protocol
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            raise ValueError(f"Suspicious pattern detected: {pattern}")
    
    # Length check
    if len(url) > 2048:
        raise ValueError("URL too long (max 2048 characters)")
    
    return url

# ==================== RATE LIMITING ====================

class RateLimiter:
    """Advanced rate limiter with Redis backend"""
    
    def __init__(self):
        self.local_counts = defaultdict(list)
    
    async def check_rate_limit(
        self, 
        key: str, 
        limit: int = 100, 
        window: int = 3600
    ) -> bool:
        """Check if request is within rate limit"""
        
        # Try Redis first
        if cache.client:
            try:
                pipe = cache.client.pipeline()
                redis_key = f"rl:{key}"
                pipe.incr(redis_key)
                pipe.expire(redis_key, window)
                results = pipe.execute()
                
                if results[0] > limit:
                    return False
                return True
            except Exception as e:
                logger.error(f"Redis rate limit error: {e}")
        
        # Fallback to local memory
        now = datetime.now()
        cutoff = now - timedelta(seconds=window)
        
        # Clean old entries
        self.local_counts[key] = [
            t for t in self.local_counts[key] if t > cutoff
        ]
        
        # Check limit
        if len(self.local_counts[key]) >= limit:
            return False
        
        self.local_counts[key].append(now)
        return True
    
    async def get_remaining(self, key: str, limit: int = 100) -> int:
        """Get remaining requests in current window"""
        if cache.client:
            try:
                count = cache.client.get(f"rl:{key}")
                if count:
                    return max(0, limit - int(count))
                return limit
            except:
                pass
        
        return max(0, limit - len(self.local_counts.get(key, [])))

rate_limiter = RateLimiter()

# ==================== UTILITY FUNCTIONS ====================

def generate_cache_key(url: str, level: str = "standard") -> str:
    """Generate consistent cache key"""
    normalized = url.lower().strip().rstrip('/')
    return hashlib.sha256(f"{normalized}:{level}".encode()).hexdigest()

def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    parsed = urlparse(url)
    return parsed.netloc.lower()

def calculate_text_stats(text: str) -> Dict[str, Any]:
    """Calculate advanced text statistics"""
    words = text.split()
    sentences = re.split(r'[.!?]+', text)
    
    stats = {
        "character_count": len(text),
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_word_length": np.mean([len(w) for w in words]) if words else 0,
        "avg_sentence_length": np.mean([len(s.split()) for s in sentences if s]) if sentences else 0,
        "unique_words": len(set(words)),
        "lexical_diversity": len(set(words)) / len(words) if words else 0
    }
    
    # Readability scores if available
    if NLP_AVAILABLE and len(text) > 100:
        try:
            stats["flesch_reading_ease"] = flesch_reading_ease(text)
            stats["flesch_kincaid_grade"] = flesch_kincaid_grade(text)
        except:
            pass
    
    return stats

def detect_language(text: str) -> str:
    """Detect text language"""
    # Simple heuristic - could be improved with langdetect
    finnish_words = ['ja', 'on', 'että', 'ovat', 'kanssa', 'mukaan', 'sekä']
    english_words = ['and', 'the', 'is', 'are', 'with', 'that', 'for']
    
    text_lower = text.lower()
    fi_count = sum(1 for word in finnish_words if word in text_lower)
    en_count = sum(1 for word in english_words if word in text_lower)
    
    if fi_count > en_count:
        return 'fi'
    elif en_count > fi_count:
        return 'en'
    else:
        return 'unknown'

def measure_performance(func):
    """Decorator to measure async function performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = datetime.now()
        try:
            result = await func(*args, **kwargs)
            duration = (datetime.now() - start).total_seconds()
            logger.info(f"{func.__name__} completed in {duration:.2f}s")
            return result
        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            logger.error(f"{func.__name__} failed after {duration:.2f}s: {e}")
            raise
    return wrapper

# ==================== OSA 2/6 LOPPUU ====================

# ==================== OSA 3/6 ALKAA ====================
# CORE ANALYSIS FUNKTIOT

# ==================== WEB SCRAPING ====================

class WebScraper:
    """Advanced web scraper with JS rendering support"""
    
    def __init__(self):
        self.session = None
        self.js_session = None
    
    async def fetch_page(
        self, 
        url: str, 
        render_js: bool = False,
        timeout: int = REQUEST_TIMEOUT
    ) -> Tuple[str, int]:
        """Fetch page with optional JS rendering"""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Try JS rendering first if requested
        if render_js and SMART_JS_RENDER:
            html = await self._render_with_javascript(url)
            if html:
                return html, 200
        
        # Standard HTTP fetch
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text, response.status_code
    
    async def _render_with_javascript(self, url: str) -> Optional[str]:
        """Render page with headless browser"""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set viewport and user agent
                await page.set_viewport_size({"width": 1920, "height": 1080})
                
                # Navigate and wait for network idle
                await page.goto(url, wait_until='networkidle')
                
                # Wait for common lazy-load patterns
                await page.wait_for_timeout(2000)
                
                # Scroll to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                
                # Get rendered HTML
                html = await page.content()
                await browser.close()
                
                return html
        except Exception as e:
            logger.warning(f"JS rendering failed: {e}")
            return None
    
    async def fetch_robots_txt(self, url: str) -> Dict[str, Any]:
        """Fetch and parse robots.txt"""
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(robots_url)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Parse robots.txt
                    sitemaps = re.findall(r'Sitemap:\s*(\S+)', content, re.IGNORECASE)
                    disallowed = re.findall(r'Disallow:\s*(\S+)', content)
                    crawl_delay = re.search(r'Crawl-delay:\s*(\d+)', content, re.IGNORECASE)
                    
                    return {
                        "exists": True,
                        "sitemaps": sitemaps,
                        "disallowed_paths": disallowed[:20],  # Limit for storage
                        "crawl_delay": int(crawl_delay.group(1)) if crawl_delay else None
                    }
        except Exception as e:
            logger.debug(f"Robots.txt fetch failed: {e}")
        
        return {"exists": False, "sitemaps": [], "disallowed_paths": [], "crawl_delay": None}
    
    async def fetch_sitemap(self, url: str, max_urls: int = 100) -> Dict[str, Any]:
        """Fetch and parse XML sitemap"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Parse sitemap
                    urls = re.findall(r'<loc>(.*?)</loc>', content)[:max_urls]
                    lastmods = re.findall(r'<lastmod>(.*?)</lastmod>', content)
                    
                    # Find latest update
                    latest_date = None
                    for date_str in lastmods:
                        try:
                            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            if not latest_date or date > latest_date:
                                latest_date = date
                        except:
                            continue
                    
                    return {
                        "url_count": len(urls),
                        "sample_urls": urls[:10],
                        "latest_update": latest_date.isoformat() if latest_date else None
                    }
        except Exception as e:
            logger.debug(f"Sitemap fetch failed: {e}")
        
        return {"url_count": 0, "sample_urls": [], "latest_update": None}

# ==================== CONTENT ANALYSIS ====================

class ContentAnalyzer:
    """Advanced content analysis with NLP"""
    
    def __init__(self):
        self.nlp = None
        if NLP_AVAILABLE:
            self._load_nlp_model()
    
    def _load_nlp_model(self):
        """Lazy load NLP model"""
        global nlp
        if not nlp:
            try:
                nlp = spacy.load("en_core_web_sm")
            except:
                try:
                    nlp = spacy.load("fi_core_news_sm")
                except:
                    logger.warning("No spaCy model found")
        self.nlp = nlp
    
    async def analyze_content(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Comprehensive content analysis"""
        
        analysis = {
            "structure": self._analyze_structure(soup),
            "text_stats": self._analyze_text(soup),
            "media": self._analyze_media(soup),
            "links": self._analyze_links(soup, url),
            "semantic": await self._analyze_semantic(soup),
            "quality_signals": self._detect_quality_signals(soup),
            "engagement": self._analyze_engagement(soup),
            "accessibility": self._check_accessibility(soup)
        }
        
        return analysis
    
    def _analyze_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page structure"""
        
        # Heading hierarchy
        headings = {}
        for i in range(1, 7):
            h_tags = soup.find_all(f'h{i}')
            if h_tags:
                headings[f'h{i}'] = {
                    "count": len(h_tags),
                    "samples": [tag.get_text(strip=True)[:100] for tag in h_tags[:3]]
                }
        
        # Main content detection
        main = soup.find('main')
        article = soup.find('article')
        content_divs = soup.find_all('div', class_=re.compile('content|main|article'))
        
        # Navigation analysis
        nav = soup.find_all('nav')
        header = soup.find('header')
        footer = soup.find('footer')
        
        return {
            "headings": headings,
            "has_main_tag": bool(main),
            "has_article_tag": bool(article),
            "content_containers": len(content_divs),
            "navigation_count": len(nav),
            "has_header": bool(header),
            "has_footer": bool(footer),
            "semantic_structure_score": self._calculate_structure_score(soup)
        }
    
    def _analyze_text(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze text content"""
        
        # Extract main text
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)
        
        # Basic stats
        stats = calculate_text_stats(text)
        
        # Keyword extraction
        keywords = self._extract_keywords(text)
        
        # Language detection
        language = detect_language(text)
        
        return {
            **stats,
            "language": language,
            "keywords": keywords,
            "estimated_reading_time": max(1, stats["word_count"] // 200),  # Minutes
            "content_density": len(text) / max(len(str(soup)), 1)
        }
    
    def _analyze_media(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze media elements"""
        
        images = soup.find_all('img')
        videos = soup.find_all('video')
        iframes = soup.find_all('iframe')
        
        # Image analysis
        img_stats = {
            "total": len(images),
            "with_alt": len([img for img in images if img.get('alt')]),
            "with_lazy_load": len([img for img in images if img.get('loading') == 'lazy']),
            "with_srcset": len([img for img in images if img.get('srcset')]),
            "formats": dict(Counter([self._get_image_format(img.get('src', '')) for img in images]))
        }
        
        # Video analysis
        video_stats = {
            "total": len(videos),
            "with_controls": len([v for v in videos if v.get('controls')]),
            "autoplay": len([v for v in videos if v.get('autoplay')])
        }
        
        # Iframe analysis (embeds)
        iframe_sources = []
        for iframe in iframes:
            src = iframe.get('src', '')
            if 'youtube' in src:
                iframe_sources.append('YouTube')
            elif 'vimeo' in src:
                iframe_sources.append('Vimeo')
            elif 'maps' in src:
                iframe_sources.append('Google Maps')
            else:
                iframe_sources.append('Other')
        
        return {
            "images": img_stats,
            "videos": video_stats,
            "iframes": {
                "total": len(iframes),
                "sources": dict(Counter(iframe_sources))
            }
        }
    
    def _analyze_links(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """Analyze link structure"""
        
        links = soup.find_all('a', href=True)
        internal = []
        external = []
        
        base_domain = extract_domain(base_url)
        
        for link in links:
            href = link['href']
            
            # Skip anchors and special protocols
            if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue
            
            # Determine if internal or external
            if href.startswith(('http://', 'https://')):
                if base_domain in href:
                    internal.append(href)
                else:
                    external.append(href)
            else:
                internal.append(href)
        
        # Analyze external domains
        external_domains = Counter([extract_domain(url) for url in external])
        
        return {
            "total": len(links),
            "internal": len(internal),
            "external": len(external),
            "internal_unique": len(set(internal)),
            "external_unique": len(set(external)),
            "external_domains": dict(list(external_domains.most_common(10))),
            "broken_link_indicators": self._detect_broken_links(soup)
        }
    
    async def _analyze_semantic(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Semantic and NLP analysis"""
        
        if not self.nlp:
            return {"available": False}
        
        # Extract main content text
        text = soup.get_text(separator=' ', strip=True)[:10000]  # Limit for performance
        
        try:
            doc = self.nlp(text)
            
            # Named entities
            entities = defaultdict(list)
            for ent in doc.ents:
                entities[ent.label_].append(ent.text)
            
            # Key phrases (noun chunks)
            noun_phrases = [chunk.text for chunk in doc.noun_chunks][:50]
            
            # Sentiment analysis (simplified)
            sentiment = self._calculate_sentiment(text)
            
            return {
                "available": True,
                "entities": {k: list(set(v))[:10] for k, v in entities.items()},
                "key_phrases": noun_phrases[:20],
                "sentiment": sentiment,
                "topics": self._extract_topics(text)
            }
        except Exception as e:
            logger.error(f"Semantic analysis failed: {e}")
            return {"available": False, "error": str(e)}
    
    def _detect_quality_signals(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Detect quality and trust signals"""
        
        signals = {
            "has_privacy_policy": bool(soup.find('a', string=re.compile('privacy|tietosuoja', re.I))),
            "has_contact_page": bool(soup.find('a', string=re.compile('contact|yhteystiedot', re.I))),
            "has_about_page": bool(soup.find('a', string=re.compile('about|tietoa|meistä', re.I))),
            "has_terms": bool(soup.find('a', string=re.compile('terms|ehdot', re.I))),
            "has_blog": bool(soup.find('a', string=re.compile('blog|news|uutiset', re.I))),
            "has_social_links": self._detect_social_links(soup),
            "has_newsletter": bool(soup.find('input', {'type': 'email'})),
            "has_search": bool(soup.find('input', {'type': 'search'})) or bool(soup.find('input', {'name': re.compile('search|haku', re.I)})),
            "trust_badges": self._detect_trust_badges(soup),
            "testimonials": bool(soup.find(string=re.compile('testimonial|review|arvostelu', re.I)))
        }
        
        # Calculate quality score
        signals["quality_score"] = sum(1 for v in signals.values() if v == True) * 10
        
        return signals
    
    def _analyze_engagement(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze engagement elements"""
        
        forms = soup.find_all('form')
        buttons = soup.find_all(['button', 'input'], {'type': ['submit', 'button']})
        
        # CTA analysis
        cta_patterns = [
            'buy', 'shop', 'order', 'subscribe', 'download', 'start', 'try',
            'osta', 'tilaa', 'lataa', 'aloita', 'kokeile', 'varaa'
        ]
        
        ctas = []
        for element in soup.find_all(['a', 'button']):
            text = element.get_text(strip=True).lower()
            if any(pattern in text for pattern in cta_patterns):
                ctas.append(text[:50])
        
        return {
            "forms_count": len(forms),
            "buttons_count": len(buttons),
            "cta_count": len(ctas),
            "cta_samples": ctas[:10],
            "has_comments": bool(soup.find(class_=re.compile('comment'))),
            "has_ratings": bool(soup.find(class_=re.compile('rating|star'))),
            "interactive_elements": self._count_interactive_elements(soup)
        }
    
    def _check_accessibility(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Check accessibility features"""
        
        return {
            "images_with_alt": len([img for img in soup.find_all('img') if img.get('alt')]),
            "images_without_alt": len([img for img in soup.find_all('img') if not img.get('alt')]),
            "has_skip_navigation": bool(soup.find('a', string=re.compile('skip', re.I))),
            "form_labels": len(soup.find_all('label')),
            "aria_landmarks": len(soup.find_all(attrs={'role': True})),
            "lang_attribute": bool(soup.find('html', {'lang': True})),
            "heading_hierarchy_valid": self._check_heading_hierarchy(soup)
        }
    
    # Helper methods
    def _calculate_structure_score(self, soup: BeautifulSoup) -> int:
        """Calculate semantic structure score"""
        score = 0
        if soup.find('header'): score += 10
        if soup.find('nav'): score += 10
        if soup.find('main'): score += 20
        if soup.find('article'): score += 15
        if soup.find('aside'): score += 10
        if soup.find('footer'): score += 10
        if soup.find('section'): score += 10
        
        # Check heading hierarchy
        h1_count = len(soup.find_all('h1'))
        if h1_count == 1: score += 15
        
        return min(100, score)
    
    def _extract_keywords(self, text: str, top_n: int = 20) -> List[str]:
        """Extract keywords using TF-IDF logic"""
        words = re.findall(r'\b[a-zA-ZäöåÄÖÅ]{3,}\b', text.lower())
        word_freq = Counter(words)
        
        # Remove common stop words
        stop_words = {'the', 'and', 'is', 'it', 'to', 'of', 'in', 'for', 'on', 'with',
                     'ja', 'on', 'ei', 'se', 'että', 'ovat', 'oli', 'olla', 'tai'}
        
        keywords = [word for word, _ in word_freq.most_common(top_n * 2) 
                   if word not in stop_words]
        
        return keywords[:top_n]
    
    def _get_image_format(self, src: str) -> str:
        """Detect image format from URL"""
        if not src:
            return 'unknown'
        
        src_lower = src.lower()
        for fmt in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico']:
            if fmt in src_lower:
                return fmt
        return 'unknown'
    
    def _detect_broken_links(self, soup: BeautifulSoup) -> int:
        """Detect potential broken link indicators"""
        broken_indicators = ['404', 'not found', 'error', 'broken']
        count = 0
        
        for link in soup.find_all('a'):
            text = link.get_text(strip=True).lower()
            if any(indicator in text for indicator in broken_indicators):
                count += 1
        
        return count
    
    def _calculate_sentiment(self, text: str) -> str:
        """Simple sentiment analysis"""
        # This is a simplified version - use TextBlob or similar for production
        positive_words = ['great', 'excellent', 'good', 'amazing', 'wonderful', 
                         'hyvä', 'erinomainen', 'loistava', 'hieno']
        negative_words = ['bad', 'poor', 'terrible', 'awful', 'horrible',
                         'huono', 'heikko', 'kamala', 'kauhea']
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _extract_topics(self, text: str) -> List[str]:
        """Extract main topics from text"""
        # Simplified topic extraction
        topics = []
        
        topic_patterns = {
            'technology': ['software', 'app', 'digital', 'tech', 'data', 'ai'],
            'business': ['business', 'company', 'service', 'customer', 'market'],
            'health': ['health', 'medical', 'wellness', 'care', 'treatment'],
            'education': ['education', 'learning', 'course', 'training', 'school'],
            'finance': ['finance', 'money', 'investment', 'payment', 'banking']
        }
        
        text_lower = text.lower()
        for topic, keywords in topic_patterns.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)
        
        return topics[:5]
    
    def _detect_social_links(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """Detect social media links"""
        social_platforms = {
            'facebook': 'facebook.com',
            'twitter': 'twitter.com',
            'linkedin': 'linkedin.com',
            'instagram': 'instagram.com',
            'youtube': 'youtube.com',
            'tiktok': 'tiktok.com'
        }
        
        found = {}
        for platform, domain in social_platforms.items():
            found[platform] = bool(soup.find('a', href=re.compile(domain)))
        
        return found
    
    def _detect_trust_badges(self, soup: BeautifulSoup) -> List[str]:
        """Detect trust badges and certifications"""
        badges = []
        
        badge_patterns = [
            'ssl', 'secure', 'certified', 'verified', 'trusted',
            'iso', 'gdpr', 'pci', 'hipaa'
        ]
        
        for img in soup.find_all('img'):
            alt = (img.get('alt') or '').lower()
            src = (img.get('src') or '').lower()
            
            for pattern in badge_patterns:
                if pattern in alt or pattern in src:
                    badges.append(pattern)
                    break
        
        return list(set(badges))
    
    def _count_interactive_elements(self, soup: BeautifulSoup) -> int:
        """Count interactive elements"""
        interactive_tags = ['button', 'input', 'select', 'textarea', 'video', 'audio', 'canvas']
        count = sum(len(soup.find_all(tag)) for tag in interactive_tags)
        
        # Count elements with onclick handlers
        count += len(soup.find_all(attrs={'onclick': True}))
        
        return count
    
    def _check_heading_hierarchy(self, soup: BeautifulSoup) -> bool:
        """Check if heading hierarchy is valid"""
        headings = []
        for i in range(1, 7):
            for heading in soup.find_all(f'h{i}'):
                headings.append((i, heading.get_text(strip=True)))
        
        if not headings:
            return True
        
        # Check if h1 comes first
        if headings and headings[0][0] != 1:
            return False
        
        # Check for skipped levels
        levels = [h[0] for h in headings]
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] + 1:
                return False
        
        return True

# ==================== OSA 3/6 LOPPUU ====================

# ==================== OSA 4/6 ALKAA ====================
# TECHNICAL JA SEO ANALYSIS

# ==================== TECHNICAL ANALYSIS ====================

class TechnicalAnalyzer:
    """Advanced technical analysis"""
    
    def __init__(self):
        self.tech_patterns = self._load_tech_patterns()
    
    def _load_tech_patterns(self) -> Dict[str, List[Tuple[str, str]]]:
        """Load technology detection patterns"""
        return {
            "cms": [
                ("wordpress", "WordPress"),
                ("wp-content", "WordPress"),
                ("shopify", "Shopify"),
                ("wix", "Wix"),
                ("squarespace", "Squarespace"),
                ("drupal", "Drupal"),
                ("joomla", "Joomla"),
                ("magento", "Magento"),
                ("prestashop", "PrestaShop"),
                ("webflow", "Webflow")
            ],
            "frameworks": [
                ("react", "React"),
                ("__next", "Next.js"),
                ("nuxt", "Nuxt.js"),
                ("vue", "Vue.js"),
                ("angular", "Angular"),
                ("svelte", "Svelte"),
                ("gatsby", "Gatsby"),
                ("ember", "Ember.js"),
                ("backbone", "Backbone.js"),
                ("meteor", "Meteor")
            ],
            "analytics": [
                ("google-analytics.com", "Google Analytics"),
                ("gtag(", "Google Analytics 4"),
                ("googletagmanager.com", "Google Tag Manager"),
                ("facebook.com/tr", "Facebook Pixel"),
                ("connect.facebook.net", "Facebook SDK"),
                ("matomo", "Matomo"),
                ("piwik", "Piwik"),
                ("hotjar", "Hotjar"),
                ("clarity.ms", "Microsoft Clarity"),
                ("segment.com", "Segment"),
                ("mixpanel", "Mixpanel"),
                ("amplitude", "Amplitude")
            ],
            "marketing": [
                ("mailchimp", "Mailchimp"),
                ("hubspot", "HubSpot"),
                ("marketo", "Marketo"),
                ("pardot", "Pardot"),
                ("klaviyo", "Klaviyo"),
                ("activecampaign", "ActiveCampaign"),
                ("convertkit", "ConvertKit"),
                ("drip", "Drip"),
                ("sendinblue", "Sendinblue")
            ],
            "ecommerce": [
                ("shopify", "Shopify"),
                ("woocommerce", "WooCommerce"),
                ("bigcommerce", "BigCommerce"),
                ("magento", "Magento"),
                ("opencart", "OpenCart"),
                ("prestashop", "PrestaShop"),
                ("stripe", "Stripe"),
                ("paypal", "PayPal"),
                ("square", "Square"),
                ("razorpay", "Razorpay")
            ],
            "cdn": [
                ("cloudflare", "Cloudflare"),
                ("cloudfront", "Amazon CloudFront"),
                ("fastly", "Fastly"),
                ("akamai", "Akamai"),
                ("cdn77", "CDN77"),
                ("bunny.net", "Bunny CDN"),
                ("jsdelivr", "jsDelivr")
            ],
            "hosting": [
                ("amazonaws.com", "AWS"),
                ("azure", "Microsoft Azure"),
                ("googleusercontent", "Google Cloud"),
                ("digitalocean", "DigitalOcean"),
                ("heroku", "Heroku"),
                ("netlify", "Netlify"),
                ("vercel", "Vercel"),
                ("github.io", "GitHub Pages")
            ]
        }
    
    async def analyze_technical(self, soup: BeautifulSoup, html: str, url: str) -> Dict[str, Any]:
        """Comprehensive technical analysis"""
        
        return {
            "technologies": self._detect_technologies(soup, html),
            "performance": self._analyze_performance(soup, html),
            "security": self._analyze_security(soup, url),
            "meta_tags": self._analyze_meta_tags(soup),
            "structured_data": self._analyze_structured_data(soup),
            "javascript": self._analyze_javascript(soup, html),
            "css": self._analyze_css(soup),
            "api_endpoints": self._detect_api_endpoints(html),
            "cookies": self._analyze_cookies(soup),
            "compliance": self._check_compliance(soup)
        }
    
    def _detect_technologies(self, soup: BeautifulSoup, html: str) -> Dict[str, List[str]]:
        """Detect technologies used"""
        
        detected = defaultdict(list)
        html_lower = html.lower()
        
        # Check patterns
        for category, patterns in self.tech_patterns.items():
            for pattern, name in patterns:
                if pattern in html_lower:
                    if name not in detected[category]:
                        detected[category].append(name)
        
        # Check meta generator
        generator = soup.find('meta', {'name': 'generator'})
        if generator:
            content = generator.get('content', '').lower()
            for category, patterns in self.tech_patterns.items():
                for pattern, name in patterns:
                    if pattern in content:
                        if name not in detected[category]:
                            detected[category].append(name)
        
        # Check JavaScript libraries
        scripts = soup.find_all('script', src=True)
        for script in scripts:
            src = script['src'].lower()
            
            # Common libraries
            if 'jquery' in src:
                detected['libraries'].append('jQuery')
            if 'bootstrap' in src:
                detected['libraries'].append('Bootstrap')
            if 'tailwind' in src:
                detected['libraries'].append('Tailwind CSS')
            if 'd3' in src:
                detected['libraries'].append('D3.js')
            if 'three' in src:
                detected['libraries'].append('Three.js')
        
        return dict(detected)
    
    def _analyze_performance(self, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """Analyze performance indicators"""
        
        # Page size
        page_size = len(html.encode('utf-8'))
        
        # Resource counts
        scripts = soup.find_all('script')
        stylesheets = soup.find_all('link', {'rel': 'stylesheet'})
        images = soup.find_all('img')
        
        # Performance features
        performance = {
            "page_size_bytes": page_size,
            "page_size_kb": round(page_size / 1024, 2),
            "script_count": len(scripts),
            "stylesheet_count": len(stylesheets),
            "image_count": len(images),
            "inline_scripts": len([s for s in scripts if not s.get('src')]),
            "external_scripts": len([s for s in scripts if s.get('src')]),
            "async_scripts": len([s for s in scripts if s.get('async') is not None]),
            "defer_scripts": len([s for s in scripts if s.get('defer') is not None]),
            "lazy_loaded_images": len([img for img in images if img.get('loading') == 'lazy']),
            "preload_hints": len(soup.find_all('link', {'rel': 'preload'})),
            "prefetch_hints": len(soup.find_all('link', {'rel': 'prefetch'})),
            "dns_prefetch": len(soup.find_all('link', {'rel': 'dns-prefetch'})),
            "critical_css": bool(soup.find('style', string=re.compile('critical|above-the-fold'))),
            "resource_hints_score": 0
        }
        
        # Calculate resource hints score
        hints_score = 0
        if performance['lazy_loaded_images'] > 0: hints_score += 20
        if performance['async_scripts'] > 0: hints_score += 15
        if performance['defer_scripts'] > 0: hints_score += 15
        if performance['preload_hints'] > 0: hints_score += 20
        if performance['dns_prefetch'] > 0: hints_score += 15
        if performance['critical_css']: hints_score += 15
        
        performance['resource_hints_score'] = min(100, hints_score)
        
        return performance
    
    def _analyze_security(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Analyze security features"""
        
        parsed_url = urlparse(url)
        
        security = {
            "https": parsed_url.scheme == 'https',
            "hsts": False,  # Would need response headers
            "csp": bool(soup.find('meta', {'http-equiv': 'Content-Security-Policy'})),
            "x_frame_options": bool(soup.find('meta', {'http-equiv': 'X-Frame-Options'})),
            "sri": len(soup.find_all(attrs={'integrity': True})),
            "crossorigin": len(soup.find_all(attrs={'crossorigin': True})),
            "mixed_content": self._check_mixed_content(soup, parsed_url.scheme == 'https'),
            "external_forms": self._check_external_forms(soup, parsed_url.netloc),
            "security_headers_meta": self._check_security_meta(soup)
        }
        
        # Calculate security score
        score = 0
        if security['https']: score += 30
        if security['csp']: score += 20
        if security['sri'] > 0: score += 15
        if not security['mixed_content']: score += 20
        if not security['external_forms']: score += 15
        
        security['security_score'] = min(100, score)
        
        return security
    
    def _analyze_meta_tags(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze meta tags"""
        
        meta_tags = {
            "title": None,
            "description": None,
            "keywords": None,
            "author": None,
            "viewport": None,
            "robots": None,
            "canonical": None,
            "og_tags": {},
            "twitter_tags": {},
            "other_meta": {}
        }
        
        # Title
        title_tag = soup.find('title')
        if title_tag:
            meta_tags['title'] = {
                "content": title_tag.get_text(strip=True),
                "length": len(title_tag.get_text(strip=True))
            }
        
        # Standard meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            prop = meta.get('property', '').lower()
            content = meta.get('content', '')
            
            if name == 'description':
                meta_tags['description'] = {
                    "content": content[:200],
                    "length": len(content)
                }
            elif name == 'keywords':
                meta_tags['keywords'] = content.split(',')[:10]
            elif name == 'author':
                meta_tags['author'] = content
            elif name == 'viewport':
                meta_tags['viewport'] = content
            elif name == 'robots':
                meta_tags['robots'] = content
            elif prop.startswith('og:'):
                meta_tags['og_tags'][prop] = content[:200]
            elif name.startswith('twitter:'):
                meta_tags['twitter_tags'][name] = content[:200]
            elif name and content:
                meta_tags['other_meta'][name] = content[:100]
        
        # Canonical
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical:
            meta_tags['canonical'] = canonical.get('href')
        
        # Alternate languages
        alternates = soup.find_all('link', {'rel': 'alternate', 'hreflang': True})
        if alternates:
            meta_tags['hreflang'] = [
                {"lang": alt.get('hreflang'), "url": alt.get('href')}
                for alt in alternates[:10]
            ]
        
        return meta_tags
    
    def _analyze_structured_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze structured data (JSON-LD, microdata)"""
        
        structured = {
            "json_ld": [],
            "microdata": {},
            "rdfa": {},
            "types_found": []
        }
        
        # JSON-LD
        json_ld_scripts = soup.find_all('script', {'type': 'application/ld+json'})
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                
                # Extract type
                if '@type' in data:
                    structured['types_found'].append(data['@type'])
                
                # Store simplified version
                structured['json_ld'].append({
                    "@type": data.get('@type'),
                    "@context": data.get('@context'),
                    "properties": list(data.keys())[:10]
                })
            except Exception as e:
                logger.debug(f"JSON-LD parse error: {e}")
        
        # Microdata
        items_with_scope = soup.find_all(attrs={'itemscope': True})
        for item in items_with_scope[:10]:
            item_type = item.get('itemtype', 'unknown')
            structured['microdata'][item_type] = True
            structured['types_found'].append(item_type.split('/')[-1] if '/' in item_type else item_type)
        
        # Count properties
        structured['microdata_properties'] = len(soup.find_all(attrs={'itemprop': True}))
        
        # RDFa
        rdfa_elements = soup.find_all(attrs={'typeof': True})
        for element in rdfa_elements[:10]:
            rdfa_type = element.get('typeof')
            structured['rdfa'][rdfa_type] = True
            structured['types_found'].append(rdfa_type)
        
        # Deduplicate types
        structured['types_found'] = list(set(structured['types_found']))
        
        return structured
    
    def _analyze_javascript(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze JavaScript usage"""
        
        scripts = soup.find_all('script')
        
        js_analysis = {
            "total_scripts": len(scripts),
            "inline_scripts": 0,
            "external_scripts": 0,
            "async_scripts": 0,
            "defer_scripts": 0,
            "module_scripts": 0,
            "nomodule_scripts": 0,
            "frameworks_detected": [],
            "minified_scripts": 0,
            "total_inline_size": 0
        }
        
        for script in scripts:
            if script.get('src'):
                js_analysis['external_scripts'] += 1
                
                src = script['src'].lower()
                if '.min.js' in src:
                    js_analysis['minified_scripts'] += 1
                
                # Detect frameworks
                if 'react' in src:
                    js_analysis['frameworks_detected'].append('React')
                elif 'vue' in src:
                    js_analysis['frameworks_detected'].append('Vue')
                elif 'angular' in src:
                    js_analysis['frameworks_detected'].append('Angular')
            else:
                js_analysis['inline_scripts'] += 1
                if script.string:
                    js_analysis['total_inline_size'] += len(script.string)
            
            # Attributes
            if script.get('async') is not None:
                js_analysis['async_scripts'] += 1
            if script.get('defer') is not None:
                js_analysis['defer_scripts'] += 1
            if script.get('type') == 'module':
                js_analysis['module_scripts'] += 1
            if script.get('nomodule') is not None:
                js_analysis['nomodule_scripts'] += 1
        
        # Deduplicate frameworks
        js_analysis['frameworks_detected'] = list(set(js_analysis['frameworks_detected']))
        
        return js_analysis
    
    def _analyze_css(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze CSS usage"""
        
        stylesheets = soup.find_all('link', {'rel': 'stylesheet'})
        inline_styles = soup.find_all('style')
        
        css_analysis = {
            "external_stylesheets": len(stylesheets),
            "inline_styles": len(inline_styles),
            "critical_css": False,
            "css_frameworks": [],
            "inline_style_attributes": len(soup.find_all(attrs={'style': True})),
            "media_queries": [],
            "total_inline_size": 0
        }
        
        # Detect CSS frameworks
        for link in stylesheets:
            href = link.get('href', '').lower()
            if 'bootstrap' in href:
                css_analysis['css_frameworks'].append('Bootstrap')
            elif 'tailwind' in href:
                css_analysis['css_frameworks'].append('Tailwind')
            elif 'bulma' in href:
                css_analysis['css_frameworks'].append('Bulma')
            elif 'foundation' in href:
                css_analysis['css_frameworks'].append('Foundation')
            
            # Media queries
            media = link.get('media')
            if media and media != 'all':
                css_analysis['media_queries'].append(media)
        
        # Check for critical CSS
        for style in inline_styles:
            if style.string:
                css_analysis['total_inline_size'] += len(style.string)
                if 'critical' in style.string or 'above-the-fold' in style.string:
                    css_analysis['critical_css'] = True
        
        # Deduplicate
        css_analysis['css_frameworks'] = list(set(css_analysis['css_frameworks']))
        css_analysis['media_queries'] = list(set(css_analysis['media_queries']))[:5]
        
        return css_analysis
    
    def _detect_api_endpoints(self, html: str) -> List[str]:
        """Detect API endpoints in HTML/JS"""
        
        # Common API patterns
        api_patterns = [
            r'/api/[\w/]+',
            r'/v\d+/[\w/]+',
            r'\.json\b',
            r'/graphql',
            r'/rest/[\w/]+',
            r'/services/[\w/]+'
        ]
        
        endpoints = []
        for pattern in api_patterns:
            matches = re.findall(pattern, html)
            endpoints.extend(matches)
        
        # Deduplicate and limit
        return list(set(endpoints))[:20]
    def _analyze_cookies(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze cookie usage indicators"""
        
        # Look for cookie consent banners
        cookie_patterns = ['cookie', 'gdpr', 'consent', 'privacy', 'tracking']
        cookie_elements = []
        
        for pattern in cookie_patterns:
            elements = soup.find_all(class_=re.compile(pattern, re.I))
            cookie_elements.extend(elements[:5])
        
        return {
            "has_cookie_banner": len(cookie_elements) > 0,
            "cookie_banner_text": cookie_elements[0].get_text(strip=True)[:200] if cookie_elements else None,
            "has_cookie_policy": bool(soup.find('a', string=re.compile('cookie', re.I)))
        }
    
    def _check_compliance(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Check regulatory compliance indicators"""
        
        return {
            "gdpr_indicators": {
                "privacy_policy": bool(soup.find('a', string=re.compile('privacy|tietosuoja', re.I))),
                "cookie_consent": bool(soup.find(string=re.compile('cookie consent|evästeet', re.I))),
                "data_controller": bool(soup.find(string=re.compile('data controller|rekisterinpitäjä', re.I))),
                "rights_mention": bool(soup.find(string=re.compile('your rights|oikeutesi', re.I)))
            },
            "accessibility": {
                "wcag_mention": bool(soup.find(string=re.compile('wcag', re.I))),
                "accessibility_statement": bool(soup.find('a', string=re.compile('accessibility|saavutettavuus', re.I)))
            }
        }
    
    def _check_mixed_content(self, soup: BeautifulSoup, is_https: bool) -> bool:
        """Check for mixed content issues"""
        if not is_https:
            return False
        
        # Check for HTTP resources on HTTPS page
        for tag, attr in [('img', 'src'), ('script', 'src'), ('link', 'href'), ('iframe', 'src')]:
            for element in soup.find_all(tag, {attr: True}):
                url = element.get(attr)
                if url and url.startswith('http://'):
                    return True
        
        return False
    
    def _check_external_forms(self, soup: BeautifulSoup, domain: str) -> bool:
        """Check for forms posting to external domains"""
        for form in soup.find_all('form', {'action': True}):
            action = form.get('action')
            if action and action.startswith(('http://', 'https://')):
                if domain not in action:
                    return True
        
        return False
    
    def _check_security_meta(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """Check security-related meta tags"""
        return {
            "x_ua_compatible": bool(soup.find('meta', {'http-equiv': 'X-UA-Compatible'})),
            "x_content_type": bool(soup.find('meta', {'http-equiv': 'X-Content-Type-Options'})),
            "referrer_policy": bool(soup.find('meta', {'name': 'referrer'}))
        }

# ==================== SEO ANALYSIS ====================

class SEOAnalyzer:
    """Advanced SEO analysis"""
    
    async def analyze_seo(self, soup: BeautifulSoup, url: str, content_analysis: Dict) -> Dict[str, Any]:
        """Comprehensive SEO analysis"""
        
        return {
            "title_analysis": self._analyze_title(soup),
            "meta_description": self._analyze_meta_description(soup),
            "headings": self._analyze_headings(soup),
            "url_analysis": self._analyze_url(url),
            "images": self._analyze_images_seo(soup),
            "internal_linking": self._analyze_internal_linking(soup, url),
            "schema_markup": self._analyze_schema(soup),
            "canonicalization": self._analyze_canonicalization(soup, url),
            "indexability": self._analyze_indexability(soup),
            "mobile_optimization": self._analyze_mobile(soup),
            "page_speed_indicators": self._analyze_speed_indicators(soup),
            "content_seo": self._analyze_content_seo(content_analysis),
            "social_signals": self._analyze_social_signals(soup),
            "seo_score": 0  # Will be calculated
        }
    
    def _analyze_title(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze title tag"""
        title = soup.find('title')
        
        if not title:
            return {
                "exists": False,
                "content": None,
                "length": 0,
                "issues": ["Missing title tag"]
            }
        
        title_text = title.get_text(strip=True)
        length = len(title_text)
        
        issues = []
        if length < 30:
            issues.append("Title too short (recommended: 30-60 characters)")
        elif length > 60:
            issues.append("Title too long (recommended: 30-60 characters)")
        
        if '|' not in title_text and '-' not in title_text:
            issues.append("Consider adding brand separator")
        
        return {
            "exists": True,
            "content": title_text,
            "length": length,
            "word_count": len(title_text.split()),
            "has_brand": '|' in title_text or '-' in title_text,
            "issues": issues,
            "score": 100 if not issues else max(0, 100 - len(issues) * 25)
        }
    
    def _analyze_meta_description(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze meta description"""
        meta_desc = soup.find('meta', {'name': 'description'})
        
        if not meta_desc:
            return {
                "exists": False,
                "content": None,
                "length": 0,
                "issues": ["Missing meta description"]
            }
        
        content = meta_desc.get('content', '')
        length = len(content)
        
        issues = []
        if length < 120:
            issues.append("Meta description too short (recommended: 120-160 characters)")
        elif length > 160:
            issues.append("Meta description too long (recommended: 120-160 characters)")
        
        if not content:
            issues.append("Empty meta description")
        
        return {
            "exists": True,
            "content": content[:200],
            "length": length,
            "word_count": len(content.split()),
            "issues": issues,
            "score": 100 if not issues else max(0, 100 - len(issues) * 25)
        }
    
    def _analyze_headings(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze heading structure"""
        headings = {}
        issues = []
        
        for level in range(1, 7):
            h_tags = soup.find_all(f'h{level}')
            if h_tags:
                headings[f'h{level}'] = {
                    "count": len(h_tags),
                    "texts": [h.get_text(strip=True)[:100] for h in h_tags[:5]]
                }
        
        # Check for issues
        h1_tags = soup.find_all('h1')
        h1_count = len(h1_tags)
        
        if h1_count == 0:
            issues.append("Missing H1 tag")
        elif h1_count > 1:
            issues.append(f"Multiple H1 tags found ({h1_count})")
        
        # Check hierarchy
        if 'h3' in headings and 'h2' not in headings:
            issues.append("H3 found without H2 (broken hierarchy)")
        
        return {
            "structure": headings,
            "h1_count": h1_count,
            "total_headings": sum(h['count'] for h in headings.values()) if headings else 0,
            "issues": issues,
            "hierarchy_valid": len(issues) == 0,
            "score": 100 if not issues else max(0, 100 - len(issues) * 20)
        }
    
    def _analyze_url(self, url: str) -> Dict[str, Any]:
        """Analyze URL structure"""
        parsed = urlparse(url)
        path = parsed.path
        
        issues = []
        
        # Check URL length
        if len(url) > 100:
            issues.append("URL longer than 100 characters")
        
        # Check for parameters
        if parsed.query:
            issues.append("URL contains parameters")
        
        # Check for underscores
        if '_' in path:
            issues.append("URL contains underscores (use hyphens instead)")
        
        # Check depth
        depth = len([p for p in path.split('/') if p])
        if depth > 3:
            issues.append(f"Deep URL structure (depth: {depth})")
        
        return {
            "url": url,
            "length": len(url),
            "depth": depth,
            "has_parameters": bool(parsed.query),
            "has_underscores": '_' in path,
            "is_https": parsed.scheme == 'https',
            "issues": issues,
            "score": 100 if not issues else max(0, 100 - len(issues) * 20)
        }
    
    def _analyze_images_seo(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze images for SEO"""
        images = soup.find_all('img')
        
        with_alt = 0
        without_alt = 0
        alt_too_long = 0
        with_title = 0
        
        for img in images:
            alt = img.get('alt', '')
            if alt:
                with_alt += 1
                if len(alt) > 125:
                    alt_too_long += 1
            else:
                without_alt += 1
            
            if img.get('title'):
                with_title += 1
        
        issues = []
        if without_alt > 0:
            issues.append(f"{without_alt} images without alt text")
        
        if alt_too_long > 0:
            issues.append(f"{alt_too_long} images with alt text > 125 characters")
        
        alt_percentage = (with_alt / len(images) * 100) if images else 100
        
        return {
            "total": len(images),
            "with_alt": with_alt,
            "without_alt": without_alt,
            "alt_percentage": round(alt_percentage, 1),
            "with_title": with_title,
            "alt_too_long": alt_too_long,
            "issues": issues,
            "score": min(100, alt_percentage)
        }
    
    def _analyze_internal_linking(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Analyze internal linking structure"""
        domain = extract_domain(url)
        links = soup.find_all('a', href=True)
        
        internal_links = []
        for link in links:
            href = link['href']
            if not href.startswith(('http://', 'https://', 'mailto:', 'tel:', '#')):
                internal_links.append(href)
            elif domain in href:
                internal_links.append(href)
        
        unique_internal = list(set(internal_links))
        
        # Safe division to avoid zero division
        section_count = max(len(soup.find_all(['section', 'article', 'div'])), 1)
        
        return {
            "total_internal": len(internal_links),
            "unique_internal": len(unique_internal),
            "average_per_section": len(internal_links) / section_count,
            "has_breadcrumbs": bool(soup.find(class_=re.compile('breadcrumb'))),
            "has_sitemap_link": bool(soup.find('a', string=re.compile('sitemap', re.I))),
            "score": min(100, len(unique_internal) * 5)
        }
    
    def _analyze_schema(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze schema markup"""
        json_ld = soup.find_all('script', type='application/ld+json')
        microdata = soup.find_all(attrs={'itemscope': True})
        
        schema_types = []
        for script in json_ld:
            try:
                data = json.loads(script.string)
                if '@type' in data:
                    schema_types.append(data['@type'])
            except:
                pass
        
        return {
            "has_schema": len(json_ld) > 0 or len(microdata) > 0,
            "json_ld_count": len(json_ld),
            "microdata_count": len(microdata),
            "types": schema_types[:10],
            "score": 100 if schema_types else 0
        }
    
    def _analyze_canonicalization(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Analyze canonical setup"""
        canonical = soup.find('link', rel='canonical')
        
        if not canonical:
            return {
                "has_canonical": False,
                "canonical_url": None,
                "self_referencing": False,
                "issues": ["Missing canonical tag"],
                "score": 0
            }
        
        canonical_url = canonical.get('href')
        self_referencing = canonical_url == url
        
        issues = []
        if not self_referencing and canonical_url != url.rstrip('/'):
            issues.append("Canonical points to different URL")
        
        return {
            "has_canonical": True,
            "canonical_url": canonical_url,
            "self_referencing": self_referencing,
            "issues": issues,
            "score": 100 if self_referencing else 50
        }
    
    def _analyze_indexability(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze indexability"""
        robots_meta = soup.find('meta', {'name': 'robots'})
        
        indexable = True
        issues = []
        
        if robots_meta:
            content = robots_meta.get('content', '').lower()
            if 'noindex' in content:
                indexable = False
                issues.append("Page marked as noindex")
            if 'nofollow' in content:
                issues.append("Page marked as nofollow")
        
        return {
            "indexable": indexable,
            "robots_meta": robots_meta.get('content') if robots_meta else None,
            "issues": issues,
            "score": 100 if indexable and not issues else 0
        }
    
    def _analyze_mobile(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze mobile optimization"""
        viewport = soup.find('meta', {'name': 'viewport'})
        
        issues = []
        if not viewport:
            issues.append("Missing viewport meta tag")
        
        # Check for mobile-unfriendly elements
        if soup.find_all('frame'):
            issues.append("Uses frames (not mobile-friendly)")
        
        if soup.find_all('object'):
            issues.append("Uses Flash/plugins (not mobile-friendly)")
        
        return {
            "has_viewport": bool(viewport),
            "viewport_content": viewport.get('content') if viewport else None,
            "issues": issues,
            "score": 100 if not issues else max(0, 100 - len(issues) * 30)
        }
    
    def _analyze_speed_indicators(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page speed indicators"""
        
        indicators = {
            "lazy_loading": len(soup.find_all(loading='lazy')),
            "async_scripts": len(soup.find_all('script', async_=True)),
            "defer_scripts": len(soup.find_all('script', defer=True)),
            "preload": len(soup.find_all('link', rel='preload')),
            "prefetch": len(soup.find_all('link', rel='prefetch')),
            "preconnect": len(soup.find_all('link', rel='preconnect'))
        }
        
        score = 0
        if indicators['lazy_loading'] > 0: score += 20
        if indicators['async_scripts'] > 0: score += 20
        if indicators['defer_scripts'] > 0: score += 20
        if indicators['preload'] > 0: score += 20
        if indicators['preconnect'] > 0: score += 20
        
        indicators['score'] = min(100, score)
        
        return indicators
    
    def _analyze_content_seo(self, content_analysis: Dict) -> Dict[str, Any]:
        """Analyze content for SEO"""
        
        text_stats = content_analysis.get('text_stats', {})
        word_count = text_stats.get('word_count', 0)
        
        issues = []
        if word_count < 300:
            issues.append("Thin content (< 300 words)")
        
        keyword_density = {}
        if 'keywords' in text_stats:
            for keyword in text_stats['keywords'][:10]:
                # Simplified density calculation
                keyword_density[keyword] = "~1-3%"  # Would need actual calculation
        
        return {
            "word_count": word_count,
            "keyword_density": keyword_density,
            "readability_score": text_stats.get('flesch_reading_ease', 0),
            "issues": issues,
            "score": min(100, word_count / 10) if word_count > 300 else word_count / 3
        }
    
    def _analyze_social_signals(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze social media optimization"""
        
        og_tags = {}
        twitter_tags = {}
        
        for meta in soup.find_all('meta'):
            prop = meta.get('property', '')
            name = meta.get('name', '')
            
            if prop.startswith('og:'):
                og_tags[prop] = bool(meta.get('content'))
            elif name.startswith('twitter:'):
                twitter_tags[name] = bool(meta.get('content'))
        
        og_complete = all(og_tags.get(tag) for tag in ['og:title', 'og:description', 'og:image'])
        twitter_complete = all(twitter_tags.get(tag) for tag in ['twitter:card', 'twitter:title'])
        
        return {
            "open_graph": {
                "complete": og_complete,
                "tags": list(og_tags.keys())
            },
            "twitter_cards": {
                "complete": twitter_complete,
                "tags": list(twitter_tags.keys())
            },
            "score": (50 if og_complete else 0) + (50 if twitter_complete else 0)
        }

# ==================== OSA 4/6 LOPPUU ====================

# ==================== OSA 5/6 ALKAA ====================
# AI ANALYSIS JA LIGHTHOUSE INTEGRATION

# ==================== AI ANALYZER ====================

class AIAnalyzer:
    """Advanced AI-powered analysis"""
    
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and OPENAI_API_KEY:
            self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    async def analyze_with_ai(
        self, 
        analysis_data: Dict[str, Any],
        language: str = 'fi'
    ) -> Optional[AIInsights]:
        """Generate AI insights using GPT-4"""
        
        if not self.client:
            logger.warning("OpenAI client not available")
            return None
        
        try:
            # Prepare summary for AI
            summary = self._prepare_summary(analysis_data)
            
            # Create prompt
            prompt = self._create_prompt(summary, language)
            
            # Call OpenAI
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": self._get_system_prompt(language)},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )
            
            # Parse response
            # Parse response safely (handle code fences and partial JSON)
            raw = response.choices[0].message.content or "{}"
            try:
                # Extract JSON inside ```json ... ``` if present
                import re, json
                m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw)
                if m:
                    raw_json = m.group(1)
                else:
                    # Trim to last closing brace to avoid stray text after JSON
                    end = raw.rfind('}')
                    raw_json = raw[:end+1] if end != -1 else raw
                insights_data = json.loads(raw_json)
            except Exception as e:
                logger.error(f"AI enhancement failed: {e}")
                # Fallback: minimal structure to keep API running
                insights_data = {
                    "executive_summary": "",
                    "strengths": [],
                    "weaknesses": [],
                    "opportunities": [],
                    "threats": [],
                    "market_position": "",
                    "competitive_advantages": [],
                    "improvement_recommendations": []
                }
            ai_requests.labels(provider='openai', model='gpt-4').inc()
            
            # Create AIInsights object
            return AIInsights(**insights_data)
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            error_counter.labels(error_type='ai_analysis').inc()
            return None
    
    def _prepare_summary(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare analysis summary for AI"""
        
        return {
            "url": analysis_data.get("url"),
            "technologies": analysis_data.get("technical_analysis", {}).get("technologies", {}),
            "performance": {
                "page_size_kb": analysis_data.get("technical_analysis", {}).get("performance", {}).get("page_size_kb"),
                "script_count": analysis_data.get("technical_analysis", {}).get("performance", {}).get("script_count"),
                "resource_hints_score": analysis_data.get("technical_analysis", {}).get("performance", {}).get("resource_hints_score")
            },
            "seo": {
                "title": analysis_data.get("seo_analysis", {}).get("title_analysis", {}),
                "meta_description": analysis_data.get("seo_analysis", {}).get("meta_description", {}),
                "headings": analysis_data.get("seo_analysis", {}).get("headings", {}),
                "schema": analysis_data.get("seo_analysis", {}).get("schema_markup", {})
            },
            "content": {
                "word_count": analysis_data.get("content_analysis", {}).get("text_stats", {}).get("word_count"),
                "readability": analysis_data.get("content_analysis", {}).get("text_stats", {}).get("flesch_reading_ease"),
                "keywords": analysis_data.get("content_analysis", {}).get("text_stats", {}).get("keywords", [])[:10],
                "language": analysis_data.get("content_analysis", {}).get("text_stats", {}).get("language")
            },
            "engagement": analysis_data.get("content_analysis", {}).get("engagement", {}),
            "quality_signals": analysis_data.get("content_analysis", {}).get("quality_signals", {}),
            "security": analysis_data.get("technical_analysis", {}).get("security", {})
        }
    
    def _create_prompt(self, summary: Dict[str, Any], language: str) -> str:
        """Create AI analysis prompt"""
        
        if language == 'en':
            return f"""
Analyze this competitor website data and provide comprehensive insights:

{json.dumps(summary, indent=2, ensure_ascii=False)}

Provide a JSON response with the following structure:
{{
    "summary": "3-4 sentence executive summary of the website's current state and market position",
    "strengths": ["list of 5-7 key strengths based on the data"],
    "weaknesses": ["list of 5-7 key weaknesses identified"],
    "opportunities": ["list of 4-6 market opportunities"],
    "threats": ["list of 3-4 potential threats"],
    "market_position": "Assessment of market positioning and competitive stance",
    "competitive_advantages": ["list of 3-5 unique competitive advantages"],
    "improvement_recommendations": [
        {{
            "title": "Recommendation title",
            "description": "Detailed description",
            "priority": "high/medium/low",
            "effort": "low/medium/high",
            "impact": "low/medium/high",
            "timeline": "immediate/short-term/long-term"
        }}
    ],
    "estimated_traffic": {{
        "organic": 40,
        "direct": 25,
        "social": 15,
        "paid": 10,
        "referral": 10
    }},
    "technology_score": 7,
    "content_strategy": "Assessment of content strategy effectiveness",
    "user_experience_score": 8
}}

Focus on actionable insights and specific observations from the data.
"""
        else:  # Finnish
            return f"""
Analysoi tämä kilpailijasivuston data ja tuota kattavat näkemykset:

{json.dumps(summary, indent=2, ensure_ascii=False)}

Anna JSON-vastaus seuraavalla rakenteella:
{{
    "summary": "3-4 lauseen yhteenveto sivuston nykytilasta ja markkina-asemasta",
    "strengths": ["lista 5-7 keskeisestä vahvuudesta datan perusteella"],
    "weaknesses": ["lista 5-7 tunnistetusta heikkoudesta"],
    "opportunities": ["lista 4-6 markkinamahdollisuudesta"],
    "threats": ["lista 3-4 potentiaalisesta uhasta"],
    "market_position": "Arvio markkina-asemoinnista ja kilpailullisesta asemasta",
    "competitive_advantages": ["lista 3-5 ainutlaatuisesta kilpailuedusta"],
    "improvement_recommendations": [
        {{
            "title": "Suosituksen otsikko",
            "description": "Yksityiskohtainen kuvaus",
            "priority": "high/medium/low",
            "effort": "low/medium/high",
            "impact": "low/medium/high",
            "timeline": "immediate/short-term/long-term"
        }}
    ],
    "estimated_traffic": {{
        "organic": 40,
        "direct": 25,
        "social": 15,
        "paid": 10,
        "referral": 10
    }},
    "technology_score": 7,
    "content_strategy": "Arvio sisältöstrategian tehokkuudesta",
    "user_experience_score": 8
}}

Keskity toiminnallisiin näkemyksiin ja konkreettisiin havaintoihin datasta.
"""
    
    def _get_system_prompt(self, language: str) -> str:
        """Get system prompt for AI"""
        
        if language == 'en':
            return """You are an expert digital marketing and competitive intelligence analyst. 
            Analyze website data to provide actionable insights for business improvement. 
            Focus on practical recommendations backed by data. 
            Always respond in valid JSON format."""
        else:
            return """Olet digitaalisen markkinoinnin ja kilpailija-analyysin asiantuntija. 
            Analysoi sivustodataa tuottaaksesi toiminnallisia näkemyksiä liiketoiminnan parantamiseen. 
            Keskity käytännöllisiin suosituksiin, jotka perustuvat dataan. 
            Vastaa aina validissa JSON-muodossa."""

# ==================== LIGHTHOUSE INTEGRATION ====================

class LighthouseAnalyzer:
    """Google Lighthouse integration for performance analysis"""
    
    async def run_lighthouse(self, url: str) -> Optional[Dict[str, Any]]:
        """Run Lighthouse audit"""
        
        if not LIGHTHOUSE_ENABLED:
            return None
        
        try:
            import subprocess
            import json
            
            # Run Lighthouse CLI
            result = await asyncio.create_subprocess_exec(
                'lighthouse',
                url,
                '--output=json',
                '--quiet',
                '--chrome-flags=--headless',
                '--only-categories=performance,accessibility,best-practices,seo',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                logger.error(f"Lighthouse failed: {stderr.decode()}")
                return None
            
            # Parse results
            lighthouse_data = json.loads(stdout.decode())
            
            # Extract key metrics
            return self._extract_metrics(lighthouse_data)
            
        except FileNotFoundError:
            logger.warning("Lighthouse CLI not found")
            return None
        except Exception as e:
            logger.error(f"Lighthouse error: {e}")
            return None
    
    def _extract_metrics(self, lighthouse_data: Dict) -> Dict[str, Any]:
        """Extract key metrics from Lighthouse data"""
        
        categories = lighthouse_data.get('categories', {})
        audits = lighthouse_data.get('audits', {})
        
        metrics = {
            "scores": {
                "performance": categories.get('performance', {}).get('score', 0) * 100,
                "accessibility": categories.get('accessibility', {}).get('score', 0) * 100,
                "best_practices": categories.get('best-practices', {}).get('score', 0) * 100,
                "seo": categories.get('seo', {}).get('score', 0) * 100
            },
            "metrics": {}
        }
        
        # Core Web Vitals
        if 'first-contentful-paint' in audits:
            metrics['metrics']['fcp'] = audits['first-contentful-paint'].get('numericValue')
        
        if 'largest-contentful-paint' in audits:
            metrics['metrics']['lcp'] = audits['largest-contentful-paint'].get('numericValue')
        
        if 'cumulative-layout-shift' in audits:
            metrics['metrics']['cls'] = audits['cumulative-layout-shift'].get('numericValue')
        
        if 'total-blocking-time' in audits:
            metrics['metrics']['tbt'] = audits['total-blocking-time'].get('numericValue')
        
        if 'speed-index' in audits:
            metrics['metrics']['speed_index'] = audits['speed-index'].get('numericValue')
        
        if 'interactive' in audits:
            metrics['metrics']['tti'] = audits['interactive'].get('numericValue')
        
        # Opportunities
        opportunities = []
        for audit_id, audit in audits.items():
            if audit.get('score', 1) < 0.9 and audit.get('details', {}).get('type') == 'opportunity':
                opportunities.append({
                    "id": audit_id,
                    "title": audit.get('title'),
                    "savings": audit.get('details', {}).get('overallSavingsMs', 0)
                })
        
        metrics['opportunities'] = sorted(opportunities, key=lambda x: x['savings'], reverse=True)[:5]
        
        # Diagnostics
        diagnostics = []
        for audit_id, audit in audits.items():
            if audit.get('score', 1) < 0.5 and 'diagnostic' in audit.get('categories', []):
                diagnostics.append({
                    "id": audit_id,
                    "title": audit.get('title'),
                    "description": audit.get('description')
                })
        
        metrics['diagnostics'] = diagnostics[:5]
        
        return metrics

# ==================== COMPETITOR FINDER ====================

class CompetitorFinder:
    """Find and analyze competitors"""
    
    async def find_competitors(
        self, 
        url: str, 
        industry: Optional[str] = None
    ) -> List[str]:
        """Find competitor websites"""
        
        domain = extract_domain(url)
        competitors = []
        
        # Method 1: Search for similar sites
        if industry:
            search_query = f"{industry} companies Finland"
            competitors.extend(await self._search_competitors(search_query))
        
        # Method 2: Check backlink sources (would need API)
        # competitors.extend(await self._check_backlinks(domain))
        
        # Method 3: Industry directories (predefined)
        if industry:
            competitors.extend(self._get_industry_competitors(industry))
        
        # Remove duplicates and own domain
        competitors = [c for c in set(competitors) if domain not in c]
        
        return competitors[:10]
    
    async def _search_competitors(self, query: str) -> List[str]:
        """Search for competitors using search engines"""
        
        # This would typically use a search API
        # For now, return empty list
        return []
    
    def _get_industry_competitors(self, industry: str) -> List[str]:
        """Get known competitors by industry"""
        
        # Predefined competitor lists by industry
        industry_competitors = {
            "ecommerce": [
                "https://www.verkkokauppa.com",
                "https://www.prisma.fi",
                "https://www.tokmanni.fi"
            ],
            "technology": [
                "https://www.tivi.fi",
                "https://www.techfinland.fi"
            ],
            "marketing": [
                "https://www.markkinointi.fi",
                "https://www.digitalmedia.fi"
            ]
        }
        
        return industry_competitors.get(industry.lower(), [])

# ==================== CHANGE TRACKER ====================

class ChangeTracker:
    """Track changes in competitor websites over time"""
    
    def __init__(self):
        self.db_session = None
        if DB_AVAILABLE:
            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine)
            SessionLocal = sessionmaker(bind=engine)
            self.db_session = SessionLocal
    
    async def track_changes(
        self, 
        url: str, 
        current_analysis: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Track and detect changes"""
        
        if not self.db_session:
            return None
        
        session = self.db_session()
        
        try:
            # Get previous analysis
            previous = session.query(CompetitorAnalysis).filter_by(
                url=url
            ).order_by(CompetitorAnalysis.created_at.desc()).first()
            
            if not previous:
                # First analysis
                self._save_analysis(session, url, current_analysis)
                return None
            
            # Detect changes
            changes = self._detect_changes(
                previous.analysis_data,
                current_analysis
            )
            
            if changes['significant_changes']:
                # Save tracking record
                tracking = CompetitorTracking(
                    url=url,
                    changes_detected=changes,
                    score_change=changes.get('score_change', 0)
                )
                session.add(tracking)
            
            # Save new analysis
            self._save_analysis(session, url, current_analysis)
            
            session.commit()
            return changes
            
        except Exception as e:
            logger.error(f"Change tracking error: {e}")
            session.rollback()
            return None
        finally:
            session.close()
    
    def _detect_changes(
        self, 
        previous: Dict, 
        current: Dict
    ) -> Dict[str, Any]:
        """Detect significant changes between analyses"""
        
        changes = {
            "significant_changes": [],
            "score_change": 0,
            "new_technologies": [],
            "removed_technologies": [],
            "content_change": 0
        }
        
        # Score change
        prev_score = previous.get('scores', {}).get('total', 0)
        curr_score = current.get('scores', {}).get('total', 0)
        score_change = curr_score - prev_score
        
        if abs(score_change) > 10:
            changes['significant_changes'].append(
                f"Score changed by {score_change:+.0f} points"
            )
        changes['score_change'] = score_change
        
        # Technology changes
        prev_tech = set()
        curr_tech = set()
        
        # Safely extract technologies
        prev_tech_dict = previous.get('technical_analysis', {}).get('technologies', {})
        for tech_list in prev_tech_dict.values():
            if isinstance(tech_list, list):
                prev_tech.update(tech_list)
        
        curr_tech_dict = current.get('technical_analysis', {}).get('technologies', {})
        for tech_list in curr_tech_dict.values():
            if isinstance(tech_list, list):
                curr_tech.update(tech_list)
        
        new_tech = curr_tech - prev_tech
        removed_tech = prev_tech - curr_tech
        
        if new_tech:
            changes['new_technologies'] = list(new_tech)
            changes['significant_changes'].append(f"New technologies: {', '.join(new_tech)}")
        
        if removed_tech:
            changes['removed_technologies'] = list(removed_tech)
            changes['significant_changes'].append(f"Removed technologies: {', '.join(removed_tech)}")
        
        # Content change
        prev_words = previous.get('content_analysis', {}).get('text_stats', {}).get('word_count', 0)
        curr_words = current.get('content_analysis', {}).get('text_stats', {}).get('word_count', 0)
        content_change_pct = ((curr_words - prev_words) / max(prev_words, 1)) * 100
        
        if abs(content_change_pct) > 20:
            changes['significant_changes'].append(
                f"Content changed by {content_change_pct:+.0f}%"
            )
        changes['content_change'] = content_change_pct
        
        return changes
    
    def _save_analysis(
        self, 
        session, 
        url: str, 
        analysis: Dict[str, Any]
    ):
        """Save analysis to database"""
        
        record = CompetitorAnalysis(
            url=url,
            company_name=analysis.get('company_name'),
            analysis_data=analysis,
            scores=analysis.get('scores', {}),
            ai_insights=analysis.get('ai_insights'),
            version=APP_VERSION
        )
        session.add(record)

# ==================== OSA 5/6 LOPPUU ====================

# ==================== OSA 6/6 ALKAA ====================
# MAIN APPLICATION JA API ENDPOINTS

# ==================== MAIN ANALYZER ====================

class CompetitiveIntelligenceAnalyzer:
    """Main analyzer orchestrating all components"""
    
    def __init__(self):
        self.scraper = WebScraper()
        self.content_analyzer = ContentAnalyzer()
        self.technical_analyzer = TechnicalAnalyzer()
        self.seo_analyzer = SEOAnalyzer()
        self.ai_analyzer = AIAnalyzer()
        self.lighthouse = LighthouseAnalyzer()
        self.competitor_finder = CompetitorFinder()
        self.change_tracker = ChangeTracker()
    
    async def analyze(
        self,
        url: str,
        level: AnalysisLevel = AnalysisLevel.STANDARD,
        include_ai: bool = True,
        include_lighthouse: bool = False,
        track_changes: bool = False
    ) -> SmartAnalysisResponse:
        """Main analysis method"""
        
        active_analyses.inc()
        start_time = datetime.now()
        
        try:
            # Validate URL
            url = validate_and_sanitize_url(url)
            
            # Check cache
            cache_key = generate_cache_key(url, level.value)
            cached = await cache.get(cache_key)
            if cached:
                cache_hits.inc()
                return SmartAnalysisResponse(**cached)
            
            # Fetch page
            render_js = level in [AnalysisLevel.ADVANCED, AnalysisLevel.PREMIUM]
            html, status_code = await self.scraper.fetch_page(url, render_js=render_js)
            
            # Parse HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # Run analyses in parallel
            tasks = []
            
            # Core analyses
            tasks.append(self.content_analyzer.analyze_content(soup, url))
            tasks.append(self.technical_analyzer.analyze_technical(soup, html, url))
            tasks.append(self.seo_analyzer.analyze_seo(soup, url, {}))  # Will update with content
            
            # Optional analyses
            if level >= AnalysisLevel.ADVANCED:
                tasks.append(self.scraper.fetch_robots_txt(url))
                
            if include_lighthouse and level >= AnalysisLevel.PREMIUM:
                tasks.append(self.lighthouse.run_lighthouse(url))
            
            # Execute parallel tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            content_analysis = results[0] if not isinstance(results[0], Exception) else {}
            technical_analysis = results[1] if not isinstance(results[1], Exception) else {}
            seo_analysis = results[2] if not isinstance(results[2], Exception) else {}
            
            # Update SEO with content analysis
            seo_analysis = await self.seo_analyzer.analyze_seo(soup, url, content_analysis)
            
            # Calculate scores
            scores = self._calculate_scores(
                content_analysis,
                technical_analysis,
                seo_analysis
            )
            
            # Prepare response data
            analysis_data = {
                "url": url,
                "company_name": self._extract_company_name(soup, url),
                "analysis_date": datetime.now(),
                "level": level,
                "scores": scores,
                "technical_analysis": technical_analysis,
                "content_analysis": content_analysis,
                "seo_analysis": seo_analysis
            }
            
            # Add optional data
            if len(results) > 3 and not isinstance(results[3], Exception):
                analysis_data["robots_txt"] = results[3]
            
            if include_lighthouse and len(results) > 4 and not isinstance(results[4], Exception):
                analysis_data["performance_metrics"] = results[4]
            
            # AI Analysis
            ai_insights = None
            if include_ai and level >= AnalysisLevel.STANDARD:
                ai_insights = await self.ai_analyzer.analyze_with_ai(analysis_data)
                if ai_insights:
                    analysis_data["ai_insights"] = ai_insights.model_dump()
            
            # Track changes
            if track_changes:
                changes = await self.change_tracker.track_changes(url, analysis_data)
                if changes:
                    analysis_data["changes_detected"] = changes
            
            # Create response
            response = SmartAnalysisResponse(
                success=True,
                url=url,
                company_name=analysis_data["company_name"],
                analysis_date=analysis_data["analysis_date"],
                level=level,
                scores=scores,
                technical_analysis=technical_analysis,
                content_analysis=content_analysis,
                seo_analysis=seo_analysis,
                performance_metrics=analysis_data.get("performance_metrics"),
                ai_insights=ai_insights,
                competitor_comparison=None,  # Will be added separately
                tracking_enabled=track_changes,
                report_id=None  # Will be generated if needed
            )
            
            # Cache result
            await cache.set(cache_key, response.model_dump())
            
            # Track metrics
            duration = (datetime.now() - start_time).total_seconds()
            analysis_duration.observe(duration)
            analysis_counter.inc()
            
            return response
            
        except Exception as e:
            logger.error(f"Analysis failed for {url}: {e}")
            error_counter.labels(error_type='analysis').inc()
            raise
        finally:
            active_analyses.dec()
    
    def _calculate_scores(
        self,
        content: Dict,
        technical: Dict,
        seo: Dict
    ) -> Dict[str, Any]:
        """Calculate comprehensive scores"""
        
        scores = {
            "total": 0,
            "seo": 0,
            "content": 0,
            "technical": 0,
            "performance": 0,
            "security": 0,
            "user_experience": 0,
            "breakdown": {}
        }
        
        # SEO Score
        seo_components = [
            seo.get("title_analysis", {}).get("score", 0) * 0.2,
            seo.get("meta_description", {}).get("score", 0) * 0.15,
            seo.get("headings", {}).get("score", 0) * 0.15,
            seo.get("images", {}).get("score", 0) * 0.1,
            seo.get("internal_linking", {}).get("score", 0) * 0.1,
            seo.get("schema_markup", {}).get("score", 0) * 0.1,
            seo.get("canonicalization", {}).get("score", 0) * 0.05,
            seo.get("mobile_optimization", {}).get("score", 0) * 0.1,
            seo.get("social_signals", {}).get("score", 0) * 0.05
        ]
        scores["seo"] = sum(seo_components)
        
        # Content Score
        content_quality = content.get("quality_signals", {}).get("quality_score", 0)
        text_stats = content.get("text_stats", {})
        word_count = text_stats.get("word_count", 0)
        
        content_score = min(100, (
            (min(100, word_count / 10) * 0.3) +
            (content_quality * 0.4) +
            (content.get("structure", {}).get("semantic_structure_score", 0) * 0.3)
        ))
        scores["content"] = content_score
        
        # Technical Score
        tech_score = (
            technical.get("performance", {}).get("resource_hints_score", 0) * 0.3 +
            technical.get("security", {}).get("security_score", 0) * 0.3 +
            (100 if technical.get("technologies", {}) else 0) * 0.2 +
            (100 if technical.get("structured_data", {}).get("json_ld") else 0) * 0.2
        )
        scores["technical"] = min(100, tech_score)
        
        # Performance Score
        perf = technical.get("performance", {})
        perf_score = 100
        if perf.get("page_size_kb", 0) > 3000: perf_score -= 20
        if perf.get("script_count", 0) > 20: perf_score -= 20
        if perf.get("lazy_loaded_images", 0) == 0: perf_score -= 10
        scores["performance"] = max(0, perf_score)
        
        # Security Score
        scores["security"] = technical.get("security", {}).get("security_score", 0)
        
        # User Experience Score
        ux_score = (
            content.get("engagement", {}).get("forms_count", 0) * 5 +
            content.get("engagement", {}).get("cta_count", 0) * 5 +
            (50 if content.get("accessibility", {}).get("heading_hierarchy_valid") else 0)
        )
        scores["user_experience"] = min(100, ux_score)
        
        # Total Score (weighted average)
        scores["total"] = int(
            scores["seo"] * 0.25 +
            scores["content"] * 0.20 +
            scores["technical"] * 0.20 +
            scores["performance"] * 0.15 +
            scores["security"] * 0.10 +
            scores["user_experience"] * 0.10
        )
        
        # Round all scores
        for key in scores:
            if isinstance(scores[key], (int, float)):
                scores[key] = round(scores[key])
        
        return scores
    
    def _extract_company_name(self, soup: BeautifulSoup, url: str) -> str:
        """Extract company name from page"""
        
        # Try various methods
        
        # 1. OG site name
        og_site = soup.find('meta', property='og:site_name')
        if og_site:
            return og_site.get('content', '')
        
        # 2. Title tag
        title = soup.find('title')
        if title:
            title_text = title.get_text(strip=True)
            # Extract before separator
            for sep in ['|', '-', '–', '•']:
                if sep in title_text:
                    parts = title_text.split(sep)
                    return parts[-1].strip()  # Usually company name is last
        
        # 3. Schema.org
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Organization':
                    return data.get('name', '')
            except:
                pass
        
        # 4. Domain name
        domain = extract_domain(url)
        return domain.replace('www.', '').split('.')[0].title()

# ==================== FASTAPI APPLICATION ====================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Advanced Competitive Intelligence API with AI-powered insights",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize main analyzer
analyzer = CompetitiveIntelligenceAnalyzer()

# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "documentation": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    health_status = {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "components": {
            "redis": "healthy" if cache.client else "unavailable",
            "database": "healthy" if DB_AVAILABLE else "unavailable",
            "openai": "healthy" if analyzer.ai_analyzer.client else "unavailable",
            "nlp": "healthy" if NLP_AVAILABLE else "unavailable",
            "lighthouse": "enabled" if LIGHTHOUSE_ENABLED else "disabled"
        },
        "metrics": {
            "total_analyses": 0,  # Would need proper metric access
            "active_analyses": 0,  # Would need proper metric access
            "cache_hit_rate": 0  # Would need proper metric access
        }
    }
    
    # Overall status
    if all(v == "healthy" or v == "disabled" for v in health_status["components"].values()):
        health_status["status"] = "healthy"
    elif any(v == "unavailable" for v in ["redis", "database"] if v in health_status["components"]):
        health_status["status"] = "degraded"
    
    return health_status

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")

@app.post("/api/v1/analyze", response_model=SmartAnalysisResponse)
async def analyze_endpoint(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user)
):
    """Main analysis endpoint"""
    
    # Rate limiting
    rate_limit_key = f"analyze:{current_user}"
    if not await rate_limiter.check_rate_limit(rate_limit_key, limit=100):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    
    try:
        # Run analysis
        result = await analyzer.analyze(
            url=request.url,
            level=request.level,
            include_ai=request.include_ai,
            include_lighthouse=request.include_lighthouse,
            track_changes=request.track_changes
        )
        
        # Schedule background tasks if needed
        if request.track_changes:
            background_tasks.add_task(
                send_webhook_notification,
                "analysis_complete",
                result.model_dump()
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")

@app.post("/api/v1/batch")
async def batch_analyze(
    request: BatchAnalysisRequest,
    current_user: str = Depends(get_current_user)
):
    """Batch analysis endpoint"""
    
    # Rate limiting
    if not await rate_limiter.check_rate_limit(f"batch:{current_user}", limit=10):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    results = []
    
    # Analyze URLs in parallel (with concurrency limit)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
    
    async def analyze_with_semaphore(url):
        async with semaphore:
            try:
                return await analyzer.analyze(
                    url=url,
                    level=request.level,
                    include_ai=request.level >= AnalysisLevel.STANDARD
                )
            except Exception as e:
                logger.error(f"Batch analysis error for {url}: {e}")
                return {"success": False, "url": url, "error": str(e)}
    
    results = await asyncio.gather(
        *[analyze_with_semaphore(url) for url in request.urls]
    )
    
    # Generate comparison if requested
    comparison = None
    if request.compare_all and len(results) > 1:
        comparison = compare_analyses([r.model_dump() if hasattr(r, 'model_dump') else r for r in results if isinstance(r, SmartAnalysisResponse)])
    
    return {
        "success": True,
        "count": len(results),
        "results": results,
        "comparison": comparison
    }

@app.get("/api/v1/compare")
async def compare_competitors(
    url1: str,
    url2: str,
    current_user: str = Depends(get_current_user)
):
    """Compare two competitors"""
    
    # Rate limiting
    if not await rate_limiter.check_rate_limit(f"compare:{current_user}", limit=50):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Analyze both URLs
    results = await asyncio.gather(
        analyzer.analyze(url1),
        analyzer.analyze(url2)
    )
    
    # Create comparison
    comparison = {
        "competitor1": results[0].model_dump(),
        "competitor2": results[1].model_dump(),
        "winner": determine_winner(results[0], results[1]),
        "key_differences": identify_key_differences(results[0], results[1]),
        "recommendations": generate_comparison_recommendations(results[0], results[1])
    }
    
    return comparison

@app.post("/api/v1/track")
async def enable_tracking(
    url: str,
    webhook_url: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """Enable change tracking for a URL"""
    
    # This would set up regular monitoring
    # Implementation would depend on your scheduling system
    
    return {
        "success": True,
        "url": url,
        "tracking_enabled": True,
        "webhook_url": webhook_url,
        "check_frequency": "daily"
    }

@app.post("/api/v1/report/generate")
async def generate_report(
    analysis_id: str,
    format: str = "pdf",
    current_user: str = Depends(get_current_user)
):
    """Generate analysis report"""
    
    # This would generate PDF/Excel reports
    # Implementation depends on your reporting needs
    
    return {
        "success": True,
        "report_url": f"/api/v1/report/{analysis_id}.{format}",
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
    }

# ==================== HELPER FUNCTIONS ====================

def compare_analyses(analyses: List[Dict]) -> Dict:
    """Compare multiple analyses"""
    
    if not analyses:
        return {}
    
    # Calculate averages and identify best/worst
    scores = [a.get("scores", {}).get("total", 0) for a in analyses]
    
    return {
        "average_score": sum(scores) / len(scores) if scores else 0,
        "best_performer": max(analyses, key=lambda x: x.get("scores", {}).get("total", 0)) if analyses else None,
        "worst_performer": min(analyses, key=lambda x: x.get("scores", {}).get("total", 0)) if analyses else None,
        "score_range": max(scores) - min(scores) if scores else 0
    }

def determine_winner(result1, result2) -> Dict:
    """Determine winner between two competitors"""
    
    score1 = result1.scores.get("total", 0)
    score2 = result2.scores.get("total", 0)
    
    if score1 > score2:
        return {"url": result1.url, "margin": score1 - score2}
    else:
        return {"url": result2.url, "margin": score2 - score1}

def identify_key_differences(result1, result2) -> List[str]:
    """Identify key differences between competitors"""
    
    differences = []
    
    # Compare scores
    for category in ["seo", "content", "technical", "performance"]:
        score1 = result1.scores.get(category, 0)
        score2 = result2.scores.get(category, 0)
        diff = abs(score1 - score2)
        if diff > 20:
            winner = result1.url if score1 > score2 else result2.url
            differences.append(f"{category.title()}: {winner} leads by {diff} points")
    
    return differences

def generate_comparison_recommendations(result1, result2) -> List[str]:
    """Generate recommendations based on comparison"""
    
    recommendations = []
    
    # Identify weaker competitor
    total1 = result1.scores.get("total", 0)
    total2 = result2.scores.get("total", 0)
    
    weaker = result1 if total1 < total2 else result2
    stronger = result2 if weaker == result1 else result1
    
    # Generate recommendations for weaker competitor
    for category in ["seo", "content", "technical"]:
        weaker_score = weaker.scores.get(category, 0)
        stronger_score = stronger.scores.get(category, 0)
        if weaker_score < stronger_score - 10:
            recommendations.append(
                f"Improve {category} to match competitor ({stronger_score} vs {weaker_score})"
            )
    
    return recommendations[:5]

async def send_webhook_notification(event: str, data: Dict):
    """Send webhook notification"""
    
    # This would send notifications to configured webhooks
    logger.info(f"Webhook event: {event}")

# ==================== STARTUP/SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info(f"{APP_NAME} v{APP_VERSION} starting up...")
    
    # Warm up caches
    if cache.client:
        try:
            cache.client.ping()
        except:
            pass
    
    logger.info("Startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    
    # Close connections
    if cache.client:
        try:
            cache.client.close()
        except:
            pass
    
    logger.info("Shutdown complete")

# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )

# ==================== OSA 6/6 LOPPUU ====================
# ==================== KOKO KOODI VALMIS ====================
