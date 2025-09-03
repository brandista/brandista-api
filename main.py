#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Competitive Intelligence API
Version: 5.5.0 - Production Ready
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import httpx
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
import asyncio
import logging
import base64
import hashlib

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Brandista Competitive Intelligence API",
    version="5.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Models
class CompetitorAnalysisRequest(BaseModel):
    url: str
    company_name: str
    analysis_type: Optional[str] = "comprehensive"
    language: Optional[str] = "fi"

# Simple cache
cache = {}

def get_cache_key(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()

# Core analysis function
async def analyze_website(url: str) -> Dict[str, Any]:
    """Analyze website and extract data"""
    try:
        if not url.startswith("http"):
            url = f"https://{url}"
            
        # Check cache
        cache_key = get_cache_key(url)
        if cache_key in cache:
            logger.info(f"Cache hit for {url}")
            return cache[cache_key]
            
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract data
        title = soup.find('title')
        title_text = title.text.strip() if title else ""
        
        meta_desc = soup.find('meta', {'name': 'description'})
        description = meta_desc.get('content', '') if meta_desc else ""
        
        text_content = soup.get_text(separator=' ', strip=True)
        word_count = len(text_content.split())
        
        # Detect technologies
        tech_detected = []
        html_lower = html.lower()
        
        tech_patterns = {
            "WordPress": r"wp-content|wp-includes",
            "React": r"react|_react",
            "Google Analytics": r"google-analytics|gtag",
            "jQuery": r"jquery",
            "Bootstrap": r"bootstrap"
        }
        
        for tech, pattern in tech_patterns.items():
            if re.search(pattern, html_lower):
                tech_detected.append(tech)
        
        result = {
            "url": url,
            "title": title_text,
            "description": description,
            "word_count": word_count,
            "technologies": tech_detected,
            "success": True
        }
        
        # Cache result
        cache[cache_key] = result
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing {url}: {e}")
        return {
            "url": url,
            "title": "",
            "description": "",
            "word_count": 0,
            "technologies": [],
            "success": False,
            "error": str(e)
        }

def calculate_score(data: Dict) -> int:
    """Calculate quality score"""
    score = 40
    if data.get("title"):
        score += 15
    if data.get("description"):
        score += 15
    if data.get("word_count", 0) > 500:
        score += 15
    if len(data.get("technologies", [])) > 0:
        score += 10
    if data.get("url", "").startswith("https"):
        score += 5
    return min(score, 100)

def generate_finnish_swot(data: Dict, company_name: str, score: int) -> Dict:
    """Generate Finnish SWOT analysis"""
    
    yhteenveto = f"Analysoitu sivusto {company_name} sai digitaalisessa arvioinnissa {score}/100 pistettä. "
    yhteenveto += f"Sivustolla on {data.get('word_count', 0)} sanaa sisältöä. "
    if data.get("technologies"):
        yhteenveto += f"Käytössä on {len(data['technologies'])} teknologiaa. "
    yhteenveto += "Analyysi tunnisti useita kehityskohteita."
    
    vahvuudet = []
    if score > 60:
        vahvuudet.append(f"Hyvä digitaalinen laatupisteet: {score}%")
    if data.get("technologies"):
        vahvuudet.append("Moderni teknologia käytössä")
    if data.get("word_count", 0) > 500:
        vahvuudet.append(f"Kattava sisältö: {data['word_count']} sanaa")
    if not vahvuudet:
        vahvuudet = ["Sivusto on toiminnassa", "Perusrakenne kunnossa"]
    
    heikkoudet = []
    if score < 70:
        heikkoudet.append("Digitaalista laatua voi parantaa")
    if not data.get("description"):
        heikkoudet.append("Meta-kuvaus puuttuu")
    if data.get("word_count", 0) < 500:
        heikkoudet.append("Sisältöä voisi olla enemmän")
    if not heikkoudet:
        heikkoudet = ["Pieniä parannuskohteita"]
    
    return {
        "yhteenveto": yhteenveto,
        "vahvuudet": vahvuudet[:5],
        "heikkoudet": heikkoudet[:5],
        "mahdollisuudet": [
            "Sisällön optimointi hakukoneille",
            "Käyttäjäkokemuksen parantaminen",
            "Analytiikan tehostaminen"
        ],
        "uhat": [
            "Kilpailijoiden kehitys",
            "Teknologinen muutos"
        ],
        "toimenpidesuositukset": [
            {
                "otsikko": "SEO-optimointi",
                "kuvaus": "Paranna hakukonenäkyvyyttä",
                "prioriteetti": "korkea",
                "aikataulu": "heti"
            },
            {
                "otsikko": "Sisällön lisäys",
                "kuvaus": "Lisää laadukasta sisältöä",
                "prioriteetti": "korkea",
                "aikataulu": "1-3kk"
            }
        ],
        "digitaalinen_jalanjalki": {
            "arvio": score // 10,
            "sosiaalinen_media": ["Facebook", "LinkedIn"],
            "sisaltostrategia": "Kehitettävä"
        },
        "quick_wins": [
            "Lisää meta-kuvaus",
            "Optimoi otsikot",
            "Asenna analytiikka"
        ]
    }

# Main endpoint
@app.post("/api/v1/ai-analyze")
async def ai_analyze(req: CompetitorAnalysisRequest):
    """AI analysis endpoint for frontend"""
    try:
        logger.info(f"Analyzing {req.url} for {req.company_name}")
        
        # Analyze website
        data = await analyze_website(req.url)
        
        # Calculate score
        score = calculate_score(data)
        
        # Generate SWOT
        ai_analysis = generate_finnish_swot(data, req.company_name, score)
        
        # Build response
        response = {
            "success": True,
            "company_name": req.company_name,
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": {
                "company": req.company_name,
                "website": req.url,
                "word_count": data.get("word_count", 0)
            },
            "ai_analysis": ai_analysis,
            "smart": {
                "actions": ai_analysis["toimenpidesuositukset"]
            }
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            "success": False,
            "company_name": req.company_name,
            "ai_analysis": {
                "yhteenveto": "Analyysi epäonnistui. Yritä uudelleen.",
                "vahvuudet": [],
                "heikkoudet": ["Sivustoa ei voitu analysoida"],
                "mahdollisuudet": [],
                "uhat": [],
                "toimenpidesuositukset": [],
                "digitaalinen_jalanjalki": {"arvio": 0},
                "quick_wins": []
            },
            "smart": {"actions": []}
        }

# PDF endpoint
@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(pdf_data: Dict[str, Any]):
    """Generate PDF in base64"""
    try:
        company = pdf_data.get("company_name", "Unknown")
        content = f"Kilpailija-analyysi\nYritys: {company}\nPäivämäärä: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        
        if "ai_analysis" in pdf_data:
            ai = pdf_data["ai_analysis"]
            content += f"Yhteenveto:\n{ai.get('yhteenveto', '')}\n\n"
            
            content += "Vahvuudet:\n"
            for v in ai.get("vahvuudet", []):
                content += f"- {v}\n"
                
        pdf_bytes = content.encode('utf-8')
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        return {
            "success": True,
            "pdf_base64": pdf_base64,
            "filename": f"analyysi_{company}_{datetime.now().strftime('%Y%m%d')}.txt"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Basic endpoints
@app.get("/")
def root():
    return {
        "name": "Brandista API",
        "version": "5.5.0",
        "status": "operational"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
