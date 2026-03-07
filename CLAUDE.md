# Brandista API - Projektin muisti

## Yleiskuvaus
Brandista Growth Engine - AI-pohjainen markkinointianalyysi- ja strategiatyökalu yrityksille. Multi-agent arkkitehtuuri.

## Tekniset tiedot
- **Backend**: Python FastAPI
- **AI**: OpenAI API (GPT-4)
- **Tietokanta**: PostgreSQL (Railway)
- **Cache/Queue**: Redis
- **Deployment**: Railway (auto-deploy GitHubista)
- **Frontend**: Erillinen repo `brandista-frontend 2 agentit`

## Tuotanto
- **API URL**: Railway project `69c31d7d-071c-4a66-9d8c-35ea735327ed`
- **Frontend**: https://brandista.eu/growthengine/dashboard
- **Logit**: Railway Logs-välilehti

## Agentit (Multi-Agent System)
- `scout_agent.py` - Kilpailija- ja markkinahaku
- `analyst_agent.py` - Data-analyysi
- `strategist_agent.py` - Strategiasuositukset
- `planner_agent.py` - 90 päivän suunnitelmat
- `guardian_agent.py` - Laadunvalvonta, uhka-ennusteet + Gustav 2.0 Competitive Intelligence integraatio
- `prospector_agent.py` - Liiketoimintamahdollisuudet
- `orchestrator.py` - Agenttien koordinointi + oppimisen verifikaatio
- `blackboard.py` - Agenttien välinen tiedonjako

### Gustav 2.0 — Business Threat Intelligence (v3.0.0)
- `competitive_intelligence.py` - Battlecards, action playbooks, uhkakorrelaatiot, inaction cost
- `threat_history.py` - Snapshots, deltas, trend prediction, recurring threats
- `intelligence_brief.py` - Executive briefs (CEO-luettava, template + LLM)
- `guardian_pulse.py` - Pulse monitoring, ContentHashTracker, kilpailijamuutosten havaitseminen
- `hallucination_guard.py` - 4-kerroksinen anti-hallusinaatiojärjestelmä (provenance, guardrails, validation, transparency)

## Anti-Hallusinaatio (Hallucination Guard) — AKTIIVINEN v3.0.0
- **4 kerrosta**: Data Provenance → Prompt Guardrails → Post-generation Validation → Transparency Markers
- **ProvenanceTracker**: Jokainen luku jäljitettävissä lähteeseen (HTML_ANALYSIS, WHOIS, BUSINESS_REGISTRY, SCORE_CALCULATION, ym.)
- **ConfidenceLevel**: VERIFIED → CALCULATED → ESTIMATED → SPECULATIVE (heikoin lenkki määrää kokonaisluottamuksen)
- **Prompt Guardrails**: ANTI_HALLUCINATION_SUFFIX (fi/en) lisätään kaikkiin LLM-prompteihin
- **OutputValidator**: Tarkistaa LLM-outputin tunnettujen faktojen perusteella (yritysnimet, euromäärät, prosentit)
- **TransparencyEnvelope**: Rahoitusestimaatit wrappautuvat {value, best_case, worst_case, is_estimate, confidence}
- **IntelligenceGuard**: Korkean tason API — käytössä competitive_intelligence.py:ssä + guardian_pulse.py:ssä

## Competitive Intelligence (Gustav 2.0) — AKTIIVINEN v3.0.0
- **Battlecards**: Head-to-head vertailu 8 ulottuvuudessa per kilpailija (content, seo, performance, trust, mobile, company_size, digital_breadth, growth_signals)
- **Action Playbooks**: Konkreettiset toimenpiteet ROI-laskelmilla (ACTION_COST_MATRIX: 9 toimenpidetyyppiä)
- **6 uhkakorrelaatiota**: Content Gap Attack, Digital Erosion, Competitive Surge, AI Invisibility, Trust Collapse, Market Displacement
- **Inaction Cost**: Toimimattomuuden hinta per kategoria (estimaatti + vaihteluväli)
- **Threat History**: Snapshots + deltas (NEW/ESCALATED/MITIGATED/RESOLVED/RECURRING) + lineaarinen regressio trendi
- **Executive Briefs**: CEO-luettava brief: key findings, top actions, trend, competitive position
- **Guardian Pulse**: Kilpailijoiden muutosten havaitseminen (content hash), HTTP health, SSL, response time
- **Integraatio**: `guardian_agent.py` execute() → `competitive_intelligence` dict returnissa

