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
- `main.py` - Pää-API, hakutermien käännökset (~rivit 7560-7630)
- `agents/scout_agent.py` - Toimialan tunnistus, kilpailijoiden pisteytys
- `database.py` - Tietokantayhteydet
- `auth_magic_link.py` - Magic link -kirjautuminen
- `stripe_module.py` - Maksut

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
- **Testit**: `python3 -m pytest tests/ -x -q` (342 testiä / 29 skipped)
- **Tunnettu**: `test_detect_industry_technology` failaa lokaalisti (puuttuva `jwt`-moduuli)
- **Manuaalinen**: https://brandista.eu/growthengine/dashboard → aloita analyysi → tarkista Railway logit

## Versiohistoria
- **Versio**: 2.2.2
- **Changelog**: `CHANGELOG.md`

## Kehityskäytännöt
- **AINA aja testit** ennen committia: `python3 -m pytest tests/ -x -q`
- **Versiohistoria**: Päivitä `CHANGELOG.md` jokaisessa muutoksessa — päivämäärät, mitä, miksi
- **Learning System**: Jos lisäät uusia ennusteita agenttiin, varmista että verifikaatio on kytketty orchestratorissa

## Käyttäjäpreferenssit
- Kieli: Suomi
- Omistaja: Tuukka
