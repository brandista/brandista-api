"""
Growth Engine 2.0 - Scout Agent
🔍 "The Explorer" - Finds and identifies competitors
Uses: multi_provider_search(), generate_smart_search_terms()
"""

import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .base_agent import BaseAgent
from .agent_types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class ScoutAgent(BaseAgent):
    """
    🔍 Scout Agent - Market Explorer
    
    Responsibilities:
    - Detect industry from website
    - Generate smart search terms
    - Find competitors via multi-provider search
    - Score and rank competitors by relevance
    """
    
    def __init__(self):
        super().__init__(
            agent_id="scout",
            name="Scout",
            role="Market Explorer",
            avatar="🔍",
            personality="Curious explorer who loves discovering new competitors"
        )
        self.dependencies = []  # Scout runs first
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Find and analyze competitors"""
        
        # Import main.py functions
        from main import (
            multi_provider_search,
            generate_smart_search_terms,
            get_domain_from_url,
            clean_url,
            get_website_content  # Fixed: was fetch_and_parse_website
        )
        
        self._emit_insight(
            "🔍 Hunting for your competitors...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # Get website data first
        self._update_progress(10, "Analyzing your website...")
        
        try:
            html_content, used_spa = await get_website_content(context.url)
            
            # Parse basic info from HTML
            website_data = {'html': html_content, 'used_spa': used_spa}
            if html_content:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extract title
                title_tag = soup.find('title')
                website_data['title'] = title_tag.get_text(strip=True) if title_tag else ''
                
                # Extract meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                website_data['meta_description'] = meta_desc.get('content', '') if meta_desc else ''
                
                # Extract company name from various sources
                og_site = soup.find('meta', attrs={'property': 'og:site_name'})
                if og_site:
                    website_data['company'] = og_site.get('content', '')
                else:
                    # Try to extract from title or domain
                    website_data['company'] = get_domain_from_url(context.url).replace('www.', '').split('.')[0].capitalize()
            
            company_name = website_data.get('company', 'Unknown')
            
            self._emit_insight(
                f"Got it — analyzing {company_name}",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING,
                data={'company': company_name}
            )
        except Exception as e:
            logger.error(f"[Scout] Website fetch failed: {e}")
            website_data = {}
            company_name = "Unknown"
        
        self._update_progress(20, "Detecting industry...")
        
        # Detect industry
        industry = await self._detect_industry(
            context.url, 
            website_data, 
            context.industry
        )
        
        self._emit_insight(
            f"📊 Industry detected: {industry}",
            priority=AgentPriority.LOW,
            insight_type=InsightType.FINDING,
            data={'industry': industry}
        )
        
        # If competitors provided, use those
        if context.competitor_urls:
            self._update_progress(90, "Using provided competitors...")
            
            self._emit_insight(
                f"✅ {len(context.competitor_urls)} competitors provided — skipping search",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
            
            return {
                'company': company_name,
                'industry': industry,
                'competitor_urls': context.competitor_urls,
                'competitor_count': len(context.competitor_urls),
                'discovery_method': 'user_provided',
                'website_data': website_data
            }
        
        # Generate search terms
        self._update_progress(30, "Generating search strategy...")
        
        try:
            search_terms = generate_smart_search_terms(
                industry=industry,
                country_code=context.country_code,
                custom_terms=None
            )
            
            self._emit_insight(
                f"🎯 Search strategy: {len(search_terms)} queries planned",
                priority=AgentPriority.LOW,
                insight_type=InsightType.FINDING
            )
        except Exception as e:
            logger.error(f"[Scout] Search term generation failed: {e}")
            search_terms = [f"top {industry} companies"]
        
        self._update_progress(40, "Searching multiple providers...")
        
        # Multi-provider search
        try:
            all_results = await multi_provider_search(
                search_terms=search_terms,
                num_results=7,
                country_code=context.country_code
            )
            
            self._emit_insight(
                f"🌐 Found {len(all_results)} potential matches",
                priority=AgentPriority.LOW,
                insight_type=InsightType.FINDING
            )
        except Exception as e:
            logger.error(f"[Scout] Multi-provider search failed: {e}")
            all_results = []
        
        self._update_progress(60, "Filtering and scoring...")
        
        # Filter and score competitors
        own_domain = get_domain_from_url(context.url)
        scored_competitors = []
        
        for url in all_results:
            try:
                domain = get_domain_from_url(url)
                
                # Skip own domain
                if own_domain.lower() in domain.lower():
                    continue
                
                # Skip non-relevant domains
                if self._is_non_relevant_domain(domain):
                    continue
                
                # Calculate relevance score
                relevance = self._calculate_relevance(url, industry, website_data)
                
                scored_competitors.append({
                    'url': clean_url(url),
                    'domain': domain,
                    'relevance_score': relevance
                })
                
            except Exception as e:
                logger.debug(f"[Scout] Skipping URL {url}: {e}")
                continue
        
        # Sort by relevance and deduplicate
        scored_competitors.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        # Dedupe by domain
        seen_domains = set()
        unique_competitors = []
        for comp in scored_competitors:
            base_domain = comp['domain'].replace('www.', '').lower()
            if base_domain not in seen_domains:
                seen_domains.add(base_domain)
                unique_competitors.append(comp)
        
        # Take top 5
        top_competitors = unique_competitors[:5]
        competitor_urls = [c['url'] for c in top_competitors]
        
        self._update_progress(90, "Discovery complete!")
        
        if top_competitors:
            top_match = top_competitors[0]
            self._emit_insight(
                f"🎯 Found {len(top_competitors)} solid competitors! "
                f"Top match: {top_match['domain']} ({top_match['relevance_score']}% relevance)",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'competitors': top_competitors}
            )
        else:
            self._emit_insight(
                "⚠️ No competitors found — try providing URLs manually",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        
        return {
            'company': company_name,
            'industry': industry,
            'competitor_urls': competitor_urls,
            'competitor_count': len(competitor_urls),
            'discovery_method': 'auto_discovered',
            'website_data': website_data,
            'all_candidates': top_competitors
        }
    
    async def _detect_industry(
        self, 
        url: str, 
        website_data: Dict[str, Any],
        provided_industry: Optional[str] = None
    ) -> str:
        """Detect industry from website content"""
        if provided_industry:
            return provided_industry
        
        # Try to detect from website data
        title = website_data.get('title', '').lower()
        description = website_data.get('meta_description', '').lower()
        content = f"{title} {description}"
        
        # Simple keyword matching for common industries
        industry_keywords = {
            'software': ['software', 'saas', 'app', 'platform', 'tech'],
            'marketing': ['marketing', 'agency', 'advertising', 'digital', 'brand'],
            'ecommerce': ['shop', 'store', 'ecommerce', 'buy', 'products'],
            'consulting': ['consulting', 'advisory', 'strategy', 'solutions'],
            'finance': ['finance', 'banking', 'investment', 'fintech', 'payments'],
            'healthcare': ['health', 'medical', 'clinic', 'care', 'wellness'],
            'education': ['education', 'learning', 'training', 'courses', 'academy'],
            'real estate': ['real estate', 'property', 'homes', 'rentals'],
            'manufacturing': ['manufacturing', 'industrial', 'factory', 'production'],
            'hospitality': ['hotel', 'restaurant', 'travel', 'tourism', 'booking'],
        }
        
        for industry, keywords in industry_keywords.items():
            if any(kw in content for kw in keywords):
                return industry
        
        return 'general business'
    
    def _is_non_relevant_domain(self, domain: str) -> bool:
        """Check if domain is a non-relevant platform"""
        non_relevant = [
            'facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com',
            'youtube.com', 'tiktok.com', 'pinterest.com',
            'wikipedia.org', 'reddit.com', 'medium.com',
            'google.com', 'bing.com', 'yahoo.com',
            'amazon.com', 'ebay.com', 'alibaba.com',
            'github.com', 'stackoverflow.com',
            'yelp.com', 'trustpilot.com', 'glassdoor.com'
        ]
        
        domain_lower = domain.lower()
        return any(nr in domain_lower for nr in non_relevant)
    
    def _calculate_relevance(
        self, 
        url: str, 
        industry: str, 
        website_data: Dict[str, Any]
    ) -> int:
        """Calculate relevance score 0-100"""
        score = 50  # Base score
        
        url_lower = url.lower()
        industry_lower = industry.lower()
        
        # Industry in URL/domain
        if industry_lower.replace(' ', '') in url_lower:
            score += 20
        
        # TLD matching (.fi for Finnish companies)
        if '.fi' in url_lower:
            score += 10
        
        # Business-like TLD
        if any(tld in url_lower for tld in ['.com', '.io', '.co', '.fi', '.eu']):
            score += 5
        
        # Penalize very long URLs (usually not homepages)
        if len(url) > 100:
            score -= 15
        
        # Penalize URLs with many parameters
        if url.count('?') > 0 or url.count('&') > 1:
            score -= 10
        
        return max(0, min(100, score))
