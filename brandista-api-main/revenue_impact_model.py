"""
Growth Engine 2.0 - Realistic Revenue Impact Model
===================================================
Laskee realistisen "Revenue at Risk" perustuen:
1. Digitaalinen osuus liikevaihdosta (toimialan mukaan)
2. Konkreettiset ongelmat ja niiden vaikutus konversioon
3. Industry benchmarks ja tutkimusdata

Lahteet:
- Google: 53% mobiilikayttajista poistuu jos sivu latautuu >3s
- Portent: Jokainen sekunti latausaikaa = -4.42% konversio
- GlobalSign: 84% kayttajista hylkaa ostoksen jos ei SSL
- Baymard Institute: Keskimaarainen cart abandonment 70%
- Backlinko: #1 Google-tulos saa 27.6% klikkauksista
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# INDUSTRY PROFILES - Digitaalisen liikevaihdon osuus
# =============================================================================

INDUSTRY_PROFILES = {
    # B2C Retail/E-commerce - korkea digitaalinen osuus
    'ecommerce': {
        'name': {'fi': 'Verkkokauppa', 'en': 'E-commerce'},
        'digital_revenue_share': 0.85,  # 85% tulee verkosta
        'organic_traffic_share': 0.40,  # 40% liikenteesta orgaanista
        'mobile_traffic_share': 0.65,   # 65% mobiilikayttajia
        'avg_conversion_rate': 0.025,   # 2.5% konversio
    },
    'retail': {
        'name': {'fi': 'Vahittaiskauppa', 'en': 'Retail'},
        'digital_revenue_share': 0.35,  # 35% verkosta (omnichannel)
        'organic_traffic_share': 0.35,
        'mobile_traffic_share': 0.60,
        'avg_conversion_rate': 0.020,
    },
    'jewelry': {
        'name': {'fi': 'Koruala', 'en': 'Jewelry'},
        'digital_revenue_share': 0.25,  # 25% verkosta, paljon myymaloita
        'organic_traffic_share': 0.30,
        'mobile_traffic_share': 0.55,
        'avg_conversion_rate': 0.015,   # Korkeampi AOV, matalampi konversio
    },
    # B2B - matalampi digitaalinen osuus
    'b2b_services': {
        'name': {'fi': 'B2B-palvelut', 'en': 'B2B Services'},
        'digital_revenue_share': 0.20,  # 20% liideista verkosta
        'organic_traffic_share': 0.45,
        'mobile_traffic_share': 0.35,
        'avg_conversion_rate': 0.030,   # Lead conversion
    },
    'saas': {
        'name': {'fi': 'SaaS/Ohjelmistot', 'en': 'SaaS/Software'},
        'digital_revenue_share': 0.90,
        'organic_traffic_share': 0.50,
        'mobile_traffic_share': 0.30,
        'avg_conversion_rate': 0.020,
    },
    'manufacturing': {
        'name': {'fi': 'Teollisuus', 'en': 'Manufacturing'},
        'digital_revenue_share': 0.10,  # Paaosin offline
        'organic_traffic_share': 0.25,
        'mobile_traffic_share': 0.25,
        'avg_conversion_rate': 0.015,
    },
    # Default
    'default': {
        'name': {'fi': 'Yleinen', 'en': 'General'},
        'digital_revenue_share': 0.25,
        'organic_traffic_share': 0.35,
        'mobile_traffic_share': 0.55,
        'avg_conversion_rate': 0.020,
    }
}


# =============================================================================
# BUSINESS PRESENCE TYPE - Online-only vs Kivijalka
# =============================================================================

PRESENCE_MULTIPLIERS = {
    'online_only': {
        'name': {'fi': 'Vain verkossa', 'en': 'Online only'},
        'digital_share_multiplier': 1.8,
        'description': 'No physical stores, all revenue from online'
    },
    'omnichannel': {
        'name': {'fi': 'Monikanavainen', 'en': 'Omnichannel'},
        'digital_share_multiplier': 1.0,
        'description': 'Online + physical stores, integrated experience'
    },
    'brick_and_mortar': {
        'name': {'fi': 'Kivijalka', 'en': 'Brick & mortar'},
        'digital_share_multiplier': 0.5,
        'description': 'Primarily physical stores, website for info only'
    },
    'hybrid': {
        'name': {'fi': 'Hybridi', 'en': 'Hybrid'},
        'digital_share_multiplier': 0.75,
        'description': 'Physical stores with some online sales'
    }
}


import re

def detect_business_presence(html_content: str, basic_analysis: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Tunnistaa onko yritys online-only, kivijalka vai omnichannel.
    """
    html_lower = html_content.lower() if html_content else ''
    signals = {
        'has_opening_hours': False,
        'has_store_locator': False,
        'has_physical_address': False,
        'has_local_business_schema': False,
        'has_checkout': False,
        'has_cart': False,
        'store_count': 0
    }
    
    # 1. Aukioloajat
    opening_patterns = [
        'aukioloaj', 'opening hour', 'openingstime',
        'ma-pe', 'mon-fri', 'arkisin', 'avoinna', 'suljettu'
    ]
    for pattern in opening_patterns:
        if pattern in html_lower:
            signals['has_opening_hours'] = True
            break
    
    # 2. Myymalasijainnit
    store_patterns = [
        'myymala', 'myymalat', 'liike', 'liikkeet',
        'store locat', 'find store', 'our stores',
        'toimipist', 'store finder', 'etsi myymala'
    ]
    for pattern in store_patterns:
        if pattern in html_lower:
            signals['has_store_locator'] = True
            break
    
    # 3. Fyysinen osoite
    address_patterns = [
        r'\b[A-Za-z]+katu\s*\d{1,4}',
        r'\b[A-Za-z]+tie\s*\d{1,4}',
        r'\d{1,4}\s+\w+\s+(street|road|avenue)\b'
    ]
    for pattern in address_patterns:
        if re.search(pattern, html_lower):
            signals['has_physical_address'] = True
            break
    
    # 4. Postinumerot
    postal_matches = re.findall(r'\b\d{5}\b', html_lower)
    if len(postal_matches) >= 2:
        signals['has_physical_address'] = True
        signals['store_count'] = len(set(postal_matches))
    
    # 5. Schema.org LocalBusiness
    local_schemas = ['localbusiness', 'store', 'retailer', 'jewelrystore']
    for schema in local_schemas:
        if f'"@type":"{schema}"' in html_lower or f'"@type": "{schema}"' in html_lower:
            signals['has_local_business_schema'] = True
            break
    
    # 6. Verkkokauppa signaalit
    if any(p in html_lower for p in ['checkout', 'kassa', 'tilaus', 'maksu']):
        signals['has_checkout'] = True
    if any(p in html_lower for p in ['cart', 'ostoskori', 'add to cart', 'lisaa koriin']):
        signals['has_cart'] = True
    
    # 7. Maarita presence type
    physical = sum([
        signals['has_opening_hours'],
        signals['has_store_locator'],
        signals['has_physical_address'],
        signals['has_local_business_schema']
    ])
    online = sum([signals['has_checkout'], signals['has_cart']])
    
    if physical == 0 and online >= 1:
        presence_type = 'online_only'
    elif physical >= 3 and online >= 1:
        presence_type = 'omnichannel'
    elif physical >= 3:
        presence_type = 'brick_and_mortar'
    elif physical >= 1 and online >= 1:
        presence_type = 'hybrid'
    elif physical >= 1:
        presence_type = 'brick_and_mortar'
    else:
        presence_type = 'hybrid'
    
    return presence_type, signals


