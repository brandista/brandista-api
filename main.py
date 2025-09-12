async def analyze_social_media_presence(url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'html.parser')
    score = 0; platforms = []
    weights = {'facebook':15,'instagram':15,'linkedin':12,'youtube':12,'twitter/x':10,'tiktok':10,'pinterest':5,'snapchat':3}
    patterns = {
        'facebook': r'facebook\.com/[^/\s"\']+',
        'instagram': r'instagram\.com/[^/\s"\']+',
        'linkedin': r'linkedin\.com/(company|in)/[^/\s"\']+',
        'youtube': r'youtube\.com/(@|channel|user|c)[^/\s"\']+',
        'twitter/x': r'(twitter\.com|x\.com)/[^/\s"\']+',
        'tiktok': r'tiktok\.com/@[^/\s"\']+',
        'pinterest': r'pinterest\.(\w+)/[^/\s"\']+',
        'snapchat': r'snapchat\.com/add/[^/\s"\']+'
    }
    for platform, pat in patterns.items():
        if re.search(pat, html, re.I):
            platforms.append(platform); score += weights.get(platform, 5)
    has_sharing = any(p in html.lower() for p in ['addtoany','sharethis','addthis','social-share'])
    if has_sharing: score += 15
    og_count = len(soup.find_all('meta', property=re.compile('^og:')))
    if og_count >= 4: score += 10
    elif og_count >= 2: score += 5
    twitter_cards = bool(soup.find_all('meta', attrs={'name': re.compile('^twitter:')}))
    if twitter_cards: score += 5
    return {
        'platforms': platforms,
        'total_followers': 0,
        'engagement_rate': 0.0,
        'posting_frequency': "unknown",
        'social_score': min(100, score),
        'has_sharing_buttons': has_sharing,
        'open_graph_tags': og_count,
        'twitter_cards': twitter_cards
    }

async def analyze_competitive_positioning(url: str, basic: Dict[str, Any]) -> Dict[str, Any]:
    score = basic.get('digital_maturity_score', 0)
    if score >= 75:
        position = "Digital Leader"
        advantages = ["Excellent digital presence", "Advanced technical execution", "Competitive user experience"]
        threats = ["Fast-followers copying features", "Pressure to innovate continuously"]
        comp_score = 85
    elif score >= 60:
        position = "Strong Performer"
        advantages = ["Solid digital foundation", "Good growth potential"]
        threats = ["Gap to market leaders", "Need for ongoing improvements"]
        comp_score = 70
    elif score >= 45:
        position = "Average Competitor"
        advantages = ["Baseline established", "Clear areas to improve"]
        threats = ["At risk of falling behind", "Increasing competitive pressure"]
        comp_score = 50
    elif score >= 30:
        position = "Below Average"
        advantages = ["Significant upside potential"]
        threats = ["Clear competitive disadvantage", "Risk of losing customers"]
        comp_score = 30
    else:
        position = "Digital Laggard"
        advantages = ["Opportunity for a major leap"]
        threats = ["Critical competitive handicap", "Threat to business continuity"]
        comp_score = 15

    return {
        'market_position': position,
        'competitive_advantages': advantages,
        'competitive_threats': threats,
        'market_share_estimate': "Data not available",
        'competitive_score': comp_score,
        'industry_comparison': {
            'your_score': score,
            'industry_average': 45,
            'top_quartile': 70,
            'bottom_quartile': 30
        }
    }

# ============================================================================
# ENHANCED FEATURES
# ============================================================================

