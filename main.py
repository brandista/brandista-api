# ========== OSA 4/5 ALKAA: MAIN ENDPOINTS ========== #

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

        # Välimuistin voisi ottaa käyttöön halutessa:
        # cached = get_cached_analysis(url)
        # if cached:
        #     return SmartAnalyzeResponse(**cached)

        # 1) Nopea haku
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; BrandistaBot/1.0)'})
            response.raise_for_status()
            html_text = response.text

        soup = BeautifulSoup(html_text, 'html.parser')
        title_el = soup.find('title')
        meta_desc_el = soup.find('meta', {'name':'description'})
        h1_present = bool(soup.find('h1'))

        # 2) Heuristiikka → kokeile JS-renderiä lazyna
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
        content_data = analyze_content(soup, url)
        scores = score_and_recommend(head_sig, tech_cro, word_count)

        smart = {
            "meta": {"title": title or "Ei otsikkoa", "description": description or "Ei kuvausta", "canonical": head_sig['canonical']},
            "head_signals": head_sig,
            "tech_cro": tech_cro,
            "sitemap": sitemap_info,
            "content_analysis": content_data,
            "scores": scores["scores"],
            "top_findings": scores["top_findings"],
            "actions": scores["actions"],
            "flags": {"js_render_enabled": SMART_JS_RENDER, "cached": False}
        }

        result = SmartAnalyzeResponse(
            success=True,
            url=url,
            title=title or "Ei otsikkoa",
            description=description or "Ei kuvausta",
            score=scores["scores"]["total"],
            insights={"word_count": word_count},
            smart=smart
        )

        # save_to_cache(url, result.dict())
        return result

    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Virhe sivun haussa: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyysi epäonnistui: {str(e)}")

# ========== KORJATTU AI-ANALYZE ENDPOINT ========== #

