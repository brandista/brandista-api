import os
import re
import json
import base64
from io import BytesIO
from datetime import datetime
from typing import Dict, List, Optional, Any

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# OpenAI (optional)
try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore

# PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

APP_VERSION = "4.1.0"

app = FastAPI(
    title="Brandista Competitive Intel API",
    version=APP_VERSION,
    description="Kilpailija-analyysi API with AI ja Smart Analyzer"
)

# CORS (voit kiristää domain-listan kun haluat)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers (älä aseta X-Frame meta-tagina frontissa)
@app.middleware("http")
async def add_security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp

# OpenAI client (optional)
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if (AsyncOpenAI and os.getenv("OPENAI_API_KEY")) else None

# Feature flag: JS render on/off (default OFF for stability)
SMART_JS_RENDER = os.getenv("SMART_JS_RENDER", "0").lower() in ("1", "true", "yes")

# ========== MODELS ==========

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
    url: Optional[str] = None  # voi käyttää samaa kenttää analyysiin

# ========== HELPERS ==========

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

    return {
        "scores":{"seo":seo_score,"content":content_score,"cro":cro_score,"trust":trust_score,"tech":tech_score,"total":total},
        "top_findings":findings[:6],
        "actions":actions[:8]
    }

# ========== ENDPOINTS ==========

@app.get("/")
def home():
    return {
        "api":"Brandista Competitive Intelligence API",
        "version": APP_VERSION,
        "status":"ok",
        "js_render_enabled": SMART_JS_RENDER
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
        "deps": {
            "requests_html": can_import("requests_html"),
            "lxml_html_clean": can_import("lxml_html_clean"),
            "pyppeteer": can_import("pyppeteer"),
        }
    }

@app.post("/api/v1/analyze", response_model=SmartAnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    try:
        url = request.url if request.url.startswith("http") else f"https://{request.url}"

        # 1) Nopea haku
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
            response.raise_for_status()
            html_text = response.text

        soup = BeautifulSoup(html_text, 'html.parser')
        title_el = soup.find('title')
        meta_desc_el = soup.find('meta', {'name':'description'})
        h1_present = bool(soup.find('h1'))

        # 2) Heuristiikka → kokeile JS-renderiä lazyna (vain jos flag päällä ja signaalit puuttuvat)
        if SMART_JS_RENDER and (not title_el or not meta_desc_el or not h1_present or soup.find('script', src=False)):
            js_html = maybe_scrape_with_javascript(url)
            if js_html:
                soup = BeautifulSoup(js_html, 'html.parser')

        title = (soup.find('title').text.strip() if soup.find('title') else "")
        description = (soup.find('meta', {'name':'description'}) or {}).get('content','')
        word_count = len(soup.get_text(" ", strip=True))

        head_sig = extract_head_signals(soup)
        tech_cro = detect_tech_and_cro(soup, str(soup))
        sitemap_info = await collect_robots_and_sitemap(url)
        scores = score_and_recommend(head_sig, tech_cro, word_count)

        smart = {
            "meta": {"title": title or "Ei otsikkoa", "description": description or "Ei kuvausta", "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"],
            "flags": {"js_render_enabled": SMART_JS_RENDER}
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
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest):
    """
    Yhteensopivuus-endpoint vanhalle frontille:
    - Ajaa /api/v1/analyze (älydata)
    - (valinnainen) AI-rikastus OPENAI_API_KEY:llä
    - Palauttaa legacy-muotoisen `ai_analysis`-lohkon + koko `smart` datan
    """
    try:
        target_url = req.url or req.website
        if not target_url:
            raise HTTPException(status_code=400, detail="url or website required")

        # 1) Aja uusi älyanalyysi
        smart_resp = await analyze_competitor(AnalyzeRequest(url=target_url))
        result = smart_resp.dict()

        # 2) (Optional) AI-rikastus – lisätään mukaan recommendations_ai
        ai_reco: List[Dict[str, Any]] = []
        if openai_client and req.use_ai:
            # Rakenna tiivis prompt smart-datasta
            summary = {
                "url": result.get("url"),
                "scores": result["smart"]["scores"],
                "top_findings": result["smart"]["top_findings"],
                "actions": result["smart"]["actions"],
                "tech_cro": result["smart"]["tech_cro"],
                "head_signals": result["smart"]["head_signals"],
            }
            prompt = (
                "Laadi 5 konkreettista toimenpidettä prioriteetin ja vaikutuksen mukaan. "
                "Muotoile JSON-listana, jokaisessa: otsikko, kuvaus, prioriteetti (korkea/keskitaso/matala), "
                "aikataulu (heti/1–3kk/3–6kk), mittari (KPI). Perusta ehdotukset tähän dataan:\n"
                + json.dumps(summary, ensure_ascii=False)
            )

            try:
                resp = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Olet suomalainen digitaalisen kasvun asiantuntija."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.5,
                    max_tokens=900,
                )
                parsed = json.loads(resp.choices[0].message.content)
                ai_reco = parsed.get("actions", parsed if isinstance(parsed, list) else [])
            except Exception as e:
                ai_reco = [{"otsikko":"AI-rikastus epäonnistui","kuvaus":str(e)}]

        # 3) Palauta legacy-ystävällinen muoto + smart-dataset
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
                "yhteenveto": f"Yhteenveto kohteesta {req.company_name or target_url}.",
                "vahvuudet": req.strengths or [],
                "heikkoudet": req.weaknesses or [],
                "mahdollisuudet": [],
                "uhat": [],
                "toimenpidesuositukset": ai_reco or result["smart"]["actions"],
                "digitaalinen_jalanjalki": {
                    "arvio": result["smart"]["scores"]["total"] // 10,
                    "sosiaalinen_media": result["smart"]["tech_cro"]["analytics_pixels"],
                    "sisaltostrategia": "—"
                },
                "erottautumiskeinot": [],
                "quick_wins": [a["otsikko"] for a in result["smart"]["actions"][:3]] if result["smart"]["actions"] else []
            },
            "smart": result["smart"]  # koko rikas dataset saatavilla frontille
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analyze failed: {str(e)}")

