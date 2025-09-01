from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
import json
import re

app = FastAPI(
    title="Brandista Competitive Intel API",
    version="2.0.0",
    description="Kilpailija-analyysi API"
)

# CORS - Tärkeä React-yhteyttä varten!
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://brandista.eu",
        "https://www.brandista.eu",
        "http://localhost:3000",
        "*"  # Testauksessa kaikki sallittu
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic mallit
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

@app.get("/")
def home():
    """API:n kotisivu"""
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": "2.0.0",
        "status": "operational",
        "documentation": "https://fastapi-production-51f9.up.railway.app/docs",
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "health": "GET /health",
            "test": "GET /test"
        }
    }

@app.get("/test")
def test():
    """Test endpoint"""
    return {"status": "NEW VERSION WORKING!"}

@app.get("/health")
def health_check():
    """Tarkista palvelun tila"""
    return {
        "status": "healthy",
        "api": "running",
        "version": "2.0.0"
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_competitor(request: AnalyzeRequest):
    """
    Analysoi kilpailijan verkkosivu
    
    Käyttö:
    POST /api/v1/analyze
    {"url": "https://example.com"}
    """
    try:
        # Lisää https:// jos puuttuu
        url = request.url
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        # Hae sivun sisältö
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; BrandistaBot/1.0)'}
            )
            response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Kerää perustiedot
        title = soup.find('title')
        title_text = title.text.strip() if title else "Ei otsikkoa"
        
        meta_desc = soup.find('meta', {'name': 'description'})
        description = meta_desc.get('content', '').strip() if meta_desc else "Ei kuvausta"
        
        # Kerää otsikot analyysia varten
        h1_tags = [h1.text.strip() for h1 in soup.find_all('h1') if h1.text.strip()][:5]
        h2_tags = [h2.text.strip() for h2 in soup.find_all('h2') if h2.text.strip()][:10]
        
        # Kerää linkit
        internal_links = []
        external_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                if url.split('/')[2] in href:
                    internal_links.append(href)
                else:
                    external_links.append(href)
        
        # Etsi yhteystiedot
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, response.text)
        
        phone_pattern = r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,5}[-\s\.]?[0-9]{1,5}'
        phones = re.findall(phone_pattern, response.text)[:5]
        
        # Laske kilpailija-pisteet (0-100)
        score = 0
        strengths = []
        weaknesses = []
        recommendations = []
        
        # SEO pisteet
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
            
        # Sisältö pisteet
        if h1_tags:
            score += 15
            strengths.append(f"{len(h1_tags)} H1-otsikkoa")
        else:
            weaknesses.append("Ei H1-otsikoita")
            recommendations.append("Käytä H1-otsikoita sivun rakenteessa")
            
        if h2_tags:
            score += 10
            strengths.append(f"{len(h2_tags)} H2-otsikkoa")
            
        # Sisällön määrä
        content_length = len(response.text)
        if content_length > 10000:
            score += 15
            strengths.append("Runsaasti sisältöä")
        elif content_length > 5000:
            score += 8
        else:
            weaknesses.append("Vähän sisältöä")
            recommendations.append("Lisää enemmän laadukasta sisältöä")
            
        # Linkit
        if internal_links:
            score += 10
            strengths.append(f"{len(internal_links)} sisäistä linkkiä")
            
        # Yhteystiedot
        if emails or phones:
            score += 10
            strengths.append("Yhteystiedot löytyvät")
        else:
            weaknesses.append("Yhteystietoja ei löydy helposti")
            
        # Mobile-responsive check
        viewport = soup.find('meta', {'name': 'viewport'})
        if viewport:
            score += 10
            strengths.append("Mobiiliresponsiivinen")
        else:
            weaknesses.append("Ei viewport-tagia (mobiili?)")
            recommendations.append("Varmista mobiiliresponsiivisuus")
            
        # Lisää yleisiä suosituksia
        if score > 70:
            recommendations.append("Kilpailija on vahva - keskity erikoistumiseen")
        elif score > 50:
            recommendations.append("Kilpailijalla on parannettavaa - hyödynnä heikkoudet")
        else:
            recommendations.append("Kilpailija on heikko verkossa - ota markkinaosuutta")
            
        # Rakenna insights
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
            recommendations=recommendations[:5]  # Top 5 suositusta
        )
        
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Virhe sivun haussa: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analyysi epäonnistui: {str(e)}"
        )
