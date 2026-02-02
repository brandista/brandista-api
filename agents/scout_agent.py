# -*- coding: utf-8 -*-
# Version: 2.1.0 - TRUE SWARM EDITION
"""
Growth Engine 2.0 - Scout Agent
TRUE SWARM EDITION - Actively communicates findings to other agents

"The Market Explorer" - Finds competitors and maps the market

SWARM FEATURES:
- Broadcasts competitor discoveries to Guardian and Strategist
- Publishes industry data to blackboard for all agents
- Alerts on high-threat competitors immediately
- Shares company intel with Analyst
"""

import logging
from typing import Dict, Any, List, Optional, Set

from .base_agent import BaseAgent
from .agent_types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)
from .communication import MessageType, MessagePriority
from .blackboard import DataCategory

# Company Intelligence for due diligence
try:
    from company_intel import CompanyIntel
    COMPANY_INTEL_AVAILABLE = True
except ImportError:
    COMPANY_INTEL_AVAILABLE = False
    CompanyIntel = None

logger = logging.getLogger("agents.scout_agent")


# Progress task translations
SCOUT_TASKS = {
    "analyzing_company": {"fi": "Analysoimassa kohdeyritystä...", "en": "Analyzing target company..."},
    "detecting_industry": {"fi": "Tunnistamassa toimialaa...", "en": "Detecting industry..."},
    "validating_competitors": {"fi": "Validoimassa annettuja kilpailijoita...", "en": "Validating provided competitors..."},
    "searching_competitors": {"fi": "Etsimässä kilpailijoita...", "en": "Searching for competitors..."},
    "scoring_results": {"fi": "Pisteytämässä tuloksia...", "en": "Scoring results..."},
    "enriching_companies": {"fi": "Haetaan yritystietoja (YTJ/Kauppalehti)...", "en": "Fetching company data (YTJ/Kauppalehti)..."},
    "finalizing": {"fi": "Viimeistellään löydöksiä...", "en": "Finalizing findings..."},
}


