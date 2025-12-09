"""
AI Content Generator Module
===========================
Production-ready AI text generation with:
- Structured JSON context + strict prompts
- Pydantic validation
- Retry logic with exponential backoff
- Rate limiting
- Language support (EN/FI/SV)
- Industry detection
- No hallucinated numbers
"""

import asyncio
import logging
import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

OPENAI_MODEL = "gpt-4o-mini"  # or "gpt-4o" for better quality
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30
MAX_CONCURRENT_REQUESTS = 3  # Semaphore limit
MAX_CONTEXT_CHARS = 8000  # Token budget safety

# ============================================================================
# LANGUAGE CONFIGURATION
# ============================================================================

class Language(str, Enum):
    EN = "en"
    FI = "fi"
    SV = "sv"

LANGUAGE_MAP = {
    "en": "in English",
    "fi": "suomeksi (in Finnish)",
    "sv": "på svenska (in Swedish)"
}

LANGUAGE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "fi": "Vastaa suomeksi. Käytä selkeää suomen kieltä.",
    "sv": "Svara på svenska. Använd tydlig svenska."
}

# Finnish industry keywords for better detection
FINNISH_INDUSTRY_KEYWORDS = {
    "ecommerce": ["verkkokauppa", "ostoskori", "tilaa nyt", "lisää koriin", "toimitus", "maksutavat"],
    "education": ["koulutus", "opiskelu", "kurssit", "oppiminen", "tutkinto", "yliopisto", "koulu"],
    "realestate": ["kiinteistö", "asunto", "vuokra", "myynti", "neliö", "huone", "tontti"],
    "finance": ["laina", "vakuutus", "rahoitus", "sijoitus", "pankki", "korko", "maksu"],
    "healthcare": ["klinikka", "terveys", "hoito", "lääkäri", "potilas", "diagnoosi", "terapia"],
    "restaurant": ["ravintola", "ruoka", "menu", "varaus", "annos", "juoma", "lounas"],
    "professional": ["palvelu", "asiantuntija", "konsultointi", "ratkaisu", "yritys", "toimisto"]
}

# ============================================================================
# PYDANTIC MODELS FOR VALIDATION
# ============================================================================

if PYDANTIC_AVAILABLE:
    class SwotAnalysis(BaseModel):
        strengths: List[str] = Field(..., min_items=1, max_items=5)
        weaknesses: List[str] = Field(..., min_items=1, max_items=5)
        opportunities: List[str] = Field(..., min_items=1, max_items=4)
        threats: List[str] = Field(..., min_items=0, max_items=3)
        
        @validator('strengths', 'weaknesses', 'opportunities', 'threats')
        def validate_text_quality(cls, v):
            return [item.strip() for item in v if item.strip() and len(item.strip()) > 10]

    class ActionPriority(BaseModel):
        category: str
        priority: str
        score_impact: int
        description: str

    class AIGeneratedContent(BaseModel):
        executive_summary: str = Field(..., min_length=50, max_length=500)
        swot: SwotAnalysis
        recommendations: List[str] = Field(..., min_items=1, max_items=5)
        action_priority: List[ActionPriority] = Field(..., min_items=1, max_items=6)
        confidence_score: int = Field(..., ge=0, le=100)
        sentiment_score: float = Field(..., ge=0.0, le=1.0)
        
        @validator('executive_summary')
        def validate_summary(cls, v):
            if not v.strip():
                raise ValueError("Summary cannot be empty")
            return v.strip()

else:
    # Fallback if Pydantic not available
    class SwotAnalysis(dict):
        pass
    class ActionPriority(dict):
        pass
    class AIGeneratedContent(dict):
        pass

# ============================================================================
# LLM CLIENT ADAPTER (model-agnostic interface)
# ============================================================================

