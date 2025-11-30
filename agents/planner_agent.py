# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Planner Agent V2
📋 "The Project Manager" - 90-päivän roadmap ja ROI
ENHANCED: Rich action items with steps, owners, success metrics

2025 PRIORITY ORDER:
1. Conversion & UX (get more from existing traffic)
2. AI/GEO Visibility (ChatGPT, Perplexity readiness)
3. Content & Authority (E-E-A-T)
4. Technical Foundation (speed, mobile)
5. SEO comes naturally from above
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)

# ============================================================================
# RICH ACTION LIBRARY - Detailed, actionable tasks
# ============================================================================

ACTION_LIBRARY = {
    # ========================================
    # SECURITY & FOUNDATION
    # ========================================
    'ssl_setup': {
        'en': {
            'title': '🔒 SSL Certificate & HTTPS Setup',
            'description': 'Install SSL certificate and configure HTTPS. Google requires HTTPS for rankings.',
            'steps': [
                'Purchase/obtain SSL certificate (Let\'s Encrypt free or paid)',
                'Install certificate on web server',
                'Configure HTTP→HTTPS 301 redirect',
                'Update internal links to HTTPS',
                'Test all pages load correctly',
                'Set up HSTS header',
                'Submit HTTPS version to Google Search Console'
            ],
            'owner': 'Developer',
            'time_estimate': '3-5 hours',
            'success_metric': 'All pages via HTTPS, SSL Labs grade A',
            'priority': 'Critical',
            'category': 'security'
        },
        'fi': {
            'title': '🔒 SSL-sertifikaatti ja HTTPS',
            'description': 'Asenna SSL-sertifikaatti ja konfiguroi HTTPS. Google vaatii HTTPS:n hakutuloksiin.',
            'steps': [
                'Hanki SSL-sertifikaatti (Let\'s Encrypt ilmainen tai maksullinen)',
                'Asenna sertifikaatti palvelimelle',
                'Konfiguroi HTTP→HTTPS 301 uudelleenohjaus',
                'Päivitä sisäiset linkit HTTPS:ksi',
                'Testaa kaikkien sivujen latautuminen',
                'Aseta HSTS-header',
                'Lähetä HTTPS-versio Google Search Consoleen'
            ],
            'owner': 'Kehittäjä',
            'time_estimate': '3-5 tuntia',
            'success_metric': 'Kaikki sivut HTTPS:llä, SSL Labs arvosana A',
            'priority': 'Kriittinen',
            'category': 'security'
        }
    },
    
    'analytics_setup': {
        'en': {
            'title': '📊 Google Analytics 4 & Tracking Setup',
            'description': 'Install GA4 to collect data. You need 30 days of data before optimization.',
            'steps': [
                'Create GA4 property',
                'Install GA4 tag (GTM or direct)',
                'Define 3-5 conversion events',
                'Configure enhanced measurement',
                'Link to Google Search Console',
                'Set up custom events for key actions',
                'Create basic dashboard',
                'Test with GA4 DebugView'
            ],
            'owner': 'Marketing',
            'time_estimate': '4-6 hours',
            'success_metric': 'GA4 collecting data, 3+ conversion events tracked',
            'priority': 'Critical',
            'category': 'analytics'
        },
        'fi': {
            'title': '📊 Google Analytics 4 & Seuranta',
            'description': 'Asenna GA4 datan keräämiseksi. Tarvitset 30 päivää dataa ennen optimointia.',
            'steps': [
                'Luo GA4-property',
                'Asenna GA4-tagi (GTM tai suora)',
                'Määritä 3-5 konversiotapahtumaa',
                'Konfiguroi laajennettu mittaus',
                'Yhdistä Google Search Consoleen',
                'Aseta mukautetut tapahtumat',
                'Luo peruskontrollipaneeli',
                'Testaa GA4 DebugView:llä'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '4-6 tuntia',
            'success_metric': 'GA4 kerää dataa, 3+ konversiota seurannassa',
            'priority': 'Kriittinen',
            'category': 'analytics'
        }
    },
    
    # ========================================
    # SEO & CONTENT
    # ========================================
    'seo_foundation': {
        'en': {
            'title': '🎯 SEO Foundation: Titles, Metas & Structure',
            'description': 'Fix SEO basics on top 10 pages. Results visible in 2-4 weeks.',
            'steps': [
                'Identify top 10 pages by traffic',
                'Optimize titles: 50-60 chars, keyword + brand',
                'Write meta descriptions: 150-160 chars, compelling',
                'Fix H1 tags (exactly 1 per page)',
                'Fix heading hierarchy (H1→H2→H3)',
                'Add alt text to all images',
                'Create/update XML sitemap',
                'Submit sitemap to Search Console',
                'Add Organization schema markup'
            ],
            'owner': 'Marketing + Developer',
            'time_estimate': '8-12 hours',
            'success_metric': 'All top 10 pages optimized, 0 H1 errors',
            'priority': 'High',
            'category': 'seo'
        },
        'fi': {
            'title': '🎯 SEO-perusta: Otsikot, metat ja rakenne',
            'description': 'Korjaa SEO-perusteet top 10 sivuilla. Tulokset näkyvät 2-4 viikossa.',
            'steps': [
                'Tunnista top 10 sivua liikenteen mukaan',
                'Optimoi otsikot: 50-60 merkkiä, avainsana + brändi',
                'Kirjoita meta-kuvaukset: 150-160 merkkiä',
                'Korjaa H1-tagit (tasan 1 per sivu)',
                'Korjaa otsikkohierarkia (H1→H2→H3)',
                'Lisää alt-teksti kuviin',
                'Luo/päivitä XML-sivukartta',
                'Lähetä sivukartta Search Consoleen',
                'Lisää Organization schema'
            ],
            'owner': 'Markkinointi + Kehittäjä',
            'time_estimate': '8-12 tuntia',
            'success_metric': 'Kaikki top 10 sivua optimoitu, 0 H1-virhettä',
            'priority': 'Korkea',
            'category': 'seo'
        }
    },
    
    'meta_optimization': {
        'en': {
            'title': '📝 Meta Description Optimization',
            'description': 'Write compelling meta descriptions that increase click-through rates.',
            'steps': [
                'Audit current meta descriptions',
                'Research competitor descriptions',
                'Write unique descriptions for each page',
                'Include target keywords naturally',
                'Add call-to-action where appropriate',
                'Test with SERP preview tool',
                'Monitor CTR changes in Search Console'
            ],
            'owner': 'Marketing',
            'time_estimate': '4-6 hours',
            'success_metric': 'All pages have unique, optimized meta descriptions',
            'priority': 'High',
            'category': 'seo'
        },
        'fi': {
            'title': '📝 Meta-kuvausten optimointi',
            'description': 'Kirjoita houkuttelevat meta-kuvaukset jotka nostavat klikkausprosenttia.',
            'steps': [
                'Auditoi nykyiset meta-kuvaukset',
                'Tutki kilpailijoiden kuvauksia',
                'Kirjoita uniikki kuvaus jokaiselle sivulle',
                'Sisällytä avainsanat luonnollisesti',
                'Lisää toimintakehote tarvittaessa',
                'Testaa SERP-esikatselutyökalulla',
                'Seuraa CTR-muutoksia Search Consolessa'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '4-6 tuntia',
            'success_metric': 'Kaikilla sivuilla uniikki, optimoitu meta-kuvaus',
            'priority': 'Korkea',
            'category': 'seo'
        }
    },
    
    'h1_optimization': {
        'en': {
            'title': '📌 H1 Heading Optimization',
            'description': 'Add clear H1 headings to improve SEO and user experience.',
            'steps': [
                'Audit pages missing H1 tags',
                'Write keyword-rich H1 for each page',
                'Ensure only one H1 per page',
                'Make H1 descriptive and engaging',
                'Check heading hierarchy'
            ],
            'owner': 'Marketing',
            'time_estimate': '2-4 hours',
            'success_metric': 'Every page has exactly one optimized H1',
            'priority': 'High',
            'category': 'seo'
        },
        'fi': {
            'title': '📌 H1-otsikon optimointi',
            'description': 'Lisää selkeät H1-otsikot parantaaksesi SEO:ta ja käyttökokemusta.',
            'steps': [
                'Auditoi sivut joilta puuttuu H1',
                'Kirjoita avainsanarikas H1 jokaiselle sivulle',
                'Varmista vain yksi H1 per sivu',
                'Tee H1:stä kuvaava ja kiinnostava',
                'Tarkista otsikkohierarkia'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '2-4 tuntia',
            'success_metric': 'Jokaisella sivulla tasan yksi optimoitu H1',
            'priority': 'Korkea',
            'category': 'seo'
        }
    },
    
    'cta_optimization': {
        'en': {
            'title': '🎯 Clear Call-to-Action Implementation',
            'description': 'Add compelling CTAs to convert visitors into customers.',
            'steps': [
                'Audit current CTAs on key pages',
                'Define primary action for each page',
                'Design prominent CTA buttons',
                'Write action-oriented button text',
                'Place CTAs above the fold',
                'A/B test button colors and text',
                'Track CTA click rates'
            ],
            'owner': 'Marketing + Designer',
            'time_estimate': '4-8 hours',
            'success_metric': 'Every key page has clear, trackable CTA',
            'priority': 'High',
            'category': 'ux'
        },
        'fi': {
            'title': '🎯 Selkeä toimintakehote (CTA)',
            'description': 'Lisää houkuttelevat CTA:t kävijöiden konvertoimiseksi asiakkaiksi.',
            'steps': [
                'Auditoi nykyiset CTA:t avainasivuilla',
                'Määritä ensisijainen toiminto jokaiselle sivulle',
                'Suunnittele näkyvät CTA-napit',
                'Kirjoita toimintaan ohjaava teksti',
                'Sijoita CTA:t näkyvälle paikalle',
                'A/B-testaa nappien värejä ja tekstejä',
                'Seuraa CTA-klikkauksia'
            ],
            'owner': 'Markkinointi + Suunnittelija',
            'time_estimate': '4-8 tuntia',
            'success_metric': 'Jokaisella avainasivulla selkeä, seurattava CTA',
            'priority': 'Korkea',
            'category': 'ux'
        }
    },
    
    # ========================================
    # MOBILE & PERFORMANCE
    # ========================================
    'mobile_optimization': {
        'en': {
            'title': '📱 Mobile Optimization & Core Web Vitals',
            'description': 'Ensure mobile users have fast, smooth experience. 60%+ traffic is mobile.',
            'steps': [
                'Add viewport meta tag',
                'Test on real devices + Chrome DevTools',
                'Run PageSpeed Insights (target 70+)',
                'Compress images (<200KB each)',
                'Implement lazy loading',
                'Minify CSS and JavaScript',
                'Enable browser caching',
                'Fix tap targets (min 48x48px)',
                'Achieve Core Web Vitals: LCP <2.5s, CLS <0.1'
            ],
            'owner': 'Developer',
            'time_estimate': '10-15 hours',
            'success_metric': 'Mobile PageSpeed 70+, all Core Web Vitals "Good"',
            'priority': 'High',
            'category': 'mobile'
        },
        'fi': {
            'title': '📱 Mobiilioptimointi & Core Web Vitals',
            'description': 'Varmista mobiilikäyttäjille nopea, sujuva kokemus. 60%+ liikenteestä on mobiilia.',
            'steps': [
                'Lisää viewport meta tag',
                'Testaa oikeilla laitteilla + Chrome DevTools',
                'Aja PageSpeed Insights (tavoite 70+)',
                'Pakkaa kuvat (<200KB kukin)',
                'Ota käyttöön lazy loading',
                'Minifioi CSS ja JavaScript',
                'Ota käyttöön selaimen välimuisti',
                'Korjaa napautusalueet (min 48x48px)',
                'Saavuta Core Web Vitals: LCP <2.5s, CLS <0.1'
            ],
            'owner': 'Kehittäjä',
            'time_estimate': '10-15 tuntia',
            'success_metric': 'Mobiili PageSpeed 70+, kaikki Core Web Vitals "Hyvä"',
            'priority': 'Korkea',
            'category': 'mobile'
        }
    },
    
    'page_speed': {
        'en': {
            'title': '⚡ Page Speed Optimization',
            'description': 'Improve loading speed to reduce bounce rate and improve rankings.',
            'steps': [
                'Run PageSpeed Insights audit',
                'Optimize and compress images',
                'Enable GZIP compression',
                'Minify HTML, CSS, JavaScript',
                'Leverage browser caching',
                'Use CDN for static assets',
                'Defer non-critical JavaScript',
                'Optimize server response time'
            ],
            'owner': 'Developer',
            'time_estimate': '8-12 hours',
            'success_metric': 'PageSpeed score 80+ on desktop and mobile',
            'priority': 'High',
            'category': 'performance'
        },
        'fi': {
            'title': '⚡ Sivuston nopeuden optimointi',
            'description': 'Paranna latausnopeutta vähentääksesi poistumisprosenttia ja parantaaksesi sijoituksia.',
            'steps': [
                'Aja PageSpeed Insights -auditointi',
                'Optimoi ja pakkaa kuvat',
                'Ota käyttöön GZIP-pakkaus',
                'Minifioi HTML, CSS, JavaScript',
                'Hyödynnä selaimen välimuistia',
                'Käytä CDN:ää staattisille tiedostoille',
                'Viivästytä ei-kriittistä JavaScriptiä',
                'Optimoi palvelimen vasteaika'
            ],
            'owner': 'Kehittäjä',
            'time_estimate': '8-12 tuntia',
            'success_metric': 'PageSpeed-pisteet 80+ työpöydällä ja mobiilissa',
            'priority': 'Korkea',
            'category': 'performance'
        }
    },
    
    # ========================================
    # CONTENT & GROWTH
    # ========================================
    'content_strategy': {
        'en': {
            'title': '✍️ Content Strategy & Planning',
            'description': 'Plan high-quality content that attracts and converts ideal customers.',
            'steps': [
                'Research 10-15 target keywords',
                'Analyze search intent for each',
                'Identify 3-4 pillar topics',
                'Map 8-10 cluster subtopics per pillar',
                'Analyze competitor content',
                'Create content brief template',
                'Define content calendar for 90 days',
                'Set up editorial workflow'
            ],
            'owner': 'Content/Marketing',
            'time_estimate': '6-8 hours',
            'success_metric': 'Content calendar created, first brief complete',
            'priority': 'High',
            'category': 'content'
        },
        'fi': {
            'title': '✍️ Sisältöstrategia & suunnittelu',
            'description': 'Suunnittele laadukas sisältö joka houkuttelee ja konvertoi ideaaliasiakkaita.',
            'steps': [
                'Tutki 10-15 kohde-avainsanaa',
                'Analysoi hakutarkoitus jokaiselle',
                'Tunnista 3-4 pilariaiheita',
                'Kartoita 8-10 klusteriteemaa per pilari',
                'Analysoi kilpailijoiden sisältö',
                'Luo sisältöbriefin malli',
                'Määritä sisältökalenteri 90 päivälle',
                'Aseta toimitusprosessi'
            ],
            'owner': 'Sisältö/Markkinointi',
            'time_estimate': '6-8 tuntia',
            'success_metric': 'Sisältökalenteri luotu, ensimmäinen briefi valmis',
            'priority': 'Korkea',
            'category': 'content'
        }
    },
    
    'competitive_content_gap': {
        'en': {
            'title': '🎯 Close Competitive Content Gaps',
            'description': 'Identify and fix content areas where competitors outrank you.',
            'steps': [
                'Run competitor content gap analysis',
                'Prioritize by search volume × relevance',
                'Analyze top 5 ranking competitors',
                'Create superior content (longer, more actionable)',
                'Add unique value: data, case studies, tools',
                'Optimize for search intent',
                'Internal link from authority pages',
                'Promote on relevant channels'
            ],
            'owner': 'Content + Marketing',
            'time_estimate': '12-16 hours',
            'success_metric': '3 new pages ranking in top 10 within 30 days',
            'priority': 'High',
            'category': 'content'
        },
        'fi': {
            'title': '🎯 Sulje kilpailijoiden sisältöaukot',
            'description': 'Tunnista ja korjaa sisältöalueet joissa kilpailijat sijoittuvat paremmin.',
            'steps': [
                'Tee kilpailija-aukkianalyysi',
                'Priorisoi hakuvolyymin × relevanssin mukaan',
                'Analysoi top 5 kilpailijaa',
                'Luo ylivoimaista sisältöä',
                'Lisää uniikkia arvoa: dataa, caseja, työkaluja',
                'Optimoi hakutarkoitukselle',
                'Linkitä sisäisesti auktoriteettisivuilta',
                'Promoa relevanteissa kanavissa'
            ],
            'owner': 'Sisältö + Markkinointi',
            'time_estimate': '12-16 tuntia',
            'success_metric': '3 uutta sivua top 10:ssä 30 päivässä',
            'priority': 'Korkea',
            'category': 'content'
        }
    },
    
    # ========================================
    # CONVERSION & TRUST
    # ========================================
    'conversion_funnel': {
        'en': {
            'title': '💰 Conversion Funnel Optimization',
            'description': 'Find and fix the biggest leak in your funnel. Often 20-50% revenue boost.',
            'steps': [
                'Map current funnel stages',
                'Identify drop-off points in GA4',
                'Run heatmaps and session recordings',
                'Survey customers: why did you buy?',
                'Survey abandoners: why didn\'t you buy?',
                'Fix #1 friction point',
                'A/B test the fix for 2 weeks',
                'Measure revenue impact'
            ],
            'owner': 'Marketing + Product',
            'time_estimate': '10-14 hours',
            'success_metric': 'Identified and fixed #1 funnel leak, measured impact',
            'priority': 'Critical',
            'category': 'conversion'
        },
        'fi': {
            'title': '💰 Konversiosuppilon optimointi',
            'description': 'Löydä ja korjaa suurin vuoto suppilossasi. Usein 20-50% tulosboosti.',
            'steps': [
                'Kartoita nykyiset suppilovaiheet',
                'Tunnista poistumispisteet GA4:ssä',
                'Aja lämpökartat ja sessiotallenteet',
                'Kysy asiakkailta: miksi ostit?',
                'Kysy hylkääjiltä: miksi et ostanut?',
                'Korjaa #1 kitkakohta',
                'A/B-testaa korjaus 2 viikkoa',
                'Mittaa tulosvaikutus'
            ],
            'owner': 'Markkinointi + Tuote',
            'time_estimate': '10-14 tuntia',
            'success_metric': 'Tunnistettu ja korjattu #1 suppilovuoto, mitattu vaikutus',
            'priority': 'Kriittinen',
            'category': 'conversion'
        }
    },
    
    'social_proof': {
        'en': {
            'title': '⭐ Social Proof & Trust Signals',
            'description': 'Add credibility signals that increase conversion by 20-40%.',
            'steps': [
                'Collect 20+ customer testimonials',
                'Create 3-5 detailed case studies',
                'Add review schema markup',
                'Display real-time social proof',
                'Add trust badges (secure checkout, guarantees)',
                'Showcase media mentions, awards, logos',
                'Add video testimonials to landing pages',
                'Track conversion rate change'
            ],
            'owner': 'Marketing + Sales',
            'time_estimate': '10-12 hours',
            'success_metric': '20+ testimonials live, conversion +15%',
            'priority': 'High',
            'category': 'trust'
        },
        'fi': {
            'title': '⭐ Sosiaalinen todiste & luottamussignaalit',
            'description': 'Lisää uskottavuussignaaleja jotka nostavat konversiota 20-40%.',
            'steps': [
                'Kerää 20+ asiakassuositusta',
                'Luo 3-5 yksityiskohtaista case studya',
                'Lisää arvostelu-schema',
                'Näytä reaaliaikaista sosiaalista todistetta',
                'Lisää luottamusmerkit (turvallinen maksu, takuut)',
                'Esittele mediamainintoja, palkintoja, logoja',
                'Lisää videosuosituksia laskeutumissivuille',
                'Seuraa konversiomuutosta'
            ],
            'owner': 'Markkinointi + Myynti',
            'time_estimate': '10-12 tuntia',
            'success_metric': '20+ suositusta käytössä, konversio +15%',
            'priority': 'Korkea',
            'category': 'trust'
        }
    },
    
    # ========================================
    # EMAIL & AUTOMATION
    # ========================================
    'email_automation': {
        'en': {
            'title': '📧 Revenue-Driving Email Automation',
            'description': 'Set up 3 automated email flows that generate revenue on autopilot.',
            'steps': [
                'Segment list: new, engaged, inactive, customers',
                'Build Welcome series (3-5 emails)',
                'Build Abandoned cart flow (3 emails)',
                'Build Re-engagement flow (2 emails)',
                'A/B test subject lines',
                'Design mobile-first emails',
                'Set up tracking: opens, clicks, revenue',
                'Test flows with 10% of list first'
            ],
            'owner': 'Marketing',
            'time_estimate': '8-12 hours',
            'success_metric': '3 email flows live, generating measurable revenue',
            'priority': 'High',
            'category': 'email'
        },
        'fi': {
            'title': '📧 Tuottoa tuottava sähköpostiautomaatio',
            'description': 'Asenna 3 automatisoitua sähköpostivirtaa jotka tuottavat tuloja autopilotilla.',
            'steps': [
                'Segmentoi lista: uudet, aktiiviset, passiiviset, asiakkaat',
                'Rakenna Tervetuloa-sarja (3-5 sähköpostia)',
                'Rakenna Hylätty ostoskori -virta (3 sähköpostia)',
                'Rakenna Uudelleenaktivointi-virta (2 sähköpostia)',
                'A/B-testaa otsikkorivejä',
                'Suunnittele mobiili-ensin sähköpostit',
                'Aseta seuranta: avaukset, klikkaukset, tuotto',
                'Testaa virrat 10%:lla listasta ensin'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '8-12 tuntia',
            'success_metric': '3 sähköpostivirtaa käytössä, mitattavaa tuottoa',
            'priority': 'Korkea',
            'category': 'email'
        }
    },
    
    # ========================================
    # REVIEW & REPORTING
    # ========================================
    'review_optimize': {
        'en': {
            'title': '🎯 90-Day Review & Q2 Planning',
            'description': 'Review results, document wins, plan next quarter.',
            'steps': [
                'Compile metrics: traffic, rankings, conversions, revenue',
                'Compare pre vs post implementation',
                'Document quick wins and biggest ROI',
                'Identify ongoing issues',
                'Calculate total ROI',
                'Survey team for feedback',
                'Plan Q2 priorities',
                'Celebrate wins!'
            ],
            'owner': 'All',
            'time_estimate': '4-6 hours',
            'success_metric': 'Complete 90-day report, Q2 roadmap defined',
            'priority': 'High',
            'category': 'planning'
        },
        'fi': {
            'title': '🎯 90 päivän katsaus & Q2 suunnittelu',
            'description': 'Arvioi tulokset, dokumentoi voitot, suunnittele seuraava kvartaali.',
            'steps': [
                'Kokoa mittarit: liikenne, sijoitukset, konversiot, tuotto',
                'Vertaa ennen vs jälkeen toteutuksen',
                'Dokumentoi nopeat voitot ja paras ROI',
                'Tunnista jatkuvat haasteet',
                'Laske kokonais-ROI',
                'Kerää tiimin palaute',
                'Suunnittele Q2-prioriteetit',
                'Juhli voittoja!'
            ],
            'owner': 'Kaikki',
            'time_estimate': '4-6 tuntia',
            'success_metric': 'Taydellinen 90 paivan raportti, Q2-suunnitelma valmis',
            'priority': 'Korkea',
            'category': 'planning'
        }
    },
    
    # ========================================
    # AI/GEO OPTIMIZATION (2025+)
    # ========================================
    'ai_optimization': {
        'en': {
            'title': '🤖 AI Search Optimization (ChatGPT, Perplexity)',
            'description': 'Optimize your content to be found and recommended by AI search engines.',
            'steps': [
                'Write clear, factual content that AI can quote',
                'Add FAQ sections with direct answers',
                'Use structured data (Schema.org)',
                'Build topical authority clusters',
                'Create "best X for Y" style content',
                'Ensure fast page load (AI crawlers are impatient)',
                'Add author bios and credentials (E-E-A-T)',
                'Test your content in ChatGPT/Perplexity'
            ],
            'owner': 'Content + SEO',
            'time_estimate': '12-20 hours',
            'success_metric': 'Brand mentioned in AI search results',
            'priority': 'High',
            'category': 'ai_visibility'
        },
        'fi': {
            'title': '🤖 AI-hakuoptimointi (ChatGPT, Perplexity)',
            'description': 'Optimoi sisaltosi loytymaan ja suositeltavaksi AI-hakukoneissa.',
            'steps': [
                'Kirjoita selkeaa, faktuaalista sisaltoa jota AI voi lainata',
                'Lisaa UKK-osiot suorilla vastauksilla',
                'Kayta strukturoitua dataa (Schema.org)',
                'Rakenna aihe-auktoriteettiryppaat',
                'Luo "paras X:lle Y" -tyyppista sisaltoa',
                'Varmista nopea lataus (AI-crawlerit ovat karstamattomia)',
                'Lisaa kirjoittajien biot ja patevyydet (E-E-A-T)',
                'Testaa sisaltosi ChatGPT:ssa/Perplexityssa'
            ],
            'owner': 'Sisalto + SEO',
            'time_estimate': '12-20 tuntia',
            'success_metric': 'Brandi mainitaan AI-hakutuloksissa',
            'priority': 'Korkea',
            'category': 'ai_visibility'
        }
    },
    
    'authority_building': {
        'en': {
            'title': '🏆 Authority & E-E-A-T Building',
            'description': 'Establish expertise, experience, authoritativeness, and trust.',
            'steps': [
                'Create detailed author pages with credentials',
                'Add case studies and real results',
                'Get mentions on industry sites',
                'Publish original research or data',
                'Add customer testimonials with photos',
                'Display certifications and awards',
                'Create a compelling About page',
                'Build presence on LinkedIn/industry forums'
            ],
            'owner': 'Marketing',
            'time_estimate': '15-25 hours',
            'success_metric': 'Increased trust signals, more inbound links',
            'priority': 'High',
            'category': 'authority'
        },
        'fi': {
            'title': '🏆 Auktoriteetin & E-E-A-T rakentaminen',
            'description': 'Vahvista asiantuntemusta, kokemusta, auktoriteettia ja luotettavuutta.',
            'steps': [
                'Luo yksityiskohtaiset kirjoittajasivut patevyyksilla',
                'Lisaa tapaustutkimuksia ja oikeita tuloksia',
                'Hanki mainintoja alan sivustoilla',
                'Julkaise alkuperaista tutkimusta tai dataa',
                'Lisaa asiakasarvioita kuvilla',
                'Nayta sertifikaatit ja palkinnot',
                'Luo vakuuttava Tietoa meista -sivu',
                'Rakenna lasnaoloo LinkedInissa/alan foorumeilla'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '15-25 tuntia',
            'success_metric': 'Kasvaneet luottamussignaalit, enemman linkkeja',
            'priority': 'Korkea',
            'category': 'authority'
        }
    },
    
    'ux_improvements': {
        'en': {
            'title': '✨ UX & Conversion Improvements',
            'description': 'Improve user experience to increase conversions and engagement.',
            'steps': [
                'Simplify navigation (max 7 items)',
                'Add clear value proposition above fold',
                'Reduce form fields to minimum',
                'Add progress indicators for multi-step forms',
                'Improve readability (font size, contrast)',
                'Add sticky CTA buttons',
                'Test with real users (5 is enough)',
                'Implement feedback based on tests'
            ],
            'owner': 'Design + Dev',
            'time_estimate': '10-15 hours',
            'success_metric': 'Improved conversion rate, lower bounce rate',
            'priority': 'High',
            'category': 'ux'
        },
        'fi': {
            'title': '✨ UX & konversioparannukset',
            'description': 'Paranna kayttokokemusta lisataksesi konversioita ja sitoutumista.',
            'steps': [
                'Yksinkertaista navigaatio (max 7 kohdetta)',
                'Lisaa selkea arvolupaus naitton ylaosaan',
                'Vahenna lomakekenttiä minimiin',
                'Lisaa edistymisilmaisimet monivaihelomakkeisiin',
                'Paranna luettavuutta (fonttikoko, kontrasti)',
                'Lisaa kiinnitetyt CTA-napit',
                'Testaa oikeilla kayttajilla (5 riittaa)',
                'Toteuta palaute testien perusteella'
            ],
            'owner': 'Design + Kehitys',
            'time_estimate': '10-15 tuntia',
            'success_metric': 'Parantunut konversioprosentti, matalampi poistumisprosentti',
            'priority': 'Korkea',
            'category': 'ux'
        }
    },
    
    'trust_building': {
        'en': {
            'title': '⭐ Social Proof & Trust Signals',
            'description': 'Add elements that build trust and credibility with visitors.',
            'steps': [
                'Collect and display customer reviews',
                'Add client logos (with permission)',
                'Display trust badges (SSL, payment, certifications)',
                'Add real team photos',
                'Show social media follower counts',
                'Display awards and press mentions',
                'Add live chat or chatbot',
                'Create video testimonials'
            ],
            'owner': 'Marketing',
            'time_estimate': '8-12 hours',
            'success_metric': 'Increased trust metrics, more conversions',
            'priority': 'High',
            'category': 'trust'
        },
        'fi': {
            'title': '⭐ Sosiaalinen todiste & luottamussignaalit',
            'description': 'Lisaa elementteja jotka rakentavat luottamusta kavijoissa.',
            'steps': [
                'Keraa ja nayta asiakasarviot',
                'Lisaa asiakaslogot (luvalla)',
                'Nayta luottamussymbolit (SSL, maksu, sertifikaatit)',
                'Lisaa oikeat tiimikuvat',
                'Nayta sosiaalisen median seuraajamarat',
                'Nayta palkinnot ja medianakyyvyys',
                'Lisaa live-chat tai chatbot',
                'Luo videosuosituksia'
            ],
            'owner': 'Markkinointi',
            'time_estimate': '8-12 tuntia',
            'success_metric': 'Kasvaneet luottamusmittarit, enemman konversioita',
            'priority': 'Korkea',
            'category': 'trust'
        }
    },
    
    'quarterly_review': {
        'en': {
            'title': '📊 90-Day Review & Next Quarter Planning',
            'description': 'Review results, celebrate wins, plan the next 90 days.',
            'steps': [
                'Compare metrics: before vs after',
                'Calculate ROI for each initiative',
                'Document biggest wins',
                'Identify what did not work',
                'Gather team feedback',
                'Prioritize next quarter actions',
                'Set new KPIs',
                'Celebrate progress!'
            ],
            'owner': 'All',
            'time_estimate': '4-6 hours',
            'success_metric': 'Clear Q2 roadmap, documented learnings',
            'priority': 'High',
            'category': 'planning'
        },
        'fi': {
            'title': '📊 90 paivan katsaus & seuraava kvartaali',
            'description': 'Arvioi tulokset, juhli voittoja, suunnittele seuraavat 90 paivaa.',
            'steps': [
                'Vertaa mittareita: ennen vs jalkeen',
                'Laske ROI jokaiselle aloitteelle',
                'Dokumentoi suurimmat voitot',
                'Tunnista mika ei toiminut',
                'Keraa tiimin palaute',
                'Priorisoi seuraavan kvartaalin toimet',
                'Aseta uudet KPI:t',
                'Juhli edistymista!'
            ],
            'owner': 'Kaikki',
            'time_estimate': '4-6 tuntia',
            'success_metric': 'Selkea Q2-suunnitelma, dokumentoidut opit',
            'priority': 'Korkea',
            'category': 'planning'
        }
    },
    
    'structured_data': {
        'en': {
            'title': '📋 Structured Data (Schema.org)',
            'description': 'Add structured data to help search engines and AI understand your content.',
            'steps': [
                'Identify relevant schema types (Organization, Product, FAQ, etc.)',
                'Implement JSON-LD markup on key pages',
                'Add Organization schema to homepage',
                'Add Product/Service schemas if applicable',
                'Add FAQ schema for common questions',
                'Test with Google Rich Results Test',
                'Monitor in Google Search Console'
            ],
            'owner': 'Developer',
            'time_estimate': '4-8 hours',
            'success_metric': 'Rich snippets appearing in search, no schema errors',
            'priority': 'Medium',
            'category': 'seo'
        },
        'fi': {
            'title': '📋 Strukturoitu data (Schema.org)',
            'description': 'Lisaa strukturoitu data auttamaan hakukoneita ja tekoalya ymmartamaan sisaltosi.',
            'steps': [
                'Tunnista relevantit schema-tyypit (Organization, Product, FAQ, jne.)',
                'Toteuta JSON-LD-merkinta keskeisilla sivuilla',
                'Lisaa Organization-schema etusivulle',
                'Lisaa Product/Service-schemat tarvittaessa',
                'Lisaa FAQ-schema yleisiin kysymyksiin',
                'Testaa Google Rich Results Test -tyokalulla',
                'Seuraa Google Search Consolessa'
            ],
            'owner': 'Kehittaja',
            'time_estimate': '4-8 tuntia',
            'success_metric': 'Rich snippetit nakyvat haussa, ei schema-virheita',
            'priority': 'Keskitaso',
            'category': 'seo'
        }
    }
}

# Task key mapping based on detected issues
TASK_MAPPING = {
    'ssl_missing': 'ssl_setup',
    'analytics_missing': 'analytics_setup',
    'meta_weak': 'meta_optimization',
    'h1_missing': 'h1_optimization',
    'cta_missing': 'cta_optimization',
    'mobile_weak': 'mobile_optimization',
    'speed_slow': 'page_speed',
    'content_thin': 'content_strategy',
    'seo_weak': 'seo_foundation',
    'conversion_low': 'conversion_funnel',
    'trust_missing': 'social_proof',
}


class PlannerAgent(BaseAgent):
    """
    📋 Planner Agent V2 - Enhanced with rich action items
    """
    
    def __init__(self):
        super().__init__(
            agent_id="planner",
            name="Planner",
            role="Projektimanageri",
            avatar="📋",
            personality="Käytännöllinen ja järjestelmällinen organisoija"
        )
        self.dependencies = ['scout', 'analyst', 'guardian', 'prospector', 'strategist']
    
    def _get_action(self, key: str) -> Dict[str, Any]:
        """Get rich action item from library"""
        action = ACTION_LIBRARY.get(key, {})
        return action.get(self._language, action.get('en', {}))
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        self._context = context
        
        # Get dependency results
        strategist_results = self.get_dependency_results(context, 'strategist')
        guardian_results = self.get_dependency_results(context, 'guardian')
        prospector_results = self.get_dependency_results(context, 'prospector')
        analyst_results = self.get_dependency_results(context, 'analyst')
        
        overall_score = strategist_results.get('overall_score', 50) if strategist_results else 50
        priorities = strategist_results.get('strategic_priorities', []) if strategist_results else []
        
        logger.info(f"[Planner] Strategist overall_score: {overall_score}")
        logger.info(f"[Planner] Strategist priorities count: {len(priorities)}")
        
        self._emit_insight(
            self._t("planner.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Analyze issues and map to rich actions
        detected_issues = self._detect_issues(analyst_results)
        logger.info(f"[Planner] Detected issues: {detected_issues}")
        
        # 2. Build phases with rich action items
        phases = self._build_rich_phases(
            detected_issues, 
            overall_score, 
            priorities,
            guardian_results,
            prospector_results
        )
        
        for phase in phases:
            task_count = len(phase.get('tasks', []))
            self._emit_insight(
                self._t("planner.phase",
                       name=phase.get('name', ''),
                       duration=phase.get('duration', ''),
                       tasks=task_count),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.ACTION,
                data=phase
            )
        
        # 3. Create weekly sprints
        weekly_sprints = self._create_weekly_sprints(phases)
        self._emit_insight(
            self._t("planner.sprints_created", count=len(weekly_sprints)),
            priority=AgentPriority.LOW,
            insight_type=InsightType.FINDING
        )
        
        # 4. Define milestones
        milestones = self._define_milestones(phases)
        for ms in milestones[:2]:
            self._emit_insight(
                self._t("planner.milestone",
                       title=ms.get('title', ''),
                       date=ms.get('target_date', '')),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.ACTION,
                data=ms
            )
        
        # 5. Estimate resources
        resource_estimate = self._estimate_resources(phases)
        total_cost = resource_estimate.get('total_cost', 0)
        self._emit_insight(
            self._t("planner.investment", amount=f"{total_cost:,.0f}"),
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data=resource_estimate
        )
        
        # 6. Calculate ROI
        roi_projection = self._calculate_roi_projection(
            resource_estimate,
            guardian_results,
            prospector_results
        )
        self._emit_insight(
            self._t("planner.roi",
                   roi=roi_projection.get('roi_percentage', 0),
                   months=roi_projection.get('payback_months', 0)),
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data=roi_projection
        )
        
        # 7. Quick start guide
        quick_start_guide = self._create_quick_start_guide(phases)
        
        # Final summary
        self._emit_insight(
            self._t("planner.complete",
                   phases=len(phases),
                   milestones=len(milestones),
                   quick_start=len(quick_start_guide)),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return {
            'roadmap': {
                'total_duration_days': 90,
                'phases': len(phases),
                'total_tasks': sum(len(p.get('tasks', [])) for p in phases)
            },
            'phases': phases,
            'weekly_sprints': weekly_sprints,
            'milestones': milestones,
            'resource_estimate': resource_estimate,
            'roi_projection': roi_projection,
            'quick_start_guide': quick_start_guide,
            'projected_improvement': roi_projection.get('potential_score_gain', 15)
        }
    
    def _detect_issues(self, analyst_results: Dict[str, Any]) -> List[str]:
        """Detect issues from analyst results"""
        issues = []
        
        if not analyst_results:
            return ['seo_weak', 'content_thin']
        
        your_analysis = analyst_results.get('your_analysis', {})
        detailed = your_analysis.get('detailed_analysis', {})
        technical = detailed.get('technical_audit', {})
        seo = detailed.get('seo_basics', {})
        content = detailed.get('content_analysis', {})
        
        # Check SSL
        if technical.get('has_ssl') is False:
            issues.append('ssl_missing')
        
        # Check analytics
        if technical.get('has_analytics') is False:
            issues.append('analytics_missing')
        
        # Check meta
        meta_score = seo.get('meta_score', 100)
        if meta_score < 70:
            issues.append('meta_weak')
        
        # Check H1
        if not seo.get('has_h1', True):
            issues.append('h1_missing')
        
        # Check mobile
        if technical.get('has_mobile_optimization') is False:
            issues.append('mobile_weak')
        
        # Check speed
        speed_score = technical.get('page_speed_score', 80)
        if speed_score < 50:
            issues.append('speed_slow')
        
        # Check content
        word_count = content.get('word_count', 0)
        if word_count < 500:
            issues.append('content_thin')
        
        # General SEO weakness
        seo_score = your_analysis.get('basic_analysis', {}).get('score_breakdown', {}).get('seo_basics', 20)
        if seo_score < 12:
            issues.append('seo_weak')
        
        # Check structured data / schema
        basic = your_analysis.get('basic_analysis', {})
        if not basic.get('has_schema') and not technical.get('has_structured_data'):
            issues.append('schema_missing')
        
        return issues
    
    def _build_rich_phases(
        self,
        issues: List[str],
        overall_score: int,
        priorities: List[Dict[str, Any]],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build phases with rich action items from library
        
        2025 PRIORITY ORDER (modern approach):
        1. Conversion & UX (leads, user experience)
        2. AI/GEO Readiness (ChatGPT, Perplexity visibility)
        3. Content Strategy (E-E-A-T, expertise)
        4. Technical Foundation (speed, mobile, security)
        5. SEO comes naturally from above
        """
        
        phases = []
        used_keys = set()
        
        # ========================================
        # PHASE 1: Conversion & Quick Wins
        # Focus: Get more value from existing traffic
        # ========================================
        phase1_tasks = []
        
        # 1. CRITICAL: Analytics first (can't improve what you can't measure)
        if 'analytics_missing' in issues and 'analytics_setup' not in used_keys:
            action = self._get_action('analytics_setup')
            if action:
                phase1_tasks.append(action)
                used_keys.add('analytics_setup')
        
        # 2. Conversion & UX (highest ROI)
        conversion_actions = ['cta_optimization', 'conversion_funnel', 'ux_improvements']
        for action_key in conversion_actions:
            if action_key not in used_keys and len(phase1_tasks) < 3:
                if action_key == 'cta_optimization' and 'cta_missing' not in issues:
                    continue
                action = self._get_action(action_key)
                if action:
                    phase1_tasks.append(action)
                    used_keys.add(action_key)
        
        # 3. Mobile (55%+ of traffic is mobile)
        if 'mobile_weak' in issues and 'mobile_optimization' not in used_keys:
            action = self._get_action('mobile_optimization')
            if action:
                phase1_tasks.append(action)
                used_keys.add('mobile_optimization')
        
        # 4. Security only if missing (SSL)
        if 'ssl_missing' in issues and 'ssl_setup' not in used_keys:
            action = self._get_action('ssl_setup')
            if action:
                phase1_tasks.append(action)
                used_keys.add('ssl_setup')
        
        if phase1_tasks:
            phases.append({
                'phase': 1,
                'name': 'Phase 1: Conversion & UX' if self._language == 'en' else 'Vaihe 1: Konversio & UX',
                'duration': 'Weeks 1-4' if self._language == 'en' else 'Viikot 1-4',
                'goal': 'Get more leads from existing traffic' if self._language == 'en' else 'Saa enemman liideja nykyisesta liikenteesta',
                'tasks': phase1_tasks[:4]
            })
        
        # ========================================
        # PHASE 2: Content & AI Visibility
        # Focus: Be found by AI search (ChatGPT, Perplexity)
        # ========================================
        phase2_tasks = []
        
        # 1. AI/GEO Readiness (future of search)
        if 'ai_optimization' not in used_keys:
            action = self._get_action('ai_optimization')
            if action:
                phase2_tasks.append(action)
                used_keys.add('ai_optimization')
        
        # 2. Content Strategy (E-E-A-T)
        content_actions = ['content_strategy', 'authority_building', 'competitive_content_gap']
        for action_key in content_actions:
            if action_key not in used_keys and len(phase2_tasks) < 4:
                action = self._get_action(action_key)
                if action:
                    phase2_tasks.append(action)
                    used_keys.add(action_key)
        
        # 3. Structured data (helps AI understand your content)
        if 'schema_missing' in issues and 'structured_data' not in used_keys:
            action = self._get_action('structured_data')
            if action:
                phase2_tasks.append(action)
                used_keys.add('structured_data')
        
        if phase2_tasks:
            phases.append({
                'phase': 2,
                'name': 'Phase 2: Content & AI Visibility' if self._language == 'en' else 'Vaihe 2: Sisalto & AI-nakyvyys',
                'duration': 'Weeks 5-8' if self._language == 'en' else 'Viikot 5-8',
                'goal': 'Be found by AI search engines' if self._language == 'en' else 'Loydy AI-hakukoneista',
                'tasks': phase2_tasks[:4]
            })
        
        # ========================================
        # PHASE 3: Scale & Automation
        # Focus: Systematize growth
        # ========================================
        phase3_tasks = []
        
        # 1. Email automation (owned channel)
        if 'email_automation' not in used_keys:
            action = self._get_action('email_automation')
            if action:
                phase3_tasks.append(action)
                used_keys.add('email_automation')
        
        # 2. Social proof & trust
        if 'trust_building' not in used_keys:
            action = self._get_action('trust_building')
            if action:
                phase3_tasks.append(action)
                used_keys.add('trust_building')
        
        # 3. Performance optimization
        if 'speed_slow' in issues and 'performance_optimization' not in used_keys:
            action = self._get_action('performance_optimization')
            if action:
                phase3_tasks.append(action)
                used_keys.add('performance_optimization')
        
        # 4. Review and next quarter
        if 'quarterly_review' not in used_keys:
            action = self._get_action('quarterly_review')
            if action:
                phase3_tasks.append(action)
                used_keys.add('quarterly_review')
        
        if phase3_tasks:
            phases.append({
                'phase': 3,
                'name': 'Phase 3: Scale & Automate' if self._language == 'en' else 'Vaihe 3: Skaalaa & Automatisoi',
                'duration': 'Weeks 9-12' if self._language == 'en' else 'Viikot 9-12',
                'goal': 'Build systematic growth engine' if self._language == 'en' else 'Rakenna systemaattinen kasvumoottori',
                'tasks': phase3_tasks[:3]
            })
        # PHASE 3: Scale and optimize
        # ========================================
        phase3_tasks = []
        
        # Add scaling actions
        scale_actions = ['social_proof', 'review_optimize']
        for action_key in scale_actions:
            if action_key not in used_keys and len(phase3_tasks) < 4:
                action = self._get_action(action_key)
                if action:
                    phase3_tasks.append(action)
                    used_keys.add(action_key)
        
        if phase3_tasks:
            phases.append({
                'phase': 3,
                'name': 'Phase 3: Scale' if self._language == 'en' else 'Vaihe 3: Skaalaus',
                'duration': 'Days 61-90' if self._language == 'en' else 'Päivät 61-90',
                'goal': 'Scale growth and measure results' if self._language == 'en' else 'Skaalaa kasvua ja mittaa tuloksia',
                'tasks': phase3_tasks[:5]
            })
        
        return phases
    
    def _map_priority_to_action(self, title: str) -> Optional[str]:
        """Map a priority title to an action key"""
        title_lower = title.lower()
        
        mappings = {
            'ssl': 'ssl_setup',
            'https': 'ssl_setup',
            'analytics': 'analytics_setup',
            'seuranta': 'analytics_setup',
            'meta': 'meta_optimization',
            'h1': 'h1_optimization',
            'otsik': 'h1_optimization',
            'cta': 'cta_optimization',
            'toimintakehote': 'cta_optimization',
            'mobile': 'mobile_optimization',
            'mobiili': 'mobile_optimization',
            'speed': 'page_speed',
            'nopeu': 'page_speed',
            'content': 'content_strategy',
            'sisält': 'content_strategy',
            'seo': 'seo_foundation',
            'hakukone': 'seo_foundation',
        }
        
        for keyword, action_key in mappings.items():
            if keyword in title_lower:
                return action_key
        
        return None
    
    def _create_weekly_sprints(self, phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create weekly sprints from phases"""
        sprints = []
        
        for phase in phases:
            phase_num = phase.get('phase', 1)
            tasks = phase.get('tasks', [])
            start_week = (phase_num - 1) * 4 + 1
            
            for week_offset in range(4):
                week_num = start_week + week_offset
                week_tasks = []
                
                if tasks and week_offset < len(tasks):
                    week_tasks.append(tasks[week_offset])
                
                sprints.append({
                    'week': week_num,
                    'phase': phase_num,
                    'tasks': week_tasks,
                    'focus': phase.get('goal', '')
                })
        
        return sprints
    
    def _define_milestones(self, phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Define milestones"""
        milestones = [
            {
                'id': 1,
                'title': 'Quick wins implemented' if self._language == 'en' else 'Nopeat voitot toteutettu',
                'week': 2,
                'target_date': 'Week 2' if self._language == 'en' else 'Viikko 2',
                'phase': 1
            },
            {
                'id': 2,
                'title': 'Foundation complete' if self._language == 'en' else 'Perusta valmis',
                'week': 4,
                'target_date': 'Week 4' if self._language == 'en' else 'Viikko 4',
                'phase': 1
            },
            {
                'id': 3,
                'title': 'Growth systems active' if self._language == 'en' else 'Kasvujärjestelmät aktiiviset',
                'week': 8,
                'target_date': 'Week 8' if self._language == 'en' else 'Viikko 8',
                'phase': 2
            },
            {
                'id': 4,
                'title': '90-day program complete' if self._language == 'en' else '90 päivän ohjelma valmis',
                'week': 12,
                'target_date': 'Week 12' if self._language == 'en' else 'Viikko 12',
                'phase': 3
            }
        ]
        return milestones
    
    def _estimate_resources(self, phases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimate resources from rich action items"""
        hourly_rate = 80
        total_hours = 0
        category_hours = {}
        
        for phase in phases:
            for task in phase.get('tasks', []):
                # Parse time_estimate like "8-12 hours" or "8-12 tuntia"
                time_str = task.get('time_estimate', '8 hours')
                hours = self._parse_hours(time_str)
                total_hours += hours
                
                cat = task.get('category', 'other')
                category_hours[cat] = category_hours.get(cat, 0) + hours
        
        total_cost = total_hours * hourly_rate
        
        return {
            'total_hours': total_hours,
            'total_cost': total_cost,
            'hourly_rate': hourly_rate,
            'by_category': category_hours,
            'resource_split': {
                'internal': round(total_cost * 0.6),
                'external': round(total_cost * 0.4)
            }
        }
    
    def _parse_hours(self, time_str: str) -> int:
        """Parse hours from time string like '8-12 hours'"""
        import re
        numbers = re.findall(r'\d+', time_str)
        if len(numbers) >= 2:
            return (int(numbers[0]) + int(numbers[1])) // 2
        elif len(numbers) == 1:
            return int(numbers[0])
        return 8  # Default
    
    def _calculate_roi_projection(
        self,
        resource_estimate: Dict[str, Any],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate ROI projection"""
        investment = resource_estimate.get('total_cost', 0)
        
        # Risk saved from Guardian
        annual_risk = 0
        if guardian_results:
            revenue_impact = guardian_results.get('revenue_impact', {})
            annual_risk = revenue_impact.get('total_annual_risk', 0)
        risk_saved = annual_risk * 0.5
        
        # Revenue gain from opportunities
        revenue_gain = 0
        potential_score_gain = 0
        if prospector_results:
            opportunities = prospector_results.get('growth_opportunities', [])
            high_impact = len([o for o in opportunities if o.get('impact') == 'high'])
            medium_impact = len([o for o in opportunities if o.get('impact') == 'medium'])
            revenue_gain = high_impact * 5000
            potential_score_gain = (high_impact * 5) + (medium_impact * 3)
            
            if guardian_results:
                priority_actions = guardian_results.get('priority_actions', [])
                potential_score_gain += len(priority_actions) * 2
            
            potential_score_gain = min(potential_score_gain, 35)
        
        total_benefit = risk_saved + revenue_gain
        
        if investment > 0:
            roi_percentage = round(((total_benefit - investment) / investment) * 100)
        else:
            roi_percentage = 0
        
        if total_benefit > 0:
            payback_months = round((investment / total_benefit) * 12)
        else:
            payback_months = 0
        
        return {
            'investment': investment,
            'risk_saved': round(risk_saved),
            'revenue_gain': round(revenue_gain),
            'total_annual_benefit': round(total_benefit),
            'roi_percentage': roi_percentage,
            'payback_months': min(payback_months, 36),
            'potential_score_gain': potential_score_gain
        }
    
    def _create_quick_start_guide(self, phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create quick start guide from first phase tasks"""
        quick_start = []
        
        if phases and phases[0].get('tasks'):
            for idx, task in enumerate(phases[0]['tasks'][:3]):
                quick_start.append({
                    'step': idx + 1,
                    'title': task.get('title', ''),
                    'description': task.get('description', ''),
                    'owner': task.get('owner', ''),
                    'time_estimate': task.get('time_estimate', ''),
                    'success_metric': task.get('success_metric', '')
                })
        
        return quick_start
