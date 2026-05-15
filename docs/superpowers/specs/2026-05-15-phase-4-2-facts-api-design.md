# Profile Facts API — Design (Phase 4.2)

**Date:** 2026-05-15
**Phase:** 4.2 (Shared semantic facts across products)
**Prerequisite:** Phase 4.1 complete — canonical platform identity in production, Veyra + brandista-api + Continuity sharing `(user_id, org_id)` UUID space (verified by SQL 2026-05-14, see `tuukan-ja-clauden-tyot/2026-05-14.md` §7).
**Status:** Spec for review. No code changes yet.

## 1. Context and goal

Phase 4.1 wired identity across products. Phase 4.2 wires **semantic state** across products: discrete user-scoped facts that one product writes and the others read.

Worked example — today: a user with a cervical-spine MRI restriction tells Continuity "no impact exercises". Continuity records it as a `safety_class` tag. The next day the same user opens Veyra; the coach proposes burpees because it has no idea about the restriction. The user has to repeat themselves. **After Phase 4.2:** Veyra's coach pipeline reads the safety tag from brandista-api before generating the plan and quietly removes impact exercises. The user never repeats the constraint.

This is the **functional half** of the Sprint §02 hypothesis ("multiple domain agents reasoning over a single shared organisational memory"). Phase 4.1 proved the agents are *talking about the same user*; Phase 4.2 proves their decisions are *informed by the same state*.

## 2. Scope

### In scope
- `profile_facts` table (Alembic migration 0006).
- `POST /api/v1/profile/facts` — write a fact bound to the current user.
- `GET /api/v1/profile/facts?scope=<comma-separated>` — read this user's facts, optionally filtered to scope set.
- `DELETE /api/v1/profile/facts/{fact_id}` — delete a single fact (user-initiated).
- `DELETE /api/v1/profile/facts?source_product=<name>` — bulk delete on product offboarding (admin-only, used when a user revokes a product).
- Canonical-JWT auth on every endpoint via `get_current_canonical_user`.
- Pydantic models for fact lifecycle: `FactCreate`, `Fact`, `FactList`.
- Tests covering: schema validation, scope filtering, auth required, FK to org, source_product bulk delete, GDPR-sensitive content rejection.