def detect_technology_stack(html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    detected = []
    hl = html.lower()
    # CMS
    cms_patterns = {
        'WordPress': ['wp-content','wp-includes','wordpress'],
        'Joomla': ['joomla','/components/','/modules/'],
        'Drupal': ['drupal','/sites/all/','drupal.settings'],
        'Shopify': ['shopify','myshopify.com','cdn.shopify'],
        'Wix': ['wix.com','static.wixstatic.com'],
        'Squarespace': ['squarespace','sqsp.net'],
        'Webflow': ['webflow.io','webflow.com'],
        'Ghost': ['ghost.io','ghost-themes']
    }
    for cms, pats in cms_patterns.items():
        if any(p in hl for p in pats):
            detected.append(f"CMS: {cms}")
            break
    # Frameworks
    frameworks = {
        'React': ['react', '_react', 'reactdom'],
        'Angular': ['ng-','angular','__zone_symbol__'],
        'Vue.js': ['vue','v-for','v-if','v-model'],
        'Next.js': ['_next','nextjs','__next_data__'],
        'Gatsby': ['gatsby','___gatsby'],
        'Nuxt.js': ['__nuxt','_nuxt'],
        'Django': ['csrfmiddlewaretoken','django'],
        'Laravel': ['laravel','livewire'],
        'Ruby on Rails': ['rails','csrf-token','action_controller']
    }
    for fw, pats in frameworks.items():
        if any(p in hl for p in pats): detected.append(f"Framework: {fw}")
    # Analytics
    if 'google-analytics' in hl or 'gtag' in hl: detected.append("Analytics: Google Analytics")
    if 'googletagmanager' in hl: detected.append("Analytics: Google Tag Manager")
    if 'matomo' in hl or 'piwik' in hl: detected.append("Analytics: Matomo")
    if 'hotjar' in hl: detected.append("Analytics: Hotjar")
    if 'clarity.ms' in hl: detected.append("Analytics: Microsoft Clarity")
    # CDN/Hosting
    if 'cloudflare' in hl: detected.append("CDN: Cloudflare")
    if 'akamai' in hl: detected.append("CDN: Akamai")
    if 'fastly' in hl: detected.append("CDN: Fastly")
    if 'amazonaws' in hl: detected.append("Hosting: AWS")
    if 'azurewebsites' in hl: detected.append("Hosting: Azure")
    # E-comm
    if 'woocommerce' in hl: detected.append("E-commerce: WooCommerce")
    if 'shopify' in hl: detected.append("E-commerce: Shopify")
    if 'magento' in hl: detected.append("E-commerce: Magento")
    # CSS
    if 'bootstrap' in hl: detected.append("CSS: Bootstrap")
    if 'tailwind' in hl: detected.append("CSS: Tailwind")
    if 'bulma' in hl: detected.append("CSS: Bulma")
    if 'material' in hl: detected.append("CSS: Material Design")
    # JS libs
    if 'jquery' in hl: detected.append("JS: jQuery")
    if 'lodash' in hl: detected.append("JS: Lodash")
    if 'axios' in hl: detected.append("JS: Axios")

    return {
        "detected": detected,
        "count": len(detected),
        "categories": {
            "cms": [t.split(": ")[1] for t in detected if t.startswith("CMS:")],
            "frameworks": [t.split(": ")[1] for t in detected if t.startswith("Framework:")],
            "analytics": [t.split(": ")[1] for t in detected if t.startswith("Analytics:")],
            "cdn": [t.split(": ")[1] for t in detected if t.startswith("CDN:")],
            "ecommerce": [t.split(": ")[1] for t in detected if t.startswith("E-commerce:")]
        }
    }

def assess_mobile_first_readiness(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    score = 0; issues = []; recs = []
    vp = soup.find('meta', attrs={'name':'viewport'})
    if vp:
        vc = vp.get('content','')
        if 'width=device-width' in vc: score += 30
        else: issues.append("Viewport not properly configured"); recs.append("Add proper viewport meta tag")
    else:
        issues.append("No viewport meta tag"); recs.append("Add viewport meta tag with width=device-width")

    hl = html.lower()
    if '@media' in hl:
        c = hl.count('@media')
        if c >= 5: score += 25
        elif c >= 2: score += 15
        else: issues.append("Limited responsive CSS"); recs.append("Add additional responsive breakpoints")
    else:
        issues.append("No responsive media queries"); recs.append("Implement responsive design with media queries")

    if 'font-size' in hl:
        if 'rem' in hl or 'em' in hl: score += 15
        else: issues.append("Fixed font sizes used"); recs.append("Use relative font sizes (rem/em)")
    if 'touch' in hl or 'tap' in hl: score += 10
    if soup.find('meta', attrs={'name':'apple-mobile-web-app-capable'}): score += 10
    if 'flash' in hl: score -= 20; issues.append("Uses Flash"); recs.append("Remove Flash content")

    imgs = soup.find_all('img')
    if imgs:
        lazy = [i for i in imgs if i.get('loading') == 'lazy']
        if lazy: score += 10
        else: recs.append("Implement lazy loading for images")

    ready = score >= 60
    return {
        "ready": ready,
        "score": score,
        "status": "Ready" if ready else "Not Ready",
        "issues": issues if not ready else [],
        "recommendations": [r for r in recs if r]
    }

def estimate_core_web_vitals(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    size = len(html); imgs = soup.find_all('img'); scripts = soup.find_all('script')
    recs = []
    lcp = 2.0
    if size > 500000: lcp += 2.0
    elif size > 200000: lcp += 1.0
    elif size > 100000: lcp += 0.5
    if len(imgs) > 20: lcp += 1.0
    elif len(imgs) > 10: lcp += 0.5
    if [i for i in imgs if i.get('loading') == 'lazy']: lcp -= 0.5

    fid = 50
    if len(scripts) > 20: fid += 100
    elif len(scripts) > 10: fid += 50
    elif len(scripts) > 5: fid += 25
    if [s for s in scripts if s.get('async') or s.get('defer')]: fid -= 25

    cls = 0.05
    imgs_no_dims = [i for i in imgs if not (i.get('width') and i.get('height'))]
    if len(imgs_no_dims) > 5: cls += 0.15
    elif len(imgs_no_dims) > 2: cls += 0.10
    elif imgs_no_dims: cls += 0.05
    if 'font-face' in html.lower(): cls += 0.05

    lcp_status = "Good" if lcp <= 2.5 else "Needs Improvement" if lcp <= 4.0 else "Poor"
    fid_status = "Good" if fid <= 100 else "Needs Improvement" if fid <= 300 else "Poor"
    cls_status = "Good" if cls <= 0.1 else "Needs Improvement" if cls <= 0.25 else "Poor"

    if lcp_status != "Good": recs.append("Optimize images with lazy loading and proper sizing")
    if fid_status != "Good": recs.append("Reduce JavaScript execution time and split bundles")
    if cls_status != "Good": recs.append("Add explicit width/height to images and embeds; avoid FOIT")

    overall = "Pass"
    if "Poor" in (lcp_status, fid_status, cls_status): overall = "Fail"
    elif "Needs Improvement" in (lcp_status, fid_status, cls_status): overall = "Needs Improvement"

    return {
        "lcp": {"value": f"{lcp:.1f}s", "status": lcp_status, "threshold": "≤2.5s Good, ≤4.0s Needs Improvement"},
        "fid": {"value": f"{fid}ms", "status": fid_status, "threshold": "≤100ms Good, ≤300ms Needs Improvement"},
        "cls": {"value": f"{cls:.2f}", "status": cls_status, "threshold": "≤0.1 Good, ≤0.25 Needs Improvement"},
        "overall_status": overall,
        "recommendations": recs
    }

def estimate_traffic_rank(url: str, basic: Dict[str, Any]) -> str:
    s = basic.get('digital_maturity_score', 0)
    if s >= 75: return "Top 10% in industry (High traffic potential)"
    if s >= 60: return "Top 25% in industry (Good traffic potential)"
    if s >= 45: return "Average (Moderate traffic)"
    if s >= 30: return "Below average (Limited traffic)"
    return "Low visibility (Minimal traffic)"

def generate_competitor_gaps(basic: Dict[str, Any], competitive: Dict[str, Any]) -> List[str]:
    s = basic.get('digital_maturity_score', 0)
    if s < 30:
        return ["Very weak digital presence vs. peers", "Foundational optimizations missing", "High risk of customer loss to modern competitors"]
    if s < 50:
        return ["Content strategy lags behind peers", "Technical implementation below average", "UX not competitive"]
    if s < 70:
        return ["Gap to top performers remains", "Potential to catch up with focused investments", "Conversion optimization required"]
    return ["Competitive vs. most peers", "Focus on innovation to differentiate", "Maintain lead with continuous improvement"]

# ============================================================================
# AI INSIGHTS (EN-only)
# ============================================================================

async def generate_ai_insights(
    url: str,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any],
) -> AIAnalysis:
    overall = basic.get('digital_maturity_score', 0)
    insights = generate_english_insights(overall, basic, technical, content, ux, social)

    if openai_client:
        try:
            ctx = f"""
            Website: {url}
            Score: {overall}/100
            Technical: {technical.get('overall_technical_score', 0)}/100
            Content words: {content.get('word_count', 0)}
            Social: {social.get('social_score', 0)}/100
            UX: {ux.get('overall_ux_score', 0)}/100
            """
            prompt = (
                "Given the following website audit context, provide exactly 5 concise, high-impact, "
                "actionable recommendations. Each recommendation must be ONE sentence, imperative voice, "
                "and cover different areas (technical, content, SEO, UX, social/conversion). "
                "Return them as a plain list, one per line, prefixed with a hyphen, with no intro/outro text:\n"
                f"{ctx}"
            )

            resp = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.6
            )

            raw = resp.choices[0].message.content.strip()

            # Parse into clean 5-item list
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            cleaned = []
            for ln in lines:
                ln = re.sub(r'^\s*[-•\d]+\s*[.)-]?\s*', '', ln).strip()
                if len(ln.split()) >= 4:
                    cleaned.append(ln)
            recs = cleaned[:5]

            if recs:
                base = (insights.get('recommendations') or [])[:2]
                insights['recommendations'] = base + recs
        except Exception as e:
            logger.warning(f"OpenAI enhancement failed: {e}")

    return AIAnalysis(**insights)

def generate_english_insights(
    overall: int,
    basic: Dict[str, Any],
    technical: Dict[str, Any],
    content: Dict[str, Any],
    ux: Dict[str, Any],
    social: Dict[str, Any]
) -> Dict[str, Any]:
    strengths, weaknesses, opportunities, threats, recs, quick_wins = [], [], [], [], [], []
    breakdown = basic.get('score_breakdown', {})
    wc = content.get('word_count', 0)

    # Strengths
    if breakdown.get('security', 0) >= 13:
        strengths.append(f"Strong security posture ({breakdown['security']}/15) — HTTPS and key headers present.")
    elif breakdown.get('security', 0) >= 10:
        strengths.append(f"Good security ({breakdown['security']}/15) — HTTPS enabled.")
    if breakdown.get('seo_basics', 0) >= 15:
        strengths.append(f"Excellent SEO fundamentals ({breakdown['seo_basics']}/20).")
    elif breakdown.get('seo_basics', 0) >= 10:
        strengths.append(f"Solid SEO foundation ({breakdown['seo_basics']}/20).")
    if breakdown.get('mobile', 0) >= 12:
        strengths.append(f"Great mobile optimization ({breakdown['mobile']}/15).")
    elif breakdown.get('mobile', 0) >= 8:
        strengths.append(f"Good mobile UX ({breakdown['mobile']}/15).")
    if wc > 2000:
        strengths.append(f"Very comprehensive content ({wc} words).")
    elif wc > 1000:
        strengths.append(f"Adequate content volume ({wc} words).")
    if social.get('platforms'):
        strengths.append(f"Presence on {len(social['platforms'])} social platforms.")

    # Weaknesses & quick wins
    if breakdown.get('security', 0) == 0:
        weaknesses.append("CRITICAL: No SSL — site not secured.")
        threats.append("Search engines and browsers penalize non-HTTPS sites.")
        quick_wins.append("Install an SSL certificate immediately (Let's Encrypt).")
    elif breakdown.get('security', 0) < 10:
        weaknesses.append(f"Security can be improved ({breakdown['security']}/15).")

    if breakdown.get('content', 0) < 5:
        weaknesses.append(f"Very low content depth ({breakdown['content']}/20, {wc} words).")
        recs.append("Create an editorial calendar and expand core landing pages.")
    elif breakdown.get('content', 0) < 10:
        weaknesses.append(f"Content requires expansion ({breakdown['content']}/20).")

    if breakdown.get('social', 0) < 5:
        weaknesses.append(f"Weak social presence ({breakdown['social']}/10).")
        recs.append("Set up company pages on LinkedIn and Facebook at minimum.")

    if not technical.get('has_analytics'):
        weaknesses.append("Analytics missing — no data-driven decision-making.")
        quick_wins.append("Install Google Analytics 4 (free, ~30 minutes).")

    if breakdown.get('performance', 0) < 3:
        weaknesses.append(f"Performance needs work ({breakdown['performance']}/5).")
        quick_wins.append("Enable lazy loading for images and use modern formats (WebP/AVIF).")

    # Opportunities vs score
    if overall < 30:
        opportunities += [
            f"Massive upside — realistic near-term target {overall + 40} points.",
            "Fixing fundamentals can yield +20–30 points quickly.",
            "Peers may be similar — the fastest mover wins."
        ]
    elif overall < 50:
        opportunities += [
            f"Meaningful growth potential — target {overall + 30} points.",
            "SEO optimization could lift organic traffic by 50–100%.",
            "Content marketing can boost visibility and expertise."
        ]
    elif overall < 70:
        opportunities += [
            f"Strong base — target {overall + 20} points.",
            "Chance to reach top quartile with focused investment.",
            "A/B testing and CRO will improve outcomes."
        ]
    else:
        opportunities += [
            "Strong foundation for innovation.",
            "AI and automation are the next leverage points.",
            "Personalization and UX can be a competitive edge."
        ]

    # Summary
    summary_parts = []
    if overall >= 75:
        summary_parts.append(f"Excellent digital maturity ({overall}/100). You are among the digital leaders in your space.")
    elif overall >= 60:
        summary_parts.append(f"Good digital presence ({overall}/100). Fundamentals are in place with room to improve.")
    elif overall >= 45:
        summary_parts.append(f"Baseline achieved ({overall}/100). Significant improvement opportunities identified.")
    elif overall >= 30:
        summary_parts.append(f"Digital presence needs work ({overall}/100). Multiple critical gaps observed.")
    else:
        summary_parts.append(f"Early-stage digital maturity ({overall}/100). Immediate action required to stay competitive.")

    if wc < 500:
        summary_parts.append(f"Content volume is low ({wc} words) — this is the biggest single lever.")
    if not technical.get('has_analytics'):
        summary_parts.append("No analytics — start tracking to measure impact and iterate.")

    if overall < 60:
        max_realistic = min(100, overall + 40)
        summary_parts.append(f"Realistic improvement potential: +{max_realistic - overall} points in 3–6 months.")

    if overall < 45:
        summary_parts.append("You lag peers — fast action is important.")
    elif overall > 60:
        summary_parts.append("You are ahead of many competitors; maintain momentum.")

    summary = " ".join(summary_parts)

    return {
        'summary': summary,
        'strengths': strengths[:5],
        'weaknesses': weaknesses[:5],
        'opportunities': opportunities[:4],
        'threats': threats[:3],
        'recommendations': (recs + quick_wins)[:5],
        'confidence_score': min(95, max(60, overall + 20)),
        'sentiment_score': (overall / 100) * 0.8 + 0.2,
        'key_metrics': {},
        'action_priority': []
    }

def generate_smart_actions(ai: AIAnalysis, technical: Dict[str, Any], content: Dict[str, Any], basic: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = []
    breakdown = basic.get('score_breakdown', {})
    overall = basic.get('digital_maturity_score', 0)

    # SECURITY
    sec = breakdown.get('security', 0)
    if sec < 15:
        if sec == 0:
            actions.append({
                "title": "Critical: Enable HTTPS immediately",
                "description": "No SSL certificate present — this is a critical security issue.",
                "priority": "critical", "effort": "low", "impact": "critical",
                "estimated_score_increase": 10, "category": "security", "estimated_time": "1–2 days"
            })
        elif sec < 10:
            actions.append({
                "title": "Add missing security headers",
                "description": f"Security {sec}/15. Add CSP, HSTS and X-Frame-Options.",
                "priority": "high", "effort": "low", "impact": "high",
                "estimated_score_increase": 15 - sec, "category": "security", "estimated_time": "1 day"
            })
        else:
            actions.append({
                "title": "Tighten security headers",
                "description": f"Security {sec}/15. Finalize header policies.",
                "priority": "medium", "effort": "low", "impact": "medium",
                "estimated_score_increase": 15 - sec, "category": "security", "estimated_time": "2–4 hours"
            })

    # SEO
    seo = breakdown.get('seo_basics', 0)
    if seo < 20:
        gap = 20 - seo
        if gap > 10:
            actions.append({
                "title": "Fix critical SEO basics",
                "description": f"SEO {seo}/20. Correct titles, meta descriptions, and heading structure.",
                "priority": "critical", "effort": "low", "impact": "critical",
                "estimated_score_increase": min(10, gap), "category": "seo", "estimated_time": "1–2 days"
            })
        elif gap > 5:
            actions.append({
                "title": "Improve on-page SEO",
                "description": f"SEO {seo}/20. Optimize metadata and URL structure.",
                "priority": "high", "effort": "medium", "impact": "high",
                "estimated_score_increase": gap, "category": "seo", "estimated_time": "3–5 days"
            })
        else:
            actions.append({
                "title": "Fine-tune advanced SEO",
                "description": f"SEO {seo}/20. Add canonical, hreflang, and structured data.",
                "priority": "medium", "effort": "medium", "impact": "medium",
                "estimated_score_increase": gap, "category": "seo", "estimated_time": "1 week"
            })

    # CONTENT
    c = breakdown.get('content', 0)
    if c < 20:
        gap = 20 - c
        wc = content.get('word_count', 0)
        if c <= 5:
            actions.append({
                "title": "Create a comprehensive content strategy",
                "description": f"Content only {c}/20. {wc} words across key pages — substantial content production required.",
                "priority": "critical", "effort": "high", "impact": "critical",
                "estimated_score_increase": min(15, gap), "category": "content", "estimated_time": "2–4 weeks"
            })
        elif c <= 10:
            actions.append({
                "title": "Expand core content depth",
                "description": f"Content {c}/20. Add in-depth pages and supporting articles.",
                "priority": "high", "effort": "high", "impact": "high",
                "estimated_score_increase": min(10, gap), "category": "content", "estimated_time": "2 weeks"
            })
        else:
            actions.append({
                "title": "Improve content quality & readability",
                "description": f"Content {c}/20. Increase readability and add rich media.",
                "priority": "medium", "effort": "medium", "impact": "medium",
                "estimated_score_increase": gap, "category": "content", "estimated_time": "1 week"
            })

    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    actions.sort(key=lambda x: (priority_order.get(x['priority'], 4), -x.get('estimated_score_increase', 0)))
    return actions[:15]

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/auth/login")
async def login(request: LoginRequest):
    """Login endpoint compatible with frontend"""
    logger.info(f"Login attempt for user: {request.username}")
    
    # Check if user exists
    if request.username not in USERS_PASSWORDS:
        logger.warning(f"User not found: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Verify password
    expected_password = USERS_PASSWORDS[request.username]
    if not verify_password(request.password, expected_password):
        logger.warning(f"Invalid password for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create token
    user_role = users_data[request.username]["role"]
    token = create_access_token({"sub": request.username, "role": user_role})
    
    logger.info(f"Login successful for user: {request.username}")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user_role,
        "username": request.username
    }

@app.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    username = current_user["username"]
    role = current_user["role"]
    
    user_data = users_data.get(username, {"role": "guest", "usage_count": 0})
    usage_count = user_data.get("usage_count", 0)
    usage_limit = USAGE_LIMITS.get(role, 3)
    
    return {
        "username": username,
        "role": role,
        "usage_count": usage_count,
        "usage_limit": usage_limit,
        "remaining": usage_limit - usage_count if usage_limit != float('inf') else "unlimited"
    }

@app.post("/auth/logout")
async def logout():
    """Logout endpoint"""
    return {"message": "Logged out successfully"}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "login": "/auth/login",
            "logout": "/auth/logout",
            "me": "/auth/me",
            "basic_analysis": "/api/v1/analyze",
            "ai_analysis": "/api/v1/ai-analyze"
        },
        "features": [
            "JWT Authentication",
            "Fair 0–100 scoring system",
            "No arbitrary baselines",
            "Comprehensive analysis",
            "AI-powered insights",
            "Enhanced features (trends, tech stack, CWV, mobile-first)"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "openai_available": bool(openai_client),
        "cache_size": len(analysis_cache),
        "bcrypt_available": BCRYPT_AVAILABLE
    }

@app.post("/api/v1/ai-analyze")
async def ai_analyze(
    request: CompetitorAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """Main AI analysis endpoint with auth"""
    username = current_user["username"]
    role = current_user["role"]
    
    # Check usage limits
    user_data = users_data.get(username, {"role": "guest", "usage_count": 0})
    usage_limit = USAGE_LIMITS.get(role, 3)
    
    if user_data["usage_count"] >= usage_limit and usage_limit != float('inf'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usage limit reached. {role.capitalize()} limit: {usage_limit} analyses"
        )
    
    try:
        url = clean_url(request.url)
        cache_key = get_cache_key(url, "ai_v5_enhanced_enonly")
        if cache_key in analysis_cache and is_cache_valid(analysis_cache[cache_key]['timestamp']):
            logger.info(f"Cache hit for {url}")
            cached_result = analysis_cache[cache_key]['data']
            cached_result['metadata']['cached'] = True
            cached_result['metadata']['user_role'] = role
            return cached_result

        resp = await fetch_url(url)
        if not resp or resp.status_code != 200:
            raise HTTPException(400, f"Cannot fetch {url}")

        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        basic = await analyze_basic_metrics(url, html)
        technical = await analyze_technical_aspects(url, html)
        content = await analyze_content_quality(html)
        ux = await analyze_ux_elements(html)
        social = await analyze_social_media_presence(url, html)
        competitive = await analyze_competitive_positioning(url, basic)

        ai = await generate_ai_insights(url, basic, technical, content, ux, social)

        tech_stack = detect_technology_stack(html, soup)
        mobile_first = assess_mobile_first_readiness(soup, html)
        core_vitals = estimate_core_web_vitals(soup, html)
        traffic_rank = estimate_traffic_rank(url, basic)
        market_trends = generate_market_trends()
        improvement_potential = calculate_improvement_potential(basic)
        competitor_gaps = generate_competitor_gaps(basic, competitive)

        enhanced = {
            "industry_benchmarking": {
                "value": f"{basic['digital_maturity_score']} / 100",
                "description": "Industry avg: 45, Top 25%: 70",
                "status": "above_average" if basic['digital_maturity_score'] > 45 else "below_average",
                "details": {
                    "your_score": basic['digital_maturity_score'],
                    "industry_average": 45,
                    "top_quartile": 70,
                    "bottom_quartile": 30,
                    "percentile": min(100, int((basic['digital_maturity_score'] / 45) * 50)) if basic['digital_maturity_score'] <= 45 else 50 + int(((basic['digital_maturity_score'] - 45) / 55) * 50)
                }
            },
            "competitor_gaps": {
                "value": f"{len(competitor_gaps)} identified",
                "description": "Most significant differences vs. competitors",
                "items": competitor_gaps,
                "status": "critical" if len(competitor_gaps) > 2 else "moderate"
            },
            "growth_opportunities": {
                "value": f"+{improvement_potential} points",
                "description": "Realistic improvement potential in ~6 months",
                "items": ai.opportunities[:3] if hasattr(ai, 'opportunities') else [],
                "potential_score": basic['digital_maturity_score'] + improvement_potential
            },
            "risk_assessment": {
                "value": f"{len(ai.threats if hasattr(ai, 'threats') else [])} risks",
                "description": "Identified critical risks",
                "items": ai.threats[:3] if hasattr(ai, 'threats') else [],
                "severity": "high" if basic['digital_maturity_score'] < 30 else "medium" if basic['digital_maturity_score'] < 60 else "low"
            },
            "market_trends": {
                "value": f"{len(market_trends)} trends",
                "description": "Relevant market trends",
                "items": market_trends,
                "alignment": "aligned" if basic['digital_maturity_score'] > 60 else "partially_aligned" if basic['digital_maturity_score'] > 30 else "not_aligned"
            },
            "technology_stack": {
                "value": f"{tech_stack['count']} technologies",
                "description": ", ".join(tech_stack['detected'][:3]) + ("..." if len(tech_stack['detected']) > 3 else "") if tech_stack['detected'] else "Not detected",
                "detected": tech_stack['detected'],
                "categories": tech_stack['categories'],
                "modernity": "modern" if any(x for x in tech_stack['detected'] if any(y in x for y in ['React','Next','Vue'])) else "traditional"
            },
            "estimated_traffic_rank": {
                "value": traffic_rank,
                "description": "Estimated position by traffic potential",
                "confidence": "medium",
                "factors": ["Digital maturity score", "SEO optimization", "Content volume"]
            },
            "mobile_first_index_ready": {
                "value": "Yes" if mobile_first['ready'] else "No",
                "description": "Google Mobile-First readiness",
                "status": "ready" if mobile_first['ready'] else "not_ready",
                "score": mobile_first['score'],
                "issues": mobile_first['issues'],
                "recommendations": mobile_first['recommendations']
            },
            "core_web_vitals_assessment": {
                "value": core_vitals['overall_status'],
                "description": f"LCP: {core_vitals['lcp']['value']}, FID: {core_vitals['fid']['value']}, CLS: {core_vitals['cls']['value']}",
                "lcp": core_vitals['lcp'],
                "fid": core_vitals['fid'],
                "cls": core_vitals['cls'],
                "overall_status": core_vitals['overall_status'],
                "recommendations": core_vitals['recommendations']
            }
        }

        result = {
            "success": True,
            "company_name": request.company_name or basic.get('title', 'Unknown'),
            "analysis_date": datetime.now().isoformat(),
            "basic_analysis": BasicAnalysis(
                company=request.company_name or basic.get('title', 'Unknown'),
                website=url,
                digital_maturity_score=basic['digital_maturity_score'],
                social_platforms=basic.get('social_platforms', 0),
                technical_score=technical.get('overall_technical_score', 0),
                content_score=content.get('content_quality_score', 0),
                seo_score=int((basic.get('score_breakdown', {}).get('seo_basics', 0) / 20) * 100),
                score_breakdown=ScoreBreakdown(**basic.get('score_breakdown', {}))
            ).dict(),
            "ai_analysis": ai.dict(),
            "detailed_analysis": DetailedAnalysis(
                social_media=SocialMediaAnalysis(**social),
                technical_audit=TechnicalAudit(**technical),
                content_analysis=ContentAnalysis(**content),
                ux_analysis=UXAnalysis(**ux),
                competitive_analysis=CompetitiveAnalysis(**competitive)
            ).dict(),
            "smart": {
                "actions": generate_smart_actions(ai, technical, content, basic),
                "scores": SmartScores(
                    overall=basic['digital_maturity_score'],
                    technical=technical.get('overall_technical_score', 0),
                    content=content.get('content_quality_score', 0),
                    social=social.get('social_score', 0),
                    ux=ux.get('overall_ux_score', 0),
                    competitive=competitive.get('competitive_score', 0),
                    trend="improving" if improvement_potential > 20 else "stable",
                    percentile=enhanced['industry_benchmarking']['details']['percentile']
                ).dict()
            },
            "enhanced_features": enhanced,
            "metadata": {
                "version": APP_VERSION,
                "analysis_depth": "comprehensive",
                "confidence_level": ai.confidence_score,
                "data_points_analyzed": len(tech_stack['detected']) + len(basic.get('detailed_findings', {})),
                "cached": False,
                "user_role": role,
                "usage_count": user_data["usage_count"] + 1,
                "usage_limit": usage_limit
            }
        }

        result = ensure_integer_scores(result)

        # Update usage count
        if username in users_data:
            users_data[username]["usage_count"] = user_data["usage_count"] + 1

        analysis_cache[cache_key] = {'data': result, 'timestamp': datetime.now()}
        if len(analysis_cache) > MAX_CACHE_SIZE:
            oldest = min(analysis_cache.keys(), key=lambda k: analysis_cache[k]['timestamp'])
            del analysis_cache[oldest]

        logger.info(f"Enhanced analysis complete for {url}: score={basic['digital_maturity_score']}")
        return result
    except Exception as e:
        logger.error(f"Analysis error for {request.url}: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.post("/api/v1/analyze")
async def basic_analyze(
    request: CompetitorAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """Basic analysis endpoint - calls same as AI analyze"""
    return await ai_analyze(request, current_user)

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    
    print(f"""
    ╔══════════════════════════════════════════════════════╗
    ║  {APP_NAME} v{APP_VERSION}  ║
    ╠══════════════════════════════════════════════════════╣
    ║  Server: http://{host}:{port}                       ║
    ║  Docs:   http://{host}:{port}/docs                  ║
    ╠══════════════════════════════════════════════════════╣
    ║  Test Logins:                                        ║
    ║  - admin / {os.getenv('ADMIN_PASSWORD', 'kaikka123')}              ║
    ║  - user / user123                                    ║
    ║  - guest / (empty)                                   ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    logger.info(f"{APP_NAME} v{APP_VERSION} — English-only with JWT Auth")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)market_trends(industry: str = None) -> List[str]:
    trends = [
        "Mobile-first indexing is the default — mobile UX is non-negotiable",
        "Core Web Vitals directly influence search rankings",
        "AI-generated content and chat assistants are becoming standard",
        "Video content drives significantly higher engagement than text",
        "Voice search pushes toward longer, conversational queries"
    ]
    if industry:
        il = industry.lower()
        if "retail" in il or "commerce" in il:
            trends += ["Social commerce is table stakes", "Personalization can lift conversion by 10–20%"]
        elif "tech" in il:
            trends += ["Developer docs and API portals are expected", "Open source presence builds credibility"]
        elif "service" in il:
            trends += ["Online booking is a baseline expectation", "Reviews are critical to trust"]
    return trends[:5]

def calculate_improvement_potential(basic: Dict[str, Any]) -> int:
    current = basic.get('digital_maturity_score', 0)
    breakdown = basic.get('score_breakdown', {})
    potential = 0
    for cat, max_pts in SCORING_WEIGHTS.items():
        cur = breakdown.get(cat, 0)
        gap = max_pts - cur
        if gap > max_pts * 0.7: potential += int(gap * 0.8)
        elif gap > max_pts * 0.4: potential += int(gap * 0.6)
        else: potential += int(gap * 0.4)
    return min(potential, 100 - current)

def generate_
