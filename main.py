#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 4.4.0 - Enhanced with Better AI and Social Media Analysis
"""

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
from collections import defaultdict, Counter
import statistics

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
    OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore
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

APP_VERSION = "4.4.0"

# ========== APP INITIALIZATION - TÄMÄ ENNEN KAIKKEA MUUTA! ========== #

app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Kilpailija-analyysi API with Enhanced AI & Social Media Analysis"
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
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if (OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY")) else None

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
    analyze_social: Optional[bool] = True

class SocialMediaAnalysisRequest(BaseModel):
    url: str
    platforms: Optional[List[str]] = ["facebook", "instagram", "tiktok", "twitter", "linkedin", "youtube"]
    deep_analysis: Optional[bool] = True

# ================== OSA 1/5 LOPPUU ================== #
# SEURAAVAKSI: Enhanced Helper Functions (OSA 2/5)

# ================== OSA 2/5 ALKAA: ENHANCED HELPER FUNCTIONS ================== #

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

# ========== ENHANCED SOCIAL MEDIA ANALYSIS ========== #

def extract_social_signals_enhanced(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """
    Parannettu sosiaalisen median signaalien tunnistus
    """
    social_signals = {
        "platforms": {
            "facebook": None,
            "instagram": None,
            "tiktok": None,
            "twitter": None,
            "linkedin": None,
            "youtube": None,
            "snapchat": None,
            "pinterest": None,
            "github": None,
            "discord": None
        },
        "widgets": [],
        "share_buttons": [],
        "engagement_indicators": {},
        "social_meta_tags": {},
        "analysis": {
            "total_platforms": 0,
            "primary_focus": None,
            "social_strategy": "unknown"
        }
    }
    
    # Parannetut regex-patternit sosiaalisille medioille
    social_patterns = {
        "facebook": [
            r"facebook\.com/(?:pages/)?[\w\-\.]+/?(?:\?.*)?",
            r"fb\.com/[\w\-\.]+",
            r"www\.facebook\.com/[\w\-\.]+",
            r"m\.facebook\.com/[\w\-\.]+",
            r"business\.facebook\.com/[\w\-\.]+"
        ],
        "instagram": [
            r"instagram\.com/[\w\-\.]+/?(?:\?.*)?",
            r"www\.instagram\.com/[\w\-\.]+",
            r"instagr\.am/[\w\-\.]+"
        ],
        "tiktok": [
            r"tiktok\.com/@[\w\-\.]+/?(?:\?.*)?",
            r"www\.tiktok\.com/@[\w\-\.]+",
            r"vm\.tiktok\.com/[\w\-\.]+"
        ],
        "twitter": [
            r"twitter\.com/[\w\-\.]+/?(?:\?.*)?",
            r"x\.com/[\w\-\.]+/?(?:\?.*)?",
            r"www\.twitter\.com/[\w\-\.]+",
            r"mobile\.twitter\.com/[\w\-\.]+"
        ],
        "linkedin": [
            r"linkedin\.com/(?:company|in|school)/[\w\-\.]+/?(?:\?.*)?",
            r"www\.linkedin\.com/(?:company|in|school)/[\w\-\.]+",
            r"fi\.linkedin\.com/(?:company|in)/[\w\-\.]+"
        ],
        "youtube": [
            r"youtube\.com/(?:c|channel|user|@)/[\w\-\.]+/?(?:\?.*)?",
            r"www\.youtube\.com/(?:c|channel|user|@)/[\w\-\.]+",
            r"youtu\.be/[\w\-\.]+"
        ],
        "snapchat": [
            r"snapchat\.com/add/[\w\-\.]+",
            r"www\.snapchat\.com/add/[\w\-\.]+"
        ],
        "pinterest": [
            r"pinterest\.(?:com|fi)/[\w\-\.]+/?(?:\?.*)?",
            r"www\.pinterest\.(?:com|fi)/[\w\-\.]+"
        ],
        "github": [
            r"github\.com/[\w\-\.]+/?(?:\?.*)?",
            r"www\.github\.com/[\w\-\.]+"
        ],
        "discord": [
            r"discord\.(?:gg|com/invite)/[\w\-\.]+",
            r"discordapp\.com/invite/[\w\-\.]+"
        ]
    }
    
    # Etsi linkit HTML:stä
    all_links = soup.find_all('a', href=True)
    page_text = soup.get_text()
    
    for link in all_links:
        href = link.get('href', '').lower()
        link_text = link.get_text(strip=True).lower()
        
        for platform, patterns in social_patterns.items():
            for pattern in patterns:
                if re.search(pattern, href, re.IGNORECASE):
                    if not social_signals["platforms"][platform]:  # Ota ensimmäinen löytynyt
                        social_signals["platforms"][platform] = link.get('href')
                    break
    
    # Tunnista social media widgetit ja upotukset
    widget_patterns = {
        "facebook_widget": [r'facebook\.com/plugins', r'fb-like', r'fb-share', r'fb-comments'],
        "instagram_embed": [r'instagram\.com/embed', r'instagram-media'],
        "twitter_widget": [r'twitter\.com/widgets', r'twitter-tweet', r'twitter-timeline'],
        "youtube_embed": [r'youtube\.com/embed', r'youtube-player'],
        "tiktok_embed": [r'tiktok\.com/embed'],
        "linkedin_widget": [r'linkedin\.com/widgets', r'linkedin-share']
    }
    
    html_content = str(soup)
    for widget_type, patterns in widget_patterns.items():
        for pattern in patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                social_signals["widgets"].append(widget_type)
                break
    
    # Tunnista share-napit
    share_button_patterns = [
        r'share.*facebook', r'share.*instagram', r'share.*twitter', r'share.*tiktok',
        r'facebook.*share', r'instagram.*share', r'twitter.*share', r'tiktok.*share',
        r'social.*share', r'share.*social', r'addtoany', r'sharethis'
    ]
    
    for pattern in share_button_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            social_signals["share_buttons"].append(pattern)
    
    # Analysoi engagement-indikaattorit (tykkäykset, seuraajaluvut jne.)
    engagement_patterns = {
        "followers": [r'(\d+(?:,\d+)*)\s*(?:followers?|seuraa)', r'(\d+(?:k|m)?)\s*followers?'],
        "likes": [r'(\d+(?:,\d+)*)\s*(?:likes?|tykkä)', r'(\d+(?:k|m)?)\s*likes?'],
        "views": [r'(\d+(?:,\d+)*)\s*(?:views?|katso)', r'(\d+(?:k|m)?)\s*views?'],
        "subscribers": [r'(\d+(?:,\d+)*)\s*(?:subscribers?|tilaa)', r'(\d+(?:k|m)?)\s*subscribers?']
    }
    
    for metric, patterns in engagement_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            if matches:
                social_signals["engagement_indicators"][metric] = matches[:3]  # Ota max 3
    
    # Etsi social media meta-tagit
    social_meta_patterns = {
        "fb:app_id": soup.find('meta', {'property': 'fb:app_id'}),
        "twitter:site": soup.find('meta', {'name': 'twitter:site'}),
        "instagram-url": soup.find('meta', {'name': 'instagram-url'}),
        "youtube-url": soup.find('meta', {'name': 'youtube-url'})
    }
    
    for meta_name, meta_tag in social_meta_patterns.items():
        if meta_tag and meta_tag.get('content'):
            social_signals["social_meta_tags"][meta_name] = meta_tag.get('content')
    
    # Analysoi strategia
    active_platforms = [p for p, url in social_signals["platforms"].items() if url]
    social_signals["analysis"]["total_platforms"] = len(active_platforms)
    
    # Määritä pääfokus
    if "instagram" in active_platforms and "tiktok" in active_platforms:
        social_signals["analysis"]["primary_focus"] = "visual_content"
        social_signals["analysis"]["social_strategy"] = "modern_visual"
    elif "linkedin" in active_platforms and "twitter" in active_platforms:
        social_signals["analysis"]["primary_focus"] = "business_networking"
        social_signals["analysis"]["social_strategy"] = "b2b_focused"
    elif "facebook" in active_platforms and len(active_platforms) >= 3:
        social_signals["analysis"]["primary_focus"] = "multi_platform"
        social_signals["analysis"]["social_strategy"] = "comprehensive"
    elif len(active_platforms) >= 4:
        social_signals["analysis"]["primary_focus"] = "omnichannel"
        social_signals["analysis"]["social_strategy"] = "aggressive_growth"
    elif len(active_platforms) == 0:
        social_signals["analysis"]["social_strategy"] = "minimal_presence"
    else:
        social_signals["analysis"]["social_strategy"] = "selective_presence"
    
    return social_signals

# ========== ENHANCED AI ANALYSIS ========== #

class EnhancedAIAnalyzer:
    """Parannettu AI-analyysi luokka"""
    
    def __init__(self):
        self.sentiment_analyzer = TextBlob if TEXTBLOB_AVAILABLE else None
        self.openai_client = openai_client
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analysoi tekstin tunnelma"""
        if not self.sentiment_analyzer or not text:
            return {
                "polarity": 0,
                "subjectivity": 0,
                "sentiment_label": "neutral",
                "confidence": 0,
                "available": False
            }
        
        try:
            blob = TextBlob(text[:2000])  # Rajoita tekstin pituus
            polarity = blob.sentiment.polarity
            subjectivity = blob.sentiment.subjectivity
            
            # Määritä tunnelataus
            if polarity > 0.3:
                sentiment_label = "positive"
            elif polarity < -0.3:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"
            
            return {
                "polarity": round(polarity, 3),
                "subjectivity": round(subjectivity, 3),
                "sentiment_label": sentiment_label,
                "confidence": round(abs(polarity), 3),
                "available": True,
                "interpretation": self._interpret_sentiment(polarity, subjectivity)
            }
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {
                "polarity": 0,
                "subjectivity": 0,
                "sentiment_label": "neutral",
                "confidence": 0,
                "available": False,
                "error": str(e)
            }
    
    def _interpret_sentiment(self, polarity: float, subjectivity: float) -> str:
        """Tulkitse tunnelma-analyysi"""
        if polarity > 0.5 and subjectivity < 0.5:
            return "Strongly positive and objective tone"
        elif polarity > 0.3:
            return "Positive tone"
        elif polarity < -0.3:
            return "Negative tone"
        elif subjectivity > 0.7:
            return "Highly subjective content"
        elif subjectivity < 0.3:
            return "Objective, factual content"
        else:
            return "Neutral, balanced tone"
    
    def detect_industry_enhanced(self, content: Dict) -> Dict[str, Any]:
        """Parannettu toimialan tunnistus"""
        industry_keywords = {
            "technology": {
                "keywords": ["software", "app", "platform", "digital", "cloud", "AI", "data", "tech", "development", "programming", "innovation"],
                "weight": 1.0
            },
            "healthcare": {
                "keywords": ["health", "medical", "patient", "clinic", "doctor", "therapy", "medicine", "hospital", "care", "wellness"],
                "weight": 1.0
            },
            "finance": {
                "keywords": ["banking", "investment", "financial", "payment", "insurance", "loan", "credit", "money", "finance", "accounting"],
                "weight": 1.0
            },
            "retail": {
                "keywords": ["shop", "store", "product", "buy", "sale", "customer", "retail", "commerce", "shopping", "marketplace"],
                "weight": 1.0
            },
            "education": {
                "keywords": ["learn", "course", "student", "education", "training", "academy", "school", "university", "teaching"],
                "weight": 1.0
            },
            "manufacturing": {
                "keywords": ["production", "factory", "industrial", "equipment", "supply", "manufacturing", "assembly", "quality"],
                "weight": 1.0
            },
            "hospitality": {
                "keywords": ["hotel", "restaurant", "travel", "tourism", "booking", "accommodation", "hospitality", "dining"],
                "weight": 1.0
            },
            "real_estate": {
                "keywords": ["property", "real estate", "apartment", "house", "rent", "mortgage", "housing", "construction"],
                "weight": 1.0
            },
            "automotive": {
                "keywords": ["car", "vehicle", "automotive", "driving", "motor", "transportation", "auto", "garage"],
                "weight": 1.0
            },
            "media": {
                "keywords": ["news", "content", "media", "publishing", "entertainment", "journalism", "broadcasting", "creative"],
                "weight": 1.0
            },
            "consulting": {
                "keywords": ["consulting", "advisory", "strategy", "business", "professional", "expertise", "solutions", "services"],
                "weight": 0.8
            },
            "fitness": {
                "keywords": ["fitness", "gym", "exercise", "workout", "sports", "training", "health", "wellness", "nutrition"],
                "weight": 1.0
            }
        }
        
        # Yhdistä kaikki teksti analyysiä varten
        all_text = " ".join([
            content.get('title', ''),
            content.get('description', ''),
            " ".join(content.get('headings', [])),
            content.get('text_content', '')[:1000]  # Rajoita tekstin määrä
        ]).lower()
        
        industry_scores = {}
        total_matches = 0
        
        for industry, data in industry_keywords.items():
            score = 0
            keywords = data["keywords"]
            weight = data["weight"]
            
            for keyword in keywords:
                matches = len(re.findall(r'\b' + re.escape(keyword) + r'\b', all_text))
                score += matches * weight
                total_matches += matches
            
            if score > 0:
                industry_scores[industry] = score
        
        # Normalisoi pisteet
        if industry_scores and total_matches > 0:
            for industry in industry_scores:
                industry_scores[industry] = industry_scores[industry] / total_matches
        
        # Määritä päätuomiala
        if industry_scores:
            primary_industry = max(industry_scores, key=industry_scores.get)
            confidence = industry_scores[primary_industry]
            
            # Jos confidence on liian matala, merkitse yleiseksi
            if confidence < 0.2:
                primary_industry = "general"
                confidence = 0.1
        else:
            primary_industry = "general"
            confidence = 0.0
        
        return {
            "primary_industry": primary_industry,
            "confidence": round(confidence, 3),
            "all_scores": {k: round(v, 3) for k, v in industry_scores.items()},
            "detected_keywords": total_matches,
            "analysis_date": datetime.now().isoformat()
        }
    
    def analyze_content_quality_enhanced(self, content: Dict, social_data: Dict = None) -> Dict[str, Any]:
        """Parannettu sisällön laadun analyysi"""
        quality_score = 0
        max_score = 100
        factors = []
        recommendations = []
        
        # SEO-perusteet (30 pistettä)
        if content.get('title'):
            title_len = len(content['title'])
            if 30 <= title_len <= 60:
                quality_score += 15
                factors.append("optimal_title_length")
            elif title_len > 0:
                quality_score += 8
                recommendations.append("Optimize title length (30-60 characters)")
        else:
            recommendations.append("Add page title")
        
        if content.get('description'):
            desc_len = len(content['description'])
            if 120 <= desc_len <= 160:
                quality_score += 15
                factors.append("optimal_description_length")
            elif desc_len > 0:
                quality_score += 8
                recommendations.append("Optimize meta description (120-160 characters)")
        else:
            recommendations.append("Add meta description")
        
        # Sisältö (25 pistettä)
        word_count = content.get('word_count', 0)
        if word_count > 1500:
            quality_score += 20
            factors.append("comprehensive_content")
        elif word_count > 800:
            quality_score += 15
            factors.append("good_content_depth")
        elif word_count > 300:
            quality_score += 10
            factors.append("adequate_content")
        elif word_count > 0:
            quality_score += 5
            recommendations.append("Increase content depth (minimum 300 words recommended)")
        
        headings = content.get('headings', [])
        if len(headings) > 5:
            quality_score += 5
            factors.append("structured_headings")
        elif len(headings) > 0:
            quality_score += 3
        else:
            recommendations.append("Add heading structure (H1, H2, H3)")
        
        # Multimedia (15 pistettä)
        images = content.get('images', [])
        if len(images) > 3:
            quality_score += 10
            factors.append("rich_media")
        elif len(images) > 0:
            quality_score += 5
            factors.append("has_images")
        else:
            recommendations.append("Add relevant images")
        
        videos = content.get('videos', [])
        if len(videos) > 0:
            quality_score += 5
            factors.append("has_videos")
        
        # Tekninen laatu (15 pistettä)
        if content.get('canonical'):
            quality_score += 5
            factors.append("canonical_url")
        else:
            recommendations.append("Add canonical URL")
        
        if content.get('url', '').startswith('https'):
            quality_score += 5
            factors.append("secure_connection")
        else:
            recommendations.append("Implement HTTPS")
        
        if content.get('viewport'):
            quality_score += 5
            factors.append("mobile_optimized")
        else:
            recommendations.append("Add viewport meta tag for mobile")
        
        # Sosiaalinen läsnäolo (15 pistettä)
        if social_data:
            platforms = social_data.get('analysis', {}).get('total_platforms', 0)
            if platforms >= 4:
                quality_score += 15
                factors.append("strong_social_presence")
            elif platforms >= 2:
                quality_score += 10
                factors.append("good_social_presence")
            elif platforms >= 1:
                quality_score += 5
                factors.append("basic_social_presence")
            else:
                recommendations.append("Establish social media presence")
            
            widgets = social_data.get('widgets', [])
            if len(widgets) > 0:
                factors.append("social_integration")
        else:
            recommendations.append("Analyze social media integration")
        
        # Laske lopullinen pistemäärä
        quality_score = min(quality_score, max_score)
        
        # Määritä arvosana
        if quality_score >= 90:
            grade = "A+"
        elif quality_score >= 80:
            grade = "A"
        elif quality_score >= 70:
            grade = "B"
        elif quality_score >= 60:
            grade = "C"
        elif quality_score >= 50:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "quality_score": quality_score,
            "grade": grade,
            "factors": factors,
            "recommendations": recommendations[:5],  # Top 5 suositusta
            "analysis_breakdown": {
                "seo_score": min(30, sum([15 if "title" in f else 15 if "description" in f else 0 for f in factors])),
                "content_score": min(25, word_count // 60),  # Simplified calculation
                "technical_score": len([f for f in factors if f in ["canonical_url", "secure_connection", "mobile_optimized"]]) * 5,
                "social_score": len([f for f in factors if "social" in f]) * 5
            }
        }
    
    def extract_keywords_enhanced(self, content: Dict, max_keywords: int = 15) -> List[Dict[str, Any]]:
        """Parannettu avainsanojen poiminta"""
        # Yhdistä teksti
        text = " ".join([
            content.get('title', ''),
            content.get('description', ''),
            " ".join(content.get('headings', [])),
            content.get('text_content', '')
        ]).lower()
        
        # Suomalaiset ja englantilaiset stop-sanat
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from',
            'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
            'ja', 'tai', 'mutta', 'sekä', 'että', 'kun', 'jos', 'niin', 'kuin', 'kuin', 'koko', 'kaikki',
            'joka', 'jotka', 'joita', 'jonka', 'ovat', 'olivat', 'ole', 'olla', 'ollut', 'tämä', 'tuo',
            'nämä', 'nuo', 'siinä', 'tässä', 'tuossa', 'kanssa', 'ilman', 'mukaan', 'kautta', 'ennen',
            'jälkeen', 'aikana', 'myös', 'vielä', 'nyt', 'sitten', 'aivan', 'hyvin', 'melko', 'erittäin'
        }
        
        # Poimi sanat
        words = re.findall(r'\b[a-zäöåü]{3,}\b', text)
        words = [w for w in words if w not in stop_words]
        
        # Laske frekvenssi
        word_freq = Counter(words)
        total_words = len(words)
        
        keywords = []
        for word, count in word_freq.most_common(max_keywords):
            density = (count / total_words * 100) if total_words > 0 else 0
            
            # Kategorisoi avainsana
            category = self._categorize_keyword(word)
            
            keywords.append({
                "keyword": word,
                "frequency": count,
                "density": round(density, 2),
                "category": category,
                "relevance_score": self._calculate_keyword_relevance(word, count, total_words)
            })
        
        return keywords
    
    def _categorize_keyword(self, word: str) -> str:
        """Kategorisoi avainsana"""
        business_words = ['yritys', 'palvelu', 'tuote', 'asiakas', 'business', 'service', 'product', 'customer']
        tech_words = ['teknologia', 'digitaalinen', 'online', 'technology', 'digital', 'software', 'system']
        marketing_words = ['markkinointi', 'myynti', 'brändi', 'marketing', 'sales', 'brand', 'advertising']
        
        word_lower = word.lower()
        
        if any(bw in word_lower for bw in business_words):
            return "business"
        elif any(tw in word_lower for tw in tech_words):
            return "technology"
        elif any(mw in word_lower for mw in marketing_words):
            return "marketing"
        else:
            return "general"
    
    def _calculate_keyword_relevance(self, word: str, frequency: int, total_words: int) -> float:
        """Laske avainsanan relevanssi"""
        # Yksinkertainen relevanssilaskenta
        base_score = frequency / total_words if total_words > 0 else 0
        
        # Bonuspisteitä pitkemmille sanoille
        length_bonus = min(len(word) / 10, 0.5)
        
        # Bonuspisteitä liiketoimintasanoille
        business_bonus = 0.2 if self._categorize_keyword(word) in ["business", "marketing"] else 0
        
        return round(base_score + length_bonus + business_bonus, 3)

