# Cross-Product Event Bus — Design (Phase 4.3)

**Date:** 2026-05-15
**Phase:** 4.3 (Event-driven cross-product coordination)
**Prerequisite:** Phase 4.2 complete — canonical identity + shared facts API in production, server-to-server internal channel mounted, cross-product loop verified by Railway-log line on 2026-05-15.
**Status:** Spec for review. No code yet.
**Estimated effort:** 9–11 working days.

## 1. Context and goal

Phase 4.2 proved that **agents read the same state**: Veyran coach records `nutrition.allergy` → Continuityn nutrition-finding-generator sees it → user never repeats themselves. The state-sharing direction is a pull-model REST CRUD store with TTL-cached reads. Suitable for facts that hold for weeks/months.

Phase 4.3 proves something architecturally different: **agents react coherently to each other's actions in time**. A Veyran coach locks the 18:00 workout → Continuity suppresses the medication reminder it would have pushed at 18:15. Continuity detects a >2 SD HRV drop → Veyran next-day plan softens automatically. The signals are short-lived (relevant for minutes-hours), latency-sensitive (push or near-real-time pull), and **drive decisions in another product without the user being asked**.

This is the Sprint application §02 hypothesis's load-bearing test:

> "…whether longitudinal state persistence introduces emergent instability at system level when multiple domain agents reason over a single shared organisational memory"

Phase 4.2 demonstrated *shared persistent state* — facts as static reference data. Phase 4.3 demonstrates *shared dynamic state* — events as decision triggers — and forces the **emergent-stability question** into observable territory. WP B failure-thresholds (coherence rate >90%, conflict-resolution latency <200 ms) and WP D failure-thresholds (hallucination reduction >40%, NPS delta >15 pts) are measured **on this layer**.

Karoliinan validointi-case (cross-product-data-sharing.md §4.3) is the canonical end-to-end test: HRV drop in Continuity at night → Veyran morning coach plan automatically softens, no user input, audit-row demonstrating the chain. If that works deterministically, the Sprint §02-hypothesis is functionally validated; if the SBE oscillates or Veyran coach feedback loops produce nonsense, the hypothesis fails its tightest test.

## 2. Scope

### In scope
- Migration `0007_event_bus` — `events`, `event_subscriber_checkpoints`, and `event_audit` tables.
- `app/events/` package — `EventEnvelope` Pydantic model + per-event-type schemas + a small validator registry.
- `app/routers/events.py` — three endpoints under `/api/v1/events`:
  - `POST /` — canonical-JWT producer write (anti-spoofed via the v2 product claim, same as facts API).
  - `GET /` (server-to-server, internal-secret) — pull events newer than caller's last checkpoint, paginated.
  - `POST /ack` (server-to-server) — checkpoint commit.
- Four event types in v1, fully specified:
  - `workout.scheduled` — Veyra → Continuity (medication-suppression)
  - `workout.completed` — Veyra → Continuity (ContinuityScore, chapter-detection)
  - `health.recovery_pressure` — Continuity → Veyra (coach-plan softening)
  - `medication.taken` — Continuity → opt-in subscribers (Sprint-only; default off)
- HMAC-signed envelope on the wire — same SHA-256 + shared-secret pattern as Continuityn entitlement-push.
- Idempotency: producer supplies `idempotency_key`; brandista-api dedup at write.
- Subscriber-side checkpoint pattern: each consumer tracks `last_processed_event_id` server-side so a restart resumes cleanly.
- Replay CLI: `python -m app.events.replay --subscriber=<id> --from-event-id=<uuid>` re-streams events for catch-up.
- Veyran integration: publisher for `workout.*`, subscriber for `health.recovery_pressure`.
- Continuityn integration: publisher for `health.recovery_pressure`, subscriber for `workout.*`.
- Tests: per-schema unit, end-to-end publish→pull→ack round-trip, idempotency-key collision, checkpoint-replay, HMAC-signature validation.

