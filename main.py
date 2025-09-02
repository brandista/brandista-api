import os
import re
import json
import base64
import hashlib
import logging
import asyncio
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from functools import lru_cache, wraps
from collections import defaultdict
from enum import Enum
import time

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, validator, HttpUrl

# System monitoring (optional)
try:
    import psutil
    import platform
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

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

APP_VERSION = "5.0.0"

# ========== CUSTOM EXCEPTIONS ==========
class AnalysisError(Exception):
    """Custom exception for analysis errors"""
    pass

class RateLimitError(Exception):
    """Custom exception for rate limit errors"""
    pass

class ScrapingError(Exception):
    """Custom exception for scraping errors"""
    pass

# ========== PERFORMANCE TRACKING ==========
def track_performance(func):
    """Decorator to track async function performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            duration = time.perf_counter() - start
            logger.info(f"{func.__name__} completed in {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            logger.error(f"{func.__name__} failed after {duration:.2f}s: {str(e)}")
            raise
    return wrapper

# ========== CACHE HELPERS ==========
analysis_cache: Dict[str, Dict[str, Any]] = {}

def cache_key(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode("utf-8")).hexdigest()

def get_cached_analysis(url: str):
    """Get from cache if less than 24h old"""
    key = cache_key(url)
    cached = analysis_cache.get(key)
    if cached and (datetime.now() - cached['timestamp'] < timedelta(hours=24)):
        logger.info(f"Cache hit for {url}")
        return cached['data']
    return None

def save_to_cache(url: str, data: dict):
    """Save to cache"""
    key = cache_key(url)
    analysis_cache[key] = {'timestamp': datetime.now(), 'data': data}
    logger.info(f"Cached analysis for {url}")

# ========== APP INITIALIZATION ==========
app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Advanced Competitive Intelligence API with AI-powered analysis"
)

# CORS - Restrict in production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,https://yourdomain.com").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if os.getenv("ENV") == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    return response

# OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if (AsyncOpenAI and os.getenv("OPENAI_API_KEY")) else None

# Feature flags
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "1").lower() in ("1", "true", "yes")
USE_ENHANCED_AI = os.getenv("USE_ENHANCED_AI", "1").lower() in ("1", "true", "yes")

# ========== ENHANCED MODELS ==========

class MarketPosition(str, Enum):
    LEADER = "market_leader"
    CHALLENGER = "challenger"
    FOLLOWER = "follower"
    NICHER = "nicher"

class TechnologyMaturity(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall technology maturity score")
    modern_stack: bool = Field(description="Using modern tech stack")
    performance_optimized: bool = Field(description="Site is performance optimized")
    mobile_ready: bool = Field(description="Mobile-responsive design")
    security_headers: bool = Field(description="Proper security headers present")

class TrafficEstimate(BaseModel):
    organic_search: float = Field(ge=0, le=100, description="Estimated % from organic search")
    direct: float = Field(ge=0, le=100, description="Estimated % from direct traffic")
    social_media: float = Field(ge=0, le=100, description="Estimated % from social media")
    referral: float = Field(ge=0, le=100, description="Estimated % from referrals")
    paid_search: float = Field(ge=0, le=100, description="Estimated % from paid search")

class CompetitorInsights(BaseModel):
    """Structured competitor analysis insights"""
    market_positioning: MarketPosition
    unique_value_proposition: str = Field(max_length=500)
    target_audiences: List[str] = Field(max_items=5)
    competitive_advantages: List[str] = Field(max_items=10)
    improvement_areas: List[str] = Field(max_items=10)
    estimated_traffic_sources: TrafficEstimate
    technology_maturity: TechnologyMaturity
    content_strategy: str = Field(max_length=500)
    estimated_monthly_visitors: Optional[int] = Field(ge=0, default=None)
    conversion_optimization_score: int = Field(ge=1, le=10)

class ActionItem(BaseModel):
    title: str
    description: str
    priority: str = Field(pattern="^(high|medium|low|korkea|keskitaso|matala)$")
    timeline: str
    expected_impact: Optional[str] = None
    metrics: Optional[List[str]] = None
    estimated_cost: Optional[str] = None

class StrategicRecommendations(BaseModel):
    immediate_actions: List[ActionItem] = Field(max_items=3)
    short_term_actions: List[ActionItem] = Field(max_items=5)
    long_term_strategy: List[ActionItem] = Field(max_items=5)
    competitive_positioning: str = Field(max_length=1000)

class AnalyzeRequest(BaseModel):
    url: str
    options: Optional[Dict[str, Any]] = {}
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v

class SmartAnalyzeResponse(BaseModel):
    success: bool
    url: str
    title: str
    description: str
    score: int
    insights: Dict[str, Any]
    smart: Dict[str, Any]
    performance_metrics: Optional[Dict[str, float]] = None

class CompetitorAnalysisRequest(BaseModel):
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    strengths: Optional[List[str]] = []
    weaknesses: Optional[List[str]] = []
    market_position: Optional[str] = None
    use_ai: Optional[bool] = True
    use_enhanced: Optional[bool] = True
    url: Optional[str] = None
    language: Optional[str] = 'fi'

# ========== HELPERS ==========

def maybe_scrape_with_javascript(url: str) -> Optional[str]:
    """Render JavaScript lazily. Returns HTML string or None if unavailable/failed."""
    if not SMART_JS_RENDER:
        return None
    try:
        from requests_html import HTMLSession
    except Exception as e:
        logger.warning(f"[JS-RENDER] requests_html unavailable: {e}")
        return None

    try:
        session = HTMLSession()
        response = session.get(url, timeout=30)
        response.html.render(timeout=20, sleep=2)
        return response.html.html
    except Exception as e:
        logger.error(f"[JS-RENDER] Rendering failed: {e}")
        return None

async def fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""

@track_performance
async def collect_robots_and_sitemap(base_url: str) -> Dict[str, Any]:
    from urllib.parse import urljoin
    origin = base_url.split('/', 3)[:3]
    origin = '/'.join(origin) + '/'
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
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
    
    return {
        "sitemap_count": len(sitemap_urls),
        "url_sample_count": len(urls),
        "latest_post_date": str(latest_date) if latest_date else None
    }

def extract_head_signals(soup: BeautifulSoup) -> Dict[str, Any]:
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

TECH_HINTS = {
    "cms": [
        ("wordpress","WordPress"),("shopify","Shopify"),("wix","Wix"),
        ("webflow","Webflow"),("woocommerce","WooCommerce"),("squarespace","Squarespace"),
        ("joomla","Joomla"),("drupal","Drupal"),("magento","Magento")
    ],
    "framework": [
        ("__next","Next.js"),("nuxt","Nuxt"),("vite","Vite"),
        ("astro","Astro"),("sapper","Sapper"),("reactRoot","React"),
        ("angular","Angular"),("vue","Vue.js"),("svelte","Svelte")
    ],
    "analytics": [
        ("gtag(","GA4/gtag"),("googletagmanager.com","GTM"),
        ("facebook.net/en_US/fbevents.js","Meta Pixel"),
        ("clarity.ms","MS Clarity"),("hotjar","Hotjar"),
        ("matomo","Matomo"),("plausible","Plausible"),
        ("segment.com","Segment"),("mixpanel","Mixpanel")
    ]
}

def detect_tech_and_cro(soup: BeautifulSoup, html_text: str) -> Dict[str, Any]:
    lower = html_text.lower()
    gen = (soup.find('meta', attrs={'name':'generator'}) or {}).get('content','').lower()
    
    cms = next((name for key,name in TECH_HINTS["cms"] if key in gen or key in lower), None)
    framework = next((name for key,name in TECH_HINTS["framework"] if key in lower), None)
    analytics_pixels = [name for key,name in TECH_HINTS["analytics"] if key in lower]

    CTA_WORDS = [
        "osta","tilaa","varaa","lataa","book","buy","subscribe",
        "contact","get started","request a quote","pyydä tarjous",
        "varaa aika","aloita","sign up","demo","trial"
    ]
    
    cta_count = sum(1 for el in soup.find_all(["a","button"]) 
                    if any(w in (el.get_text(" ", strip=True) or "").lower() for w in CTA_WORDS))
    forms_count = len(soup.find_all("form"))

    contact_channels = []
    text = soup.get_text(" ", strip=True)
    if re.search(r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b', text, re.I): 
        contact_channels.append("email")
    if re.search(r'\+?\d[\d\s().-]{6,}', text): 
        contact_channels.append("phone")
    if "wa.me/" in lower or "api.whatsapp.com" in lower: 
        contact_channels.append("whatsapp")
    if "m.me/" in lower or "messenger" in lower:
        contact_channels.append("messenger")
    if "linkedin.com" in lower:
        contact_channels.append("linkedin")

    languages = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if re.search(r'/fi(/|$)', href): languages.add('fi')
        if re.search(r'/en(/|$)', href): languages.add('en')
        if re.search(r'/sv(/|$)', href): languages.add('sv')
        if re.search(r'/de(/|$)', href): languages.add('de')
        if re.search(r'/fr(/|$)', href): languages.add('fr')

    return {
        "cms": cms, 
        "framework": framework, 
        "analytics_pixels": sorted(list(set(analytics_pixels))),
        "cta_count": cta_count, 
        "forms_count": forms_count,
        "contact_channels": sorted(list(set(contact_channels))),
        "languages": sorted(list(languages))
    }

def score_and_recommend(head_sig, tech_cro, word_count) -> Dict[str, Any]:
    seo_score = 0
    seo_score += 10 if head_sig['canonical'] else 0
    seo_score += 10 if head_sig['og_status']['has_title'] else 0
    seo_score += 5 if head_sig['og_status']['has_desc'] else 0
    seo_score += 5 if head_sig['og_status']['has_image'] else 0
    
    content_score = 20 if word_count > 10000 else 15 if word_count > 5000 else 8 if word_count > 1000 else 0
    
    cro_score = min(15, tech_cro['cta_count']*2) + (5 if tech_cro['forms_count'] > 0 else 0)
    
    trust_score = 0
    if 'Organization' in head_sig['schema_counts']: trust_score += 5
    if 'LocalBusiness' in head_sig['schema_counts']: trust_score += 3
    if len(tech_cro['contact_channels']) >= 2: trust_score += 2
    
    tech_score = 0
    if tech_cro['analytics_pixels']: tech_score += 5
    if tech_cro['cms'] or tech_cro['framework']: tech_score += 5
    
    total = min(100, seo_score + content_score + cro_score + trust_score + tech_score)

    findings, actions = [], []
    
    if not head_sig['canonical']:
        findings.append("Canonical puuttuu → riski duplikaateista")
        actions.append({
            "otsikko":"Lisää canonical",
            "kuvaus":"Aseta kanoninen osoite kaikille sivuille",
            "prioriteetti":"korkea",
            "aikataulu":"heti",
            "mittari":"Canonical löytyy"
        })
    
    if not (head_sig['og_status']['has_title'] and head_sig['og_status']['has_desc']):
        findings.append("OG-metat vajaat/puuttuu → heikko jaettavuus")
        actions.append({
            "otsikko":"OG-perusmetat kuntoon",
            "kuvaus":"og:title & og:description + 1200×630 og:image",
            "prioriteetti":"keskitaso",
            "aikataulu":"1–3kk",
            "mittari":"OG-validi"
        })
    
    if content_score < 8:
        findings.append("Sisältö vähäinen → kasvata laadukasta tekstiä")
        actions.append({
            "otsikko":"Sisältöohjelma",
            "kuvaus":"2–4 artikkelia/kk, FAQ ja case-tarinat",
            "prioriteetti":"korkea",
            "aikataulu":"1–3kk",
            "mittari":"Julkaisutahti"
        })
    
    if tech_cro['cta_count'] < 2:
        findings.append("Vähän CTA-elementtejä → heikko ohjaus konversioon")
        actions.append({
            "otsikko":"Lisää CTA-napit",
            "kuvaus":"Heroon pää-CTA + osioihin toissijaiset",
            "prioriteetti":"korkea",
            "aikataulu":"heti",
            "mittari":"CTA-tiheys"
        })
    
    if not tech_cro['analytics_pixels']:
        findings.append("Analytiikka/pikselit puuttuvat → ei seurantaa")
        actions.append({
            "otsikko":"Asenna analytiikka & pikselit",
            "kuvaus":"GA4, GTM, Meta Pixel, LinkedIn Insight",
            "prioriteetti":"korkea",
            "aikataulu":"heti",
            "mittari":"Tägien läsnäolo"
        })

    return {
        "scores": {
            "seo": seo_score,
            "content": content_score,
            "cro": cro_score,
            "trust": trust_score,
            "tech": tech_score,
            "total": total
        },
        "top_findings": findings[:6],
        "actions": actions[:8]
    }

def analyze_content(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Analyze site content in depth"""
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

    # Service/product hints
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

    # Trust signals
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

    # Quality metrics
    content_analysis["content_quality"] = {
        "text_length": len(text),
        "unique_words": len(set(text.lower().split())),
        "avg_sentence_length": len(text.split()) / max(len(text.split('.')), 1),
        "has_contact_info": bool(re.search(r'@|puh|tel|phone', text_lower)),
        "has_address": bool(re.search(r'\d{5}|finland|suomi|helsinki|tampere|turku|oulu', text_lower))
    }
    
    return content_analysis

