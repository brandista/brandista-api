# Changelog - Brandista Growth Engine API

Kaikki merkittavat muutokset dokumentoidaan tahan tiedostoon.
Muoto: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [3.0.0] - 2026-03-07 — Gustav 2.0: Business Threat Intelligence

### Lisätty

#### Gustav 2.0 — Competitive Intelligence Engine (Phase 1)
- **`agents/competitive_intelligence.py`** — CompetitiveIntelligenceEngine
  - Battlecards: head-to-head vertailu 8 ulottuvuudessa per kilpailija
  - Action Playbooks: konkreettiset toimenpiteet ROI-laskelmilla (ACTION_COST_MATRIX)
  - 6 uhkakorrelaatiota: Content Gap Attack, Digital Erosion, Competitive Surge, AI Invisibility, Trust Collapse, Market Displacement
  - Inaction Cost: toimimattomuuden hinta per kategoria (estimaatti + vaihteluväli)
  - Integroitu `guardian_agent.py` execute():iin → `competitive_intelligence` dict returnissa

#### Gustav 2.0 — Threat History & Predictive Analytics (Phase 2)
- **`agents/threat_history.py`** — ThreatHistoryManager
  - Snapshots: analyysitilanteen tallennus (in-memory, DB-backing API-tasolla)
  - Deltas: NEW, ESCALATED, MITIGATED, RESOLVED, RECURRING uhkakategoriat
  - Trend Prediction: lineaarinen regressio, confidence scoring, threshold detection
  - Recurring Threats: uhkat joita ei korjata + kumulatiivinen hinta

#### Gustav 2.0 — Executive Intelligence Briefs (Phase 3)
- **`agents/intelligence_brief.py`** — IntelligenceBriefGenerator
  - CEO-luettava brief: key findings, top actions, trend, competitive position
  - Template-pohjainen narratiivi (ei vaadi LLM:ää perusversiolle)
  - LLM-prompt rakentaja anti-hallusinaatio-guardrailsein

#### Gustav 2.0 — Guardian Pulse Monitoring (Phase 4)
- **`agents/guardian_pulse.py`** — GuardianPulse
  - ContentHashTracker: kilpailijoiden muutosten havaitseminen (title, content, schema, pages)
  - Pulse checks: HTTP health, response time, SSL, kilpailijamuutokset
  - Alert generation kontekstuaalisilla LLM-prompteilla

#### Anti-Hallucination Guard System
- **`agents/hallucination_guard.py`** — 4-kerroksinen suojajärjestelmä
  - Data Provenance: jokainen luku jäljitettävissä lähteeseen (DataSource, ConfidenceLevel)
  - Prompt Guardrails: ANTI_HALLUCINATION_SUFFIX kaikissa LLM-prompteissa
  - Post-generation Validation: OutputValidator tarkistaa LLM-outputin input-dataa vasten
  - Transparency Markers: estimaatit wrappautuvat best/worst case -arvioilla
  - IntelligenceGuard: korkean tason API koko järjestelmään
  - Data Quality Summary: kokonaislaatu 0-100 + kuvaus fi/en

#### 115 uutta yksikkötestiä (545 yhteensä, 0 failannutta)
- `test_hallucination_guard.py` — 28 testiä (provenance, guardrails, validation, transparency)
- `test_competitive_intelligence.py` — 42 testiä (battlecards, actions, correlations, inaction cost)
- `test_threat_history.py` — 23 testiä (snapshots, deltas, trends, recurring)
- `test_intelligence_brief.py` — 8 testiä (brief generation, narratives, prompts)
- `test_guardian_pulse.py` — 14 testiä (hash tracking, pulse checks, alerts)

---

## [2.3.2] - 2026-03-06

### Lisätty

#### Yksikkötestit — scoring_constants + schema markup
- **58 uutta testiä** (40 + 18), kaikki läpi
- `tests/unit/test_scoring_constants.py` — kattaa kaikki scoring_constants.py:n funktiot:
  - `interpret_score()` raja-arvot ja boundary-testit
  - `factor_status()` luokittelut
  - `score_to_risk_level()`, `calculate_roi_score()`, `classify_financial_risk()`
  - `get_positioning_tier()`, `get_competitive_position()`, `classify_tech_modernity()`
  - Painojen konsistenssi: ChatGPT/Perplexity/Strategic summat = 1.0, samat faktorit