### Out of scope (deferred)
- **Push-mode webhooks** — producer-side outbox-worker pushing to subscriber URLs. Phase 4.3.5 if the polling 60-second latency proves unacceptable; today's use cases tolerate it.
- **External brokers** (Kafka, Redis Streams, SQS) — not needed for the volume profile. The `events` table + per-subscriber checkpoint is the standard pattern for ≤100k events/day, which is one or two orders of magnitude above the current observable load. The schema design admits a future broker migration without rewriting either producers or subscribers.
- **Cross-org fan-out** — every event in v1 is scoped to a single `(user_id, org_id)`. Multi-user / team events (e.g. coach views client) are a Phase 4.5+ scope.
- **Backend-driven push notifications** — `workout.scheduled` only suppresses Continuity's own scheduling logic; the actual APNs / FCM delivery decision stays with each product. Sprint application is explicit that this Sprint is about cognitive infrastructure, not notification UX.
- **Schema-evolution beyond v1** — `event_version: int = 1` is on every payload from day one so v2 schemas can land additively. Migration / deprecation rules are Phase 4.4.

## 3. Schema

### `events` table

```sql
CREATE TABLE events (
    event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type       VARCHAR(64) NOT NULL,
    event_version    SMALLINT NOT NULL DEFAULT 1,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source_product   VARCHAR(64) NOT NULL,
    idempotency_key  VARCHAR(255),
    occurred_at      TIMESTAMPTZ NOT NULL,
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload          JSONB NOT NULL,
    UNIQUE (source_product, idempotency_key)
);
CREATE INDEX ix_events_user_received_at ON events (user_id, received_at);
CREATE INDEX ix_events_type_received_at ON events (event_type, received_at);
CREATE INDEX ix_events_org_received_at ON events (org_id, received_at);
```

Notes:
- `event_id` is the canonical wire ID — what subscribers checkpoint on.
- `received_at` (not `occurred_at`) is the cursor for subscriber pulls — guarantees monotonic forward progress even if a delayed producer back-dates `occurred_at`.
- `idempotency_key` is UNIQUE per (source_product, key) — a Veyra re-POST of the same key returns the existing row, not a duplicate. Empty / NULL key means "no idempotency contract" (every POST creates a new row).
- Indexes cover the three read patterns: per-user replay, per-type subscriber scan, per-org admin queries.

### `event_subscriber_checkpoints` table