## Oppiminen (Learning System) — AKTIIVINEN v2.2.2
- **Infra**: `agents/learning.py` — ennusteiden seuranta, verifikaatio, trendit
- **Guardian**: Kirjaa uhkaennusteet (`_log_prediction`) ja RASM-ennusteet
- **Orchestrator**: Verifioi ennusteet analyysin jälkeen (`_verify_learning_predictions`)
- **Feedback loop**: Guardian ennustaa → Strategist tuottaa tulokset → Orchestrator verifioi → Learning System oppii
- **Tilastot**: `swarm_summary.learning` sisältää verified/correct/accuracy per analyysi

## Tärkeät tiedostot
- `main.py` - Pää-API, AI-näkyvyysanalyysi (6 faktoria), hakutermien käännökset
- `agents/scoring_constants.py` - Yhtenäiset kynnysarvot, painot ja apufunktiot kaikille agenteille
- `agents/scout_agent.py` - Toimialan tunnistus, kilpailijoiden pisteytys
- `agents/url_utils.py` - URL-apufunktiot (clean_url, get_domain_from_url) — eristetty main.py:stä
- `agents/competitive_intelligence.py` - Gustav 2.0 Competitive Intelligence Engine (~1180 riviä)
- `agents/hallucination_guard.py` - Anti-hallusinaatiojärjestelmä (~450 riviä)
- `agents/threat_history.py` - Threat History & Predictive Analytics (~420 riviä)
- `agents/intelligence_brief.py` - Executive Intelligence Briefs (~310 riviä)
- `agents/guardian_pulse.py` - Guardian Pulse Monitoring (~290 riviä)
- `database.py` - Tietokantayhteydet
- `auth_magic_link.py` - Magic link -kirjautuminen
- `stripe_module.py` - Maksut

## Pisteytysarkkitehtuuri (v2.3.0)
- **Kaikki vakiot**: `agents/scoring_constants.py` — yksi lähde totuudelle
- **Score-tulkinta**: 80/60/40/20 (excellent/good/average/poor/critical)
- **Faktoristatus**: 70/50/30 (excellent/good/needs_improvement/poor)
- **AI-näkyvyys**: 6 faktoria (structured_data, semantic_structure, content_depth, authority_signals, conversational_format, ai_accessibility)
- **Painot**: `CHATGPT_WEIGHTS` (sisältö+rakenne), `PERPLEXITY_WEIGHTS` (auktoriteetti+saavutettavuus)
- **Riski**: Prosenttipohjainen (>10%/5%/2% liikevaihdosta), ei kiinteitä EUR-rajoja

## Tunnetut ongelmat (5.2.2026)

### ✅ KORJATTU: Progress-palkit katoavat
- Syy: `useEffect` kutsuttiin uudelleen GrowthEngine.tsx:ssä
- Korjaus: Jaettu kahteen erilliseen `useEffect`-hookiin

### 🔄 ODOTTAA TESTAUSTA: Kilpailijahaku
- Ongelma: kultajousi.fi → löytää "Laite-Saraka Oy" (väärä toimiala)
- Korjaukset:
  - Hakutermit käännetty oikeaksi suomeksi
  - Domain-nimi tarkistetaan toimialaavainsanoista
  - Tunnetut brändit lisätty (kultajousi, kultakeskus)
- Jos ei toimi: Lisää kovakoodattu kilpailijalista per toimiala

## Toimialakäännökset (main.py)
```python
INDUSTRY_TRANSLATIONS = {
    'jewelry': {'fi': 'koruliike', 'en': 'jewelry store', 'sv': 'smyckebutik'},
    # ... jne
}
```

## Testaus
- **Testit**: `python3 -m pytest tests/ -x -q` (545 testiä läpi, 29 skipped, 0 failed)
- **Gustav 2.0 testit** (115 uutta):
  - `test_hallucination_guard.py` — 28 testiä
  - `test_competitive_intelligence.py` — 42 testiä
  - `test_threat_history.py` — 23 testiä
  - `test_intelligence_brief.py` — 8 testiä
  - `test_guardian_pulse.py` — 14 testiä
- **Manuaalinen**: https://brandista.eu/growthengine/dashboard → aloita analyysi → tarkista Railway logit

## Versiohistoria
- **Versio**: 3.0.0 (Gustav 2.0: Business Threat Intelligence)
- **Changelog**: `CHANGELOG.md`

## Kehityskäytännöt
- **AINA aja testit** ennen committia: `python3 -m pytest tests/ -x -q`
- **Versiohistoria**: Päivitä `CHANGELOG.md` jokaisessa muutoksessa — päivämäärät, mitä, miksi
- **Learning System**: Jos lisäät uusia ennusteita agenttiin, varmista että verifikaatio on kytketty orchestratorissa

## Käyttäjäpreferenssit
- Kieli: Suomi
- Omistaja: Tuukka