# =============================================================================
# RISK FACTORS - Tutkimukseen perustuvat vaikutuskertoimet
# =============================================================================

@dataclass
class RiskFactor:
    """Yksittainen riskitekija"""
    id: str
    name: Dict[str, str]
    description: Dict[str, str]
    
    # Vaikutus eri osa-alueisiin (0.0 - 1.0 = prosenttiosuus menetetysta)
    conversion_impact: float      # Vaikutus konversioon
    traffic_impact: float         # Vaikutus liikenteeseen
    trust_impact: float           # Vaikutus luottamukseen
    
    # Mihin liikenteeseen vaikuttaa
    affects_mobile: bool = False
    affects_organic: bool = False
    affects_all: bool = False
    
    # Todennakoisyys etta vaikutus toteutuu
    probability: float = 0.8
    
    # Korjauksen vaikeus ja kustannus
    fix_effort: str = 'medium'  # low/medium/high
    fix_cost_eur: Tuple[int, int] = (500, 2000)
    fix_time_days: Tuple[int, int] = (1, 7)
    
    # Lahteet/perustelut
    sources: List[str] = None


# Maaritellaan riskitekijat tutkimusdataan perustuen
RISK_FACTORS = {
    # ==========================================================================
    # KRIITTISET (valiton vaikutus)
    # ==========================================================================
    'ssl_missing': RiskFactor(
        id='ssl_missing',
        name={'fi': 'SSL-sertifikaatti puuttuu', 'en': 'Missing SSL Certificate'},
        description={
            'fi': 'Selaimet nayttavat "Ei turvallinen" -varoituksen. 84% kayttajista hylkaa ostoksen.',
            'en': 'Browsers show "Not Secure" warning. 84% of users abandon purchase.'
        },
        conversion_impact=0.40,  # -40% konversio (GlobalSign tutkimus)
        traffic_impact=0.10,     # -10% liikenne (Google rankaa alaspain)
        trust_impact=0.50,       # -50% luottamus
        affects_all=True,
        probability=0.95,
        fix_effort='low',
        fix_cost_eur=(0, 100),
        fix_time_days=(1, 2),
        sources=['GlobalSign: 84% abandon without SSL', 'Google: HTTPS as ranking factor']
    ),
    
    'page_speed_critical': RiskFactor(
        id='page_speed_critical',
        name={'fi': 'Kriittisen hidas sivusto (>5s)', 'en': 'Critically Slow Website (>5s)'},
        description={
            'fi': 'Sivusto latautuu yli 5 sekunnissa. 90% mobiilikayttajista poistuu.',
            'en': 'Page loads in over 5 seconds. 90% of mobile users leave.'
        },
        conversion_impact=0.35,  # -35% konversio
        traffic_impact=0.20,     # -20% liikenne (bounce)
        trust_impact=0.25,
        affects_mobile=True,
        affects_all=True,
        probability=0.90,
        fix_effort='high',
        fix_cost_eur=(2000, 10000),
        fix_time_days=(14, 60),
        sources=['Google: 53% leave if >3s', 'Portent: -4.42% per second']
    ),
    
    # ==========================================================================
    # KORKEAT (merkittava vaikutus)
    # ==========================================================================
    'mobile_not_optimized': RiskFactor(
        id='mobile_not_optimized',
        name={'fi': 'Heikko mobiilioptimointi', 'en': 'Poor Mobile Optimization'},
        description={
            'fi': 'Sivusto ei toimi hyvin mobiilissa. 61% kayttajista ei palaa huonon mobiilikokemuksen jalkeen.',
            'en': 'Website doesn\'t work well on mobile. 61% won\'t return after poor mobile experience.'
        },
        conversion_impact=0.25,  # -25% mobiilikonversio
        traffic_impact=0.15,     # -15% mobiililiikenne
        trust_impact=0.20,
        affects_mobile=True,
        probability=0.85,
        fix_effort='medium',
        fix_cost_eur=(1000, 5000),
        fix_time_days=(7, 30),
        sources=['Google: Mobile-first indexing', 'McKinsey: 61% won\'t return']
    ),
    
    'no_meta_descriptions': RiskFactor(
        id='no_meta_descriptions',
        name={'fi': 'Meta-kuvaukset puuttuvat', 'en': 'Missing Meta Descriptions'},
        description={
            'fi': 'Hakutuloksissa nakyy satunnainen teksti. CTR voi laskea 5-10%.',
            'en': 'Search results show random text. CTR can drop 5-10%.'
        },
        conversion_impact=0.05,
        traffic_impact=0.08,     # -8% orgaaninen CTR
        trust_impact=0.05,
        affects_organic=True,
        probability=0.80,
        fix_effort='low',
        fix_cost_eur=(200, 500),
        fix_time_days=(1, 3),
        sources=['Backlinko: Meta descriptions affect CTR']
    ),
    
    'thin_content': RiskFactor(
        id='thin_content',
        name={'fi': 'Ohut sisalto', 'en': 'Thin Content'},
        description={
            'fi': 'Liian vahan sisaltoa hakukoneoptimointiin. Vaikuttaa orgaaniseen nakyvyyteen.',
            'en': 'Too little content for SEO. Affects organic visibility.'
        },
        conversion_impact=0.10,
        traffic_impact=0.15,     # -15% orgaaninen liikenne
        trust_impact=0.10,
        affects_organic=True,
        probability=0.75,
        fix_effort='medium',
        fix_cost_eur=(500, 3000),
        fix_time_days=(7, 30),
        sources=['Ahrefs: Long-form content ranks better']
    ),
    
    'no_h1_tags': RiskFactor(
        id='no_h1_tags',
        name={'fi': 'H1-otsikot puuttuvat', 'en': 'Missing H1 Tags'},
        description={
            'fi': 'Paaotsikot puuttuvat. Heikentaa hakukonenakyvyytta.',
            'en': 'Main headings missing. Weakens search visibility.'
        },
        conversion_impact=0.03,
        traffic_impact=0.05,
        trust_impact=0.02,
        affects_organic=True,
        probability=0.70,
        fix_effort='low',
        fix_cost_eur=(100, 300),
        fix_time_days=(1, 2),
        sources=['Moz: H1 tags as ranking factor']
    ),
    
    # ==========================================================================
    # KESKITASOISET (kohtalainen vaikutus)
    # ==========================================================================
    'page_speed_slow': RiskFactor(
        id='page_speed_slow',
        name={'fi': 'Hidas sivusto (3-5s)', 'en': 'Slow Website (3-5s)'},
        description={
            'fi': 'Sivusto latautuu 3-5 sekunnissa. Konversio karsii.',
            'en': 'Page loads in 3-5 seconds. Conversion suffers.'
        },
        conversion_impact=0.15,
        traffic_impact=0.08,
        trust_impact=0.10,
        affects_mobile=True,
        probability=0.80,
        fix_effort='medium',
        fix_cost_eur=(500, 3000),
        fix_time_days=(3, 14),
        sources=['Portent: -4.42% conversion per second']
    ),
    
    'no_analytics': RiskFactor(
        id='no_analytics',
        name={'fi': 'Analytiikka puuttuu', 'en': 'Missing Analytics'},
        description={
            'fi': 'Ei dataa paatoksentekoon. Et tieda mika toimii ja mika ei.',
            'en': 'No data for decisions. You don\'t know what works and what doesn\'t.'
        },
        conversion_impact=0.10,  # Epasuora: et voi optimoida
        traffic_impact=0.05,
        trust_impact=0.0,
        affects_all=True,
        probability=0.60,
        fix_effort='low',
        fix_cost_eur=(0, 200),
        fix_time_days=(1, 2),
        sources=['Cannot optimize what you don\'t measure']
    ),
    
    'no_structured_data': RiskFactor(
        id='no_structured_data',
        name={'fi': 'Schema markup puuttuu', 'en': 'Missing Structured Data'},
        description={
            'fi': 'Ei rich snippeteja hakutuloksissa. CTR voi olla 30% matalampi.',
            'en': 'No rich snippets in search results. CTR can be 30% lower.'
        },
        conversion_impact=0.02,
        traffic_impact=0.06,
        trust_impact=0.03,
        affects_organic=True,
        probability=0.65,
        fix_effort='medium',
        fix_cost_eur=(300, 1000),
        fix_time_days=(2, 7),
        sources=['Search Engine Journal: Rich snippets increase CTR']
    ),
    
    'spa_not_rendered': RiskFactor(
        id='spa_not_rendered',
        name={'fi': 'SPA ei renderoidy hakukoneille', 'en': 'SPA Not Search Engine Rendered'},
        description={
            'fi': 'JavaScript-sovellus ei nay hakukoneille. Orgaaninen liikenne karsii merkittavasti.',
            'en': 'JavaScript app not visible to search engines. Organic traffic suffers significantly.'
        },
        conversion_impact=0.05,
        traffic_impact=0.40,     # -40% orgaaninen (vakava)
        trust_impact=0.05,
        affects_organic=True,
        probability=0.85,
        fix_effort='high',
        fix_cost_eur=(3000, 15000),
        fix_time_days=(14, 60),
        sources=['Google: JavaScript rendering challenges']
    ),
    
    # ==========================================================================
    # MATALAT (pieni mutta mitattava vaikutus)
    # ==========================================================================
    'missing_alt_texts': RiskFactor(
        id='missing_alt_texts',
        name={'fi': 'Kuva-alt-tekstit puuttuvat', 'en': 'Missing Image Alt Texts'},
        description={
            'fi': 'Kuvien alt-tekstit puuttuvat. Vaikuttaa kuvahaun nakyvyyteen.',
            'en': 'Image alt texts missing. Affects image search visibility.'
        },
        conversion_impact=0.01,
        traffic_impact=0.03,
        trust_impact=0.01,
        affects_organic=True,
        probability=0.60,
        fix_effort='low',
        fix_cost_eur=(100, 500),
        fix_time_days=(1, 5),
        sources=['Google: Alt text for image SEO']
    ),
    
    'no_sitemap': RiskFactor(
        id='no_sitemap',
        name={'fi': 'Sivukartta puuttuu', 'en': 'Missing Sitemap'},
        description={
            'fi': 'XML-sivukartta puuttuu. Voi hidastaa indeksointia.',
            'en': 'XML sitemap missing. May slow down indexing.'
        },
        conversion_impact=0.0,
        traffic_impact=0.03,
        trust_impact=0.0,
        affects_organic=True,
        probability=0.50,
        fix_effort='low',
        fix_cost_eur=(50, 200),
        fix_time_days=(1, 2),
        sources=['Google: Sitemaps help crawling']
    ),
}


