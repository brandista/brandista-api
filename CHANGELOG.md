# Changelog - Brandista Growth Engine API

Kaikki merkittavat muutokset dokumentoidaan tahan tiedostoon.
Muoto: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

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