```sql
CREATE TABLE event_subscriber_checkpoints (
    subscriber_id           VARCHAR(64) PRIMARY KEY,
    last_processed_event_id UUID NOT NULL,
    last_processed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`subscriber_id` is a stable string per consumer:
- `continuity-pipeline` — Continuityn nightly + on-sync pipeline that reads workout events.
- `veyra-coach-builder` — Veyran coach-plan generator that reads recovery-pressure events.

Each consumer reads `WHERE event_id > checkpoint.last_processed_event_id`, processes, then `POST /api/v1/events/ack` to advance. Process restarts pick up exactly where they left off.

### `event_audit` table

```sql
CREATE TABLE event_audit (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID REFERENCES events(event_id) ON DELETE CASCADE,
    actor           VARCHAR(64) NOT NULL,
    action          VARCHAR(64) NOT NULL,
    actor_meta      JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_event_audit_event_id ON event_audit (event_id);
```

Logs every published-by and handled-by trace. Sprint-report builds the Karoliina-style narrative out of this table:

> "07:14:23 — Continuity-pipeline published `health.recovery_pressure` event_id=… because HRV-drop = 27% (3.1 SD).
> 07:14:24 — Veyra-coach-builder consumed event_id=…, softened next plan from `training_intervals` → `training_zone2`."

Audit-rows on both publish and handle = audit trail of the Sprint hypothesis itself.

## 4. Event types (v1)

Each type is a Pydantic model under `app/events/types/<type>_v1.py`. Wire payload is `EventEnvelope.payload`, validated against the registered v1 schema at write-time on the producer side and at handler-deserialization on the subscriber side.

### `workout.scheduled` (Veyra → Continuity)

```python
class WorkoutScheduledV1(BaseModel):
    starts_at: datetime
    ends_at: datetime
    intensity: Literal["low", "moderate", "high"]
    workout_type: Literal["strength", "zone2", "intervals", "mobility", "rest"]
    equipment: list[str] = []  # informational, max 20 items
```

Consumer behaviour (Continuity):
- Notification scheduler queries `events WHERE event_type='workout.scheduled' AND starts_at <= now+24h AND ends_at >= now`.
- Any medication reminder whose `next_at` falls within `[starts_at - 15min, ends_at + 15min]` is suppressed (logged but not pushed). Audit row: `notification.suppressed_due_to=workout.scheduled`.

GDPR-rajat: no biometric values, no medication identifiers. Workout type + intensity + timing only.

### `workout.completed` (Veyra → Continuity)

```python
class WorkoutCompletedV1(BaseModel):
    started_at: datetime
    ended_at: datetime
    workout_type: Literal["strength", "zone2", "intervals", "mobility", "rest"]
    perceived_exertion_1_to_10: int | None = None  # RPE if user reported
    estimated_kcal: int | None = None  # informational
```

Consumer behaviour (Continuity):
- ContinuityScore-laskuri lukee viime 7 päivän `workout.completed`-eventit komponenttina (training_load proxy).
- Chapter-detector (`engine/chapters.py`) tunnistaa `consecutive_training_strain` -chapter:in jos >5 high-intensity-completion 7 päivässä.
- Audit row: `continuity_score.input=workout.completed`.

### `health.recovery_pressure` (Continuity → Veyra)

```python
class HealthRecoveryPressureV1(BaseModel):
    observed_at: datetime
    hrv_drop_pct: float | None = None  # negative = drop, e.g. -0.27 = 27% below baseline
    sleep_deficit_hours: float | None = None  # positive = behind baseline
    rhythm_deviation_pct: float | None = None  # circadian-drift proxy
    severity: Literal["informational", "advisory", "significant"]
```

GDPR-raja sisäänrakennettu: **no raw HRV values, no sleep timestamps, no medication-context**. Only aggregates. Producer-puolen Pydantic-validator hylkää writeen mukaan tulleen `raw_hrv_ms` -tyyppisen kentän.

Consumer behaviour (Veyra):
- Coach-plan-builder lukee viime 24h `health.recovery_pressure WHERE severity >= 'advisory'` ennen plan-generointia.
- Jos viimeinen pressure-event on `severity='significant'`, plan-builder pakottaa next-day `workout_type='rest'` tai `'mobility'`, ei kysytä käyttäjältä.
- Audit row: `coach_plan.softened_due_to=health.recovery_pressure`.

### `medication.taken` (Continuity → opt-in subscribers)

```python
class MedicationTakenV1(BaseModel):
    taken_at: datetime
    scheduled_at: datetime
    delta_minutes: int  # taken_at - scheduled_at, signed
```

**Default-off**: Continuity does not publish this event-type unless the user opts in via a profile setting (Sprint pilot infrastructure — not in standard Continuity flow).

GDPR Art. 9 erityisturva: tämä on lähinnä terveysdataan luokiteltava. Foundation invariant #3 -tasoinen dose-redaction enforced producer side: schema EI sisällä `drug_name`, `dose_mg`, `prescription_id` -kenttiä. Vain timing-delta.

Consumer behaviour: brandista-api itse ei kuluta, mutta Continuity publishes for audit-rakennetta. Tulee käyttöön step 4.3 -loppupuolella jos Karoliina-pilotin reflexive timing-data tarvitaan.

## 5. API contract

All endpoints sit under `/api/v1/events`. Same router is mounted on both `app/main.py` (modular) and `main.py` (legacy) — dual-mount pattern from Phase 4.2.

### `POST /api/v1/events` — producer

Auth: canonical v2 JWT (`get_current_canonical_user`). Body schema:

```json
{
  "event_type": "workout.scheduled",
  "event_version": 1,
  "source_product": "veyra",
  "occurred_at": "2026-05-15T15:00:00Z",
  "idempotency_key": "veyra:workout:f72e1c45-2026-05-15",
  "payload": {
    "starts_at": "2026-05-15T18:00:00Z",
    "ends_at": "2026-05-15T18:45:00Z",
    "intensity": "moderate",
    "workout_type": "zone2"
  }
}
```

Validation:
- `source_product` must match JWT `product` claim (anti-spoof, identical to facts API).
- `event_type` resolved against registered v1 schemas — unknown type → 400.
- `payload` parsed by per-event-type Pydantic model — failure → 400 with field-level detail.
- `user_id` and `org_id` derived from JWT — never from body.
- If `idempotency_key` is set and `(source_product, idempotency_key)` exists, return 200 with existing row (idempotent) rather than 409.

Response: 201 (new) or 200 (idempotent) with full `EventEnvelope`. Audit row written with `actor=<source_product>`, `action=published`.

### `GET /api/v1/events` — subscriber pull (server-to-server)

Auth: `X-Brandista-Internal-Auth` header (same internal-secret as facts internal endpoint).

```
GET /api/v1/events?subscriber_id=continuity-pipeline&event_types=workout.scheduled,workout.completed&limit=100
```

Behaviour:
- Resolve checkpoint from `event_subscriber_checkpoints WHERE subscriber_id=…`. If no row, start from beginning.
- `SELECT * FROM events WHERE event_id > checkpoint.last_processed_event_id AND event_type IN (…) ORDER BY received_at LIMIT 100`.
- Response includes `events: [...]` + `next_cursor: <event_id>` (last in batch) so consumer can re-pull with `?after_event_id=<next_cursor>` for second page in same processing pass.
- **Does NOT auto-advance the checkpoint**. Consumer must explicitly ack — at-least-once semantics. Combined with idempotent handlers, this gives exactly-once practical behaviour.

### `POST /api/v1/events/ack` — subscriber checkpoint commit

Auth: same internal-secret.

```json
{
  "subscriber_id": "continuity-pipeline",
  "last_processed_event_id": "f72e1c45-…"
}
```

Updates the checkpoint row. Idempotent — re-posting the same event_id is a no-op. Going *backwards* (smaller event_id than current checkpoint) is refused with 400 — accidental rollbacks would re-fire handlers.

Audit row per ack: `actor=<subscriber_id>`, `action=acked`.

## 6. Outbox-pattern (without external broker)

Conventional outbox needs a worker that polls the outbox table and pushes to a broker. We don't have a broker — subscribers pull directly from `events`. So the "outbox" is just the `events` table itself, and the worker is the subscriber's cron.

This works because:
- Producer write to `events` is a single SQL INSERT → atomicity guaranteed by Postgres.
- Subscriber pull is a SELECT with cursor-pagination → exactly-once-by-checkpoint.
- No data lives in a volatile buffer between producer and subscriber.

When (if) we ever add an external broker, the producer side already writes durably. We add an outbox-worker process that tails `events` and publishes to the broker — but subscribers can also keep pulling directly. The transition is additive, not a rewrite.

## 7. HMAC signing

Every wire payload (POST publish, GET response item) carries an `envelope_signature` field computed as:

```
HMAC-SHA256(
  shared_secret = BRANDISTA_EVENT_SIGNING_SECRET,
  message = f"{event_id}|{event_type}|{event_version}|{user_id}|{occurred_at_iso}|{sha256(payload_json_canonical)}"
)
```

Subscribers validate before processing. Tampering with payload or replacing event_id changes the hash → reject.

Why on top of the internal-secret transport auth: the transport secret only proves *who is calling brandista-api*, not *who originally wrote the event*. The signature lets a subscriber verify the brandista-api server itself was the source — defense in depth if a future deployment adds a non-brandista-controlled relay.

Pattern is identical to `billing/internal_push.py` HMAC validation in continuity-api (FOUNDATION_STATUS invariant #5).

## 8. Idempotency

Producer-side:
- `idempotency_key` is producer-chosen. Recommended format: `<source_product>:<event_type>:<natural_key>`, e.g. `veyra:workout.scheduled:workout_id_3f2c1e09`.
- Same key re-POSTed → 200 with existing row. No duplicate.

Subscriber-side:
- Handler is responsible for being idempotent (re-handling the same event_id is a no-op).
- For Continuity's notification-suppression: handler checks "is this workout.scheduled already used to suppress a notification?" before suppressing — natural deduplication on workout_id.
- For Continuity's ContinuityScore: workout.completed contributes to a daily aggregate — same event_id contributing twice would double-count, so handler stores `last_processed_event_id` per (user, day) too.

## 9. GDPR boundaries (per-event-type)

| Event type | GDPR scope | Restriction |
|---|---|---|
| `workout.scheduled` | Not Art. 9 | No restriction |
| `workout.completed` | Not Art. 9 | RPE is self-rated, not biometric |
| `health.recovery_pressure` | **Art. 9** | Aggregates only; no raw HRV-ms, no sleep-event timestamps, no medication context |
| `medication.taken` | **Art. 9** | Opt-in only; default off; no drug name / dose / prescription id |

Producer-side schema validators enforce these constraints at the type-system level: a Veyra developer trying to publish `health.recovery_pressure` with `raw_hrv_ms` in the payload gets a 422 validation error from Pydantic, not a quiet leak.

Mirror of facts API `app/auth/facts_safety.py:scan_for_gdpr_violations` — same defensive scan over the payload before write.

## 10. Replay tool

```
python -m app.events.replay --subscriber=continuity-pipeline --from-event-id=<uuid> --dry-run
```

Re-streams events from `<uuid>` forward to the named subscriber, optionally without advancing checkpoint. Used for:
- Backfill: a Continuity subscriber that was down for a day → run `replay` to catch up after deploy.
- Debug: re-emit a specific event to test a handler change locally.
- Audit reconstruction: Sprint loppuraportin Karoliina-narrative is produced by `replay --dry-run --filter=user_id=karoliina` + render audit rows as a timeline.

## 11. Validation scenarios

| # | Scenario | Pass condition |
|---|---|---|
| **W1** | Veyra publishes `workout.scheduled` at 14:00 for an 18:00 workout | `events` row exists; Continuity subscriber consumes within 60s pull-cycle; medication reminder for 18:15 audit-row `suppressed_due_to=workout.scheduled` |
| **W2** | Same Veyra publishes same workout twice with same `idempotency_key` | Second POST returns 200 with first row's event_id; only one events row exists |
| **R1 — Karoliina** | Continuity SBE detects HRV drop 27% at 06:00 → publishes `health.recovery_pressure severity=significant` | Veyran morning coach build at 07:30 reads the event, plan softens to `zone2` or `rest`; audit row `coach_plan.softened_due_to=<event_id>` |
| **R2** | Subscriber restarts after handling 1000 events | Checkpoint persists, restart picks up exactly at event 1001, no replays |
| **S1** | Producer attempts `health.recovery_pressure` with `raw_hrv_ms=42` field | 422 with Pydantic validation error; nothing written |
| **S2** | Veyra-token attempts `source_product=continuity` | 403 anti-spoof |
| **H1** | Subscriber receives event with tampered payload but valid envelope | HMAC mismatch → reject, audit-row `signature_invalid` |

The Sprint loppuraportin core demonstration: scenario R1 (Karoliina-case) running deterministically + audit-trail.

## 12. Ship sequence

| # | Step | Effort |
|---|---|---|
| 1 | Migration 0007 + SQLAlchemy models | 0.5 d |
| 2 | `app/events/` package: `EventEnvelope`, registry, four type schemas, HMAC helper, GDPR scan | 1.5 d |
| 3 | `app/routers/events.py`: POST, GET, ack endpoints + dual-mount | 1 d |
| 4 | Replay CLI (`python -m app.events.replay`) | 0.5 d |
| 5 | Unit tests (per-type schema, idempotency, HMAC, checkpoint, GDPR refuse) + integration test (publish→pull→ack round-trip) | 1.5 d |
| 6 | Veyran publisher: coach-route `workout.scheduled` on plan-lock + `workout.completed` on sync | 1 d |
| 7 | Veyran subscriber: cron-task pulling `health.recovery_pressure`, feed into coach-plan-builder | 1 d |
| 8 | Continuityn publisher: SBE pipeline emits `health.recovery_pressure` on significant findings | 1 d |
| 9 | Continuityn subscriber: cron-task pulling `workout.*`, feed into notification-suppression + ContinuityScore | 1 d |
| 10 | Live validation scenarios W1, W2, R1, R2, S1, S2, H1 against production | 0.5 d |
| 11 | Audit-helper for Sprint loppuraportti (`audit query --user-id=… --window=…`) | 0.5 d |
| **Σ** | | **~10 working days** |

## 13. Sprint context

Phase 4.3 ships the **WP B + WP D failure-threshold instrumentation**. After this lands, Sprint metrics are computable directly from `event_audit`:

- **Coherence rate** (WP B failure-threshold ≥ 90%) = `1 - (count(events where consumer rejected) / count(events handled))`.
- **Conflict resolution latency** (WP B ≤ 200 ms) = `event_audit.handled_at - event_audit.published_at` p95 per event_type.
- **Hallucination-rate reduction** (WP D ≥ 40%) = ratio of (Veyra plan recommendations rejected by safety-fact merge) over baseline. Comparable against the pre-Phase-4 audit window.
- **NPS delta** (WP D ≥ 15 pts) requires a separate pilot survey — not derivable from event-bus data alone.

The Karoliina-case (scenario R1) is the **sub-second functional demonstration** Sprint reviewers can replay from production audit:

> 06:14:23 — continuity-api: `event=health.recovery_pressure severity=significant id=<uuid>` published.
> 07:30:01 — veyra-coach-builder: pulled batch including <uuid>; coach-plan-builder log: "plan softened: original=intervals → adapted=zone2 reason=recovery_pressure id=<uuid>".

This timeline, reproducible from one SQL query, is the most concrete answer the hakemus can give to "does cross-domain agent coherence work in real-world conditions". Every other Sprint deliverable rests on it.

## 14. Open questions

1. **Poll interval.** Continuityn subscriber default 60 s — is that low enough for `workout.scheduled` 15 min suppression-window? Yes (60 s + 15 min window = 16 min total worst-case). For `health.recovery_pressure` Veyran morning build is once per day, 60 s irrelevant. If we add push-mode later, this drops to seconds.
2. **Retention.** Default 90 days for `events`. `event_audit` 180 days. Configurable per-event-type via `events_retention_policy` table — out of scope for v1 but schema admits it.
3. **Event-type registration mechanism.** v1 hardcodes 4 types in `app/events/registry.py`. v2+ would move to a DB-backed registry to allow per-deploy schema-evolution — but premature now.
4. **What does subscriber do when handler raises?** Default: log + advance checkpoint (skip-and-continue). Alternative: pause checkpoint advance, re-attempt on next pull. Pick skip-and-continue + audit row `handle_failed` for v1, revisit if it produces real production gaps.
5. **Backpressure if subscriber lags hours behind.** No automatic action in v1. Add a `subscriber_lag_seconds` Prometheus metric so we see it; mitigation (rate-limit producer, fan-out to broker) is a Phase 4.3.5 question.
6. **Cross-region eventually.** Single Railway region for v1. If brandista-api ever splits geographically, `events.event_id` UUID is timezone-safe but `received_at` ordering needs hybrid logical clocks. Not a v1 problem.

## 15. Risks

- **Subscriber idempotency drift.** If a Continuity handler accidentally non-idempotent (e.g. counter increment without dedup), restart-replay double-counts. Mitigation: include integration test that intentionally replays the last 100 events and asserts downstream state unchanged.
- **Schema-evolution surprise.** A v2 schema that's strict-additive (new optional fields) is safe. A v2 that renames a field is not. Compile-time guard: v1 model frozen after this PR; v2 is a new file `<type>_v2.py`, never overwrite. Test: per-type-version Pydantic instance matches a frozen JSON snapshot.
- **GDPR creep.** Engineers add a "useful" field over time and don't notice it crosses Art. 9. Mitigation: per-event-type schema review required for any new field (CODEOWNERS rule on `app/events/types/`).
- **Audit-table bloat.** 90-day retention + multiple audit-rows per event → maybe 10x events row count. ~1 GB/year at expected volume; not a problem until end of next year. Add partitioning when needed.

## 16. Definition of done

- Phase 4.3 is shipped when all of the following hold against production:
  1. Scenarios W1, W2, R1, R2, S1, S2, H1 pass (SQL- or Railway-log-verifiable).
  2. `event_audit` shows at least one Karoliina-case round trip (continuity emits `health.recovery_pressure` → veyra consumes → plan softens) without manual intervention.
  3. `python -m app.events.replay --subscriber=… --from-event-id=… --dry-run` produces correct timeline output.
  4. No `raw_hrv_ms`-shaped field, no medication-name field, no dose-field anywhere in the live `events.payload` (audit query confirming `_DOSE_PATTERN` and `_FORBIDDEN_DIAGNOSIS_KEYS` find zero matches).
  5. Continuity-pipeline `subscriber_lag_seconds` p95 < 120 s (subscriber stays caught up).

Once these are green, hakemuksen §02-hypoteesi on Sprint-validointi-tasolla todistettu: agentit eivät vain **näe** samaa state'iä, vaan **muuttavat käyttäytymistään** koherentisti toistensa tuottamiin signaaleihin.
