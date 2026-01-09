# Growth Engine 2.0 - Test Prompt
## "Sintra for Serious Business" - Multi-Agent Competitive Intelligence

---

## MIKSI TAMA ON
Growth Engine 2.0 on agenttipohjainen kilpailija-analyysialusta joka:

- Analysoi verkkosivuston 90 sekunnissa
- 6 erikoistunutta AI-agenttia tyoskentelee yhdessa (TRUE SWARM)
- Tuottaa strategisen toimintasuunnitelman + ROI-arviot
- Seuraa kilpailijoita ja varoittaa uhkista

---

## AGENTTITIIMI

| Agentti | Nimi | Rooli | Mita tekee |
|---------|------|-------|------------|
| Scout | Sofia | Market Scout | Loytaa kilpailijat, analysoi sivuston, hakee YTJ/Kauppalehti-tiedot |
| Analyst | Alex | Digital Analyst | Benchmark-vertailu, pisteytys, kategoria-analyysi |
| Guardian | Gustav | Threat Watchdog | RASM-riskianalyysi, liikevaihtoriskit, kilpailijauhka-arviot |
| Prospector | Petra | Opportunity Hunter | Markkinaaukot, quick wins, SWOT, kasvumahdollisuudet |
| Strategist | Stefan | Chief Strategist | Kokonaisstrategia, priorisointi, kilpailuasema |
| Planner | Pinja | Execution Lead | 90-paivan roadmap, toimenpiteet, ROI-laskelmat |

---

## SWARM-ARKKITEHTUURI

```
EXECUTION PLAN:
Phase 1: [Scout]                    <- Loytaa kilpailijat
Phase 2: [Analyst]                  <- Analysoi kaikki
Phase 3: [Guardian + Prospector]    <- RINNAKKAIN: Uhat + Mahdollisuudet
Phase 4: [Strategist]               <- Syntetisoi strategia
Phase 5: [Planner]                  <- Toimintasuunnitelma

KOMMUNIKAATIO:
- MessageBus: Agentit lahettavat alertteja ja dataa toisilleen
- Blackboard: Jaettu muisti johon kaikki kirjoittavat/lukevat
- SharedKnowledge: detected_threats, detected_opportunities, collaboration_results
- Unified Context: Historiallinen data aiemmista analyyseista

NEW IN 2.1 - ACTIVE COLLABORATION:
- Guardian + Prospector keskustelevat reaaliaikaisesti
- Planner validoi suunnitelman muilta agenteilta
- agent_conversation eventit nakyva frontendissa
```

---

## TESTITAPAUKSET

### TEST 1: Perusanalyysi (Happy Path)

```bash
POST /api/v1/agents/analyze
{
  "url": "https://www.example.fi",
  "language": "fi"
}
```

**ODOTETTU:**
- [ ] Scout loytaa 3-10 kilpailijaa
- [ ] Analyst tuottaa benchmark-vertailun
- [ ] Guardian laskee RASM-scoren ja revenue at risk
- [ ] Prospector loytaa quick wins + market gaps
- [ ] Strategist antaa overall score + position
- [ ] Planner generoi 90-day roadmap
- [ ] Kesto: < 90 sekuntia

---

### TEST 2: Swarm-kommunikaatio

**TARKISTA LOGEISTA:**

```
[Scout] ALERT: 3 high-threat competitors found
[Guardian] Received ALERT from scout: High-threat competitors
[Guardian] Forwarded critical alert to Strategist
[Prospector] Received Guardian data: threat assessment
[Prospector] Adding 2 opportunities from threat analysis
[Strategist] Received CRITICAL alert from guardian
[Strategist] Using 5 threats from SharedKnowledge
```

**ODOTETTU:**
- [ ] Scout -> Guardian ALERT toimii
- [ ] Guardian -> Strategist FORWARD toimii
- [ ] Guardian -> Prospector DATA toimii
- [ ] SharedKnowledge sisaltaa dataa kaikilta agenteilta

---

### TEST 3: Blackboard Subscriptions

**TARKISTA LOGEISTA:**

```
[Guardian] RECEIVED competitor data from Blackboard: 5 competitors - WILL USE IN ANALYSIS
[Guardian] Received industry data: IT-palvelut
```

**ODOTETTU:**
- [ ] Guardian reagoi scout.competitors.* paivityksiin
- [ ] Guardian reagoi scout.industry paivityksiin
- [ ] Blackboard entries nakyvat swarm_summary:ssa

---

### TEST 4: Company Intel (Suomalainen yritys)