def enhanced_ai_analysis(data: Dict, language: str = "fi") -> Dict[str, Any]:
    """Suorita parannettu AI-analyysi"""
    ai_analyzer = EnhancedAIAnalyzer()
    
    # Perustiedot
    content = {
        'title': data.get('head_signals', {}).get('title', ''),
        'description': data.get('head_signals', {}).get('description', ''),
        'headings': data.get('content_analysis', {}).get('headings', {}).get('h1', []),
        'text_content': data.get('content_analysis', {}).get('text_content', ''),
        'word_count': data.get('insights', {}).get('word_count', 0),
        'images': data.get('content_analysis', {}).get('images', {}),
        'videos': data.get('content_analysis', {}).get('videos', []),
        'canonical': data.get('smart', {}).get('head_signals', {}).get('canonical'),
        'url': data.get('url', ''),
        'viewport': bool(data.get('smart', {}).get('head_signals', {}).get('viewport'))
    }
    
    social_data = data.get('smart', {}).get('social_signals')
    
    # Suorita analyysit
    sentiment = ai_analyzer.analyze_sentiment(content['text_content'])
    industry = ai_analyzer.detect_industry_enhanced(content)
    quality = ai_analyzer.analyze_content_quality_enhanced(content, social_data)
    keywords = ai_analyzer.extract_keywords_enhanced(content)
    
    return {
        "sentiment_analysis": sentiment,
        "industry_detection": industry,
        "content_quality": quality,
        "keyword_analysis": {
            "keywords": keywords,
            "top_categories": Counter([kw["category"] for kw in keywords]).most_common(3)
        },
        "ai_confidence": calculate_ai_confidence_score(sentiment, industry, quality),
        "analysis_timestamp": datetime.now().isoformat()
    }

