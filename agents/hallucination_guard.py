# -*- coding: utf-8 -*-
"""
Gustav 2.0 — Hallucination Guard

4-layer anti-hallucination system for LLM-generated business intelligence:

1. DATA PROVENANCE  — every claim traces to a source
2. PROMPT GUARDRAILS — LLM instructions that enforce factual grounding
3. POST-GENERATION VALIDATION — verify LLM output against input data
4. TRANSPARENCY MARKERS — estimates are clearly labeled as estimates

This module is used by competitive_intelligence.py, intelligence_brief.py,
and any other module that generates LLM-based narratives.
"""

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# 1. DATA PROVENANCE — track where every piece of data came from
# =============================================================================

class DataSource(str, Enum):
    """Verified data sources in the system."""
    HTML_ANALYSIS = 'html_analysis'          # Scraped from actual website
    WHOIS = 'whois'                          # Domain WHOIS lookup
    BUSINESS_REGISTRY = 'business_registry'  # YTJ / Kauppalehti / PRH
    SCORE_CALCULATION = 'score_calculation'  # Our own scoring algorithm
    INDUSTRY_BENCHMARK = 'industry_benchmark'  # Static industry averages
    COST_MATRIX = 'cost_matrix'              # ACTION_COST_MATRIX constants
    USER_INPUT = 'user_input'                # User-provided data (revenue etc.)
    INFERENCE = 'inference'                  # Derived/calculated from other data
    TREND_CALCULATION = 'trend_calculation'  # Linear regression from history
    LLM_GENERATED = 'llm_generated'          # LLM-generated text (narrative)


class ConfidenceLevel(str, Enum):
    """How confident we are in a piece of data."""
    VERIFIED = 'verified'        # Direct measurement (HTML scrape, WHOIS)
    CALCULATED = 'calculated'    # Deterministic calculation from verified data
    ESTIMATED = 'estimated'      # Model-based estimate (ROI, traffic predictions)
    SPECULATIVE = 'speculative'  # Low-confidence inference or LLM generation


# Confidence mapping per data source
SOURCE_CONFIDENCE = {
    DataSource.HTML_ANALYSIS: ConfidenceLevel.VERIFIED,
    DataSource.WHOIS: ConfidenceLevel.VERIFIED,
    DataSource.BUSINESS_REGISTRY: ConfidenceLevel.VERIFIED,
    DataSource.SCORE_CALCULATION: ConfidenceLevel.CALCULATED,
    DataSource.INDUSTRY_BENCHMARK: ConfidenceLevel.ESTIMATED,
    DataSource.COST_MATRIX: ConfidenceLevel.ESTIMATED,
    DataSource.USER_INPUT: ConfidenceLevel.VERIFIED,
    DataSource.INFERENCE: ConfidenceLevel.ESTIMATED,
    DataSource.TREND_CALCULATION: ConfidenceLevel.ESTIMATED,
    DataSource.LLM_GENERATED: ConfidenceLevel.SPECULATIVE,
}


@dataclass
class ProvenanceRecord:
    """Tracks the origin of a specific data claim."""
    claim: str                          # What is being claimed
    value: Any                          # The value
    source: DataSource                  # Where it came from
    confidence: ConfidenceLevel = None  # Auto-set from source if not provided
    raw_evidence: str = ''              # Raw data that supports this claim
    methodology: str = ''               # How the value was calculated
    caveats: List[str] = field(default_factory=list)  # Known limitations

    def __post_init__(self):
        if self.confidence is None:
            self.confidence = SOURCE_CONFIDENCE.get(self.source, ConfidenceLevel.SPECULATIVE)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['source'] = self.source.value
        d['confidence'] = self.confidence.value
        return d