# ========== ENHANCED AI ANALYSIS ==========

async def enhanced_ai_analysis(
    data: dict, 
    language: str = 'fi',
    use_gpt4: bool = True
) -> Dict[str, Any]:
    """Enhanced AI analysis with structured output using GPT-4 or fallback"""
    
    if not openai_client:
        logger.warning("OpenAI client not configured, returning basic analysis")
        return generate_fallback_analysis(data, language)
    
    # Prepare context from smart analysis
    context = {
        "url": data.get("url"),
        "scores": data.get("smart", {}).get("scores", {}),
        "top_findings": data.get("smart", {}).get("top_findings", []),
        "actions": data.get("smart", {}).get("actions", []),
        "tech_cro": data.get("smart", {}).get("tech_cro", {}),
        "head_signals": data.get("smart", {}).get("head_signals", {}),
        "content_analysis": data.get("smart", {}).get("content_analysis", {}),
        "sitemap": data.get("smart", {}).get("sitemap", {})
    }
    
    # Build comprehensive prompt
    if language == 'en':
        system_prompt = """You are an expert digital marketing strategist and competitive intelligence analyst. 
        Analyze the provided website data and generate structured insights following the exact schema provided.
        Base all conclusions on actual data provided, not assumptions."""
        
        user_prompt = f"""Analyze this competitor website data and provide structured insights:

WEBSITE DATA:
{json.dumps(context, ensure_ascii=False, indent=2)}

Create a comprehensive JSON analysis with:
1. "summary": 4-6 sentence description of the site, its condition and services/products found
2. "strengths": list of 4-6 strengths based on data
3. "weaknesses": list of 4-6 weaknesses based on findings
4. "opportunities": list of 4-5 opportunities to improve
5. "threats": list of 2-3 potential threats or risks
6. "recommendations": list of 6-8 actions with title, description, priority, timeline
7. "competitor_profile": assessment with target_audience, strengths, market_position

Respond ONLY in valid JSON format in ENGLISH."""

    else:  # Finnish
        system_prompt = """Olet digitaalisen markkinoinnin strategisti ja kilpailija-analyysin asiantuntija.
        Analysoi sivustodataa ja tuota strukturoituja oivalluksia annetun skeeman mukaisesti.
        Perusta kaikki johtopäätökset todelliseen dataan, ei oletuksiin."""
        
        user_prompt = f"""Analysoi tämä kilpailijasivuston data ja tuota strukturoidut oivallukset:

SIVUSTODATA:
{json.dumps(context, ensure_ascii=False, indent=2)}

Luo kattava JSON-analyysi sisältäen:
1. "yhteenveto": 4–6 lausetta sivuston tilasta ja palveluista/tuotteista
2. "vahvuudet": 4–6 vahvuutta datan perusteella
3. "heikkoudet": 4–6 heikkoutta löydösten perusteella
4. "mahdollisuudet": 4–5 mahdollisuutta parantaa
5. "uhat": 2–3 uhkaa/riskitekijää
6. "toimenpidesuositukset": 6–8 toimenpidettä: otsikko, kuvaus, prioriteetti, aikataulu
7. "kilpailijaprofiili": kohderyhmä, vahvuusalueet, markkina-asema

Vastaa VAIN JSON-muodossa SUOMEKSI."""

    try:
        model = "gpt-4-turbo-preview" if use_gpt4 else "gpt-4o-mini"
        
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000
        )
        
        result = json.loads(response.choices[0].message.content or "{}")
        
        # Calculate confidence score
        confidence = calculate_confidence_score(data)
        
        # Assess data quality
        quality = assess_data_quality(data)
        
        return {
            "success": True,
            "analysis_timestamp": datetime.now().isoformat(),
            "ai_full": result,
            "confidence_score": confidence,
            "data_quality": quality,
            "model_used": model
        }
        
    except Exception as e:
        logger.error(f"Enhanced AI analysis failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "fallback": generate_fallback_analysis(data, language)
        }