def calculate_ai_confidence_score(sentiment: Dict, industry: Dict, quality: Dict) -> float:
    """Laske AI-analyysin luotettavuus"""
    confidence_factors = []
    
    # Sentiment-analyysin luotettavuus
    if sentiment.get('available'):
        confidence_factors.append(min(sentiment.get('confidence', 0), 0.3))
    
    # Toimiala-analyysin luotettavuus
    if industry.get('confidence', 0) > 0.2:
        confidence_factors.append(min(industry['confidence'], 0.3))
    
    # Laatuanalyysin luotettavuus (aina saatavilla)
    quality_confidence = quality.get('quality_score', 0) / 100 * 0.4
    confidence_factors.append(quality_confidence)
    
    # Laske keskiarvo
    if confidence_factors:
        return round(sum(confidence_factors) / len(confidence_factors), 3)
    else:
        return 0.1

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

def score_and_recommend(head_sig, tech_cro, word_count, social_signals=None):
    seo_score = 0
    seo_score += 10 if head_sig['canonical'] else 0
    seo_score += 10 if head_sig['og_status']['has_title'] else 0
    content_score = 15 if word_count > 10000 else 8 if word_count > 5000 else 0
    cro_score = min(15, tech_cro['cta_count']*2) + (5 if tech_cro['forms_count'] > 0 else 0)
    trust_score = 5 if 'Organization' in head_sig['schema_counts'] else 0
    tech_score = 5 if tech_cro['analytics_pixels'] else 0
    
    # Lisää sosiaalisen median pistemäärä
    social_score = 0
    if social_signals:
        platforms = social_signals.get('analysis', {}).get('total_platforms', 0)
        social_score = min(10, platforms * 2)  # Max 10 pistettä
    
    total = min(100, seo_score + content_score + cro_score + trust_score + tech_score + social_score)

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
    
    # Lisää sosiaalisen median suosituksia
    if social_signals and social_signals.get('analysis', {}).get('total_platforms', 0) < 2:
        findings.append("Heikko sosiaalisen median läsnäolo")
        actions.append({"otsikko":"Vahvista sosiaalista mediaa","kuvaus":"Perusta profiilit vähintään Facebookissa ja Instagramissa","prioriteetti":"keskitaso","aikataulu":"1–2kk","mittari":"Aktiiviset profiilit"})

    return {
        "scores":{"seo":seo_score,"content":content_score,"cro":cro_score,"trust":trust_score,"tech":tech_score,"social":social_score,"total":total},
        "top_findings":findings[:6],
        "actions":actions[:8]
    }

