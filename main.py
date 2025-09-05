#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 4.5.0 - Enhanced with Full AI, Social Media, UX, and Competitive Analysis
"""

import os
import re
import json
import base64
import hashlib
import logging
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

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

APP_VERSION = "4.5.0"

# App initialization
app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Enhanced Kilpailija-analyysi API with Full AI, UX, and Competitive Analysis"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Feature flags
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "1").lower() in ("1", "true", "yes")

# Cache helpers
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

# Pydantic models
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
    url: Optional[str] = None
    language: Optional[str] = 'fi'
    analyze_social: Optional[bool] = True

class SocialMediaAnalysisRequest(BaseModel):
    url: str
    platforms: Optional[List[str]] = ["facebook", "instagram", "tiktok", "twitter", "linkedin", "youtube"]
    deep_analysis: Optional[bool] = True

class ReportGenerationRequest(BaseModel):
    company_name: str
    analysis_data: Dict[str, Any]
    language: Optional[str] = 'fi'
    format: Optional[str] = 'pdf'

# Enhanced technology detection patterns
ENHANCED_TECH_HINTS = {
    "cms": [
        ("wordpress", "WordPress"), ("wp-content", "WordPress"), ("wp-includes", "WordPress"),
        ("shopify", "Shopify"), ("myshopify.com", "Shopify"), ("shopify-generated", "Shopify"),
        ("wix", "Wix"), ("wixstatic.com", "Wix"), ("wix.com", "Wix"),
        ("webflow", "Webflow"), ("webflow.com", "Webflow"), ("webflow.io", "Webflow"),
        ("woocommerce", "WooCommerce"), ("wc-", "WooCommerce"),
        ("squarespace", "Squarespace"), ("squarespace.com", "Squarespace"),
        ("drupal", "Drupal"), ("joomla", "Joomla"), ("magento", "Magento"),
        ("typo3", "TYPO3"), ("umbraco", "Umbraco"), ("craft", "Craft CMS")
    ],
    "framework": [
        ("__next", "Next.js"), ("_next/", "Next.js"), ("next.js", "Next.js"),
        ("nuxt", "Nuxt"), ("_nuxt/", "Nuxt"), ("nuxt.js", "Nuxt"),
        ("vite", "Vite"), ("@vite", "Vite"), ("vite.js", "Vite"),
        ("astro", "Astro"), ("_astro/", "Astro"), ("astro.js", "Astro"),
        ("sapper", "Sapper"), ("svelte", "Svelte"), ("_svelte/", "Svelte"),
        ("reactRoot", "React"), ("react", "React"), ("_react/", "React"),
        ("vue", "Vue.js"), ("_vue/", "Vue.js"), ("vuetify", "Vue.js"),
        ("angular", "Angular"), ("ng-", "Angular"), ("_angular/", "Angular"),
        ("gatsby", "Gatsby"), ("_gatsby/", "Gatsby"), ("gatsby.js", "Gatsby"),
        ("ember", "Ember.js"), ("_ember/", "Ember.js")
    ],
    "analytics": [
        ("gtag(", "GA4/gtag"), ("googletagmanager.com", "GTM"), ("google-analytics", "Google Analytics"),
        ("facebook.net/en_US/fbevents.js", "Meta Pixel"), ("fbevents", "Meta Pixel"), ("facebook-pixel", "Meta Pixel"),
        ("clarity.ms", "MS Clarity"), ("clarity(", "MS Clarity"), ("microsoft-clarity", "MS Clarity"),
        ("hotjar", "Hotjar"), ("hj(", "Hotjar"), ("hotjar.com", "Hotjar"),
        ("mixpanel", "Mixpanel"), ("amplitude", "Amplitude"), ("segment.com", "Segment"),
        ("intercom", "Intercom"), ("zendesk", "Zendesk"), ("hubspot", "HubSpot"),
        ("linkedin.com/in/", "LinkedIn Insight"), ("ads.linkedin.com", "LinkedIn Ads"),
        ("pinterest.com/ct/", "Pinterest Pixel"), ("tiktok.com/i18n/pixel", "TikTok Pixel"),
        ("snapchat.com/ct/", "Snapchat Pixel"), ("reddit.com/ct/", "Reddit Pixel")
    ],
    "ecommerce": [
        ("shopify", "Shopify"), ("woocommerce", "WooCommerce"), ("magento", "Magento"),
        ("bigcommerce", "BigCommerce"), ("prestashop", "PrestaShop"), ("opencart", "OpenCart"),
        ("stripe", "Stripe"), ("paypal", "PayPal"), ("klarna", "Klarna"), ("afterpay", "Afterpay"),
        ("add-to-cart", "E-commerce"), ("shopping-cart", "E-commerce"), ("buy-now", "E-commerce")
    ],
    "hosting": [
        ("cloudflare", "Cloudflare"), ("aws", "AWS"), ("amazonaws.com", "AWS"),
        ("netlify", "Netlify"), ("vercel", "Vercel"), ("digitalocean", "DigitalOcean"),
        ("github.io", "GitHub Pages"), ("firebase", "Firebase"), ("azure", "Microsoft Azure")
    ],
    "tools": [
        ("calendly", "Calendly"), ("typeform", "Typeform"), ("mailchimp", "Mailchimp"),
        ("hubspot", "HubSpot"), ("salesforce", "Salesforce"), ("zendesk", "Zendesk"),
        ("drift", "Drift"), ("intercom", "Intercom"), ("crisp", "Crisp"),
        ("google-fonts", "Google Fonts"), ("font-awesome", "Font Awesome"), ("bootstrap", "Bootstrap")
    ]
}# Helper functions
def maybe_scrape_with_javascript(url: str) -> Optional[str]:
    if not SMART_JS_RENDER:
        return None
    try:
        from requests_html import HTMLSession
    except Exception as e:
        print(f"[JS-RENDER] requests_html unavailable: {e}")
        return None

    try:
        session = HTMLSession()
        response = session.get(url, timeout=30)
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
        if isinstance(t, list): 
            types.extend(t)
        elif t: 
            types.append(t)
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

def enhanced_detect_tech_and_cro(soup: BeautifulSoup, html_text: str):
    """Parannettu teknologia- ja CRO-tunnistus"""
    lower = html_text.lower()
    gen = (soup.find('meta', attrs={'name':'generator'}) or {}).get('content','').lower()
    
    # Tunnista teknologiat
    detected_tech = {
        "cms": [],
        "framework": [],
        "analytics": [],
        "ecommerce": [],
        "hosting": [],
        "tools": []
    }
    
    for category, tech_list in ENHANCED_TECH_HINTS.items():
        for key, name in tech_list:
            if key in gen or key in lower:
                if name not in detected_tech[category]:
                    detected_tech[category].append(name)
    
    # Valitse pääteknikat
    primary_cms = detected_tech["cms"][0] if detected_tech["cms"] else None
    primary_framework = detected_tech["framework"][0] if detected_tech["framework"] else None
    
    # CTA-analyysi (parannettu)
    CTA_WORDS_FI = ["osta", "tilaa", "varaa", "lataa", "rekisteröidy", "liity", "hanki", "pyydä tarjous", "ota yhteyttä", "aloita", "kokeile"]
    CTA_WORDS_EN = ["buy", "order", "book", "download", "register", "join", "get", "request quote", "contact", "start", "try", "subscribe"]
    
    cta_elements = soup.find_all(["a", "button"])
    cta_count = 0
    cta_types = []
    
    for el in cta_elements:
        text = (el.get_text(" ", strip=True) or "").lower()
        classes = " ".join(el.get("class", [])).lower()
        
        for word in CTA_WORDS_FI + CTA_WORDS_EN:
            if word in text or word in classes:
                cta_count += 1
                if "buy" in word or "osta" in word:
                    cta_types.append("purchase")
                elif "contact" in word or "yhteyttä" in word:
                    cta_types.append("contact")
                elif "download" in word or "lataa" in word:
                    cta_types.append("download")
                elif "subscribe" in word or "tilaa" in word:
                    cta_types.append("subscription")
                break
    
    # Lomakkeiden analyysi
    forms = soup.find_all("form")
    forms_count = len(forms)
    form_types = []
    
    for form in forms:
        form_text = form.get_text(" ", strip=True).lower()
        if "newsletter" in form_text or "uutiskirje" in form_text:
            form_types.append("newsletter")
        elif "contact" in form_text or "yhteystiedot" in form_text:
            form_types.append("contact")
        elif "login" in form_text or "kirjaudu" in form_text:
            form_types.append("login")
        elif "search" in form_text or "haku" in form_text:
            form_types.append("search")
        else:
            form_types.append("generic")
    
    # Yhteystietokanavat (parannettu)
    contact_channels = []
    text = soup.get_text(" ", strip=True)
    
    # Email
    email_pattern = r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b'
    if re.search(email_pattern, text, re.I):
        emails = re.findall(email_pattern, text, re.I)
        contact_channels.append(f"email ({len(set(emails))} osoitetta)")
    
    # Puhelin
    phone_pattern = r'\+?\d[\d\s().-]{6,}'
    if re.search(phone_pattern, text):
        phones = re.findall(phone_pattern, text)
        contact_channels.append(f"phone ({len(set(phones))} numeroa)")
    
    # Sosiaalinen media ja chat
    if "wa.me/" in lower or "api.whatsapp.com" in lower:
        contact_channels.append("whatsapp")
    if "t.me/" in lower or "telegram" in lower:
        contact_channels.append("telegram")
    if "messenger" in lower or "fb-messenger" in lower:
        contact_channels.append("messenger")
    if "chat" in lower or "live-chat" in lower:
        contact_channels.append("live_chat")
    
    # Kieliversiot
    languages = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if re.search(r'/fi(/|$)', href): languages.add('fi')
        if re.search(r'/en(/|$)', href): languages.add('en')
        if re.search(r'/sv(/|$)', href): languages.add('sv')
        if re.search(r'/de(/|$)', href): languages.add('de')
        if re.search(r'/fr(/|$)', href): languages.add('fr')
        if re.search(r'/es(/|$)', href): languages.add('es')
    
    # Performance indikaattorit
    performance_indicators = {
        "lazy_loading": "loading=\"lazy\"" in lower or "lazy-load" in lower,
        "service_worker": "serviceWorker" in html_text or "sw.js" in lower,
        "amp": "amp-" in lower or "⚡" in html_text,
        "pwa": "manifest.json" in lower or "web-app-manifest" in lower,
        "cdn_usage": any(cdn in lower for cdn in ["cloudflare", "cloudfront", "fastly", "maxcdn"]),
        "compression": "gzip" in lower or "brotli" in lower
    }
    
    # Laske teknologiapinojen kypsyystaso
    tech_maturity = 0
    if detected_tech["cms"]: tech_maturity += 2
    if detected_tech["framework"]: tech_maturity += 2
    if len(detected_tech["analytics"]) >= 1: tech_maturity += 2
    if len(detected_tech["analytics"]) >= 3: tech_maturity += 1
    if performance_indicators["lazy_loading"]: tech_maturity += 1
    if performance_indicators["cdn_usage"]: tech_maturity += 1
    if performance_indicators["pwa"]: tech_maturity += 2
    if performance_indicators["service_worker"]: tech_maturity += 1
    if len(detected_tech["tools"]) >= 2: tech_maturity += 1
    if len(detected_tech["ecommerce"]) >= 1: tech_maturity += 1
    tech_maturity = min(10, tech_maturity)
    
    return {
        "primary_cms": primary_cms,
        "primary_framework": primary_framework,
        "detected_technologies": detected_tech,
        "analytics_pixels": detected_tech["analytics"],
        "ecommerce_platforms": detected_tech["ecommerce"],
        "hosting_services": detected_tech["hosting"],
        "marketing_tools": detected_tech["tools"],
        "cta_analysis": {
            "count": cta_count,
            "types": list(set(cta_types)),
            "density": round(cta_count / max(len(cta_elements), 1) * 100, 1)
        },
        "forms_analysis": {
            "count": forms_count,
            "types": list(set(form_types))
        },
        "contact_channels": contact_channels,
        "languages": sorted(list(languages)),
        "performance_indicators": performance_indicators,
        "tech_stack_maturity": tech_maturity
    }# Enhanced social media analysis
def extract_social_signals_enhanced(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
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
    
    # Find links in HTML
    all_links = soup.find_all('a', href=True)
    
    for link in all_links:
        href = link.get('href', '').lower()
        
        for platform, patterns in social_patterns.items():
            for pattern in patterns:
                if re.search(pattern, href, re.IGNORECASE):
                    if not social_signals["platforms"][platform]:
                        social_signals["platforms"][platform] = link.get('href')
                    break
    
    # Detect social media widgets
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
    
    # Detect share buttons
    share_button_patterns = [
        r'share.*facebook', r'share.*instagram', r'share.*twitter', r'share.*tiktok',
        r'facebook.*share', r'instagram.*share', r'twitter.*share', r'tiktok.*share',
        r'social.*share', r'share.*social', r'addtoany', r'sharethis'
    ]
    
    for pattern in share_button_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            social_signals["share_buttons"].append(pattern)
    
    # Find social media meta tags
    social_meta_patterns = {
        "fb:app_id": soup.find('meta', {'property': 'fb:app_id'}),
        "twitter:site": soup.find('meta', {'name': 'twitter:site'}),
        "instagram-url": soup.find('meta', {'name': 'instagram-url'}),
        "youtube-url": soup.find('meta', {'name': 'youtube-url'})
    }
    
    for meta_name, meta_tag in social_meta_patterns.items():
        if meta_tag and meta_tag.get('content'):
            social_signals["social_meta_tags"][meta_name] = meta_tag.get('content')
    
    # Analyze strategy
    active_platforms = [p for p, url in social_signals["platforms"].items() if url]
    social_signals["analysis"]["total_platforms"] = len(active_platforms)
    
    # Determine primary focus
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

# Content Quality and Sentiment Analysis
class ContentQualityAnalyzer:
    def __init__(self):
        self.positive_words = ['hyvä', 'erinomainen', 'laadukas', 'ammattitaitoinen', 'luotettava', 'excellent', 'quality', 'professional', 'trusted']
        self.negative_words = ['huono', 'heikko', 'ongelma', 'vaikea', 'kallis', 'bad', 'poor', 'problem', 'difficult', 'expensive']
        self.expertise_words = ['asiantuntija', 'kokemus', 'vuotta', 'sertifioitu', 'expert', 'experience', 'years', 'certified', 'specialist']
        self.trust_signals = ['takuu', 'warranty', 'guarantee', 'sertifikaatti', 'certificate', 'ISO', 'award', 'palkinto']

    def analyze_content_sentiment_and_quality(self, soup: BeautifulSoup, text_content: str) -> Dict[str, Any]:
        """Analysoi sisällön sentiment ja laatu"""
        
        # Sentiment-analyysi
        words = text_content.lower().split()
        positive_count = sum(1 for word in words if any(pos in word for pos in self.positive_words))
        negative_count = sum(1 for word in words if any(neg in word for neg in self.negative_words))
        
        sentiment_score = (positive_count - negative_count) / max(len(words), 1) * 100
        
        if sentiment_score > 1:
            sentiment = "positive"
        elif sentiment_score < -1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        # Asiantuntijuuden arviointi
        expertise_count = sum(1 for word in words if any(exp in word for exp in self.expertise_words))
        expertise_score = min(10, expertise_count * 2)
        
        # Luottamuksen signaalit
        trust_count = sum(1 for word in words if any(trust in word for trust in self.trust_signals))
        trust_score = min(10, trust_count * 3)
        
        # Luettavuuden arviointi
        sentences = text_content.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        readability_score = max(0, min(10, 15 - (avg_sentence_length - 15) * 0.5))
        
        # Sisällön syvyys
        paragraphs = len([p for p in soup.find_all('p') if len(p.get_text().strip()) > 50])
        headings = len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']))
        content_depth = min(10, (paragraphs * 0.5) + (headings * 1))
        
        return {
            "sentiment": {
                "label": sentiment,
                "score": round(sentiment_score, 2),
                "positive_signals": positive_count,
                "negative_signals": negative_count
            },
            "quality_metrics": {
                "expertise_score": expertise_score,
                "trust_score": trust_score,
                "readability_score": round(readability_score, 1),
                "content_depth": round(content_depth, 1),
                "overall_quality": round((expertise_score + trust_score + readability_score + content_depth) / 4, 1)
            },
            "brand_perception": self._analyze_brand_perception(text_content, soup)
        }
    
    def _analyze_brand_perception(self, text: str, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analysoi brändi-mielikuva"""
        # Brändi-adjektiivit
        brand_adjectives = {
            'innovatiivinen': ['innovatiivinen', 'moderni', 'tulevaisuus', 'innovative', 'modern', 'future'],
            'luotettava': ['luotettava', 'vakaa', 'varma', 'reliable', 'stable', 'trusted'],
            'henkilökohtainen': ['henkilökohtainen', 'yksilöllinen', 'räätälöity', 'personal', 'individual', 'customized'],
            'ammattitaitoinen': ['ammattitaitoinen', 'asiantunteva', 'kokenut', 'professional', 'expert', 'experienced']
        }
        
        brand_traits = {}
        for trait, keywords in brand_adjectives.items():
            count = sum(1 for word in keywords if word in text.lower())
            brand_traits[trait] = count
        
        primary_trait = max(brand_traits, key=brand_traits.get) if any(brand_traits.values()) else "neutraali"
        
        return {
            "primary_brand_trait": primary_trait,
            "brand_adjectives": brand_traits,
            "messaging_tone": "professional" if "ammattitaitoinen" in primary_trait else "friendly"
        }

