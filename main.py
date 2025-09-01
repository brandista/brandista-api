from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
import os
import json

app = FastAPI(
    title="Brandista Competitive Intel API",
    version="1.0.0",
    description="Kilpailija-analyysi työkalu"
)

# CORS - Sallii frontend yhteydet
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tuotannossa vaihda: ["https://brandista.eu"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic mallit
class AnalysisRequest(BaseModel):
    url: str
    
class AnalysisResponse(BaseModel):
    success: bool
    url: str
    data: Dict
    score: int
    message: str

@app.get("/")
def home():
    """API:n etusivu"""
    return {
        "api": "Brandista Competitive Intelligence API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "documentation": "/docs",
            "health": "/health",
            "analyze": "POST /api/v1/analyze"
        },
        "github": "https://github.com/brandista/brandista-api"
    }

@app.get("/health")
def health_check():
    """Tarkista palvelun tila"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01",
        "services": {
            "api": "operational",
            "database": bool(os.getenv("DATABASE_URL")),
            "redis": bool(os.getenv("REDIS_URL"))
        }
    }

@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze_competitor(request: AnalysisRequest):
    """
    Analysoi kilpailijan verkkosivu
    """
    try:
        # Varmista https://
        url = request.url
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        # Hae sivun sisältö
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
        
        # Parse HTML BeautifulSoupilla
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Kerää tiedot
        title = soup.find('title')
        title_text = title.text.strip() if title else "Ei otsikkoa"
        
        meta_desc = soup.find('meta', {'name': 'description'})
        description = meta_desc.get('content', '') if meta_desc else "Ei kuvausta"
        
        # Kerää otsikot
        h1_tags = [h1.text.strip() for h1 in soup.find_all('h1')][:5]
        h2_tags = [h2.t