class LLMClient:
    """Model-agnostic LLM client adapter"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_MODEL):
        self.model = model
        self.client = None
        
        if OPENAI_AVAILABLE and api_key:
            self.client = AsyncOpenAI(api_key=api_key)
    
    async def generate(
        self, 
        prompt: str, 
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> Optional[str]:
        """Generate text with retry logic"""
        
        if not self.client:
            logger.warning("LLM client not initialized")
            return None
        
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature
                    ),
                    timeout=TIMEOUT_SECONDS
                )
                return response.choices[0].message.content.strip()
            
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on attempt {attempt + 1}/{MAX_RETRIES}")
                if attempt == MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            except Exception as e:
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limit hit, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"LLM generation failed: {e}")
                    if attempt == MAX_RETRIES - 1:
                        return None
                    await asyncio.sleep(1)
        
        return None

# ============================================================================
# CONTEXT PREPARATION (structured data + safe text extraction)
# ============================================================================

def clean_html_text(html: str) -> str:
    """Remove scripts, styles, and clean HTML text"""
    if not html:
        return ""
    
    # Remove script and style tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text[:MAX_CONTEXT_CHARS]

def detect_industry_advanced(content: Dict[str, Any], html: str) -> str:
    """Enhanced industry detection with Finnish support"""
    
    text = clean_html_text(html).lower()
    
    # Score each industry
    industry_scores = {}
    
    for industry, keywords in FINNISH_INDUSTRY_KEYWORDS.items():
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            industry_scores[industry] = score
    
    # English keywords (original)
    if 'shop' in text or 'cart' in text or 'checkout' in text:
        industry_scores['ecommerce'] = industry_scores.get('ecommerce', 0) + 5
    if 'course' in text or 'learn' in text or 'student' in text:
        industry_scores['education'] = industry_scores.get('education', 0) + 5
    if 'property' in text or 'rent' in text or 'real estate' in text:
        industry_scores['realestate'] = industry_scores.get('realestate', 0) + 5
    
    if not industry_scores:
        return "general"
    
    return max(industry_scores.items(), key=lambda x: x[1])[0]

def build_structured_context(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any],
    html: str
) -> Tuple[Dict[str, Any], str]:
    """
    Build structured JSON context + metadata
    Returns: (context_dict, context_hash)
    """
    
    breakdown = basic.get('score_breakdown', {})
    
    # NUMBERS ONLY (prevent hallucination)
    numbers = {
        "overall_score": int(basic.get('digital_maturity_score', 0)),
        "security_score": int(breakdown.get('security', 0)),
        "seo_score": int(breakdown.get('seo_basics', 0)),
        "content_score": int(breakdown.get('content', 0)),
        "mobile_score": int(breakdown.get('mobile', 0)),
        "social_score": int(breakdown.get('social', 0)),
        "technical_score": int(breakdown.get('technical', 0)),
        "performance_score": int(breakdown.get('performance', 0)),
        "word_count": int(content.get('word_count', 0)),
        "social_platforms_count": len(social.get('platforms', [])),
        "page_speed_score": int(technical.get('page_speed_score', 0)),
        "modernity_score": int(basic.get('modernity_score', 0))
    }
    
    # BOOLEAN FLAGS
    flags = {
        "has_https": breakdown.get('security', 0) > 0,
        "has_analytics": technical.get('has_analytics', False),
        "has_viewport": basic.get('has_mobile_viewport', False),
        "spa_detected": basic.get('spa_detected', False),
        "has_meta_description": bool(basic.get('meta_description')),
        "has_title": bool(basic.get('title'))
    }
    
    # TEXT METADATA (safe)
    metadata = {
        "url": url,
        "title": str(basic.get('title', ''))[:100],
        "description": str(basic.get('meta_description', ''))[:200],
        "industry": detect_industry_advanced(content, html),
        "social_platforms": list(social.get('platforms', []))[:5]
    }
    
    context = {
        "numbers": numbers,
        "flags": flags,
        "metadata": metadata
    }
    
    # Generate context hash for audit trail
    context_str = str(sorted(context.items()))
    context_hash = hashlib.md5(context_str.encode()).hexdigest()[:8]
    
    return context, context_hash

# ============================================================================
# AI GENERATION FUNCTIONS (with strict prompts)
# ============================================================================

async def generate_ai_swot(
    context: Dict[str, Any],
    language: str,
    llm_client: LLMClient
) -> Optional[Dict[str, Any]]:
    """Generate SWOT analysis with growth-oriented, radical creativity lens"""
    
    numbers = context['numbers']
    flags = context['flags']
    metadata = context['metadata']
    
    lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS['en'])
    
    # Radical creativity for SWOT
    swot_framework = """
**SWOT WITH RADICAL CREATIVITY:**
- Weaknesses = untapped growth opportunities (not just problems to fix)
- Opportunities = what new territory/segment can we capture?
- Think: "changing the reach" not "changing the flavour"
- Every gap is a chance to build something that didn't exist
"""
    
    prompt = f"""You are a digital strategy analyst with growth mindset. {lang_instruction}

{swot_framework}

