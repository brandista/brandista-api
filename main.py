# app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Dict, List, Optional, Any
import httpx
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime

# OpenAI import
from openai import AsyncOpenAI

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