@app.post("/api/v1/ai-analyze")
async def ai_analyze_compat(req: CompetitorAnalysisRequest):
    """
    Enhanced AI analysis endpoint with better error handling and debugging
    """
    try:
        target_url = req.url or req.website
        if not target_url:
            raise HTTPException(status_code=400, detail="url or website required")

        # 1) Run smart analysis first
        logger.info(f"Starting analysis for {target_url}")
        smart_resp = await analyze_competitor(AnalyzeRequest(url=target_url))
        result = smart_resp.dict()

        # 2) Prepare AI enhancement
        ai_full: Dict[str, Any] = {}
        ai_reco: List[Dict[str, Any]] = []

        if openai_client and req.use_ai:
            try:
                content_info = result["smart"].get("content_analysis", {})
                
                # Create comprehensive summary for AI
                summary = {
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "description": result.get("description"),
                    "scores": result["smart"]["scores"],
                    "top_findings": result["smart"]["top_findings"],
                    "actions": result["smart"]["actions"],
                    "tech_cro": result["smart"]["tech_cro"],
                    "head_signals": result["smart"]["head_signals"],
                    "sitemap": result["smart"]["sitemap"],
                    "content_summary": {
                        "headings": content_info.get("headings", {}),
                        "images": content_info.get("images", {}),
                        "links": content_info.get("links", {}),
                        "services_hints": content_info.get("services_hints", []),
                        "trust_signals": content_info.get("trust_signals", []),
                        "content_quality": content_info.get("content_quality", {}),
                        "text_preview": content_info.get("text_content", "")[:1000]
                    }
                }

                language = (req.language or 'fi').lower()
                
                # Enhanced prompts with explicit instructions
                if language == 'en':
                    system_msg = """You are a digital marketing and competitor analysis expert. 
                    You MUST provide concrete, specific insights based on the data provided.
                    Always return valid JSON with all required fields populated."""
                    
                    prompt = f"""Analyze this competitor website data and create a comprehensive JSON analysis.

WEBSITE DATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

You MUST create a JSON object with ALL of the following fields (no empty arrays):

{{
  "summary": "4-6 sentence description of the website's current state, digital presence, and main offerings based on the data",
  "strengths": [
    "At least 4-6 specific strengths based on the scores and technical data",
    "Example: Good SEO score of X/30",
    "Example: Has analytics tracking with Y pixels",
    "Example: Z contact channels available"
  ],
  "weaknesses": [
    "At least 4-6 specific weaknesses based on the findings",
    "Example: Missing canonical tags",
    "Example: Low content score",
    "Example: Few CTA elements"
  ],
  "opportunities": [
    "At least 4-5 improvement opportunities",
    "Example: Add more content to improve content score",
    "Example: Implement missing meta tags"
  ],
  "threats": [
    "At least 2-3 potential risks",
    "Example: Poor mobile optimization",
    "Example: Missing analytics tracking"
  ],
  "recommendations": [
    {{
      "title": "Specific action title",
      "description": "Detailed description",
      "priority": "high/medium/low",
      "timeline": "immediate/1-3 months/3-6 months"
    }}
  ],
  "competitor_profile": {{
    "target_audience": ["audience segment 1", "audience segment 2"],
    "strengths": ["key strength 1", "key strength 2"],
    "market_position": "Description of their market position"
  }}
}}

Base ALL insights on the actual data provided. Return ONLY valid JSON."""

                else:  # Finnish
                    system_msg = """Olet digitaalisen markkinoinnin ja kilpailija-analyysin asiantuntija.
                    SINUN TÄYTYY antaa konkreettisia, spesifisiä oivalluksia datan perusteella.
                    Palauta aina validi JSON kaikilla vaadituilla kentillä täytettyinä."""
                    
                    prompt = f"""Analysoi tämä kilpailijasivuston data ja luo kattava JSON-analyysi.

SIVUSTODATA:
{json.dumps(summary, ensure_ascii=False, indent=2)}

SINUN TÄYTYY luoda JSON-objekti, jossa on KAIKKI seuraavat kentät (ei tyhjiä taulukoita):

{{
  "yhteenveto": "4-6 lausetta sivuston nykytilasta, digitaalisesta läsnäolosta ja pääpalveluista datan perusteella",
  "vahvuudet": [
    "Vähintään 4-6 konkreettista vahvuutta pisteiden ja teknisen datan perusteella",
    "Esim: Hyvä SEO-pistemäärä X/30",
    "Esim: Analytiikka käytössä Y pikselillä",
    "Esim: Z yhteystietokanavaa"
  ],
  "heikkoudet": [
    "Vähintään 4-6 konkreettista heikkoutta löydösten perusteella",
    "Esim: Canonical-tagit puuttuvat",
    "Esim: Matala sisältöpistemäärä",
    "Esim: Vähän CTA-elementtejä"
  ],
  "mahdollisuudet": [
    "Vähintään 4-5 kehitysmahdollisuutta",
    "Esim: Lisää sisältöä parantaaksesi sisältöpisteitä",
    "Esim: Toteuta puuttuvat meta-tagit"
  ],
  "uhat": [
    "Vähintään 2-3 potentiaalista riskiä",
    "Esim: Heikko mobiilioptimointi",
    "Esim: Puuttuva analytiikkaseuranta"
  ],
  "toimenpidesuositukset": [
    {{
      "otsikko": "Konkreettinen toimenpiteen otsikko",
      "kuvaus": "Yksityiskohtainen kuvaus",
      "prioriteetti": "korkea/keskitaso/matala",
      "aikataulu": "heti/1-3kk/3-6kk"
    }}
  ],
  "kilpailijaprofiili": {{
    "kohderyhmat": ["kohderyhmä 1", "kohderyhmä 2"],
    "vahvuusalueet": ["keskeinen vahvuus 1", "keskeinen vahvuus 2"],
    "markkina_asema": "Kuvaus markkina-asemasta"
  }}
}}

Perusta KAIKKI oivallukset todelliseen dataan. Palauta VAIN validi JSON."""

                logger.info(f"Calling OpenAI API with model gpt-4o-mini")
                
                # Make the API call with explicit JSON mode
                resp = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    max_tokens=2000,
                )
                
                # Parse the response
                ai_response = resp.choices[0].message.content
                logger.info(f"OpenAI response received, length: {len(ai_response or '')}")
                
                if ai_response:
                    try:
                        parsed = json.loads(ai_response)
                        ai_full = parsed if isinstance(parsed, dict) else {}
                        
                        # Log what we got
                        logger.info(f"Parsed AI response keys: {list(ai_full.keys())}")
                        
                        # Extract recommendations
                        ai_reco = (
                            ai_full.get("toimenpidesuositukset")
                            or ai_full.get("recommendations")
                            or []
                        )
                        
                        # Validate that we got actual content
                        if language == 'fi':
                            if not ai_full.get("vahvuudet") or len(ai_full.get("vahvuudet", [])) == 0:
                                logger.warning("AI returned empty vahvuudet, using fallback")
                                ai_full = generate_fallback_swot(result, language)
                        else:
                            if not ai_full.get("strengths") or len(ai_full.get("strengths", [])) == 0:
                                logger.warning("AI returned empty strengths, using fallback")
                                ai_full = generate_fallback_swot(result, language)
                                
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse AI response: {e}")
                        ai_full = generate_fallback_swot(result, language)
                else:
                    logger.warning("Empty AI response, using fallback")
                    ai_full = generate_fallback_swot(result, language)
                    
            except Exception as e:
                logger.error(f"AI enhancement failed: {str(e)}")
                logger.exception(e)  # This will log the full traceback
                ai_full = generate_fallback_swot(result, req.language or 'fi')
                ai_reco = []
        else:
            logger.info("AI analysis disabled or OpenAI client not configured, using fallback")
            ai_full = generate_fallback_swot(result, req.language or 'fi')

        # 3) Build response with fallbacks for empty fields
        
        # Extract competitor profile
        kilpailijaprofiili = ai_full.get("kilpailijaprofiili") or ai_full.get("competitor_profile") or {}
        if isinstance(kilpailijaprofiili, dict):
            erottautumiskeinot = kilpailijaprofiili.get("vahvuusalueet", kilpailijaprofiili.get("strengths", []))
        else:
            erottautumiskeinot = []

        # Build quick wins list
        quick_wins_list = []
        if ai_reco or result["smart"]["actions"]:
            for a in (ai_reco or result["smart"]["actions"])[:3]:
                if isinstance(a, dict):
                    win = a.get("otsikko", a.get("title", ""))
                else:
                    win = str(a)
                if win:
                    quick_wins_list.append(win)

        # Ensure we have non-empty arrays
        response_data = {
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
                "yhteenveto": ai_full.get(
                    "yhteenveto",
                    ai_full.get(
                        "summary",
                        f"Sivusto {req.company_name} sai {result['smart']['scores']['total']}/100 pistettä digitaalisessa analyysissä. "
                        f"Sivustolla on {len(result['smart']['tech_cro'].get('analytics_pixels', []))} analytiikkatyökalua käytössä ja "
                        f"{result['smart']['tech_cro'].get('cta_count', 0)} CTA-elementtiä. "
                        f"Sisältöä on {result.get('insights', {}).get('word_count', 0)} sanaa."
                    )
                ),
                "vahvuudet": ai_full.get("vahvuudet", ai_full.get("strengths", [])) or generate_strengths(result),
                "heikkoudet": ai_full.get("heikkoudet", ai_full.get("weaknesses", [])) or generate_weaknesses(result),
                "mahdollisuudet": ai_full.get("mahdollisuudet", ai_full.get("opportunities", [])) or generate_opportunities(result),
                "uhat": ai_full.get("uhat", ai_full.get("threats", [])) or generate_threats(result),
                "toimenpidesuositukset": ai_reco or result["smart"]["actions"],
                "digitaalinen_jalanjalki": {
                    "arvio": result["smart"]["scores"]["total"] // 10,
                    "sosiaalinen_media": result["smart"]["tech_cro"]["analytics_pixels"],
                    "sisaltostrategia": "Aktiivinen" if len(result["smart"].get("content_analysis", {}).get("services_hints", [])) > 2 else "Kehitettävä"
                },
                "erottautumiskeinot": erottautumiskeinot or ["Tekninen toteutus", "Sisältöstrategia", "Käyttäjäkokemus"],
                "quick_wins": quick_wins_list or ["Lisää meta-tagit", "Paranna CTA-elementtejä", "Asenna analytiikka"]
            },
            "smart": result["smart"]
        }

        logger.info(f"Response prepared successfully for {req.company_name}")
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI analyze failed completely: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI analyze failed: {str(e)}")

