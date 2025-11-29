"""
Growth Engine 2.0 - Realistic Revenue Impact Model
===================================================
Laskee realistisen "Revenue at Risk" perustuen:
1. Digitaalinen osuus liikevaihdosta (toimialan mukaan)
2. Konkreettiset ongelmat ja niiden vaikutus konversioon
3. Industry benchmarks ja tutkimusdata

Lähteet:
- Google: 53% mobiilikäyttäjistä poistuu jos sivu latautuu >3s
- Portent: Jokainen sekunti latausaikaa = -4.42% konversio
- GlobalSign: 84% käyttäjistä hylkää ostoksen jos ei SSL
- Baymard Institute: Keskimääräinen cart abandonment 70%
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
        'organic_traffic_share': 0.40,  # 40% liikenteestä orgaanista
        'mobile_traffic_share': 0.65,   # 65% mobiilikäyttäjiä
        'avg_conversion_rate': 0.025,   # 2.5% konversio
    },
    'retail': {
        'name': {'fi': 'Vähittäiskauppa', 'en': 'Retail'},
        'digital_revenue_share': 0.35,  # 35% verkosta (omnichannel)
        'organic_traffic_share': 0.35,
        'mobile_traffic_share': 0.60,
        'avg_conversion_rate': 0.020,
    },
    'jewelry': {
        'name': {'fi': 'Koruala', 'en': 'Jewelry'},
        'digital_revenue_share': 0.25,  # 25% verkosta, paljon myymälöitä
        'organic_traffic_share': 0.30,
        'mobile_traffic_share': 0.55,
        'avg_conversion_rate': 0.015,   # Korkeampi AOV, matalampi konversio
    },
    # B2B - matalampi digitaalinen osuus
    'b2b_services': {
        'name': {'fi': 'B2B-palvelut', 'en': 'B2B Services'},
        'digital_revenue_share': 0.20,  # 20% liideistä verkosta
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
        'digital_revenue_share': 0.10,  # Pääosin offline
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
# RISK FACTORS - Tutkimukseen perustuvat vaikutuskertoimet
# =============================================================================

@dataclass
class RiskFactor:
    """Yksittäinen riskitekijä"""
    id: str
    name: Dict[str, str]
    description: Dict[str, str]
    
    # Vaikutus eri osa-alueisiin (0.0 - 1.0 = prosenttiosuus menetetystä)
    conversion_impact: float      # Vaikutus konversioon
    traffic_impact: float         # Vaikutus liikenteeseen
    trust_impact: float           # Vaikutus luottamukseen
    
    # Mihin liikenteeseen vaikuttaa
    affects_mobile: bool = False
    affects_organic: bool = False
    affects_all: bool = False
    
    # Todennäköisyys että vaikutus toteutuu
    probability: float = 0.8
    
    # Korjauksen vaikeus ja kustannus
    fix_effort: str = 'medium'  # low/medium/high
    fix_cost_eur: Tuple[int, int] = (500, 2000)
    fix_time_days: Tuple[int, int] = (1, 7)
    
    # Lähteet/perustelut
    sources: List[str] = None


# Määritellään riskitekijät tutkimusdataan perustuen
RISK_FACTORS = {
    # ==========================================================================
    # KRIITTISET (välitön vaikutus)
    # ==========================================================================
    'ssl_missing': RiskFactor(
        id='ssl_missing',
        name={'fi': 'SSL-sertifikaatti puuttuu', 'en': 'Missing SSL Certificate'},
        description={
            'fi': 'Selaimet näyttävät "Ei turvallinen" -varoituksen. 84% käyttäjistä hylkää ostoksen.',
            'en': 'Browsers show "Not Secure" warning. 84% of users abandon purchase.'
        },
        conversion_impact=0.40,  # -40% konversio (GlobalSign tutkimus)
        traffic_impact=0.10,     # -10% liikenne (Google rankaa alaspäin)
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
            'fi': 'Sivusto latautuu yli 5 sekunnissa. 90% mobiilikäyttäjistä poistuu.',
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
    # KORKEAT (merkittävä vaikutus)
    # ==========================================================================
    'mobile_not_optimized': RiskFactor(
        id='mobile_not_optimized',
        name={'fi': 'Heikko mobiilioptimointi', 'en': 'Poor Mobile Optimization'},
        description={
            'fi': 'Sivusto ei toimi hyvin mobiilissa. 61% käyttäjistä ei palaa huonon mobiilikokemuksen jälkeen.',
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
            'fi': 'Hakutuloksissa näkyy satunnainen teksti. CTR voi laskea 5-10%.',
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
        name={'fi': 'Ohut sisältö', 'en': 'Thin Content'},
        description={
            'fi': 'Liian vähän sisältöä hakukoneoptimointiin. Vaikuttaa orgaaniseen näkyvyyteen.',
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
            'fi': 'Pääotsikot puuttuvat. Heikentää hakukonenäkyvyyttä.',
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
            'fi': 'Sivusto latautuu 3-5 sekunnissa. Konversio kärsii.',
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
            'fi': 'Ei dataa päätöksentekoon. Et tiedä mikä toimii ja mikä ei.',
            'en': 'No data for decisions. You don\'t know what works and what doesn\'t.'
        },
        conversion_impact=0.10,  # Epäsuora: et voi optimoida
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
            'fi': 'Ei rich snippetejä hakutuloksissa. CTR voi olla 30% matalampi.',
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
        name={'fi': 'SPA ei renderöidy hakukoneille', 'en': 'SPA Not Search Engine Rendered'},
        description={
            'fi': 'JavaScript-sovellus ei näy hakukoneille. Orgaaninen liikenne kärsii merkittävästi.',
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
            'fi': 'Kuvien alt-tekstit puuttuvat. Vaikuttaa kuvahaun näkyvyyteen.',
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
    """Yksittäisen riskin vaikutus euroissa"""
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
    
    # Digitaalinen jalanjälki
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
    """Tunnista toimiala URL:n, sisällön ja yritystietojen perusteella"""
    
    # Yritä ensin company_intel:sta
    if company_intel:
        industry_code = company_intel.get('industry_code', '')
        industry_name = company_intel.get('industry', '').lower()
        
        # TOL-koodit (Suomi)
        if industry_code:
            if industry_code.startswith('47'):  # Vähittäiskauppa
                if '4791' in industry_code:  # Verkkokauppa
                    return 'ecommerce'
                return 'retail'
            if industry_code.startswith('32'):  # Korut
                return 'jewelry'
            if industry_code.startswith('62'):  # IT
                return 'saas'
            if industry_code.startswith('C'):   # Teollisuus
                return 'manufacturing'
        
        # Toimialan nimestä
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
    
    # SSL
    if not basic.get('has_ssl', True):
        detected_risks.append('ssl_missing')
    
    # Page speed
    speed_score = technical.get('page_speed_score', 100)
    if speed_score < 30:
        detected_risks.append('page_speed_critical')
    elif speed_score < 50:
        detected_risks.append('page_speed_slow')
    
    # Mobile
    mobile_score = breakdown.get('mobile', 20)
    if mobile_score < 10:
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
    language: str = 'en'
) -> RevenueImpactAnalysis:
    """
    Laske realistinen revenue impact
    
    Logiikka:
    1. Ota digitaalinen osuus liikevaihdosta (toimialan mukaan)
    2. Laske jokaisen riskin vaikutus erikseen
    3. Huomioi päällekkäisyydet (riskit eivät summaudu 100%)
    4. Anna range (low-high) ja expected arvo
    """
    
    profile = INDUSTRY_PROFILES.get(industry, INDUSTRY_PROFILES['default'])
    
    # Lasketaan digitaalinen liikevaihto
    digital_revenue = int(annual_revenue * profile['digital_revenue_share'])
    organic_revenue = int(digital_revenue * profile['organic_traffic_share'])
    mobile_revenue = int(digital_revenue * profile['mobile_traffic_share'])
    
    risk_items = []
    total_fix_cost_low = 0
    total_fix_cost_high = 0
    
    # Lasketaan jokaisen riskin vaikutus
    for risk_id in detected_risks:
        if risk_id not in RISK_FACTORS:
            continue
            
        risk = RISK_FACTORS[risk_id]
        
        # Määritä mihin liikevaihtoon vaikuttaa
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
        
        # Huomioi todennäköisyys
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
            fix_cost_range=f"€{fix_cost_low:,} - €{fix_cost_high:,}",
            fix_time_range=f"{fix_time_low}-{fix_time_high} päivää" if language == 'fi' else f"{fix_time_low}-{fix_time_high} days",
            priority=priority,
            roi_ratio=round(roi_ratio, 1)
        ))
    
    # Järjestä prioriteetin mukaan
    risk_items.sort(key=lambda x: (x.priority, -x.annual_impact_expected))
    
    # Laske kokonaisvaikutus
    # HUOM: Riskit eivät summaudu suoraan - käytetään "diminishing returns" logiikkaa
    # Ensimmäinen riski = 100%, toinen = 80%, kolmas = 60%, jne.
    total_impact_expected = 0
    diminishing_factor = 1.0
    
    for item in risk_items:
        total_impact_expected += int(item.annual_impact_expected * diminishing_factor)
        diminishing_factor *= 0.75  # Jokainen seuraava riski vaikuttaa vähemmän
    
    # Cap total impact to max 40% of digital revenue (realistinen yläraja)
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
        confidence_note = 'Rajoitettu data - suosittelemme lisäanalyysiä' if language == 'fi' else 'Limited data - we recommend additional analysis'
    
    methodology_note = (
        f"Laskelma perustuu {profile['name'][language]}-toimialan keskiarvoihin: "
        f"{int(profile['digital_revenue_share']*100)}% liikevaihdosta digitaalista, "
        f"{int(profile['organic_traffic_share']*100)}% liikenteestä orgaanista, "
        f"{int(profile['mobile_traffic_share']*100)}% mobiilikäyttäjiä."
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
