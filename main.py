from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
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
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI(
    title="Brandista Competitive Intel API",
    version="3.0.0",
    description="Kilpailija-analyysi API with AI"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://brandista.eu",
        "https://www.brandista.eu",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ========== PYDANTIC MODELS ==========

class AnalyzeRequest(BaseModel):
    url: str
    
class AnalyzeResponse(BaseModel):
    success: bool
    url: str
    title: str
    description: str
    score: int
    insights: Dict
    recommendations: List[str]

class CompetitorAnalysisRequest(BaseModel):
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    strengths: Optional[List[str]] = []
    weaknesses: Optional[List[str]] = []
    market_position: Optional[str] = None
    use_ai: Optional[bool] = True

class AIAnalysisResponse(BaseModel):
    success: bool
    company_name: str
    analysis_date: str
    basic_analysis: Dict[str, Any]
    ai_analysis: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None

# ========== ORIGINAL ENDPOINTS ==========

@app.get("/")
def home():
    """API:n kotisivu"""
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": "3.0.0",
        "status": "operational",
        "documentation": "https://fastapi-production-51f9.up.railway.app/docs",
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "ai_analyze": "POST /api/v1/ai-analyze",
            "sample_analysis": "GET /api/v1/sample-analysis",
            "generate_pdf": "POST /api/v1/generate-pdf",
            "generate_pdf_base64": "POST /api/v1/generate-pdf-base64",
            "health": "GET /health",
            "test": "GET /test"
        }
    }

@app.get("/test")
def test():
    """Test endpoint"""
    return {"status": "AI VERSION WORKING!"}

@app.get("/health")
def health_check():
    """Tarkista palvelun tila"""
    return {
        "status": "healthy",
        "api": "running",
        "version": "3.0.0",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY"))
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    """Original HTML analysis endpoint"""
    try:
        url = request.url
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; BrandistaBot/1.0)'}
            )
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title = soup.find('title')
        title_text = title.text.strip() if title else "Ei otsikkoa"
        
        meta_desc = soup.find('meta', {'name': 'description'})
        description = meta_desc.get('content', '').strip() if meta_desc else "Ei kuvausta"
        
        h1_tags = [h1.text.strip() for h1 in soup.find_all('h1') if h1.text.strip()][:5]
        h2_tags = [h2.text.strip() for h2 in soup.find_all('h2') if h2.text.strip()][:10]
        
        internal_links = []
        external_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                if url.split('/')[2] in href:
                    internal_links.append(href)
                else:
                    external_links.append(href)
        
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, response.text)
        
        phone_pattern = r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,5}[-\s\.]?[0-9]{1,5}'
        phones = re.findall(phone_pattern, response.text)[:5]
        
        score = 0
        strengths = []
        weaknesses = []
        recommendations = []
        
        if title:
            score += 10
            strengths.append("Sivulla on title-tagi")
        else:
            weaknesses.append("Title-tagi puuttuu")
            recommendations.append("Varmista että sinun sivulla on optimoitu title-tagi")
            
        if meta_desc:
            score += 10
            strengths.append("Meta description löytyy")
        else:
            weaknesses.append("Meta description puuttuu")
            recommendations.append("Lisää houkutteleva meta description")
            
        if h1_tags:
            score += 15
            strengths.append(f"{len(h1_tags)} H1-otsikkoa")
        else:
            weaknesses.append("Ei H1-otsikoita")
            recommendations.append("Käytä H1-otsikoita sivun rakenteessa")
            
        if h2_tags:
            score += 10
            strengths.append(f"{len(h2_tags)} H2-otsikkoa")
            
        content_length = len(response.text)
        if content_length > 10000:
            score += 15
            strengths.append("Runsaasti sisältöä")
        elif content_length > 5000:
            score += 8
        else:
            weaknesses.append("Vähän sisältöä")
            recommendations.append("Lisää enemmän laadukasta sisältöä")
            
        if internal_links:
            score += 10
            strengths.append(f"{len(internal_links)} sisäistä linkkiä")
            
        if emails or phones:
            score += 10
            strengths.append("Yhteystiedot löytyvät")
        else:
            weaknesses.append("Yhteystietoja ei löydy helposti")
            
        viewport = soup.find('meta', {'name': 'viewport'})
        if viewport:
            score += 10
            strengths.append("Mobiiliresponsiivinen")
        else:
            weaknesses.append("Ei viewport-tagia (mobiili?)")
            recommendations.append("Varmista mobiiliresponsiivisuus")
            
        if score > 70:
            recommendations.append("Kilpailija on vahva - keskity erikoistumiseen")
        elif score > 50:
            recommendations.append("Kilpailijalla on parannettavaa - hyödynnä heikkoudet")
        else:
            recommendations.append("Kilpailija on heikko verkossa - ota markkinaosuutta")
            
        insights = {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "seo_score": min(30, (10 if title else 0) + (10 if meta_desc else 0) + (10 if h1_tags else 0)),
            "content_score": min(35, (15 if content_length > 10000 else 8 if content_length > 5000 else 0) + (10 if h2_tags else 0) + (10 if internal_links else 0)),
            "technical_score": min(35, (10 if viewport else 0) + (10 if emails or phones else 0) + 15),
            "h1_count": len(h1_tags),
            "h2_count": len(h2_tags),
            "internal_links": len(internal_links),
            "external_links": len(external_links),
            "emails_found": len(emails),
            "content_length": content_length
        }
        
        return AnalyzeResponse(
            success=True,
            url=url,
            title=title_text,
            description=description,
            score=min(100, score),
            insights=insights,
            recommendations=recommendations[:5]
        )
        
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

