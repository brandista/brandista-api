# -*- coding: utf-8 -*-
"""
Unit tests for _check_schema_markup in main.py

Tests structured data scoring with real-world schema examples
including BemuFix.fi's comprehensive AutoRepair schema.
"""

import pytest
import json
import sys
import os
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

# main.py has heavy imports (jwt, openai, etc), so we mock them and extract the function
# by reading the source and extracting just what we need
from agents.scoring_constants import factor_status

# Import _check_schema_markup without importing all of main.py
# We extract the function source and exec it in a clean namespace
_ns = {'json': json, 'factor_status': factor_status, 'BeautifulSoup': BeautifulSoup}

# Define the AISearchFactor as a simple dataclass substitute
class AISearchFactor:
    def __init__(self, name="", score=0, status="poor", findings=None, recommendations=None):
        self.name = name
        self.score = score
        self.status = status
        self.findings = findings or []
        self.recommendations = recommendations or []

_ns['AISearchFactor'] = AISearchFactor

# Read and exec just the _check_schema_markup function from main.py
_main_path = os.path.join(os.path.dirname(__file__), '..', '..', 'main.py')
with open(_main_path, 'r') as f:
    _source = f.read()

# Extract the function (from 'def _check_schema_markup' to next function at same indent)
import re
_match = re.search(
    r'(def _check_schema_markup\(html: str, soup: BeautifulSoup\) -> AISearchFactor:.*?)(?=\ndef [a-z_])',
    _source, re.DOTALL
)
if _match:
    # Fix type hint for our namespace
    _func_source = _match.group(1).replace('-> AISearchFactor:', ':')
    exec(_func_source, _ns)

_check_schema_markup = _ns.get('_check_schema_markup')
if not _check_schema_markup:
    pytest.skip("Could not extract _check_schema_markup from main.py", allow_module_level=True)


def _make_html(jsonld_data=None, og_tags=None, microdata=False):
    """Helper: build minimal HTML with optional JSON-LD, OG tags, microdata."""
    parts = ['<html><head>']
    if jsonld_data is not None:
        data_str = json.dumps(jsonld_data, ensure_ascii=False)
        parts.append(f'<script type="application/ld+json">{data_str}</script>')
    if og_tags:
        for prop, content in og_tags.items():
            parts.append(f'<meta property="{prop}" content="{content}">')
    parts.append('</head><body>')
    if microdata:
        parts.append('<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Test</span></div>')
    parts.append('</body></html>')
    html = ''.join(parts)
    return html, BeautifulSoup(html, 'html.parser')


# =============================================================================
# Basic cases
# =============================================================================

class TestSchemaMarkupBasic:
    def test_no_schema_at_all(self):
        html, soup = _make_html()
        result = _check_schema_markup(html, soup)
        assert result.score == 0
        assert result.status == 'poor'
        assert len(result.recommendations) > 0

    def test_empty_jsonld(self):
        html, soup = _make_html(jsonld_data={})
        result = _check_schema_markup(html, soup)
        # JSON-LD exists but no @type
        assert result.score == 20  # Base score for JSON-LD

    def test_simple_organization(self):
        html, soup = _make_html(jsonld_data={
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Test Corp",
            "description": "A test company"
        })
        result = _check_schema_markup(html, soup)
        assert result.score >= 30  # 20 base + 5 org + 5 description


# =============================================================================
# BemuFix real-world schema
# =============================================================================

BEMUFIX_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "AutoRepair",
    "@id": "https://www.bemufix.fi/#organization",
    "name": "BemuFix",
    "alternateName": "BemuFIX BMW-erikoiskorjaamo",
    "url": "https://www.bemufix.fi",
    "description": "BMW-erikoiskorjaamo Helsingissä.",
    "telephone": "+358505477779",
    "email": "myynti@bemufix.fi",
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "Hankasuontie 7",
        "addressLocality": "Helsinki",
        "postalCode": "00390",
        "addressCountry": "FI"
    },
    "geo": {
        "@type": "GeoCoordinates",
        "latitude": "60.2295",
        "longitude": "24.8590"
    },
    "openingHoursSpecification": [{
        "@type": "OpeningHoursSpecification",
        "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "opens": "09:00",
        "closes": "18:00"
    }],
    "areaServed": [
        {"@type": "City", "name": "Helsinki"},
        {"@type": "City", "name": "Espoo"},
    ],
    "brand": [{"@type": "Brand", "name": "BMW"}],
    "hasOfferCatalog": {
        "@type": "OfferCatalog",
        "name": "BMW Huolto- ja korjaamopalvelut",
        "itemListElement": [
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "BMW määräaikaishuolto", "description": "CBS huolto"}},
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "BMW vikadiagnoosi", "description": "ISTA diagnostiikka"}},
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "BMW korjaustyöt", "description": "Korjaukset"}},
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "Öljynvaihto", "description": "Premium-öljynvaihto"}},
            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "Renkaanvaihto", "description": "Renkaat"}},
        ]
    }
}