# ========== OSA 4/5 LOPPUU ========== ## ========== OSA 5/5 ALKAA: MUUT ENDPOINTIT, RATE LIMITING, PDF & ERROR HANDLING ========== #

@app.get("/api/v1/test-openai")
async def test_openai():
    """Test OpenAI API connection"""
    if not openai_client:
        return {
            "status": "error",
            "message": "OpenAI client not configured",
            "api_key_set": bool(os.getenv("OPENAI_API_KEY")),
            "client_exists": False
        }

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a test bot."},
                {"role": "user", "content": "Reply with just 'OK' if you work."}
            ],
            max_tokens=10
        )
        return {
            "status": "success",
            "message": "OpenAI API works!",
            "response": response.choices[0].message.content,
            "model": "gpt-4o-mini"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"OpenAI API error: {str(e)}",
            "error_type": type(e).__name__
        }

@app.post("/api/v1/batch-analyze")
async def batch_analyze_competitors(urls: List[str]):
    """Analysoi useita kilpailijoita kerralla"""
    results = []
    for url in urls[:10]:  # Max 10 kerralla
        try:
            result = await analyze_competitor(AnalyzeRequest(url=url))
            results.append(result.dict())
        except Exception as e:
            results.append({"success": False, "url": url, "error": str(e)})

    successful = [r for r in results if r.get('success')]
    avg_score = sum(r.get('score', 0) for r in successful) / len(successful) if successful else 0

    return {
        "success": True,
        "analyzed_count": len(results),
        "successful_count": len(successful),
        "average_score": round(avg_score, 1),
        "results": results,
        "summary": {
            "best_performer": max(successful, key=lambda x: x.get('score', 0)) if successful else None,
            "common_weaknesses": _find_common_patterns([r['smart']['top_findings'] for r in successful if 'smart' in r]),
            "tech_stack_distribution": _analyze_tech_distribution(successful)
        }
    }