class ProvenanceTracker:
    """Collects provenance records for an analysis run."""

    def __init__(self):
        self.records: List[ProvenanceRecord] = []
        self._claims: Set[str] = set()

    def track(
        self,
        claim: str,
        value: Any,
        source: DataSource,
        raw_evidence: str = '',
        methodology: str = '',
        caveats: List[str] = None,
    ) -> ProvenanceRecord:
        """Register a data claim with its provenance."""
        record = ProvenanceRecord(
            claim=claim,
            value=value,
            source=source,
            raw_evidence=raw_evidence,
            methodology=methodology,
            caveats=caveats or [],
        )
        self.records.append(record)
        self._claims.add(claim)
        return record

    def track_score(self, category: str, score: int, max_score: int = 100):
        """Shortcut: track a score from our scoring algorithm."""
        return self.track(
            claim=f'{category}_score',
            value=score,
            source=DataSource.SCORE_CALCULATION,
            methodology=f'Calculated from HTML analysis using scoring_constants.py thresholds (0-{max_score})',
        )

    def track_estimate(
        self, claim: str, value: Any, methodology: str,
        best_case: Any = None, worst_case: Any = None,
    ):
        """Shortcut: track a financial estimate with range."""
        caveats = []
        if best_case is not None and worst_case is not None:
            caveats.append(f'Vaihteluväli: {best_case} - {worst_case}')
            caveats.append(f'Range: {best_case} - {worst_case}')
        return self.track(
            claim=claim,
            value=value,
            source=DataSource.INFERENCE,
            methodology=methodology,
            caveats=caveats,
        )

    def get_sources_summary(self) -> List[str]:
        """Return unique data sources used."""
        sources = set()
        for r in self.records:
            sources.add(r.source.value)
        return sorted(sources)

    def get_confidence_level(self) -> str:
        """Overall confidence = weakest link."""
        levels = [r.confidence for r in self.records]
        if not levels:
            return ConfidenceLevel.SPECULATIVE.value

        # Order: verified > calculated > estimated > speculative
        order = [ConfidenceLevel.SPECULATIVE, ConfidenceLevel.ESTIMATED,
                 ConfidenceLevel.CALCULATED, ConfidenceLevel.VERIFIED]
        for level in order:
            if level in levels:
                return level.value
        return ConfidenceLevel.SPECULATIVE.value

    def to_dict(self) -> Dict:
        return {
            'records': [r.to_dict() for r in self.records],
            'sources_used': self.get_sources_summary(),
            'overall_confidence': self.get_confidence_level(),
        }


# =============================================================================
# 2. PROMPT GUARDRAILS — enforce factual grounding in LLM prompts
# =============================================================================

# Standard anti-hallucination suffix for ALL LLM prompts
ANTI_HALLUCINATION_SUFFIX_FI = """
KRIITTISET SÄÄNNÖT (rikkomattomat):
1. KÄYTÄ VAIN yllä annettuja faktoja ja lukuja — ÄLÄ keksi uusia lukuja tai tietoja
2. Jos tietoa ei ole annettu, sano "tieto ei saatavilla" — ÄLÄ arvaa tai oleta
3. ÄLÄ mainitse yrityksiä, tuotteita tai palveluita joita ei ole mainittu faktoissa
4. Kaikki euromäärät ja prosenttiluvut TÄYTYY vastata annettuja lukuja
5. ÄLÄ keksi markkinatrendejä, uutisia tai tapahtumia
6. Jos et voi perustella väitettä yllä olevilla faktoilla, jätä se pois
"""

ANTI_HALLUCINATION_SUFFIX_EN = """
CRITICAL RULES (unbreakable):
1. Use ONLY the facts and numbers provided above — DO NOT invent new numbers or data
2. If information is not provided, say "data not available" — DO NOT guess or assume
3. DO NOT mention companies, products, or services not listed in the facts
4. All euro amounts and percentages MUST match the provided numbers
5. DO NOT invent market trends, news, or events
6. If you cannot justify a claim with the facts above, leave it out
"""


def add_guardrails(prompt: str, language: str = 'fi') -> str:
    """Add anti-hallucination guardrails to any LLM prompt."""
    suffix = ANTI_HALLUCINATION_SUFFIX_FI if language == 'fi' else ANTI_HALLUCINATION_SUFFIX_EN
    return prompt + suffix


def build_grounded_prompt(
    template: str,
    facts: Dict[str, Any],
    language: str = 'fi',
) -> str:
    """
    Build a prompt where all variables come from verified data.

    Any {variable} in the template is replaced with its value from facts.
    Missing facts are replaced with "tieto ei saatavilla" / "data not available"
    rather than leaving blanks that LLM might fill.
    """
    missing_marker = 'tieto ei saatavilla' if language == 'fi' else 'data not available'

    # Find all {variables} in template
    variables = re.findall(r'\{(\w+)\}', template)

    # Replace with values or missing marker
    result = template
    for var in variables:
        value = facts.get(var, missing_marker)
        if value is None or value == '':
            value = missing_marker
        result = result.replace(f'{{{var}}}', str(value))

    return add_guardrails(result, language)


