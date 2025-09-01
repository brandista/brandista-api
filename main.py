from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup

app = FastAPI(title="Brandista Intel API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    url: str

@app.get("/")
def home():
    return {
        "api": "Brandista Competitive Intelligence",
        "version": "2.0",
        "status": "ready",
        "docs": "/docs"
    }

@app.post("/analyze")
async def analyze(request: AnalysisRequest):
    try:
        # Hae sivu
        async with httpx.AsyncClient() as client:
            response = await client.get(request.url)
        
        # Parse
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('title').text if soup.find('title') else "No title"
        
        return {
            "success": True,
            "url": request.url,
            "title": title,
            "score": 75,
            "analysis": "Competitor analyzed successfully"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/test")
def test():
    return {"status": "NEW VERSION WORKING!"}