### Out of scope (later steps)
- **Aggregate / event-driven facts** (e.g. "average HRV last 14 days", "workout completed at 18:00") → Phase 4.3 event bus, not facts API. Facts API is for state that holds for weeks/months.
- **Active reasoning over facts** (e.g. brandista-api recomputing derived constraints) — clients consume the raw fact set and run their own reasoning.
- **Sharing per-fact ACL** (e.g. "Veyra may write but only Continuity may read"). All products in the same org can read all facts in scopes they request. Per-product visibility is a Phase 4.4+ feature if a concrete need appears.
- **Webhook notifications** when a fact changes — readers poll on the next reasoning pass. Push-on-change is Phase 4.3.
- **Multi-tenant fact-sharing** across orgs (e.g. coach view of a client's facts). Org boundary is hard in Phase 4.2.

## 3. Schema

```python
class ProfileFact(Base):
    __tablename__ = "profile_facts"

    id            UUID PRIMARY KEY DEFAULT gen_random_uuid()
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE
    user_id       UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE
    scope         VARCHAR(32) NOT NULL  -- 'safety' | 'nutrition' | 'training' | 'general'
    key           VARCHAR(120) NOT NULL  -- e.g. 'cervical_spine_no_impact', 'lactose_intolerant'
    value         JSONB NOT NULL  -- structured payload, see §4
    source_product VARCHAR(64) NOT NULL  -- 'veyra' | 'continuity' | 'kirjanpito' | ...
    provenance    VARCHAR(16) NOT NULL  -- 'user_stated' | 'extracted' | 'inferred'
    confidence    VARCHAR(8)  NOT NULL  -- 'high' | 'medium' | 'low'
    expires_at    TIMESTAMPTZ NULL  -- NULL = indefinite
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()

    # Composite unique: a (user, scope, key) is one fact. Same key in
    # different scopes is allowed (e.g. 'iron' in nutrition and safety).
    # A second write upserts (UPDATE, not duplicate row).
    UNIQUE (user_id, scope, key)

    # Indexes
    INDEX (user_id, scope)     -- the most common read path
    INDEX (org_id)              -- admin queries, GDPR purge
    INDEX (source_product)      -- product offboarding cascade
```

**Why these columns:**
- `scope` is a small closed enum — keeps the GET filter simple and forces callers to think about whether a fact is safety-relevant (different consumer set than nutrition).
- `key` + `value` separated so a consumer can match on `key='lactose_intolerant'` cheaply without parsing JSON, then drill into `value` for the structured detail.
- `source_product` makes GDPR-on-offboard a single `DELETE WHERE source_product=X AND user_id=Y` — clean and auditable.
- `provenance` mirrors Brandista's hallucination-guard pattern (`extracted | inferred | user_stated`). Honesty rule: anyone consuming a fact should know whether the user *said* it or a model *deduced* it.
- `confidence` lets readers skip low-confidence facts when stakes are high (Continuity's SBE would only honor `high` for safety_class; Veyra's coach can use `medium` for nutrition preferences).
- `expires_at` is a forward-compat hatch — most facts are indefinite, but "currently injured, expires in 6 weeks" needs a TTL.

## 4. `value` JSONB shape

Free-form per `(scope, key)` pair, but a reference convention to keep readers sane:

```json
// scope=safety, key=cervical_spine_no_impact
{
  "label": "Ei iskutreenejä",
  "blocked_actions": ["impact_cardio", "plyometrics", "running_concrete"],
  "user_note": "MRI 2026-02-23, pullistuma, hermojuurikompressio"
}

// scope=nutrition, key=lactose_intolerant
{
  "label": "Laktoosi-intoleranssi",
  "severity": "moderate",  // 'mild' | 'moderate' | 'severe'
  "alternatives_preferred": ["oat_milk", "almond_milk"]
}

// scope=training, key=available_equipment
{
  "label": "Kotitreeni-kalusto",
  "items": ["dumbbells_20kg_pair", "pull_up_bar", "kettlebell_16"]
}
```

Schema for `value` is **not enforced server-side** in 4.2. Producers and consumers agree informally per `(scope, key)`. We add JSON-schema validation in a later phase if drift becomes a real problem; for now, conservative key naming + lowercase-snake_case discipline is enough.

## 5. API contract

All endpoints require canonical v2 JWT. `user_id` is taken from the JWT — never from the request body. `org_id` is taken from the JWT too.

### `POST /api/v1/profile/facts`

```json
// request
{
  "scope": "safety",
  "key": "cervical_spine_no_impact",
  "value": { "label": "Ei iskutreenejä", "blocked_actions": ["..."] },
  "source_product": "continuity",     // must match a known product name
  "provenance": "user_stated",
  "confidence": "high",
  "expires_at": null
}
// 201 response: full Fact row (incl. id, timestamps)
// 200 if upsert (same user+scope+key already exists)
// 400 if scope or provenance/confidence enum invalid
// 401 if no canonical JWT
// 403 if source_product doesn't match the requesting product (anti-spoofing — Veyra cannot post a fact tagged source_product=continuity)
```

### `GET /api/v1/profile/facts`

```
GET /api/v1/profile/facts?scope=safety,nutrition&min_confidence=medium
→ 200 { "facts": [ ...Fact... ], "as_of": "2026-05-15T..." }
```

Query parameters:
- `scope` (comma-separated, optional) — defaults to all scopes
- `min_confidence` (optional) — `high` | `medium` | `low`, defaults to `low` (all)
- `include_expired` (optional, default false) — facts with `expires_at < now()` are filtered out by default

### `DELETE /api/v1/profile/facts/{fact_id}`

User-initiated single-fact delete. 204 on success; 404 if not the requesting user's fact (privacy: don't reveal cross-user fact_ids exist).

### `DELETE /api/v1/profile/facts?source_product={name}`

Bulk-delete all the requesting user's facts written by a specific product. Used when the user revokes that product's access via brandista-api admin UI. Returns `{ "deleted": <count> }`.

## 6. Anti-spoofing: source_product is server-derived

Each product's canonical-JWT-issuing flow tags the token with a product claim (added in Phase 4.1 step 2 — `role` claim today, extended in step 3.5 — note that's a separate item). For 4.2 we need a `product` claim or an out-of-band map from JWT issuer ID → product name.

**Decision for 4.2:** add a `product` string claim to the canonical JWT, populated at issuance time based on the issuing endpoint:
- `POST /api/auth/v2/google/native` from Veyran proxy → product=`veyra`
- `POST /api/auth/v2/apple/native` from Continuity → product=`continuity`
- `POST /api/auth/v2/magic-link/verify` from brandista.eu web → product=`growth_engine`

**How brandista-api knows which product is calling:** the calling product passes an `X-Brandista-Product: veyra` header on each auth-flow request. The endpoint validates it against an allowlist and bakes it into the JWT. Without the header the token gets `product=unknown` and facts endpoint rejects `source_product` writes (only read allowed).

This is a small Phase 4.1 step 2 retrofit (one new claim + one allowlist) but it's required *for* Phase 4.2. Spec'd here, executed before facts API ships.

## 7. GDPR & sensitivity boundary

The facts table **must not** become a back-door for Article 9 health data. Hard rules enforced in the POST handler:

1. **`value` is shallow-scanned for dose-like patterns** (`mg`, `mcg`, `µg`, `IU` adjacent to a number; drug-name list-of-known-prescribed terms). Match → 400 with `dose_data_not_allowed`. Same defense as Continuity's `FOUNDATION_STATUS.md` invariant #3.
2. **No raw diagnoses** — keys like `diabetes`, `cancer`, `depression` are blocked. Use derived labels instead (`carbohydrate_restriction`, `chronic_fatigue_pacing`). Maintains a reviewed enum of accepted safety keys; unknown keys go to scope=`general` with a manual review flag.
3. **`source_product=continuity` may bypass the dose/diagnosis check** because Continuity itself enforces dose-redaction upstream. But Continuity is the only product allowed to write `safety` facts — `source_product=veyra` writing `safety` is refused (403). Veyra's coach can suggest nutrition / training facts but not declare medical safety constraints.

## 8. Veyran publisher

`apps/web/src/lib/coach/extract-facts.ts` (new file, ~80 LOC):
- After every coach reply, scan the conversation for `FACT_ADD` markers the coach emits (existing pattern from coach prompt).
- For each marker: classify into scope (`safety` | `nutrition` | `training` | `general`) by keyword heuristics + small LLM call if heuristic misses.
- POST to `${BRANDISTA_API_URL}/api/v1/profile/facts` with the canonical JWT the user signed in with. `source_product=veyra`.
- Failures logged but do not block the coach response — facts API is a best-effort write.

## 9. Continuityn reader

`apps/continuity-api/src/continuity_api/safety/engine.py:bound(...)` extends:
- Before calling `_redact_if_needed` and computing `blocked_actions`, fetch `GET /api/v1/profile/facts?scope=safety&min_confidence=high` from brandista-api with the user's JWT.
- For each fact, if `value.blocked_actions` array is present, merge into the `Finding.blocked_actions` field.
- Cache the fetch for 5 minutes (in-memory per worker) so a single bound() call doesn't double-hit brandista-api.

Foundation invariant #1 (no raw payload to narrator) is unaffected — facts are summary tags, not raw event data.

## 10. Validation scenarios

| Scenario | Pre-4.2 behavior | Post-4.2 behavior | How we measure |
|---|---|---|---|
| User adds `cervical_spine_no_impact` safety tag in Continuity | Veyra coach recommends burpees on next plan | Veyra coach removes all impact exercises automatically | SQL: `profile_facts` row exists; manual: open Veyra plan, no impact exercises |
| User tells Veyra coach "olen laktoosi-intolerantti" | Continuity nutrition-finding (if generated) ignores it | Continuity reads `nutrition.lactose_intolerant`, generates lactose-free nutrition narrative | SQL: fact row exists with `source_product=veyra`; manual: Continuity nutrition page shows oat-milk alternatives |
| User revokes Veyra | Facts written by Veyra linger in brandista-api forever | Single SQL `DELETE WHERE source_product=veyra AND user_id=X` | Admin endpoint returns `deleted: <n>`, GET returns 0 veyra-sourced facts |

## 11. Open questions

1. **Product claim retrofit:** do we ship the `product` JWT claim as part of the 4.2 PR or as a tiny standalone step 2.5 PR first? Inclined to standalone — security review surface is smaller.
2. **Confidence-based blocking in Continuity SBE:** is min_confidence=`high` the right default, or should we accept `medium` too? `high` is safer (less false-positive safety constraints) but misses Veyra coach inferences that were correct-but-cautious. Suggest `high` default + per-fact-key override list.
3. **Naming convention for `key`:** lowercase_snake_case is what the worked examples use, but should we enforce it at API level? Cheap to do (regex on POST), prevents drift.
4. **Editing UX:** users will eventually want a "manage my facts" page in some product. Out of scope for 4.2 but worth deciding which product owns it — probably brandista.eu/profile.

## 12. Sequence to ship

1. Standalone PR: add `product` JWT claim + `X-Brandista-Product` header allowlist on `/api/auth/v2/*`. ~150 LOC + tests.
2. Migration 0006 (`profile_facts` table) + `app/db/models.py` ProfileFact + Pydantic schemas.
3. `app/routers/facts.py` with POST / GET / DELETE handlers, mounted at `/api/v1/profile/facts`. ~250 LOC.
4. Dose/diagnosis defensive scan helper.
5. Tests: schema, scope filter, auth, cross-product anti-spoof, GDPR rejection. ~300 LOC.
6. Veyran `extract-facts.ts` + integration in coach pipeline. ~80 LOC.
7. Continuityn `bound()` extension + cache + tests. ~50 LOC.
8. Cross-product validation SQL once a fact has flowed both directions.

Estimated effort at Phase 4.1 pace: **3–5 working days end-to-end**, mostly testing + the Veyra/Continuity integrations.