def calculate_confidence_score(data: dict) -> float:
    """Calculate confidence score based on data completeness"""
    score = 0.0
    weights = {
        "has_title": 0.1,
        "has_description": 0.1,
        "has_canonical": 0.1,
        "has_og_tags": 0.15,
        "has_schema": 0.15,
        "has_analytics": 0.15,
        "content_length": 0.15,
        "tech_detected": 0.1
    }
    
    smart = data.get("smart", {})
    
    if smart.get("meta", {}).get("title"):
        score += weights["has_title"]
    if smart.get("meta", {}).get("description"):
        score += weights["has_description"]
    if smart.get("head_signals", {}).get("canonical"):
        score += weights["has_canonical"]
    if smart.get("head_signals", {}).get("og_status", {}).get("has_title"):
        score += weights["has_og_tags"]
    if smart.get("head_signals", {}).get("schema_counts"):
        score += weights["has_schema"]
    if smart.get("tech_cro", {}).get("analytics_pixels"):
        score += weights["has_analytics"]
    if smart.get("content_analysis", {}).get("content_quality", {}).get("text_length", 0) > 1000:
        score += weights["content_length"]
    if smart.get("tech_cro", {}).get("cms") or smart.get("tech_cro", {}).get("framework"):
        score += weights["tech_detected"]
    
    return round(score * 100, 1)

