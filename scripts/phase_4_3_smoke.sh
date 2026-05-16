#!/usr/bin/env bash
#
# Phase 4.3 production smoke. Run from any local shell with:
#
#   export BRANDISTA_INTERNAL_SECRET="<value-from-railway>"
#   export TEST_USER_EMAIL="<dogfood-account-email>"
#   ./scripts/phase_4_3_smoke.sh
#
# Optional:
#   export BRANDISTA_API_BASE="https://api.brandista.eu"   # default
#
# Exits 0 on full success, non-zero on first failure. Designed to be
# rerun safely — the moderate-recovery_pressure event uses an
# idempotency key tied to the day so back-to-back runs collapse.
#
# Full runbook: docs/superpowers/specs/2026-05-16-phase-4-3-step-11-rollout-runbook.md

set -euo pipefail

BASE="${BRANDISTA_API_BASE:-https://api.brandista.eu}"
SECRET="${BRANDISTA_INTERNAL_SECRET:?BRANDISTA_INTERNAL_SECRET must be exported}"
EMAIL="${TEST_USER_EMAIL:?TEST_USER_EMAIL must be exported}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

# Use `python3 -c` for JSON parsing so we don't depend on jq being installed.
get_json_field() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1',''))"
}

# ----------------------------------------------------------------------------
# 1. Endpoint reachability — known unauth refusals.
# ----------------------------------------------------------------------------

bold "1. Endpoint reachability"

for path in "/api/v1/events?subscriber_id=continuity-sbe-pipeline" \
            "/api/v1/internal/events" \
            "/api/v1/events/ack"; do
  method=$([[ "$path" == *"?"* ]] && echo GET || echo POST)
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
    -X "$method" -H 'Content-Type: application/json' -d '{}' \
    "$BASE$path")
  if [[ "$code" == "401" ]]; then
    ok "$method $path → 401 (unauth refused as expected)"
  else
    fail "$method $path → $code (expected 401)"
  fi
done

# ----------------------------------------------------------------------------
# 2. Internal POST smoke — moderate health.recovery_pressure.
# ----------------------------------------------------------------------------

bold "2. Internal POST smoke (continuity → bus)"

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)
IDEM_KEY="smoke:rollout:${EMAIL}:${TODAY}"

PAYLOAD=$(cat <<JSON
{
  "event_type": "health.recovery_pressure",
  "event_version": 1,
  "source_product": "continuity",
  "occurred_at": "$NOW",
  "idempotency_key": "$IDEM_KEY",
  "email": "$EMAIL",
  "payload": {
    "observed_at": "$NOW",
    "severity": "moderate",
    "severity_rank": 2,
    "hrv_drop_pct": -18.0,
    "contributing_signals": ["hrv_below_baseline"]
  }
}
JSON
)

RESPONSE=$(curl -sS -X POST "$BASE/api/v1/internal/events" \
  -H "X-Brandista-Internal-Auth: $SECRET" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

EVENT_SEQ=$(echo "$RESPONSE" | get_json_field event_seq)
RESOLVED=$(echo "$RESPONSE" | get_json_field resolved_user_id)
IDEMPOTENT=$(echo "$RESPONSE" | get_json_field idempotent)

if [[ -n "$EVENT_SEQ" && -n "$RESOLVED" ]]; then
  ok "POST /api/v1/internal/events → event_seq=$EVENT_SEQ resolved_user_id=${RESOLVED:0:8}... idempotent=$IDEMPOTENT"
else
  echo "  response: $RESPONSE"
  fail "POST /api/v1/internal/events did not return event_seq + resolved_user_id"
fi

# ----------------------------------------------------------------------------
# 3. Re-POST → idempotent dedup, same event_seq.
# ----------------------------------------------------------------------------

bold "3. Idempotency dedup (same body, second POST)"

RESPONSE2=$(curl -sS -X POST "$BASE/api/v1/internal/events" \
  -H "X-Brandista-Internal-Auth: $SECRET" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

SEQ2=$(echo "$RESPONSE2" | get_json_field event_seq)
IDEM2=$(echo "$RESPONSE2" | get_json_field idempotent)

if [[ "$SEQ2" == "$EVENT_SEQ" && "$IDEM2" == "True" ]]; then
  ok "Re-POST → idempotent=True, same event_seq=$SEQ2"
else
  echo "  response: $RESPONSE2"
  fail "Re-POST not idempotent (expected event_seq=$EVENT_SEQ, idempotent=True; got $SEQ2 / $IDEM2)"
fi

# ----------------------------------------------------------------------------
# 4. Subscriber GET — veyra-coach-builder should see the published event.
# ----------------------------------------------------------------------------

bold "4. Subscriber GET smoke (veyra-coach-builder)"

LIST=$(curl -sS -G "$BASE/api/v1/events" \
  -H "X-Brandista-Internal-Auth: $SECRET" \
  --data-urlencode "subscriber_id=veyra-coach-builder" \
  --data-urlencode "email=$EMAIL")

COUNT=$(echo "$LIST" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('events',[])))")
MATCH=$(echo "$LIST" | python3 -c "
import json,sys
events = json.load(sys.stdin).get('events',[])
seq=$EVENT_SEQ
print('yes' if any(e.get('event_seq')==seq for e in events) else 'no')
")

if [[ "$MATCH" == "yes" ]]; then
  ok "GET returned $COUNT events; smoke event_seq=$EVENT_SEQ is in the list"
else
  echo "  response: $LIST"
  fail "GET returned $COUNT events but smoke event_seq=$EVENT_SEQ not found"
fi

# ----------------------------------------------------------------------------
# 5. Anti-spoof — same call but with an internal-secret that's wrong.
# ----------------------------------------------------------------------------

bold "5. Anti-spoof (wrong secret refused)"

CODE=$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST "$BASE/api/v1/internal/events" \
  -H "X-Brandista-Internal-Auth: WRONG-SECRET-VALUE" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [[ "$CODE" == "401" || "$CODE" == "403" ]]; then
  ok "Wrong secret → $CODE (refused)"
else
  fail "Wrong secret → $CODE (expected 401 or 403)"
fi

# ----------------------------------------------------------------------------
# Summary.
# ----------------------------------------------------------------------------

echo
bold "Phase 4.3 smoke: all green"
echo "  - 3 unauth endpoints refused with 401 ✓"
echo "  - internal POST published event_seq=$EVENT_SEQ ✓"
echo "  - dedup returned idempotent=True ✓"
echo "  - subscriber GET surfaced the event ✓"
echo "  - wrong secret refused ✓"
echo
echo "Next: tail Railway logs for 'events: internal-published' line"
echo "      and query event_audit for the (user_id, occurred_at) tuple."