# UX Analysis
class UXAnalyzer:
    def analyze_ux_factors(self, soup: BeautifulSoup, html_text: str) -> Dict[str, Any]:
        """Automaattinen UX-arviointi"""
        
        # Navigaation arviointi
        nav_elements = soup.find_all(['nav', 'menu']) + soup.find_all(class_=re.compile('nav|menu', re.I))
        nav_score = min(10, len(nav_elements) * 3)
        
        # Mobiiliystävällisyys
        viewport_meta = soup.find('meta', {'name': 'viewport'})
        responsive_indicators = ['responsive', 'mobile', 'device-width', '@media']
        mobile_score = 0
        if viewport_meta: mobile_score += 4
        mobile_score += sum(2 for indicator in responsive_indicators if indicator in html_text.lower())
        mobile_score = min(10, mobile_score)
        
        # Saavutettavuus
        alt_images = len([img for img in soup.find_all('img') if img.get('alt')])
        total_images = len(soup.find_all('img'))
        alt_ratio = (alt_images / max(total_images, 1)) * 100
        
        aria_labels = len(soup.find_all(attrs={'aria-label': True}))
        headings_hierarchy = self._check_heading_hierarchy(soup)
        
        accessibility_score = (
            (alt_ratio / 10) +  # Alt-tekstit
            min(3, aria_labels * 0.5) +  # ARIA-labelit  
            (3 if headings_hierarchy else 0) +  # Otsikkohierarkia
            (2 if soup.find('main') else 0)  # Semantic HTML
        )
        accessibility_score = min(10, accessibility_score)
        
        # Latausnopeus-indikaattorit
        speed_factors = {
            'image_optimization': 'lazy' in html_text.lower() or 'loading="lazy"' in html_text,
            'minified_assets': '.min.css' in html_text or '.min.js' in html_text,
            'cdn_usage': any(cdn in html_text.lower() for cdn in ['cloudflare', 'cloudfront', 'jsdelivr']),
            'compression': 'gzip' in html_text.lower()
        }
        speed_score = sum(2.5 for factor in speed_factors.values() if factor)
        
        # Käytettävyys-pistemäärä
        usability_elements = {
            'search_function': bool(soup.find('input', {'type': 'search'}) or soup.find(class_=re.compile('search', re.I))),
            'breadcrumbs': bool(soup.find(class_=re.compile('breadcrumb', re.I))),
            'contact_info_visible': self._has_visible_contact(soup),
            'clear_cta_buttons': len(soup.find_all(class_=re.compile('btn|button|cta', re.I))) > 0
        }
        usability_score = sum(2.5 for element in usability_elements.values() if element)
        
        return {
            "navigation_score": nav_score,
            "mobile_friendliness": mobile_score,
            "accessibility_score": round(accessibility_score, 1),
            "performance_indicators": speed_factors,
            "performance_score": speed_score,
            "usability_elements": usability_elements,
            "usability_score": usability_score,
            "overall_ux_score": round((nav_score + mobile_score + accessibility_score + speed_score + usability_score) / 5, 1)
        }
    
    def _check_heading_hierarchy(self, soup: BeautifulSoup) -> bool:
        """Tarkista otsikkohierarkia"""
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if not headings:
            return False
        
        # Tarkista että on H1 ja että järjestys on looginen
        has_h1 = any(h.name == 'h1' for h in headings)
        return has_h1
    
    def _has_visible_contact(self, soup: BeautifulSoup) -> bool:
        """Tarkista näkyvätkö yhteystiedot"""
        contact_indicators = ['yhteystiedot', 'contact', 'ota yhteyttä', 'puhelin', 'sähköposti', 'email', 'phone']
        text = soup.get_text().lower()
        return any(indicator in text for indicator in contact_indicators)# Keyword and SEO Focus Analysis