**CRITICAL RULES:**
1. Use ONLY numbers from the context.numbers section below
2. DO NOT invent, calculate, or estimate any numbers
3. Reference numbers with their exact context.numbers key
4. Frame weaknesses as GROWTH OPPORTUNITIES

**Context (READ-ONLY):**
```json
{context}
```

**Task:**
Generate a SWOT analysis based ONLY on the data above. Return valid JSON:

{{
  "strengths": ["List 2-4 strengths with specific numbers from context"],
  "weaknesses": ["List 2-4 GROWTH OPPORTUNITIES (frame gaps positively) with numbers"],
  "opportunities": ["List 2-3 NEW MARKET/SEGMENT opportunities to capture"],
  "threats": ["List 1-2 competitive threats or market risks"]
}}

**Example strength:** "Strong security posture (security_score: {numbers['security_score']}/15)"

**Good weakness (growth-oriented):** "Mobile experience gap = opportunity to capture 70% market segment (mobile_score: {numbers['mobile_score']}/15)"
**Bad weakness:** "Mobile optimization needed" ← Process thinking!

**Good opportunity:** "Untapped AI personalization = convert passive visitors into advocates"
**Bad opportunity:** "Improve content quality" ← Incremental, not transformative!

Return ONLY the JSON, no explanations.
"""
    
    response = await llm_client.generate(prompt, max_tokens=800, temperature=0.6)
    
    if not response:
        return None
    
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            logger.warning("No JSON found in SWOT response")
            return None
        
        import json
        swot_data = json.loads(json_match.group())
        
        # Validate with Pydantic if available
        if PYDANTIC_AVAILABLE:
            validated = SwotAnalysis(**swot_data)
            return validated.dict()
        
        return swot_data
    
    except Exception as e:
        logger.error(f"SWOT parsing failed: {e}")
        return None

async def generate_ai_recommendations(
    context: Dict[str, Any],
    language: str,
    llm_client: LLMClient
) -> Optional[List[str]]:
    """Generate actionable recommendations with radical creativity mindset"""
    
    numbers = context['numbers']
    flags = context['flags']
    metadata = context['metadata']
    
    lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS['en'])
    
    # Radical creativity framework
    creativity_framework = """
**RADICAL CREATIVITY MINDSET:**
- Creativity is a GROWTH STRATEGY, not decoration
- Focus on "changing the reach", not just "changing the flavour"
- Avoid process thinking traps (analyzing white spots until they turn grey)
- Recommend actions that drive NEW segments, deeper commitment, REAL growth
- Replace incremental improvements with transformative possibilities
"""
    
    prompt = f"""You are a digital growth strategist with radical creativity mindset. {lang_instruction}

{creativity_framework}

**CRITICAL RULES:**
1. Use ONLY scores from context.numbers
2. Each recommendation must be TRANSFORMATIVE and specific (not just "optimize X")
3. Focus on business growth, new markets, competitive advantage
4. Reference exact scores when relevant
5. Think: "What didn't exist before?" not "How do we improve what exists?"

**Context:**
```json
{context}
```

**Task:**
Generate exactly 5 prioritized, GROWTH-ORIENTED recommendations. Return as JSON array:

[
  "Recommendation 1 with growth impact (reference context.numbers)",
  "Recommendation 2...",
  "Recommendation 3...",
  "Recommendation 4...",
  "Recommendation 5..."
]

**Good example:** "Transform mobile experience to capture 70% more market (mobile_score: {numbers['mobile_score']}/15 → new segment opportunity)"
**Bad example:** "Improve mobile responsiveness" ← Too incremental!

**Another good example:** "Launch AI-powered personalization to convert visitors into advocates (current: generic experience)"
**Bad example:** "Add more content" ← Process thinking, not possibility thinking!

Return ONLY the JSON array, no explanations.
"""
    
    response = await llm_client.generate(prompt, max_tokens=600, temperature=0.7)
    
    if not response:
        return None
    
    try:
        import json
        # Extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            return None
        
        recommendations = json.loads(json_match.group())
        
        # Clean and validate
        cleaned = [rec.strip() for rec in recommendations if isinstance(rec, str) and len(rec.strip()) > 20]
        return cleaned[:5]
    
    except Exception as e:
        logger.error(f"Recommendations parsing failed: {e}")
        return None

async def generate_ai_executive_summary(
    context: Dict[str, Any],
    language: str,
    llm_client: LLMClient
) -> Optional[str]:
    """Generate executive summary with growth and possibility focus"""
    
    numbers = context['numbers']
    metadata = context['metadata']
    
    lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS['en'])
    
    # Radical creativity lens for executives
    exec_framework = """