- `tests/unit/test_schema_markup.py` — testaa `_check_schema_markup()` eristetysti (exec-lähestymistapa, ei tarvitse main.py:n raskaita importteja):
  - BemuFix.fi:n oikea AutoRepair + OfferCatalog schema
  - Sisäkkäisten tyyppien tunnistus, address/geo, catalog richness
  - @graph-muoto (WordPress/Yoast), FAQPage, microdata, OG-tagit

#### URL-utilityjen eristäminen (`agents/url_utils.py`)
- `get_domain_from_url()` ja `clean_url()` siirretty `main.py`:stä omaan moduuliin
- `scout_agent.py` importtaa nyt `url_utils`:sta → ei enää vedä koko main.py:tä mukaansa
- **Korjasi 4 failaavaa testiä** (TestIndustryDetection): `ModuleNotFoundError: jwt` poistui

### Korjattu
- **416/416 testiä läpi**, 0 virhettä (aiemmin 412/445 + 4 failed)

---

## [2.3.1] - 2026-03-05

### Korjattu

#### Structured Data -pisteytys — rekursiivinen JSON-LD parsinta
- **Vaikutus**: Sivustot joilla on kattava JSON-LD schema (esim. AutoRepair + OfferCatalog + Service) saivat liian matalat pisteet koska sisäkkäiset @type:t eivät löytyneet
- **Juurisyy**: `_check_schema_markup()` kävi vain top-level @type:t, ei sisäkkäisiä. Esim. BemuFix: AutoRepair-scheman sisällä OfferCatalog → 5 × Offer → Service — nämä kaikki jäivät tunnistamatta
- **Korjaus**: Rekursiivinen `_extract_schema_types()` (max depth 5) käy kaikki sisäkkäiset objektit ja listat
- **Lisäksi**: Quality-bonus nostettu 15→20, OfferCatalog richness -bonus (3+ tarjousta), rich schema coverage (5+ tyyppiä)
- **Esimerkki**: BemuFix.fi Structured Data 50/100 → ~60/100
- **Tiedostot**: `main.py` (`_check_schema_markup`)

---

## [2.3.0] - 2026-03-05

### Lisätty

#### AI-näkyvyysanalyysi uudistettu (6 faktoria)
- **Uusi faktori: `ai_accessibility`** — tarkistaa llms.txt, robots.txt AI-bottidirektiivit, sitemap-laatu
  - llms.txt / llms-full.txt tunnistus ja pisteytys
  - robots.txt: GPTBot, ChatGPT-User, CCBot, PerplexityBot, Google-Extended, ClaudeBot, anthropic-ai
  - Sitemap.xml URL-kattavuus
- **E-E-A-T signaalit** lisätty `_check_authority_markers()`:iin
  - Author metadata, rel="author", about-sivu, yhteystiedot, sosiaalinen todiste
  - Freshness metadata (article:published_time, dateModified)
- **JSON-LD laaduntarkistus** lisätty `_check_schema_markup()`:iin
  - Tyyppikohtainen pisteytys (LocalBusiness, Product, FAQPage, Article, ym.)
  - Laatutarkistus (description, address/geo, tyyppimonipuolisuus)
- **Meta description -laatu** ja **kuva alt-teksti -kattavuus** lisätty `_assess_content_comprehensiveness()`:iin
- **Painot päivitetty**: ChatGPT-readiness painottaa sisältöä+rakennetta, Perplexity painottaa auktoriteettia+saavutettavuutta
- **Tiedostot**: `main.py` (AI-näkyvyysfunktiot)

#### Yhtenäinen pisteytysmoduuli (`agents/scoring_constants.py`)
- Kaikki kynnysarvot, painot ja apufunktiot yhdessä paikassa
- `SCORE_THRESHOLDS` (80/60/40/20) — yhtenäinen kaikille agenteille (aiemmin 3 eri skaalaa)
- `factor_status()` — yksittäisten faktorien luokittelu (70/50/30)
- `get_positioning_tier()` — absoluuttinen positiointi (75/60/45)
- `get_competitive_position()` — suhteellinen SWOT-positiointi vs. kilpailijat
- `classify_tech_modernity()` — teknologiatason luokittelu
- `classify_financial_risk()` — prosenttipohjainen riskiluokittelu (aiemmin kiinteät EUR-rajat)
- `calculate_roi_score()` — impact × effort ROI-laskenta
- `CHATGPT_WEIGHTS`, `PERPLEXITY_WEIGHTS` — AI-näkyvyyspainot
- `INDUSTRY_AVERAGE_SCORE`, `INDUSTRY_TOP_QUARTILE`, `INDUSTRY_BOTTOM_QUARTILE`
- `DEFAULT_ANNUAL_REVENUE_EUR` — yhtenäinen oletustuloluku (500k)

