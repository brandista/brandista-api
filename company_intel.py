"""
Growth Engine 2.0 - Company Intelligence Module
Due Diligence data from official Finnish sources

Sources:
- YTJ (PRH/Vero) - Official company registry, free API
- Kauppalehti - Financial data (revenue, employees, profit)

Usage:
    from company_intel import CompanyIntel
    
    intel = CompanyIntel()
    
    # Search by name
    companies = await intel.search_company("Valio")
    
    # Get full profile by Y-tunnus
    profile = await intel.get_company_profile("0116754-4")
    
    # Get from domain (extracts company name, searches)
    profile = await intel.get_company_from_domain("valio.fi")
"""

import logging
import re
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse, quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CompanyIntel:
    """
    Finnish Company Intelligence
    Combines YTJ (official registry) + Kauppalehti (financial data)
    """
    
    # PRH/YTJ Open Data API - V3 (updated August 2024)
    # Note: V3 uses query parameters for businessId
    YTJ_API_BASE = "https://avoindata.prh.fi/opendata-ytj-api/v3/companies"
    
    # Kauppalehti company pages
    KAUPPALEHTI_BASE = "https://www.kauppalehti.fi/yritykset/yritys"
    
    # Finder.fi
    FINDER_SEARCH = "https://www.finder.fi/search?what="
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            follow_redirects=True
        )
        self._last_domain_name = None
    
    async def close(self):
        await self.client.aclose()
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    async def search_company(self, name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search companies by name using YTJ API.
        
        Returns list of matching companies with basic info.
        """
        try:
            results = await self._ytj_search(name, max_results)
            return results
        except Exception as e:
            logger.error(f"[CompanyIntel] Search failed for '{name}': {e}")
            return []
    
    async def get_company_profile(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full company profile by Y-tunnus (business ID).
        
        Combines data from YTJ + Kauppalehti.
        """
        # Validate and format Y-tunnus
        business_id = self._format_business_id(business_id)
        if not business_id:
            logger.warning(f"[CompanyIntel] Invalid business ID format")
            return None
        
        try:
            # Fetch from sources
            ytj_task = self._ytj_get_company(business_id)
            kl_task = self._kauppalehti_get_company(business_id)
            finder_task = self._finder_get_company(business_id)
            
            ytj_data, kl_data, finder_data = await asyncio.gather(ytj_task, kl_task, finder_task, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(ytj_data, Exception):
                logger.warning(f"[CompanyIntel] YTJ fetch failed: {ytj_data}")
                ytj_data = None
            if isinstance(kl_data, Exception):
                logger.warning(f"[CompanyIntel] Kauppalehti fetch failed: {kl_data}")
                kl_data = None
            if isinstance(finder_data, Exception):
                logger.warning(f"[CompanyIntel] Finder fetch failed: {finder_data}")
                finder_data = None
            
            if not ytj_data and not kl_data and not finder_data:
                # One last try: if we have a name (from domain extraction), search by name
                if not getattr(self, '_last_domain_name', None):
                    return None
                    
                logger.info(f"[CompanyIntel] ID lookup failed for {business_id}, trying to find by name: {self._last_domain_name}")
                search_results = await self.search_companies(self._last_domain_name)
                if search_results:
                    # Take the first relative match and try fetching its ID
                    # (Prevent infinite recursion by not name-searching again)
                    best_match = search_results[0]
                    new_id = best_match.get('business_id')
                    if new_id and new_id != business_id:
                        return await self.get_company_profile(new_id)
                return None
            
            # Merge data
            profile = self._merge_company_data(ytj_data, kl_data, finder_data, business_id)
            
            logger.info(f"[CompanyIntel] ✅ Profile fetched: {profile.get('name', business_id)}")
            return profile
            
        except Exception as e:
            logger.error(f"[CompanyIntel] Profile fetch failed for {business_id}: {e}")
            return None
    
    def _find_best_company_match(self, results: List[Dict], search_term: str) -> Optional[Dict]:
        """
        Find the best company match from search results.
        Filters out housing cooperatives and prioritizes domain name matches.
        
        Args:
            results: List of company results from YTJ search
            search_term: The domain/company name being searched for
            
        Returns:
            Best matching company dict or None
        """
        if not results:
            return None
        
        search_lower = search_term.lower()
        
        # Housing cooperative patterns to skip
        skip_patterns = [
            'asunto oy', 'asunto-oy', 'as oy', 'as. oy', 
            'bostads', 'kiinteistö oy', 'kiinteistö ab',
            'asunto-osake', 'housing'
        ]
        
        # First pass: find companies with search term in name (excluding housing)
        priority_matches = []
        regular_matches = []
        
        for company in results:
            company_name = (company.get('name') or '').lower()
            
            # Skip dissolved companies (status "4" or endDate exists)
            # tradeRegisterStatus is a string in some versions, check both
            tr_status = str(company.get('tradeRegisterStatus', ''))
            if tr_status == '4' or company.get('endDate'):
                logger.info(f"[CompanyIntel] Skipping dissolved company: {company.get('name')}")
                continue
            
            # Skip housing cooperatives
            if any(skip in company_name for skip in skip_patterns):
                logger.info(f"[CompanyIntel] Skipping housing cooperative: {company.get('name')}")
                continue
            
            # Check if search term appears in company name
            if search_lower in company_name:
                # Higher priority if it's at the start of the name
                if company_name.startswith(search_lower):
                    priority_matches.insert(0, company)
                else:
                    priority_matches.append(company)
            else:
                regular_matches.append(company)
        
        # Return best priority match if found
        if priority_matches:
            best = priority_matches[0]
            logger.info(f"[CompanyIntel] Best match found: {best.get('name')}")
            return best
        
        # Return first regular match if no priority matches
        if regular_matches:
            best = regular_matches[0]
            logger.info(f"[CompanyIntel] Fallback match: {best.get('name')}")
            return best
        
        return None
    
    async def get_company_from_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Try to find company info from a domain name.
        
        1. Extracts likely company name from domain
        2. Searches YTJ
        3. Returns best match with full profile (prioritizes real companies over housing cooperatives)
        """
        logger.info(f"[CompanyIntel] Looking up company for domain: {domain}")
        
        # Clean domain
        domain = domain.lower().strip()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        domain = domain.split('/')[0]  # Remove path
        
        # Extract company name from domain
        # valio.fi -> Valio
        # verkkokauppa.com -> Verkkokauppa
        name_part = domain.split('.')[0]
        self._last_domain_name = name_part
        
        logger.info(f"[CompanyIntel] Extracted name from domain: '{name_part}'")
        
        # Try search with Oy suffix first (more likely to find the real company)
        results = await self.search_company(f"{name_part} oy", max_results=10)
        
        # If Oy search returned results, filter and check for good match
        best_match = self._find_best_company_match(results, name_part) if results else None
        
        # If no good match with Oy, try industry-specific suffixes
        if not best_match:
            for suffix in [' koru', ' design', ' group', ' ab']:
                suffix_results = await self.search_company(f"{name_part}{suffix}", max_results=5)
                if suffix_results:
                    best_match = self._find_best_company_match(suffix_results, name_part)
                    if best_match:
                        logger.info(f"[CompanyIntel] Found with suffix '{suffix}': {best_match.get('name')}")
                        break
        
        # If still no match, try plain name search but filter aggressively
        if not best_match:
            results = await self.search_company(name_part, max_results=20)
            best_match = self._find_best_company_match(results, name_part) if results else None
        
        # Try removing common domain suffixes
        if not best_match:
            for suffix in ['oy', 'ab', 'group', 'finland', 'fi']:
                if name_part.endswith(suffix):
                    clean_name = name_part[:-len(suffix)]
                    results = await self.search_company(clean_name, max_results=10)
                    best_match = self._find_best_company_match(results, clean_name) if results else None
                    if best_match:
                        break
        
        if not best_match:
            logger.info(f"[CompanyIntel] No suitable company found for domain: {domain}")
            return None
        
        business_id = best_match.get('business_id')
        
        if business_id:
            return await self.get_company_profile(business_id)
        
        return best_match
    
    async def enrich_competitor(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a competitor dict with company intelligence.
        
        Input: {'url': 'https://valio.fi', 'score': 80, ...}
        Output: Same dict with added 'company_intel' field
        """
        url = competitor.get('url', '')
        if not url:
            return competitor
        
        # Extract domain
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            domain = domain.replace('www.', '')
        except:
            return competitor
        
        # Get company intel
        intel = await self.get_company_from_domain(domain)
        
        if intel:
            competitor['company_intel'] = intel
            
            # Add key fields to top level for easy access
            competitor['company_name'] = intel.get('name')
            competitor['business_id'] = intel.get('business_id')
            competitor['revenue'] = intel.get('revenue')
            competitor['employees'] = intel.get('employees')
            competitor['founded_year'] = intel.get('founded_year')
        
        return competitor
    
    # =========================================================================
    # YTJ API (PRH Open Data)
    # =========================================================================
    
    async def _ytj_search(self, name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search YTJ by company name using V3 API"""
        
        logger.info(f"[CompanyIntel] Searching YTJ V3 for: '{name}'")
        
        url = f"{self.YTJ_API_BASE}"
        params = {
            'name': name
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        # V3 API returns 'companies' array instead of 'results'
        results = data.get('companies', data.get('results', []))
        
        logger.info(f"[CompanyIntel] YTJ V3 returned {len(results)} results for '{name}'")
        
        # Debug: log first result structure
        if results:
            first = results[0]
            logger.info(f"[CompanyIntel] V3 response keys: {list(first.keys())}")
            logger.info(f"[CompanyIntel] V3 businessId: {first.get('businessId')}")
            logger.info(f"[CompanyIntel] V3 names: {first.get('names', [])[:2]}")
        
        companies = []
        for item in results[:max_results]:
            company = self._parse_ytj_result(item)
            if company:
                companies.append(company)
                logger.info(f"[CompanyIntel] Found: {company.get('name')} ({company.get('business_id')})")
        
        return companies
    
    async def _ytj_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Get single company from YTJ V3 by business ID"""
        
        # V3 API uses businessId parameter instead of path
        url = f"{self.YTJ_API_BASE}"
        params = {'businessId': business_id}
        
        try:
            logger.info(f"[CompanyIntel] Fetching YTJ V3: {url} (ID: {business_id})")
            response = await self.client.get(url, params=params)
            logger.info(f"[CompanyIntel] YTJ V3 Status: {response.status_code}")
            
            results = []
            if response.status_code == 200:
                data = response.json()
                # V3 returns 'companies', V1 returns 'results'
                results = data.get('companies', data.get('results', []))
            
            # If V3 fails or returns no results, try V1 fallback (more stable for ID lookups)
            if not results:
                logger.info(f"[CompanyIntel] YTJ V3 empty or failed, trying V1 fallback...")
                # Try without dash first in V1
                bid_clean = business_id.replace('-', '')
                url_v1 = f"https://avoindata.prh.fi/opendata/bis/v1/{bid_clean}"
                try:
                    response_v1 = await self.client.get(url_v1)
                    if response_v1.status_code == 200:
                        data_v1 = response_v1.json()
                        results = data_v1.get('results', [])
                    elif response_v1.status_code == 404:
                        # Try with dash just in case
                        url_v1_dash = f"https://avoindata.prh.fi/opendata/bis/v1/{business_id}"
                        response_v1 = await self.client.get(url_v1_dash)
                        if response_v1.status_code == 200:
                            data_v1 = response_v1.json()
                            results = data_v1.get('results', [])
                except Exception as e:
                    logger.warning(f"[CompanyIntel] V1 fallback failed: {e}")
            
            if not results:
                logger.info(f"[CompanyIntel] No results found in YTJ for {business_id}")
                return None
            
            # V3 and V1 have slightly different item structures, but our parser handles them
            return self._parse_ytj_result(results[0])
            
        except Exception as e:
            logger.error(f"[CompanyIntel] YTJ fetch failed for {business_id}: {e}")
            return None
    
    def _parse_ytj_result(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse YTJ V3 API result into clean format"""
        
        try:
            # Basic info - V3 'businessId' is a dict with 'value' key, not a string!
            business_id_raw = item.get('businessId', '')
            if isinstance(business_id_raw, dict):
                business_id = business_id_raw.get('value', '')
            else:
                business_id = business_id_raw
            
            # Get names - V3 uses 'names' array with 'name' and 'type' fields
            names = item.get('names', [])
            name = ''
            for n in names:
                # V3: type is string like "0" for current name
                n_type = n.get('type', '')
                if n_type == '0' or not n.get('endDate'):  # Current/active name
                    name = n.get('name', '')
                    break
            if not name and names:
                name = names[0].get('name', '')
            
            # Registration date - V3 uses 'registrationDate' in root
            reg_date = item.get('registrationDate', '')
            founded_year = None
            if reg_date:
                try:
                    founded_year = int(reg_date[:4])
                except:
                    pass
            
            # Address - V3 uses 'addresses' array
            addresses = item.get('addresses', [])
            address = None
            city = None
            postal_code = None
            for addr in addresses:
                # V3: type is string, "1" = street address, "2" = postal
                addr_type = str(addr.get('type', ''))
                if addr_type == '1' or not address:  # Street address preferred
                    address = addr.get('street', '')
                    city = addr.get('city', '')
                    postal_code = addr.get('postCode', '')
                    if addr_type == '1':
                        break
            
            # Business line (TOL code) - V3 uses 'businessLines'
            business_lines = item.get('businessLines', [])
            industry = None
            industry_code = None
            for bl in business_lines:
                # Get descriptions for industry name
                descriptions = bl.get('descriptions', [])
                for desc in descriptions:
                    if desc.get('language') == 'FI':
                        industry = desc.get('description', '')
                        break
                if not industry and descriptions:
                    industry = descriptions[0].get('description', '')
                industry_code = bl.get('code', '')
                if not bl.get('endDate'):  # Current business line
                    break
            
            # Company form - V3 uses 'companyForms'
            company_forms = item.get('companyForms', [])
            company_form = None
            for cf in company_forms:
                # V3: name is in 'descriptions' array
                descriptions = cf.get('descriptions', [])
                for desc in descriptions:
                    if desc.get('language') == 'FI':
                        company_form = desc.get('description', '')
                        break
                if not company_form and descriptions:
                    company_form = descriptions[0].get('description', '')
                if company_form:
                    break
            
            # Status - V3 uses 'companySituations' for liquidation etc.
            status = 'active'
            situations = item.get('companySituations', [])
            if situations:
                status = 'liquidation'
            
            # Trade register status - V3 has 'tradeRegisterStatus'
            tr_status = item.get('tradeRegisterStatus', '')
            if tr_status and 'Poistettu' in tr_status:
                status = 'dissolved'
            
            return {
                'business_id': business_id,
                'name': name,
                'founded_year': founded_year,
                'registration_date': reg_date,
                'address': address,
                'city': city,
                'postal_code': postal_code,
                'industry': industry,
                'industry_code': industry_code,
                'company_form': company_form,
                'status': status,
                'source': 'ytj'
            }
            
        except Exception as e:
            logger.error(f"[CompanyIntel] YTJ parse error: {e}")
            return None
    
    # =========================================================================
    # KAUPPALEHTI (Web Scraping)
    # =========================================================================
    
    async def _kauppalehti_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Scrape company financial data from Kauppalehti.
        
        Note: This is scraping, may break if they change their HTML.
        """
        
        # Format: https://www.kauppalehti.fi/yritykset/yritys/01167544
        # Y-tunnus without dash
        clean_id = business_id.replace('-', '')
        url = f"{self.KAUPPALEHTI_BASE}/{clean_id}"
        
        try:
            logger.info(f"[CompanyIntel] Fetching Kauppalehti: {url}")
            response = await self.client.get(url)
            logger.info(f"[CompanyIntel] Kauppalehti Status: {response.status_code}")
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            
            html = response.text
            return self._parse_kauppalehti_html(html, business_id)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def _parse_kauppalehti_html(self, html: str, business_id: str) -> Optional[Dict[str, Any]]:
        """Parse Kauppalehti company page HTML"""
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            data = {
                'business_id': business_id,
                'source': 'kauppalehti'
            }
            
            # Company name (h1)
            h1 = soup.find('h1')
            if h1:
                data['name'] = h1.get_text(strip=True)
            
            # Look for key metrics in the page
            # Kauppalehti uses various div structures, try common patterns
            
            # Method 1: Look for labeled values
            # Updated labels to include more variations
            labels = [
                'Liikevaihto', 'Liikevaihto (euroa)', 'Liikevaihto (euroa) ', 'Liikevaihto (EUR)', 'Liikevaihto (1000 EUR)',
                'Henkilöstö', 'Henkilöstömäärä', 'Tulos', 'Liikevaihtoluokka', 'Tilikauden tulos'
            ]
            
            for label_text in labels:
                # Use regex for flexible matching (handles cases like "Liikevaihto (€)")
                label = soup.find(string=re.compile(rf'^{re.escape(label_text)}\s*$', re.IGNORECASE))
                if not label:
                    # Try partial match if exact fails
                    label = soup.find(string=re.compile(re.escape(label_text), re.IGNORECASE))
                    
                if label:
                    parent = label.find_parent(['div', 'td', 'tr', 'li', 'dt', 'span', 'th'])
                    if parent:
                        # Try to find the value nearby - search in siblings or children of parent
                        value_text = None
                        
                        # 1. Check next sibling (td/span/div)
                        next_sib = parent.find_next(['span', 'div', 'td', 'dd', 'b', 'strong', 'p'])
                        if next_sib:
                            value_text = next_sib.get_text(strip=True)
                        
                        # 2. If parent is row, check cells
                        if not value_text and parent.name in ['tr', 'th', 'td']:
                            row = parent if parent.name == 'tr' else parent.find_parent('tr')
                            if row:
                                cells = row.find_all(['td', 'th'])
                                if len(cells) >= 2:
                                    value_text = cells[-1].get_text(strip=True)
                        
                        if value_text:
                            parsed = self._parse_financial_value(value_text)
                            
                            if 'Liikevaihto' in label_text:
                                if parsed.get('value') and not data.get('revenue'):
                                    data['revenue'] = parsed['value']
                                    data['revenue_text'] = value_text
                            elif 'Henkilöstö' in label_text:
                                if parsed.get('value') and not data.get('employees'):
                                    data['employees'] = int(parsed['value'])
                                    data['employees_text'] = value_text
                            elif 'Tulos' in label_text:
                                if parsed.get('value') and not data.get('profit'):
                                    data['profit'] = parsed['value']
                                    data['profit_text'] = value_text
            
            # Method 2: Look for structured data (JSON-LD)
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    import json
                    json_data = json.loads(script.string)
                    if isinstance(json_data, dict):
                        # Some sites wrap LD-JSON in a list
                        if json_data.get('@type') == 'Organization':
                            if 'numberOfEmployees' in json_data:
                                emp = json_data['numberOfEmployees']
                                if isinstance(emp, dict):
                                    data['employees'] = emp.get('value')
                                else:
                                    data['employees'] = emp
                except:
                    pass
            
            # Method 3: Look for common CSS classes and data attributes
            # Kauppalehti often uses specific data-testid or class names like "financials__row"
            revenue_elem = soup.select_one('[class*="revenue"], [class*="liikevaihto"], [data-testid*="revenue"]')
            if revenue_elem and not data.get('revenue'):
                parsed = self._parse_financial_value(revenue_elem.get_text())
                if parsed.get('value'):
                    data['revenue'] = parsed['value']
                    data['revenue_text'] = revenue_elem.get_text(strip=True)
            
            employees_elem = soup.select_one('[class*="employees"], [class*="henkilosto"], [data-testid*="employees"]')
            if employees_elem and not data.get('employees'):
                parsed = self._parse_financial_value(employees_elem.get_text())
                if parsed.get('value'):
                    data['employees'] = int(parsed['value'])
                    data['employees_text'] = employees_elem.get_text(strip=True)
            
            # Method 4: Specific table parsing for Kauppalehti's "Tunnusluvut" (Key figures)
            figures_section = soup.find(string=re.compile('Tunnusluvut', re.IGNORECASE))
            if figures_section:
                table = figures_section.find_parent(['div', 'section']).find('table') if figures_section.find_parent(['div', 'section']) else None
                if table:
                    for row in table.find_all('tr'):
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True).lower()
                            value_text = cells[1].get_text(strip=True)
                            parsed = self._parse_financial_value(value_text)
                            
                            if 'liikevaihto' in label and not data.get('revenue'):
                                data['revenue'] = parsed.get('value')
                                data['revenue_text'] = value_text
                            elif 'tulos' in label and not data.get('profit'):
                                data['profit'] = parsed.get('value')
                                data['profit_text'] = value_text

            # Try to extract financial history from tables
            tables = soup.find_all('table')
            for table in tables:
                headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
                if any(h in ['vuosi', 'year', 'liikevaihto', 'tulos'] for h in headers):
                    # This might be financial history table
                    rows = table.find_all('tr')
                    history = []
                    for row in rows[1:]:  # Skip header
                        cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                        if len(cells) >= 2:
                            history.append(cells)
                    if history:
                        data['financial_history'] = history[:5]  # Last 5 years
            
            # Method 5: Look for metadata (meta description often contains basic financials)
            if not data.get('revenue'):
                meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
                if meta_desc:
                    desc_text = meta_desc.get('content', '')
                    # Look for pattern: "Liikevaihto 123,4 M€" or "Liikevaihto: 123 456"
                    pattern = re.search(r'Liikevaihto[:\s]+([\d\s,.]+)\s*([MK]€|EUR|EUROA|milj|e)', desc_text, re.IGNORECASE)
                    if not pattern:
                        # Try even simpler: "123,4 milj. euroa" near the start
                        pattern = re.search(r'([\d\s,.]+)\s*(M€|EUR|milj|euro)', desc_text, re.IGNORECASE)
                    
                    if pattern:
                        value_text = pattern.group(1)
                        unit_text = pattern.group(2) if len(pattern.groups()) > 1 else ""
                        full_text = value_text + " " + unit_text
                        parsed = self._parse_financial_value(full_text)
                        if parsed.get('value'):
                            data['revenue'] = parsed['value']
                            data['revenue_text'] = full_text
                            logger.info(f"[CompanyIntel] Extracted revenue from metadata pattern: {data['revenue']}")

            # Only return if we got some useful data
            if data.get('revenue') or data.get('employees') or data.get('name'):
                logger.info(f"[CompanyIntel] Scraped from Kauppalehti: {data.get('name')} - Revenue: {data.get('revenue')}")
                return data
            
            logger.warning(f"[CompanyIntel] Kauppalehti scrape failed to find key data for {business_id}")
            return None
            
        except Exception as e:
            logger.error(f"[CompanyIntel] Kauppalehti parse error: {e}")
            return None

    # =========================================================================
    # FINDER.FI (Web Scraping)
    # =========================================================================

    async def _finder_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Scrape company data from Finder.fi"""
        # Try both formats: with and without dash
        ids_to_try = [business_id, business_id.replace('-', '')]
        
        for bid in ids_to_try:
            url = f"{self.FINDER_SEARCH}{bid}"
            try:
                logger.info(f"[CompanyIntel] Fetching Finder: {url}")
                response = await self.client.get(url)
                logger.info(f"[CompanyIntel] Finder Status: {response.status_code}")
                
                if response.status_code == 202:
                    logger.info(f"[CompanyIntel] Finder returned 202 (Accepted), waiting 2s for redirect...")
                    await asyncio.sleep(2.0)
                    response = await self.client.get(url)
                    logger.info(f"[CompanyIntel] Finder Retry Status: {response.status_code}")
                
                if response.status_code == 200:
                    html = response.text
                    # Check if we actually found something
                    if "tuloksia" in html.lower() and "löydetty" in html.lower() and "0" in html:
                        continue # No results
                        
                    data = self._parse_finder_html(html, business_id)
                    if data:
                        return data
            except Exception as e:
                logger.error(f"[CompanyIntel] Finder fetch failed for {bid}: {e}")
                
        return None

    def _parse_finder_html(self, html: str, business_id: str) -> Optional[Dict[str, Any]]:
        """Parse Finder.fi company page"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            data = {
                'business_id': business_id,
                'source': 'finder'
            }
            
            # Find name
            name_elem = soup.select_one('.Profile__Name, h1')
            if name_elem:
                data['name'] = name_elem.get_text(strip=True)
            
            # Financials table parsing
            financial_table = soup.select_one('.Financials__Table, table')
            if financial_table:
                rows = financial_table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value_text = cells[1].get_text(strip=True)
                        parsed = self._parse_financial_value(value_text)
                        
                        if 'liikevaihto' in label and not data.get('revenue'):
                            data['revenue'] = parsed.get('value')
                        elif 'tulos' in label and not data.get('profit'):
                            data['profit'] = parsed.get('value')
                        elif 'henkilöstö' in label and not data.get('employees'):
                            data['employees'] = parsed.get('value')

            if data.get('revenue') or data.get('employees') or data.get('name'):
                logger.info(f"[CompanyIntel] Scraped from Finder: {data.get('name')} - Revenue: {data.get('revenue')}")
                return data
            
            return None
        except Exception as e:
            logger.error(f"[CompanyIntel] Finder parse error: {e}")
            return None
    
    def _parse_financial_value(self, text: str) -> Dict[str, Any]:
        """
        Parse Finnish financial value text.
        
        Examples:
        - "12 500 000 €" -> {'value': 12500000, 'unit': 'EUR'}
        - "12,5 M€" -> {'value': 12500000, 'unit': 'EUR'}
        - "12.5 M€" -> {'value': 12500000, 'unit': 'EUR'}
        - "1 234" -> {'value': 1234}
        - "15 hlö" -> {'value': 15}
        - "1,2 milj. €" -> {'value': 1200000}
        """
        
        result = {'raw': text}
        
        if not text:
            return result
        
        # Clean and normalize
        text = text.strip().upper()
        
        # Remove currency symbols and common labels
        text = text.replace('€', '').replace('EUR', '').replace('HLÖ', '').replace('HENKILÖÄ', '')
        
        # Handle millions/thousands abbreviations
        multiplier = 1
        if 'MILJ' in text or 'M' in text:
            multiplier = 1_000_000
            # Remove M or MILJ but keep dots if they are decimals (handled later)
            text = re.sub(r'MILJ\.?|M\.?', '', text)
        elif 'K' in text or 'T€' in text or 'TEUR' in text or 'TUIHAN' in text:
            multiplier = 1_000
            text = text.replace('K', '').replace('T€', '').replace('TEUR', '').replace('TUIHAN', '')
        
        # Check if it's a range like "1-4"
        if '-' in text and not text.startswith('-'):
            parts = text.split('-')
            try:
                # Use the higher end of the range
                text = parts[1]
            except:
                pass

        # Remove all whitespace (thousand separators)
        # Finnish often uses non-breaking space (0xA0) or normal space
        text = text.replace('\xa0', '').replace(' ', '')
        
        # Replace comma with dot for float parsing (Finnish decimal)
        text = text.replace(',', '.')
        
        # Remove any other non-numeric characters except first dot and minus
        # (Handling cases like "1.2.345,67" where dots are thousand separators)
        if text.count('.') > 1:
            # If multiple dots, they are likely thousand separators
            text = text.replace('.', '')
        
        # Final cleanup for float parsing
        text = re.sub(r'[^\d.\-]', '', text)
        
        try:
            if not text:
                return result
                
            value = float(text) * multiplier
            # Convert to int if it's a whole number
            result['value'] = int(value) if value == int(value) else value
            logger.debug(f"[CompanyIntel] Parsed '{result['raw']}' to {result['value']}")
        except ValueError:
            logger.debug(f"[CompanyIntel] Failed to parse financial value: '{text}' (original: '{result['raw']}')")
            pass
        
        return result
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _format_business_id(self, business_id: str) -> Optional[str]:
        """
        Format and validate Finnish Y-tunnus.
        
        Valid formats: 1234567-8, 12345678
        """
        
        if not business_id:
            return None
        
        # Remove whitespace
        clean = business_id.strip().replace(' ', '')
        
        # Remove dash for validation
        digits = clean.replace('-', '')
        
        # Must be 8 digits
        if not re.match(r'^\d{8}$', digits):
            return None
        
        # Format with dash
        return f"{digits[:7]}-{digits[7]}"
    
    def _merge_company_data(
        self, 
        ytj_data: Optional[Dict], 
        kl_data: Optional[Dict],
        finder_data: Optional[Dict],
        business_id: str
    ) -> Dict[str, Any]:
        """Merge data from YTJ, Kauppalehti and Finder into unified profile"""
        
        profile = {
            'business_id': business_id,
            'fetched_at': datetime.now().isoformat(),
            'sources': []
        }
        
        # Start with YTJ data (official)
        if ytj_data:
            profile['sources'].append('ytj')
            profile.update({
                'name': ytj_data.get('name'),
                'founded_year': ytj_data.get('founded_year'),
                'registration_date': ytj_data.get('registration_date'),
                'address': ytj_data.get('address'),
                'city': ytj_data.get('city'),
                'postal_code': ytj_data.get('postal_code'),
                'industry': ytj_data.get('industry'),
                'industry_code': ytj_data.get('industry_code'),
                'company_form': ytj_data.get('company_form'),
                'status': ytj_data.get('status'),
            })
        
        # Enrich with Kauppalehti data (financial)
        if kl_data:
            profile['sources'].append('kauppalehti')
            
            # Only override name if YTJ didn't have it
            if not profile.get('name') and kl_data.get('name'):
                profile['name'] = kl_data['name']
            
            # Financial data (only from Kauppalehti)
            if kl_data.get('revenue'):
                profile['revenue'] = kl_data['revenue']
                profile['revenue_text'] = kl_data.get('revenue_text')
            
            if kl_data.get('employees'):
                profile['employees'] = kl_data['employees']
                profile['employees_text'] = kl_data.get('employees_text')
            
            if kl_data.get('profit'):
                profile['profit'] = kl_data['profit']
                profile['profit_text'] = kl_data.get('profit_text')
            
            if kl_data.get('financial_history'):
                profile['financial_history'] = kl_data['financial_history']
        
        # Enrich with Finder data (backup/additional financials)
        if finder_data:
            profile['sources'].append('finder')
            
            # Prefer Finder revenue if KL failed
            if not profile.get('revenue') and finder_data.get('revenue'):
                profile['revenue'] = finder_data['revenue']
                profile['revenue_source'] = 'finder'
                
            if not profile.get('employees') and finder_data.get('employees'):
                profile['employees'] = finder_data['employees']
                
            if not profile.get('profit') and finder_data.get('profit'):
                profile['profit'] = finder_data['profit']
        
        # Calculate company age
        if profile.get('founded_year'):
            profile['company_age_years'] = datetime.now().year - profile['founded_year']
        
        # Determine company size category
        employees = profile.get('employees')
        revenue = profile.get('revenue')
        
        if employees:
            if employees >= 250:
                profile['size_category'] = 'large'
            elif employees >= 50:
                profile['size_category'] = 'medium'
            elif employees >= 10:
                profile['size_category'] = 'small'
            else:
                profile['size_category'] = 'micro'
        elif revenue:
            if revenue >= 50_000_000:
                profile['size_category'] = 'large'
            elif revenue >= 10_000_000:
                profile['size_category'] = 'medium'
            elif revenue >= 2_000_000:
                profile['size_category'] = 'small'
            else:
                profile['size_category'] = 'micro'
        
        return profile


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_company_intel(business_id: str) -> Optional[Dict[str, Any]]:
    """Quick function to get company profile"""
    intel = CompanyIntel()
    try:
        return await intel.get_company_profile(business_id)
    finally:
        await intel.close()


async def search_companies(name: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Quick function to search companies"""
    intel = CompanyIntel()
    try:
        return await intel.search_company(name, max_results)
    finally:
        await intel.close()


async def enrich_competitors(competitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich a list of competitors with company intelligence.
    
    Usage in agent:
        competitors = await enrich_competitors(competitor_list)
    """
    intel = CompanyIntel()
    try:
        tasks = [intel.enrich_competitor(c.copy()) for c in competitors]
        return await asyncio.gather(*tasks)
    finally:
        await intel.close()


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    async def test():
        intel = CompanyIntel()
        
        print("🔍 Testing YTJ search...")
        results = await intel.search_company("Valio")
        print(f"Found {len(results)} results")
        for r in results[:3]:
            print(f"  - {r['name']} ({r['business_id']})")
        
        if results:
            print("\n📊 Testing full profile...")
            profile = await intel.get_company_profile(results[0]['business_id'])
            if profile:
                print(f"  Name: {profile.get('name')}")
                print(f"  Founded: {profile.get('founded_year')}")
                print(f"  Industry: {profile.get('industry')}")
                print(f"  Revenue: {profile.get('revenue')}")
                print(f"  Employees: {profile.get('employees')}")
                print(f"  Sources: {profile.get('sources')}")
        
        print("\n🌐 Testing domain lookup...")
        profile = await intel.get_company_from_domain("valio.fi")
        if profile:
            print(f"  Found: {profile.get('name')} ({profile.get('business_id')})")
        
        await intel.close()
    
    asyncio.run(test())