def assess_data_quality(data: dict) -> Dict[str, Any]:
    """Assess the quality and completeness of scraped data"""
    smart = data.get("smart", {})
    content = smart.get("content_analysis", {})
    
    return {
        "completeness": {
            "meta_tags": bool(smart.get("meta", {}).get("title")),
            "content_extracted": content.get("content_quality", {}).get("text_length", 0) > 500,
            "tech_detected": bool(smart.get("tech_cro", {}).get("cms")),
            "seo_signals": bool(smart.get("head_signals", {}).get("canonical")),
            "sitemap_found": smart.get("sitemap", {}).get("sitemap_count", 0) > 0
        },
        "reliability": {
            "javascript_rendered": smart.get("flags", {}).get("js_render_enabled", False),
            "fresh_data": not smart.get("flags", {}).get("cached", False),
            "response_time": "fast"
        },
        "coverage": {
            "pages_analyzed": 1,
            "depth": "homepage_only"
        }
    }

def generate_fallback_analysis(data: dict, language: str) -> Dict[str, Any]:
    """Generate basic analysis when AI fails"""
    smart = data.get("smart", {})
    scores = smart.get("scores", {})
    
    if language == 'en':
        return {
            "summary": f"Website scored {scores.get('total', 0)}/100 in digital analysis.",
            "key_findings": smart.get("top_findings", []),
            "recommendations": [
                {"title": action.get("otsikko"), "priority": action.get("prioriteetti")}
                for action in smart.get("actions", [])[:5]
            ]
        }
    else:
        return {
            "yhteenveto": f"Sivusto sai {scores.get('total', 0)}/100 pistettä digitaalisessa analyysissä.",
            "keskeiset_löydökset": smart.get("top_findings", []),
            "suositukset": [
                {"otsikko": action.get("otsikko"), "prioriteetti": action.get("prioriteetti")}
                for action in smart.get("actions", [])[:5]
            ]
        }