### Korjattu

#### html_content-bugi (analyst + guardian)
- `basic.get('html_content', '')` ei koskaan sisältänyt dataa → AI-näkyvyyspisteet aina 0
- Molemmat agentit käyttävät nyt valmiiksi laskettua `overall_ai_search_score` -arvoa
- **Tiedostot**: `agents/analyst_agent.py`, `agents/guardian_agent.py`

#### Duplikaatti Pydantic-mallit poistettu
- 11 mallia oli määritelty kahdesti main.py:ssä (111 riviä duplikaattikoodia)
- AISearchFactor, AISearchVisibility, AIAnalysis, SmartAction, SmartScores, DetailedAnalysis, ym.

#### Syntaksivirhe korjattu
- `perplexity_score = int(sum(...)` — puuttuva sulku

#### Epäjohdonmukaisuudet korjattu
- Revenue-oletus: 450k vs 500k → yhtenäinen `DEFAULT_ANNUAL_REVENUE_EUR`
- Riskikynnykset: kiinteät EUR (>50k, >20k) → prosenttipohjainen (>10%, >5%, >2%)
- Impact/effort-pisteytys: 3 eri skaalaa → yhtenäinen `IMPACT_SCORES`/`EFFORT_SCORES`
- Score-tulkinta: analyst (90/75/60/40), strategist (80/65/50/35), guardian (<40/<70) → yhtenäinen (80/60/40/20)
- Hardcoded positioning strings → `get_positioning_tier()`, `classify_tech_modernity()`, jne.

### Muutetut tiedostot
- `main.py` — AI-näkyvyys, mallit, importit, pisteytys
- `agents/scoring_constants.py` — **UUSI**: yhtenäinen vakiomoduuli
- `agents/analyst_agent.py` — html_content-korjaus, vakioiden käyttö
- `agents/guardian_agent.py` — html_content-korjaus, vakioiden käyttö, riskiluokittelu
- `agents/strategist_agent.py` — vakioiden käyttö, painot, maturity levels
- `agents/prospector_agent.py` — vakioiden käyttö, market gap threshold

---

## [2.2.2] - 2026-03-03

### Lisätty

#### Learning System aktivoitu — ennusteiden verifikaatiolooppi suljettu
- **Orchestrator**: `_verify_learning_predictions()` kutsutaan jokaisen analyysin jälkeen
  - Vertaa Guardian-agentin uhkaennusteita Strategistin lopullisiin pisteisiin
  - Verifioi RASM-parannusennusteet todellisia tuloksia vastaan
  - Fire-and-forget, ei hidasta analyysia
- **Guardian Agent**: `_log_prediction()` oli jo käytössä — tallentaa uhkien vakavuusennusteet ja RASM-ennusteet
- **Verifikaatio**: `_verify_prediction()` (base_agent.py) oli olemassa mutta sitä ei koskaan kutsuttu — nyt kytkettynä
- **Tilastot**: `get_learning_stats()` lisätty orkestroijaan — oppimistilastot saatavilla
- **swarm_summary.learning**: Jokaisen analyysin tulos sisältää nyt oppimistilastot (verified, correct, accuracy)
- **Tiedostot**: `agents/orchestrator.py`

### Korjattu
- **Learning feedback loop**: Ennusteet kirjattiin mutta niitä ei koskaan verifioitu → oppimissykli oli rikki
  - Sama pattern kuin BemuFix v4.1.3 CollectiveKnowledge-korjaus

---

## [2.2.1] - 2026-01-19

### Lisätty
- RunStore Redis-backed persistence
- RunContext per-request isolation
- Learning System infrastructure (`agents/learning.py`)
  - `log_prediction()`, `verify_prediction()`, `get_agent_stats()`
  - Guardian Agent logging predictions

### Huomioita
- Learning System infra rakennettu mutta verifikaatiolooppi jäi kytkemättä (korjattu 2.2.2)

---

## [2.2.0] - 2025-12-22

### Lisätty
- Multi-agent system (Scout, Analyst, Guardian, Prospector, Strategist, Planner)
- Blackboard-pohjainen agenttien välinen tiedonjako
- Unified Context for cross-analysis learning
- Analysis History DB
- WebSocket-pohjainen reaaliaikainen progress

---

## [2.1.0] - 2025-11-15

### Lisätty
- Kilpailija-analyysi ja toimialan tunnistus
- RASM-pisteytys (Relevance, Authority, Social, Mobile)
- 90 päivän toimintasuunnitelma
- Magic link -kirjautuminen
- Stripe-integraatio