def _find_common_patterns(findings_lists):
    """Tunnista yleisimmät löydökset"""
    all_findings = []
    for findings in findings_lists:
        all_findings.extend(findings)

    patterns = {}
    keywords = ['canonical', 'CTA', 'analytiikka', 'sisältö', 'OG-meta']
    for keyword in keywords:
        count = sum(1 for f in all_findings if keyword.lower() in f.lower())
        if count > 0:
            patterns[keyword] = count
    return patterns

def _analyze_tech_distribution(results):
    """Analysoi teknologiajakauma"""
    tech_dist = {'cms': {}, 'frameworks': {}, 'analytics': {}}
    for r in results:
        if 'smart' in r and 'tech_cro' in r['smart']:
            tech = r['smart']['tech_cro']
            cms = tech.get('cms')
            if cms:
                tech_dist['cms'][cms] = tech_dist['cms'].get(cms, 0) + 1
            fw = tech.get('framework')
            if fw:
                tech_dist['frameworks'][fw] = tech_dist['frameworks'].get(fw, 0) + 1
            for pixel in tech.get('analytics_pixels', []):
                tech_dist['analytics'][pixel] = tech_dist['analytics'].get(pixel, 0) + 1
    return tech_dist

@app.get("/api/v1/compare/{url1}/{url2}")
async def compare_competitors(url1: str, url2: str):
    """Vertaa kahta kilpailijaa keskenään"""
    try:
        result1 = await analyze_competitor(AnalyzeRequest(url=url1))
        result2 = await analyze_competitor(AnalyzeRequest(url=url2))
        r1 = result1.dict()
        r2 = result2.dict()

        comparison = {
            "competitor1": {"url": url1, "score": r1['score'], "title": r1['title']},
            "competitor2": {"url": url2, "score": r2['score'], "title": r2['title']},
            "winner": url1 if r1['score'] > r2['score'] else url2,
            "score_difference": abs(r1['score'] - r2['score']),
            "detailed_comparison": {
                "seo": {"competitor1": r1['smart']['scores']['seo'], "competitor2": r2['smart']['scores']['seo'],
                        "winner": 1 if r1['smart']['scores']['seo'] > r2['smart']['scores']['seo'] else 2},
                "content": {"competitor1": r1['smart']['scores']['content'], "competitor2": r2['smart']['scores']['content'],
                            "winner": 1 if r1['smart']['scores']['content'] > r2['smart']['scores']['content'] else 2},
                "cro": {"competitor1": r1['smart']['scores']['cro'], "competitor2": r2['smart']['scores']['cro'],
                        "winner": 1 if r1['smart']['scores']['cro'] > r2['smart']['scores']['cro'] else 2},
                "tech": {"competitor1": r1['smart']['scores']['tech'], "competitor2": r2['smart']['scores']['tech'],
                         "winner": 1 if r1['smart']['scores']['tech'] > r2['smart']['scores']['tech'] else 2}
            },
            "tech_comparison": {
                "competitor1": {"cms": r1['smart']['tech_cro'].get('cms'),
                                "framework": r1['smart']['tech_cro'].get('framework'),
                                "analytics": r1['smart']['tech_cro'].get('analytics_pixels', [])},
                "competitor2": {"cms": r2['smart']['tech_cro'].get('cms'),
                                "framework": r2['smart']['tech_cro'].get('framework'),
                                "analytics": r2['smart']['tech_cro'].get('analytics_pixels', [])}
            },
            "recommendations": {
                "for_weaker": _generate_improvement_tips(
                    r1 if r1['score'] < r2['score'] else r2,
                    r2 if r1['score'] < r2['score'] else r1
                )
            }
        }
        return comparison

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vertailu epäonnistui: {str(e)}")