def _find_common_patterns(findings_lists):
    """Tunnista yleisimmät löydökset"""
    all_findings = []
    for findings in findings_lists:
        all_findings.extend(findings)

    patterns = {}
    keywords = ['canonical', 'CTA', 'analytiikka', 'sisältö', 'OG-meta', 'sosiaalinen']
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
    for category in ['seo', 'content', 'cro', 'tech', 'social']:
        if weaker['smart']['scores'][category] < stronger['smart']['scores'][category]:
            if category == 'seo':
                tips.append(f"Paranna SEO:ta - kilpailijalla {stronger['smart']['scores'][category]} pistettä vs sinun {weaker['smart']['scores'][category]}")
            elif category == 'content':
                tips.append(f"Lisää sisältöä - kilpailijalla parempi sisältöpisteet")
            elif category == 'cro':
                tips.append(f"Paranna konversiota - lisää CTA-elementtejä")
            elif category == 'tech':
                tips.append(f"Päivitä analytiikka - kilpailijalla parempi seuranta")
            elif category == 'social':
                tips.append(f"Vahvista sosiaalista mediaa - kilpailijalla parempi läsnäolo")
    if stronger['smart']['tech_cro'].get('analytics_pixels') and not weaker['smart']['tech_cro'].get('analytics_pixels'):
        tips.append("Asenna analytiikkapikselit (GA4, Meta Pixel)")
    return tips[:5]

