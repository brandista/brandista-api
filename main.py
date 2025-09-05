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

def enhanced_ai_analysis(data: Dict, language: str = "fi") -> Dict[str, Any]:
    """Suorita parannettu AI-analyysi"""
    ai_analyzer = EnhancedAIAnalyzer()
    
    # Perustiedot
    content = {
        'title': data.get('head_signals', {}).get('title', ''),
        'description': data.get('head_signals', {}).get('description', ''),
        'text_content': data.get('content_analysis', {}).get('text_content', ''),
        'word_count': data.get('insights', {}).get('word_count', 0),
        'url': data.get('url', ''),
    }
    
    social_data = data.get('smart', {}).get('social_signals')
    
    # Suorita analyysit
    sentiment = ai_analyzer.analyze_sentiment(content['text_content'])
    
    return {
        "sentiment_analysis": sentiment,
        "analysis_timestamp": datetime.now().isoformat(),
        "language": language
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

# ========== SWOT GENERATION ========== #

def generate_strengths(data: dict, social_data: dict = None) -> list:
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
    
    # Sosiaalisen median vahvuudet
    if social_data:
        platforms = social_data.get('analysis', {}).get('total_platforms', 0)
        if platforms >= 3:
            strengths.append(f"Vahva sosiaalisen median läsnäolo ({platforms} alustaa)")
    
    return strengths[:6] if strengths else ["Sivusto on toiminnassa", "Responsiivinen suunnittelu"]

def generate_weaknesses(data: dict, social_data: dict = None) -> list:
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
    
    # Sosiaalisen median heikkoudet
    if social_data:
        platforms = social_data.get('analysis', {}).get('total_platforms', 0)
        if platforms == 0:
            weaknesses.append("Ei sosiaalisen median läsnäoloa")
        elif platforms < 2:
            weaknesses.append("Rajallinen sosiaalisen median läsnäolo")
            
    return weaknesses[:6] if weaknesses else ["Kehityskohteita tunnistettu"]

def generate_opportunities(data: dict, social_data: dict = None) -> list:
    """Generate opportunities based on analysis data"""
    opportunities = []
    smart = data.get("smart", {})
    actions = smart.get("actions", [])
    
    for action in actions[:4]:
        if isinstance(action, dict):
            opportunities.append(action.get("kuvaus", action.get("otsikko", "")))
    
    # Sosiaalisen median mahdollisuudet
    if social_data:
        platforms = social_data.get('platforms', {})
        missing_platforms = [k for k, v in platforms.items() if not v and k in ['instagram', 'tiktok', 'linkedin']]
        if missing_platforms:
            opportunities.append(f"Laajenna sosiaaliseen mediaan: {', '.join(missing_platforms[:2])}")
    
    if not opportunities:
        opportunities = [
            "Sisällöntuotannon tehostaminen",
            "SEO-optimoinnin parantaminen",
            "Konversio-optimointi",
            "Analytiikan hyödyntäminen"
        ]
    
    return opportunities[:5]

def generate_threats(data: dict, social_data: dict = None) -> list:
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
    
    # Sosiaalisen median uhat
    if social_data:
        platforms = social_data.get('analysis', {}).get('total_platforms', 0)
        if platforms == 0:
            threats.append("Kilpailijoiden parempi sosiaalisen median näkyvyys")
        
    return threats[:3] if threats else ["Markkinadynamiikan muutokset", "Teknologinen jälkeenjääneisyys"]

def generate_fallback_swot(data: dict, language: str, social_data: dict = None) -> dict:
    """Generate fallback SWOT analysis when AI fails"""
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    
    if language == 'en':
        return {
            "summary": f"Website scored {scores.get('total', 0)}/100 in digital analysis. Social media presence on {social_data.get('analysis', {}).get('total_platforms', 0) if social_data else 0} platforms.",
            "strengths": generate_strengths(data, social_data),
            "weaknesses": generate_weaknesses(data, social_data),
            "opportunities": generate_opportunities(data, social_data),
            "threats": generate_threats(data, social_data),
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
            "yhteenveto": f"Sivusto sai {scores.get('total', 0)}/100 pistettä digitaalisessa analyysissä. Sosiaalinen läsnäolo {social_data.get('analysis', {}).get('total_platforms', 0) if social_data else 0} alustalla.",
            "vahvuudet": generate_strengths(data, social_data),
            "heikkoudet": generate_weaknesses(data, social_data),
            "mahdollisuudet": generate_opportunities(data, social_data),
            "uhat": generate_threats(data, social_data),
            "toimenpidesuositukset": smart.get("actions", [])[:5],
            "kilpailijaprofiili": {
                "kohderyhmat": ["Yleisö"],
                "vahvuusalueet": ["Digitaalinen läsnäolo"],
                "markkina_asema": "Aktiivinen digitaalisissa kanavissa"
            }
        }

# ================== MAIN ENDPOINTS ================== #

@app.get("/")
def home():
    return {
        "api":"Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status":"ok",
        "features": {
            "ai_analysis": OPENAI_AVAILABLE or TEXTBLOB_AVAILABLE,
            "social_media_analysis": True,
            "enhanced_content_analysis": True,
            "js_render_enabled": SMART_JS_RENDER
        }
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
        "ai_features": {
            "openai_configured": bool(openai_client),
            "textblob_available": TEXTBLOB_AVAILABLE,
            "sentiment_analysis": TEXTBLOB_AVAILABLE
        },
        "smart_js_render_flag": SMART_JS_RENDER,
        "deps": {
            "requests_html": can_import("requests_html"),
            "textblob": TEXTBLOB_AVAILABLE,
            "openai": OPENAI_AVAILABLE
        }
    }

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"

        # Tarkista välimuisti
        cached = get_cached_analysis(url)
        if cached:
            return SmartAnalyzeResponse(**cached)

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

        # 3) Parannetut analyysit
        head_sig = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, str(soup))
        sitemap_info = await collect_robots_and_sitemap(url)
        content_data = analyze_content(soup, url)
        social_signals = extract_social_signals_enhanced(soup, url)
        
        # 4) Pisteytys sosiaalisella medialla
        scores = score_and_recommend(head_sig, tech_cro, word_count, social_signals)

        smart = {
            "meta": {"title": title or "Ei otsikkoa", "description": description or "Ei kuvausta", "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "content_analysis": content_data,
            "social_signals": social_signals,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"],
            "flags": {"js_render_enabled": SMART_JS_RENDER, "cached": False, "enhanced_analysis": True}
        }

        # 5) AI-analyysi jos mahdollista
        ai_analysis = None
        if OPENAI_AVAILABLE or TEXTBLOB_AVAILABLE:
            try:
                ai_analysis = enhanced_ai_analysis({
                    "head_signals": head_sig,
                    "smart": smart,
                    "content_analysis": content_data,
                    "insights": {"word_count": word_count},
                    "url": url
                })
            except Exception as e:
                logger.error(f"AI analysis failed: {e}")

        result = SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title or "Ei otsikkoa",
            description=description or "Ei kuvausta",
            score=scores["scores"]["total"],
            insights={"word_count": word_count, "ai_available": bool(ai_analysis)},
            smart={**smart, **({"ai_analysis": ai_analysis} if ai_analysis else {})}
        )

        save_to_cache(url, result.dict())
        return result

    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/social-media-analysis")