# =============================================================================
# REVENUE IMPACT CALCULATOR
# =============================================================================

@dataclass
class RiskImpactItem:
    """Yksittaisen riskin vaikutus euroissa"""
    risk_id: str
    risk_name: str
    description: str
    
    # Lasketut vaikutukset
    annual_impact_low: int
    annual_impact_high: int
    annual_impact_expected: int
    
    # Prosenttiosuus
    impact_percentage: float
    
    # Mihin vaikuttaa
    affected_revenue_base: int
    affected_area: str  # 'mobile', 'organic', 'all'
    
    # Korjaus
    fix_effort: str
    fix_cost_range: str
    fix_time_range: str
    
    # Prioriteetti (laskettu ROI:n perusteella)
    priority: int  # 1-5
    roi_ratio: float  # Expected impact / fix cost


@dataclass  
class RevenueImpactAnalysis:
    """Kokonaisanalyysi"""
    # Yrityksen tiedot
    company_name: str
    annual_revenue: int
    industry: str
    industry_name: str
    
    # Digitaalinen jalanjalki
    digital_revenue: int
    digital_revenue_share: float
    organic_revenue: int
    mobile_revenue: int
    
    # Riskit
    risks: List[RiskImpactItem]
    total_risks_found: int
    
    # Kokonaisvaikutus
    total_impact_low: int
    total_impact_high: int
    total_impact_expected: int
    total_impact_percentage: float
    
    # Korjauksen ROI
    total_fix_cost_low: int
    total_fix_cost_high: int
    estimated_roi_ratio: float  # Impact / Cost
    
    # Confidence
    confidence_level: str  # 'high', 'medium', 'low'
    confidence_note: str
    
    # Methodology note
    methodology_note: str