```bash
POST /api/v1/agents/analyze
{
  "url": "https://www.verkkokauppa.com",
  "language": "fi"
}
```

**ODOTETTU:**
- [ ] Scout hakee YTJ-tiedot (y-tunnus, toimiala)
- [ ] Scout hakee Kauppalehti-tiedot (liikevaihto, henkilosto)
- [ ] Guardian kayttaa OIKEAA liikevaihtoa riskianalyysissä
- [ ] your_company_intel sisaltaa: name, business_id, revenue, employees

---

### TEST 5: Unified Context (Toistuva analyysi)

1. Aja analyysi kerran
2. Aja SAMA analyysi uudelleen

**TARKISTA LOGEISTA (2. kerralla):**

```
[Scout] UNIFIED CONTEXT AVAILABLE - Using historical data!
[Scout] Found 3 tracked competitors in Radar
[Analyst] Previous score: 67/100 (2025-01-08)
[Guardian] Previous RASM: 45/100
[Strategist] Score history: [72, 67, 65]
```

**ODOTETTU:**
- [ ] Agentit nakevat aiemmat tulokset
- [ ] Trendianalyysi toimii (improving/declining/stable)
- [ ] Historialliset uhat ja mahdollisuudet huomioidaan

---

### TEST 6: Guardian + Prospector Active Collaboration (NEW!)

**TARKISTA WEBSOCKET-EVENTEISTA:**

```json
// collaboration_started event
{
  "type": "swarm_event",
  "data": {
    "event_type": "collaboration_started",
    "session_type": "threat_opportunity_analysis",
    "participants": ["guardian", "prospector"]
  }
}

// agent_conversation events
{
  "type": "swarm_event",
  "data": {
    "event_type": "agent_conversation",
    "from": "guardian",
    "from_avatar": "shield",
    "to": "prospector",
    "to_avatar": "gem",
    "message": "Hei Prospector! Loysin 3 kriittista uhkaa. Naetkoe naissa mahdollisuuksia?"
  }
}

{
  "type": "swarm_event",
  "data": {
    "event_type": "agent_conversation",
    "from": "prospector",
    "from_avatar": "gem",
    "to": "guardian",
    "to_avatar": "shield",
    "message": "Loysin mahdollisuuden! Capitalize on competitor gap..."
  }
}

// collaboration_complete event
{
  "type": "swarm_event",
  "data": {
    "event_type": "collaboration_complete",
    "consensus_reached": true,
    "confidence": 0.85
  }
}
```

**TARKISTA TULOKSISTA:**

```json
{
  "collaboration_insight": {
    "consensus_reached": true,
    "solution": "Focus on mobile optimization...",
    "confidence": 0.85,
    "participating_agents": ["guardian", "prospector"],
    "conversation": [
      {"from": "guardian", "message": "Found 3 critical threats"},
      {"from": "prospector", "message": "Opportunities identified"}
    ]
  },
  "prospector_swarm": {
    "threat_opportunities": 3,
    "guardian_data_received": 2
  }
}
```

**ODOTETTU:**
- [ ] WebSocket lahettaa collaboration_started eventin
- [ ] WebSocket lahettaa agent_conversation eventeja
- [ ] WebSocket lahettaa collaboration_complete eventin
- [ ] Frontend nayttaa "Agentit keskustelevat" animaation
- [ ] Prospector loytaa mahdollisuuksia Guardian:in uhkista
- [ ] collaboration_insight sisaltaa consensus-ratkaisun
- [ ] swarm_contributions nayttaa yhteistyon tulokset

---

### TEST 7: Planner Validation (NEW!)

**TARKISTA WEBSOCKET-EVENTEISTA:**

```json
// Planner kysyy Guardianilta
{
  "type": "swarm_event",
  "data": {
    "event_type": "agent_conversation",
    "from": "planner",
    "from_avatar": "clipboard",
    "to": "guardian",
    "to_avatar": "shield",
    "message": "Hei Guardian! Priorisoinko turvallisuustoimenpiteet oikein? (3 tehtavaa)"
  }
}

// Planner kysyy Prospectorilta
{
  "type": "swarm_event",
  "data": {
    "event_type": "agent_conversation",
    "from": "planner",
    "from_avatar": "clipboard",
    "to": "prospector",
    "to_avatar": "gem",
    "message": "Hei Prospector! Onko kasvusuunnitelma kattava? (5 tehtavaa)"
  }
}

// plan_validated event
{
  "type": "swarm_event",
  "data": {
    "event_type": "plan_validated",
    "agents_consulted": ["guardian", "prospector"],
    "phases_count": 3,
    "tasks_count": 15
  }
}
```