async def social_media_analysis(request: SocialMediaAnalysisRequest):
    """Erillinen sosiaalisen median analyysi"""
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
            response.raise_for_status()
            html_text = response.text

        soup = BeautifulSoup(html_text, 'html.parser')
        
        # Perusanalyysi
        social_signals = extract_social_signals_enhanced(soup, url)
        
        return {
            "success": True,
            "url": url,
            "social_analysis": social_signals,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sosiaalisen median analyysi epäonnistui: {str(e)}")

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

        # 2) Get social media analysis
        social_data = None
        if req.analyze_social:
            try:
                social_resp = await social_media_analysis(SocialMediaAnalysisRequest(url=target_url))
                social_data = social_resp["social_analysis"]
                result["smart"]["social_signals"] = social_data
            except Exception as e:
                logger.error(f"Social media analysis failed: {e}")

        # 3) Prepare AI enhancement
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
                    "social_signals": social_data,
                    "content_summary": {
                        "word_count": content_info.get("content_quality", {}).get("text_length", 0),
                        "services_hints": content_info.get("services_hints", [])[:3],
                        "trust_signals": content_info.get("trust_signals", [])
                    }
                }

                language = (req.language or 'fi').lower()
                
                # Enhanced prompts
                if language == 'en':
                    system_msg = """You are a digital marketing strategist and competitor analysis expert. 
                    You MUST provide concrete, specific insights based on the data provided.
                    Always return valid JSON with all required fields populated."""
                    
                    prompt = f"""Analyze this comprehensive competitor data and create strategic insights.

ANALYSIS DATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

Create a JSON analysis with:

{{
  "executive_summary": "3-4 sentence overview of digital presence and competitive position",
  "strengths": [
    "At least 4-5 specific competitive advantages based on data",
    "Include scores, social presence, content quality, technical capabilities"
  ],
  "weaknesses": [
    "At least 4-5 areas needing improvement based on findings",
    "Be specific about gaps and missing elements"
  ],
  "opportunities": [
    "At least 4-5 growth opportunities",
    "Include social media expansion, content strategy, technical improvements"
  ],
  "threats": [
    "At least 3 competitive risks",
    "Consider digital maturity gaps, social presence issues"
  ],
  "strategic_recommendations": [
    {{
      "title": "Specific action",
      "description": "Detailed implementation guidance",
      "priority": "high/medium/low",
      "timeline": "timeframe",
      "expected_impact": "business impact description"
    }}
  ],
  "competitive_positioning": {{
    "market_position": "leader/challenger/follower/nicher",
    "differentiation_opportunities": ["How to stand out"],
    "benchmarking_insights": ["Competitive gaps and advantages"]
  }}
}}

Base all insights on the provided data. Return only valid JSON."""

                else:  # Finnish
                    system_msg = """Olet digitaalisen markkinoinnin strategi ja kilpailija-analyysin asiantuntija.
                    SINUN TÄYTYY antaa konkreettisia, spesifisiä oivalluksia datan perusteella.
                    Palauta aina validi JSON kaikilla vaadituilla kentillä täytettyinä."""
                    
                    prompt = f"""Analysoi tämä kattava kilpailijavata ja luo strategisia oivalluksia.

ANALYYSIDATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

Luo JSON-analyysi:

{{
  "johtopäätökset": "3-4 lauseen strateginen yhteenveto digitaalisesta läsnäolosta ja kilpailuasemasta",
  "vahvuudet": [
    "Vähintään 4-5 konkreettista kilpailuetua datan perusteella",
    "Sisällytä pisteet, sosiaalinen läsnäolo, sisällön laatu, tekniset kyvykkyydet"
  ],
  "heikkoudet": [
    "Vähintään 4-5 kehityskohdetta löydösten perusteella",
    "Ole spesifinen puutteista ja puuttuvista elementeistä"
  ],
  "mahdollisuudet": [
    "Vähintään 4-5 kasvumahdollisuutta",
    "Sisällytä sosiaalisen median laajentaminen, sisältöstrategia, tekniset parannukset"
  ],
  "uhat": [
    "Vähintään 3 kilpailuriskiä",
    "Huomioi digitaalisen kypsyyden puutteet, sosiaalisen median ongelmat"
  ],
  "strategiset_suositukset": [
    {{
      "otsikko": "Konkreettinen toimenpide",
      "kuvaus": "Yksityiskohtainen toteutusohje",
      "prioriteetti": "korkea/keskitaso/matala",
      "aikataulu": "aikajana",
      "odotettu_vaikutus": "liiketoimintavaikutuksen kuvaus"
    }}
  ],
  "kilpailuasemointi": {{
    "markkina_asema": "johtaja/haastaja/seuraaja/erikoistunut",
    "erottautumismahdollisuudet": ["Miten erottua"],
    "vertailuoivallukset": ["Kilpailukuilut ja edut"]
  }}
}}

Perusta kaikki oivallukset toimitettuun dataan. Palauta vain validi JSON."""

                logger.info(f"Calling OpenAI API with enhanced prompt")
                
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
                
                ai_response = resp.choices[0].message.content
                logger.info(f"Enhanced OpenAI response received, length: {len(ai_response or '')}")
                
                if ai_response:
                    try:
                        parsed = json.loads(ai_response)
                        ai_full = parsed if isinstance(parsed, dict) else {}
                        
                        # Extract recommendations
                        ai_reco = (
                            ai_full.get("strategiset_suositukset")
                            or ai_full.get("strategic_recommendations")
                            or []
                        )
                        
                        logger.info(f"Enhanced AI analysis completed with keys: {list(ai_full.keys())}")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse enhanced AI response: {e}")
                        ai_full = generate_fallback_swot(result, language, social_data)
                else:
                    logger.warning("Empty enhanced AI response")
                    ai_full = generate_fallback_swot(result, language, social_data)
                    
            except Exception as e:
                logger.error(f"Enhanced AI analysis failed: {str(e)}")
                ai_full = generate_fallback_swot(result, req.language or 'fi', social_data)
                ai_reco = []
        else:
            logger.info("AI analysis disabled or not available")
            ai_full = generate_fallback_swot(result, req.language or 'fi', social_data)

        # 4) Build enhanced response
        
        # Extract competitive positioning
        competitive_positioning = ai_full.get("kilpailuasemointi") or ai_full.get("competitive_positioning") or {}
        
        # Quick wins list
        quick_wins_list = []
        if ai_reco or result["smart"]["actions"]:
            for a in (ai_reco or result["smart"]["actions"])[:3]:
                if isinstance(a, dict):
                    win = a.get("otsikko", a.get("title", ""))
                else:
                    win = str(a)
                if win:
                    quick_wins_list.append(win)

        response_data = {
            "success": True,
            "company_name": req.company_name,
            "analysis_date": datetime.now().isoformat(),
            "enhanced_features": {
                "social_media_analysis": bool(social_data),
                "ai_analysis": bool(ai_full),
                "sentiment_analysis": TEXTBLOB_AVAILABLE,
                "competitive_positioning": bool(competitive_positioning)
            },
            "basic_analysis": {
                "company": req.company_name,
                "website": req.website or req.url,
                "industry": req.industry,
                "digital_maturity_score": result["smart"]["scores"]["total"],
                "social_platforms": social_data.get('analysis', {}).get('total_platforms', 0) if social_data else 0
            },
            "ai_analysis": {
                "johtopäätökset": ai_full.get(
                    "johtopäätökset",
                    ai_full.get(
                        "executive_summary",
                        f"Yritys {req.company_name} saavutti {result['smart']['scores']['total']}/100 pistettä digitaalisessa analyysissä. "
                        f"Sosiaalinen läsnäolo {social_data.get('analysis', {}).get('total_platforms', 0) if social_data else 0} alustalla."
                    )
                ),
                "vahvuudet": ai_full.get("vahvuudet", ai_full.get("strengths", [])) or generate_strengths(result, social_data),
                "heikkoudet": ai_full.get("heikkoudet", ai_full.get("weaknesses", [])) or generate_weaknesses(result, social_data),
                "mahdollisuudet": ai_full.get("mahdollisuudet", ai_full.get("opportunities", [])) or generate_opportunities(result, social_data),
                "uhat": ai_full.get("uhat", ai_full.get("threats", [])) or generate_threats(result, social_data),
                "strategiset_suositukset": ai_reco or result["smart"]["actions"],
                "kilpailuasemointi": competitive_positioning,
                "quick_wins": quick_wins_list or ["Optimoi meta-tagit", "Lisää sosiaalisen median integraatio", "Paranna CTA-elementtejä"]
            },
            "detailed_analysis": {
                "social_media": social_data,
                "technical_audit": result["smart"]["tech_cro"],
                "content_analysis": result["smart"]["content_analysis"]
            },
            "smart": result["smart"]
        }

        logger.info(f"Enhanced analysis completed for {req.company_name}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enhanced AI analyze failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Enhanced AI analyze failed: {str(e)}")

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
            "