# ========== NEW AI ENDPOINTS ==========

@app.post("/api/v1/ai-analyze", response_model=AIAnalysisResponse)
async def ai_analyze_competitor(request: CompetitorAnalysisRequest):
    """
    Analysoi kilpailija AI:n avulla
    """
    try:
        # Basic analysis
        basic_analysis = {
            "company": request.company_name,
            "website": request.website,
            "industry": request.industry,
            "strengths_count": len(request.strengths) if request.strengths else 0,
            "weaknesses_count": len(request.weaknesses) if request.weaknesses else 0,
            "has_market_position": bool(request.market_position)
        }
        
        ai_analysis = None
        recommendations = None
        
        # AI analysis if requested
        if request.use_ai and os.getenv("OPENAI_API_KEY"):
            # Build prompt
            prompt = f"""
            Analysoi seuraava kilpailija ja anna toimenpidesuositukset:
            
            **Yritys:** {request.company_name}
            **Verkkosivusto:** {request.website or 'Ei tiedossa'}
            **Toimiala:** {request.industry or 'Ei määritelty'}
            
            **Kilpailijan vahvuudet:**
            {chr(10).join(['- ' + s for s in (request.strengths or [])])}
            
            **Kilpailijan heikkoudet:**
            {chr(10).join(['- ' + w for w in (request.weaknesses or [])])}
            
            **Markkinatilanne:**
            {request.market_position or 'Ei analysoitu'}
            
            Anna vastauksesi JSON-muodossa seuraavalla rakenteella:
            {{
                "yhteenveto": "Lyhyt 2-3 lauseen yhteenveto kilpailijasta",
                "vahvuudet": ["lista kilpailijan päävahvuuksista"],
                "heikkoudet": ["lista kilpailijan heikkouksista"],
                "mahdollisuudet": ["lista mahdollisuuksista, joita voit hyödyntää"],
                "uhat": ["lista uhista, joihin varautua"],
                "toimenpidesuositukset": [
                    {{
                        "otsikko": "Toimenpiteen nimi",
                        "kuvaus": "Mitä pitää tehdä",
                        "prioriteetti": "korkea/keskitaso/matala",
                        "aikataulu": "heti/1-3kk/3-6kk/6-12kk"
                    }}
                ],
                "digitaalinen_jalanjälki": {{
                    "arvio": "Kilpailijan digitaalisen näkyvyyden arvio 1-10",
                    "sosiaalinen_media": ["aktiiviset kanavat"],
                    "sisältöstrategia": "Kuvaus sisältöstrategiasta"
                }},
                "erottautumiskeinot": ["Konkreettiset tavat erottautua tästä kilpailijasta"],
                "quick_wins": ["Nopeat voitot, jotka voit toteuttaa heti"]
            }}
            """
            
            # Call OpenAI
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Olet digitaalisen markkinoinnin asiantuntija, joka analysoi kilpailijoita suomalaisille yrityksille. Anna konkreettisia toimenpidesuosituksia. Vastaa aina JSON-muodossa."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )
            
            ai_analysis = json.loads(response.choices[0].message.content)
            recommendations = ai_analysis.get("toimenpidesuositukset", [])
        
        return AIAnalysisResponse(
            success=True,
            company_name=request.company_name,
            analysis_date=datetime.now().isoformat(),
            basic_analysis=basic_analysis,
            ai_analysis=ai_analysis,
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/sample-analysis")
async def get_sample_analysis():
    """
    Hae esimerkki AI-analyysista (demo-tarkoituksiin)
    """
    if not os.getenv("OPENAI_API_KEY"):
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "message": "Add OPENAI_API_KEY to environment variables"
        }
    
    sample_competitor = CompetitorAnalysisRequest(
        company_name="Esimerkki Oy",
        website="https://esimerkki.fi",
        industry="Digitaalinen markkinointi",
        strengths=[
            "Vahva brändi",
            "Laaja asiakaskunta",
            "Hyvä asiakaspalvelu"
        ],
        weaknesses=[
            "Vanhentunut verkkosivusto",
            "Heikko sosiaalisen median läsnäolo",
            "Rajoitettu tuotevalikoima"
        ],
        market_position="Markkinajohtaja perinteisessä segmentissä, mutta haastaja digitaalisissa kanavissa",
        use_ai=True
    )
    
    # Use the AI analyze endpoint
    result = await ai_analyze_competitor(sample_competitor)
    
    return {
        "success": True,
        "sample_input": sample_competitor.dict(),
        "ai_analysis": result.dict(),
        "note": "Tämä on demo-analyysi. Käytä POST /api/v1/ai-analyze omille kilpailijoillesi."
    }

