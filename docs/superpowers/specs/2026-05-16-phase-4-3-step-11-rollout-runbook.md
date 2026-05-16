# Phase 4.3 — Step 11 Production Rollout Runbook

**Date:** 2026-05-16
**Status:** Production rollout in progress
**Spec:** [`2026-05-16-phase-4-3-event-bus-design-v0-2.md`](./2026-05-16-phase-4-3-event-bus-design-v0-2.md)

This is the runbook for taking the cross-product event bus live across **brandista-api**, **continuity-api**, and **treeniohjelma**. Steps 1–10 (code) merged 2026-05-16. This document covers (a) env-var prerequisites, (b) deploy-order constraints, (c) smoke-test protocol, and (d) Karoliinan-case end-to-end validation.

## 1. Merge timeline (for the record)

| PR | Repo | Branch | Merge commit |
|---|---|---|---|
| [#14](https://github.com/brandista/brandista-api/pull/14) | brandista-api | `feature/phase-4-3-event-bus` | `e660cf4` |
| [#15](https://github.com/brandista/brandista-api/pull/15) | brandista-api | `feat/event-bus-followups` | `9f36521` |
| [#4](https://github.com/brandista/treeniohjelma/pull/4) | treeniohjelma | `feat/event-bus-publisher` | (auto-deployed) |
| [#2](https://github.com/brandista/continuity-os-health/pull/2) | continuity-os-health | `feat/event-bus-publisher` | `aed72bf` |

All four landed within the same day. Railway auto-deployed all three services from `main` after each merge.

## 2. Env-var prerequisites

The bus relies on **one shared HMAC secret** across three services. It MUST be byte-identical on all three or signature verification on GET responses (and internal-auth on POST endpoints) fails silently.

| Service | Env var | Required | Source of truth |
|---|---|---|---|
| brandista-api | `BRANDISTA_INTERNAL_SECRET` | yes | This is the canonical value (already set from Phase 4.2). |
| brandista-api | `SECRET_KEY` | yes (already set) | Phase 4.1 — canonical JWT signing. |
| continuity-api | `BRANDISTA_INTERNAL_SECRET` | yes | Same byte-value as brandista-api. (Already set from Phase 4.2 step 4 facts client.) |
| continuity-api | `BRANDISTA_API_URL` | optional | Defaults to `https://api.brandista.eu`. |
| continuity-api | `BRANDISTA_CORE_SECRET_KEY` | yes (already set) | Phase 4.1 — verifies inbound canonical JWTs. |
| treeniohjelma | `BRANDISTA_INTERNAL_SECRET` | **yes — NEW for step 8 subscriber** | Same value as the other two. Without this, Veyran coach silently skips recovery-pressure reads (degrades to local-only). |
| treeniohjelma | `BRANDISTA_API_URL` | yes (already set) | Phase 4.2 — facts publisher. |

The optional `BRANDISTA_EVENT_SIGNING_SECRET` env exists for a future per-region/per-subscriber key split (spec §7); leave unset in v1 — falls back to `BRANDISTA_INTERNAL_SECRET`.

## 3. Deploy-order constraints

Migrations and route mounts have one ordering dependency: **brandista-api 0007 migration must apply before any other service POSTs an event**. The Railway boot sequence handles this automatically because `start.py` runs `alembic upgrade head` before Uvicorn (Phase 4.1 step 3.5 hardening). No manual coordination needed.

Beyond that, the services are independent:

- Continuityn pipeline POSTs to `/api/v1/internal/events` and reads `/api/v1/events?email=…`. Both require brandista-api 0007 + the new endpoints to be deployed.
- Veyran publisher POSTs to `/api/v1/events` with canonical JWT. Same dependency.
- Veyran subscriber reads `/api/v1/events?subscriber_id=veyra-coach-builder&user_id=…`. Requires brandista-api endpoints + the `BRANDISTA_INTERNAL_SECRET` on the Veyran deploy.

If any service deploys before brandista-api has finished its migration, the dependent calls 404 / 503 and the service silently degrades (Phase 4.3's documented honest-failure contract). No data corruption risk.

## 4. Endpoint smoke (read-only)

The fastest "is it deployed" check. No secret needed — these all expect to refuse and return a known error code.

```bash
for path in "/api/v1/events?subscriber_id=continuity-sbe-pipeline" \
            "/api/v1/internal/events" \
            "/api/v1/events/ack"; do
  echo "$path → $(curl -sS -o /dev/null -w '%{http_code}' \
    -X $([[ $path == */events?* ]] && echo GET || echo POST) \
    -H 'Content-Type: application/json' \
    -d '{}' \
    https://api.brandista.eu$path)"
done
```

Expected output:

```
/api/v1/events?…       → 401   (missing internal auth)
/api/v1/internal/events → 401  (missing internal auth)
/api/v1/events/ack     → 401   (missing internal auth)
```

If any returns `404`, brandista-api has not yet re-deployed with the merged code — wait for Railway and retry.

## 5. Authenticated smoke (internal POST roundtrip)

Validates: the internal endpoint accepts a valid secret, resolves the user by email, registers the event with `event_seq`, and the audit row lands.

**Prereq:** export `BRANDISTA_INTERNAL_SECRET` locally (matches Railway value). Use a real test user's email — production users get a real bus event, so pick a dogfood account (e.g. `tuukka@brandista.eu`).

```bash
# Run smoke from any local shell with the secret exported.
export BRANDISTA_INTERNAL_SECRET="<paste-value-here>"
export TEST_USER_EMAIL="tuukka@brandista.eu"

# Smoke 1 — moderate recovery_pressure (severity_rank=2; valid wire shape).
curl -sS -X POST https://api.brandista.eu/api/v1/internal/events \
  -H "X-Brandista-Internal-Auth: $BRANDISTA_INTERNAL_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "health.recovery_pressure",
    "event_version": 1,
    "source_product": "continuity",
    "occurred_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
    "idempotency_key": "smoke:rollout-'"$(date +%s)"'",
    "email": "'"$TEST_USER_EMAIL"'",
    "payload": {
      "observed_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
      "severity": "moderate",
      "severity_rank": 2,
      "hrv_drop_pct": -18.0,
      "contributing_signals": ["hrv_below_baseline"]
    }
  }' | python3 -m json.tool
```

Expected: `201 Created`, body has `event_id`, `event_seq` (integer ≥ 1), `envelope_sig_hex` (64-char hex), `resolved_user_id` (UUID), `idempotent: false`.

```bash
# Smoke 2 — re-POST the same body → idempotent dedup, 200, idempotent: true.
# (Re-run the same curl above; brandista-api dedups on the
# (source_product, event_type, user_id, idempotency_key) tuple.)
```

Verify in Railway logs:

```
events: internal-published (event_id=…, seq=N, type=health.recovery_pressure, source=continuity, user=<uuid>)
events: internal idempotent dedup (event_id=…, seq=N, type=health.recovery_pressure, user=<uuid>)
```

## 6. Subscriber-side smoke (GET pull)

Validates: the GET path returns the event you just published when authed with the same secret.

```bash
curl -sS "https://api.brandista.eu/api/v1/events?subscriber_id=veyra-coach-builder&email=$TEST_USER_EMAIL" \
  -H "X-Brandista-Internal-Auth: $BRANDISTA_INTERNAL_SECRET" | python3 -m json.tool
```

Expected: `200 OK`, body `{ events: [...], has_more: false }`. At least one event should have `event_type=health.recovery_pressure` if the smoke 1 event is recent.

## 7. Karoliinan-case end-to-end validation

The full §11 R1 scenario. Requires Continuityn pipeline to have HRV data on the test user that crosses the `recovery_weakening` significant cutoff (≥ 25% drop from baseline), and a recent Veyran coach interaction.

**Path A — Live cron** (preferred):

1. Wait for the next nightly Continuityn pipeline (`apscheduler` in `jobs/scheduler.py`). It runs at midnight in the user's timezone.
2. Tail `continuity.brandista.eu` Railway log; expect a line like
   `brandista_events: publish ok event_seq=N` (or the failure-mode log if the user doesn't qualify).
3. Open Veyran coach in training mode with the same user the next morning. Send any message that triggers a plan re-render.
4. Coach response should include a kevyt/lepo-leaning plan with a brief HRV-flavoured one-liner (the prompt instructs: "HRV oli yöllä alle perustason, joten tehdään palauttava päivä").

**Path B — Forced** (faster):

If you have access to inject HRV data directly via the Continuityn manual-entry endpoint (or a SQL helper), drop `hrv_rmssd` values for the test user that are 27%+ below their 30-day median. Then trigger the pipeline:

```bash
# Pipeline can be poked via the existing sync endpoint or a one-off
# `safe_run_pipeline(user_id)` call in a Railway shell.
```

## 8. Audit verification

After any smoke event, the `event_audit` table should have at least one row tying the event to a producer:

```sql
SELECT id, event_seq_at_audit, event_type, source_product, actor_kind, action, occurred_at
FROM event_audit
WHERE user_id = (SELECT id FROM users WHERE email = 'tuukka@brandista.eu')
ORDER BY occurred_at DESC
LIMIT 5;
```

Expected: rows with `actor_kind='producer'`, `action='published'`, plus optionally `actor_meta` containing `{"channel": "internal"}` for events that came through the internal POST.

## 9. Rollback plan

If the smoke uncovers a regression that blocks production:

1. **Revert the merge commit** on the affected repo. `git revert -m 1 <merge-sha>` then push to main → Railway redeploys with the prior state.
2. **Migration rollback:** `alembic downgrade -1` from a Railway shell. This drops `events`, `event_subscribers`, `event_subscriber_checkpoints`, `event_handler_attempts`, `event_audit`. No data loss for OTHER tables.
3. **Veyran/Continuityn-side rollback** is implicit — if the brandista-api endpoint disappears, both products silently degrade to local-only (honest-failure contract).

Rollback decision criteria: revert if a P0 bug surfaces (data corruption, user data leak, secret leak). Don't revert for P1+ that has a forward-fix path within ≤2 hours.

## 10. Sprint loppuraportti hook

The audit trail is now sufficient to reconstruct cross-product timelines for the Sprint application §02 hypothesis. Example query — "show all cross-product events for Karoliina on 2026-05-17":

```sql
SELECT
  ea.event_seq_at_audit,
  ea.event_type,
  ea.source_product,
  ea.actor_kind,
  ea.action,
  ea.payload_summary,
  ea.occurred_at
FROM event_audit ea
JOIN users u ON u.id = ea.user_id
WHERE u.email = 'karoliina@example.com'
  AND ea.occurred_at::date = '2026-05-17'
ORDER BY ea.event_seq_at_audit;
```

This is the data Sprint reviewers will see: "Continuity published `health.recovery_pressure severity=significant` at 06:14; Veyra-coach-builder consumed it at 08:32 when Karoliina opened the app; the coach plan softened from raskas to kevyt (audit `coach_plan.softened_due_to=event_id`)."

## 11. Done conditions

Step 11 (and Phase 4.3 as a whole) is complete when:

- [x] All four PRs merged.
- [x] Railway shows successful deploy of all three services from the merged commits.
- [x] §4 endpoint smoke green (401s + 403s in the right places).
- [ ] §5 internal POST smoke returns `201` + `event_seq`.
- [ ] §6 subscriber GET smoke returns the published event.
- [ ] §7 Karoliinan-case end-to-end observed at least once on a real user.
- [ ] §8 audit query confirms the producer + subscriber rows landed.

Steps 5–8 require a live test user; check them off as you go.

## 12. Known follow-ups (deferred, not blocking)

- **ack-stale-events cleanup cron** — request-bound subscribers (Veyran coach, Continuityn pipeline) don't ack their cursors in v1. A future cron should advance past events older than the audit-retention window so the cursor stays bounded.
- **Per-subscriber signing keys** — v1 shares `BRANDISTA_INTERNAL_SECRET` across all signers; spec §15 documents the v2 separation path.
- **medication.taken end-to-end** — schema exists, no subscriber registered, no publisher emits. v2 work.
- **Replay CLI** — `python -m app.events.replay` was deferred from step 4. Re-prioritize when the first audit-reconstruction request comes from Sprint reviewers.