def detect_industry(url: str, basic_analysis: Dict[str, Any], company_intel: Dict[str, Any] = None) -> str:
    """Tunnista toimiala URL:n, sisallon ja yritystietojen perusteella"""
    
    # Yrita ensin company_intel:sta
    if company_intel:
        industry_code = company_intel.get('industry_code') or ''
        industry_name = (company_intel.get('industry') or '').lower()
        
        # TOL-koodit (Suomi)
        if industry_code:
            if industry_code.startswith('47'):  # Vahittaiskauppa
                if '4791' in industry_code:  # Verkkokauppa
                    return 'ecommerce'
                return 'retail'
            if industry_code.startswith('32'):  # Korut
                return 'jewelry'
            if industry_code.startswith('62'):  # IT
                return 'saas'
            if industry_code.startswith('C'):   # Teollisuus
                return 'manufacturing'
        
        # Toimialan nimesta
        if any(x in industry_name for x in ['koru', 'jewelry', 'gold', 'kulta']):
            return 'jewelry'
        if any(x in industry_name for x in ['verkkokauppa', 'ecommerce', 'e-commerce']):
            return 'ecommerce'
    
    # URL-pohjainen arvaus
    url_lower = url.lower()
    if any(x in url_lower for x in ['shop', 'store', 'kauppa', 'buy']):
        return 'ecommerce'
    if any(x in url_lower for x in ['koru', 'jewelry', 'gold', 'kulta']):
        return 'jewelry'
    
    return 'default'