def _generate_improvement_tips(weaker, stronger):
    """Generoi parannusehdotuksia heikommalle"""
    tips = []
    for category in ['seo', 'content', 'cro', 'tech']:
        if weaker['smart']['scores'][category] < stronger['smart']['scores'][category]:
            if category == 'seo':
                tips.append(f"Paranna SEO:ta - kilpailijalla {stronger['smart']['scores'][category]} pistettä vs sinun {weaker['smart']['scores'][category]}")
            elif category == 'content':
                tips.append(f"Lisää sisältöä - kilpailijalla parempi sisältöpisteet")
            elif category == 'cro':
                tips.append(f"Paranna konversiota - lisää CTA-elementtejä")
            elif category == 'tech':
                tips.append(f"Päivitä analytiikka - kilpailijalla parempi seuranta")
    if stronger['smart']['tech_cro'].get('analytics_pixels') and not weaker['smart']['tech_cro'].get('analytics_pixels'):
        tips.append("Asenna analytiikkapikselit (GA4, Meta Pixel)")
    return tips[:5]

@app.get("/api/v1/docs")
def api_documentation():
    """API-dokumentaatio"""
    return {
        "version": APP_VERSION,
        "endpoints": {
            "/api/v1/analyze": {"method": "POST", "description": "Analysoi yksittäinen kilpailijan sivusto", "body": {"url": "string"}, "response": "SmartAnalyzeResponse"},
            "/api/v1/ai-analyze": {"method": "POST", "description": "Analysoi AI-rikastuksella (vaatii OPENAI_API_KEY)", "body": {"company_name": "string","url": "string","industry": "string (optional)","use_ai": "boolean (default: true)"}},
            "/api/v1/batch-analyze": {"method": "POST", "description": "Analysoi max 10 URL:ia kerralla", "body": ["url1", "url2", "..."], "response": "Batch analysis with summary"},
            "/api/v1/compare/{url1}/{url2}": {"method": "GET", "description": "Vertaa kahta kilpailijaa", "params": "url1 ja url2 pathissa", "response": "Comparison report"},
            "/api/v1/generate-pdf": {"method": "POST", "description": "Luo PDF-raportti analyysista", "body": "analysis_data object", "response": "PDF file stream"},
            "/api/v1/generate-pdf-base64": {"method": "POST", "description": "Luo PDF base64-muodossa", "body": "analysis_data + language", "response": {"pdf_base64": "string", "filename": "string"}},
            "/api/v1/test-openai": {"method": "GET", "description": "Testaa OpenAI-yhteys", "response": "Connection status"},
            "/health": {"method": "GET", "description": "Tarkista API:n tila", "response": "Health status"}
        },
        "features": {
            "smart_analysis": "Automaattinen SEO, CRO ja teknologia-analyysi",
            "ai_enrichment": "GPT-4 pohjainen SWOT ja suositukset",
            "caching": "24h välimuisti analyyseille",
            "js_rendering": "JavaScript-sivujen tuki (jos SMART_JS_RENDER=1)",
            "pdf_generation": "Automaattinen PDF-raportointi",
            "batch_processing": "Usean kilpailijan analyysi kerralla",
            "comparison": "Kilpailijavertailu"
        },
        "environment_variables": {
            "OPENAI_API_KEY": "OpenAI API avain (valinnainen)",
            "SMART_JS_RENDER": "JavaScript rendering on/off (default: 1)"
        },
        "rate_limits": {
            "analyze": "100 requests/hour per IP",
            "batch": "10 requests/hour per IP",
            "ai_analyze": "50 requests/hour per IP"
        }
    }