# ================== OSA 2/5 LOPPUU ================== #
# SEURAAVAKSI: Enhanced Content Analysis & SWOT (OSA 3/5)

# ================== OSA 3/5 ALKAA: ENHANCED CONTENT ANALYSIS & SWOT GENERATORS ================== #

def analyze_content_enhanced(soup: BeautifulSoup, url: str):
    """
    Parannettu sivuston sisällön analyysi
    """
    content_analysis = {
        "headings": {},
        "images": {"total": 0, "with_alt": 0, "without_alt": 0, "optimized": 0},
        "links": {"internal": 0, "external": 0, "total": 0, "broken_indicators": 0},
        "text_content": "",
        "services_hints": [],
        "trust_signals": [],
        "content_quality": {},
        "semantic_analysis": {},
        "user_experience": {},
        "accessibility": {}
    }

    # Parannettu otsikkoanalyysi
    heading_structure = {}
    for i in range(1, 7):
        h_tags = soup.find_all(f'h{i}')
        if h_tags:
            headings = []
            for tag in h_tags[:10]:  # Max 10 per level
                text = tag.get_text(strip=True)
                if text:
                    headings.append({
                        "text": text[:150],
                        "length": len(text),
                        "has_keywords": bool(re.search(r'\b(service|palvelu|tuote|product|solution|ratkaisu)\b', text.lower()))
                    })
            heading_structure[f'h{i}'] = headings
            content_analysis["headings"][f'h{i}'] = [h["text"] for h in headings]

    # Parannettu kuva-analyysi
    images = soup.find_all('img')
    content_analysis["images"]["total"] = len(images)
    
    for img in images:
        alt = img.get('alt', '')
        src = img.get('src', '')
        
        if alt:
            content_analysis["images"]["with_alt"] += 1
            # Tarkista alt-tekstin laatu
            if len(alt) > 10 and not alt.lower() in ['image', 'kuva', 'photo']:
                content_analysis["images"]["optimized"] += 1
        else:
            content_analysis["images"]["without_alt"] += 1

    # Parannettu linkki-analyysi
    links = soup.find_all('a', href=True)
    base_domain = url.split('/')[2] if '://' in url else url.split('/')[0]
    
    for link in links:
        href = link['href']
        link_text = link.get_text(strip=True)
        
        # Tarkista onko linkki rikki (indikaattorit)
        if not href or href in ['#', 'javascript:void(0)', 'javascript:;']:
            content_analysis["links"]["broken_indicators"] += 1
        elif href.startswith('http://') or href.startswith('https://'):
            if base_domain in href:
                content_analysis["links"]["internal"] += 1
            else:
                content_analysis["links"]["external"] += 1
        elif not href.startswith('#') and not href.startswith('mailto:') and not href.startswith('tel:'):
            content_analysis["links"]["internal"] += 1
    
    content_analysis["links"]["total"] = len(links)

    # Parannettu tekstianalyysi
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile('content|main'))
    if main_content:
        text = main_content.get_text(separator=' ', strip=True)
    else:
        text = soup.get_text(separator=' ', strip=True)
    
    # Puhdista teksti
    text = re.sub(r'\s+', ' ', text)
    content_analysis["text_content"] = text[:5000]  # Lisää tekstiä analyysiin

    # Parannetut palvelu-/tuotevihjeet
    service_keywords = [
        'palvelu', 'tuote', 'ratkaisu', 'tarjoa', 'toiminta', 'asiantuntija', 'konsultointi',
        'service', 'product', 'solution', 'offer', 'expert', 'consulting', 'specialist',
        'auttaa', 'help', 'support', 'tuki', 'neuvonta', 'guidance'
    ]
    
    sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20]
    text_lower = text.lower()
    
    for keyword in service_keywords:
        if keyword in text_lower:
            for sentence in sentences:
                if keyword in sentence.lower() and len(sentence) < 300:
                    # Tarkista että lause on merkityksellinen
                    if len([w for w in sentence.split() if len(w) > 3]) > 5:
                        content_analysis["services_hints"].append(sentence.strip())
                        if len(content_analysis["services_hints"]) >= 8:
                            break

    # Parannetut luottamussignaalit
    trust_patterns = [
        (r'\d{7}-\d', 'Y-tunnus (Finnish business ID)'),
        (r'(?:perustettu|founded|since)\s+\d{4}', 'Perustamisvuosi'),
        (r'ISO[ -]?\d{4,}', 'ISO-sertifikaatti'),
        (r'(?:palkinto|award|voittaja|winner)', 'Palkinnot/tunnustukset'),
        (r'(?:\d+\+?\s*)?(?:asiakasta|clients|customers)', 'Asiakasreferenssit'),
        (r'(?:\d+\+?\s*)?(?:henkilö|työntekijä|employees|team)', 'Tiimitieto'),
        (r'(?:yhteystiedot|contact|ota yhteyttä)', 'Yhteystiedot'),
        (r'(?:testimoni|referenssi|case|arvostelu|review)', 'Asiakastarinat'),
        (r'(?:sertifioitu|certified|akkreditoitu|accredited)', 'Sertifioinnit'),
        (r'(?:vakuutus|insurance|takuu|warranty)', 'Vakuutukset/takuut'),
        (r'(?:GDPR|tietosuoja|privacy|yksityisyys)', 'Tietosuoja')
    ]
    
    for pattern, signal_type in trust_patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        if matches:
            content_analysis["trust_signals"].append({
                "type": signal_type,
                "count": len(matches),
                "examples": matches[:2]  # Max 2 esimerkkiä
            })

    # Sisällön laadun mittarit
    words = text.split()
    sentences_count = len([s for s in text.split('.') if len(s.strip()) > 10])
    
    content_analysis["content_quality"] = {
        "text_length": len(text),
        "word_count": len(words),
        "unique_words": len(set([w.lower() for w in words if len(w) > 2])),
        "avg_sentence_length": len(words) / max(sentences_count, 1),
        "reading_level": calculate_reading_level(text),
        "has_contact_info": bool(re.search(r'@|puh|tel|phone|\+\d', text_lower)),
        "has_address": bool(re.search(r'\d{5}|finland|suomi|helsinki|tampere|turku|oulu|espoo|vantaa', text_lower)),
        "call_to_actions": len(re.findall(r'\b(?:osta|tilaa|varaa|soita|kirjoita|lähetä|buy|order|call|contact|book)\b', text_lower)),
        "urgency_words": len(re.findall(r'\b(?:nyt|heti|nopeasti|rajattu|now|today|limited|urgent|fast)\b', text_lower))
    }

    # Semanttinen analyysi
    content_analysis["semantic_analysis"] = {
        "topic_keywords": extract_topic_keywords(text),
        "entity_mentions": extract_entities(text),
        "content_categories": categorize_content(text)
    }

    # Käyttäjäkokemus-indikaattorit
    content_analysis["user_experience"] = {
        "readability_score": calculate_readability_score(text),
        "navigation_hints": find_navigation_elements(soup),
        "interactive_elements": count_interactive_elements(soup),
        "multimedia_ratio": calculate_multimedia_ratio(soup)
    }

    # Saavutettavuus
    content_analysis["accessibility"] = {
        "alt_text_coverage": (content_analysis["images"]["with_alt"] / max(content_analysis["images"]["total"], 1)) * 100,
        "heading_structure_score": calculate_heading_structure_score(heading_structure),
        "color_contrast_indicators": find_color_indicators(soup),
        "aria_labels": len(soup.find_all(attrs={"aria-label": True}))
    }

    return content_analysis