**TARKISTA TULOKSISTA:**

```json
{
  "validation_result": {
    "validated": true,
    "agents_consulted": ["guardian", "prospector"],
    "feedback": [
      {"agent": "guardian", "topic": "security_priorities", "status": "consulted"},
      {"agent": "prospector", "topic": "growth_opportunities", "status": "consulted"}
    ]
  },
  "shared_knowledge": {
    "validated_plan": {
      "phases_count": 3,
      "total_tasks": 15,
      "validation": {...}
    },
    "strategic_recommendations": [...]
  }
}
```

**ODOTETTU:**
- [ ] Planner lahettaa agent_conversation eventeja
- [ ] Planner kysyy Guardianilta turvallisuustehtavista
- [ ] Planner kysyy Prospectorilta kasvutehtavista
- [ ] plan_validated event lahetetaan
- [ ] validation_result sisaltaa consulted agents
- [ ] SharedKnowledge sisaltaa validated_plan ja strategic_recommendations

---

### TEST 8: Error Handling

```bash
POST /api/v1/agents/analyze
{
  "url": "https://thisdomaindoesnotexist12345.com",
  "language": "fi"
}
```

**ODOTETTU:**
- [ ] Scout palauttaa virheen mutta ei kaadu
- [ ] Muut agentit kasittelevat tyhjan datan gracefully
- [ ] Palautus sisaltaa errors-listan
- [ ] HTTP status 200 (partial success) tai 500 (total failure)

---

### TEST 9: Performance

**MITTAA:**
- Scout: < 30s (web scraping + competitor search)
- Analyst: < 20s (comprehensive analysis)
- Guardian + Prospector: < 15s (parallel)
- Strategist: < 10s
- Planner: < 10s

**KOKONAISAIKA: < 90s**

**TARKISTA swarm_summary:**
```json
{
  "total_messages": 15-30,
  "blackboard_entries": 10-20
}
```

---

### TEST 10: Frontend Agent Conversation UI (NEW!)

**MANUAALINEN TESTAUS:**

1. Aloita analyysi frontendissa
2. Odota kun Guardian + Prospector aloittavat

**ODOTETTU UI:**
- [ ] Oikeaan alakulmaan ilmestyy "Agentit keskustelevat" ikkuna
- [ ] Header nayttaa violetti gradient + "Agentit keskustelevat" / "Agents Collaborating"
- [ ] Live-indikaattori (vihrea pallo) nakyy
- [ ] Kun collaboration alkaa, nakyy banneri: "Guardian + Prospector analysoidaan yhdessa..."
- [ ] Viestit ilmestyvat animaatiolla:
  - Guardian: "Hei Prospector! Loysin X kriittista uhkaa..."
  - Prospector: "Loysin mahdollisuuden! [title]"
  - Planner: "Hei Guardian! Priorisoinko turvallisuustoimenpiteet oikein?"
- [ ] Kun consensus saavutettu, nakyy vihrea banneri: "Yhteisymmarrys saavutettu! 85%"
- [ ] Analyysin jalkeen ikkuna hairtyy 3 sekunnin kuluttua

---

## ODOTETTU VASTAUSRAKENNE

```json
{
  "success": true,
  "duration_seconds": 45.2,

  "your_company": {
    "name": "Example Oy",
    "business_id": "1234567-8",
    "revenue": 2500000,
    "employees": 15
  },

  "competitors_found": 5,
  "your_score": 72,
  "your_ranking": 2,
  "total_competitors": 5,

  "revenue_at_risk": 125000,
  "rasm_score": 45,

  "market_gaps": [...],
  "competitor_threats": [...],

  "action_plan": {
    "this_week": {...},
    "phase1": [...],
    "phase2": [...],
    "phase3": [...]
  },

  "shared_knowledge": {
    "detected_threats": [...],
    "detected_opportunities": [...],
    "collaboration_results": [...],
    "validated_plan": {...},
    "strategic_recommendations": [...]
  },

  "collaboration_insight": {
    "consensus_reached": true,
    "participating_agents": ["guardian", "prospector"],
    "conversation": [...]
  },

  "validation_result": {
    "validated": true,
    "agents_consulted": ["guardian", "prospector"]
  },

  "swarm_metrics": {
    "predictions_logged": 3,
    "alerts_processed": 5,
    "collaborations_completed": 1
  }
}
```

