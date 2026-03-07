# -*- coding: utf-8 -*-
"""
Gustav 2.0 — Guardian Pulse

Lightweight monitoring checks between full analyses.
Detects competitor changes, anomalies, and triggers alerts.

This module defines the data structures and logic for pulse checks.
Actual scheduling and HTTP fetching is handled by the API layer.
"""

import logging
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

from .hallucination_guard import (
    IntelligenceGuard,
    DataSource,
    add_guardrails,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PulseCheck:
    """Result of a lightweight pulse check."""
    url: str
    status: str              # 'ok' | 'warning' | 'critical'
    checks_performed: int = 0
    changes_detected: int = 0
    alerts: List[Dict] = field(default_factory=list)
    competitor_changes: List[Dict] = field(default_factory=list)
    checked_at: str = ''

    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CompetitorChange:
    """Detected change on a competitor's website."""
    competitor_url: str
    competitor_name: str
    change_type: str           # 'new_pages' | 'content_expansion' | 'schema_upgrade' | 'meta_change'
    severity: str              # 'high' | 'medium' | 'low'
    business_impact: str       # 'competitive_move' | 'content_expansion' | 'technical_upgrade' | 'no_threat'
    details_fi: str
    details_en: str
    recommended_response_fi: str = ''
    recommended_response_en: str = ''
    detected_at: str = ''

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# CONTENT HASH TRACKER
# =============================================================================

class ContentHashTracker:
    """
    Tracks content hashes for change detection.

    Stores hashes of key page elements to detect meaningful changes
    (not just cosmetic updates).
    """

    def __init__(self):
        # {url: {element_key: hash_value}}
        self._hashes: Dict[str, Dict[str, str]] = {}

    def compute_hashes(self, url: str, page_data: Dict) -> Dict[str, str]:
        """
        Compute hashes of key page elements.

        Args:
            page_data: Dict with keys like 'title', 'meta_description',
                       'word_count', 'schema_types', 'h1_tags', 'page_count'
        """
        hashes = {}

        # Title
        title = page_data.get('title', '')
        if title:
            hashes['title'] = hashlib.md5(title.encode()).hexdigest()[:8]

        # Meta description
        meta = page_data.get('meta_description', '')
        if meta:
            hashes['meta_description'] = hashlib.md5(meta.encode()).hexdigest()[:8]

        # Content length bucket (changes if word count shifts significantly)
        word_count = page_data.get('word_count', 0)
        # Bucket: 0-500, 500-1000, 1000-2000, 2000+
        bucket = word_count // 500
        hashes['content_bucket'] = str(bucket)

        # Schema types
        schemas = sorted(page_data.get('schema_types', []))
        if schemas:
            hashes['schemas'] = hashlib.md5(
                ','.join(schemas).encode()
            ).hexdigest()[:8]

        # Page count (from sitemap or link analysis)
        page_count = page_data.get('page_count', 0)
        hashes['page_count'] = str(page_count)

        return hashes

    def detect_changes(
        self, url: str, new_hashes: Dict[str, str], competitor_name: str
    ) -> List[CompetitorChange]:
        """
        Compare new hashes against stored ones. Returns list of changes.
        """
        old_hashes = self._hashes.get(url, {})
        changes = []

        if not old_hashes:
            # First check — store and return (no changes to detect)
            self._hashes[url] = new_hashes
            return []

        # Title change
        if (old_hashes.get('title') and new_hashes.get('title') and
                old_hashes['title'] != new_hashes['title']):
            changes.append(CompetitorChange(
                competitor_url=url,
                competitor_name=competitor_name,
                change_type='meta_change',
                severity='medium',
                business_impact='technical_upgrade',
                details_fi=f'{competitor_name} muutti sivustonsa otsikkoa — mahdollisesti uusi kohdistus',
                details_en=f'{competitor_name} changed their site title — possible new targeting',
                recommended_response_fi='Tarkista kohdistuuko muutos samoihin avainsanoihin kuin sinun sivustosi.',
                recommended_response_en='Check if the change targets the same keywords as your site.',
            ))

        # Content expansion
        old_bucket = int(old_hashes.get('content_bucket', '0'))
        new_bucket = int(new_hashes.get('content_bucket', '0'))
        if new_bucket > old_bucket:
            growth_pct = ((new_bucket - old_bucket) / max(1, old_bucket)) * 100
            changes.append(CompetitorChange(
                competitor_url=url,
                competitor_name=competitor_name,
                change_type='content_expansion',
                severity='medium' if new_bucket - old_bucket <= 2 else 'high',
                business_impact='content_expansion',
                details_fi=(
                    f'{competitor_name} kasvatti sisältöään merkittävästi '
                    f'(sisältöluokka {old_bucket} → {new_bucket})'
                ),
                details_en=(
                    f'{competitor_name} significantly expanded their content '
                    f'(content bucket {old_bucket} → {new_bucket})'
                ),
                recommended_response_fi='Harkitse vastaavan sisällön julkaisemista.',
                recommended_response_en='Consider publishing comparable content.',
            ))

        # Schema changes
        if (old_hashes.get('schemas') and new_hashes.get('schemas') and
                old_hashes['schemas'] != new_hashes['schemas']):
            changes.append(CompetitorChange(
                competitor_url=url,
                competitor_name=competitor_name,
                change_type='schema_upgrade',
                severity='low',
                business_impact='technical_upgrade',
                details_fi=f'{competitor_name} muutti schema-merkintöjään',
                details_en=f'{competitor_name} updated their schema markup',
                recommended_response_fi='Tarkista onko sinun schema-merkintäsi ajan tasalla.',
                recommended_response_en='Check if your schema markup is up to date.',
            ))

        # New pages
        old_pages = int(old_hashes.get('page_count', '0'))
        new_pages = int(new_hashes.get('page_count', '0'))
        if new_pages > old_pages:
            diff = new_pages - old_pages
            changes.append(CompetitorChange(
                competitor_url=url,
                competitor_name=competitor_name,
                change_type='new_pages',
                severity='high' if diff >= 3 else 'medium',
                business_impact='competitive_move',
                details_fi=f'{competitor_name} lisäsi {diff} uutta sivua (yhteensä {new_pages})',
                details_en=f'{competitor_name} added {diff} new pages (total {new_pages})',
                recommended_response_fi='Tarkista kohdistuvatko uudet sivut avainsanoihisi.',
                recommended_response_en='Check if new pages target your keywords.',
            ))

        # Update stored hashes
        self._hashes[url] = new_hashes

        return changes


# =============================================================================
# PULSE CHECKER
# =============================================================================

class GuardianPulse:
    """
    Lightweight monitoring between full analyses.

    Usage:
        pulse = GuardianPulse()

        # Register competitors to monitor
        pulse.register_monitoring(
            url='https://bemufix.fi',
            competitor_urls=['https://dasauto.fi'],
            competitor_names={'https://dasauto.fi': 'Das Auto'},
        )

        # Run pulse check (page_data comes from HTTP fetch in API layer)
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450},
            competitor_data=[
                {'url': 'https://dasauto.fi', 'page_data': {...}},
            ],
        )
    """

    def __init__(self):
        self.hash_tracker = ContentHashTracker()
        self.guard = IntelligenceGuard()

        # {url: {competitor_urls: [...], competitor_names: {...}}}
        self._monitored: Dict[str, Dict] = {}

    def register_monitoring(
        self,
        url: str,
        competitor_urls: List[str],
        competitor_names: Dict[str, str] = None,
    ):
        """Register a URL and its competitors for pulse monitoring."""
        self._monitored[url] = {
            'competitor_urls': competitor_urls,
            'competitor_names': competitor_names or {},
        }

    def run_pulse_check(
        self,
        url: str,
        your_status: Dict,
        competitor_data: List[Dict] = None,
    ) -> PulseCheck:
        """
        Run a lightweight pulse check.

        Args:
            url: Your website URL
            your_status: {'status_code': 200, 'response_time_ms': 450, 'ssl_valid': True}
            competitor_data: [{'url': '...', 'page_data': {...}}]
        """
        alerts = []
        changes = []
        checks = 0

        # 1. Your site health checks
        checks += 1
        status_code = your_status.get('status_code', 0)
        if status_code >= 500:
            alerts.append({
                'type': 'site_down',
                'severity': 'critical',
                'message_fi': f'Sivustosi palauttaa HTTP {status_code} -virheen!',
                'message_en': f'Your site returns HTTP {status_code} error!',
            })
        elif status_code >= 400:
            alerts.append({
                'type': 'site_error',
                'severity': 'high',
                'message_fi': f'Sivustosi palauttaa HTTP {status_code} -virheen.',
                'message_en': f'Your site returns HTTP {status_code} error.',
            })

        # Response time check
        checks += 1
        response_time = your_status.get('response_time_ms', 0)
        if response_time > 3000:
            alerts.append({
                'type': 'slow_response',
                'severity': 'high',
                'message_fi': f'Sivustosi latautuu hitaasti ({response_time}ms). Tavoite: alle 3000ms.',
                'message_en': f'Your site loads slowly ({response_time}ms). Target: under 3000ms.',
            })
        elif response_time > 1500:
            alerts.append({
                'type': 'slow_response',
                'severity': 'medium',
                'message_fi': f'Sivustosi latautuminen kestää {response_time}ms. Optimointia suositellaan.',
                'message_en': f'Your site takes {response_time}ms to load. Optimization recommended.',
            })

        # SSL check
        checks += 1
        if not your_status.get('ssl_valid', True):
            alerts.append({
                'type': 'ssl_issue',
                'severity': 'critical',
                'message_fi': 'SSL-sertifikaatissa ongelma! Asiakkaat näkevät varoituksen.',
                'message_en': 'SSL certificate issue! Customers will see a warning.',
            })

        # 2. Competitor change detection
        monitored = self._monitored.get(url, {})
        comp_names = monitored.get('competitor_names', {})

        for comp_data in (competitor_data or []):
            comp_url = comp_data.get('url', '')
            page_data = comp_data.get('page_data', {})
            comp_name = comp_names.get(comp_url, comp_url)

            checks += 1
            new_hashes = self.hash_tracker.compute_hashes(comp_url, page_data)
            detected = self.hash_tracker.detect_changes(comp_url, new_hashes, comp_name)

            for change in detected:
                changes.append(change.to_dict())

                # Create alert for significant changes
                if change.severity in ('high', 'critical'):
                    alerts.append({
                        'type': 'competitor_change',
                        'severity': change.severity,
                        'message_fi': change.details_fi,
                        'message_en': change.details_en,
                        'competitor': comp_name,
                    })

        # Determine overall status
        if any(a.get('severity') == 'critical' for a in alerts):
            status = 'critical'
        elif any(a.get('severity') == 'high' for a in alerts):
            status = 'warning'
        else:
            status = 'ok'

        return PulseCheck(
            url=url,
            status=status,
            checks_performed=checks,
            changes_detected=len(changes),
            alerts=alerts,
            competitor_changes=changes,
        )

    # =========================================================================
    # LLM PROMPT (for contextual alerts)
    # =========================================================================

    def build_alert_prompt(
        self,
        change: CompetitorChange,
        your_score: int,
        comp_score: int,
        your_weaknesses: List[str] = None,
    ) -> str:
        """Build LLM prompt for contextual pulse alert.

        Anti-hallucination: only verified change data in prompt.
        """
        weaknesses_str = '\n'.join([f'  - {w}' for w in (your_weaknesses or [])]) or '  (ei tunnettuja heikkouksia)'

        prompt = f"""Olet liiketoiminnan varhaisen varoituksen järjestelmä.

FAKTAT (käytä VAIN näitä):
- Kilpailija: {change.competitor_name} ({change.competitor_url})
- Muutos: {change.details_fi}
- Muutoksen tyyppi: {change.change_type}
- Vakavuus: {change.severity}

KONTEKSTI:
- Sinun pisteesi: {your_score}/100
- Kilpailijan pisteesi: {comp_score}/100

SINUN HEIKKOUTESI tällä alueella:
{weaknesses_str}

OHJE: Kirjoita 2-3 lauseen hälytys suomeksi. Kerro:
1. Mitä tapahtui (konkreettisesti)
2. Miten se vaikuttaa sinuun
3. Yksi konkreettinen toimenpide

Pidä tiiviinä. Tämä on push-ilmoitus.
Merkitse kaikki arviot sanalla "arviolta"."""

        return add_guardrails(prompt, 'fi')