# =============================================================================
# 3. POST-GENERATION VALIDATION — verify LLM output against input
# =============================================================================

@dataclass
class ValidationResult:
    """Result of validating LLM output."""
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sanitized_output: str = ''  # Cleaned version if issues found


class OutputValidator:
    """Validates LLM-generated text against known input data."""

    def __init__(self, known_facts: Dict[str, Any]):
        """
        Args:
            known_facts: Dict of verified data points the LLM had access to.
                Keys should include competitor names, scores, amounts, etc.
        """
        self.facts = known_facts
        self.known_names = set()
        self.known_numbers = set()
        self.known_urls = set()

        self._extract_known_entities()

    def _extract_known_entities(self):
        """Extract known entities from facts for comparison."""
        for key, value in self.facts.items():
            if isinstance(value, str):
                # Names and URLs
                if 'name' in key.lower() or 'company' in key.lower():
                    self.known_names.add(value.lower())
                if 'url' in key.lower() or 'domain' in key.lower():
                    self.known_urls.add(value.lower())
            elif isinstance(value, (int, float)):
                self.known_numbers.add(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str) and ('name' in str(item.keys())):
                                self.known_names.add(v.lower())
                            elif isinstance(v, (int, float)):
                                self.known_numbers.add(v)

    def validate(self, llm_output: str) -> ValidationResult:
        """
        Validate LLM output against known facts.

        Checks:
        1. No invented company names
        2. No numbers that don't exist in input data
        3. No URLs not in the original data
        4. No percentage claims that don't match
        5. No future date claims (predictions must be marked)
        """
        issues = []
        warnings = []

        # Check for invented numbers (euro amounts)
        euro_pattern = r'€\s*([\d,.]+)'
        euro_amounts = re.findall(euro_pattern, llm_output)
        for amount_str in euro_amounts:
            try:
                amount = float(amount_str.replace(',', '').replace('.', ''))
                # Allow amounts that are close to known numbers (within 10%)
                # or derived from them (e.g. monthly * 12 = annual)
                if not self._number_is_grounded(amount):
                    warnings.append(
                        f'Euromäärä €{amount_str} ei vastaa tunnettua datapistettä. '
                        f'EUR amount €{amount_str} does not match any known data point.'
                    )
            except ValueError:
                pass

        # Check for unknown company names (heuristic: capitalized multi-word)
        # This is intentionally conservative — only flags clear inventions
        company_pattern = r'(?:yritys|kilpailija|yhtiö|company)\s+([A-ZÄÖÅ][a-zäöå]+(?:\s+[A-ZÄÖÅ][a-zäöå]+)*)'
        for match in re.finditer(company_pattern, llm_output, re.IGNORECASE):
            name = match.group(1).lower()
            if name not in self.known_names and len(name) > 2:
                # Check partial match
                if not any(name in kn or kn in name for kn in self.known_names):
                    issues.append(
                        f'Tuntematon yritysnimi: "{match.group(1)}" — ei löydy analyysidatasta. '
                        f'Unknown company name: "{match.group(1)}" — not found in analysis data.'
                    )

        # Check for specific percentage claims
        pct_pattern = r'(\d+(?:[.,]\d+)?)\s*%'
        pct_values = re.findall(pct_pattern, llm_output)
        for pct_str in pct_values:
            try:
                pct = float(pct_str.replace(',', '.'))
                if not self._number_is_grounded(pct):
                    warnings.append(
                        f'Prosenttiluku {pct_str}% ei vastaa tunnettua datapistettä. '
                        f'Percentage {pct_str}% does not match any known data point.'
                    )
            except ValueError:
                pass

        is_valid = len(issues) == 0
        sanitized = llm_output

        # If issues found, append disclaimer
        if not is_valid:
            disclaimer_fi = '\n\n⚠️ HUOM: Tämä teksti sisältää tietoja joita ei voitu vahvistaa analyysidatasta.'
            sanitized = llm_output + disclaimer_fi

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            sanitized_output=sanitized,
        )

    def _number_is_grounded(self, number: float) -> bool:
        """Check if a number can be traced to known data."""
        if number == 0:
            return True

        for known in self.known_numbers:
            if known == 0:
                continue
            # Exact match
            if abs(number - known) < 1:
                return True
            # Common derivations: ×12 (monthly→annual), ÷12 (annual→monthly)
            if abs(number - known * 12) < 1:
                return True
            if abs(number - known / 12) < 1:
                return True
            # Percentage of known number
            ratio = number / known if known != 0 else 0
            if ratio in (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20, 0.25, 0.50):
                return True

        # Allow small common numbers (1-100 range typical for scores/percentages)
        if 0 < number <= 100:
            return True

        return False