# ========== PARALLEL PROCESSING ==========

async def collect_all_signals(url: str) -> Dict[str, Any]:
    """Parallel collection of all signals"""
    tasks = [
        collect_robots_and_sitemap(url),
        # Add more parallel tasks here as needed
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    combined = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task {i} failed: {result}")
        else:
            if i == 0:  # sitemap data
                combined["sitemap"] = result
    
    return combined

# ========== ENDPOINTS ==========

@app.get("/")
def home():
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status": "ok",
        "features": {
            "js_render": SMART_JS_RENDER,
            "enhanced_ai": USE_ENHANCED_AI,
            "monitoring": MONITORING_AVAILABLE
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
        "openai_configured": bool(openai_client),
        "smart_js_render_flag": SMART_JS_RENDER,
        "enhanced_ai_enabled": USE_ENHANCED_AI,
        "deps": {
            "requests_html": can_import("requests_html"),
            "lxml_html_clean": can_import("lxml_html_clean"),
            "pyppeteer": can_import("pyppeteer"),
        }
    }

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
@track_performance
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url
        
        # Check cache
        cached = get_cached_analysis(url)
        if cached:
            return SmartAnalyzeResponse(**cached)

        start_time = time.perf_counter()

        # 1) Fast fetch
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/2.0)'})
            response.raise_for_status()
            html_text = response.text

        fetch_time = time.perf_counter() - start_time

        soup = BeautifulSoup(html_text, 'html.parser')
        title_el = soup.find('title')
        meta_desc_el = soup.find('meta', {'name':'description'})
        h1_present = bool(soup.find('h1'))

        # 2) Heuristic → try JS rendering if needed
        if SMART_JS_RENDER and (not title_el or not meta_desc_el or not h1_present or soup.find('script', src=False)):
            js_html = maybe_scrape_with_javascript(url)
            if js_html:
                soup = BeautifulSoup(js_html, 'html.parser')

        title = (soup.find('title').text.strip() if soup.find('title') else "")
        description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
        word_count = len(soup.get_text(" ", strip=True).split())

        # Parallel signal collection
        signals = await collect_all_signals(url)
        
        head_sig = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, str(soup))
        content_data = analyze_content(soup, url)
        scores = score_and_recommend(head_sig, tech_cro, word_count)

        analysis_time = time.perf_counter() - start_time

        smart = {
            "meta": {
                "title": title or "Ei otsikkoa", 
                "description": description or "Ei kuvausta", 
                "canonical": head_sig['canonical']
            },
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": signals.get("sitemap", {}),
            "content_analysis": content_data,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"],
            "flags": {
                "js_render_enabled": SMART_JS_RENDER, 
                "cached": False
            }
        }

        result = SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title or "Ei otsikkoa",
            description=description or "Ei kuvausta",
            score=scores["scores"]["total"],
            insights={"word_count": word_count},
            smart=smart,
            performance_metrics={
                "fetch_time": round(fetch_time, 2),
                "total_time": round(analysis_time, 2)
            }
        )

        save_to_cache(url, result.dict())
        return result

    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/ai-analyze-enhanced")
