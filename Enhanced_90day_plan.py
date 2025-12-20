# Enhanced 90-Day Implementation Plan Generator
# Much more detailed and actionable than the current version

from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ActionItem(BaseModel):
    """Detailed action item with all necessary context"""
    week: str                    # e.g. "Week 1-2"
    title: str                   # e.g. "SSL Certificate Installation"
    description: str             # Detailed what & why
    steps: List[str] = []        # Concrete step-by-step actions
    owner: str                   # "Dev", "Marketing", "Content", "Agency"
    time_estimate: str           # e.g. "2-4 hours"
    dependencies: List[str] = [] # What needs to be done first
    success_metric: str          # How to measure completion
    priority: str                # "Critical", "High", "Medium"

class Plan90D(BaseModel):
    """Complete 90-day plan structure"""
    wave_1: List[ActionItem] = []            # Weeks 1-4: Foundation
    wave_2: List[ActionItem] = []            # Weeks 5-8: Content & SEO
    wave_3: List[ActionItem] = []            # Weeks 9-12: Scale
    one_thing_this_week: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None

def generate_enhanced_90day_plan(
    basic: Dict[str, Any], 
    content: Dict[str, Any], 
    technical: Dict[str, Any], 
    language: str = 'en',
    competitor_gap: Dict[str, Any] = None
) -> Plan90D:
    """
    Generate a comprehensive, actionable 90-day plan with:
    - Detailed step-by-step instructions
    - Time estimates
    - Clear ownership
    - Success metrics
    - Dependencies
    
    NEW: Intelligent prioritization based on:
    - Business impact (revenue potential)
    - Competitive gaps (what competitors do better)
    - Actual maturity level (no SSL if you already have it)
    - Quick wins vs long-term investments
    """
    
    score = basic.get('digital_maturity_score', 0)
    breakdown = basic.get('score_breakdown', {})
    
    # Analyze gaps to prioritize
    has_ssl = technical.get('has_ssl', True)
    has_analytics = technical.get('has_analytics', False)
    mobile_score = breakdown.get('mobile', 0)
    seo_score = breakdown.get('seo_basics', 0)
    content_score = breakdown.get('content', 0)
    security_score = breakdown.get('security', 0)
    
    # NEW: Calculate maturity tier for smart prioritization
    maturity_tier = 'high' if score >= 75 else 'medium' if score >= 50 else 'low'
    
    # NEW: Analyze competitive gaps
    comp_gap = competitor_gap or {}
    avg_competitor_score = comp_gap.get('avg_competitor_score', score)
    gap = avg_competitor_score - score
    
    # Build action library
    actions_en = {
        'ssl_setup': ActionItem(
            week="Week 1",
            title="🔒 SSL Certificate Installation & Security Hardening",
            description="Install SSL certificate and configure HTTPS to secure your website and improve SEO rankings. Google requires HTTPS for top rankings.",
            steps=[
                "Purchase SSL certificate from provider (Let's Encrypt free, or paid from Cloudflare/DigiCert)",
                "Install certificate on web server (cPanel/Plesk/manual)",
                "Configure automatic HTTP→HTTPS redirect (301 permanent)",
                "Update internal links to use HTTPS",
                "Test all pages load correctly over HTTPS",
                "Set up HSTS header (max-age=31536000)",
                "Submit HTTPS version to Google Search Console"
            ],
            owner="Developer",
            time_estimate="3-5 hours",
            dependencies=[],
            success_metric="All pages accessible via HTTPS, no mixed content warnings, SSL Labs grade A",
            priority="Critical"
        ),
        
        'analytics_setup': ActionItem(
            week="Week 1",
            title="📊 Google Analytics 4 & Conversion Tracking Setup",
            description="Install GA4 to start collecting data immediately. You need 30 days of data before making optimization decisions.",
            steps=[
                "Create GA4 property in Google Analytics",
                "Install GA4 tag via GTM or direct embed",
                "Define 3-5 key conversion events (form submit, purchase, newsletter signup, etc.)",
                "Configure enhanced measurement (scroll, outbound clicks, file downloads)",
                "Link to Google Search Console",
                "Set up custom events for critical user actions",
                "Create basic dashboard: traffic sources, popular pages, conversions",
                "Test events firing correctly (use GA4 DebugView)",
                "Set up weekly automated email reports"
            ],
            owner="Marketing",
            time_estimate="4-6 hours",
            dependencies=[],
            success_metric="GA4 collecting data, 3+ conversion events tracked, 0 errors in DebugView",
            priority="Critical"
        ),
        
        'seo_foundation': ActionItem(
            week="Week 2-3",
            title="🎯 SEO Foundation: Titles, Metas & Technical Basics",
            description="Fix low-hanging SEO fruit on your top 10 pages. These changes can show results in 2-4 weeks.",
            steps=[
                "Identify top 10 pages by traffic (Google Analytics)",
                "Audit titles: 50-60 chars, include primary keyword, brand at end",
                "Audit meta descriptions: 150-160 chars, compelling copy, include keyword",
                "Fix missing H1 tags (exactly 1 per page)",
                "Fix heading hierarchy (H1→H2→H3, no skipping levels)",
                "Add alt text to all images (descriptive, include keywords where natural)",
                "Check for duplicate titles/metas, make each unique",
                "Create XML sitemap if missing",
                "Submit sitemap to Google Search Console",
                "Fix broken internal links (use Screaming Frog or Ahrefs)",
                "Add schema.org markup for Organization/LocalBusiness"
            ],
            owner="Marketing + Developer",
            time_estimate="8-12 hours",
            dependencies=["Analytics setup"],
            success_metric="All top 10 pages have optimized titles/metas, 0 H1 errors, sitemap submitted",
            priority="High"
        ),
        
        'mobile_optimization': ActionItem(
            week="Week 3-4",
            title="📱 Mobile Optimization & Core Web Vitals",
            description="Ensure mobile users have a fast, smooth experience. 60%+ of traffic is mobile.",
            steps=[
                "Add viewport meta tag if missing: <meta name='viewport' content='width=device-width, initial-scale=1'>",
                "Test on real devices (iPhone, Android) + Chrome DevTools mobile emulator",
                "Run Google PageSpeed Insights for mobile, target 70+ score",
                "Compress images: use TinyPNG/ImageOptim, target <200KB per image",
                "Implement lazy loading for below-fold images",
                "Minify CSS and JavaScript",
                "Enable browser caching (set Cache-Control headers)",
                "Consider CDN for static assets (Cloudflare free tier)",
                "Fix tap targets: min 48x48px, adequate spacing",
                "Test forms on mobile: ensure inputs are properly sized",
                "Optimize font loading (font-display: swap)",
                "Achieve Core Web Vitals: LCP <2.5s, FID <100ms, CLS <0.1"
            ],
            owner="Developer",
            time_estimate="10-15 hours",
            dependencies=["SSL setup"],
            success_metric="Mobile PageSpeed 70+, all Core Web Vitals 'Good', responsive on all devices",
            priority="High"
        ),
        
        'content_strategy': ActionItem(
            week="Week 5-6",
            title="✍️ Content Strategy & Pillar Article Planning",
            description="Plan high-quality content that attracts and converts your ideal customers.",
            steps=[
                "Research 10-15 keywords your customers search (Ahrefs, SEMrush, or AnswerThePublic)",
                "Analyze search intent: what are users really looking for?",
                "Identify 3-4 'pillar' topics (broad, high search volume)",
                "For each pillar, identify 8-10 'cluster' subtopics",
                "Analyze top 3 ranking competitors for each topic",
                "Create content brief for first pillar article: outline, target keywords, word count (2000+), competitor gaps",
                "Define content calendar for next 90 days",
                "Allocate budget: in-house writer vs freelancer vs agency",
                "Set up editorial workflow: draft→review→optimize→publish"
            ],
            owner="Content/Marketing",
            time_estimate="6-8 hours",
            dependencies=["Analytics setup", "SEO foundation"],
            success_metric="Content calendar created, 3 pillar topics researched, first brief complete",
            priority="High"
        ),
        
        'content_creation': ActionItem(
            week="Week 7-8",
            title="📝 Content Creation: First Pillar Articles",
            description="Create comprehensive, expert-level content that ranks and converts.",
            steps=[
                "Write first pillar article (2000-3000 words)",
                "Include: clear H1, logical H2/H3 structure, images/diagrams, internal links",
                "Optimize for featured snippet: concise answer at top",
                "Add FAQ section with 5-8 common questions",
                "Include CTA: newsletter signup, consultation booking, product demo",
                "SEO optimize: target keyword in title, URL, H1, first paragraph, 2-3% density",
                "Add internal links to 3-5 related pages",
                "Source and compress images (<200KB each)",
                "Write compelling meta description",
                "Peer review for accuracy and quality",
                "Publish and share on social media"
            ],
            owner="Content",
            time_estimate="12-16 hours per article",
            dependencies=["Content strategy"],
            success_metric="First 2 pillar articles published, 2000+ words each, fully optimized",
            priority="High"
        ),
        
        'technical_seo': ActionItem(
            week="Week 7-8",
            title="⚙️ Technical SEO: Schema, Sitemap & Speed",
            description="Implement technical improvements that help search engines understand and rank your site.",
            steps=[
                "Implement FAQ schema markup on key pages (use Google's Schema Markup Helper)",
                "Add BreadcrumbList schema for navigation",
                "Set up structured data testing (Google Rich Results Test)",
                "Create/update robots.txt: disallow admin areas, allow important pages",
                "Generate/update XML sitemap with priority and changefreq",
                "Submit sitemap to Google Search Console + Bing Webmaster Tools",
                "Set up Google Search Console: verify property, check for crawl errors",
                "Fix any crawl errors or coverage issues",
                "Implement canonical tags to avoid duplicate content",
                "Set up 301 redirects for any moved/deleted pages"
            ],
            owner="Developer",
            time_estimate="6-8 hours",
            dependencies=["SEO foundation"],
            success_metric="Schema validated, sitemap submitted, 0 crawl errors in Search Console",
            priority="Medium"
        ),
        
        'content_expansion': ActionItem(
            week="Week 9-10",
            title="🚀 Content Expansion: Cluster Articles & Link Building",
            description="Expand content hub with supporting articles and build internal linking structure.",
            steps=[
                "Write 4-6 cluster articles (1000-1500 words each) supporting pillar content",
                "Link all cluster articles to main pillar (contextual links)",
                "Link pillar article to relevant clusters",
                "Update older content: add links to new articles, refresh dates, add new info",
                "Create topic cluster diagram (visual representation)",
                "Optimize images for all new articles",
                "Share new content on social media, LinkedIn, relevant communities",
                "Reach out to 5-10 relevant sites for backlinks/guest posts",
                "Monitor rankings in Google Search Console"
            ],
            owner="Content/Marketing",
            time_estimate="16-20 hours",
            dependencies=["Content creation"],
            success_metric="4+ cluster articles published, internal linking complete, 2+ external backlinks",
            priority="Medium"
        ),
        
        'conversion_optimization': ActionItem(
            week="Week 10-11",
            title="💰 Conversion Rate Optimization: Testing & Optimization",
            description="Optimize your highest-traffic pages to convert more visitors into customers.",
            steps=[
                "Identify top 3 landing pages by traffic",
                "Analyze current conversion rate and user behavior (heatmaps, session recordings)",
                "Identify friction points: slow loading, unclear CTA, poor mobile UX",
                "Create A/B test hypotheses: headline variations, CTA button text/color, form length",
                "Set up A/B tests (Google Optimize, VWO, or Optimizely)",
                "Test variations for 2 weeks minimum (need statistical significance)",
                "Analyze results: winner by conversion rate, revenue per visitor",
                "Implement winning variation",
                "Document learnings and apply to other pages"
            ],
            owner="Marketing",
            time_estimate="10-12 hours",
            dependencies=["Analytics setup", "Mobile optimization"],
            success_metric="3 A/B tests running, 1+ winning variation implemented, documented learnings",
            priority="Medium"
        ),
        
        'advanced_tracking': ActionItem(
            week="Week 11",
            title="📈 Advanced Analytics: Dashboards & Attribution",
            description="Set up comprehensive tracking and reporting to measure ROI and guide decisions.",
            steps=[
                "Create custom GA4 dashboard: traffic, conversions, revenue, engagement",
                "Set up goal funnels: identify drop-off points",
                "Configure enhanced e-commerce tracking (if applicable)",
                "Set up Google Tag Manager: migrate tracking codes, create triggers/tags",
                "Implement event tracking: scroll depth, video plays, downloads, outbound clicks",
                "Set up custom dimensions: user type, product category, campaign source",
                "Create automated weekly report: key metrics, trends, anomalies",
                "Set up alerts for traffic drops, conversion drops, critical errors",
                "Document analytics setup for team"
            ],
            owner="Marketing + Developer",
            time_estimate="8-10 hours",
            dependencies=["Analytics setup"],
            success_metric="Custom dashboard live, enhanced tracking implemented, automated reports active",
            priority="Medium"
        ),
        
        # ========================================
        # NEW: MODERN, BUSINESS-FOCUSED ACTIONS
        # ========================================
        
        'competitive_content_gap': ActionItem(
            week="Week 1-2",
            title="🎯 Close Competitive Content Gaps",
            description="Identify and fix the 3-5 content areas where competitors outrank you. Quick wins with high ROI.",
            steps=[
                "Run competitor content gap analysis (Ahrefs/SEMrush): find keywords they rank for but you don't",
                "Prioritize by search volume × business relevance (focus on money keywords)",
                "Identify their top 5 ranking pages: what makes them rank?",
                "Create superior content: longer, more actionable, better visuals",
                "Add unique value: original data, case studies, tools/calculators",
                "Optimize for search intent: informational vs transactional",
                "Internal link from high-authority pages",
                "Promote on channels where competitors got traction"
            ],
            owner="Content + Marketing",
            time_estimate="12-16 hours",
            dependencies=[],
            success_metric="3 new pages published targeting competitor gaps, ranking in top 10 within 30 days",
            priority="High"
        ),
        
        'conversion_funnel_audit': ActionItem(
            week="Week 1-2",
            title="💰 Conversion Funnel Deep Dive",
            description="Find the biggest leak in your funnel and fix it. Often worth 20-50% revenue increase.",
            steps=[
                "Map current funnel: awareness → consideration → decision → action",
                "Identify drop-off points in GA4: where do you lose 50%+ of users?",
                "Run heatmaps + session recordings on key pages (Hotjar/Microsoft Clarity)",
                "Survey 10-20 customers: why did you buy? What almost stopped you?",
                "Survey 10-20 abandoners: why didn't you buy?",
                "Fix the #1 friction point (often: unclear pricing, slow checkout, missing trust signals)",
                "A/B test the fix for 2 weeks",
                "Measure revenue impact"
            ],
            owner="Marketing + Product",
            time_estimate="10-14 hours",
            dependencies=[],
            success_metric="Identified #1 funnel leak, implemented fix, measured before/after conversion rate",
            priority="Critical"
        ),
        
        'email_automation_revenue': ActionItem(
            week="Week 2-3",
            title="📧 Revenue-Driving Email Automation",
            description="Set up 3 automated email flows that generate revenue on autopilot.",
            steps=[
                "Segment your list: new subscribers, engaged, inactive, customers",
                "Flow 1: Welcome series (3-5 emails) → educate → soft sell",
                "Flow 2: Abandoned cart (3 emails over 7 days) → reminder → discount → urgency",
                "Flow 3: Re-engagement (2 emails) → value reminder → last chance offer",
                "Write compelling subject lines (A/B test 2 variants)",
                "Design mobile-first emails (70% open on mobile)",
                "Set up tracking: open rate, click rate, conversion rate, revenue per email",
                "Test flows with 10% of list first"
            ],
            owner="Marketing",
            time_estimate="8-12 hours",
            dependencies=[],
            success_metric="3 email flows live, generating measurable revenue within 30 days",
            priority="High"
        ),
        
        'ai_content_seo_boost': ActionItem(
            week="Week 3-4",
            title="🤖 AI-Powered Content Scaling",
            description="Use AI to 10x your content output while maintaining quality. Focus on long-tail keywords.",
            steps=[
                "Identify 50-100 long-tail keywords (low competition, high intent)",
                "Create content templates for each content type (how-to, comparison, listicle)",
                "Use Claude/ChatGPT to generate first drafts (with your brand voice prompt)",
                "Human editing: add unique insights, update with latest data, inject personality",
                "Batch-optimize: titles, metas, internal links",
                "Publish 2-3 articles per week",
                "Track: rankings, traffic, time-to-rank",
                "Double down on what works"
            ],
            owner="Content",
            time_estimate="15-20 hours setup + 4 hours/week ongoing",
            dependencies=[],
            success_metric="20+ AI-assisted articles published, 50% ranking in top 20 within 60 days",
            priority="High"
        ),
        
        'customer_retention_program': ActionItem(
            week="Week 4-5",
            title="🔁 Customer Retention & LTV Increase",
            description="Increase customer lifetime value by 30%+ with a simple retention program.",
            steps=[
                "Calculate current LTV and churn rate",
                "Interview 10 churned customers: why did they leave?",
                "Interview 10 loyal customers: why do they stay?",
                "Build retention program: onboarding checklist, success milestones, check-ins",
                "Create value-add content: tips, best practices, insider knowledge",
                "Set up automated nurture emails (monthly)",
                "Launch referral program: give $X, get $X",
                "Track: churn rate reduction, NPS increase, referral signups"
            ],
            owner="Customer Success + Marketing",
            time_estimate="12-16 hours",
            dependencies=[],
            success_metric="Churn reduced by 15%, referral program generating 5+ signups/month",
            priority="High"
        ),
        
        'social_proof_trust_boost': ActionItem(
            week="Week 5-6",
            title="⭐ Social Proof & Trust Signal Overhaul",
            description="Add credibility signals that increase conversion by 20-40%.",
            steps=[
                "Collect 20+ customer testimonials (email blast + incentive)",
                "Create 3-5 detailed case studies with metrics",
                "Add review schema markup (stars show in Google)",
                "Display real-time social proof: 'X people bought this today'",
                "Add trust badges: secure checkout, money-back guarantee, free shipping",
                "Showcase: media mentions, awards, certifications, client logos",
                "Add video testimonials to key landing pages",
                "Track conversion rate before/after"
            ],
            owner="Marketing + Sales",
            time_estimate="10-12 hours",
            dependencies=[],
            success_metric="20+ testimonials live, 3 case studies published, conversion rate +15%",
            priority="High"
        ),
        
        'competitor_feature_parity': ActionItem(
            week="Week 6-7",
            title="⚔️ Competitive Feature Parity Analysis",
            description="Identify the 3 features/benefits competitors highlight that you don't. Close the gap or reframe.",
            steps=[
                "Audit competitors' top 5 landing pages: what do they emphasize?",
                "List all features/benefits they mention that you don't",
                "Survey your sales team: what objections do prospects raise?",
                "Decision: do we build it, buy it, partner, or reframe?",
                "If reframe: craft messaging that neutralizes their advantage",
                "Update homepage, product pages, sales deck",
                "Train sales team on new positioning",
                "A/B test new messaging vs old"
            ],
            owner="Product + Marketing",
            time_estimate="8-10 hours",
            dependencies=[],
            success_metric="3 competitive gaps addressed, sales objections reduced by 30%",
            priority="Medium"
        ),
        
        'google_merchant_shopping_ads': ActionItem(
            week="Week 7-8",
            title="🛍️ Google Shopping Ads Quick Win",
            description="If you sell products, Shopping ads often have 2-3x better ROI than search ads.",
            steps=[
                "Set up Google Merchant Center account",
                "Create product feed (Shopify/WooCommerce plugin or manual CSV)",
                "Optimize product titles: brand + type + key attributes",
                "Add high-quality images (white background, 800x800px min)",
                "Set competitive prices (Google shows price comparison)",
                "Launch Shopping campaign: $20-50/day budget",
                "Optimize bids: increase for products with good ROAS",
                "Track: impressions, clicks, conversion rate, ROAS"
            ],
            owner="Marketing + E-commerce",
            time_estimate="6-8 hours",
            dependencies=[],
            success_metric="Shopping ads live, generating 3:1 ROAS or better within 30 days",
            priority="Medium"
        ),
        
        'local_seo_domination': ActionItem(
            week="Week 8-9",
            title="📍 Local SEO Domination (If Applicable)",
            description="For local businesses: rank #1 in Google Maps and local pack.",
            steps=[
                "Claim/optimize Google Business Profile: complete every field",
                "Add 20+ high-quality photos (interior, exterior, team, products)",
                "Get 50+ Google reviews (email campaign + QR codes in-store)",
                "Respond to ALL reviews (good and bad) within 24 hours",
                "Post weekly updates on GBP (offers, events, news)",
                "Build local citations: Yelp, Yellow Pages, industry directories",
                "Create location pages on website (if multi-location)",
                "Track: map rankings, profile views, direction requests, calls"
            ],
            owner="Marketing + Operations",
            time_estimate="10-14 hours",
            dependencies=[],
            success_metric="Ranking in top 3 for primary local keywords, 50+ reviews, 2x profile views",
            priority="High"
        ),
        
        'partnership_co_marketing': ActionItem(
            week="Week 9-10",
            title="🤝 Strategic Partnership Co-Marketing",
            description="Partner with complementary businesses to 2x your reach at zero cost.",
            steps=[
                "Identify 10 complementary businesses (same audience, different offering)",
                "Pitch collaboration: joint webinar, co-branded content, email swap",
                "Create partnership one-pager: your audience size, engagement stats",
                "Host joint webinar: each promotes to their list",
                "Co-create content: 'Ultimate Guide to X' with both brands",
                "Email list swap: each promotes other's lead magnet",
                "Track: new leads, conversion rate, cost per acquisition",
                "Nurture top 3 partnerships for ongoing collaboration"
            ],
            owner="Marketing + Partnerships",
            time_estimate="12-16 hours",
            dependencies=[],
            success_metric="2 partnerships launched, 500+ new leads generated, CPA <$10",
            priority="Medium"
        ),
        
        'video_content_youtube_seo': ActionItem(
            week="Week 10-11",
            title="🎥 Video Content & YouTube SEO",
            description="YouTube is the 2nd largest search engine. Capture that traffic.",
            steps=[
                "Identify 10 high-volume keywords in your niche",
                "Script 5-10 minute videos answering common questions",
                "Record with smartphone (good lighting + lapel mic = 80% of quality)",
                "Edit with CapCut/DaVinci Resolve (free)",
                "Optimize: keyword in title, description, tags",
                "Add timestamps, pinned comment with links",
                "Create custom thumbnail (text + face + contrast)",
                "Promote: embed on blog, share on LinkedIn, email list",
                "Track: views, watch time, subscribers, click-through to website"
            ],
            owner="Content + Marketing",
            time_estimate="15-20 hours",
            dependencies=[],
            success_metric="10 videos published, 1000+ total views, 50+ website clicks",
            priority="Medium"
        ),
        
        'review_optimize': ActionItem(
            week="Week 12",
            title="🎯 90-Day Review & Q2 Planning",
            description="Review results, document wins, identify next priorities for continued growth.",
            steps=[
                "Compile metrics: traffic change, ranking improvements, conversion rate, revenue impact",
                "Compare: pre-implementation vs current scores, traffic, conversions",
                "Document quick wins: what worked best, biggest ROI",
                "Identify ongoing issues: what still needs work",
                "Calculate ROI: revenue increase vs time/money invested",
                "Survey team: what went well, what was challenging",
                "Plan Q2 priorities: 3-5 key initiatives based on learnings",
                "Schedule quarterly check-ins for ongoing optimization",
                "Celebrate wins with team!"
            ],
            owner="All",
            time_estimate="4-6 hours",
            dependencies=["All previous tasks"],
            success_metric="Complete 90-day report, ROI calculated, Q2 roadmap defined",
            priority="High"
        ),
    }
    
    # Finnish translations
    # Finnish translations would go here, but for now use English actions
    # to ensure all action keys are available
    actions_fi = actions_en.copy()  # TODO: Add proper Finnish translations
    
    actions = actions_fi if language == 'fi' else actions_en
    
    # ========================================
    # NEW: INTELLIGENT WAVE PRIORITIZATION
    # ========================================
    wave_1_tasks = []
    wave_2_tasks = []
    wave_3_tasks = []
    
    # CRITICAL: Only suggest SSL if it's ACTUALLY missing (rare in 2025!)
    if not has_ssl and security_score == 0:
        wave_1_tasks.append(actions['ssl_setup'])
    
    # CRITICAL: Analytics if missing (common issue)
    if not has_analytics:
        wave_1_tasks.append(actions['analytics_setup'])
    
    # === WAVE 1: HIGHEST IMPACT, QUICKEST WINS ===
    
    # 1. Conversion optimization beats everything (direct revenue impact)
    if maturity_tier in ['medium', 'high']:
        wave_1_tasks.append(actions['conversion_funnel_audit'])
    
    # 2. Competitive content gaps = quick SEO wins
    if seo_score < 18 or gap > 10:
        wave_1_tasks.append(actions['competitive_content_gap'])
    
    # 3. Email automation = passive revenue
    if maturity_tier != 'low':
        wave_1_tasks.append(actions['email_automation_revenue'])
    
    # 4. Only suggest SEO foundation if it's actually broken
    if seo_score < 12:  # Raised threshold: only if really bad
        wave_1_tasks.append(actions['seo_foundation'])
    
    # 5. Mobile only if it's really bad (most sites are responsive now)
    if mobile_score < 8:  # Raised threshold
        wave_1_tasks.append(actions['mobile_optimization'])
    
    # === WAVE 2: CONTENT & GROWTH ===
    
    # 6. AI content scaling (modern approach)
    if content_score < 18 and maturity_tier != 'low':
        wave_2_tasks.append(actions['ai_content_seo_boost'])
    else:
        # Fallback to traditional content strategy
        if content_score < 15:
            wave_2_tasks.extend([
                actions['content_strategy'],
                actions['content_creation']
            ])
    
    # 7. Social proof & trust (huge conversion boost)
    wave_2_tasks.append(actions['social_proof_trust_boost'])
    
    # 8. Customer retention (often overlooked, huge impact)
    if maturity_tier == 'high':
        wave_2_tasks.append(actions['customer_retention_program'])
    
    # 9. Technical SEO (only if content exists)
    if content_score >= 10:
        wave_2_tasks.append(actions['technical_seo'])
    
    # === WAVE 3: SCALE & DIFFERENTIATION ===
    
    # 10. Competitive positioning
    if gap > 5:
        wave_3_tasks.append(actions['competitor_feature_parity'])
    
    # 11. E-commerce specific
    # Note: Check if 'industry' exists in basic dict
    industry = basic.get('industry', '').lower()
    if 'ecommerce' in industry or 'e-commerce' in industry:
        wave_3_tasks.append(actions['google_merchant_shopping_ads'])
    
    # 12. Local SEO (if applicable)
    if 'local' in industry or basic.get('has_physical_location', False):
        wave_3_tasks.append(actions['local_seo_domination'])
    
    # 13. Partnerships & co-marketing
    if maturity_tier in ['medium', 'high']:
        wave_3_tasks.append(actions['partnership_co_marketing'])
    
    # 14. Video content (modern trend)
    if maturity_tier == 'high':
        wave_3_tasks.append(actions['video_content_youtube_seo'])
    else:
        # Fallback to traditional content expansion
        if content_score >= 10:
            wave_3_tasks.append(actions['content_expansion'])
    
    # 15. CRO & advanced tracking
    wave_3_tasks.extend([
        actions['conversion_optimization'],
        actions['advanced_tracking']
    ])
    
    # Always end with review
    wave_3_tasks.append(actions['review_optimize'])
    
    # Limit to reasonable amounts
    wave_1_tasks = wave_1_tasks[:5]
    wave_2_tasks = wave_2_tasks[:5]
    wave_3_tasks = wave_3_tasks[:5]
    
    # ========================================
    # ONE THING THIS WEEK - Business Impact Focus
    # ========================================
    one_thing_texts = {
        'en': {
            'conversion': 'Audit your conversion funnel - find the biggest leak (often worth 20-50% revenue boost)',
            'content_gap': 'Close top 3 competitive content gaps - quick SEO wins',
            'email': 'Set up abandoned cart email flow - instant revenue recovery',
            'ssl': 'Install SSL certificate (blocks everything else)',
            'analytics': 'Install GA4 tracking - you need data to make decisions',
            'seo': 'Fix SEO on your top 10 revenue-generating pages',
            'default': 'Talk to 5 customers who churned - understand why they left'
        },
        'fi': {
            'conversion': 'Auditoi konversiosuppilo - löydä suurin vuoto (usein 20-50% tulosboosti)',
            'content_gap': 'Sulje 3 kilpailija-aukkoa sisällössä - nopeat SEO-voitot',
            'email': 'Asenna hylätyn ostoskorin sähköpostivirta - välitön tuotto',
            'ssl': 'Asenna SSL-sertifikaatti (estää kaiken muun)',
            'analytics': 'Asenna GA4-seuranta - tarvitaan dataa päätöksiin',
            'seo': 'Korjaa SEO 10 parhaalla tulosta tuottavalla sivulla',
            'default': 'Haastattele 5 lähtenyttä asiakasta - ymmärrä miksi lähtivät'
        }
    }
    
    texts = one_thing_texts[language]
    
    # Prioritize by business impact, not technical perfection
    if maturity_tier in ['medium', 'high']:
        one_thing = texts['conversion']  # Conversion always wins at this stage
    elif not has_ssl and security_score == 0:
        one_thing = texts['ssl']  # Only if truly missing
    elif not has_analytics:
        one_thing = texts['analytics']
    elif gap > 10:
        one_thing = texts['content_gap']  # Competitive gaps
    elif seo_score < 12:
        one_thing = texts['seo']
    else:
        one_thing = texts['default']  # Customer insights > random optimization
    
    return Plan90D(
        wave_1=wave_1_tasks,
        wave_2=wave_2_tasks,
        wave_3=wave_3_tasks,
        one_thing_this_week=one_thing,
        summary={
            'total_actions': len(wave_1_tasks) + len(wave_2_tasks) + len(wave_3_tasks),
            'estimated_hours': sum_hours(wave_1_tasks + wave_2_tasks + wave_3_tasks),
            'critical_path': [t.title for t in wave_1_tasks if t.priority == 'Critical']
        }
    )

def sum_hours(tasks: List[ActionItem]) -> str:
    """Calculate total estimated hours"""
    total = 0
    for task in tasks:
        # Parse "X-Y hours" format
        parts = task.time_estimate.split('-')
        if len(parts) == 2:
            low = int(parts[0].split()[0])
            high = int(parts[1].split()[0])
            total += (low + high) / 2
    return f"{int(total)}-{int(total * 1.3)} hours"
