"""
Growth Engine 2.0 - Scout Agent
🔍 "The Market Explorer" - Löytää kilpailijat ja kartoittaa markkinan
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

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
        # DEBUG: Commented out - may crash during import before logger is configured
        # logger.info(f"[Scout] *** ScoutAgent initialized, COMPANY_INTEL_AVAILABLE={COMPANY_INTEL_AVAILABLE} ***")
    
    def _task(self, key: str) -> str:
        """Get task text in current language"""
        return SCOUT_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        # DEBUG: Log BEFORE any imports to catch import errors
        logger.info(f"[Scout] ========== SCOUT AGENT STARTING ==========")
        logger.info(f"[Scout] URL: {context.url}")
        logger.info(f"[Scout] COMPANY_INTEL_AVAILABLE at start: {COMPANY_INTEL_AVAILABLE}")
        
        try:
            from main import (
                get_website_content,
                multi_provider_search,
                generate_smart_search_terms,
                clean_url,
                get_domain_from_url
            )
            logger.info(f"[Scout] ✅ Main imports successful")
        except Exception as e:
            logger.error(f"[Scout] ❌ IMPORT FAILED: {e}")
            raise
        
        self._update_progress(15, self._task("analyzing_company"))
        
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
        
        # 2. Tunnista toimiala
        industry = await self._detect_industry(context.url, website_data, context.industry_context)
        
        self._emit_insight(
            self._t("scout.industry", industry=industry),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'industry': industry}
        )
        
        # 3. Jos kilpailijat jo annettu, validoi ne
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
            
            # Get your own company intel
            your_company_intel = await self._get_own_company_intel(context.url)
            
            return {
                'company': company_name,
                'industry': industry,
                'competitor_urls': validated_competitors,
                'competitor_count': len(validated_competitors),
                'discovery_method': 'user_provided',
                'website_data': website_data,
                'competitors_enriched': enriched_competitors,
                'your_company_intel': your_company_intel
            }
        
        # 4. Etsi kilpailijat automaattisesti
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
            
            # Get your own company intel
            your_company_intel = await self._get_own_company_intel(context.url)
            
            self._update_progress(95, self._task("finalizing"))
            
            return {
                'company': company_name,
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
                'industry': industry,
                'competitor_urls': [],
                'competitor_count': 0,
                'discovery_method': 'failed',
                'website_data': website_data,
                'error': str(e)
            }
    
    async def _detect_industry(
        self, 
        url: str, 
        website_data: Dict[str, Any],
        provided_industry: Optional[str] = None
    ) -> str:
        if provided_industry:
            return provided_industry
        
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
        
        for url in competitor_urls:
            try:
                cleaned = clean_url(url)
                domain = get_domain_from_url(cleaned)
                
                if domain == own_domain:
                    continue
                
                skip_domains = ['google.', 'facebook.', 'linkedin.', 'twitter.', 'wikipedia.']
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
        
        # Domains to always skip
        skip_domains = [
            'google.', 'facebook.', 'linkedin.', 'twitter.', 
            'wikipedia.', 'youtube.', 'instagram.', 'tiktok.',
            'amazon.', 'ebay.', 'reddit.', 'pinterest.',
            'yelp.', 'tripadvisor.', 'trustpilot.', 'github.',
            'medium.', 'wordpress.com', 'blogspot.', 'tumblr.'
        ]
        
        # Industry-specific keywords for better matching
        industry_keywords = {
            'jewelry': ['koru', 'korut', 'jewelry', 'jewellery', 'kulta', 'gold', 'hopea', 'silver', 'timantit', 'diamond', 'kello', 'watch', 'sormus', 'ring', 'kaulakoru', 'necklace'],
            'fashion': ['vaate', 'muoti', 'fashion', 'clothing', 'pukeutuminen', 'style'],
            'ecommerce': ['verkkokauppa', 'shop', 'store', 'kauppa', 'myynti'],
            'technology': ['tech', 'software', 'ohjelmisto', 'saas', 'app'],
            'real_estate': ['kiinteistö', 'asunto', 'real estate', 'housing'],
        }
        
        keywords = industry_keywords.get(industry.lower(), [industry.lower()])
        
        for comp in competitors:
            url = comp.get('url', '')
            domain = get_domain_from_url(url)
            
            # Skip own domain
            if domain == own_domain:
                continue
            
            # Skip known non-competitor domains
            if any(skip in domain.lower() for skip in skip_domains):
                continue
            
            # Skip personal blogs/portfolios (common patterns)
            if any(pattern in domain.lower() for pattern in ['blog', 'portfolio', 'personal', '.blogspot.', '.wordpress.']):
                continue
            
            score = 50  # Base score
            
            # Same TLD bonus (e.g., both .fi)
            if own_domain.split('.')[-1] == domain.split('.')[-1]:
                score += 10
            
            # Industry keyword matching in snippet
            snippet = comp.get('snippet', '').lower()
            keyword_matches = sum(1 for kw in keywords if kw in snippet)
            score += min(keyword_matches * 10, 30)  # Max 30 points from keywords
            
            # Industry keyword in title
            title = comp.get('title', '').lower()
            title_keyword_matches = sum(1 for kw in keywords if kw in title)
            score += min(title_keyword_matches * 8, 24)  # Max 24 points
            
            # Industry keyword in domain name
            domain_lower = domain.lower()
            if any(kw in domain_lower for kw in keywords):
                score += 15
            
            # Commercial indicators
            if any(term in title or term in snippet for term in ['oy', 'ab', 'ltd', 'inc', 'gmbh', 'yritys', 'company']):
                score += 10
            
            # E-commerce indicators (good for retail competitors)
            if any(term in snippet for term in ['verkkokauppa', 'osta', 'buy', 'shop', 'tilaa', 'order', 'hinta', 'price']):
                score += 8
            
            # Penalize if looks like a personal site
            if any(term in domain_lower for term in ['hanna', 'matti', 'personal', 'portfolio', 'blog']):
                score -= 20
            
            # Penalize very generic domains
            if len(domain.split('.')[0]) < 4:
                score -= 10
            
            # Alternative/competitor mention bonus
            if any(term in title for term in ['vs', 'alternative', 'competitor', 'vaihtoehto', 'kilpailija']):
                score += 20
            
            # Only include if score is decent
            if score >= 40:
                comp['relevance_score'] = min(score, 100)
                comp['name'] = comp.get('title', domain).split(' - ')[0].split(' | ')[0][:50]
                scored.append(comp)
            else:
                logger.debug(f"[Scout] Filtered out low-relevance competitor: {domain} (score: {score})")
        
        scored.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        logger.info(f"[Scout] Scored {len(scored)} relevant competitors from {len(competitors)} candidates")
        
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