# ========== PDF GENERATION ENDPOINTS ==========

@app.post("/api/v1/generate-pdf")
async def generate_pdf_report(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti AI-analyysista
    """
    try:
        # Luo BytesIO buffer PDFää varten
        buffer = BytesIO()
        
        # Luo PDF dokumentti
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Hae tyylit
        styles = getSampleStyleSheet()
        
        # Luo custom tyylit
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=13,
            textColor=colors.HexColor('#475569'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#334155'),
            alignment=TA_JUSTIFY,
            spaceAfter=8
        )
        
        # Story - PDF sisältö
        story = []
        
        # Otsikko
        company_name = analysis_data.get('company_name', 'Kilpailija')
        story.append(Paragraph(f"Kilpailija-analyysi: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))
        
        # Perustiedot
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
        
        # AI-analyysi
        ai_analysis = analysis_data.get('ai_analysis', {})
        
        if ai_analysis:
            # Yhteenveto
            if ai_analysis.get('yhteenveto'):
                story.append(Paragraph("Yhteenveto", heading_style))
                story.append(Paragraph(ai_analysis['yhteenveto'], normal_style))
                story.append(Spacer(1, 20))
            
            # SWOT-analyysi
            story.append(Paragraph("SWOT-analyysi", heading_style))
            
            # Vahvuudet
            if ai_analysis.get('vahvuudet'):
                story.append(Paragraph("Vahvuudet", subheading_style))
                for vahvuus in ai_analysis['vahvuudet']:
                    story.append(Paragraph(f"• {vahvuus}", normal_style))
                story.append(Spacer(1, 10))
            
            # Heikkoudet
            if ai_analysis.get('heikkoudet'):
                story.append(Paragraph("Heikkoudet", subheading_style))
                for heikkous in ai_analysis['heikkoudet']:
                    story.append(Paragraph(f"• {heikkous}", normal_style))
                story.append(Spacer(1, 10))
            
            # Mahdollisuudet
            if ai_analysis.get('mahdollisuudet'):
                story.append(Paragraph("Mahdollisuudet", subheading_style))
                for mahdollisuus in ai_analysis['mahdollisuudet']:
                    story.append(Paragraph(f"• {mahdollisuus}", normal_style))
                story.append(Spacer(1, 10))
            
            # Uhat
            if ai_analysis.get('uhat'):
                story.append(Paragraph("Uhat", subheading_style))
                for uhka in ai_analysis['uhat']:
                    story.append(Paragraph(f"• {uhka}", normal_style))
                story.append(Spacer(1, 20))
            
            # Digitaalinen jalanjälki
            if ai_analysis.get('digitaalinen_jalanjälki'):
                story.append(Paragraph("Digitaalinen jalanjälki", heading_style))
                digi = ai_analysis['digitaalinen_jalanjälki']
                
                if digi.get('arvio'):
                    story.append(Paragraph(f"<b>Arvio:</b> {digi['arvio']}/10", normal_style))
                
                if digi.get('sosiaalinen_media'):
                    story.append(Paragraph("<b>Aktiiviset kanavat:</b>", normal_style))
                    for kanava in digi['sosiaalinen_media']:
                        story.append(Paragraph(f"• {kanava}", normal_style))
                
                if digi.get('sisältöstrategia'):
                    story.append(Paragraph(f"<b>Sisältöstrategia:</b> {digi['sisältöstrategia']}", normal_style))
                
                story.append(Spacer(1, 20))
            
            # Toimenpidesuositukset
            if ai_analysis.get('toimenpidesuositukset'):
                story.append(PageBreak())  # Uusi sivu toimenpiteille
                story.append(Paragraph("Toimenpidesuositukset", heading_style))
                
                for idx, toimenpide in enumerate(ai_analysis['toimenpidesuositukset'], 1):
                    # Toimenpiteen otsikko
                    otsikko = toimenpide.get('otsikko', f'Toimenpide {idx}')
                    story.append(Paragraph(f"{idx}. {otsikko}", subheading_style))
                    
                    # Kuvaus
                    if toimenpide.get('kuvaus'):
                        story.append(Paragraph(toimenpide['kuvaus'], normal_style))
                    
                    # Prioriteetti ja aikataulu
                    details = []
                    if toimenpide.get('prioriteetti'):
                        prioriteetti = toimenpide['prioriteetti']
                        color = '#dc2626' if prioriteetti == 'korkea' else '#f59e0b' if prioriteetti == 'keskitaso' else '#10b981'
                        details.append(f"<font color='{color}'><b>Prioriteetti:</b> {prioriteetti}</font>")
                    
                    if toimenpide.get('aikataulu'):
                        details.append(f"<b>Aikataulu:</b> {toimenpide['aikataulu']}")
                    
                    if details:
                        story.append(Paragraph(" | ".join(details), normal_style))
                    
                    story.append(Spacer(1, 15))
            
            # Erottautumiskeinot
            if ai_analysis.get('erottautumiskeinot'):
                story.append(Paragraph("Erottautumiskeinot", heading_style))
                for keino in ai_analysis['erottautumiskeinot']:
                    story.append(Paragraph(f"• {keino}", normal_style))
                story.append(Spacer(1, 20))
            
            # Quick Wins
            if ai_analysis.get('quick_wins'):
                story.append(Paragraph("Nopeat voitot", heading_style))
                for win in ai_analysis['quick_wins']:
                    story.append(Paragraph(f"✓ {win}", normal_style))
        
        # Generoi PDF
        doc.build(story)
        
        # Palauta PDF
        buffer.seek(0)
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=kilpailija_analyysi_{company_name.replace(' ', '_')}.pdf"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-generointi epäonnistui: {str(e)}")

@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti base64-muodossa (helpompi käsitellä frontendissä)
    """
    try:
        # Luo BytesIO buffer PDFää varten
        buffer = BytesIO()
        
        # Luo PDF dokumentti (sama koodi kuin yllä)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Hae tyylit
        styles = getSampleStyleSheet()
        
        # Luo custom tyylit
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=13,
            textColor=colors.HexColor('#475569'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#334155'),
            alignment=TA_JUSTIFY,
            spaceAfter=8
        )
        
        # Story - PDF sisältö
        story = []
        
        # Otsikko
        company_name = analysis_data.get('company_name', 'Kilpailija')
        story.append(Paragraph(f"Kilpailija-analyysi: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))
        
        # Perustiedot
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
        
        # AI-analyysi
        ai_analysis = analysis_data.get('ai_analysis', {})
        
        if ai_analysis:
            # Yhteenveto
            if ai_analysis.get('yhteenveto'):
                story.append(Paragraph("Yhteenveto", heading_style))
                story.append(Paragraph(ai_analysis['yhteenveto'], normal_style))
                story.append(Spacer(1, 20))
            
            # SWOT-analyysi
            story.append(Paragraph("SWOT-analyysi", heading_style))
            
            # Vahvuudet
            if ai_analysis.get('vahvuudet'):
                story.append(Paragraph("Vahvuudet", subheading_style))
                for vahvuus in ai_analysis['vahvuudet']:
                    story.append(Paragraph(f"• {vahvuus}", normal_style))
                story.append(Spacer(1, 10))
            
            # Heikkoudet
            if ai_analysis.get('heikkoudet'):
                story.append(Paragraph("Heikkoudet", subheading_style))
                for heikkous in ai_analysis['heikkoudet']:
                    story.append(Paragraph(f"• {heikkous}", normal_style))
                story.append(Spacer(1, 10))
            
            # Mahdollisuudet
            if ai_analysis.get('mahdollisuudet'):
                story.append(Paragraph("Mahdollisuudet", subheading_style))
                for mahdollisuus in ai_analysis['mahdollisuudet']:
                    story.append(Paragraph(f"• {mahdollisuus}", normal_style))
                story.append(Spacer(1, 10))
            
            # Uhat
            if ai_analysis.get('uhat'):
                story.append(Paragraph("Uhat", subheading_style))
                for uhka in ai_analysis['uhat']:
                    story.append(Paragraph(f"• {uhka}", normal_style))
                story.append(Spacer(1, 20))
            
            # Digitaalinen jalanjälki
            if ai_analysis.get('digitaalinen_jalanjälki'):
                story.append(Paragraph("Digitaalinen jalanjälki", heading_style))
                digi = ai_analysis['digitaalinen_jalanjälki']
                
                if digi.get('arvio'):
                    story.append(Paragraph(f"<b>Arvio:</b> {digi['arvio']}/10", normal_style))
                
                if digi.get('sosiaalinen_media'):
                    story.append(Paragraph("<b>Aktiiviset kanavat:</b>", normal_style))
                    for kanava in digi['sosiaalinen_media']:
                        story.append(Paragraph(f"• {kanava}", normal_style))
                
                if digi.get('sisältöstrategia'):
                    story.append(Paragraph(f"<b>Sisältöstrategia:</b> {digi['sisältöstrategia']}", normal_style))
                
                story.append(Spacer(1, 20))
            
            # Toimenpidesuositukset
            if ai_analysis.get('toimenpidesuositukset'):
                story.append(PageBreak())  # Uusi sivu toimenpiteille
                story.append(Paragraph("Toimenpidesuositukset", heading_style))
                
                for idx, toimenpide in enumerate(ai_analysis['toimenpidesuositukset'], 1):
                    # Toimenpiteen otsikko
                    otsikko = toimenpide.get('otsikko', f'Toimenpide {idx}')
                    story.append(Paragraph(f"{idx}. {otsikko}", subheading_style))
                    
                    # Kuvaus
                    if toimenpide.get('kuvaus'):
                        story.append(Paragraph(toimenpide['kuvaus'], normal_style))
                    
                    # Prioriteetti ja aikataulu
                    details = []
                    if toimenpide.get('prioriteetti'):
                        prioriteetti = toimenpide['prioriteetti']
                        color = '#dc2626' if prioriteetti == 'korkea' else '#f59e0b' if prioriteetti == 'keskitaso' else '#10b981'
                        details.append(f"<font color='{color}'><b>Prioriteetti:</b> {prioriteetti}</font>")
                    
                    if toimenpide.get('aikataulu'):
                        details.append(f"<b>Aikataulu:</b> {toimenpide['aikataulu']}")
                    
                    if details:
                        story.append(Paragraph(" | ".join(details), normal_style))
                    
                    story.append(Spacer(1, 15))
            
            # Erottautumiskeinot
            if ai_analysis.get('erottautumiskeinot'):
                story.append(Paragraph("Erottautumiskeinot", heading_style))
                for keino in ai_analysis['erottautumiskeinot']:
                    story.append(Paragraph(f"• {keino}", normal_style))
                story.append(Spacer(1, 20))
            
            # Quick Wins
            if ai_analysis.get('quick_wins'):
                story.append(Paragraph("Nopeat voitot", heading_style))
                for win in ai_analysis['quick_wins']:
                    story.append(Paragraph(f"✓ {win}", normal_style))
        
        # Generoi PDF
        doc.build(story)
        
        # Muunna base64:ksi
        buffer.seek(0)
        pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        
        return {
            "success": True,
            "pdf_base64": pdf_base64,
            "filename": f"kilpailija_analyysi_{company_name.replace(' ', '_')}.pdf"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-generointi epäonnistui: {str(e)}")