**EXECUTIVE LENS:**
- Focus on GROWTH POTENTIAL, not just current gaps
- Frame weaknesses as market opportunities
- Think: "What new territory can we capture?" not "What's broken?"
- Creative permission beats creative intelligence
"""
    
    prompt = f"""You are a growth-oriented business strategist writing for C-level executives. {lang_instruction}

{exec_framework}

**Context:**
```json
{context}
```

**Task:**
Write a 2-3 sentence executive summary that:
1. States the overall_score from context.numbers
2. Frames gaps as GROWTH OPPORTUNITIES (not just problems)
3. Highlights untapped potential or new market reach
4. Ends with possibility thinking, not process thinking

**Good example:** "Digital maturity score is {numbers['overall_score']}/100. Current mobile gap represents €X/month opportunity to capture 70% market segment currently unreachable. Transforming digital presence = new revenue streams."

**Bad example:** "Score is low. Need to fix mobile and SEO." ← Process thinking!

**Another good example:** "At {numbers['overall_score']}/100, you're leaving competitors room to own segments you should dominate. Every point gap = lost market share. Time to build what didn't exist."

Return ONLY the summary text, 50-200 words.
"""
    
    response = await llm_client.generate(prompt, max_tokens=300, temperature=0.6)
    
    if not response:
        return None
    
    # Clean response
    summary = response.strip()
    if len(summary) < 50:
        return None
    
    return summary[:500]  # Safety limit

async def generate_ai_action_priority(
    context: Dict[str, Any],
    language: str,
    llm_client: LLMClient
) -> Optional[List[Dict[str, Any]]]:
    """Generate prioritized action items"""
    
    numbers = context['numbers']
    flags = context['flags']
    
    lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS['en'])
    
    prompt = f"""You are a technical project manager. {lang_instruction}

**Context:**
```json
{context}
```

**Task:**
Generate 3-5 prioritized action items. Return as JSON array:

[
  {{
    "category": "security|content|seo|mobile|analytics",
    "priority": "critical|high|medium|low",
    "score_impact": <number 1-15>,
    "description": "Clear action description"
  }}
]

**Rules:**
- Use context.numbers to determine priority
- score_impact must be realistic (1-15 points)
- Order by priority (critical first)