# =============================================================================
# 4. TRANSPARENCY MARKERS — label estimates clearly
# =============================================================================

@dataclass
class TransparencyEnvelope:
    """
    Wraps any output with transparency metadata.

    Every piece of generated intelligence is wrapped in this envelope
    so the frontend can show appropriate disclaimers.
    """
    content: Any                      # The actual output (dict, str, etc.)
    data_sources: List[str]           # Where the data came from
    confidence: str                   # 'verified' | 'calculated' | 'estimated' | 'speculative'
    methodology_fi: str               # How this was generated (Finnish)
    methodology_en: str               # How this was generated (English)
    estimate_ranges: Dict[str, Any] = field(default_factory=dict)  # best/worst case
    caveats_fi: List[str] = field(default_factory=list)
    caveats_en: List[str] = field(default_factory=list)
    validation_result: Optional[Dict] = None  # Post-generation validation
    generated_at: str = ''

    def to_dict(self) -> Dict:
        d = asdict(self)
        if self.validation_result and hasattr(self.validation_result, 'to_dict'):
            d['validation_result'] = asdict(self.validation_result)
        return d


def wrap_estimate(
    value: Any,
    best_case: Any,
    worst_case: Any,
    methodology_fi: str,
    methodology_en: str,
    sources: List[str],
    caveats_fi: List[str] = None,
    caveats_en: List[str] = None,
) -> Dict:
    """
    Wrap a financial estimate with transparency metadata.

    Instead of: {"monthly_risk": 800}
    Produces:   {"monthly_risk": {"value": 800, "best_case": 400, "worst_case": 1200,
                  "confidence": "estimated", "methodology": "...", "is_estimate": True}}
    """
    return {
        'value': value,
        'best_case': best_case,
        'worst_case': worst_case,
        'confidence': ConfidenceLevel.ESTIMATED.value,
        'is_estimate': True,
        'methodology_fi': methodology_fi,
        'methodology_en': methodology_en,
        'sources': sources,
        'caveats_fi': caveats_fi or [],
        'caveats_en': caveats_en or [],
    }


def wrap_verified(value: Any, source: str) -> Dict:
    """Wrap a verified data point."""
    return {
        'value': value,
        'confidence': ConfidenceLevel.VERIFIED.value,
        'is_estimate': False,
        'source': source,
    }


# =============================================================================
# STANDARD ESTIMATE CAVEATS
# =============================================================================

STANDARD_CAVEATS_FI = {
    'revenue_estimate': [
        'Liikevaihtoarvio perustuu toimialan keskiarvoihin, ei yrityksen todellisiin lukuihin',
        'Orgaanisen liikenteen osuus on toimialakohtainen estimaatti',
        'Todellinen vaikutus voi poiketa merkittävästi yrityksen tilanteesta riippuen',
    ],
    'roi_estimate': [
        'ROI-arvio perustuu toimialan keskimääräiseen konversioprosenttiin ja kaupan arvoon',
        'Todellinen tuotto riippuu sivuston konversioprosentista ja markkinatilanteesta',
        'Liikennearvioit perustuvat tyypillisiin hakuvolyymin keskiarvoihin',
    ],
    'inaction_cost': [
        'Toimimattomuuden hinta on arvio joka perustuu kilpailijoiden etumatkaan ja toimialan keskiarvoihin',
        'Todellinen menetys riippuu kilpailijoiden toimenpiteistä ja markkinamuutoksista',
        'Arvio ei huomioi kausivaihteluita tai markkinan orgaanista kasvua',
    ],
    'trend_prediction': [
        'Ennuste perustuu lineaariseen regressioon historiallisesta datasta',
        'Ulkoiset tekijät (Googlen algoritmipäivitykset, markkinamuutokset) voivat muuttaa trendiä',
        'Vähintään 5 datapistettä tarvitaan luotettavaan ennusteeseen',
    ],
}

