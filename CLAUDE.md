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
- **Railway project ID**: `69c31d7d-071c-4a66-9d8c-35ea735327ed`
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

### 4 kerrosta + 3 rehellisyyssääntöä
- **Data Provenance**: ProvenanceTracker jäljittää jokaisen luvun lähteeseen (DataSource enum: HTML_ANALYSIS, WHOIS, BUSINESS_REGISTRY, SCORE_CALCULATION, INFERENCE, LLM_GENERATED ym.)
- **Prompt Guardrails**: ANTI_HALLUCINATION_SUFFIX (fi/en) + 3 rehellisyyssääntöä (ks. alla)
- **Post-generation Validation**: OutputValidator tarkistaa LLM-outputin (yritysnimet, euromäärät, prosentit)
- **Transparency Markers**: TransparencyEnvelope wrappaa estimaatit {value, best_case, worst_case, is_estimate, confidence}
- **ConfidenceLevel**: VERIFIED → CALCULATED → ESTIMATED → SPECULATIVE (heikoin lenkki määrää)
- **IntelligenceGuard**: Korkean tason API — käytössä competitive_intelligence.py:ssä + guardian_pulse.py:ssä

### 3 rehellisyyssääntöä (Davis Rules, lisätty v3.3.0)
Kaikki LLM-promptit noudattavat näitä — sisäänrakennettu ANTI_HALLUCINATION_SUFFIX:iin:
1. **Tyhjä > arvaus**: Jos tieto puuttuu → `"tieto ei saatavilla"` + selitys miksi. Ei confidence scorea.
2. **3x-rangaistus**: Väärä vastaus on 3x pahempi kuin tyhjä. Epävarmoissa: jätä tyhjäksi.
3. **Lähde näkyviin**: Jokainen väite on `extracted` (suoraan datasta) tai `inferred` (päätelty). Jos inferred → evidence miksi ja mistä.

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
- `main.py` - Legacy pää-API (11500+ riviä), AI-näkyvyysanalyysi (6 faktoria), hakutermien käännökset. **Tuotannon entrypoint** (Railway Nixpacks auto-detect)
- `app/main.py` - Refaktoroitu modulaarinen entrypoint (importtaa agentteja `agents/`-kansiosta). Kehitysversio, EI vielä tuotannossa
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
- `stripe_module.py` - Stripe Checkout -integraatio (Phase 1)

## Stripe Checkout (Phase 1) — AKTIIVINEN

### stripe_module.py
Standalone Stripe-integraatiomoduuli. Ei riippuvuuksia main.py:hyn — voidaan importata erikseen.

### SubscriptionTier enum
`FREE`, `ANALYSIS` (149€/kerta), `PRO` (99€/kk), `PROFESSIONAL` (199€/kk), `ENTERPRISE` (custom)

### API-endpointit
- `POST /api/subscription/checkout` — Luo Stripe Checkout -sessio. JSON body: `{ tier: string, frontend_base_url?: string }`. Palauttaa `{ checkout_url }`.
- `POST /api/subscription/webhook` — Stripe webhook handler. Käsittelee `checkout.session.completed` -eventin.

### Ympäristömuuttujat (Stripe)
| Muuttuja | Kuvaus |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key (palautetaan frontendille) |
| `STRIPE_WEBHOOK_SECRET` | Webhook-allekirjoituksen tarkistus |
| `STRIPE_PRICE_ANALYSIS` | Stripe Price ID: Analysis (149€) |
| `STRIPE_PRICE_PRO` | Stripe Price ID: Pro (99€/kk) |
| `STRIPE_PRICE_PROFESSIONAL` | Stripe Price ID: Professional (199€/kk) |
| `STRIPE_PRICE_ENTERPRISE` | Stripe Price ID: Enterprise |
| `FRONTEND_BASE_URL` | Checkout success/cancel redirect URL base |

## Pisteytysarkkitehtuuri (v2.3.0)
- **Kaikki vakiot**: `agents/scoring_constants.py` — yksi lähde totuudelle
- **Score-tulkinta**: 80/60/40/20 (excellent/good/average/poor/critical)
- **Faktoristatus**: 70/50/30 (excellent/good/needs_improvement/poor)
- **AI-näkyvyys**: 6 faktoria (structured_data, semantic_structure, content_depth, authority_signals, conversational_format, ai_accessibility)
- **Painot**: `CHATGPT_WEIGHTS` (sisältö+rakenne), `PERPLEXITY_WEIGHTS` (auktoriteetti+saavutettavuus)
- **Riski**: Prosenttipohjainen (>10%/5%/2% liikevaihdosta), ei kiinteitä EUR-rajoja

## Toimialakäännökset (main.py)
```python
INDUSTRY_TRANSLATIONS = {
    'jewelry': {'fi': 'koruliike', 'en': 'jewelry store', 'sv': 'smyckebutik'},
    # ... jne
}
```

## Testaus
- **Aja testit**: `python3 -m pytest tests/ -x -q` (tarkista aina tuore tulos, älä luota dokumentoituun lukuun)
- **Gustav 2.0 testisuitet**:
  - `test_hallucination_guard.py`, `test_competitive_intelligence.py`, `test_threat_history.py`, `test_intelligence_brief.py`, `test_guardian_pulse.py`
- **Manuaalinen**: https://brandista.eu/growthengine/dashboard → aloita analyysi → tarkista Railway logit

## Tärkeät tiedostot — lisäykset v3.1.0
- `agents/config.py` — **UUSI** — yhteinen SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES. Kaikki moduulit importtaavat tästä, ei omia määrittelyjä.
- `database.py` — ThreadedConnectionPool (min=2/max=10) + `run_in_db_thread()` async-wrappi. Käytä `connect_db()` / `release_connection()` kaikkialla.
- `agents/base_agent.py` — `_call_llm()` metodi LLM-kutsuille. Käyttää `_LLM_SEMAPHORE` (max 5 samanaikaista OpenAI-kutsua).