async def ai_analyze_enhanced(req: CompetitorAnalysisRequest):
    """Enhanced AI analysis endpoint with structured output"""
    try:
        target_url = req.url or req.website
        if not target_url:
            raise HTTPException(status_code=400, detail="url or website required")

        # Run smart analysis first
        smart_resp = await analyze_competitor(AnalyzeRequest(url=target_url))
        result = smart_resp.dict()

        # Run enhanced AI analysis if requested
        if req.use_enhanced and USE_ENHANCED_AI:
            enhanced_result = await enhanced_ai_analysis(
                result,
                language=req.language or 'fi',
                use_gpt4=True
            )
            
            ai_full = enhanced_result.get("ai_full", {})
        else:
            # Use standard AI analysis
            enhanced_result = None
            ai_full = {}

        # Extract relevant data
        kilpailijaprofiili = ai_full.get("kilpailijaprofiili") or ai_full.get("competitor_profile") or {}
        if isinstance(kilpailijaprofiili, dict):
            erottautumiskeinot = kilpailijaprofiili.get("vahvuusalueet", kilpailijaprofiili.get("strengths", []))
        else:
            erottautumiskeinot = []

        # Quick wins
        ai_reco = ai_full.get("toimenpidesuositukset") or ai_full.get("recommendations") or []
        quick_wins_list = []
        for a in (ai_reco or result["smart"]["actions"])[:3]:
            if isinstance(a, dict):
                win = a.get("otsikko", a.get("title", ""))
            else:
                win = str(a)
            if win:
                quick_wins_list.append(win)

        return {
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
                        f"Sivusto {req.company_name} sai {result['smart']['scores']['total']}/100 pistettä digitaalisessa analyysissä."
                    )
                ),
                "vahvuudet": ai_full.get("vahvuudet", ai_full.get("strengths", [])),
                "heikkoudet": ai_full.get("heikkoudet", ai_full.get("weaknesses", [])),
                "mahdollisuudet": ai_full.get("mahdollisuudet", ai_full.get("opportunities", [])),
                "uhat": ai_full.get("uhat", ai_full.get("threats", [])),
                "toimenpidesuositukset": ai_reco or result["smart"]["actions"],
                "digitaalinen_jalanjalki": {
                    "arvio": result["smart"]["scores"]["total"] // 10,
                    "sosiaalinen_media": result["smart"]["tech_cro"]["analytics_pixels"],
                    "sisaltostrategia": "Aktiivinen" if len(result["smart"].get("content_analysis", {}).get("services_hints", [])) > 2 else "Kehitettävä"
                },
                "erottautumiskeinot": erottautumiskeinot,
                "quick_wins": quick_wins_list
            },
            "smart": result["smart"],
            "enhanced_insights": enhanced_result if enhanced_result else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enhanced AI analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI analyze failed: {str(e)}")

# Keep the original endpoint for compatibility
@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest):
    """Compatibility endpoint for legacy frontend"""
    req.use_enhanced = False  # Use standard analysis for compatibility
    return await ai_analyze_enhanced(req)

# Continue with remaining endpoints (batch, compare, PDF generation, etc.)
# [Include all the other endpoints from the original code...]

# ========== RATE LIMITING ==========
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
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if request.url.path.startswith("/api/v1/"):
        limits = {
            "/api/v1/batch-analyze": 10,
            "/api/v1/ai-analyze": 50,
            "/api/v1/analyze": 100
        }
        limit = next((v for k, v in limits.items() if request.url.path.startswith(k)), 100)
        if not check_rate_limit(ip, limit):
            return JSONResponse(
                status_code=429, 
                content={"detail": f"Rate limit exceeded. Max {limit} requests/hour"}
            )
    return await call_next(request)

# ========== ERROR HANDLER ==========
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    error_id = hashlib.md5(f"{datetime.now()}{str(exc)}".encode()).hexdigest()[:8]
    logger.error(f"ERROR {error_id}: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "error_id": error_id,
            "message": "Something went wrong. Please contact support with the error ID."
        }
    )
