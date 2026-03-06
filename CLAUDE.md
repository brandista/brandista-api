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
- `guardian_agent.py` - Laadunvalvonta ja uhka-ennusteet (Learning System)
- `prospector_agent.py` - Liiketoimintamahdollisuudet
- `orchestrator.py` - Agenttien koordinointi + oppimisen verifikaatio
- `blackboard.py` - Agenttien välinen tiedonjako

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
- **Testit**: `python3 -m pytest tests/ -x -q` (416 testiä läpi, 29 skipped, 0 failed)
- **Manuaalinen**: https://brandista.eu/growthengine/dashboard → aloita analyysi → tarkista Railway logit

## Versiohistoria
- **Versio**: 2.3.2
- **Changelog**: `CHANGELOG.md`

## Kehityskäytännöt
- **AINA aja testit** ennen committia: `python3 -m pytest tests/ -x -q`
- **Versiohistoria**: Päivitä `CHANGELOG.md` jokaisessa muutoksessa — päivämäärät, mitä, miksi
- **Learning System**: Jos lisäät uusia ennusteita agenttiin, varmista että verifikaatio on kytketty orchestratorissa

## Käyttäjäpreferenssit
- Kieli: Suomi
- Omistaja: Tuukka