def calculate_reading_level(text: str) -> str:
    """Laske tekstin lukutaso (yksinkertaistettu)"""
    if not text:
        return "unknown"
    
    words = text.split()
    sentences = [s for s in text.split('.') if len(s.strip()) > 5]
    
    if not words or not sentences:
        return "unknown"
    
    avg_words_per_sentence = len(words) / len(sentences)
    avg_syllables = sum([count_syllables(word) for word in words[:100]]) / min(len(words), 100)
    
    # Yksinkertaistettu Flesch-kine indeksi
    if avg_words_per_sentence < 15 and avg_syllables < 1.5:
        return "easy"
    elif avg_words_per_sentence < 20 and avg_syllables < 2:
        return "moderate"
    else:
        return "difficult"

def count_syllables(word: str) -> int:
    """Laske tavumäärä (yksinkertaistettu)"""
    word = word.lower().strip('.,!?;:"')
    if not word:
        return 0
    
    # Yksinkertainen laskenta vokaalien perusteella
    vowels = 'aeiouyäöå'
    syllables = 0
    prev_was_vowel = False
    
    for char in word:
        if char in vowels:
            if not prev_was_vowel:
                syllables += 1
            prev_was_vowel = True
        else:
            prev_was_vowel = False
    
    return max(syllables, 1)