# ========== PDF GENERATION (säilytetty) ==========

@app.post("/api/v1/generate-pdf")
async def generate_pdf_report(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti AI-analyysista
    """
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24,
                                     textColor=colors.HexColor('#1a1a1a'), spaceAfter=30,
                                     alignment=TA_CENTER, fontName='Helvetica-Bold')
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16,
                                       textColor=colors.HexColor('#2563eb'), spaceAfter=12,
                                       spaceBefore=20, fontName='Helvetica-Bold')
        subheading_style = ParagraphStyle('CustomSubHeading', parent=styles['Heading3'], fontSize=13,
                                          textColor=colors.HexColor('#475569'), spaceAfter=8,
                                          spaceBefore=12, fontName='Helvetica-Bold')
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11,
                                      textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=8)

        story = []
        company_name = analysis_data.get('company_name', 'Kilpailija')
        story.append(Paragraph(f"Kilpailija-analyysi: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))

        story.append(Paragraph("Perustiedot", heading_style))
        basic_info = analysis_data.get('basic_analysis', {})
        basic_data = [
            ['Yritys:', company_name],
            ['Verkkosivusto:', basic_info.get('website', 'Ei tiedossa')],
            ['Toimiala:', basic_info.get('industry', 'Ei määritelty')],
            ['Analyysipäivä:', analysis_data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))]
        ]
        basic_table = Table(basic_data, colWidths=[5*cm, 12*cm])
        basic_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#334155')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 20))

        ai_analysis = analysis_data.get('ai_analysis', {})
        if ai_analysis:
            if ai_analysis.get('yhteenveto'):
                story.append(Paragraph("Yhteenveto", heading_style))
                story.append(Paragraph(ai_analysis['yhteenveto'], normal_style))
                story.append(Spacer(1, 20))

            story.append(Paragraph("SWOT-analyysi", heading_style))
            if ai_analysis.get('vahvuudet'):
                story.append(Paragraph("Vahvuudet", subheading_style))
                for v in ai_analysis['vahvuudet']: story.append(Paragraph(f"• {v}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('heikkoudet'):
                story.append(Paragraph("Heikkoudet", subheading_style))
                for w in ai_analysis['heikkoudet']: story.append(Paragraph(f"• {w}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('mahdollisuudet'):
                story.append(Paragraph("Mahdollisuudet", subheading_style))
                for o in ai_analysis['mahdollisuudet']: story.append(Paragraph(f"• {o}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('uhat'):
                story.append(Paragraph("Uhat", subheading_style))
                for t in ai_analysis['uhat']: story.append(Paragraph(f"• {t}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('digitaalinen_jalanjalki'):
                story.append(Paragraph("Digitaalinen jalanjälki", heading_style))
                digi = ai_analysis['digitaalinen_jalanjalki']
                if digi.get('arvio'): story.append(Paragraph(f"<b>Arvio:</b> {digi['arvio']}/10", normal_style))
                if digi.get('sosiaalinen_media'):
                    story.append(Paragraph("<b>Aktiiviset kanavat:</b>", normal_style))
                    for ch in digi['sosiaalinen_media']: story.append(Paragraph(f"• {ch}", normal_style))
                if digi.get('sisaltostrategia'):
                    story.append(Paragraph(f"<b>Sisältöstrategia:</b> {digi['sisaltostrategia']}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('toimenpidesuositukset'):
                story.append(PageBreak())
                story.append(Paragraph("Toimenpidesuositukset", heading_style))
                for idx, rec in enumerate(ai_analysis['toimenpidesuositukset'], 1):
                    title = rec.get('otsikko', f'Toimenpide {idx}') if isinstance(rec, dict) else f'Toimenpide {idx}'
                    story.append(Paragraph(f"{idx}. {title}", subheading_style))
                    if isinstance(rec, dict):
                        if rec.get('kuvaus'): story.append(Paragraph(rec['kuvaus'], normal_style))
                        details = []
                        if rec.get('prioriteetti'):
                            p = rec['prioriteetti']
                            color = '#dc2626' if p == 'korkea' else '#f59e0b' if p == 'keskitaso' else '#10b981'
                            details.append(f"<font color='{color}'><b>Prioriteetti:</b> {p}</font>")
                        if rec.get('aikataulu'): details.append(f"<b>Aikataulu:</b> {rec['aikataulu']}")
                        if details: story.append(Paragraph(" | ".join(details), normal_style))
                    story.append(Spacer(1, 15))

            if ai_analysis.get('erottautumiskeinot'):
                story.append(Paragraph("Erottautumiskeinot", heading_style))
                for m in ai_analysis['erottautumiskeinot']: story.append(Paragraph(f"• {m}", normal_style))
                story.append(Spacer(1, 20))
            if ai_analysis.get('quick_wins'):
                story.append(Paragraph("Nopeat voitot", heading_style))
                for win in ai_analysis['quick_wins']: story.append(Paragraph(f"✓ {win}", normal_style))

        doc.build(story)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=kilpailija_analyysi_{(company_name or 'raportti').replace(' ','_')}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-generointi epäonnistui: {str(e)}")

@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti base64-muodossa (fi/en). Sama logiikka kuin aiemmin.
    """
    try:
        language = analysis_data.get('language', 'fi')
        translations = {
            'fi': {'title':'Kilpailija-analyysi','basic_info':'Perustiedot','company':'Yritys','website':'Verkkosivusto','industry':'Toimiala','analysis_date':'Analyysipäivä','not_known':'Ei tiedossa','not_defined':'Ei määritelty','summary':'Yhteenveto','swot_analysis':'SWOT-analyysi','strengths':'Vahvuudet','weaknesses':'Heikkoudet','opportunities':'Mahdollisuudet','threats':'Uhat','digital_footprint':'Digitaalinen jalanjälki','score':'Arvio','active_channels':'Aktiiviset kanavat','content_strategy':'Sisältöstrategia','recommendations':'Toimenpidesuositukset','action':'Toimenpide','priority':'Prioriteetti','timeline':'Aikataulu','differentiation':'Erottautumiskeinot','quick_wins':'Nopeat voitot','high':'korkea','medium':'keskitaso','low':'matala'},
            'en': {'title':'Competitor Analysis','basic_info':'Basic Information','company':'Company','website':'Website','industry':'Industry','analysis_date':'Analysis Date','not_known':'Not known','not_defined':'Not defined','summary':'Summary','swot_analysis':'SWOT Analysis','strengths':'Strengths','weaknesses':'Weaknesses','opportunities':'Opportunities','threats':'Threats','digital_footprint':'Digital Footprint','score':'Score','active_channels':'Active Channels','content_strategy':'Content Strategy','recommendations':'Recommendations','action':'Action','priority':'Priority','timeline':'Timeline','differentiation':'Differentiation','quick_wins':'Quick Wins','high':'high','medium':'medium','low':'low'}
        }
        t = translations.get(language, translations['fi'])

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#1a1a1a'), spaceAfter=30, alignment=TA_CENTER, fontName='Helvetica-Bold')
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor('#2563eb'), spaceAfter=12, spaceBefore=20, fontName='Helvetica-Bold')
        subheading_style = ParagraphStyle('CustomSubHeading', parent=styles['Heading3'], fontSize=13, textColor=colors.HexColor('#475569'), spaceAfter=8, spaceBefore=12, fontName='Helvetica-Bold')
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=8)

        story = []
        company_name = analysis_data.get('company_name', 'Unknown')
        story.append(Paragraph(f"{t['title']}: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))

        story.append(Paragraph(t['basic_info'], heading_style))
        basic_info = analysis_data.get('basic_analysis', {})
        basic_data = [
            [f"{t['company']}:", company_name],
            [f"{t['website']}:", analysis_data.get('url', basic_info.get('website', t['not_known']))],
            [f"{t['industry']}:", basic_info.get('industry', t['not_defined'])],
            [f"{t['analysis_date']}:", analysis_data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))]
        ]
        basic_table = Table(basic_data, colWidths=[5*cm, 12*cm])
        basic_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#334155')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 20))

        ai_analysis = analysis_data.get('ai_analysis', {})
        if ai_analysis:
            if ai_analysis.get('yhteenveto') or ai_analysis.get('summary'):
                story.append(Paragraph(t['summary'], heading_style))
                story.append(Paragraph(ai_analysis.get('yhteenveto', ai_analysis.get('summary','')), normal_style))
                story.append(Spacer(1, 20))

            story.append(Paragraph(t['swot_analysis'], heading_style))
            for key, label in [('vahvuudet', t['strengths']), ('heikkoudet', t['weaknesses']), ('mahdollisuudet', t['opportunities']), ('uhat', t['threats'])]:
                items = ai_analysis.get(key, ai_analysis.get({'vahvuudet':'strengths','heikkoudet':'weaknesses','mahdollisuudet':'opportunities','uhat':'threats'}[key], []))
                if items:
                    story.append(Paragraph(label, subheading_style))
                    for it in items: story.append(Paragraph(f"• {it}", normal_style))
                    story.append(Spacer(1, 10))

            digi = ai_analysis.get('digitaalinen_jalanjalki', ai_analysis.get('digital_footprint', {}))
            if digi:
                story.append(Paragraph(t['digital_footprint'], heading_style))
                if digi.get('arvio') or digi.get('score'):
                    score = digi.get('arvio', digi.get('score', 0))
                    story.append(Paragraph(f"<b>{t['score']}:</b> {score}/10", normal_style))
                if digi.get('sosiaalinen_media') or digi.get('social_media'):
                    story.append(Paragraph(f"<b>{t['active_channels']}:</b>", normal_style))
                    for ch in digi.get('sosiaalinen_media', digi.get('social_media', [])):
                        story.append(Paragraph(f"• {ch}", normal_style))
                if digi.get('sisaltostrategia') or digi.get('content_strategy'):
                    story.append(Paragraph(f"<b>{t['content_strategy']}:</b> {digi.get('sisaltostrategia', digi.get('content_strategy',''))}", normal_style))
                story.append(Spacer(1, 20))

            recs = ai_analysis.get('toimenpidesuositukset', ai_analysis.get('recommendations', []))
            if recs:
                story.append(PageBreak())
                story.append(Paragraph(t['recommendations'], heading_style))
                for idx, rec in enumerate(recs, 1):
                    if isinstance(rec, dict):
                        title = rec.get('otsikko', rec.get('title', f"{t['action']} {idx}"))
                        story.append(Paragraph(f"{idx}. {title}", subheading_style))
                        if rec.get('kuvaus') or rec.get('description'):
                            story.append(Paragraph(rec.get('kuvaus', rec.get('description','')), normal_style))
                        details = []
                        p = rec.get('prioriteetti', rec.get('priority'))
                        if p:
                            color = '#dc2626' if p in ['korkea','high'] else '#f59e0b' if p in ['keskitaso','medium'] else '#10b981'
                            ptext = {'high':t['high'], 'medium':t['medium'], 'low':t['low']}.get(p, p)
                            details.append(f"<font color='{color}'><b>{t['priority']}:</b> {ptext}</font>")
                        tl = rec.get('aikataulu', rec.get('timeline'))
                        if tl: details.append(f"<b>{t['timeline']}:</b> {tl}")
                        if details: story.append(Paragraph(" | ".join(details), normal_style))
                    else:
                        story.append(Paragraph(f"{idx}. {rec}", normal_style))
                    story.append(Spacer(1, 15))

            methods = ai_analysis.get('erottautumiskeinot', ai_analysis.get('differentiation', []))
            if methods:
                story.append(Paragraph(t['differentiation'], heading_style))
                for m in methods: story.append(Paragraph(f"• {m}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('quick_wins'):
                story.append(Paragraph(t['quick_wins'], heading_style))
                for win in ai_analysis.get('quick_wins', []): story.append(Paragraph(f"✓ {win}", normal_style))

        doc.build(story)
        buffer.seek(0)
        pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        lang_suffix = 'en' if language == 'en' else 'fi'
        safe_company_name = company_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filename = f"competitor_analysis_{safe_company_name}_{timestamp}_{lang_suffix}.pdf"
        return {"success": True, "pdf_base64": pdf_base64, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