def detect_risks_from_analysis(basic: Dict[str, Any], technical: Dict[str, Any], content: Dict[str, Any]) -> List[str]:
    """Tunnista riskit analyysidatasta"""
    
    detected_risks = []
    breakdown = basic.get('score_breakdown', {})
    
    # Debug logging
    logger.info(f"[RevenueImpact] Detecting risks from analysis data:")
    logger.info(f"[RevenueImpact]   - has_ssl: {basic.get('has_ssl')}")
    logger.info(f"[RevenueImpact]   - mobile_score_raw: {basic.get('mobile_score_raw')}")
    logger.info(f"[RevenueImpact]   - has_viewport: {basic.get('has_viewport', basic.get('has_mobile_viewport'))}")
    logger.info(f"[RevenueImpact]   - breakdown.mobile: {breakdown.get('mobile')}")
    logger.info(f"[RevenueImpact]   - page_speed_score: {technical.get('page_speed_score')}")
    
    # SSL
    if not basic.get('has_ssl', True):
        detected_risks.append('ssl_missing')
    
    # Page speed
    speed_score = technical.get('page_speed_score', 100)
    if speed_score < 30:
        detected_risks.append('page_speed_critical')
    elif speed_score < 50:
        detected_risks.append('page_speed_slow')
    
    # Mobile - check multiple sources
    # 1. First try mobile_score_raw (0-100 scale)
    # 2. Then try responsive_design.score (0-100 scale)
    # 3. Finally fallback to breakdown.mobile (0-15 scale, need to convert)
    mobile_score_100 = basic.get('mobile_score_raw', 0)
    if not mobile_score_100:
        responsive = basic.get('responsive_design', {})
        mobile_score_100 = responsive.get('score', 0) if isinstance(responsive, dict) else 0
    if not mobile_score_100:
        # breakdown.mobile is 0-15, convert to 0-100
        mobile_weighted = breakdown.get('mobile', 15)
        mobile_score_100 = int((mobile_weighted / 15) * 100)
    
    # Also check specific mobile signals
    has_viewport = basic.get('has_mobile_viewport', basic.get('has_viewport', True))
    
    if mobile_score_100 < 50 or not has_viewport:
        detected_risks.append('mobile_not_optimized')
    
    # Meta descriptions
    if not basic.get('meta_description') or len(basic.get('meta_description', '')) < 50:
        detected_risks.append('no_meta_descriptions')
    
    # H1 tags
    if not basic.get('h1_count', 0) or basic.get('h1_count', 0) == 0:
        detected_risks.append('no_h1_tags')
    
    # Content depth
    word_count = content.get('word_count', 0)
    if word_count < 300:
        detected_risks.append('thin_content')
    
    # Analytics
    if not basic.get('has_analytics', False):
        detected_risks.append('no_analytics')
    
    # Structured data
    if not basic.get('has_schema', False):
        detected_risks.append('no_structured_data')
    
    # SPA rendering
    if basic.get('spa_detected') and basic.get('rendering_method') == 'http':
        detected_risks.append('spa_not_rendered')
    
    # Alt texts
    images_without_alt = technical.get('images_without_alt', 0)
    if images_without_alt > 5:
        detected_risks.append('missing_alt_texts')
    
    # Sitemap
    if not technical.get('has_sitemap', False):
        detected_risks.append('no_sitemap')
    
    return detected_risks