def extract_topic_keywords(text: str) -> List[str]:
    """Poimii aiheavainsanoja tekstistä"""
    # Yksinkertainen avainsanojen poiminta
    words = re.findall(r'\b[a-zäöåü]{4,}\b', text.lower())
    
    # Suodata stop-sanat
    stop_words = {'että', 'joka', 'kanssa', 'mukaan', 'kautta', 'lisäksi', 'myös', 'sekä', 'että', 'kun', 'jos', 'niin', 'kuin', 'koko', 'kaikki'}
    words = [w for w in words if w not in stop_words]
    
    # Laske frekvenssi ja palauta top 10
    word_freq = Counter(words)
    return [word for word, count in word_freq.most_common(10) if count > 1]

def extract_entities(text: str) -> Dict[str, List[str]]:
    """Tunnista entiteetit tekstistä (yksinkertainen versio)"""
    entities = {
        "locations": [],
        "organizations": [],
        "technologies": []
    }
    
    # Suomalaiset kaupungit
    cities = re.findall(r'\b(?:Helsinki|Tampere|Turku|Oulu|Espoo|Vantaa|Lahti|Kuopio|Jyväskylä|Pori|Vaasa|Lappeenranta|Hämeenlinna|Rovaniemi|Joensuu|Kouvola|Kotka|Mikkeli|Seinäjoki|Rauma)\b', text, re.IGNORECASE)
    entities["locations"].extend(list(set(cities)))
    
    # Teknologiat
    tech_terms = re.findall(r'\b(?:React|Vue|Angular|WordPress|Shopify|Python|JavaScript|HTML|CSS|PHP|Java|API|SaaS|CRM|ERP|CMS)\b', text, re.IGNORECASE)
    entities["technologies"].extend(list(set(tech_terms)))
    
    # Organisaatiot (yksinkertainen tunnistus)
    org_patterns = [r'\b[A-ZÄÖÅ][a-zäöå]+ (?:Oy|Ab|Ltd|Inc|Corp|Group|Company|Yhtiö)\b']
    for pattern in org_patterns:
        orgs = re.findall(pattern, text)
        entities["organizations"].extend(orgs[:5])  # Max 5
    
    return entities