def extract_keywords_and_seo_focus(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Analysoi sivuston keyword-fokus ja SEO-strategia"""
    
    # Meta keywords (vanha koulu mutta joskus löytyy)
    meta_keywords = (soup.find('meta', {'name': 'keywords'}) or {}).get('content', '')
    
    # Ota tekstisisältö
    title = (soup.find('title') or {}).get_text('')
    description = (soup.find('meta', {'name': 'description'}) or {}).get('content', '')
    h1_tags = [h.get_text(strip=True) for h in soup.find_all('h1')]
    h2_tags = [h.get_text(strip=True) for h in soup.find_all('h2')]
    
    # Poista navigaatio yms. ja ota vain pääsisältö
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile('content|main'))
    if main_content:
        content_text = main_content.get_text(' ', strip=True)
    else:
        content_text = soup.get_text(' ', strip=True)
    
    # Siirrä tekstiä
    content_text = re.sub(r'\s+', ' ', content_text)[:5000]  # Rajoita 5000 merkkiin
    
    # Analysoi sanat
    words = re.findall(r'\b[a-zA-ZäöåÄÖÅ]{3,}\b', content_text.lower())
    
    # Poista stop words (suomi ja englanti)
    stop_words = {
        'ja', 'tai', 'on', 'ei', 'ole', 'se', 'he', 'me', 'te', 'ne', 'nyt', 'kun', 'jos', 'että', 'kuin', 'joka', 'mikä',
        'and', 'or', 'is', 'not', 'are', 'was', 'were', 'the', 'a', 'an', 'this', 'that', 'these', 'those', 'with', 'for'
    }
    
    filtered_words = [w for w in words if w not in stop_words and len(w) > 3]
    
    # Laske sanafrekvenssi
    word_freq = Counter(filtered_words)
    top_keywords = word_freq.most_common(20)
    
    # Analysoi keyword-tiheys tärkeissä paikoissa
    title_keywords = [w.lower() for w in re.findall(r'\b[a-zA-ZäöåÄÖÅ]{3,}\b', title)]
    h1_keywords = []
    for h1 in h1_tags:
        h1_keywords.extend([w.lower() for w in re.findall(r'\b[a-zA-ZäöåÄÖÅ]{3,}\b', h1)])
    
    # SEO-fokuksen analyysi
    seo_focus = {
        "primary_keywords": [kw[0] for kw in top_keywords[:5]],
        "keyword_density": {kw[0]: round(kw[1] / len(filtered_words) * 100, 2) for kw in top_keywords[:10]},
        "title_keyword_match": len([kw for kw in title_keywords if kw in [k[0] for k in top_keywords[:10]]]),
        "h1_keyword_match": len([kw for kw in h1_keywords if kw in [k[0] for k in top_keywords[:10]]]),
        "meta_keywords": meta_keywords.split(',') if meta_keywords else [],
        "content_length_words": len(filtered_words),
        "unique_words": len(set(filtered_words)),
        "readability_score": len(filtered_words) / max(len(content_text.split('.')), 1)  # Yksinkertainen luettavuusindeksi
    }
    
    # Tunnista toimiala keywordien perusteella
    industry_keywords = {
        'teknologia': ['teknologia', 'ohjelmisto', 'digitaalinen', 'it', 'tech', 'software', 'digital', 'kehitys'],
        'markkinointi': ['markkinointi', 'mainonta', 'brandi', 'marketing', 'advertising', 'brand', 'kampanja'],
        'konsultointi': ['konsultointi', 'neuvonta', 'asiantuntija', 'consulting', 'expert', 'advisory', 'palvelu'],
        'kauppa': ['kauppa', 'myynti', 'tuote', 'shop', 'store', 'product', 'osta', 'buy', 'tilaa'],
        'koulutus': ['koulutus', 'oppiminen', 'kurssit', 'education', 'learning', 'course', 'training'],
        'terveys': ['terveys', 'hyvinvointi', 'lääke', 'health', 'wellness', 'medical', 'healthcare'],
        'kiinteistöt': ['kiinteistö', 'asunto', 'talo', 'real estate', 'property', 'home', 'house'],
        'ravintola': ['ravintola', 'ruoka', 'menu', 'restaurant', 'food', 'dining', 'cafe']
    }
    
    detected_industry = []
    for industry, keywords in industry_keywords.items():
        matches = sum(1 for kw in keywords if kw in [k[0] for k in top_keywords[:15]])
        if matches >= 2:
            detected_industry.append(industry)
    
    return {
        "seo_focus": seo_focus,
        "detected_industries": detected_industry,
        "content_analysis": {
            "total_words": len(words),
            "unique_words": len(set(words)),
            "avg_word_length": sum(len(w) for w in words) / len(words) if words else 0,
            "title_words": len(title_keywords),
            "h1_count": len(h1_tags),
            "h2_count": len(h2_tags)
        }
    }

# Competitor Benchmarking System
class CompetitorBenchmarking:
    def __init__(self):
        self.industry_competitors = {
            'teknologia': [
                'tivi.fi', 'digitoday.fi', 'kauppalehti.fi/teknologia', 
                'hs.fi/teknologia', 'tek.fi', 'tivia.fi'
            ],
            'markkinointi': [
                'markkinointi.fi', 'mainostajienliitto.fi', 'kuvio.fi',
                'piktochart.com', 'canva.com', 'hubspot.com'
            ],
            'konsultointi': [
                'accenture.com', 'deloitte.com', 'pwc.com',
                'kpmg.com', 'ey.com', 'mckinsey.com'
            ],
            'kauppa': [
                'verkkokauppa.com', 'amazon.com', 'zalando.fi',
                'ellos.fi', 'prisma.fi', 'tokmanni.fi'
            ],
            'ravintola': [
                'raflaamo.fi', 'eat.fi', 'foodora.fi',
                'wolt.com', 'fazer.fi', 'kotipizza.fi'
            ],
            'kiinteistöt': [
                'etuovi.com', 'oikotie.fi', 'vuokraovi.com',
                'kiinteistomaailma.fi', 'remax.fi', 'sato.fi'
            ]
        }
    
    async def analyze_competitor_landscape(self, target_url: str, detected_industries: List[str], max_competitors: int = 3) -> Dict[str, Any]:
        """Analysoi kilpailija-maisema automaattisesti"""
        
        results = {
            "target_analysis": None,
            "competitors": [],
            "benchmarking": {},
            "market_position": {},
            "competitive_gaps": [],
            "opportunities": []
        }
        
        try:
            # Analysoi pääkohde ensin
            logger.info(f"Analyzing primary target: {target_url}")
            results["target_analysis"] = await self._analyze_single_competitor(target_url)
            
            # Valitse kilpailijat toimialan perusteella
            competitor_urls = self._select_competitors(detected_industries, max_competitors)
            
            # Analysoi kilpailijat
            for comp_url in competitor_urls:
                try:
                    logger.info(f"Analyzing competitor: {comp_url}")
                    comp_analysis = await self._analyze_single_competitor(comp_url)
                    if comp_analysis:
                        results["competitors"].append(comp_analysis)
                except Exception as e:
                    logger.warning(f"Failed to analyze competitor {comp_url}: {e}")
                    continue
            
            # Tee benchmarking-vertailu
            if results["competitors"]:
                results["benchmarking"] = self._calculate_benchmarking_scores(
                    results["target_analysis"], 
                    results["competitors"]
                )
                
                results["market_position"] = self._determine_market_position(
                    results["target_analysis"], 
                    results["competitors"]
                )
                
                results["competitive_gaps"] = self._identify_competitive_gaps(
                    results["target_analysis"], 
                    results["competitors"]
                )
                
                results["opportunities"] = self._identify_opportunities(
                    results["target_analysis"], 
                    results["competitors"]
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Competitor landscape analysis failed: {e}")
            return results
    
    async def _analyze_single_competitor(self, url: str) -> Dict[str, Any]:
        """Analysoi yksittäinen kilpailija"""
        try:
            # Käytä samaa analyysisysteemiä kuin pääanalyysissä
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
                response.raise_for_status()
                html_text = response.text

            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Perusmetriikat
            title = (soup.find('title').text.strip() if soup.find('title') else "")
            description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
            word_count = len(soup.get_text(" ", strip=True))
            
            # Teknologia-analyysi
            tech_analysis = enhanced_detect_tech_and_cro(soup, html_text)
            
            # Head signals
            head_sig = extract_head_signals(soup)
            
            # Social media
            social_signals = extract_social_signals_enhanced(soup, url)
            
            # SEO & keywords
            keyword_analysis = extract_keywords_and_seo_focus(soup, url)
            
            # Laske kokonaispistemäärä (käytä yksinkertaistettua versiota)
            seo_score = 10 if head_sig['canonical'] else 0
            seo_score += 10 if head_sig['og_status']['has_title'] else 0
            content_score = 15 if word_count > 10000 else 8 if word_count > 5000 else 0
            cro_score = min(15, tech_analysis['cta_analysis']['count']*2) + (5 if tech_analysis['forms_analysis']['count'] > 0 else 0)
            tech_score = 5 if tech_analysis['analytics_pixels'] else 0
            tech_score += min(5, tech_analysis['tech_stack_maturity'])
            social_score = min(10, social_signals.get('analysis', {}).get('total_platforms', 0) * 2)
            total_score = min(100, seo_score + content_score + cro_score + tech_score + social_score)
            
            scores = {
                "seo": seo_score,
                "content": content_score, 
                "cro": cro_score,
                "tech": tech_score,
                "social": social_score,
                "total": total_score
            }
            
            return {
                "url": url,
                "domain": url.split("//")[-1].split("/")[0],
                "title": title,
                "description": description,
                "scores": scores,
                "tech_stack": {
                    "cms": tech_analysis["primary_cms"],
                    "framework": tech_analysis["primary_framework"],
                    "analytics_count": len(tech_analysis["analytics_pixels"]),
                    "tech_maturity": tech_analysis["tech_stack_maturity"]
                },
                "seo_metrics": {
                    "title_length": len(title),
                    "description_length": len(description),
                    "word_count": word_count,
                    "primary_keywords": keyword_analysis["seo_focus"]["primary_keywords"],
                    "has_canonical": bool(head_sig['canonical']),
                    "has_og_tags": head_sig['og_status']['has_title'] and head_sig['og_status']['has_desc']
                },
                "social_presence": {
                    "platform_count": social_signals.get('analysis', {}).get('total_platforms', 0),
                    "strategy": social_signals.get('analysis', {}).get('social_strategy', 'unknown')
                },
                "cro_metrics": {
                    "cta_count": tech_analysis["cta_analysis"]["count"],
                    "forms_count": tech_analysis["forms_analysis"]["count"],
                    "contact_channels": len(tech_analysis["contact_channels"])
                }
            }
            
        except Exception as e:
            logger.error(f"Single competitor analysis failed for {url}: {e}")
            return None
    
    def _select_competitors(self, detected_industries: List[str], max_competitors: int) -> List[str]:
        """Valitse sopivat kilpailijat toimialan perusteella"""
        competitors = []
        
        for industry in detected_industries:
            if industry in self.industry_competitors:
                competitors.extend(self.industry_competitors[industry][:max_competitors])
        
        # Jos ei löydy toimiala-spesifisiä, käytä yleisiä
        if not competitors:
            competitors = [
                'yle.fi', 'hs.fi', 'kauppalehti.fi', 
                'taloussanomat.fi', 'mtv.fi'
            ][:max_competitors]
        
        return list(set(competitors))[:max_competitors]
    
    def _calculate_benchmarking_scores(self, target: Dict, competitors: List[Dict]) -> Dict[str, Any]:
        """Laske benchmarking-pisteet"""
        if not target or not competitors:
            return {}
        
        metrics = ['seo', 'content', 'cro', 'tech', 'social', 'total']
        benchmarking = {}
        
        for metric in metrics:
            target_score = target["scores"].get(metric, 0)
            competitor_scores = [c["scores"].get(metric, 0) for c in competitors]
            
            avg_competitor = sum(competitor_scores) / len(competitor_scores)
            max_competitor = max(competitor_scores)
            min_competitor = min(competitor_scores)
            
            # Määritä positio
            better_than = sum(1 for score in competitor_scores if target_score > score)
            position = f"{better_than + 1}/{len(competitors) + 1}"
            
            benchmarking[metric] = {
                "target_score": target_score,
                "competitor_average": round(avg_competitor, 1),
                "competitor_max": max_competitor,
                "competitor_min": min_competitor,
                "vs_average": round(target_score - avg_competitor, 1),
                "position": position,
                "percentile": round((better_than / len(competitor_scores)) * 100, 1)
            }
        
        return benchmarking
    
    def _determine_market_position(self, target: Dict, competitors: List[Dict]) -> Dict[str, Any]:
        """Määritä markkina-asema"""
        if not target or not competitors:
            return {}
        
        target_total = target["scores"]["total"]
        competitor_totals = [c["scores"]["total"] for c in competitors]
        
        avg_score = sum(competitor_totals) / len(competitor_totals)
        max_score = max(competitor_totals)
        
        # Määritä kategoria
        if target_total >= max_score:
            category = "leader"
            description = "Markkinajohtaja - paras kokonaispistemäärä"
        elif target_total >= avg_score + 10:
            category = "challenger"
            description = "Haastaja - keskiarvon yläpuolella"
        elif target_total >= avg_score - 5:
            category = "follower"
            description = "Seuraaja - lähellä keskiarvoa"
        else:
            category = "nicher"
            description = "Erikoistunut - alle keskiarvon"
        
        return {
            "category": category,
            "description": description,
            "total_score": target_total,
            "market_average": round(avg_score, 1),
            "gap_to_leader": max_score - target_total
        }
    
    def _identify_competitive_gaps(self, target: Dict, competitors: List[Dict]) -> List[str]:
        """Tunnista kilpailukuilut"""
        gaps = []
        
        # Teknologia-kuilut
        competitor_cms_list = [c["tech_stack"]["cms"] for c in competitors if c["tech_stack"]["cms"]]
        modern_cms = ['Webflow', 'Next.js', 'Nuxt', 'Shopify']
        
        if not target["tech_stack"]["cms"] and any(cms in modern_cms for cms in competitor_cms_list):
            gaps.append("Kilpailijat käyttävät modernimpaa teknologia-alustaa")
        
        # Social media -kuilut
        target_platforms = target["social_presence"]["platform_count"]
        max_competitor_platforms = max([c["social_presence"]["platform_count"] for c in competitors])
        
        if target_platforms < max_competitor_platforms - 1:
            gaps.append(f"Kilpailijoilla vahvempi sosiaalisen median läsnäolo (max {max_competitor_platforms} vs. {target_platforms})")
        
        return gaps
    
    def _identify_opportunities(self, target: Dict, competitors: List[Dict]) -> List[str]:
        """Tunnista mahdollisuudet kilpailijoiden perusteella"""
        opportunities = []
        
        # Teknologia-mahdollisuudet
        competitor_analytics = [comp["tech_stack"]["analytics_count"] for comp in competitors]
        max_analytics = max(competitor_analytics) if competitor_analytics else 0
        target_analytics = target["tech_stack"]["analytics_count"]
        
        if target_analytics < max_analytics:
            opportunities.append(f"Lisää analytiikkatyökaluja (kilpailijoilla max {max_analytics} vs. sinulla {target_analytics})")
        
        return opportunities# Industry-Specific Analysis
class IndustrySpecificAnalysis:
    def __init__(self):
        self.industry_weights = {
            'teknologia': {
                'tech': 0.3, 'content': 0.2, 'seo': 0.2, 'social': 0.15, 'cro': 0.15
            },
            'markkinointi': {
                'social': 0.3, 'content': 0.25, 'seo': 0.2, 'cro': 0.15, 'tech': 0.1
            },
            'kauppa': {
                'cro': 0.35, 'tech': 0.25, 'seo': 0.2, 'social': 0.15, 'content': 0.05
            },
            'konsultointi': {
                'content': 0.3, 'seo': 0.25, 'social': 0.2, 'cro': 0.15, 'tech': 0.1
            },
            'ravintola': {
                'social': 0.35, 'cro': 0.25, 'content': 0.15, 'seo': 0.15, 'tech': 0.1
            }
        }
    
    def calculate_industry_weighted_score(self, scores: Dict[str, int], detected_industries: List[str]) -> Dict[str, Any]:
        """Laske toimiala-painotettu pistemäärä"""
        
        if not detected_industries:
            return {
                "weighted_score": scores.get("total", 0),
                "industry": "generic",
                "weights_used": "equal"
            }
        
        primary_industry = detected_industries[0]
        weights = self.industry_weights.get(primary_industry, {
            'seo': 0.2, 'content': 0.2, 'cro': 0.2, 'tech': 0.2, 'social': 0.2
        })
        
        weighted_total = 0
        for metric, weight in weights.items():
            score = scores.get(metric, 0)
            weighted_total += score * weight
        
        return {
            "weighted_score": round(weighted_total, 1),
            "industry": primary_industry,
            "weights_used": weights
        }

# Enhanced AI analysis
def enhanced_ai_analysis(data: Dict, language: str = "fi") -> Dict[str, Any]:
    content = {
        'title': data.get('head_signals', {}).get('title', ''),
        'description': data.get('head_signals', {}).get('description', ''),
        'text_content': data.get('content_analysis', {}).get('text_content', ''),
        'word_count': data.get('insights', {}).get('word_count', 0),
        'url': data.get('url', ''),
    }
    
    # Basic sentiment analysis without external libs
    positive_words = ['hyvä', 'erinomainen', 'laadukas', 'good', 'excellent', 'quality']
    negative_words = ['huono', 'heikko', 'ongelma', 'bad', 'poor', 'problem']
    
    text_lower = content['text_content'].lower()
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)
    
    sentiment_score = (pos_count - neg_count) / max(len(text_lower.split()), 1) * 100
    
    return {
        "sentiment_analysis": {
            "score": round(sentiment_score, 2),
            "label": "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
        },
        "analysis_timestamp": datetime.now().isoformat(),
        "language": language
    }

def analyze_content(soup: BeautifulSoup, url: str):
    content_analysis = {
        "headings": {},
        "images": {"total": 0, "with_alt": 0, "without_alt": 0},
        "links": {"internal": 0, "external": 0, "total": 0},
        "text_content": "",
        "services_hints": [],
        "trust_signals": [],
        "content_quality": {}
    }

    # Headings
    for i in range(1, 7):
        h_tags = soup.find_all(f'h{i}')
        if h_tags:
            content_analysis["headings"][f'h{i}'] = [tag.get_text(strip=True)[:100] for tag in h_tags[:5]]

    # Images
    images = soup.find_all('img')
    content_analysis["images"]["total"] = len(images)
    content_analysis["images"]["with_alt"] = len([img for img in images if img.get('alt')])
    content_analysis["images"]["without_alt"] = len(images) - content_analysis["images"]["with_alt"]

    # Links
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

    # Text
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile('content|main'))
    if main_content:
        text = main_content.get_text(separator=' ', strip=True)
    else:
        text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    content_analysis["text_content"] = text[:3000]

    # Trust signals
    trust_patterns = [
        (r'\d{4,}-\d{4,}', 'Y-tunnus'),
        (r'(?:perustettu|founded|since) \d{4}', 'Perustamisvuosi'),
        (r'ISO[ -]?\d{4,}', 'ISO-sertifikaatti'),
        (r'palkinto|award|voittaja|winner', 'Palkinnot'),
        (r'asiakasta|clients|customers', 'Asiakasreferenssit'),
        ('yhteystiedot', 'Yhteystiedot')
    ]
    text_lower = text.lower()
    for pattern, signal_type in trust_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            content_analysis["trust_signals"].append(signal_type)

    # Quality
    content_analysis["content_quality"] = {
        "text_length": len(text),
        "unique_words": len(set(text.lower().split())),
        "avg_sentence_length": len(text.split()) / max(len(text.split('.')), 1),
        "has_contact_info": bool(re.search(r'@|puh|tel|phone', text_lower)),
        "has_address": bool(re.search(r'\d{5}|finland|suomi|helsinki|tampere', text_lower))
    }
    return content_analysis

def enhanced_score_and_recommend(head_sig, tech_cro, word_count, social_signals=None, content_quality=None, ux_analysis=None):
    """Parannettu pisteytysjärjestelmä"""
    
    # SEO pisteet
    seo_score = 0
    seo_score += 10 if head_sig['canonical'] else 0
    seo_score += 10 if head_sig['og_status']['has_title'] else 0
    seo_score += 5 if head_sig['og_status']['has_desc'] else 0
    
    # Sisältöpisteet
    content_score = 15 if word_count > 10000 else 8 if word_count > 5000 else 3 if word_count > 1000 else 0
    
    # CRO pisteet
    cro_score = min(15, tech_cro['cta_analysis']['count']*2) + (5 if tech_cro['forms_analysis']['count'] > 0 else 0)
    
    # Teknologiapisteet
    tech_score = 5 if tech_cro['analytics_pixels'] else 0
    tech_score += min(10, tech_cro['tech_stack_maturity'])
    
    # Social media pisteet
    social_score = 0
    if social_signals:
        platforms = social_signals.get('analysis', {}).get('total_platforms', 0)
        social_score = min(15, platforms * 3)
    
    # Sisällön laatupisteet
    quality_score = 0
    if content_quality:
        quality_score = content_quality['quality_metrics']['overall_quality']
    
    # UX pisteet
    ux_score = 0
    if ux_analysis:
        ux_score = ux_analysis['overall_ux_score']
    
    total = min(100, seo_score + content_score + cro_score + tech_score + social_score + quality_score + ux_score)

    # Suositukset
    findings, actions = [], []
    if not head_sig['canonical']:
        findings.append("Canonical puuttuu → riski duplikaateista")
        actions.append({"otsikko":"Lisää canonical","kuvaus":"Aseta kanoninen osoite kaikille sivuille","prioriteetti":"korkea"})
    if content_score < 10:
        findings.append("Sisältö vähäinen → kasvata laadukasta tekstiä")
        actions.append({"otsikko":"Sisältöohjelma","kuvaus":"2–4 artikkelia/kk, FAQ ja case-tarinat","prioriteetti":"korkea"})
    if tech_cro['cta_analysis']['count'] < 2:
        findings.append("Vähän CTA-elementtejä → heikko ohjaus konversioon")
        actions.append({"otsikko":"Lisää CTA-napit","kuvaus":"Heroon pää-CTA + osioihin toissijaiset","prioriteetti":"korkea"})
    if social_score < 5:
        findings.append("Heikko sosiaalisen median läsnäolo")
        actions.append({"otsikko":"Vahvista sosiaalista mediaa","kuvaus":"Perusta profiilit vähintään 2 alustalle","prioriteetti":"keskitaso"})

    return {
        "scores": {
            "seo": seo_score,
            "content": content_score, 
            "cro": cro_score,
            "tech": tech_score,
            "social": social_score,
            "quality": round(quality_score, 1),
            "ux": round(ux_score, 1),
            "total": round(total, 1)
        },
        "top_findings": findings[:6],
        "actions": actions[:8]
    }

# SWOT generation functions
def generate_strengths(data: dict, social_data: dict = None) -> list:
    strengths = []
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    tech = smart.get("tech_cro", {})
    
    if scores.get("seo", 0) >= 15:
        strengths.append(f"Hyvä SEO-optimointi ({scores['seo']}/25 pistettä)")
    if scores.get("content", 0) >= 8:
        strengths.append(f"Riittävä sisältömäärä sivustolla")
    if len(tech.get("analytics_pixels", [])) > 0:
        strengths.append(f"Analytiikkatyökalut käytössä ({', '.join(tech['analytics_pixels'])})")
    if tech.get("primary_cms") or tech.get("primary_framework"):
        strengths.append(f"Moderni teknologia-alusta ({tech.get('primary_cms') or tech.get('primary_framework')})")
    
    if social_data:
        platforms = social_data.get('analysis', {}).get('total_platforms', 0)
        if platforms >= 3:
            strengths.append(f"Vahva sosiaalisen median läsnäolo ({platforms} alustaa)")
    
    return strengths[:5] if strengths else ["Sivusto on toiminnassa"]

def generate_weaknesses(data: dict, social_data: dict = None) -> list:
    weaknesses = []
    smart = data.get("smart", {})
    findings = smart.get("top_findings", [])
    
    for finding in findings:
        weaknesses.append(finding)
    
    if social_data:
        platforms = social_data.get('analysis', {}).get('total_platforms', 0)
        if platforms == 0:
            weaknesses.append("Ei sosiaalisen median läsnäoloa")
            
    return weaknesses[:5] if weaknesses else ["Kehityskohteita tunnistettu"]

def generate_opportunities(data: dict, social_data: dict = None) -> list:
    opportunities = []
    smart = data.get("smart", {})
    actions = smart.get("actions", [])
    
    for action in actions[:3]:
        if isinstance(action, dict):
            opportunities.append(action.get("kuvaus", action.get("otsikko", "")))
    
    if social_data:
        platforms = social_data.get('platforms', {})
        missing_platforms = [k for k, v in platforms.items() if not v and k in ['instagram', 'tiktok', 'linkedin']]
        if missing_platforms:
            opportunities.append(f"Laajenna sosiaaliseen mediaan: {', '.join(missing_platforms[:2])}")
    
    return opportunities[:4] if opportunities else ["Sisällöntuotannon tehostaminen"]

def generate_fallback_swot(data: dict, language: str, social_data: dict = None) -> dict:
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    
    if language == 'en':
        return {
            "summary": f"Website scored {scores.get('total', 0)}/100 in digital analysis.",
            "strengths": generate_strengths(data, social_data),
            "weaknesses": generate_weaknesses(data, social_data),
            "opportunities": generate_opportunities(data, social_data),
            "threats": ["Market competition", "Technology changes"],
            "recommendations": smart.get("actions", [])[:3]
        }
    else:
        return {
            "yhteenveto": f"Sivusto sai {scores.get('total', 0)}/100 pistettä digitaalisessa analyysissä.",
            "vahvuudet": generate_strengths(data, social_data),
            "heikkoudet": generate_weaknesses(data, social_data),
            "mahdollisuudet": generate_opportunities(data, social_data),
            "uhat": ["Kilpailijoiden parempi digitaalinen näkyvyys", "Teknologisen kehityksen jälkeenjääneisyys"],
            "toimenpidesuositukset": smart.get("actions", [])[:3]
        }# PDF Report Generation
def generate_pdf_report(data: dict, company_name: str, language: str = 'fi') -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#2E8B57'), alignment=TA_CENTER, spaceAfter=30)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2E8B57'), spaceBefore=20, spaceAfter=12)
    
    story = []
    
    # Title
    title = f"Kilpailija-analyysi: {company_name}" if language == 'fi' else f"Competitor Analysis: {company_name}"
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 20))
    
    # Executive Summary
    ai_analysis = data.get('ai_analysis', {})
    summary = ai_analysis.get('johtopäätökset', ai_analysis.get('summary', 'Analyysi ei ole saatavilla'))
    story.append(Paragraph("Johtopäätökset" if language == 'fi' else "Executive Summary", heading_style))
    story.append(Paragraph(summary, styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Scores
    basic_analysis = data.get('basic_analysis', {})
    score = basic_analysis.get('digital_maturity_score', 0)
    story.append(Paragraph("Digitaalinen pistemäärä" if language == 'fi' else "Digital Score", heading_style))
    story.append(Paragraph(f"<b>{score}/100 pistettä</b>", styles['Normal']))
    story.append(Spacer(1, 15))
    
    # SWOT Table
    story.append(Paragraph("SWOT-analyysi" if language == 'fi' else "SWOT Analysis", heading_style))
    strengths = ai_analysis.get('vahvuudet', ai_analysis.get('strengths', []))[:3]
    weaknesses = ai_analysis.get('heikkoudet', ai_analysis.get('weaknesses', []))[:3]
    
    swot_data = [
        ['Vahvuudet' if language == 'fi' else 'Strengths', 'Heikkoudet' if language == 'fi' else 'Weaknesses'],
        ['<br/>'.join([f"• {s}" for s in strengths]), '<br/>'.join([f"• {w}" for w in weaknesses])]
    ]
    
    swot_table = Table(swot_data, colWidths=[8*cm, 8*cm])
    swot_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E8B57')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(swot_table)
    story.append(Spacer(1, 20))
    
    # Footer
    story.append(Paragraph(f"Raportti luotu: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    story.append(Paragraph("Brandista API v4.5.0", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# Main endpoints
@app.get("/")
def home():
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status": "ok",
        "features": {
            "ai_analysis": OPENAI_AVAILABLE or TEXTBLOB_AVAILABLE,
            "social_media_analysis": True,
            "competitor_benchmarking": True,
            "ux_analysis": True,
            "industry_weighting": True,
            "js_render_enabled": SMART_JS_RENDER,
            "pdf_reports": True
        }
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "ai_features": {
            "openai_configured": bool(openai_client),
            "textblob_available": TEXTBLOB_AVAILABLE
        }
    }

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"
        cached = get_cached_analysis(url)
        if cached:
            return SmartAnalyzeResponse(**cached)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
            response.raise_for_status()
            html_text = response.text

        soup = BeautifulSoup(html_text, 'html.parser')
        title = (soup.find('title').text.strip() if soup.find('title') else "")
        description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
        word_count = len(soup.get_text(" ", strip=True))

        # All analyses
        head_sig = extract_head_signals(soup)
        tech_cro = enhanced_detect_tech_and_cro(soup, str(soup))
        sitemap_info = await collect_robots_and_sitemap(url)
        content_data = analyze_content(soup, url)
        social_signals = extract_social_signals_enhanced(soup, url)
        keyword_analysis = extract_keywords_and_seo_focus(soup, url)
        
        # Quality and UX analysis
        content_quality_analyzer = ContentQualityAnalyzer()
        ux_analyzer = UXAnalyzer()
        content_quality = content_quality_analyzer.analyze_content_sentiment_and_quality(soup, content_data["text_content"])
        ux_analysis = ux_analyzer.analyze_ux_factors(soup, str(soup))
        
        # Scoring with all new factors
        scores = enhanced_score_and_recommend(head_sig, tech_cro, word_count, social_signals, content_quality, ux_analysis)

        smart = {
            "meta": {"title": title, "description": description, "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "content_analysis": content_data,
            "social_signals": social_signals,
            "content_quality": content_quality,
            "ux_analysis": ux_analysis,
            "keyword_analysis": keyword_analysis,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"]
        }

        result = SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title,
            description=description,
            score=scores["scores"]["total"],
            insights={"word_count": word_count},
            smart=smart
        )

        save_to_cache(url, result.dict())
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest):
    try:
        target_url = req.url or req.website
        if not target_url:
            raise HTTPException(status_code=400, detail="url or website required")

        logger.info(f"Starting enhanced analysis for {target_url}")
        smart_resp = await analyze_competitor(AnalyzeRequest(url=target_url))
        result = smart_resp.dict()

        # Initialize analyzers
        competitor_benchmarking = CompetitorBenchmarking()
        industry_analyzer = IndustrySpecificAnalysis()
        
        # Add competitive analysis
        if req.analyze_social:
            try:
                benchmark_results = await competitor_benchmarking.analyze_competitor_landscape(
                    target_url, 
                    result["smart"]["keyword_analysis"].get("detected_industries", []),
                    max_competitors=3
                )
                result["competitive_analysis"] = benchmark_results
            except Exception as e:
                logger.error(f"Competitive analysis failed: {e}")

        # Add industry weighting
        industry_weighted = industry_analyzer.calculate_industry_weighted_score(
            result["smart"]["scores"],
            result["smart"]["keyword_analysis"].get("detected_industries", [])
        )
        result["industry_analysis"] = industry_weighted

        # AI enhancement
        ai_full = {}
        if openai_client and req.use_ai:
            try:
                summary = {
                    "url": result.get("url"),
                    "scores": result["smart"]["scores"],
                    "top_findings": result["smart"]["top_findings"],
                    "social_signals": result["smart"]["social_signals"],
                    "content_quality": result["smart"]["content_quality"]
                }

                language = (req.language or 'fi').lower()
                
                if language == 'en':
                    prompt = f"""Analyze this website data and create strategic insights in JSON format:

{json.dumps(summary, ensure_ascii=False, indent=2)}

Return JSON with:
{{
  "executive_summary": "3-4 sentence overview",
  "strengths": ["4-5 specific advantages"],
  "weaknesses": ["4-5 improvement areas"], 
  "opportunities": ["4-5 growth opportunities"],
  "threats": ["3 competitive risks"],
  "strategic_recommendations": [
    {{"title": "Action", "description": "Details", "priority": "high/medium/low"}}
  ]
}}"""
                else:
                    prompt = f"""Analysoi sivustodata ja luo strategisia oivalluksia JSON-muodossa:

{json.dumps(summary, ensure_ascii=False, indent=2)}

Palauta JSON:
{{
  "johtopäätökset": "3-4 lauseen yhteenveto",
  "vahvuudet": ["4-5 kilpailuetua"],
  "heikkoudet": ["4-5 kehityskohdetta"],
  "mahdollisuudet": ["4-5 kasvumahdollisuutta"],
  "uhat": ["3 kilpailuriskiä"],
  "strategiset_suositukset": [
    {{"otsikko": "Toimenpide", "kuvaus": "Kuvaus", "prioriteetti": "korkea/keskitaso/matala"}}
  ]
}}"""

                resp = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a digital marketing strategist. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    max_tokens=1500
                )
                
                ai_response = resp.choices[0].message.content
                if ai_response:
                    ai_full = json.loads(ai_response)
                    
            except Exception as e:
                logger.error(f"AI analysis failed: {e}")

        # Fallback SWOT if AI failed
        if not ai_full:
            ai_full = generate_fallback_swot(result, req.language or 'fi', result["smart"]["social_signals"])

        # Build response
        response_data = {
            "success": True,
            "company_name": req.company_name,
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": {
                "company": req.company_name,
                "website": req.website or req.url,
                "digital_maturity_score": result["smart"]["scores"]["total"],
                "social_platforms": result["smart"]["social_signals"].get('analysis', {}).get('total_platforms', 0)
            },
            "ai_analysis": ai_full,
            "detailed_analysis": {
                "social_media": result["smart"]["social_signals"],
                "technical_audit": result["smart"]["tech_cro"],
                "content_analysis": result["smart"]["content_analysis"],
                "ux_analysis": result["smart"]["ux_analysis"],
                "keyword_analysis": result["smart"]["keyword_analysis"]
            },
            "competitive_analysis": result.get("competitive_analysis", {}),
            "industry_analysis": result.get("industry_analysis", {}),
            "smart": result["smart"]
        }

        return response_data

    except Exception as e:
        logger.error(f"Enhanced AI analyze failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(request: dict):
    """Generoi PDF-raportti ja palauta base64-enkoodattuna"""
    try:
        if not request:
            raise HTTPException(status_code=400, detail="Request data missing")
        
        company_name = request.get('company_name', 'Unknown Company')
        language = request.get('language', 'fi')
        
        buffer = generate_pdf_report(request, company_name, language)
        pdf_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        safe_company_name = re.sub(r'[^\w\-_\.]', '_', company_name)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f"competitor_analysis_{safe_company_name}_{timestamp}.pdf"
        
        return {
            "success": True,
            "pdf_base64": pdf_base64,
            "filename": filename,
            "size_bytes": len(buffer.getvalue()),
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@app.get("/api/v1/test-openai")
async def test_openai():
    if not openai_client:
        return {"status": "error", "message": "OpenAI client not configured"}

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Reply with just 'OK' if you work."}],
            max_tokens=10
        )
        return {"status": "success", "response": response.choices[0].message.content}
    except Exception as e:
        return {"status": "error", "message": f"OpenAI API error: {str(e)}"}

# Rate limiting
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
async def rate_limit_middleware(request: Request, call_next):
    ip = request.headers.get("X-Forwarded-For", request.client.host) if request.client else "unknown"
    if request.url.path.startswith("/api/v1/"):
        if not check_rate_limit(ip, 50):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    return await call_next(request)

# Error handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = hashlib.md5(f"{datetime.now()}{str(exc)}".encode()).hexdigest()[:8]
    logger.error(f"ERROR {error_id}: {str(exc)}")
    
    if "timeout" in str(exc).lower():
        user_message = "Sivuston lataus kesti liian kauan. Yritä uudelleen."
    elif "connection" in str(exc).lower():
        user_message = "Yhteysongelma sivustoon. Tarkista URL ja yritä uudelleen."
    else:
        user_message = "Sisäinen virhe. Yritä hetken kuluttua uudelleen."
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Sisäinen virhe",
            "error_id": error_id,
            "message": user_message,
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