def calculate_revenue_impact(
    annual_revenue: int,
    detected_risks: List[str],
    industry: str = 'default',
    company_name: str = 'Company',
    language: str = 'en',
    business_presence: str = 'hybrid',
    html_content: str = ''
) -> RevenueImpactAnalysis:
    """
    Laske realistinen revenue impact
    
    Logiikka:
    1. Ota digitaalinen osuus liikevaihdosta (toimialan mukaan)
    2. Saada business presence (online-only vs kivijalka)
    3. Laske jokaisen riskin vaikutus erikseen
    4. Huomioi paallekkaisyydet (riskit eivat summaudu 100%)
    5. Anna range (low-high) ja expected arvo
    """
    
    profile = INDUSTRY_PROFILES.get(industry, INDUSTRY_PROFILES['default'])
    
    # Tunnista business presence jos HTML annettu
    presence_signals = {}
    if html_content and business_presence == 'hybrid':
        business_presence, presence_signals = detect_business_presence(html_content, {})
        logger.info(f"[RevenueImpact] Detected business presence: {business_presence}")
        logger.info(f"[RevenueImpact] Presence signals: {presence_signals}")
    
    # Hae presence multiplier
    presence_config = PRESENCE_MULTIPLIERS.get(business_presence, PRESENCE_MULTIPLIERS['hybrid'])
    presence_multiplier = presence_config['digital_share_multiplier']
    
    # Lasketaan digitaalinen liikevaihto (huomioi presence)
    base_digital_share = profile['digital_revenue_share']
    adjusted_digital_share = min(base_digital_share * presence_multiplier, 0.95)  # Max 95%
    
    digital_revenue = int(annual_revenue * adjusted_digital_share)
    organic_revenue = int(digital_revenue * profile['organic_traffic_share'])
    mobile_revenue = int(digital_revenue * profile['mobile_traffic_share'])
    
    logger.info(f"[RevenueImpact] Industry: {industry}, Presence: {business_presence}")
    logger.info(f"[RevenueImpact] Digital share: {base_digital_share} x {presence_multiplier} = {adjusted_digital_share:.2f}")
    logger.info(f"[RevenueImpact] Digital revenue: EUR{digital_revenue:,} of EUR{annual_revenue:,}")
    
    risk_items = []
    total_fix_cost_low = 0
    total_fix_cost_high = 0
    
    # Lasketaan jokaisen riskin vaikutus
    for risk_id in detected_risks:
        if risk_id not in RISK_FACTORS:
            continue
            
        risk = RISK_FACTORS[risk_id]
        
        # Maarita mihin liikevaihtoon vaikuttaa
        if risk.affects_all:
            affected_base = digital_revenue
            affected_area = 'all_digital'
        elif risk.affects_mobile:
            affected_base = mobile_revenue
            affected_area = 'mobile'
        elif risk.affects_organic:
            affected_base = organic_revenue
            affected_area = 'organic'
        else:
            affected_base = digital_revenue
            affected_area = 'all_digital'
        
        # Laske vaikutus
        # Kombinoi conversion + traffic + trust vaikutukset
        total_impact_rate = (
            risk.conversion_impact * 0.5 +  # Konversio painotetuin
            risk.traffic_impact * 0.35 +
            risk.trust_impact * 0.15
        )
        
        # Huomioi todennakoisyys
        expected_impact_rate = total_impact_rate * risk.probability
        
        # Laske eurot
        impact_expected = int(affected_base * expected_impact_rate)
        impact_low = int(impact_expected * 0.6)  # -40% pessimistinen
        impact_high = int(impact_expected * 1.4)  # +40% optimistinen
        
        # Korjauskustannukset
        fix_cost_low, fix_cost_high = risk.fix_cost_eur
        fix_time_low, fix_time_high = risk.fix_time_days
        total_fix_cost_low += fix_cost_low
        total_fix_cost_high += fix_cost_high
        
        # ROI
        avg_fix_cost = (fix_cost_low + fix_cost_high) / 2
        roi_ratio = impact_expected / max(avg_fix_cost, 1)
        
        # Prioriteetti (1-5) perustuen ROI:hin
        if roi_ratio > 50:
            priority = 1
        elif roi_ratio > 20:
            priority = 2
        elif roi_ratio > 10:
            priority = 3
        elif roi_ratio > 5:
            priority = 4
        else:
            priority = 5
        
        risk_items.append(RiskImpactItem(
            risk_id=risk_id,
            risk_name=risk.name.get(language, risk.name['en']),
            description=risk.description.get(language, risk.description['en']),
            annual_impact_low=impact_low,
            annual_impact_high=impact_high,
            annual_impact_expected=impact_expected,
            impact_percentage=round(expected_impact_rate * 100, 1),
            affected_revenue_base=affected_base,
            affected_area=affected_area,
            fix_effort=risk.fix_effort,
            fix_cost_range=f"EUR{fix_cost_low:,} - EUR{fix_cost_high:,}",
            fix_time_range=f"{fix_time_low}-{fix_time_high} paivaa" if language == 'fi' else f"{fix_time_low}-{fix_time_high} days",
            priority=priority,
            roi_ratio=round(roi_ratio, 1)
        ))
    
    # Jarjesta prioriteetin mukaan
    risk_items.sort(key=lambda x: (x.priority, -x.annual_impact_expected))
    
    # Laske kokonaisvaikutus
    # HUOM: Riskit eivat summaudu suoraan - kaytetaan "diminishing returns" logiikkaa
    # Ensimmainen riski = 100%, toinen = 80%, kolmas = 60%, jne.
    total_impact_expected = 0
    diminishing_factor = 1.0
    
    for item in risk_items:
        total_impact_expected += int(item.annual_impact_expected * diminishing_factor)
        diminishing_factor *= 0.75  # Jokainen seuraava riski vaikuttaa vahemman
    
    # Cap total impact to max 40% of digital revenue (realistinen ylaraja)
    total_impact_expected = min(total_impact_expected, int(digital_revenue * 0.40))
    total_impact_low = int(total_impact_expected * 0.6)
    total_impact_high = int(total_impact_expected * 1.4)
    
    # Prosenttiosuus koko liikevaihdosta
    total_impact_percentage = round((total_impact_expected / annual_revenue) * 100, 2) if annual_revenue > 0 else 0
    
    # ROI
    avg_total_fix_cost = (total_fix_cost_low + total_fix_cost_high) / 2
    estimated_roi = total_impact_expected / max(avg_total_fix_cost, 1)
    
    # Confidence level
    if len(detected_risks) >= 3 and annual_revenue > 1000000:
        confidence_level = 'high'
        confidence_note = 'Perustuu useaan havaittuun riskiin ja todelliseen liikevaihtodataan' if language == 'fi' else 'Based on multiple detected risks and actual revenue data'
    elif len(detected_risks) >= 2:
        confidence_level = 'medium'
        confidence_note = 'Perustuu havaittuihin riskeihin ja toimiala-arvioihin' if language == 'fi' else 'Based on detected risks and industry estimates'
    else:
        confidence_level = 'low'
        confidence_note = 'Rajoitettu data - suosittelemme lisaanalyysia' if language == 'fi' else 'Limited data - we recommend additional analysis'
    
    methodology_note = (
        f"Laskelma perustuu {profile['name'][language]}-toimialan keskiarvoihin: "
        f"{int(profile['digital_revenue_share']*100)}% liikevaihdosta digitaalista, "
        f"{int(profile['organic_traffic_share']*100)}% liikenteesta orgaanista, "
        f"{int(profile['mobile_traffic_share']*100)}% mobiilikayttajia."
    ) if language == 'fi' else (
        f"Calculation based on {profile['name'][language]} industry averages: "
        f"{int(profile['digital_revenue_share']*100)}% digital revenue, "
        f"{int(profile['organic_traffic_share']*100)}% organic traffic, "
        f"{int(profile['mobile_traffic_share']*100)}% mobile users."
    )
    
    return RevenueImpactAnalysis(
        company_name=company_name,
        annual_revenue=annual_revenue,
        industry=industry,
        industry_name=profile['name'].get(language, profile['name']['en']),
        digital_revenue=digital_revenue,
        digital_revenue_share=profile['digital_revenue_share'],
        organic_revenue=organic_revenue,
        mobile_revenue=mobile_revenue,
        risks=risk_items,
        total_risks_found=len(risk_items),
        total_impact_low=total_impact_low,
        total_impact_high=total_impact_high,
        total_impact_expected=total_impact_expected,
        total_impact_percentage=total_impact_percentage,
        total_fix_cost_low=total_fix_cost_low,
        total_fix_cost_high=total_fix_cost_high,
        estimated_roi_ratio=round(estimated_roi, 1),
        confidence_level=confidence_level,
        confidence_note=confidence_note,
        methodology_note=methodology_note
    )