class TestBemuFixSchema:
    def test_finds_autorepair_type(self):
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert any('AutoRepair' in f for f in result.findings)

    def test_finds_nested_commercial_types(self):
        """Recursive parsing must find OfferCatalog, Offer, Service inside AutoRepair"""
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        findings_text = ' '.join(result.findings)
        assert 'Commercial' in findings_text or 'Product/Service/Offer' in findings_text

    def test_finds_address_and_geo(self):
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert any('address/geo' in f for f in result.findings)

    def test_finds_rich_catalog(self):
        """Should detect OfferCatalog with 5 offers"""
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert any('catalog' in f.lower() for f in result.findings)

    def test_score_above_55(self):
        """BemuFix schema is comprehensive, should score well"""
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert result.score >= 55, f"BemuFix schema scored {result.score}, expected >= 55"

    def test_recommends_faqpage(self):
        """Even with good schema, should still recommend FAQPage"""
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert any('FAQ' in r for r in result.recommendations)

    def test_status_is_good_or_better(self):
        html, soup = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        result = _check_schema_markup(html, soup)
        assert result.status in ('excellent', 'good'), f"Status is '{result.status}', expected good or better"

    def test_with_og_tags_scores_higher(self):
        """Adding OG tags should boost score"""
        html_no_og, soup_no_og = _make_html(jsonld_data=BEMUFIX_SCHEMA)
        html_og, soup_og = _make_html(
            jsonld_data=BEMUFIX_SCHEMA,
            og_tags={
                'og:title': 'BemuFix - BMW-huolto Helsinki',
                'og:description': 'BMW-erikoiskorjaamo',
                'og:image': 'https://www.bemufix.fi/hero-garage.jpg',
                'og:type': 'website',
                'og:url': 'https://www.bemufix.fi',
            }
        )
        score_no_og = _check_schema_markup(html_no_og, soup_no_og).score
        score_og = _check_schema_markup(html_og, soup_og).score
        assert score_og > score_no_og, f"OG: {score_og} should be > no OG: {score_no_og}"


# =============================================================================
# @graph format (WordPress / Yoast style)
# =============================================================================

class TestGraphFormat:
    def test_graph_array(self):
        """WordPress/Yoast outputs @graph array"""
        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebSite", "name": "Test Site"},
                {"@type": "Organization", "name": "Test Corp", "description": "About us"},
                {"@type": "BreadcrumbList", "itemListElement": []}
            ]
        }
        html, soup = _make_html(jsonld_data=schema)
        result = _check_schema_markup(html, soup)
        findings_text = ' '.join(result.findings)
        assert 'Organization' in findings_text
        assert 'BreadcrumbList' in findings_text

    def test_graph_types_all_counted(self):
        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebSite", "name": "Test"},
                {"@type": "Organization", "name": "Test"},
                {"@type": "BreadcrumbList"},
                {"@type": "Article", "description": "Test article"},
                {"@type": "FAQPage", "mainEntity": []}
            ]
        }
        html, soup = _make_html(jsonld_data=schema)
        result = _check_schema_markup(html, soup)
        # Should get: 20 base + org 5 + breadcrumb 5 + content 10 + faq 10 + website 5 = type 35
        # quality: description 5, >=5 types 5 = 10
        # Total: 20 + 35 + 10 = 65
        assert result.score >= 60


# =============================================================================
# FAQ schema (highest value for AI)
# =============================================================================

class TestFAQSchema:
    def test_faq_removes_recommendation(self):
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "What is this?", "acceptedAnswer": {"@type": "Answer", "text": "A test"}}
            ]
        }
        html, soup = _make_html(jsonld_data=schema)
        result = _check_schema_markup(html, soup)
        assert not any('FAQ' in r for r in result.recommendations), "Should not recommend FAQ when FAQPage exists"

    def test_faq_gets_bonus(self):
        schema = {"@context": "https://schema.org", "@type": "FAQPage"}
        html, soup = _make_html(jsonld_data=schema)
        result = _check_schema_markup(html, soup)
        assert result.score >= 30  # 20 base + 10 FAQ type


# =============================================================================
# Microdata and Open Graph
# =============================================================================

class TestMicrodataAndOG:
    def test_microdata_bonus(self):
        html, soup = _make_html(microdata=True)
        result = _check_schema_markup(html, soup)
        assert result.score == 5  # Only microdata, no JSON-LD

    def test_og_tags_partial(self):
        html, soup = _make_html(og_tags={'og:title': 'Test', 'og:description': 'Desc'})
        result = _check_schema_markup(html, soup)
        assert result.score == 5  # Only 2 OG tags, partial bonus

    def test_og_tags_rich(self):
        html, soup = _make_html(og_tags={
            'og:title': 'Test', 'og:description': 'Desc',
            'og:image': 'img.jpg', 'og:type': 'website'
        })
        result = _check_schema_markup(html, soup)
        assert result.score == 10  # 4+ OG tags = full bonus
