# Cross-Product Event Bus — Design v0.2 (Phase 4.3)

**Date:** 2026-05-16
**Phase:** 4.3 (Event-driven cross-product coordination)
**Status:** Spec for review. **Supersedes** `2026-05-15-phase-4-3-event-bus-design.md` (v0.1).
**Estimated effort:** 12–14 working days (revised up from v0.1's 10 days; the additions are subscriber-registry, handler-attempts table, denormalised audit, app-populated hot-path columns, retry-policy).

> **Revision r2 (2026-05-16):** Eight pre-migration corrections applied after Tuukka's review.
> 1. Checkpoint is `(subscriber_id, user_id)` — per-user pull with a global cursor was data-lossy (§3, §5).
> 2. `workout_starts_at` / `workout_ends_at` are regular nullable columns populated by the app from Pydantic-validated payload — `(payload->>'…')::timestamptz` is not immutable enough for a STORED generated column (§3, §5 producer flow).
> 3. `event_id` (uuid4 in app) and `event_seq` (explicit `nextval`) are computed **before** INSERT so `envelope_sig BYTEA NOT NULL` is populated in the same INSERT — no insert-then-update window (§5, §7).
> 4. `HealthRecoveryPressureV1` adds `severity_rank SMALLINT` to the payload; subscriber queries filter on the indexed `severity_rank` column, not on string ordering of `severity` (§3, §4, §11 R1).
> 5. `allowed_scope='user_self'` is a **registry rajaus, not a per-call binding** in v1 — the internal-secret caller still picks the `user_id`. Limitation documented (§3, §5, §15).
> 6. `BRANDISTA_EVENT_SIGNING_SECRET == BRANDISTA_INTERNAL_SECRET` in v1 is a tamper-check, not a separate security layer. Wording corrected (§7).
> 7. Ack bounded by `max(event_seq)` of the subscriber's eligible filter — prevents `advance_to_event_seq=999999999` from silently skipping the stream. New 400 `cursor_overshoot_refused` + scenario A2 (§5, §11).
> 8. Idempotency INSERT uses `ON CONFLICT … DO NOTHING RETURNING` (or savepoint) so the outer transaction stays usable for the follow-up SELECT and audit-row write (§5 step 8).

## Changelog from v0.1

Each change is a direct response to a v0.1 hand-waved decision flagged either by Tuukka or by re-reading the producer/consumer codebases. Section labels in parentheses point to the v0.2 sections where the new design lives.

1. **Cursor:** UUID `event_id` replaced by `event_seq BIGSERIAL UNIQUE` as the ordering / checkpoint key. Subscribers `WHERE event_seq > checkpoint` ORDER BY `event_seq`. UUID stays as identity / dedup / signing key, never as ordering. (§3, §5)
2. **Audit retention:** `event_audit.event_id REFERENCES events ON DELETE SET NULL` + denormalised `event_type / source_product / user_id / payload_summary` columns on the audit row. Audit can outlive events without breaking Sprint loppuraportin reconstruction. (§3)
3. **Idempotency key:** UNIQUE `(source_product, event_type, user_id, idempotency_key)` — natural-key is user-scoped, not globally scoped. Same key + different payload → 409 `idempotency_payload_mismatch` (not silent return-old). (§5)
4. **Subscriber registry:** new `event_subscribers` table — `(subscriber_id, allowed_event_types, allowed_source_products, allowed_scope)`. Tehninen rajaus, ei prosessilupaus. `medication.taken` not in any v1 subscriber's allowed list. (§3, §5)
5. **Handler failure default:** "don't advance checkpoint, retry with backoff, dead-letter at attempt 5" — never advance past an event whose handler raised. Dead-letter is an explicit operational action. (§6)
6. **Severity values:** `HealthRecoveryPressureV1.severity ∈ {"mild","moderate","significant"}` to match Continuityn SBE `engine/types.py:Severity`. Mapped 1:1 from `recovery_weakening` detector cutoffs (15% / 25% / above). (§4)
7. **Workout intensity / type:** `WorkoutScheduledV1.intensity ∈ {"kevyt","sopiva","raskas"}` to match Veyran `coach/route.ts` z.enum. No `workout_type` field in v1 (Veyran schema doesn't carry one). `WorkoutCompletedV1.estimated_kcal` removed (no source data). (§4)
8. **Poll latency vs WP B failure-threshold:** spec now distinguishes two latencies. Event-bus delivery latency target p95 ≤ 120 s (60 s default poll + buffer). WP B "conflict-resolution latency <200 ms" refers to single-agent reasoning over conflicting signals once a finding is in-hand — it is **not** an event-bus latency. WP-mapping clarified in §13. (§5, §13)
9. **HMAC timing:** server signs **before INSERT**, after explicit `nextval('events_event_seq_seq')` + `uuid4()`, so `envelope_sig BYTEA NOT NULL` is populated in the same INSERT (no insert-then-update window). Producer-side body has no signature; subscribers verify the signature on GET responses. (§5, §7)
10. **Pydantic strictness:** every event-type model uses `model_config = ConfigDict(extra="forbid")` and `Field(default_factory=list)` for mutable defaults. GDPR scope-rajat depend on this. (§4)
11. **JSONB query paths:** workout.scheduled suppression-window and recovery-pressure severity queries use **app-populated regular columns** (`workout_starts_at`, `workout_ends_at`, `severity_rank`) — STORED generated columns rejected because `(payload->>'…')::timestamptz` is not immutable. App fills them from Pydantic-validated payload at INSERT. (§3, §5 producer flow)
12. **Terminology:** "outbox-pattern without external broker" replaced by **"pull-based event ledger"**. The `events` table is a persistent log; subscribers pull cursor-paginated. No dispatcher, no broker. (§6)

The v0.2 changes are mostly structural — schema additions and stricter contracts. The event-type semantics (which products publish/subscribe, what they do with each type, the Karoliina-case validation flow) are unchanged.

## 1. Context and goal

Identical to v0.1 §1. Phase 4.2 proved agents *read* the same state; Phase 4.3 proves they *react coherently to each other's events*. Karoliinan use case (HRV drop in Continuity → Veyra plan softens next morning) is the canonical end-to-end validation tied to Sprint application §02-hypothesis and WP B + WP D failure-thresholds.

## 2. Scope

### In scope

- Migration `0007_event_bus` — `events`, `event_subscribers`, `event_subscriber_checkpoints`, `event_handler_attempts`, `event_audit` (5 tables).
- `app/events/` package — `EventEnvelope` Pydantic model + registry + per-event-type v1 schemas + HMAC helper + GDPR scan.
- `app/routers/events.py` — three endpoints:
  - `POST /api/v1/events` (canonical-JWT producer, anti-spoof, GDPR scan, idempotency, server-signs).
  - `GET /api/v1/events` (server-to-server pull with subscriber-registry check + cursor pagination + signed envelopes).
  - `POST /api/v1/events/ack` (server-to-server checkpoint commit, advance-only).
- Four event types fully specified (workout.scheduled, workout.completed, health.recovery_pressure, medication.taken-as-schema-only).
- HMAC envelope signing on the wire (server signs, subscriber verifies).
- Retry / dead-letter policy with per-(event, subscriber) attempt counter.
- Subscriber registry: technical rather than process-level access control.
- Replay CLI: `python -m app.events.replay --subscriber=<id> --from-event-seq=<int>`.
- Veyran publisher (`workout.*`) + subscriber (`health.recovery_pressure` → coach-plan softening).
- Continuityn publisher (`health.recovery_pressure` from SBE significant findings) + subscriber (`workout.*` → notification-suppression + ContinuityScore inputs).
- Tests at all three layers (Pydantic schemas + router behaviours + integration round-trip).

### Out of scope (deferred to 4.4+)

- **Push / webhook delivery mode.** Pull at 60 s default poll-interval. If real workload shows >120 s p95 lag, evaluate webhook-mode for specific event-types — but the WP-B 200 ms threshold is not an event-bus target, see §13.
- **External brokers** (Kafka, Redis Streams, SQS). Pull-based ledger handles ≤100k events/day in our profile.
- **Per-event-type retention policies.** Single retention default in v1; per-type override (`events_retention_policy` table) is v2.
- **DB-driven event-type registry.** Hardcoded in `app/events/registry.py` for v1. DB-backed registry is v2.
- **medication.taken end-to-end.** Schema defined for forward-compat; no subscriber has it in `allowed_event_types`; no publisher emits it; user-level opt-in mechanism deferred.
- **Cross-region.** Single Railway region. `event_seq` BIGSERIAL is region-local; if we ever shard, switch to hybrid logical clock — out of scope for v1.

## 3. Schema

### `events` — the ledger

```sql
CREATE TABLE events (
    event_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_seq         BIGSERIAL UNIQUE NOT NULL,
    event_type        VARCHAR(64) NOT NULL,
    event_version     SMALLINT NOT NULL DEFAULT 1,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id            UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source_product    VARCHAR(64) NOT NULL,
    idempotency_key   VARCHAR(255),
    occurred_at       TIMESTAMPTZ NOT NULL,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload           JSONB NOT NULL,
    envelope_sig      BYTEA NOT NULL,
    -- Hot-path filter columns, populated by app from Pydantic-validated payload at INSERT.
    -- NOT generated columns: PostgreSQL requires STORED generated expressions to be IMMUTABLE,
    -- and `text::timestamptz` is only STABLE (parser consults session TimeZone for naive strings).
    -- App-populated keeps the schema portable, the cast deterministic, and the index honest.
    workout_starts_at TIMESTAMPTZ,
    workout_ends_at   TIMESTAMPTZ,
    -- Severity rank for indexed range queries on health.recovery_pressure.
    -- Populated by app from HealthRecoveryPressureV1.severity_rank.
    -- (String comparison on `severity` has no domain ordering; see §4.)
    severity_rank     SMALLINT,
    UNIQUE (source_product, event_type, user_id, idempotency_key)
);
CREATE INDEX ix_events_user_seq ON events (user_id, event_seq);
CREATE INDEX ix_events_type_seq ON events (event_type, event_seq);
CREATE INDEX ix_events_workout_window
    ON events (user_id, workout_starts_at, workout_ends_at)
    WHERE event_type = 'workout.scheduled';
CREATE INDEX ix_events_recovery_severity
    ON events (user_id, severity_rank, occurred_at DESC)
    WHERE event_type = 'health.recovery_pressure';
```

Decisions:

- **`event_seq BIGSERIAL UNIQUE`** is the cursor / checkpoint key. UUID `event_id` is the identity / signing / dedup key. The split removes the v0.1 bug where the cursor expression `WHERE event_id > checkpoint` was nonsensical (UUID v4 not monotonic).
- **`UNIQUE (source_product, event_type, user_id, idempotency_key)`** — natural-key per user-context. Two different users producing the same `workout_3f2c1e09:scheduled` key is fine; one user POST'ing twice is an idempotent dedup.
- **`envelope_sig BYTEA NOT NULL` is populated in the same INSERT, not in a follow-up UPDATE.** The router computes `event_id` (uuid4) and `event_seq` (`SELECT nextval('events_event_seq_seq')`) before the INSERT, signs the canonical envelope including those values, then INSERTs the row with the signature already in hand. See §5 + §7.
- **`workout_starts_at` / `workout_ends_at` / `severity_rank` are regular columns the app populates** from the already-Pydantic-validated payload at INSERT time. Less clever than `GENERATED ALWAYS … STORED`, more portable, and the cast happens in Python where the timezone semantics are explicit.
- `received_at` retained for audit / observability; no longer the cursor.

### `event_subscribers` — registry, technical access control

```sql
CREATE TABLE event_subscribers (
    subscriber_id            VARCHAR(64) PRIMARY KEY,
    allowed_event_types      TEXT[] NOT NULL,
    allowed_source_products  TEXT[] NOT NULL,
    allowed_scope            VARCHAR(16) NOT NULL,  -- 'user_self' in v1
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Seed rows (v1 production):

| subscriber_id | allowed_event_types | allowed_source_products | allowed_scope |
|---|---|---|---|
| `continuity-sbe-pipeline` | `{workout.scheduled, workout.completed}` | `{veyra}` | `user_self` |
| `veyra-coach-builder` | `{health.recovery_pressure}` | `{continuity}` | `user_self` |

`medication.taken` is in nobody's allowed list. Defining the schema without giving any subscriber the right to read it is the technical rajaus that turns "default off" from a process promise into a code-enforced refusal. Adding read access requires an INSERT into this table — a deliberate, reviewable operation.

`allowed_scope='user_self'` describes the **kind of events the subscriber is permitted to read** (own-user-only, no cross-user aggregation). It is **not** a per-call binding between subscriber and user. In v1 the internal-secret holder picks `user_id` on every GET; brandista-api filters events to that user but does not prove the caller is legitimately acting for that user beyond holding the secret.

This is acceptable in v1 because the internal secret is treated as fully trusted server-to-server credential (same trust level as the Phase 4.2 internal facts endpoint). It is **not** defence-in-depth — a compromised secret reads any user's events. v2 closes this gap with one of:
- a signed `X-Brandista-Subject-User` header issued by the subscriber's identity provider, or
- a server-side `(subscriber_id, user_id)` allowlist that the API consults before returning rows.

Listed as a known limitation in §15.

### `event_subscriber_checkpoints` — pull cursor state, **per (subscriber, user)**

```sql
CREATE TABLE event_subscriber_checkpoints (
    subscriber_id              VARCHAR(64) NOT NULL REFERENCES event_subscribers(subscriber_id),
    user_id                    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_processed_event_seq   BIGINT NOT NULL DEFAULT 0,
    last_processed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subscriber_id, user_id)
);
```

**Why per-user, not global:** GET is per-user (allowed_scope='user_self'), so the cursor must be per-user too. With a single global `last_processed_event_seq=1000`, a pull on user A that processes seq=1000 would advance the cursor past every user B event in `[0..1000]` that the subscriber never had a chance to see. With per-user checkpoints, each user's stream advances independently and no event is silently skipped.

Ack rule (per (subscriber, user)): new value must be ≥ current value (advance-only). Equal → idempotent no-op. Smaller → 400 `cursor_rewind_refused`.

Bootstrap rule: missing row → treat as `last_processed_event_seq=0` (do not auto-create on GET; let the first successful ack INSERT it). This keeps the table sparse — only users a subscriber has actually pulled exist.

### `event_handler_attempts` — retry state

```sql
CREATE TABLE event_handler_attempts (
    event_id          UUID REFERENCES events(event_id) ON DELETE CASCADE,
    subscriber_id     VARCHAR(64) REFERENCES event_subscribers(subscriber_id),
    attempts          SMALLINT NOT NULL DEFAULT 0,
    last_attempt_at   TIMESTAMPTZ,
    last_error        VARCHAR(255),
    dead_lettered_at  TIMESTAMPTZ,
    PRIMARY KEY (event_id, subscriber_id)
);
```

Subscriber-side runtime updates this row when it pulls an event for handling. A handler raise increments `attempts` and writes `last_error`; the cursor does NOT advance. Next pull retries the same event. After `attempts >= 5` the subscriber sets `dead_lettered_at` and the cursor advances past the event. Operator can re-queue manually via replay CLI (see §10).

### `event_audit` — denormalised, retention-independent of `events`

```sql
CREATE TABLE event_audit (
    id               BIGSERIAL PRIMARY KEY,
    -- FK is SET NULL so audit outlives event after retention sweep.
    event_id         UUID REFERENCES events(event_id) ON DELETE SET NULL,
    -- Denormalised — readable after the events row is purged.
    event_seq_at_audit BIGINT NOT NULL,
    event_type       VARCHAR(64) NOT NULL,
    source_product   VARCHAR(64) NOT NULL,
    user_id          UUID NOT NULL,
    org_id           UUID NOT NULL,
    payload_summary  JSONB NOT NULL,  -- per-type subset, see §4
    actor_kind       VARCHAR(16) NOT NULL,   -- 'producer' | 'subscriber'
    actor_id         VARCHAR(64) NOT NULL,   -- source_product or subscriber_id
    action           VARCHAR(64) NOT NULL,
    -- 'published' | 'handled' | 'handle_failed_retry' | 'handle_failed_dead_lettered' | 'cursor_advanced'
    actor_meta       JSONB,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_event_audit_user_occurred ON event_audit (user_id, occurred_at DESC);
CREATE INDEX ix_event_audit_event_id ON event_audit (event_id) WHERE event_id IS NOT NULL;
```

Decisions:

- **FK ON DELETE SET NULL + denormalised payload-summary**: events live ~365 days, audit lives ~730 days (Sprint loppuraportti reconstruction window + 1 year buffer). When `events` row is purged, audit row keeps `event_seq_at_audit`, `event_type`, `payload_summary` so the Sprint loppuraportti narrative can still be rebuilt.
- **`actor_kind` + `actor_id`** instead of overloaded `actor`. Separates producer from subscriber semantics; queries can filter on either dimension cleanly.
- **`payload_summary`** is a per-event-type subset of `payload` keeping only the fields the Sprint narrative actually quotes (see each event type in §4). Full payload only lives in `events`. This keeps `event_audit` storage bounded — Sprint loppuraportti doesn't need raw HRV-ms.

## 4. Event types (v1)

Each event type lives in `app/events/types/<type>_v1.py`. All use `model_config = ConfigDict(extra="forbid")` to enforce the no-unexpected-fields rule that the GDPR scope-rajat (§9) depend on.

### `workout.scheduled` (veyra → continuity-sbe-pipeline)

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

VeyranIntensity = Literal["kevyt", "sopiva", "raskas"]  # matches coach/route.ts z.enum

class WorkoutScheduledV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    intensity: VeyranIntensity
    title: str = Field(min_length=1, max_length=60)  # mirror WorkoutDayShape.title
    duration_descriptor: str = Field(min_length=1, max_length=40)  # mirror .duration
    equipment_summary: list[str] = Field(default_factory=list, max_length=20)
```

Notes:
- **No `workout_type` field** — Veyran `WorkoutDayShape` doesn't have one. `title` + `intensity` carry the human-readable description.
- **`intensity` enum matches Veyran z.enum** verbatim (kevyt/sopiva/raskas) rather than a translated alias. Continuity reads strings, doesn't interpret semantically — the medication-suppression decision is based on the time window, not intensity.
- **`equipment_summary` not `equipment`** + `Field(default_factory=list, max_length=20)` — name disambiguates from the `equipment.*` facts already in Phase 4.2 facts API. Max 20 items is a guard against malformed plans, not a product decision.

Consumer behaviour (continuity-sbe-pipeline subscriber):
- Pulls events for current user, filters `event_type='workout.scheduled' AND workout_ends_at >= now - 1h AND workout_starts_at <= now + 24h` (uses `ix_events_workout_window` on the app-populated columns).
- For each future medication reminder scheduled within `[starts_at - 15min, ends_at + 15min]`, suppress and write audit row.

`payload_summary` (denormalised to audit): `{starts_at, ends_at, intensity, title}`. No equipment list (not Sprint-narrative-relevant).

### `workout.completed` (veyra → continuity-sbe-pipeline)

```python
class WorkoutCompletedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    started_at: datetime
    ended_at: datetime
    completed_exercises_count: int = Field(ge=0, le=50)
    perceived_exertion_1_to_10: int | None = Field(default=None, ge=1, le=10)
```

Notes:
- **No `workout_type`** — same reason as scheduled.
- **No `estimated_kcal`** — Veyran data doesn't carry it.
- **`completed_exercises_count`** is what Veyran completion-state actually tracks (per-exercise tap-to-tick mainittu CLAUDE.md:ssa). Honest proxy for "did the workout happen", not a calculated training-load.

Consumer behaviour: ContinuityScore-laskuri lukee viime 7 päivän `workout.completed`-eventit `event_type, user_id, event_seq` -indeksin kautta. Chapter-detector tunnistaa `consecutive_training_strain` jos `count(*) > 5 AND avg(perceived_exertion) >= 7` 7 päivän ikkunassa.

`payload_summary`: `{started_at, ended_at, completed_exercises_count, perceived_exertion_1_to_10}`. Sprint loppuraportti voi sanoa "user logged N workouts in this window with average RPE M".

### `health.recovery_pressure` (continuity → veyra-coach-builder)

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
from continuity_api.engine.types import Severity  # ["mild", "moderate", "significant"]

# Single source of truth for the rank ordering. Domain ranking, NOT alphabetical.
SEVERITY_RANK: dict[Severity, int] = {"mild": 1, "moderate": 2, "significant": 3}

class HealthRecoveryPressureV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_at: datetime
    severity: Severity  # 1:1 with SBE finding severity
    severity_rank: int = Field(ge=1, le=3)  # MUST match SEVERITY_RANK[severity]
    hrv_drop_pct: float = Field(le=0.0)  # negative; SBE only emits below baseline
    contributing_signals: list[Literal["hrv_below_baseline", "sleep_deficit", "rhythm_deviation"]] = (
        Field(default_factory=list, max_length=4)
    )

    @model_validator(mode="after")
    def _rank_matches_severity(self) -> "HealthRecoveryPressureV1":
        if self.severity_rank != SEVERITY_RANK[self.severity]:
            raise ValueError(
                f"severity_rank={self.severity_rank} disagrees with severity={self.severity!r} "
                f"(expected {SEVERITY_RANK[self.severity]})"
            )
        return self
```

Notes:
- **Why `severity_rank` is in the payload (and on the row).** PostgreSQL string ordering puts `mild < moderate < significant` only by coincidence; `severity >= 'moderate'` is **not** a domain comparison. The publisher computes `severity_rank` from `SEVERITY_RANK[severity]` and the validator asserts the two agree. The router copies `severity_rank` to the indexed `events.severity_rank` column at INSERT. Subscribers filter on `WHERE severity_rank >= 2` (moderate-or-worse) using `ix_events_recovery_severity`.
- **`severity` reuses Continuityn SBE Literal** so producer-side mapping is trivial — directly forward the recovery_weakening `FindingCore.severity`. The mapping is:
  - SBE `mild`: drop 10-15% → `severity=mild`, `severity_rank=1`
  - SBE `moderate`: drop 15-25% → `severity=moderate`, `severity_rank=2`
  - SBE `significant`: drop >=25% → `severity=significant`, `severity_rank=3` (Karoliinan threshold)
- **`hrv_drop_pct` as aggregate, not raw `hrv_rmssd`.** Foundation invariant #3 + Sprint application §3.2's GDPR Art. 9 -piikki: no raw biometric values traverse the event bus. Pydantic-validator enforces by `extra="forbid"` (raw_hrv_ms etc. raise validation error).
- **`contributing_signals`** is a list of categorical labels — not values, not timestamps, not magnitudes. Veyran coach knows "user is under recovery pressure including a sleep deficit" without seeing the actual sleep data.

Consumer behaviour (veyra-coach-builder subscriber):
- Pulls events for current user, filters `event_type='health.recovery_pressure' AND severity_rank >= 2 AND observed_at >= now - 24h`. The `ix_events_recovery_severity` partial index handles the range.
- Reads the most recent matching event. If `severity='significant'` (`severity_rank=3`), next-day plan is forced to `kevyt` workout or rest. If `severity='moderate'` (`severity_rank=2`), intensity downgrades one step (raskas→sopiva, sopiva→kevyt). The decision branches on the named severity, not on the rank — the rank exists for indexed filtering, not for behaviour selection.
- Audit row written when coach-plan-builder consumes the event.

`payload_summary`: `{observed_at, severity, hrv_drop_pct, contributing_signals}`. The Karoliina-narrative reads directly off this.

### `medication.taken` (schema only — no v1 subscriber)

```python
class MedicationTakenV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taken_at: datetime
    scheduled_at: datetime
    delta_minutes: int  # signed
```

Notes:
- **No drug name, no dose, no prescription id.** GDPR Art. 9 — same defense as facts API `app/auth/facts_safety.py`.
- **Not in any subscriber's `allowed_event_types`** in v1 (see §3 registry). Continuity does not publish this in v1.
- **Schema lives so v2 can implement opt-in cleanly** without a schema migration. Producer-side opt-in mechanism is a Phase 4.4+ scope.

Acceptance of this event-type into a subscriber's allowed list is a deliberate operational action (INSERT into `event_subscribers.allowed_event_types`). The v1 spec mandates that this INSERT is coupled to a user-facing opt-in row in `user_profile` — but that's a future migration, not a v1 deliverable.

## 5. API contract

All three endpoints mount under `/api/v1/events`. Dual-mount on `app/main.py` + `main.py` per the Phase 4.2 pattern.

### `POST /api/v1/events` — producer

Auth: canonical v2 JWT (`get_current_canonical_user`).

Body:

```json
{
  "event_type": "workout.scheduled",
  "event_version": 1,
  "source_product": "veyra",
  "occurred_at": "2026-05-16T15:00:00Z",
  "idempotency_key": "veyra:workout_3f2c1e09:scheduled",
  "payload": {
    "starts_at": "2026-05-16T18:00:00Z",
    "ends_at": "2026-05-16T18:45:00Z",
    "intensity": "sopiva",
    "title": "Zone 2 polkupyörä",
    "duration_descriptor": "45 min",
    "equipment_summary": []
  }
}
```

Server actions (single SQL transaction unless noted):
1. Validate `source_product == JWT.product` (anti-spoof per Phase 4.2 audience-mapping policy).
2. Reject `PRODUCT_UNKNOWN` tokens (no canonical product → no publish capability).
3. Resolve `event_type` against `app/events/registry.py`. Unknown → 400.
4. Validate `payload` against the per-type Pydantic model (`WorkoutScheduledV1` etc.) — `extra="forbid"` catches unexpected fields. Run GDPR scan (mirror of `app/auth/facts_safety.py`) over the validated payload.
5. **Pre-compute identity & ordering** so the signature can be written in the same INSERT:
   - `event_id = uuid4()` (application-generated).
   - `event_seq = (SELECT nextval('events_event_seq_seq'))` — explicit nextval call returning the value the BIGSERIAL would have allocated. Sequence consumption is durable even if the INSERT aborts; gaps in `event_seq` are expected and harmless (cursors skip them naturally).
   - Derive hot-path columns from the validated payload: `workout_starts_at` / `workout_ends_at` (for `workout.scheduled`), `severity_rank` (for `health.recovery_pressure`).
6. Compute `envelope_sig = HMAC_SHA256(BRANDISTA_EVENT_SIGNING_SECRET, message)` with
   `event_id ++ "|" ++ event_seq ++ "|" ++ event_type ++ "|" ++ event_version ++ "|" ++ user_id ++ "|" ++ occurred_at_iso8601 ++ "|" ++ sha256_hex(canonical_payload_json)` — see §7 for the canonical byte form.
7. Single INSERT into `events` with all NOT NULL columns (`event_id`, `event_seq`, `envelope_sig`, hot-path columns) populated. The `BIGSERIAL` definition still owns the sequence; we just supplied the value explicitly.
8. **Idempotency handling — must not poison the transaction.** A plain INSERT that hits the unique constraint puts the whole Postgres transaction into `aborted` state, so any subsequent SELECT inside the same transaction errors with `current transaction is aborted, commands ignored`. Two acceptable implementations:
   - **Preferred — `INSERT … ON CONFLICT … DO NOTHING RETURNING`.** Single statement. If RETURNING is empty, the row already existed; follow up with a SELECT in the same transaction (no abort) and compare canonical payloads.
     ```sql
     INSERT INTO events (event_id, event_seq, ..., envelope_sig)
     VALUES (...)
     ON CONFLICT (source_product, event_type, user_id, idempotency_key)
     DO NOTHING
     RETURNING event_id, event_seq, envelope_sig;
     ```
     Empty result → `SELECT event_id, event_seq, payload, envelope_sig FROM events WHERE (source_product, event_type, user_id, idempotency_key) = (...)`.
   - **Alternative — SAVEPOINT around the INSERT.** Wrap the INSERT in a `SAVEPOINT idem; … EXCEPTION WHEN unique_violation THEN ROLLBACK TO SAVEPOINT idem; …` block (or SQLAlchemy `session.begin_nested()`), then SELECT existing. Slightly more code, identical guarantee.
   - Both leave the outer transaction healthy so the §9 audit-row INSERT and the response logic can run.

   Comparison of canonical payloads then determines the response:
   - Match → 200 with the existing row's `envelope_sig` (true idempotent return). The allocated `event_seq` is intentionally not used — the sequence advances, the row does not duplicate.
   - Mismatch → 409 `idempotency_payload_mismatch`.
9. Write `event_audit` row in the same transaction: `actor_kind='producer'`, `actor_id=source_product`, `action='published'`, `payload_summary=<per-type summary>`.
10. Return 201 (new) or 200 (idempotent dedup).

Idempotency: if `(source_product, event_type, user_id, idempotency_key)` already exists with **the same payload** → 200 (return existing row). Same key + different payload → 409 `idempotency_payload_mismatch`. Producer must either use a new key for the new payload or accept the prior row.

### `GET /api/v1/events` — subscriber pull (server-to-server)

Auth: `X-Brandista-Internal-Auth` header (same secret as Phase 4.2 internal facts).

```
GET /api/v1/events
  ?subscriber_id=continuity-sbe-pipeline
  &user_id=<uuid>
  &limit=100
```

Server actions:
1. Look up `event_subscribers WHERE subscriber_id=…`. Unknown → 404.
2. Look up `event_subscriber_checkpoints WHERE subscriber_id=… AND user_id=…`. Missing → treat as `last_processed_event_seq=0` (do not auto-INSERT; let `POST /ack` create the row on first advance).
3. Query: `SELECT * FROM events WHERE user_id=? AND event_seq > checkpoint.last_processed_event_seq AND event_type = ANY(subscribers.allowed_event_types) AND source_product = ANY(subscribers.allowed_source_products) ORDER BY event_seq LIMIT 100`.
4. Response items include `envelope_sig` so subscriber can verify.
5. Returns `{ events: [...], next_event_seq: <int or null> }`. `next_event_seq` non-null indicates more pages.
6. **Does NOT advance the checkpoint.** Subscriber explicitly acks via the next endpoint.

`allowed_scope='user_self'` in v1 is registry-level: it declares the subscriber is only ever permitted own-user reads. The per-call binding between subscriber and the requested `user_id` is **not** cryptographically enforced in v1 — any holder of `BRANDISTA_INTERNAL_SECRET` can request any user's events. v2 path is documented in §15.

### `POST /api/v1/events/ack` — subscriber checkpoint commit

Auth: same internal-secret.

```json
{
  "subscriber_id": "continuity-sbe-pipeline",
  "user_id": "…",
  "advance_to_event_seq": 12345
}
```

Server actions:
1. Resolve current checkpoint for `(subscriber_id, user_id)` — missing row → treat as `last_processed_event_seq=0`.
2. **Compute eligible upper bound** — SELECT `max(event_seq)` from `events` filtered by the same `(user_id, allowed_event_types, allowed_source_products)` as GET would use. This is the largest `event_seq` the subscriber could legitimately have observed; anything above it is by definition not yet visible to this subscriber for this user.
3. If `advance_to_event_seq < current` → 400 `cursor_rewind_refused`.
4. If `advance_to_event_seq == current` → 200 idempotent no-op (no row mutation).
5. If `advance_to_event_seq > max_eligible_event_seq` → 400 `cursor_overshoot_refused` with `{"max_eligible_event_seq": N}` in the body. Subscribers must ack the last event they actually pulled, not a speculative future value. This is the guardrail against `advance_to_event_seq=999999999` silently skipping the entire stream.
6. Else UPSERT `event_subscriber_checkpoints (subscriber_id, user_id) DO UPDATE SET last_processed_event_seq=..., last_processed_at=now()` + write audit row `action='cursor_advanced'` carrying both old and new cursor values.

Subscriber convention: ack the `event_seq` of the **last event of the batch the consumer successfully handled** (or successfully dead-lettered). This is what `eligible_event_seq` enforces — the value must be a real event the subscriber's filter actually exposes. Test S5 / A2 in §11 verify the overshoot refusal.

## 6. Pull-based event ledger (not "outbox-pattern")

Conventional outbox pattern needs a worker that polls an outbox table and pushes to an external broker. We have no broker. The `events` table is itself a persistent log; subscribers pull cursor-paginated. Terminology updated throughout the spec.

The key correctness property of this layout is **at-least-once-with-application-idempotency**:
- Producer write is one SQL INSERT — atomic by Postgres.
- Subscriber pull is a cursor SELECT — no events go missing while idle.
- Subscriber ack is explicit and advance-only — a crash mid-handle reprocesses, never skips.
- Application handlers are responsible for being idempotent. The §11 scenarios document each handler's dedup approach.

When (if) the system grows past a Postgres-pullable load (≥100k events/day) and we add an external broker, this layout admits an additive change: a dispatcher worker tails `events` and republishes to the broker; subscribers can choose pull or subscribe-to-broker.

## 7. HMAC signing — server-side, not producer-side

`envelope_sig` is **server-computed before INSERT** and stored on the `events` row in the same statement. The producer's POST body does not (and cannot) carry it — the client never sees `event_id` or `event_seq`. The router generates `event_id = uuid4()` and consumes the BIGSERIAL via explicit `nextval('events_event_seq_seq')`, signs the envelope, and INSERTs the row with `envelope_sig` already populated. No insert-then-update window, no `NULL`-then-`NOT-NULL` dance:

- **POST publish:** no signature on the request body. Producer-auth is canonical JWT + anti-spoof.
- **GET pull response:** each event item includes `envelope_sig`. Subscriber verifies before processing.
- **POST ack:** no signature; internal-secret + subscriber-registry are the auth.

Signing key: **`BRANDISTA_EVENT_SIGNING_SECRET`** env. In v1 this resolves to **the same value as `BRANDISTA_INTERNAL_SECRET`** — one secret to rotate, simpler operations. Because both layers share the secret, the envelope signature is best understood as a **tamper-check on transport** (catches in-flight bit-flips, mis-routing, replay of a stale body against a new event_id), **not** as a defence-in-depth boundary against secret compromise. If the internal secret leaks, both transport auth and envelope signatures are compromised together.

If future requirements need real defence-in-depth (e.g. per-subscriber keys, KMS-managed signing keys, or cross-region trust boundaries), splitting the secrets is an env-rename + redeploy with no code change.

Signing string (canonical, byte-exact):
```
event_id || "|" || event_seq || "|" || event_type || "|" || event_version || "|" || user_id || "|" || occurred_at_iso8601 || "|" || sha256_hex(canonical_payload_json)
```

`canonical_payload_json` is the JSON-serialised payload with sorted keys + no whitespace — deterministic regardless of which subscriber library serialises.

## 8. Idempotency contract

Producer is responsible for crafting `idempotency_key`. Recommended format: `<source_product>:<natural_id>:<scope>`, e.g. `veyra:workout_3f2c1e09:scheduled`. Empty / NULL means "no idempotency contract" (every POST creates a new row).

UNIQUE constraint scope: `(source_product, event_type, user_id, idempotency_key)`. This permits:
- Same Veyra natural-id for the same user → idempotent dedup.
- Same Veyra natural-id for two different users → distinct rows (legitimate).
- Veyra and Continuity both using `workout_3f2c1e09` as natural-id → distinct rows (no source_product clash).

Payload-mismatch handling (the v1 strictness):
- Insert hits the unique constraint → SELECT the existing row.
- Compare `canonical_payload_json(existing.payload)` to `canonical_payload_json(incoming.payload)`.
- Match → 200 with existing row's `envelope_sig` (true idempotent).
- Mismatch → 409 `idempotency_payload_mismatch`. The caller must either send a new `idempotency_key` for the new payload, or accept that the original write is the source of truth.

This means producers cannot "update" an event via idempotency-key reuse. If a workout's `ends_at` changes, the producer publishes a new event with a new key (likely correlated by the same `natural_id`). Subscribers see both — handler decides whether to apply the latest. Out-of-band update events are a future schema extension if needed.

## 9. GDPR boundary per event-type

| Event type | Art. 9 sensitivity | v1 defense |
|---|---|---|
| `workout.scheduled` | Not Art. 9 directly. Scheduling alone is not health data. | `extra="forbid"` on schema; no biometric / dose / drug fields in any v1 payload field |
| `workout.completed` | Not Art. 9. Self-rated RPE is not biometric. | Same. `completed_exercises_count` is action data, not health data |
| `health.recovery_pressure` | **Art. 9**. Aggregate derived from biometric. | Schema accepts only categorical (severity, contributing_signals) + ratio (hrv_drop_pct). Pydantic `extra="forbid"` rejects raw fields. Per-write defensive scan (mirror of `app/auth/facts_safety.py:scan_for_gdpr_violations`) catches any string field containing dose-shaped patterns or diagnosis terms |
| `medication.taken` | **Art. 9**. Even timing reveals medication adherence. | Schema defined but not in any v1 subscriber's allowed list. No write path exists in v1. Acceptance of this type into production is a coupled operation: INSERT into `event_subscribers.allowed_event_types` + INSERT into `user_profile.medication_event_publish_enabled` per user opt-in + reviewable PR |

## 10. Replay CLI

```
python -m app.events.replay --subscriber=<id> --from-event-seq=<int> [--dry-run] [--user-id=<uuid>] [--limit=N]
```

Pulls events from the named subscriber's `(allowed_event_types, allowed_source_products)` scope, starting at `from-event-seq`. For each event, invokes the subscriber's handler in the same process.

- `--dry-run`: do not advance checkpoint, do not invoke handler — print the timeline that would have been processed. Used for Sprint loppuraportti narrative reconstruction.
- `--user-id`: filter further by user, useful for per-user audit reproduction.
- Without flags: actually replays. Handler-attempts table updates as normal. A handler that succeeds idempotently re-acknowledges its prior work; one that's been changed since the original processing applies the new behaviour to historical events. This is the **intentional** value of replay — never used in production normal flow, used for retroactive bug-fix + audit reconstruction.

`--dry-run` is the Sprint loppuraportti producer:
```
python -m app.events.replay --dry-run --user-id=<karoliina> --from-event-seq=0 \
  > karoliina_timeline.txt
```

Output:
```
event_seq=  47821 [continuity → veyra-coach-builder] health.recovery_pressure severity=significant
event_seq=  47832 [veyra → continuity-sbe-pipeline] workout.scheduled intensity=kevyt (was scheduled raskas; adapted)
event_seq=  47844 [veyra → continuity-sbe-pipeline] workout.completed RPE=4
```

## 11. Validation scenarios

| # | Scenario | Pass condition |
|---|---|---|
| **W1** | Veyra publishes `workout.scheduled` at 14:00 for an 18:00 workout | `events` row exists with `workout_starts_at`/`_ends_at` populated by the producer-router from the validated payload. `EXPLAIN ANALYZE` on the suppression-window query (Continuityn medication-cron) uses `ix_events_workout_window`, returns the row in <10 ms. Audit row `notification.suppressed_due_to=event_id`. |
| **W2** | Same Veyra publishes same workout twice with same `idempotency_key`, same payload | Second POST returns 200; one `events` row. |
| **W3** | Same `idempotency_key`, different payload | Second POST returns 409 `idempotency_payload_mismatch`. |
| **R1 — Karoliinan case** | Continuity SBE detects HRV drop 27% (significant), publishes `health.recovery_pressure severity=significant` at 06:14 | Veyra-coach-builder next cron pass (≤60 s + plan-build-time) consumes event, audit row `coach_plan.softened_due_to=event_id` with `before=raskas`, `after=kevyt`. |
| **R2** | continuity-sbe-pipeline restarts after handling event_seq=1000 | Checkpoint persists, restart pulls starting event_seq=1001. No replay, no skip. |
| **F1** | Subscriber handler raises on event_seq=1500 | `event_handler_attempts.attempts` increments. Checkpoint NOT advanced. Next pull retries event_seq=1500. After attempt=5 → dead-letter audit row + checkpoint advances to 1501. |
| **S1** | Producer attempts `health.recovery_pressure` with `raw_hrv_ms=42` field | Pydantic `extra="forbid"` rejects with 422 listing `raw_hrv_ms`. Nothing written to `events` or `event_audit`. |
| **S2** | Veyra-token POSTs `source_product=continuity` | 403 anti-spoof (Phase 4.2 audience-mapping). |
| **S3** | Internal-secret caller GETs `medication.taken` as subscriber-id `veyra-coach-builder` | 200 OK with empty events list (registry filter excludes; not in `allowed_event_types`). No data leak. |
| **S4** | New subscriber-id `attacker-bot` calls GET | 404 (no row in `event_subscribers`); no event data returned. |
| **H1** | Subscriber receives event with tampered payload, `envelope_sig` invalid | Subscriber-side handler library rejects, raises `EnvelopeSignatureError`, audit row `signature_invalid`. Treated as failure → retry counter increments. |
| **A1** | Subscriber sends `advance_to_event_seq` smaller than current checkpoint | 400 `cursor_rewind_refused`. |
| **A2** | Subscriber sends `advance_to_event_seq` larger than `max(event_seq)` for that (subscriber, user, filter) | 400 `cursor_overshoot_refused` with `max_eligible_event_seq` echoed in body. Checkpoint unchanged. |
| **D1** | events retention sweep deletes a 365-day-old row | `event_audit.event_id` becomes NULL for those rows; denormalised columns (`event_type`, `payload_summary`, etc.) still readable. Karoliinan narrative reconstruction works from audit alone. |

## 12. Ship sequence

| # | Step | Effort |
|---|---|---|
| 1 | Migration 0007 (`events`, `event_subscribers`, `event_subscriber_checkpoints`, `event_handler_attempts`, `event_audit`) + SQLAlchemy models | 1 d |
| 2 | `app/events/` package: `EventEnvelope`, registry, 4 type schemas, HMAC helper, GDPR scan, canonical-JSON serialiser | 2 d |
| 3 | `app/routers/events.py`: POST + GET + ack endpoints, dual mount, anti-spoof, idempotency-payload-mismatch handling | 2 d |
| 4 | Replay CLI (`python -m app.events.replay`) including `--dry-run` narrative formatter | 1 d |
| 5 | Unit tests: per-type schema (extra=forbid, default_factory, GDPR rejections), idempotency (match + mismatch), HMAC sign-verify roundtrip, cursor semantics (advance, rewind-refuse, paginate), subscriber-registry filter | 2 d |
| 6 | Integration test: producer → ledger → subscriber pull → ack → checkpoint persists; restart resumes from checkpoint | 0.5 d |
| 7 | Veyran publisher (`workout.scheduled` on coach-route plan-lock; `workout.completed` on Veyran sync) | 1 d |
| 8 | Veyran subscriber: cron-task pulling `health.recovery_pressure`, integration with coach-plan-builder | 1 d |
| 9 | Continuityn publisher: SBE pipeline emits `health.recovery_pressure` on `recovery_weakening` significant findings | 0.5 d |
| 10 | Continuityn subscriber: cron-task pulling `workout.*`, integration with notification-cron + ContinuityScore-laskuri | 1 d |
| 11 | Production rollout + Karoliinan case live validation + audit-query helpers for Sprint loppuraportti | 0.5 d |
| **Σ** | | **~12–14 working days** |

## 13. Sprint WP-mappi (corrected)

| Sprint failure-threshold | Where it's measured | Phase 4.3's role |
|---|---|---|
| **WP B coherence rate ≥ 90%** | `event_audit` queries: `1 - count(action='handle_failed_dead_lettered') / count(action='handled')` over a window | Direct |
| **WP B conflict-resolution latency ≤ 200 ms** | **Single-agent internal:** measured inside `narrator.validator` and `safety.engine.bound()` reconciliation paths. **Not** an event-bus latency. | Not a 4.3 target |
| **WP D hallucination-rate reduction ≥ 40%** | Counter of "Veyran coach recommendations that the safety-facts + recovery-pressure feedback caused to soften" / baseline rate of un-softened recommendations | Direct, fed by Phase 4.2 + 4.3 combined |
| **WP D NPS delta ≥ 15 pts** | External pilot survey | Not derivable from event-bus |
| **Event-bus delivery latency p95 ≤ 120 s** (own SLA) | `event_audit.handled_at - event_audit.published_at` per (event_type, subscriber_id) | Direct |

v0.1 conflated the WP B 200 ms threshold with event-bus latency. v0.2 separates: the 200 ms is internal-to-agent reasoning over conflicting in-hand signals; the event-bus is a 60 s poll cycle (≤120 s p95 SLA) that delivers those signals.

If a future use case requires sub-second cross-product reactivity (e.g. realtime call-out: "user just finished workout — push recovery snack reminder in 90 s"), Phase 4.4 adds webhook push-mode for the relevant event types. v1 does not.

## 14. Open questions

1. **Pre-`event_seq` ordering bootstrap.** First event ever published gets `event_seq=1`. Subscribers initialise with `last_processed_event_seq=0`. No ambiguity. **Closed.**
2. **Retention sweep mechanism.** Daily cron (`apscheduler` like Continuityn `nightly_pipeline_for_timezone`) running `DELETE FROM events WHERE received_at < now() - interval '365 days'`. ON DELETE SET NULL propagates to audit. Run inside brandista-api boot-scheduler. **Decided, listed in §3.**
3. **Subscriber-registry change-control.** v1 allows admins (with brandista-api Postgres access) to INSERT into `event_subscribers`. v2 needs a small admin UI. **Deferred.**
4. **Replay-CLI auth.** v1: env var `BRANDISTA_INTERNAL_SECRET` required at CLI invocation. Admin operation. **Decided.**
5. **Multi-instance brandista-api → BIGSERIAL contention.** Single Railway service today, single Postgres → BIGSERIAL is atomic. If we ever horizontally scale brandista-api, BIGSERIAL still works (Postgres-side atomicity). Cross-region is a different problem (§2 out of scope).

## 15. Risks (v0.2 retained from v0.1 + new)

- **Subscriber idempotency drift.** Same as v0.1. Mitigation: integration test that replays last 100 events and asserts downstream state unchanged.
- **Schema-evolution surprise.** Same. Frozen v1 schemas; v2 is a parallel file. Per-type-version Pydantic snapshot tests.
- **GDPR creep.** Same. Per-event-type schema review via CODEOWNERS on `app/events/types/`.
- **(New) Audit-table bloat.** Denormalised audit rows ~3-5× event rows. 365 days × ~1000 events/day × 4 audits/event × ~2 KB → ~3 GB. Acceptable for now; partition by month if it grows.
- **(New) Dead-letter accumulation.** If a handler has a permanent bug, every event hits dead-letter, audit fills with `handle_failed_dead_lettered`. Mitigation: per-(event_type, subscriber_id) dead-letter rate alert in Sprint observability dashboard.
- **(New) Generated-column-migration cost on existing tables.** Not a v1 risk (table is new), but a note for future event types: adding a generated column requires a STORED rewrite. Plan retroactive generated columns at migration boundaries only.
- **(New, accepted) `allowed_scope='user_self'` is registry-level, not per-call.** v1 trusts `BRANDISTA_INTERNAL_SECRET` to mediate access; a leaked secret can read any user's events. Mitigation path (v2): signed `X-Brandista-Subject-User` header or `(subscriber_id, user_id)` allowlist. Tracked here so Sprint reviewers see we know the seam.
- **(New, accepted) Shared signing & transport secret.** `BRANDISTA_EVENT_SIGNING_SECRET == BRANDISTA_INTERNAL_SECRET` in v1. Envelope signature catches tampering, **not** secret compromise. Split path documented in §7.

## 16. Definition of done

Phase 4.3 ships when all of the following hold against production:

1. Scenarios W1–W3, R1 (Karoliinan case), R2, F1, S1–S4, H1, A1, D1 pass — SQL- or Railway-log-verifiable.
2. `event_audit` shows at least one end-to-end Karoliinan-case timeline: continuity publishes `health.recovery_pressure severity=significant` → veyra-coach-builder consumes within ≤120 s → coach-plan softens.
3. `python -m app.events.replay --dry-run --user-id=<test-user>` produces the timeline against the audit table.
4. Static scan of `events.payload` finds **zero** matches for `_DOSE_PATTERN`, `_FORBIDDEN_DIAGNOSIS_KEYS`, or raw biometric field names (`hrv_rmssd`, `sleep_duration_ms`, etc.).
5. Per-subscriber `subscriber_lag_seconds` p95 < 120 s in steady state.
6. The signed envelope passes verification round-trip in CI (sign on insert, verify on GET).
7. CHANGELOG-tier audit entries on brandista-api, treeniohjelma, and continuity-os-health describe the four event-types, the registry seeds, and the Karoliinan-case live-validation timestamp.

When these are all green, Sprint application §02-hypothesis is event-bus-tested: agents don't only **see** the same state (Phase 4.2), they **react coherently to each other's events** under measurable, auditable conditions.