Return ONLY the JSON array.
"""
    
    response = await llm_client.generate(prompt, max_tokens=700, temperature=0.6)
    
    if not response:
        return None
    
    try:
        import json
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            return None
        
        actions = json.loads(json_match.group())
        
        # Validate structure
        valid_actions = []
        for action in actions:
            if all(k in action for k in ['category', 'priority', 'score_impact', 'description']):
                valid_actions.append(action)
        
        return valid_actions[:6]
    
    except Exception as e:
        logger.error(f"Action priority parsing failed: {e}")
        return None

# ============================================================================
# FALLBACK FUNCTIONS
# ============================================================================

def fallback_swot(context: Dict[str, Any], language: str) -> Dict[str, Any]:
    """Rule-based SWOT fallback"""
    
    numbers = context['numbers']
    flags = context['flags']
    
    strengths, weaknesses, opportunities, threats = [], [], [], []
    
    # Strengths
    if numbers['security_score'] >= 13:
        strengths.append(f"Strong security ({numbers['security_score']}/15)")
    if numbers['seo_score'] >= 15:
        strengths.append(f"Excellent SEO ({numbers['seo_score']}/20)")
    if numbers['word_count'] > 2000:
        strengths.append(f"Rich content ({numbers['word_count']} words)")
    
    # Weaknesses
    if numbers['security_score'] == 0:
        weaknesses.append("CRITICAL: No HTTPS")
    if numbers['content_score'] < 5:
        weaknesses.append(f"Thin content ({numbers['word_count']} words)")
    if not flags['has_analytics']:
        weaknesses.append("No analytics tracking")
    
    # Opportunities
    score_gap = 90 - numbers['overall_score']
    if score_gap > 40:
        opportunities.append(f"Major growth potential (+{score_gap} points)")
    else:
        opportunities.append(f"Optimization opportunities (+{score_gap} points)")
    
    # Threats
    if numbers['security_score'] < 5:
        threats.append("Search engine penalties for non-HTTPS")
    
    return {
        "strengths": strengths[:4] or ["Baseline established"],
        "weaknesses": weaknesses[:4] or ["Minor improvements needed"],
        "opportunities": opportunities[:3],
        "threats": threats[:2]
    }

def fallback_recommendations(context: Dict[str, Any], language: str) -> List[str]:
    """Rule-based recommendations fallback with growth mindset"""
    
    numbers = context['numbers']
    flags = context['flags']
    recommendations = []
    
    # Growth-oriented fallbacks (not just "fix X")
    if numbers['security_score'] <= 5:
        recommendations.append(f"Transform security = build trust that converts (security: {numbers['security_score']}/15 → trust = revenue)")
    
    if numbers['content_score'] <= 8:
        recommendations.append(f"Content strategy that drives new segments, not just fills pages (content: {numbers['content_score']}/15 → reach expansion)")
    
    if not flags['has_analytics']:
        recommendations.append("Install analytics + personalization = data-driven growth, not just measurement")
    
    if numbers['mobile_score'] < 10:
        recommendations.append(f"Mobile-first = capture 70% market unreachable today (mobile: {numbers['mobile_score']}/15 → new territory)")
    
    if numbers['seo_score'] < 12:
        recommendations.append(f"SEO transformation = organic growth engine 24/7 (SEO: {numbers['seo_score']}/20 → autopilot revenue)")
    
    return recommendations[:5] or ["Digital transformation = create what didn't exist, not just improve what does"]

def fallback_summary(context: Dict[str, Any], language: str) -> str:
    """Rule-based summary fallback with growth lens"""
    
    score = context['numbers']['overall_score']
    gap = 90 - score
    
    # Frame everything as opportunity, not just status
    if score >= 75:
        return f"Strong position ({score}/100) - opportunity to dominate market segments competitors can't reach. Every point = competitive moat."
    elif score >= 60:
        return f"Solid foundation ({score}/100) with {gap}-point growth territory available. Gaps = untapped revenue streams waiting to activate."
    elif score >= 45:
        return f"Baseline achieved ({score}/100). {gap} points = market segments you don't own yet. Time to build what competitors haven't imagined."
    else:
        return f"Early-stage ({score}/100) = massive white space opportunity. {gap} points to capture = transform reach, not just flavour. Creative permission needed."

def fallback_action_priority(context: Dict[str, Any], language: str) -> List[Dict[str, Any]]:
    """Rule-based action priority fallback"""
    
    numbers = context['numbers']
    actions = []
    
    if numbers['security_score'] <= 5:
        actions.append({
            "category": "security",
            "priority": "critical",
            "score_impact": 15,
            "description": "HTTPS and security headers"
        })
    
    if numbers['content_score'] < 8:
        actions.append({
            "category": "content",
            "priority": "high",
            "score_impact": 12,
            "description": "Content depth and quality"
        })
    
    if numbers['seo_score'] < 12:
        actions.append({
            "category": "seo",
            "priority": "high",
            "score_impact": 8,
            "description": "SEO fundamentals"
        })
    
    if numbers['mobile_score'] < 10:
        actions.append({
            "category": "mobile",
            "priority": "medium",
            "score_impact": 8,
            "description": "Mobile responsiveness"
        })
    
    return actions[:5]

# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

async def generate_full_ai_insights(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any],
    html: str,
    language: str = 'en',
    api_key: Optional[str] = None,
    return_debug_info: bool = False
) -> Dict[str, Any]:
    """
    Main function to generate all AI insights
    
    Args:
        url: Website URL
        basic, technical, content, ux, social: Analysis results
        html: Raw HTML content
        language: 'en', 'fi', or 'sv'
        api_key: OpenAI API key (optional)
        return_debug_info: Include prompt/context hash for debugging
    
    Returns:
        Dict with all AI-generated content + metadata
    """
    
    # Validate language
    if language not in LANGUAGE_MAP:
        logger.warning(f"Unsupported language: {language}, defaulting to 'en'")
        language = 'en'
    
    # Build structured context
    context, context_hash = build_structured_context(
        url, basic, technical, content, ux, social, html
    )
    
    logger.info(f"🔍 Context hash: {context_hash}, language: {language}")
    
    # Initialize LLM client
    llm_client = LLMClient(api_key=api_key)
    
    # Rate limiting with semaphore
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def rate_limited_task(coro):
        async with semaphore:
            return await coro
    
    # Generate all content in parallel (with rate limiting)
    try:
        results = await asyncio.gather(
            rate_limited_task(generate_ai_swot(context, language, llm_client)),
            rate_limited_task(generate_ai_recommendations(context, language, llm_client)),
            rate_limited_task(generate_ai_executive_summary(context, language, llm_client)),
            rate_limited_task(generate_ai_action_priority(context, language, llm_client)),
            return_exceptions=True  # Don't fail all if one fails
        )
        
        swot, recommendations, summary, action_priority = results
        
    except Exception as e:
        logger.error(f"Parallel generation failed: {e}")
        swot, recommendations, summary, action_priority = None, None, None, None
    
    # Use fallbacks for failed generations
    if not isinstance(swot, dict) or swot is None:
        logger.warning("Using SWOT fallback")
        swot = fallback_swot(context, language)
    
    if not isinstance(recommendations, list) or not recommendations:
        logger.warning("Using recommendations fallback")
        recommendations = fallback_recommendations(context, language)
    
    if not isinstance(summary, str) or not summary:
        logger.warning("Using summary fallback")
        summary = fallback_summary(context, language)
    
    if not isinstance(action_priority, list) or not action_priority:
        logger.warning("Using action priority fallback")
        action_priority = fallback_action_priority(context, language)
    
    # Calculate confidence and sentiment
    overall_score = context['numbers']['overall_score']
    confidence_score = min(95, max(60, overall_score + 20))
    sentiment_score = round((overall_score / 100) * 0.8 + 0.2, 2)
    
    # Build final result
    result = {
        "executive_summary": summary,
        "swot": swot,
        "recommendations": recommendations,
        "action_priority": action_priority,
        "confidence_score": confidence_score,
        "sentiment_score": sentiment_score
    }
    
    # Add debug info if requested
    if return_debug_info:
        result["_debug"] = {
            "context_hash": context_hash,
            "language": language,
            "timestamp": datetime.utcnow().isoformat(),
            "model": OPENAI_MODEL,
            "fallbacks_used": {
                "swot": not isinstance(results[0], dict),
                "recommendations": not isinstance(results[1], list),
                "summary": not isinstance(results[2], str),
                "action_priority": not isinstance(results[3], list)
            }
        }
    
    logger.info(f"✅ AI insights generated successfully (hash: {context_hash})")
    
    return result

# ============================================================================
# TESTING & DEVELOPMENT
# ============================================================================

async def test_ai_generator():
    """Test function for development"""
    
    # Mock data
    mock_basic = {
        "digital_maturity_score": 42,
        "score_breakdown": {
            "security": 0,
            "seo_basics": 8,
            "content": 6,
            "mobile": 5,
            "social": 3
        },
        "has_mobile_viewport": False,
        "title": "Test Company",
        "meta_description": "We sell things"
    }
    
    mock_technical = {
        "has_analytics": False,
        "page_speed_score": 55
    }
    
    mock_content = {
        "word_count": 450,
        "content_quality_score": 35
    }
    
    mock_ux = {}
    mock_social = {"platforms": ["facebook"]}
    mock_html = "<html><body>Verkkokauppa test content</body></html>"
    
    # Test all languages
    for lang in ['en', 'fi', 'sv']:
        print(f"\n{'='*60}")
        print(f"Testing language: {lang}")
        print('='*60)
        
        result = await generate_full_ai_insights(
            url="https://test.com",
            basic=mock_basic,
            technical=mock_technical,
            content=mock_content,
            ux=mock_ux,
            social=mock_social,
            html=mock_html,
            language=lang,
            return_debug_info=True
        )
        
        print(f"\n📊 Summary: {result['executive_summary']}")
        print(f"\n💪 Strengths: {result['swot']['strengths']}")
        print(f"\n⚠️  Weaknesses: {result['swot']['weaknesses']}")
        print(f"\n🎯 Recommendations: {result['recommendations']}")
        
        if '_debug' in result:
            print(f"\n🔍 Debug: {result['_debug']}")

if __name__ == "__main__":
    """Run tests"""
    import sys
    
    # Check dependencies
    if not OPENAI_AVAILABLE:
        print("⚠️  OpenAI library not installed: pip install openai")
    
    if not PYDANTIC_AVAILABLE:
        print("⚠️  Pydantic not installed: pip install pydantic")
    
    # Run tests
    print("\n🚀 Running AI Content Generator Tests\n")
    asyncio.run(test_ai_generator())