## Tietoturva-arkkitehtuuri (v3.1.0)
- **Salasanat**: `passlib.CryptContext(schemes=["bcrypt"])` — ei SHA256, ei hardkoodattuja salasanoja
- **Käyttäjät**: `_build_users_db()` lukee `ADMIN_USER_EMAIL` / `ADMIN_USER_PASSWORD_HASH` env-muuttujista
- **SECRET_KEY**: `agents/config.py` — fail-fast tuotannossa jos ei asetettu, vakaa dev-fallback kehityksessä
- **Rate limiting**: 10 pyyntöä/min/IP oletuksena (`RATE_LIMIT_ENABLED=true`, `RATE_LIMIT_PER_MINUTE=10`)

## Agenttien eristys (v3.1.0)
- `orchestrator._create_agents_for_run()` — luo tuoreet agent-instanssit per analyysiajo
- `orchestrator.is_running` — property, käyttää `_active_runs: set` seuraamiseen
- `run_analysis()` käyttää aina per-run instansseja — ei singleton-jakoa käyttäjien välillä

## Railway ympäristömuuttujat (pakolliset)
| Muuttuja | Kuvaus |
|---|---|
| `SECRET_KEY` | JWT-allekirjoitusavain — pakollinen tuotannossa |
| `ADMIN_USER_EMAIL` | Admin-kirjautumissähköposti |
| `ADMIN_USER_PASSWORD_HASH` | bcrypt-hash (`python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('salasana'))"`) |
| `SUPER_USER_EMAIL` | Super-admin sähköposti |
| `SUPER_USER_PASSWORD_HASH` | bcrypt-hash |
| `RAILWAY_BACKEND_URL` | Backend-URL CORS-listaan |

## Versiohistoria
- **Versio**: 3.1.0 (Quality Overhaul: Security, Reliability & Performance)
- **Changelog**: `CHANGELOG.md`

## Kehityskäytännöt
- **AINA aja testit** ennen committia: `python3 -m pytest tests/ -x -q`
- **Versiohistoria**: Päivitä `CHANGELOG.md` jokaisessa muutoksessa — päivämäärät, mitä, miksi
- **Learning System**: Jos lisäät uusia ennusteita agenttiin, varmista että verifikaatio on kytketty orchestratorissa
- **SECRET_KEY**: Älä koskaan määrittele paikallisesti — importtaa `agents.config`:sta
- **DB-yhteydet**: Käytä aina `connect_db()` + `release_connection()` — älä kutsu `psycopg2.connect()` suoraan
- **LLM-kutsut**: Käytä `base_agent._call_llm()` — semafoorin ohitus kuormittaa OpenAI-ratelimitin

## Liiketoiminta & Go-to-Market

### Yritystiedot
- **Yritys**: T.Tuomisto, toiminimi (62010 Ohjelmistojen suunnittelu ja valmistus)
- **Yrittäjä**: Tuukka Tuomisto, Espoo
- **Aloitus**: Q2/2026
- **Rahoitus**: Omat säästöt 10K€ + Starttiraha ~4.2K€ + ELY-kehittämisavustus 75K€ (haetaan)

### Go-to-Market (4 kerrosta)
1. **Suoramyynti & kassavirta (kk 1–6)**: BemuFix ylläpitosopimukseksi, 20–30 pk-yritystä kontaktoitu. Growth Engine = myyntityökalu (ilmainen analyysi → avaa konsultointikeskustelun)
2. **Asiantuntija-asema (kk 1–12)**: LinkedIn + blogi, 3 ydinatarinaa (moniagentti, BemuFix-case, persistentti muisti)
3. **Growth Engine: konsultoinnista SaaS:iin (kk 4–12)**: Vaihe A ilmainen myyntityökalu → Vaihe B konsultointipaketti 1.5–2.5K€ → Vaihe C self-service SaaS
4. **Kansainvälinen valmistautuminen (kk 6–12)**: Koodi/API-dokumentaatio englanniksi, UI monikielinen, Product Hunt vuosi 2

### Growth Engine hinnoittelu (locked hybrid model)
| Taso | Hinta | Kohderyhmä |
|---|---|---|
| Free Scan | Ilmainen | Liidien generointi |
| Pro Analysis | 149€/kerta | Pk-yritykset (kertaosto) |
| Pro | 99€/kk | Pk-yritykset (tilaus) |
| Professional | 199€/kk | Kasvuyritykset |
| Enterprise | Custom | Suuremmat yritykset |

### ELY-hankkeen kaupallistamispolku
1. **Tutkimus & validointi (kk 1–8)**: Persistentti muisti BemuFix-ympäristössä, konkreettiset hyödyt mitattu
2. **Tuotteistus (kk 6–12)**: Muisti integroitu Growth Engineen + chatbot-tuotteisiin
3. **SaaS-tuote & skaalaus (vuosi 2+)**: Persistentti muisti itsenäisenä SaaS-komponenttina, Pohjoismaat/Eurooppa

### Liiketoimintadokumentit
- Sijainti: `toiminimi-ttuomisto/` -kansio (ei tässä repossa)
- `starttiraha-liiketoimintasuunnitelma-v2.pdf` — Päivitetty liiketoimintasuunnitelma (GTM, hinnoittelu, ELY-kaupallistaminen)
- `starttiraha-liiketoimintasuunnitelma-v2.md` — Sama md-muodossa
- `saatekirje-taydennys.md` — Saatekirje hakemuksen täydennykseen

## Käyttäjäpreferenssit
- Kieli: Suomi
- Omistaja: Tuukka