# ---------- Rate limiting ----------
request_counts: Dict[str, List[datetime]] = defaultdict(list)

def check_rate_limit(ip: str, limit: int = 100) -> bool:
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    request_counts[ip] = [t for t in request_counts[ip] if t > hour_ago]
    if len(request_counts[ip]) >= limit:
        return False
    request_counts[ip].append(now)
    return True

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    ip = request.headers.get("X-Forwarded-For", request.client.host) if request.client else "unknown"
    if request.url.path.startswith("/api/v1/"):
        limits = {
            "/api/v1/batch-analyze": 10,
            "/api/v1/ai-analyze": 50,
            "/api/v1/analyze": 100
        }
        limit = next((v for k, v in limits.items() if request.url.path.startswith(k)), 100)
        if not check_rate_limit(ip, limit):
            return JSONResponse(status_code=429, content={"detail": f"Rate limit exceeded. Max {limit} requests/hour"})
    return await call_next(request)

# ---------- Global error handler ----------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    error_id = hashlib.md5(f"{datetime.now()}{str(exc)}".encode()).hexdigest()[:8]
    print(f"ERROR {error_id}: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Sisäinen virhe",
            "error_id": error_id,
            "message": "Jotain meni pieleen. Ota yhteyttä tukeen virhekoodilla."
        }
    )