class ScoutAgent(BaseAgent):
    """
    🔍 Scout Agent - Kilpailijatiedustelija
    TRUE SWARM EDITION
    """
    
    def __init__(self):
        super().__init__(
            agent_id="scout",
            name="Scout",
            role="Kilpailijatiedustelija",
            avatar="🔍",
            personality="Utelias ja perusteellinen tutkimusmatkailija"
        )
        self.dependencies = []
        logger.info(f"[Scout] *** ScoutAgent initialized, COMPANY_INTEL_AVAILABLE={COMPANY_INTEL_AVAILABLE} ***")
    
    def _get_subscribed_message_types(self) -> List[MessageType]:
        """Scout subscribes to these message types"""
        return [
            MessageType.ALERT,
            MessageType.REQUEST,
            MessageType.HELP
        ]
    
    def _get_task_capabilities(self) -> Set[str]:
        """Tasks Scout can handle"""
        return {'competitor_scan', 'industry_detection', 'company_lookup'}
    
    def _setup_blackboard_subscriptions(self):
        """Scout doesn't need many subscriptions - it's the first agent"""
        pass
    
    def _task(self, key: str) -> str:
        """Get task text in current language"""
        return SCOUT_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        from main import (
            get_website_content,
            multi_provider_search,
            generate_smart_search_terms,
            clean_url,
            get_domain_from_url
        )
        
        # DEBUG: Log at very start of run
        logger.info(f"[Scout] ========== SCOUT AGENT STARTING ==========")
        logger.info(f"[Scout] URL: {context.url}")
        logger.info(f"[Scout] COMPANY_INTEL_AVAILABLE at start: {COMPANY_INTEL_AVAILABLE}")
        
        # 🧠 NEW: Check unified context for historical data
        tracked_competitor_domains = []
        discovered_competitor_domains = []
        previous_industry = None
        
        if context.unified_context:
            logger.info(f"[Scout] 🧠 UNIFIED CONTEXT AVAILABLE - Using historical data!")
            
            # Get tracked competitors from Radar
            tracked = context.unified_context.get('tracked_competitors') or []
            if tracked:
                tracked_competitor_domains = [c.get('domain') for c in tracked if c.get('domain')]
                logger.info(f"[Scout] Found {len(tracked_competitor_domains)} tracked competitors in Radar")
                
                self._emit_insight(
                    f"📊 {len(tracked_competitor_domains)} kilpailijaa jo trackattuna Radarissa",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'tracked_count': len(tracked_competitor_domains)}
                )
            
            # Get previously discovered competitors
            discovered = context.unified_context.get('discovered_competitors') or []
            if discovered:
                discovered_competitor_domains = [c.get('domain') for c in discovered if c.get('domain')]
                logger.info(f"[Scout] Found {len(discovered_competitor_domains)} previously discovered competitors")
            
            # Get previous industry detection
            profile = context.unified_context.get('profile') or {}
            previous_industry = profile.get('industry')
            if previous_industry:
                logger.info(f"[Scout] Previous industry: {previous_industry}")
                self._emit_insight(
                    f"ℹ️ Aiemmin tunnistettu toimiala: {previous_industry}",
                    priority=AgentPriority.LOW,
                    insight_type=InsightType.FINDING,
                    data={'previous_industry': previous_industry}
                )
        else:
            logger.info(f"[Scout] No unified context available (first analysis)")
        
        self._update_progress(15, self._task("analyzing_company"))

        # Emit conversation to Analyst
        self._emit_conversation(
            'analyst',
            f"Aloitan yrityksen {get_domain_from_url(context.url)} kilpailijakartoituksen.",
            f"Starting competitor mapping for {get_domain_from_url(context.url)}."
        )

        # 1. Hae kohdesivuston sisältö
        try:
            # get_website_content returns Tuple[Optional[str], bool] - (html_content, used_spa)
            html_content, used_spa = await get_website_content(context.url)
            
            # Build website_data dict for compatibility
            website_data = {
                'html': html_content or '',
                'used_spa': used_spa
            }
            context.website_data = website_data
            context.html_content = html_content or ''
            
            company_name = get_domain_from_url(context.url)
            
            self._emit_insight(
                self._t("scout.identified_company", company=company_name),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING,
                data={'company': company_name}
            )
            
        except Exception as e:
            logger.error(f"[Scout] Website fetch error: {e}")
            self._emit_insight(
                self._t("scout.website_fetch_failed"),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING
            )
            website_data = {'html': '', 'used_spa': False}
            context.website_data = website_data
            context.html_content = ''
            company_name = get_domain_from_url(context.url)
        
        self._update_progress(30, self._task("detecting_industry"))
        
        # 2. Get own company intel FIRST (needed for industry detection)
        your_company_intel = None
        if COMPANY_INTEL_AVAILABLE:
            try:
                your_company_intel = await self._get_own_company_intel(context.url)
                if your_company_intel:
                    logger.info(f"[Scout] Got company intel: {your_company_intel.get('name')}, TOL: {your_company_intel.get('industry_code')}")
                    # UPDATE company_name with real name from registry!
                    if your_company_intel.get('name'):
                        company_name = your_company_intel.get('name')
                        logger.info(f"[Scout] Updated company_name to: {company_name}")
            except Exception as e:
                logger.warning(f"[Scout] Company intel fetch failed: {e}")
        
        # 3. Detect industry (use company intel TOL code if available)
        industry = await self._detect_industry(
            context.url, 
            website_data, 
            context.industry_context,
            your_company_intel  # Pass company intel for TOL-based detection
        )
        
        self._emit_insight(
            self._t("scout.industry", industry=industry),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'industry': industry}
        )
        
        # 4. Jos kilpailijat jo annettu, validoi ne
        if context.competitor_urls and len(context.competitor_urls) > 0:
            self._update_progress(50, self._task("validating_competitors"))
            
            validated_competitors = await self._validate_competitors(
                context.competitor_urls,
                context.url
            )
            
            self._emit_insight(
                self._t("scout.validating_competitors", 
                       count=len(validated_competitors), 
                       total=len(context.competitor_urls)),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'count': len(validated_competitors)}
            )
            
            # Enrich with company intelligence (YTJ + Kauppalehti)
            self._update_progress(75, self._task("enriching_companies"))
            enriched_competitors = await self._enrich_with_company_intel(validated_competitors)
            
            # your_company_intel already fetched above
            
            return {
                'company': company_name,
                'url': context.url,  # Return the analyzed URL
                'industry': industry,
                'competitor_urls': validated_competitors,
                'competitor_count': len(validated_competitors),
                'discovery_method': 'user_provided',
                'website_data': website_data,
                'competitors_enriched': enriched_competitors,
                'your_company_intel': your_company_intel
            }
        
        # 5. Etsi kilpailijat automaattisesti
        self._update_progress(40, self._task("searching_competitors"))
        
        self._emit_insight(
            self._t("scout.starting_search"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # Generate search terms based on detected industry
        search_terms = generate_smart_search_terms(
            industry,           # Industry detected earlier (e.g., "korut", "jewelry")
            context.language,   # Country code (fi, en)
            None                # No custom terms
        )
        
        logger.info(f"[Scout] Industry: {industry}, Search terms: {search_terms}")
        
        searching_msg = {"fi": f"Haetaan: {search_terms[0]}...", "en": f"Searching: {search_terms[0]}..."}
        self._update_progress(50, searching_msg.get(self._language, searching_msg["en"]) if search_terms else "...")
        
        try:
            competitors = await multi_provider_search(
                search_terms=search_terms,
                num_results=10,
                country_code=context.language
            )
            
            # Transform URL list to competitor dicts
            competitor_dicts = []
            for url in competitors:
                competitor_dicts.append({
                    'url': url,
                    'title': get_domain_from_url(url),
                    'snippet': ''
                })
            
            self._update_progress(70, self._task("scoring_results"))
            
            scored_competitors = await self._score_competitors(
                competitor_dicts,
                context.url,
                industry
            )
            
            top_competitors = scored_competitors[:5]
            competitor_urls = [c['url'] for c in top_competitors]

            # Emit conversation to Analyst about findings
            if top_competitors:
                self._emit_conversation(
                    'analyst',
                    f"Löysin {len(top_competitors)} kilpailijaa! Paras osuma: {top_competitors[0].get('name', 'tuntematon')}.",
                    f"Found {len(top_competitors)} competitors! Best match: {top_competitors[0].get('name', 'unknown')}."
                )

            if top_competitors:
                top_score = top_competitors[0].get('relevance_score', 0)
                top_name = top_competitors[0].get('name', 'Unknown')
                
                self._emit_insight(
                    self._t("scout.found_competitors", 
                           count=len(top_competitors),
                           top=top_name,
                           score=top_score),
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.FINDING,
                    data={
                        'count': len(top_competitors),
                        'top_competitor': top_competitors[0] if top_competitors else None
                    }
                )
            else:
                self._emit_insight(
                    self._t("scout.no_competitors"),
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
            
            # Enrich with company intelligence (YTJ + Kauppalehti)
            self._update_progress(85, self._task("enriching_companies"))
            enriched_competitors = await self._enrich_with_company_intel(competitor_urls)
            
            # your_company_intel already fetched above
            
            self._update_progress(95, self._task("finalizing"))
            
            # ====================================================================
            # SWARM: Share findings with other agents
            # ====================================================================
            
            # 1. Publish industry to blackboard (all agents can use this)
            await self._publish_to_blackboard(
                key="industry",
                value={
                    'detected': industry,
                    'company': company_name,
                    'confidence': 0.8 if your_company_intel else 0.6
                },
                category=DataCategory.ANALYSIS
            )
            
            # 2. Publish competitors to blackboard
            await self._publish_to_blackboard(
                key="competitors.discovered",
                value={
                    'urls': competitor_urls,
                    'count': len(competitor_urls),
                    'enriched': enriched_competitors
                },
                category=DataCategory.COMPETITOR
            )
            
            # 3. Alert Guardian about high-threat competitors
            high_threat_competitors = [
                c for c in enriched_competitors
                if c.get('relevance_score', 0) >= 80 or 
                   (c.get('revenue') and c.get('revenue', 0) > 1000000)
            ]
            
            if high_threat_competitors:
                await self._send_message(
                    to_agent='guardian',
                    message_type=MessageType.ALERT,
                    subject=f"High-threat competitors found: {len(high_threat_competitors)}",
                    payload={
                        'competitors': high_threat_competitors,
                        'industry': industry
                    },
                    priority=MessagePriority.HIGH
                )
                logger.info(f"[Scout] 🚨 Alerted Guardian about {len(high_threat_competitors)} high-threat competitors")
            
            # 4. Share company intel with Analyst
            if your_company_intel:
                await self._send_message(
                    to_agent='analyst',
                    message_type=MessageType.DATA,
                    subject="Target company intel",
                    payload={
                        'company_name': company_name,
                        'company_intel': your_company_intel,
                        'industry': industry
                    }
                )
            
            # 5. Broadcast competitor discovery to all
            await self._share_finding(
                f"Discovered {len(competitor_urls)} competitors in {industry} industry",
                {
                    'competitor_count': len(competitor_urls),
                    'industry': industry,
                    'top_competitor': top_competitors[0] if top_competitors else None
                }
            )
            
            return {
                'company': company_name,
                'url': context.url,  # Return the analyzed URL
                'industry': industry,
                'competitor_urls': competitor_urls,
                'competitor_count': len(competitor_urls),
                'discovery_method': 'auto_discovered',
                'website_data': website_data,
                'all_candidates': scored_competitors,
                'competitors_enriched': enriched_competitors,
                'your_company_intel': your_company_intel
            }
            
        except Exception as e:
            logger.error(f"[Scout] Competitor search error: {e}")
            self._emit_insight(
                self._t("scout.search_failed", error=str(e)),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            
            return {
                'company': company_name,
                'url': context.url,  # Return the analyzed URL
                'industry': industry,
                'competitor_urls': [],
                'competitor_count': 0,
                'discovery_method': 'failed',
                'website_data': website_data,
                'your_company_intel': your_company_intel,  # Keep company intel even on error
                'error': str(e)
            }
    
    async def _detect_industry(
        self, 
        url: str, 
        website_data: Dict[str, Any],
        provided_industry: Optional[str] = None,
        company_intel: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Detect industry using multiple sources:
        1. User-provided industry (highest priority)
        2. Company intel TOL code (official registry)
        3. HTML content keywords (fallback)
        """
        if provided_industry:
            return provided_industry
        
        # Try to use TOL code from company intel
        if company_intel:
            industry_code = company_intel.get('industry_code', '')
            industry_name = company_intel.get('industry', '')
            
            # Map common TOL codes to our industry categories
            tol_mapping = {
                '47': 'ecommerce',      # Retail trade
                '46': 'ecommerce',      # Wholesale trade
                '62': 'saas',           # Computer programming
                '63': 'technology',     # Information service
                '70': 'consulting',     # Management consultancy
                '73': 'marketing',      # Advertising
                '64': 'finance',        # Financial services
                '86': 'healthcare',     # Health services
                '85': 'education',      # Education
                '68': 'real_estate',    # Real estate
                '10': 'manufacturing',  # Food manufacturing
                '25': 'manufacturing',  # Metal products
                '55': 'hospitality',    # Hotels
                '56': 'hospitality',    # Restaurants
                '45': 'automotive',     # Motor vehicles
                '32': 'jewelry',        # Other manufacturing (includes jewelry)
            }
            
            if industry_code:
                # Get first 2 digits of TOL code
                tol_prefix = str(industry_code)[:2]
                if tol_prefix in tol_mapping:
                    detected = tol_mapping[tol_prefix]
                    logger.info(f"[Scout] Industry from TOL code {industry_code}: {detected}")
                    return detected
            
            # Check industry name for keywords
            if industry_name:
                industry_lower = industry_name.lower()
                if any(kw in industry_lower for kw in ['koru', 'jewelry', 'jewel', 'kulta', 'gold']):
                    return 'jewelry'
                if any(kw in industry_lower for kw in ['ohjelmisto', 'software', 'it-', 'tietojen']):
                    return 'saas'
                if any(kw in industry_lower for kw in ['konsult', 'consult', 'neuvon']):
                    return 'consulting'
        
        # Fallback: analyze HTML content
        content = str(website_data).lower()
        
        industry_keywords = {
            # Retail & Products
            'jewelry': ['jewelry', 'jewellery', 'koru', 'korut', 'koruliike', 'timantit', 'kultaseppä', 'hopeakoru', 'ring', 'necklace', 'bracelet', 'earring', 'sormus', 'kaulakoru', 'rannekoru', 'kultakoru'],
            'fashion': ['fashion', 'clothing', 'vaate', 'muoti', 'pukeutuminen', 'design', 'accessories', 'asusteet'],
            'ecommerce': ['shop', 'store', 'buy', 'cart', 'kauppa', 'osta', 'tuote', 'verkkokauppa', 'tilaa'],
            
            # Tech
            'saas': ['software', 'saas', 'platform', 'cloud', 'app', 'ohjelmisto', 'palvelu'],
            'technology': ['tech', 'digital', 'it', 'software', 'teknologia', 'digitaalinen', 'järjestelmä'],
            
            # Services
            'consulting': ['consulting', 'advisory', 'konsultointi', 'neuvonta', 'asiantuntija'],
            'marketing': ['marketing', 'agency', 'markkinointi', 'mainos', 'brändi', 'viestintä'],
            'finance': ['finance', 'bank', 'investment', 'rahoitus', 'pankki', 'sijoitus', 'vakuutus'],
            'healthcare': ['health', 'medical', 'clinic', 'terveys', 'lääkäri', 'klinikka', 'hyvinvointi'],
            'education': ['education', 'training', 'course', 'koulutus', 'kurssi', 'oppi', 'valmennus'],
            
            # Other
            'real_estate': ['real estate', 'property', 'kiinteistö', 'asunto', 'talo', 'vuokra'],
            'manufacturing': ['manufacturing', 'factory', 'production', 'tuotanto', 'tehdas', 'valmistus'],
            'hospitality': ['hotel', 'restaurant', 'ravintola', 'hotelli', 'majoitus', 'ruoka'],
            'automotive': ['car', 'auto', 'vehicle', 'ajoneuvo', 'autokauppa', 'huolto'],
        }
        
        scores = {}
        for industry, keywords in industry_keywords.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                scores[industry] = score
        
        if scores:
            detected = max(scores, key=scores.get)
            logger.info(f"[Scout] Industry detection scores: {scores}, selected: {detected}")
            return detected
        
        logger.info(f"[Scout] No industry detected, using 'general'")
        return 'general'
    
    async def _validate_competitors(
        self,
        competitor_urls: List[str],
        own_url: str
    ) -> List[str]:
        from main import get_domain_from_url, clean_url
        
        own_domain = get_domain_from_url(own_url)
        validated = []
        
        # Use same comprehensive skip list
        skip_domains = [
            'google.', 'facebook.', 'linkedin.', 'twitter.', 'instagram.',
            'youtube.', 'wikipedia.', 'amazon.', 'ebay.', 'reddit.',
            'yelp.', 'tripadvisor.', 'trustpilot.', 'glassdoor.',
            'fonecta.', 'finder.fi', 'kauppalehti.', 'hs.fi',
            'github.', 'stackoverflow.'
        ]
        
        for url in competitor_urls:
            try:
                cleaned = clean_url(url)
                domain = get_domain_from_url(cleaned)
                
                if domain == own_domain:
                    continue
                
                if any(skip in domain for skip in skip_domains):
                    continue
                
                validated.append(cleaned)
                
            except Exception:
                continue
        
        return validated
    
    async def _score_competitors(
        self,
        competitors: List[Dict[str, Any]],
        own_url: str,
        industry: str
    ) -> List[Dict[str, Any]]:
        from main import get_domain_from_url
        
        own_domain = get_domain_from_url(own_url)
        scored = []
        
        # Comprehensive list of non-competitor domains
        skip_domains = [
            # Social media
            'facebook.', 'linkedin.', 'twitter.', 'instagram.', 
            'tiktok.', 'pinterest.', 'snapchat.', 'threads.',
            # Search & tech giants
            'google.', 'bing.', 'yahoo.', 'baidu.',
            'apple.', 'microsoft.', 'amazon.', 'ebay.',
            # Content platforms
            'youtube.', 'vimeo.', 'reddit.', 'medium.', 'substack.',
            'wikipedia.', 'wikimedia.',
            # Review & directory sites
            'yelp.', 'tripadvisor.', 'trustpilot.', 'g2.', 'capterra.',
            'glassdoor.', 'indeed.', 'crunchbase.', 'zoominfo.',
            # Finnish directories
            'fonecta.', 'finder.fi', 'yritystele.', 'kauppalehti.',
            'hs.fi', 'is.fi', 'iltalehti.', 'mtv.fi', 'yle.fi',
            # News & media
            'bbc.', 'cnn.', 'nytimes.', 'theguardian.', 'forbes.',
            # Government
            'gov.', '.gov', 'europa.eu', 'prh.fi', 'vero.fi',
            # Developer/tech
            'github.', 'gitlab.', 'stackoverflow.', 'npmjs.',
        ]
        
        for comp in competitors:
            url = comp.get('url', '')
            domain = get_domain_from_url(url)
            
            if domain == own_domain:
                continue
            if any(skip in domain for skip in skip_domains):
                continue
            
            score = 50
            
            if own_domain.split('.')[-1] == domain.split('.')[-1]:
                score += 10
            
            snippet = comp.get('snippet', '').lower()
            if industry.lower() in snippet:
                score += 15
            
            title = comp.get('title', '').lower()
            if any(term in title for term in ['vs', 'alternative', 'competitor', 'vaihtoehto']):
                score += 20
            
            comp['relevance_score'] = min(score, 100)
            comp['name'] = comp.get('title', domain).split(' - ')[0].split(' | ')[0][:50]
            scored.append(comp)
        
        scored.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return scored
    
    async def _get_own_company_intel(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get company intelligence for the user's own company.
        
        Returns dict with:
        - name, business_id, city, industry
        - revenue, employees
        - ytj_url, kauppalehti_url
        """
        logger.info(f"[Scout] _get_own_company_intel called for: {url}")
        logger.info(f"[Scout] COMPANY_INTEL_AVAILABLE: {COMPANY_INTEL_AVAILABLE}")
        
        if not COMPANY_INTEL_AVAILABLE:
            logger.warning("[Scout] Company Intel module not available!")
            return None
        
        try:
            intel = CompanyIntel()
            
            # Extract domain
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            domain = domain.replace('www.', '')
            
            logger.info(f"[Scout] Searching company for domain: {domain}")
            
            # Try to get company profile from domain
            profile = await intel.get_company_from_domain(domain)
            
            if profile:
                self._emit_insight(
                    f"🏢 {profile.get('name', domain)} - Y-tunnus: {profile.get('business_id', 'N/A')}" 
                    if self._language == 'fi' else 
                    f"🏢 {profile.get('name', domain)} - Business ID: {profile.get('business_id', 'N/A')}",
                    priority=AgentPriority.LOW,
                    insight_type=InsightType.FINDING
                )
                
                return {
                    'name': profile.get('name'),
                    'business_id': profile.get('business_id'),
                    'street': profile.get('street'),
                    'postal_code': profile.get('postal_code'),
                    'city': profile.get('city'),
                    'country': profile.get('country', 'FI'),
                    'industry': profile.get('industry'),
                    'industry_code': profile.get('industry_code'),
                    'company_form': profile.get('company_form'),
                    'registration_date': profile.get('registration_date'),
                    'revenue': profile.get('revenue'),
                    'revenue_text': profile.get('revenue_text'),
                    'employees': profile.get('employees'),
                    'employees_text': profile.get('employees_text'),
                    'profit': profile.get('profit'),
                    'profit_text': profile.get('profit_text'),
                    'status': profile.get('status'),
                    'ytj_url': f"https://www.ytj.fi/fi/yritystiedot.html?businessId={profile.get('business_id')}" if profile.get('business_id') else None,
                    'kauppalehti_url': f"https://www.kauppalehti.fi/yritykset/yritys/{profile.get('business_id').replace('-', '')}" if profile.get('business_id') else None,
                    'source': profile.get('source'),
                    'fetched_at': profile.get('fetched_at')
                }
            
            await intel.close()
            return None
            
        except Exception as e:
            logger.warning(f"[Scout] Failed to get own company intel: {e}")
            return None
    
    async def _enrich_with_company_intel(
        self,
        competitor_urls: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Enrich competitor URLs with company intelligence from YTJ + Kauppalehti.
        
        Returns list of enriched competitor dicts with:
        - company_name (official)
        - business_id (Y-tunnus)
        - revenue
        - employees
        - founded_year
        - industry (TOL)
        - size_category
        """
        
        if not COMPANY_INTEL_AVAILABLE:
            logger.info("[Scout] Company Intel not available, skipping enrichment")
            return [{'url': url} for url in competitor_urls]
        
        self._emit_insight(
            "🏢 Haetaan yritystietoja..." if self._language == 'fi' else "🏢 Fetching company data...",
            priority=AgentPriority.LOW,
            insight_type=InsightType.FINDING
        )
        
        enriched = []
        intel = CompanyIntel()
        
        try:
            for i, url in enumerate(competitor_urls):
                competitor = {'url': url}
                
                try:
                    # Extract domain
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc or parsed.path.split('/')[0]
                    domain = domain.replace('www.', '')
                    
                    # Get company intel
                    profile = await intel.get_company_from_domain(domain)
                    
                    if profile:
                        competitor['company_name'] = profile.get('name')
                        competitor['business_id'] = profile.get('business_id')
                        competitor['revenue'] = profile.get('revenue')
                        competitor['employees'] = profile.get('employees')
                        competitor['founded_year'] = profile.get('founded_year')
                        competitor['industry'] = profile.get('industry')
                        competitor['size_category'] = profile.get('size_category')
                        competitor['company_intel'] = profile
                        
                        # Emit insight for significant findings
                        revenue = profile.get('revenue')
                        employees = profile.get('employees')
                        name = profile.get('name', domain)
                        
                        if revenue or employees:
                            revenue_str = f"€{revenue:,.0f}" if revenue else "N/A"
                            emp_str = f"{employees} hlö" if employees else "N/A"
                            
                            msg = f"📊 {name}: {revenue_str}, {emp_str}" if self._language == 'fi' else f"📊 {name}: {revenue_str}, {emp_str} employees"
                            
                            self._emit_insight(
                                msg,
                                priority=AgentPriority.MEDIUM,
                                insight_type=InsightType.FINDING,
                                data={'company': name, 'revenue': revenue, 'employees': employees}
                            )
                    
                except Exception as e:
                    logger.warning(f"[Scout] Company intel failed for {url}: {e}")
                
                enriched.append(competitor)
                
                # Update progress
                progress = 85 + (i / len(competitor_urls)) * 10  # 85-95%
                self._update_progress(int(progress), self._task("enriching_companies"))
            
            # Summary
            enriched_count = sum(1 for c in enriched if c.get('company_intel'))
            if enriched_count > 0:
                msg = f"✅ Yritystiedot löytyi {enriched_count}/{len(competitor_urls)} kilpailijalle" if self._language == 'fi' else f"✅ Company data found for {enriched_count}/{len(competitor_urls)} competitors"
                self._emit_insight(
                    msg,
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
            
        except Exception as e:
            logger.error(f"[Scout] Company enrichment failed: {e}")
        finally:
            await intel.close()
        
        return enriched
