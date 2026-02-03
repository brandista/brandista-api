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

    # PRH/YTJ Open Data API - Updated to v3 (Feb 2026)
    # Old v1 endpoint (/bis/v1) was deprecated
    YTJ_API_BASE = "https://avoindata.prh.fi/opendata-ytj-api/v3"

    # Kauppalehti company pages
    KAUPPALEHTI_BASE = "https://www.kauppalehti.fi/yritykset/yritys"
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            follow_redirects=True
        )
    
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
            # Fetch from both sources in parallel
            ytj_task = self._ytj_get_company(business_id)
            kl_task = self._kauppalehti_get_company(business_id)
            
            ytj_data, kl_data = await asyncio.gather(ytj_task, kl_task, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(ytj_data, Exception):
                logger.warning(f"[CompanyIntel] YTJ fetch failed: {ytj_data}")
                ytj_data = None
            if isinstance(kl_data, Exception):
                logger.warning(f"[CompanyIntel] Kauppalehti fetch failed: {kl_data}")
                kl_data = None
            
            if not ytj_data and not kl_data:
                return None
            
            # Merge data
            profile = self._merge_company_data(ytj_data, kl_data, business_id)
            
            logger.info(f"[CompanyIntel] ✅ Profile fetched: {profile.get('name', business_id)}")
            return profile
            
        except Exception as e:
            logger.error(f"[CompanyIntel] Profile fetch failed for {business_id}: {e}")
            return None
    
    async def get_company_from_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Try to find company info from a domain name.
        
        1. Extracts likely company name from domain
        2. Searches YTJ
        3. Returns best match with full profile
        """
        # Clean domain
        domain = domain.lower().strip()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'^www\.', '', domain)
        domain = domain.split('/')[0]  # Remove path
        
        # Extract company name from domain
        # valio.fi -> Valio
        # verkkokauppa.com -> Verkkokauppa
        name_part = domain.split('.')[0]
        
        # Try search
        results = await self.search_company(name_part, max_results=3)
        
        if not results:
            # Try without common suffixes
            for suffix in ['oy', 'ab', 'group', 'finland', 'fi']:
                if name_part.endswith(suffix):
                    clean_name = name_part[:-len(suffix)]
                    results = await self.search_company(clean_name, max_results=3)
                    if results:
                        break
        
        if not results:
            logger.info(f"[CompanyIntel] No company found for domain: {domain}")
            return None
        
        # Get full profile of best match
        best_match = results[0]
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
        """Search YTJ by company name - Updated for v3 API"""

        url = f"{self.YTJ_API_BASE}/companies"
        params = {
            'name': name
        }

        response = await self.client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        results = data.get('companies', [])[:max_results]

        companies = []
        for item in results:
            company = self._parse_ytj_v3_result(item)
            if company:
                companies.append(company)

        return companies
    
    async def _ytj_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """Get single company from YTJ by business ID - Updated for v3 API"""

        url = f"{self.YTJ_API_BASE}/companies"
        params = {
            'businessId': business_id  # v3 uses query param, not path
        }

        response = await self.client.get(url, params=params)

        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()
        results = data.get('companies', [])

        if not results:
            return None

        return self._parse_ytj_v3_result(results[0])
    
    def _parse_ytj_v3_result(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse YTJ v3 API result into clean format"""

        try:
            # Business ID - v3 uses nested structure
            business_id_obj = item.get('businessId', {})
            business_id = business_id_obj.get('value', '') if isinstance(business_id_obj, dict) else str(business_id_obj)

            # Get names (prefer type '1' = official name)
            names = item.get('names', [])
            name = ''
            for n in names:
                if n.get('type') == '1':  # Official company name
                    name = n.get('name', '')
                    break
            if not name and names:
                name = names[0].get('name', '')

            # Registration date
            reg_date = item.get('registrationDate', '')
            founded_year = None
            if reg_date:
                try:
                    founded_year = int(reg_date[:4])
                except:
                    pass

            # Address - v3 structure
            addresses = item.get('addresses', [])
            address = None
            city = None
            postal_code = None
            for addr in addresses:
                if addr.get('type') == 1:  # Street address
                    street = addr.get('street', '')
                    building = addr.get('buildingNumber', '')
                    address = f"{street} {building}".strip() if street else None
                    postal_code = addr.get('postCode', '')
                    # City from postOffices
                    post_offices = addr.get('postOffices', [])
                    for po in post_offices:
                        if po.get('languageCode') == '1':  # Finnish
                            city = po.get('city', '')
                            break
                    if not city and post_offices:
                        city = post_offices[0].get('city', '')
                    break

            # Business line (TOL code) - v3 uses mainBusinessLine
            main_bl = item.get('mainBusinessLine', {})
            industry = None
            industry_code = None
            if main_bl:
                industry_code = main_bl.get('type', '')
                descriptions = main_bl.get('descriptions', [])
                for desc in descriptions:
                    if desc.get('languageCode') == '1':  # Finnish
                        industry = desc.get('description', '')
                        break
                if not industry and descriptions:
                    industry = descriptions[0].get('description', '')

            # Company form - v3 structure
            company_forms = item.get('companyForms', [])
            company_form = None
            for cf in company_forms:
                descriptions = cf.get('descriptions', [])
                for desc in descriptions:
                    if desc.get('languageCode') == '1':  # Finnish
                        company_form = desc.get('description', '')
                        break
                if company_form:
                    break

            # Status - v3 uses 'status' field directly
            status_code = item.get('status', '')
            status = 'active' if status_code == '2' else 'inactive' if status_code else 'unknown'

            # Check company situations for liquidation etc
            situations = item.get('companySituations', [])
            if situations:
                status = 'liquidation'

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
            logger.error(f"[CompanyIntel] YTJ v3 parse error: {e}")
            return None
    
    # =========================================================================
    # FINDER.FI (Web Scraping for Financial Data) - Feb 2026 update
    # Kauppalehti uses JS rendering, Finder.fi has data in HTML
    # =========================================================================

    FINDER_SEARCH_URL = "https://www.finder.fi/search"

    async def _kauppalehti_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Get company financial data - now uses Finder.fi instead of Kauppalehti.
        Kauppalehti renders data via JavaScript which doesn't work with simple HTTP requests.
        Finder.fi has financial data directly in HTML.
        """
        return await self._finder_get_company(business_id)

    async def _finder_get_company(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Scrape company financial data from Proff.fi (Finder.fi requires JS).
        Proff.fi has financial data directly in HTML.
        """
        try:
            clean_id = business_id.replace('-', '')

            # Proff.fi search by business ID
            search_url = f"https://www.proff.fi/selaa?q={business_id}"
            logger.info(f"[CompanyIntel] Searching Proff.fi: {search_url}")

            response = await self.client.get(search_url)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find company link in search results
                # Proff.fi links contain the business ID in format "0116297-6I116S"
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/yrityksen/' in href and clean_id in href.replace('-', ''):
                        company_url = href if href.startswith('http') else f"https://www.proff.fi{href}"
                        logger.info(f"[CompanyIntel] Found Proff.fi company: {company_url}")

                        # Fetch company page
                        resp2 = await self.client.get(company_url)
                        if resp2.status_code == 200:
                            return self._parse_proff_html(resp2.text, business_id)
                        break

            logger.info(f"[CompanyIntel] No financial data found for {business_id}")
            return None

        except Exception as e:
            logger.warning(f"[CompanyIntel] Financial data fetch failed for {business_id}: {e}")
            return None

    def _parse_proff_html(self, html: str, business_id: str) -> Optional[Dict[str, Any]]:
        """Parse Proff.fi company page for financial data"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text()

            data = {
                'business_id': business_id,
                'source': 'proff'
            }

            import re

            # Proff.fi shows revenue in several formats:
            # "liikevaihto oli 1 992,6 MEUR" or "Liikevaihto1 992 610" (in thousands)
            revenue_patterns = [
                (r'liikevaihto\s+oli\s+([\d\s,\.]+)\s*MEUR', 1_000_000),  # "1 992,6 MEUR"
                (r'liikevaihto\s+oli\s+([\d\s,\.]+)\s*M', 1_000_000),  # "1992 M"
                (r'Liikevaihto\s*\d{4}\s*([\d\s]+)', 1_000),  # "Liikevaihto 2024 1 992 610" (thousands)
                (r'Liikevaihto([\d\s,\.]+)(?:Liikevoitto|Yhtiömuoto)', 1_000),  # Between labels (thousands)
            ]

            for pattern, multiplier in revenue_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).strip().replace(' ', '').replace(',', '.')
                    try:
                        value = float(value_str) * multiplier
                        if value >= 10_000:  # Sanity check - at least 10k EUR
                            data['revenue'] = int(value)
                            data['revenue_text'] = match.group(0)[:50]
                            logger.info(f"[CompanyIntel] Proff.fi revenue: EUR {data['revenue']:,}")
                            break
                    except:
                        pass

            # Employees - "työllistää 3 451 henkilöä" or "Henkilöstö: 3451"
            emp_patterns = [
                r'työllistää\s*([\d\s]+)\s*henkilöä',
                r'Henkilöstö[:\s]*([\d\s]+)',
                r'([\d\s]+)\s*henkilöä',
            ]

            for pattern in emp_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).strip().replace(' ', '')
                    try:
                        emp = int(value_str)
                        if 1 <= emp <= 100_000:  # Sanity check
                            data['employees'] = emp
                            break
                    except:
                        pass

            if data.get('revenue') or data.get('employees'):
                return data

            return None

        except Exception as e:
            logger.error(f"[CompanyIntel] Proff.fi parse error: {e}")
            return None

    def _parse_finder_html(self, html: str, business_id: str) -> Optional[Dict[str, Any]]:
        """Parse Finder.fi company page HTML for financial data"""

        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text()

            data = {
                'business_id': business_id,
                'source': 'finder'
            }

            # Company name from h1
            h1 = soup.find('h1')
            if h1:
                data['name'] = h1.get_text(strip=True)

            # Extract revenue using regex patterns
            # Finder shows: "Liikevaihto, €1 520 M" or "1 993 M" etc
            import re

            # Pattern 1: "Liikevaihto, €X XXX M" or "X,X miljardia"
            revenue_patterns = [
                r'Liikevaihto[,\s]*€?\s*([\d\s,\.]+)\s*M',  # "1 993 M"
                r'Liikevaihto[^\d]*([\d,\.]+)\s*miljardia',  # "1,9 miljardia"
                r'Liikevaihto[^\d]*([\d\s,\.]+)\s*miljoonaa',  # "500 miljoonaa"
                r'Liikevaihto[^\d]*([\d\s,\.]+)\s*euroa',  # Direct euros
            ]

            for pattern in revenue_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).strip()
                    # Clean and parse
                    value_str = value_str.replace(' ', '').replace(',', '.')

                    try:
                        value = float(value_str)
                        # Determine multiplier
                        if 'miljardia' in pattern:
                            value *= 1_000_000_000
                        elif 'M' in pattern or 'miljoonaa' in pattern:
                            value *= 1_000_000

                        data['revenue'] = int(value)
                        data['revenue_text'] = match.group(0)
                        logger.info(f"[CompanyIntel] Found revenue: {data['revenue']:,}€")
                        break
                    except:
                        pass

            # Extract employees - look in structured format
            # Finder shows employees in a table or specific format
            emp_patterns = [
                r'Henkilöstömäärä\s*(\d{1,5})\s',  # "Henkilöstömäärä 3451 "
                r'Henkilöstö\s*(\d{1,5})\s*hlö',  # "Henkilöstö 123 hlö"
                r'(\d{1,5})\s*työntekijää',  # "3451 työntekijää"
                r'Henkilöstö\s+(\d{1,5})\s',  # "Henkilöstö 3451 "
            ]

            for pattern in emp_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).strip()
                    try:
                        emp_count = int(value_str)
                        # Sanity check - employee count should be reasonable
                        if 1 <= emp_count <= 100000:
                            data['employees'] = emp_count
                            data['employees_text'] = match.group(0)
                            break
                    except:
                        pass

            # Extract profit/result
            profit_patterns = [
                r'Tilikauden tulos[^\d-]*([-\d\s,\.]+)\s*M',
                r'Liiketulos[^\d-]*([-\d\s,\.]+)\s*M',
                r'Tulos[^\d-]*([-\d\s,\.]+)\s*miljoonaa',
            ]

            for pattern in profit_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).strip().replace(' ', '').replace(',', '.')
                    try:
                        value = float(value_str) * 1_000_000
                        data['profit'] = int(value)
                        data['profit_text'] = match.group(0)
                        break
                    except:
                        pass

            # Only return if we got useful data
            if data.get('revenue') or data.get('employees'):
                return data

            return None

        except Exception as e:
            logger.error(f"[CompanyIntel] Finder.fi parse error: {e}")
            return None

    def _parse_kauppalehti_html(self, html: str, business_id: str) -> Optional[Dict[str, Any]]:
        """Parse Kauppalehti company page HTML - DEPRECATED, kept for compatibility"""
        # Now using Finder.fi instead
        return None

    # =========================================================================
    # FINANCIAL VALUE PARSING
    # =========================================================================
    
    def _parse_financial_value(self, text: str) -> Dict[str, Any]:
        """
        Parse Finnish financial value text.
        
        Examples:
        - "12 500 000 €" -> {'value': 12500000, 'unit': 'EUR'}
        - "12,5 M€" -> {'value': 12500000, 'unit': 'EUR'}
        - "1 234" -> {'value': 1234}
        - "15 hlö" -> {'value': 15}
        """
        
        result = {'raw': text}
        
        if not text:
            return result
        
        text = text.strip().upper()
        
        # Remove currency symbols
        text = text.replace('€', '').replace('EUR', '')
        
        # Handle millions/thousands abbreviations
        multiplier = 1
        if 'M' in text or 'MILJ' in text:
            multiplier = 1_000_000
            text = re.sub(r'M(ILJ)?\.?', '', text)
        elif 'K' in text or 'T€' in text:
            multiplier = 1_000
            text = text.replace('K', '').replace('T', '')
        
        # Remove non-numeric except comma and minus
        text = re.sub(r'[^\d,.\-]', '', text)
        
        # Handle Finnish decimal (comma) vs thousand separator (space/dot)
        # "12 500,50" -> 12500.50
        text = text.replace(' ', '')
        
        # If both comma and dot, comma is likely decimal
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.')
        elif ',' in text:
            # Single comma - could be decimal or thousand
            parts = text.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Likely decimal: 12,5 or 12,50
                text = text.replace(',', '.')
            else:
                # Likely thousand separator
                text = text.replace(',', '')
        
        try:
            value = float(text) * multiplier
            result['value'] = int(value) if value == int(value) else value
        except:
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
        business_id: str
    ) -> Dict[str, Any]:
        """Merge data from YTJ and Kauppalehti into unified profile"""
        
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