# ========== PDF GENERATION (stream) ==========
@app.post("/api/v1/generate-pdf")
async def generate_pdf_report(analysis_data: Dict[str, Any]):
    """Generoi PDF-raportti AI-analyysista (stream)"""
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
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
                for v in ai_analysis['vahvuudet']:
                    story.append(Paragraph(f"• {v}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('heikkoudet'):
                story.append(Paragraph("Heikkoudet", subheading_style))
                for w in ai_analysis['heikkoudet']:
                    story.append(Paragraph(f"• {w}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('mahdollisuudet'):
                story.append(Paragraph("Mahdollisuudet", subheading_style))
                for o in ai_analysis['mahdollisuudet']:
                    story.append(Paragraph(f"• {o}", normal_style))
                story.append(Spacer(1, 10))
            if ai_analysis.get('uhat'):
                story.append(Paragraph("Uhat", subheading_style))
                for t in ai_analysis['uhat']:
                    story.append(Paragraph(f"• {t}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('digitaalinen_jalanjalki'):
                story.append(Paragraph("Digitaalinen jalanjälki", heading_style))
                digi = ai_analysis['digitaalinen_jalanjalki']
                if digi.get('arvio'):
                    story.append(Paragraph(f"<b>Arvio:</b> {digi['arvio']}/10", normal_style))
                if digi.get('sosiaalinen_media'):
                    story.append(Paragraph("<b>Aktiiviset kanavat:</b>", normal_style))
                    for ch in digi['sosiaalinen_media']:
                        story.append(Paragraph(f"• {ch}", normal_style))
                if digi.get('sisaltostrategia'):
                    story.append(Paragraph(f"<b>Sisältöstrategia:</b> {digi['sisaltostrategia']}", normal_style))
                story.append(Spacer(1, 20))

            # Toimenpiteet
            if ai_analysis.get('toimenpidesuositukset'):
                story.append(PageBreak())
                story.append(Paragraph("Toimenpidesuositukset", heading_style))
                for idx, rec in enumerate(ai_analysis['toimenpidesuositukset'], 1):
                    title = rec.get('otsikko', f'Toimenpide {idx}') if isinstance(rec, dict) else f'Toimenpide {idx}'
                    story.append(Paragraph(f"{idx}. {title}", subheading_style))
                    if isinstance(rec, dict):
                        if rec.get('kuvaus'):
                            story.append(Paragraph(rec['kuvaus'], normal_style))
                        details = []
                        if rec.get('prioriteetti'):
                            p = rec['prioriteetti']
                            color = '#dc2626' if p == 'korkea' else '#f59e0b' if p == 'keskitaso' else '#10b981'
                            details.append(f"<font color='{color}'><b>Prioriteetti:</b> {p}</font>")
                        if rec.get('aikataulu'):
                            details.append(f"<b>Aikataulu:</b> {rec['aikataulu']}")
                        if details:
                            story.append(Paragraph(" | ".join(details), normal_style))
                    story.append(Spacer(1, 15))

            # Erottautumiskeinot
            methods = ai_analysis.get('erottautumiskeinot', [])
            if methods:
                story.append(Paragraph("Erottautumiskeinot", heading_style))
                if isinstance(methods, str):
                    items = [m.strip() for m in methods.split(',')] if ',' in methods else [methods]
                else:
                    items = methods
                for m in items:
                    story.append(Paragraph(f"• {m}", normal_style))
                story.append(Spacer(1, 20))

            if ai_analysis.get('quick_wins'):
                story.append(Paragraph("Nopeat voitot", heading_style))
                for win in ai_analysis.get('quick_wins', []):
                    story.append(Paragraph(f"✓ {win}", normal_style))

        doc.build(story)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=kilpailija_analyysi_{(company_name or 'raportti').replace(' ','_')}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF-generointi epäonnistui: {str(e)}")

# ========== PDF GENERATION (base64) - TÄMÄ JATKUU SEURAAVASSA VIESTISSÄ ========== #
# [HUOM: PDF base64 funktio jatkuu, mutta Discord-rajoitusten takia jatketaan seuraavassa viestissä]

# ========== OSA 5/5 PÄÄTTYY (OSITTAIN - JATKUU) ========== ## ========== OSA 5B/5 ALKAA: PDF BASE64 GENERATION (VIIMEINEN PUUTTUVA PALA) ========== #

@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti base64-muodossa (fi/en).
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
                    for it in items:
                        story.append(Paragraph(f"• {it}", normal_style))
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
                        if tl:
                            details.append(f"<b>{t['timeline']}:</b> {tl}")
                        if details:
                            story.append(Paragraph(" | ".join(details), normal_style))
                    else:
                        story.append(Paragraph(f"{idx}. {rec}", normal_style))
                    story.append(Spacer(1, 15))

        methods = ai_analysis.get('erottautumiskeinot', ai_analysis.get('differentiation', []))
        if methods:
            story.append(Paragraph(t['differentiation'], heading_style))
            for m in (methods if isinstance(methods, list) else [methods]):
                story.append(Paragraph(f"• {m}", normal_style))
            story.append(Spacer(1, 20))

        if ai_analysis.get('quick_wins'):
            story.append(Paragraph(t['quick_wins'], heading_style))
            for win in ai_analysis.get('quick_wins', []):
                story.append(Paragraph(f"✓ {win}", normal_style))

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

# ========== OSA 5B/5 LOPPUU - KOKO MAIN.PY VALMIS! ========== #
