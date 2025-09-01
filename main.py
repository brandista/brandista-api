from requests_html import HTMLSession
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import httpx
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime
import base64
from io import BytesIO

# OpenAI import
from openai import AsyncOpenAI

# PDF generation imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

app = FastAPI(
    title="Brandista Competitive Intel API",
    version="4.0.0",
    description="Kilpailija-analyysi API with AI ja Smart Analyzer"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ========== JS RENDER SCRAPER ==========

def scrape_with_javascript(url: str) -> str:
    try:
        session = HTMLSession()
        response = session.get(url, timeout=30)
        response.html.render(timeout=20, sleep=2)
        return response.html.html
    except Exception as e:
        print(f"JavaScript rendering failed: {str(e)}")
        raise e

# ========== PYDANTIC MODELS ==========

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

# ========== HELPERS ==========

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
        "og_status": {"has_title": bool(og.get('og:title')), "has_desc": bool(og.get('og:description')), "has_image": bool(og.get('og:image'))},
        "twitter_status": {"has_title": bool(tw.get('twitter:title')), "has_desc": bool(tw.get('twitter:description')), "has_image": bool(tw.get('twitter:image'))},
        "schema_counts": {t: types.count(t) for t in set(types)}
    }

TECH_HINTS = {
    "cms": [("wordpress","WordPress"),("shopify","Shopify"),("wix","Wix"),("webflow","Webflow"),("woocommerce","WooCommerce")],
    "framework": [("__next","Next.js"),("nuxt","Nuxt"),("vite","Vite"),("astro","Astro")],
    "analytics": [("gtag(","GA4/gtag"),("googletagmanager.com","GTM"),("facebook.net/en_US/fbevents.js","Meta Pixel")]
}

def detect_tech_and_cro(soup: BeautifulSoup, html_text: str):
    gen = (soup.find('meta', attrs={'name':'generator'}) or {}).get('content','').lower()
    cms = next((name for key,name in TECH_HINTS["cms"] if key in gen or key in html_text.lower()), None)
    framework = next((name for key,name in TECH_HINTS["framework"] if key in html_text.lower()), None)
    analytics_pixels = [name for key,name in TECH_HINTS["analytics"] if key in html_text.lower()]
    CTA_WORDS = ["osta","tilaa","varaa","lataa","book","buy","subscribe","contact"]
    cta_count = sum(1 for el in soup.find_all(["a","button"]) if any(w in (el.get_text(" ", strip=True) or "").lower() for w in CTA_WORDS))
    forms_count = len(soup.find_all("form"))
    contact_channels = []
    text = soup.get_text(" ", strip=True)
    if re.search(r'@[a-z0-9.-]+\.[a-z]{2,}', text, re.I): contact_channels.append("email")
    if re.search(r'\+?\d[\d\s().-]{6,}', text): contact_channels.append("phone")
    languages = set()
    for a in soup.find_all('a', href=True):
        if re.search(r'/fi(/|$)', a['href']): languages.add('fi')
        if re.search(r'/en(/|$)', a['href']): languages.add('en')
    return {
        "cms": cms, "framework": framework, "analytics_pixels": analytics_pixels,
        "cta_count": cta_count, "forms_count": forms_count,
        "contact_channels": sorted(list(contact_channels)),
        "languages": sorted(list(languages))
    }

def score_and_recommend(head_sig, tech_cro, word_count):
    seo_score = 0
    seo_score += 10 if head_sig['canonical'] else 0
    seo_score += 10 if head_sig['og_status']['has_title'] else 0
    content_score = 15 if word_count>10000 else 8 if word_count>5000 else 0
    cro_score = min(15, tech_cro['cta_count']*2) + (5 if tech_cro['forms_count']>0 else 0)
    trust_score = 5 if 'Organization' in head_sig['schema_counts'] else 0
    tech_score = 5 if tech_cro['analytics_pixels'] else 0
    total = min(100, seo_score+content_score+cro_score+trust_score+tech_score)
    findings, actions = [], []
    if not head_sig['canonical']:
        findings.append("Canonical puuttuu")
        actions.append({"otsikko":"Lisää canonical","prioriteetti":"korkea","aikataulu":"heti"})
    if tech_cro['cta_count']<2:
        findings.append("Vähän CTA-elementtejä")
        actions.append({"otsikko":"Lisää CTA-napit","prioriteetti":"korkea","aikataulu":"heti"})
    return {
        "scores":{"seo":seo_score,"content":content_score,"cro":cro_score,"trust":trust_score,"tech":tech_score,"total":total},
        "top_findings":findings,
        "actions":actions
    }

# ========== ENDPOINTS ==========

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
        html_text = response.text
        soup = BeautifulSoup(html_text, 'html.parser')

        title = (soup.find('title').text.strip() if soup.find('title') else "")
        description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
        word_count = len(soup.get_text(" ", strip=True))

        # advanced signals
        head_sig = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, html_text)
        sitemap_info = await collect_robots_and_sitemap(url)
        scores = score_and_recommend(head_sig, tech_cro, word_count)

        smart = {
            "meta": {"title": title, "description": description, "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"]
        }

        return SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title or "Ei otsikkoa",
            description=description or "Ei kuvausta",
            score=scores["scores"]["total"],
            insights={"word_count": word_count},
            smart=smart
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.get("/")
def home():
    return {"api":"Brandista Competitive Intelligence API v4","status":"ok"}