---

## DEBUG-KOMENNOT

### Logitasot

```python
# Nayta kaikki swarm-viestit
logging.getLogger("agents").setLevel(logging.DEBUG)

# Nayta vain kriittiset
logging.getLogger("agents").setLevel(logging.WARNING)
```

### Swarm Stats

```python
from agents.orchestrator import GrowthEngineOrchestrator

orch = GrowthEngineOrchestrator()
result = await orch.run_analysis(url="https://example.fi")

# Tarkista swarm-statistiikat
print(f"Messages: {result.swarm_summary['total_messages']}")
print(f"Blackboard: {result.swarm_summary['blackboard_entries']}")

# Tarkista agenttien swarm-kontribuutiot
for agent_id, agent_result in result.agent_results.items():
    if hasattr(agent_result, 'swarm_stats'):
        stats = agent_result.swarm_stats
        print(f"{agent_id}: sent={stats.get('messages_sent', 0)}, received={stats.get('messages_received', 0)}")
```

### WebSocket Events (Frontend)

```javascript
// Kuuntele swarm-tapahtumia
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'swarm_event') {
    const eventType = data.data.event_type;

    if (eventType === 'agent_conversation') {
      console.log(`Agent chat: ${data.data.from} -> ${data.data.to}: ${data.data.message}`);
    }

    if (eventType === 'collaboration_started') {
      console.log(`Collaboration started: ${data.data.participants.join(' + ')}`);
    }

    if (eventType === 'collaboration_complete') {
      console.log(`Consensus: ${data.data.consensus_reached}, confidence: ${data.data.confidence}`);
    }

    if (eventType === 'plan_validated') {
      console.log(`Plan validated by: ${data.data.agents_consulted.join(', ')}`);
    }
  }

  if (data.type === 'collaboration') {
    console.log(`Collaboration: ${data.data.participating_agents.join(' + ')}`);
  }
};
```

---

## HYVAKSYMISKRITEERIT

### MVP (Minimum Viable Product)

- [ ] 6 agenttia suorittuu onnistuneesti
- [ ] Swarm-kommunikaatio toimii (logeissa nakyy viestit)
- [ ] SharedKnowledge sisaltaa dataa
- [ ] Kokonaisaika < 90 sekuntia
- [ ] Frontend nayttaa tulokset

### Production Ready

- [ ] Company Intel toimii (YTJ/Kauppalehti)
- [ ] Unified Context toimii (historia)
- [ ] Error handling kattava
- [ ] WebSocket real-time updates
- [ ] Collaboration insight nakyy frontendissa

### TRUE SWARM 2.1 (NEW!)

- [ ] Guardian + Prospector keskustelevat reaaliaikaisesti
- [ ] Planner validoi suunnitelman muilta agenteilta
- [ ] agent_conversation eventit nakyvat frontendissa
- [ ] AgentConversation UI nayttaa viestit animaatiolla
- [ ] collaboration_started/complete eventit toimivat
- [ ] plan_validated event lahetetaan
- [ ] SharedKnowledge sisaltaa validated_plan

### "Sintra for Serious Business"

- [ ] Revenue at risk perustuu OIKEAAN liikevaihtoon
- [ ] 90-day roadmap on konkreettinen ja actionable
- [ ] Trendianalyysi toimii (improving/declining)
- [ ] Kilpailijauhka-arviot ovat relevantteja
- [ ] ROI-laskelmat ovat uskottavia

---

## WEBSOCKET EVENT TYPES (2.1)

| Event Type | Lahettaja | Kuvaus |
|------------|-----------|--------|
| `collaboration_started` | Guardian | Yhteistyo alkaa |
| `agent_conversation` | Guardian, Prospector, Planner | Agentti puhuu toiselle |
| `collaboration_complete` | Guardian | Yhteistyo paattyy |
| `plan_validated` | Planner | Suunnitelma validoitu |
| `message_sent` | Any | Viesti lahetetty |
| `blackboard_update` | Any | Blackboard paivitetty |

---

## FRONTEND COMPONENTS (2.1)

| Komponentti | Tiedosto | Kuvaus |
|-------------|----------|--------|
| `AgentConversation` | `AgentConversation.tsx` | Real-time chat ikkuna |
| `GrowthEngine` | `GrowthEngine.tsx` | Paakontaineri, kasittelee eventit |
| `useAgentWebSocket` | `useAgentWebSocket.ts` | WebSocket hook |

---

*Generated with Growth Engine 2.1 - TRUE SWARM EDITION*