def revenue_impact_to_dict(analysis: RevenueImpactAnalysis) -> Dict[str, Any]:
    """Muunna RevenueImpactAnalysis dictionaryksi JSON-serialisointia varten"""
    return {
        'company_name': analysis.company_name,
        'annual_revenue': analysis.annual_revenue,
        'industry': analysis.industry,
        'industry_name': analysis.industry_name,
        
        'digital_footprint': {
            'digital_revenue': analysis.digital_revenue,
            'digital_revenue_share': analysis.digital_revenue_share,
            'organic_revenue': analysis.organic_revenue,
            'mobile_revenue': analysis.mobile_revenue,
        },
        
        'risks': [
            {
                'risk_id': r.risk_id,
                'risk_name': r.risk_name,
                'description': r.description,
                'annual_impact_low': r.annual_impact_low,
                'annual_impact_high': r.annual_impact_high,
                'annual_impact_expected': r.annual_impact_expected,
                'impact_percentage': r.impact_percentage,
                'affected_revenue_base': r.affected_revenue_base,
                'affected_area': r.affected_area,
                'fix_effort': r.fix_effort,
                'fix_cost_range': r.fix_cost_range,
                'fix_time_range': r.fix_time_range,
                'priority': r.priority,
                'roi_ratio': r.roi_ratio,
            }
            for r in analysis.risks
        ],
        
        'total_risks_found': analysis.total_risks_found,
        
        'total_impact': {
            'low': analysis.total_impact_low,
            'high': analysis.total_impact_high,
            'expected': analysis.total_impact_expected,
            'percentage_of_revenue': analysis.total_impact_percentage,
        },
        
        'fix_investment': {
            'cost_low': analysis.total_fix_cost_low,
            'cost_high': analysis.total_fix_cost_high,
            'estimated_roi_ratio': analysis.estimated_roi_ratio,
        },
        
        'confidence': {
            'level': analysis.confidence_level,
            'note': analysis.confidence_note,
        },
        
        'methodology_note': analysis.methodology_note,
    }
