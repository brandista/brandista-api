import os
import json
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import re
from collections import Counter

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# NLP Libraries
import nltk
import spacy
from textblob import TextBlob

# Machine Learning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
import numpy as np

# Transformers for advanced AI
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch

# Web scraping
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# OpenAI
try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

# --- Setup logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Download required NLTK data ---
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('vader_lexicon', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
    nltk.download('wordnet', quiet=True)
except Exception as e:
    logger.warning(f"Failed to download NLTK data: {e}")

# --- Load spaCy model ---
try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    logger.info("Downloading spaCy model...")
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# ====================== Configuration ======================

class Config:
    """Application configuration"""
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
    CACHE_TTL = 3600  # 1 hour
    MAX_WORKERS = 5
    RATE_LIMIT = "100/hour"
    SELENIUM_HEADLESS = True
    BATCH_SIZE = 10
    
    # AI Model configurations
    SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment"
    INDUSTRY_MODEL = "facebook/bart-large-mnli"
    SUMMARIZATION_MODEL = "facebook/bart-large-cnn"
    
    # Analysis thresholds
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 50000
    MIN_WORD_COUNT = 50
    QUALITY_THRESHOLD = 0.7

# ====================== Pydantic Models ======================

class AnalyzeRequest(BaseModel):
    url: HttpUrl
    deep_analysis: bool = True
    use_ai: bool = True
    language: str = Field(default="en", regex="^(en|fi|sv|de|fr|es)$")
    include_competitors: bool = False
    
class BatchAnalyzeRequest(BaseModel):
    urls: List[HttpUrl]
    compare: bool = True
    deep_analysis: bool = True
    language: str = "en"

class CompetitorAnalysisRequest(BaseModel):
    url: Optional[HttpUrl] = None
    website: Optional[HttpUrl] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    market_position: Optional[str] = None
    use_ai: bool = True
    language: Optional[str] = "fi"

class AnalysisResponse(BaseModel):
    success: bool
    url: str
    company_name: Optional[str]
    analysis_date: datetime
    basic_info: Dict[str, Any]
    smart_analysis: Dict[str, Any]
    ai_analysis: Optional[Dict[str, Any]]
    competitors: Optional[List[Dict[str, Any]]]
    recommendations: List[Dict[str, Any]]
    swot: Dict[str, List[str]]
    score: int

# ====================== Enhanced AI Analyzer ======================

class EnhancedAIAnalyzer:
    """Advanced AI analysis engine with multiple ML models"""
    
    def __init__(self):
        self.sentiment_analyzer = None
        self.industry_classifier = None
        self.summarizer = None
        self.topic_model = None
        self.initialize_models()
        
    def initialize_models(self):
        """Initialize all AI models"""
        try:
            # Sentiment analysis
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model=Config.SENTIMENT_MODEL,
                device=0 if torch.cuda.is_available() else -1
            )
            
            # Zero-shot classification for industry
            self.industry_classifier = pipeline(
                "zero-shot-classification",
                model=Config.INDUSTRY_MODEL,
                device=0 if torch.cuda.is_available() else -1
            )
            
            # Text summarization
            self.summarizer = pipeline(
                "summarization",
                model=Config.SUMMARIZATION_MODEL,
                device=0 if torch.cuda.is_available() else -1
            )
            
            logger.info("AI models initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI models: {e}")
            
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using multiple approaches"""
        results = {}
        
        # Transformer-based sentiment
        try:
            if self.sentiment_analyzer and len(text) > 10:
                transformer_result = self.sentiment_analyzer(
                    text[:512],  # Limit for BERT
                    truncation=True
                )[0]
                results["transformer"] = {
                    "label": transformer_result["label"],
                    "score": transformer_result["score"]
                }
        except Exception as e:
            logger.error(f"Transformer sentiment failed: {e}")
            
        # TextBlob sentiment
        try:
            blob = TextBlob(text)
            results["textblob"] = {
                "polarity": blob.sentiment.polarity,
                "subjectivity": blob.sentiment.subjectivity
            }
        except Exception as e:
            logger.error(f"TextBlob sentiment failed: {e}")
            
        # NLTK VADER sentiment
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer
            sia = SentimentIntensityAnalyzer()
            scores = sia.polarity_scores(text)
            results["vader"] = scores
        except Exception as e:
            logger.error(f"VADER sentiment failed: {e}")
            
        return results
    
    async def classify_industry(self, text: str, url: str) -> Dict[str, Any]:
        """Classify industry using zero-shot learning"""
        
        candidate_labels = [
            "Technology", "Healthcare", "Finance", "E-commerce",
            "Education", "Manufacturing", "Retail", "Real Estate",
            "Entertainment", "Food & Beverage", "Travel", "Automotive",
            "Energy", "Telecommunications", "Fashion", "Sports"
        ]
        
        try:
            if self.industry_classifier and len(text) > 50:
                result = self.industry_classifier(
                    text[:1024],
                    candidate_labels=candidate_labels,
                    multi_label=True
                )
                
                # Format results
                industry_scores = {}
                for label, score in zip(result["labels"], result["scores"]):
                    if score > 0.1:  # Threshold
                        industry_scores[label] = round(score, 3)
                        
                return {
                    "primary": result["labels"][0] if result["labels"] else "Unknown",
                    "scores": industry_scores,
                    "confidence": round(result["scores"][0], 3) if result["scores"] else 0
                }
        except Exception as e:
            logger.error(f"Industry classification failed: {e}")
            
        return {"primary": "Unknown", "scores": {}, "confidence": 0}
    
    async def extract_topics(self, text: str, num_topics: int = 5) -> List[Dict[str, Any]]:
        """Extract topics using LDA"""
        try:
            # Preprocess text
            sentences = nltk.sent_tokenize(text)
            if len(sentences) < 10:
                return []
                
            # TF-IDF Vectorization
            vectorizer = TfidfVectorizer(
                max_features=100,
                min_df=2,
                max_df=0.8,
                stop_words='english'
            )
            
            doc_term_matrix = vectorizer.fit_transform(sentences)
            
            # LDA Topic Modeling
            lda = LatentDirichletAllocation(
                n_components=min(num_topics, len(sentences) // 2),
                random_state=42
            )
            lda.fit(doc_term_matrix)
            
            # Extract topics
            feature_names = vectorizer.get_feature_names_out()
            topics = []
            
            for topic_idx, topic in enumerate(lda.components_):
                top_indices = topic.argsort()[-10:][::-1]
                top_words = [feature_names[i] for i in top_indices]
                topic_weight = topic[top_indices].mean()
                
                topics.append({
                    "id": topic_idx,
                    "words": top_words[:5],
                    "weight": round(float(topic_weight), 3)
                })
                
            return topics
            
        except Exception as e:
            logger.error(f"Topic extraction failed: {e}")
            return []
    
    async def analyze_competitors(self, text: str, url: str) -> List[str]:
        """Extract potential competitors from content"""
        competitors = set()
        
        try:
            # Use NER to find organizations
            doc = nlp(text[:5000])  # Limit for performance
            
            for ent in doc.ents:
                if ent.label_ == "ORG":
                    # Filter out common words
                    if len(ent.text) > 2 and ent.text.lower() not in [
                        "the", "and", "or", "we", "our", "us", "they"
                    ]:
                        competitors.add(ent.text)
                        
            # Look for competitor patterns
            patterns = [
                r"competing with ([A-Z][a-z]+)",
                r"competitors like ([A-Z][a-z]+)",
                r"vs\.? ([A-Z][a-z]+)",
                r"alternative to ([A-Z][a-z]+)"
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                competitors.update(matches)
                
        except Exception as e:
            logger.error(f"Competitor extraction failed: {e}")
            
        return list(competitors)[:10]  # Limit results
    
    async def generate_summary(self, text: str, max_length: int = 150) -> str:
        """Generate AI summary of content"""
        try:
            if self.summarizer and len(text) > 200:
                summary = self.summarizer(
                    text[:1024],
                    max_length=max_length,
                    min_length=30,
                    do_sample=False
                )[0]["summary_text"]
                return summary
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            
        # Fallback to simple extraction
        sentences = nltk.sent_tokenize(text)
        return " ".join(sentences[:3])

# ====================== Smart Web Scraper ======================

class SmartWebScraper:
    """Advanced web scraper with Selenium support"""
    
    def __init__(self):
        self.session = None
        self.driver = None
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
        if self.driver:
            self.driver.quit()
            
    def _setup_selenium(self):
        """Setup Selenium WebDriver"""
        options = Options()
        if Config.SELENIUM_HEADLESS:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        self.driver = webdriver.Chrome(options=options)
        
    async def fetch_with_render(self, url: str) -> Dict[str, Any]:
        """Fetch page with JavaScript rendering"""
        try:
            if not self.driver:
                self._setup_selenium()
                
            self.driver.get(str(url))
            
            # Wait for dynamic content
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Scroll to load lazy content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(1)
            
            # Get page data
            html = self.driver.page_source
            title = self.driver.title
            
            # Extract metadata
            meta_tags = {}
            metas = self.driver.find_elements(By.TAG_NAME, "meta")
            for meta in metas:
                name = meta.get_attribute("name") or meta.get_attribute("property")
                content = meta.get_attribute("content")
                if name and content:
                    meta_tags[name] = content
                    
            # Take screenshot
            screenshot = self.driver.get_screenshot_as_base64()
            
            return {
                "html": html,
                "title": title,
                "meta": meta_tags,
                "screenshot": screenshot,
                "rendered": True
            }
            
        except Exception as e:
            logger.error(f"Selenium fetch failed: {e}")
            # Fallback to regular fetch
            return await self.fetch_regular(url)
            
    async def fetch_regular(self, url: str) -> Dict[str, Any]:
        """Regular HTTP fetch without rendering"""
        try:
            response = await self.session.get(str(url))
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract metadata
            meta_tags = {}
            for meta in soup.find_all("meta"):
                name = meta.get("name") or meta.get("property")
                content = meta.get("content")
                if name and content:
                    meta_tags[name] = content
                    
            return {
                "html": response.text,
                "title": soup.title.string if soup.title else "",
                "meta": meta_tags,
                "rendered": False
            }
            
        except Exception as e:
            logger.error(f"HTTP fetch failed: {e}")
            raise

# ====================== Analysis Engine ======================

class AnalysisEngine:
    """Core analysis engine"""
    
    def __init__(self, ai_analyzer: EnhancedAIAnalyzer, cache: Optional[redis.Redis] = None):
        self.ai_analyzer = ai_analyzer
        self.cache = cache
        self.executor = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
        
    async def analyze_content(self, html: str, url: str) -> Dict[str, Any]:
        """Comprehensive content analysis"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract text content
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text()
        clean_text = ' '.join(text.split())
        
        # Basic metrics
        word_count = len(clean_text.split())
        
        # Headings analysis
        headings = {
            f"h{i}": len(soup.find_all(f"h{i}"))
            for i in range(1, 7)
        }
        
        # Links analysis
        internal_links = []
        external_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                if url in href:
                    internal_links.append(href)
                else:
                    external_links.append(href)
            else:
                internal_links.append(href)
                
        # Images analysis
        images = soup.find_all('img')
        images_with_alt = [img for img in images if img.get('alt')]
        
        # Forms and CTAs
        forms = soup.find_all('form')
        buttons = soup.find_all('button')
        cta_patterns = ['contact', 'buy', 'sign up', 'subscribe', 'download']
        ctas = [btn for btn in buttons if any(
            pattern in btn.get_text().lower() for pattern in cta_patterns
        )]
        
        # Technical analysis
        tech_stack = self._detect_technology(html, soup)
        
        # Schema.org data
        schema_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                schema_data.append(json.loads(script.string))
            except:
                pass
                
        return {
            "word_count": word_count,
            "headings": headings,
            "links": {
                "internal": len(internal_links),
                "external": len(external_links),
                "total": len(internal_links) + len(external_links)
            },
            "images": {
                "total": len(images),
                "with_alt": len(images_with_alt),
                "alt_percentage": round(len(images_with_alt) / len(images) * 100, 2) if images else 0
            },
            "forms": len(forms),
            "ctas": len(ctas),
            "tech_stack": tech_stack,
            "schema_data": schema_data,
            "text_preview": clean_text[:1000]
        }
        
    def _detect_technology(self, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
        """Detect technologies used on the website"""
        tech = {
            "cms": None,
            "frameworks": [],
            "analytics": [],
            "libraries": []
        }
        
        # CMS Detection
        cms_patterns = {
            "WordPress": ["wp-content", "wp-includes"],
            "Drupal": ["sites/all", "sites/default"],
            "Joomla": ["com_content", "com_users"],
            "Shopify": ["cdn.shopify", "myshopify.com"],
            "Wix": ["static.wixstatic.com"],
            "Squarespace": ["squarespace.com"],
        }
        
        for cms, patterns in cms_patterns.items():
            if any(pattern in html for pattern in patterns):
                tech["cms"] = cms
                break
                
        # Framework Detection
        framework_patterns = {
            "React": ["react", "reactdom"],
            "Angular": ["ng-app", "angular"],
            "Vue": ["vue.js", "v-for"],
            "jQuery": ["jquery"],
            "Bootstrap": ["bootstrap"],
            "Tailwind": ["tailwindcss"],
        }
        
        for framework, patterns in framework_patterns.items():
            if any(pattern.lower() in html.lower() for pattern in patterns):
                tech["frameworks"].append(framework)
                
        # Analytics Detection
        analytics_patterns = {
            "Google Analytics": ["google-analytics.com", "gtag", "ga.js"],
            "Google Tag Manager": ["googletagmanager.com"],
            "Facebook Pixel": ["facebook.com/tr"],
            "Hotjar": ["hotjar.com"],
            "Segment": ["segment.com", "segment.io"],
        }
        
        for analytics, patterns in analytics_patterns.items():
            if any(pattern in html for pattern in patterns):
                tech["analytics"].append(analytics)
                
        return tech
        
    async def calculate_scores(self, analysis: Dict[str, Any]) -> Dict[str, int]:
        """Calculate various quality scores"""
        scores = {}
        
        # SEO Score (0-30)
        seo_score = 0
        if analysis.get("meta", {}).get("description"):
            seo_score += 5
        if analysis.get("meta", {}).get("og:title"):
            seo_score += 5
        if analysis.get("content", {}).get("headings", {}).get("h1", 0) == 1:
            seo_score += 5
        if analysis.get("content", {}).get("images", {}).get("alt_percentage", 0) > 80:
            seo_score += 5
        if analysis.get("content", {}).get("schema_data"):
            seo_score += 10
        scores["seo"] = min(seo_score, 30)
        
        # Content Score (0-30)
        content_score = 0
        word_count = analysis.get("content", {}).get("word_count", 0)
        if word_count > 300:
            content_score += 10
        if word_count > 1000:
            content_score += 10
        if analysis.get("content", {}).get("headings", {}).get("h2", 0) > 2:
            content_score += 5
        if analysis.get("content", {}).get("images", {}).get("total", 0) > 3:
            content_score += 5
        scores["content"] = min(content_score, 30)
        
        # Technical Score (0-20)
        tech_score = 0
        tech = analysis.get("content", {}).get("tech_stack", {})
        if tech.get("analytics"):
            tech_score += 10
        if tech.get("frameworks"):
            tech_score += 5
        if analysis.get("rendered"):
            tech_score += 5
        scores["technical"] = min(tech_score, 20)
        
        # CRO Score (0-20)
        cro_score = 0
        if analysis.get("content", {}).get("forms", 0) > 0:
            cro_score += 10
        if analysis.get("content", {}).get("ctas", 0) > 2:
            cro_score += 10
        scores["cro"] = min(cro_score, 20)
        
        # Total Score
        scores["total"] = sum(scores.values())
        
        return scores
        
    async def generate_swot(self, analysis: Dict[str, Any], ai_insights: Dict[str, Any]) -> Dict[str, List[str]]:
        """Generate SWOT analysis"""
        swot = {
            "strengths": [],
            "weaknesses": [],
            "opportunities": [],
            "threats": []
        }
        
        scores = analysis.get("scores", {})
        content = analysis.get("content", {})
        
        # Strengths
        if scores.get("seo", 0) > 15:
            swot["strengths"].append(f"Strong SEO foundation ({scores['seo']}/30 points)")
        if content.get("word_count", 0) > 1000:
            swot["strengths"].append(f"Rich content ({content['word_count']} words)")
        if content.get("tech_stack", {}).get("analytics"):
            swot["strengths"].append(f"Analytics tracking implemented")
        if ai_insights.get("sentiment", {}).get("textblob", {}).get("polarity", 0) > 0.3:
            swot["strengths"].append("Positive brand messaging")
            
        # Weaknesses
        if scores.get("seo", 0) < 15:
            swot["weaknesses"].append("SEO needs improvement")
        if content.get("word_count", 0) < 500:
            swot["weaknesses"].append("Limited content depth")
        if not content.get("tech_stack", {}).get("analytics"):
            swot["weaknesses"].append("Missing analytics tracking")
        if content.get("images", {}).get("alt_percentage", 0) < 50:
            swot["weaknesses"].append("Poor image optimization")
            
        # Opportunities
        if scores.get("cro", 0) < 10:
            swot["opportunities"].append("Implement conversion optimization")
        if not content.get("schema_data"):
            swot["opportunities"].append("Add structured data markup")
        if len(content.get("tech_stack", {}).get("frameworks", [])) < 2:
            swot["opportunities"].append("Modernize technology stack")
        if ai_insights.get("topics"):
            swot["opportunities"].append("Expand content on key topics")
            
        # Threats
        if scores.get("total", 0) < 50:
            swot["threats"].append("Risk of losing to better-optimized competitors")
        if not content.get("tech_stack", {}).get("cms"):
            swot["threats"].append("Manual content management may limit scalability")
        if ai_insights.get("competitors"):
            swot["threats"].append(f"Competition from {len(ai_insights['competitors'])} identified competitors")
            
        # Ensure each category has at least 2 items
        for key in swot:
            if len(swot[key]) < 2:
                swot[key].append(f"Further analysis needed for {key}")
                
        return swot
        
    async def generate_recommendations(self, analysis: Dict[str, Any], swot: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations"""
        recommendations = []
        scores = analysis.get("scores", {})
        
        # Priority 1: Critical issues
        if scores.get("seo", 0) < 10:
            recommendations.append({
                "title": "Implement Essential SEO Elements",
                "description": "Add meta descriptions, optimize title tags, and implement structured data",
                "priority": "high",
                "timeline": "immediate",
                "impact": "high",
                "effort": "low"
            })
            
        if not analysis.get("content", {}).get("tech_stack", {}).get("analytics"):
            recommendations.append({
                "title": "Install Analytics Tracking",
                "description": "Implement Google Analytics and Tag Manager for data-driven decisions",
                "priority": "high",
                "timeline": "immediate",
                "impact": "high",
                "effort": "low"
            })
            
        # Priority 2: Quick wins
        if analysis.get("content", {}).get("images", {}).get("alt_percentage", 0) < 80:
            recommendations.append({
                "title": "Optimize Image Alt Tags",
                "description": "Add descriptive alt text to all images for better SEO and accessibility",
                "priority": "medium",
                "timeline": "1 week",
                "impact": "medium",
                "effort": "low"
            })
            
        if analysis.get("content", {}).get("word_count", 0) < 1000:
            recommendations.append({
                "title": "Expand Content Depth",
                "description": "Add more detailed content to key pages to improve engagement and SEO",
                "priority": "medium",
                "timeline": "2-4 weeks",
                "impact": "high",
                "effort": "medium"
            })
            
        # Priority 3: Strategic improvements
        if scores.get("cro", 0) < 15:
            recommendations.append({
                "title": "Implement CRO Strategy",
                "description": "Add clear CTAs, optimize forms, and create conversion-focused landing pages",
                "priority": "medium",
                "timeline": "1-2 months",
                "impact": "high",
                "effort": "high"
            })
            
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return recommendations[:10]  # Limit to top 10

# ====================== Cache Manager ======================

class CacheManager:
    """Redis cache manager"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        
    def _get_cache_key(self, url: str, analysis_type: str = "full") -> str:
        """Generate cache key"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"analysis:{analysis_type}:{url_hash}"
        
    async def get(self, url: str, analysis_type: str = "full") -> Optional[Dict[str, Any]]:
        """Get cached analysis"""
        if not self.redis:
            return None
            
        try:
            key = self._get_cache_key(url, analysis_type)
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            
        return None
        
    async def set(self, url: str, data: Dict[str, Any], analysis_type: str = "full"):
        """Set cached analysis"""
        if not self.redis:
            return
            
        try:
            key = self._get_cache_key(url, analysis_type)
            await self.redis.setex(
                key,
                Config.CACHE_TTL,
                json.dumps(data)
            )
        except Exception as e:
            logger.error(f"Cache set failed: {e}")

# ====================== Main Application ======================

# Initialize components
ai_analyzer = EnhancedAIAnalyzer()
redis_client = None
cache_manager = None
analysis_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client, cache_manager, analysis_engine
    
    # Startup
    try:
        redis_client = await redis.from_url(Config.REDIS_URL)
        cache_manager = CacheManager(redis_client)
        analysis_engine = AnalysisEngine(ai_analyzer, redis_client)
        logger.info("Application started successfully")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        cache_manager = CacheManager(None)
        analysis_engine = AnalysisEngine(ai_analyzer, None)
        
    yield
    
    # Shutdown
    if redis_client:
        await redis_client.close()
    logger.info("Application shutdown")

# Create FastAPI app
app = FastAPI(
    title="Advanced AI Competitor Analysis API",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ====================== API Endpoints ======================

@app.post("/api/v1/analyze", response_model=AnalysisResponse)
@limiter.limit(Config.RATE_LIMIT)
async def analyze_single(request: Request, req: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Single website analysis with AI enhancement"""
    
    url = str(req.url)
    
    # Check cache
    if cache_manager:
        cached = await cache_manager.get(url)
        if cached:
            logger.info(f"Returning cached analysis for {url}")
            return AnalysisResponse(**cached)
            
    try:
        async with SmartWebScraper() as scraper:
            # Fetch website
            if req.deep_analysis:
                page_data = await scraper.fetch_with_render(url)
            else:
                page_data = await scraper.fetch_regular(url)
                
            # Content analysis
            content_analysis = await analysis_engine.analyze_content(
                page_data["html"],
                url
            )
            
            # AI Analysis
            ai_results = {}
            if req.use_ai:
                text = content_analysis.get("text_preview", "")
                
                # Run AI analyses in parallel
                tasks = [
                    ai_analyzer.analyze_sentiment(text),
                    ai_analyzer.classify_industry(text, url),
                    ai_analyzer.extract_topics(text),
                    ai_analyzer.analyze_competitors(text, url),
                    ai_analyzer.generate_summary(text)
                ]
                
                results = await asyncio.gather(*tasks)
                
                ai_results = {
                    "sentiment": results[0],
                    "industry": results[1],
                    "topics": results[2],
                    "competitors": results[3],
                    "summary": results[4]
                }
                
            # Calculate scores
            analysis_data = {
                "meta": page_data.get("meta", {}),
                "content": content_analysis,
                "rendered": page_data.get("rendered", False)
            }
            
            scores = await analysis_engine.calculate_scores(analysis_data)
            
            # Generate SWOT
            swot = await analysis_engine.generate_swot(
                {"scores": scores, "content": content_analysis},
                ai_results
            )
            
            # Generate recommendations
            recommendations = await analysis_engine.generate_recommendations(
                {"scores": scores, "content": content_analysis},
                swot
            )
            
            # Prepare response
            response_data = {
                "success": True,
                "url": url,
                "company_name": page_data.get("meta", {}).get("og:site_name"),
                "analysis_date": datetime.now(),
                "basic_info": {
                    "title": page_data.get("title", ""),
                    "description": page_data.get("meta", {}).get("description", ""),
                    "keywords": page_data.get("meta", {}).get("keywords", "")
                },
                "smart_analysis": {
                    "scores": scores,
                    "content": content_analysis,
                    "tech_stack": content_analysis.get("tech_stack", {})
                },
                "ai_analysis": ai_results if req.use_ai else None,
                "competitors": ai_results.get("competitors") if req.use_ai else None,
                "recommendations": recommendations,
                "swot": swot,
                "score": scores.get("total", 0)
            }
            
            # Cache result in background
            if cache_manager:
                background_tasks.add_task(
                    cache_manager.set,
                    url,
                    response_data
                )
                
            return AnalysisResponse(**response_data)
            
    except Exception as e:
        logger.error(f"Analysis failed for {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/batch-analyze")
@limiter.limit("10/hour")
async def batch_analyze(request: Request, req: BatchAnalyzeRequest):
    """Batch analysis of multiple websites"""
    
    urls = [str(url) for url in req.urls[:Config.BATCH_SIZE]]
    
    # Create analysis tasks
    tasks = []
    for url in urls:
        analyze_req = AnalyzeRequest(
            url=url,
            deep_analysis=req.deep_analysis,
            use_ai=True,
            language=req.language
        )
        tasks.append(analyze_single(request, analyze_req, BackgroundTasks()))
        
    # Run analyses in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    analyses = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Batch analysis failed for {urls[i]}: {result}")
            analyses.append({
                "url": urls[i],
                "success": False,
                "error": str(result)
            })
        else:
            analyses.append(result)
            
    # Comparison analysis if requested
    comparison = None
    if req.compare and len(analyses) > 1:
        comparison = await compare_competitors(analyses)
        
    return {
        "success": True,
        "total": len(urls),
        "analyses": analyses,
        "comparison": comparison
    }

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(request: Request, req: CompetitorAnalysisRequest):
    """Compatibility endpoint for existing system"""
    
    target_url = req.url or req.website
    if not target_url:
        raise HTTPException(status_code=400, detail="url or website required")
        
    # Convert to standard analyze request
    analyze_req = AnalyzeRequest(
        url=target_url,
        deep_analysis=True,
        use_ai=req.use_ai,
        language=req.language or "fi"
    )
    
    # Run analysis
    result = await analyze_single(request, analyze_req, BackgroundTasks())
    
    # Convert to compatibility format
    language = (req.language or "fi").lower()
    
    if language == "fi":
        response_format = {
            "success": result.success,
            "company_name": req.company_name,
            "analysis_date": result.analysis_date.isoformat(),
            "basic_analysis": {
                "company": req.company_name,
                "website": str(target_url),
                "industry": result.ai_analysis.get("industry", {}).get("primary") if result.ai_analysis else None,
                "strengths_count": len(req.strengths or []),
                "weaknesses_count": len(req.weaknesses or []),
                "has_market_position": bool(req.market_position),
            },
            "ai_analysis": {
                "yhteenveto": result.ai_analysis.get("summary") if result.ai_analysis else "",
                "vahvuudet": result.swot["strengths"],
                "heikkoudet": result.swot["weaknesses"],
                "mahdollisuudet": result.swot["opportunities"],
                "uhat": result.swot["threats"],
                "toimenpidesuositukset": [
                    {
                        "otsikko": r["title"],
                        "kuvaus": r["description"],
                        "prioriteetti": r["priority"],
                        "aikataulu": r["timeline"]
                    }
                    for r in result.recommendations[:5]
                ],
                "digitaalinen_jalanjalki": {
                    "arvio": result.score // 10,
                    "sosiaalinen_media": result.smart_analysis.get("tech_stack", {}).get("analytics", []),
                    "sisaltostrategia": "Aktiivinen" if result.score > 60 else "Kehitettävä"
                },
                "erottautumiskeinot": [
                    "Tekninen toteutus",
                    "Sisältöstrategia",
                    "Käyttäjäkokemus"
                ],
                "quick_wins": [r["title"] for r in result.recommendations[:3]]
            },
            "smart": result.smart_analysis
        }
    else:
        response_format = {
            "success": result.success,
            "company_name": req.company_name,
            "analysis_date": result.analysis_date.isoformat(),
            "basic_analysis": {
                "company": req.company_name,
                "website": str(target_url),
                "industry": result.ai_analysis.get("industry", {}).get("primary") if result.ai_analysis else None,
                "strengths_count": len(req.strengths or []),
                "weaknesses_count": len(req.weaknesses or []),
                "has_market_position": bool(req.market_position),
            },
            "ai_analysis": {
                "summary": result.ai_analysis.get("summary") if result.ai_analysis else "",
                "strengths": result.swot["strengths"],
                "weaknesses": result.swot["weaknesses"],
                "opportunities": result.swot["opportunities"],
                "threats": result.swot["threats"],
                "recommendations": result.recommendations[:5],
                "digital_footprint": {
                    "score": result.score,
                    "analytics": result.smart_analysis.get("tech_stack", {}).get("analytics", []),
                    "content_strategy": "Active" if result.score > 60 else "Needs improvement"
                },
                "differentiation": [
                    "Technical implementation",
                    "Content strategy",
                    "User experience"
                ],
                "quick_wins": [r["title"] for r in result.recommendations[:3]]
            },
            "smart": result.smart_analysis
        }
        
    return response_format

async def compare_competitors(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare multiple competitor analyses"""
    
    comparison = {
        "average_score": 0,
        "best_performer": None,
        "weakest_performer": None,
        "common_strengths": [],
        "common_weaknesses": [],
        "industry_landscape": {},
        "recommendations": []
    }
    
    # Calculate averages and find extremes
    scores = [a.get("score", 0) for a in analyses if a.get("success")]
    if scores:
        comparison["average_score"] = round(sum(scores) / len(scores), 1)
        
        # Find best and weakest
        sorted_analyses = sorted(
            [a for a in analyses if a.get("success")],
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        
        if sorted_analyses:
            comparison["best_performer"] = {
                "url": sorted_analyses[0]["url"],
                "score": sorted_analyses[0]["score"]
            }
            comparison["weakest_performer"] = {
                "url": sorted_analyses[-1]["url"],
                "score": sorted_analyses[-1]["score"]
            }
            
    # Find common patterns
    all_strengths = []
    all_weaknesses = []
    
    for analysis in analyses:
        if analysis.get("success") and analysis.get("swot"):
            all_strengths.extend(analysis["swot"].get("strengths", []))
            all_weaknesses.extend(analysis["swot"].get("weaknesses", []))
            
    # Count occurrences
    strength_counts = Counter(all_strengths)
    weakness_counts = Counter(all_weaknesses)
    
    # Common patterns (appearing in >50% of sites)
    threshold = len(analyses) / 2
    comparison["common_strengths"] = [
        s for s, count in strength_counts.items()
        if count >= threshold
    ]
    comparison["common_weaknesses"] = [
        w for w, count in weakness_counts.items()
        if count >= threshold
    ]
    
    # Industry insights
    industries = {}
    for analysis in analyses:
        if analysis.get("ai_analysis", {}).get("industry"):
            ind = analysis["ai_analysis"]["industry"].get("primary")
            if ind:
                industries[ind] = industries.get(ind, 0) + 1
                
    comparison["industry_landscape"] = industries
    
    # Strategic recommendations
    if comparison["common_weaknesses"]:
        comparison["recommendations"].append({
            "title": "Exploit Common Weaknesses",
            "description": f"Most competitors share these weaknesses: {', '.join(comparison['common_weaknesses'][:3])}. Excel in these areas to gain competitive advantage.",
            "priority": "high"
        })
        
    if comparison["average_score"] < 60:
        comparison["recommendations"].append({
            "title": "Industry-Wide Digital Transformation Opportunity",
            "description": "The industry average digital score is low, presenting an opportunity to become a digital leader.",
            "priority": "high"
        })
        
    return comparison

@app.get("/health")
async def health():
    """Health check endpoint"""
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "api": "operational",
            "redis": "operational" if redis_client else "degraded",
            "ai_models": "operational" if ai_analyzer.sentiment_analyzer else "degraded"
        }
    }
    
    # Check Redis
    if redis_client:
        try:
            await redis_client.ping()
        except:
            health_status["components"]["redis"] = "down"
            health_status["status"] = "degraded"
            
    return health_status

@app.get("/")
async def root():
    """API information"""
    return {
        "name": "Advanced AI Competitor Analysis API",
        "version": "2.0.0",
        "endpoints": [
            "/api/v1/analyze - Single website analysis",
            "/api/v1/batch-analyze - Batch analysis",
            "/api/v1/ai-analyze - Legacy compatibility endpoint",
            "/health - Health check"
        ],
        "documentation": "/docs"
    }

# ====================== Main Entry Point ======================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV", "production") == "development"
    )