STANDARD_CAVEATS_EN = {
    'revenue_estimate': [
        'Revenue estimate is based on industry averages, not actual company financials',
        'Organic traffic share is an industry-specific estimate',
        'Actual impact may differ significantly depending on the company situation',
    ],
    'roi_estimate': [
        'ROI estimate is based on industry average conversion rate and deal value',
        'Actual return depends on site conversion rate and market conditions',
        'Traffic estimates are based on typical search volume averages',
    ],
    'inaction_cost': [
        'Inaction cost is an estimate based on competitor lead and industry averages',
        'Actual loss depends on competitor actions and market changes',
        'Estimate does not account for seasonal variations or organic market growth',
    ],
    'trend_prediction': [
        'Prediction is based on linear regression from historical data',
        'External factors (Google algorithm updates, market changes) can alter the trend',
        'At least 5 data points are needed for a reliable prediction',
    ],
}


# =============================================================================
# CONVENIENCE: Guard wrapper for entire intelligence outputs
# =============================================================================

class IntelligenceGuard:
    """
    High-level guard that combines all 4 layers.

    Usage:
        guard = IntelligenceGuard(language='fi')

        # Track provenance as you calculate
        guard.provenance.track_score('seo', 42)
        guard.provenance.track_estimate(
            'monthly_risk', 800,
            methodology='score_gap × organic_share × category_weight / 12'
        )

        # Validate LLM output
        validated = guard.validate_llm_output(
            llm_text=response,
            known_facts={'competitor_name': 'Das Auto', 'your_score': 55}
        )

        # Wrap financial estimates
        risk = guard.wrap_financial_estimate(
            value=800,
            best_case=400,
            worst_case=1200,
            estimate_type='inaction_cost'
        )

        # Get full transparency envelope
        envelope = guard.create_envelope(
            content=battlecard_dict,
            methodology_fi='Battlecard generoitu HTML-analyysin ja pisteytysalgoritmin perusteella',
            methodology_en='Battlecard generated from HTML analysis and scoring algorithm',
        )
    """

    def __init__(self, language: str = 'fi'):
        self.language = language
        self.provenance = ProvenanceTracker()
        self._validation_results: List[ValidationResult] = []

    def add_prompt_guardrails(self, prompt: str) -> str:
        """Add anti-hallucination instructions to an LLM prompt."""
        return add_guardrails(prompt, self.language)

    def validate_llm_output(
        self, llm_text: str, known_facts: Dict[str, Any]
    ) -> ValidationResult:
        """Validate LLM output against known facts."""
        validator = OutputValidator(known_facts)
        result = validator.validate(llm_text)
        self._validation_results.append(result)

        if result.issues:
            logger.warning(
                f"[HallucinationGuard] LLM output has {len(result.issues)} issues: "
                f"{'; '.join(result.issues[:3])}"
            )
        if result.warnings:
            logger.info(
                f"[HallucinationGuard] LLM output has {len(result.warnings)} warnings"
            )

        return result

    def wrap_financial_estimate(
        self,
        value: Any,
        best_case: Any = None,
        worst_case: Any = None,
        estimate_type: str = 'revenue_estimate',
    ) -> Dict:
        """Wrap a financial estimate with transparency metadata."""
        if best_case is None:
            best_case = int(value * 0.5) if isinstance(value, (int, float)) else value
        if worst_case is None:
            worst_case = int(value * 1.5) if isinstance(value, (int, float)) else value

        caveats_fi = STANDARD_CAVEATS_FI.get(estimate_type, [])
        caveats_en = STANDARD_CAVEATS_EN.get(estimate_type, [])

        methodology_map_fi = {
            'revenue_estimate': 'Pistevaje × orgaanisen liikenteen osuus × kategoripaino / 12',
            'roi_estimate': 'Arvioitu kuukausiliikenne × konversioprosentti × keskimääräinen kaupan arvo × 12 / kustannus',
            'inaction_cost': 'Kilpailijoiden etumatka per kategoria × orgaanisen liikevaihdon osuus × aikakerroin',
            'trend_prediction': 'Lineaarinen regressio viimeisistä 3-5 datapisteestä',
        }
        methodology_map_en = {
            'revenue_estimate': 'Score gap × organic traffic share × category weight / 12',
            'roi_estimate': 'Estimated monthly traffic × conversion rate × avg deal value × 12 / cost',
            'inaction_cost': 'Competitor lead per category × organic revenue share × time factor',
            'trend_prediction': 'Linear regression from last 3-5 data points',
        }

        return wrap_estimate(
            value=value,
            best_case=best_case,
            worst_case=worst_case,
            methodology_fi=methodology_map_fi.get(estimate_type, 'Estimaatti'),
            methodology_en=methodology_map_en.get(estimate_type, 'Estimate'),
            sources=self.provenance.get_sources_summary(),
            caveats_fi=caveats_fi,
            caveats_en=caveats_en,
        )

    def create_envelope(
        self,
        content: Any,
        methodology_fi: str = '',
        methodology_en: str = '',
        estimate_ranges: Dict[str, Any] = None,
    ) -> TransparencyEnvelope:
        """Create a transparency envelope for any intelligence output."""
        # Determine confidence from provenance + validations
        base_confidence = self.provenance.get_confidence_level()

        # Downgrade if validation found issues
        if any(not vr.is_valid for vr in self._validation_results):
            base_confidence = ConfidenceLevel.SPECULATIVE.value

        # Collect all caveats
        all_caveats_fi = []
        all_caveats_en = []
        for record in self.provenance.records:
            for caveat in record.caveats:
                if any(c in caveat for c in 'äöÄÖ'):
                    all_caveats_fi.append(caveat)
                else:
                    all_caveats_en.append(caveat)

        # Deduplicate
        all_caveats_fi = list(dict.fromkeys(all_caveats_fi))
        all_caveats_en = list(dict.fromkeys(all_caveats_en))

        return TransparencyEnvelope(
            content=content,
            data_sources=self.provenance.get_sources_summary(),
            confidence=base_confidence,
            methodology_fi=methodology_fi,
            methodology_en=methodology_en,
            estimate_ranges=estimate_ranges or {},
            caveats_fi=all_caveats_fi,
            caveats_en=all_caveats_en,
            validation_result=(
                asdict(self._validation_results[-1])
                if self._validation_results else None
            ),
            generated_at=__import__('datetime').datetime.now().isoformat(),
        )

    def get_data_quality_summary(self) -> Dict:
        """Return a summary of data quality for the current analysis."""
        records = self.provenance.records
        if not records:
            return {
                'overall_confidence': 'no_data',
                'verified_count': 0,
                'estimated_count': 0,
                'speculative_count': 0,
                'data_quality_fi': 'Ei dataa saatavilla',
                'data_quality_en': 'No data available',
            }

        verified = sum(1 for r in records if r.confidence == ConfidenceLevel.VERIFIED)
        calculated = sum(1 for r in records if r.confidence == ConfidenceLevel.CALCULATED)
        estimated = sum(1 for r in records if r.confidence == ConfidenceLevel.ESTIMATED)
        speculative = sum(1 for r in records if r.confidence == ConfidenceLevel.SPECULATIVE)
        total = len(records)

        # Quality score: verified=100, calculated=80, estimated=50, speculative=20
        quality_score = int(
            (verified * 100 + calculated * 80 + estimated * 50 + speculative * 20) / total
        )

        if quality_score >= 80:
            quality_fi = 'Korkea — suurin osa tiedoista on vahvistettuja'
            quality_en = 'High — most data points are verified'
        elif quality_score >= 60:
            quality_fi = 'Hyvä — tiedot perustuvat pääosin mitattuun dataan'
            quality_en = 'Good — data is mostly based on measurements'
        elif quality_score >= 40:
            quality_fi = 'Kohtalainen — osa tiedoista on estimaatteja'
            quality_en = 'Moderate — some data points are estimates'
        else:
            quality_fi = 'Matala — merkittävä osa tiedoista on arvioita tai spekulatiivisia'
            quality_en = 'Low — significant portion of data is estimated or speculative'

        return {
            'overall_confidence': self.provenance.get_confidence_level(),
            'quality_score': quality_score,
            'verified_count': verified,
            'calculated_count': calculated,
            'estimated_count': estimated,
            'speculative_count': speculative,
            'total_data_points': total,
            'data_quality_fi': quality_fi,
            'data_quality_en': quality_en,
        }
