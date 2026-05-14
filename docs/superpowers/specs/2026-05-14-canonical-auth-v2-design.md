# Canonical Auth v2 — Design

**Date:** 2026-05-14
**Phase:** 4.1, Step 2 (Identity unification — token issuance + canonical dependency)
**Prerequisite:** Migration `0002_canonical_id` (already shipped in PR feat/canonical-platform-identity, commit 6907cf6)

## 1. Context and goal

Migration 0002 introduced the canonical identity tables (`organizations`, `users` with UUID `id`, `credits`, `entitlements`) and backfilled them from legacy `users.username`. The schema is in place but no API endpoint issues or accepts canonical tokens yet.

This design defines the next step: issue and validate **canonical platform JWTs** alongside legacy tokens, so that:

1. New frontend flows can carry `user_id` + `org_id` end-to-end instead of opaque email-as-identity.
2. Continuity (continuity-api) — which already documents the canonical token shape it expects in `auth/brandista_core.py` — can begin consuming v2 tokens issued by brandista-api without further negotiation.
3. The current production path (Google native + 14d auto-trial that launched 2026-05-13) is **not disturbed**. Legacy endpoints and tokens keep working untouched until a later step deprecates them.

This is a B3-shaped change in the original framing: cutover-driven, internal first, no external consumer commitments locked in yet beyond what Continuity already documented.

## 2. Scope

### In scope (Step 3)

- `app/auth/` package — `CanonicalUser` Pydantic model, token issuance helper, token decode helper.
- `app/auth/dependencies.py` — new `get_current_canonical_user` FastAPI dependency, separate from legacy `get_current_user`.
- `app/routers/auth_v2.py` — new router mounted at `/api/auth/v2/*`.
- Five v2 endpoints (see §6).
- Auto-provisioning logic for new emails (see §7).
- Tests for round-trip, malformed/expired/legacy-shaped tokens, auto-provisioning, and legacy coexistence.

### Out of scope (deferred)

- **Apple Sign In** → Step 3.5 (own spec; needs `users.apple_id` migration, Apple Developer Service ID config, JWKS verification, private relay email handling).
- **Refresh tokens** → Step 4+ when concrete consumer requirement exists. Adds substantial cost (~500 LOC + frontend choreography + new storage) for security benefit that has no concrete trigger today.
- **RS256 / JWKS migration** → Step 4+ when external consumers beyond Continuity appear.
- **`entitlements` claim in token** → Step 4+ when caching becomes a measured need (today's flow does DB lookup per request and is fine).
- **Real token revocation (blocklist)** → Step 4+. v2 tokens get a `jti` claim now so the blocklist can be added later without re-issuing tokens, but the blocklist itself is deferred.
- **Legacy `/auth/*` endpoint deprecation** → Step 5+ after frontend cutover is complete.
- **Admin `/auth/login` (password) v2 port** → Not prioritized; admin UI is not on the canonical-cutover path.
- **Frontend cutover code** → Lives in `brandista-frontend 2 agentit` and Continuity iOS app. Tracked as separate plan, not in this repo.

## 3. Architecture

### File layout

```
app/
├── auth/                          (NEW package)
│   ├── __init__.py
│   ├── canonical.py               CanonicalUser model + create_canonical_token + decode_canonical_token + provision_canonical_user
│   └── dependencies.py            get_current_canonical_user FastAPI dep
├── routers/
│   └── auth_v2.py                 (NEW) /api/auth/v2/* endpoints
└── db/                            (already exists from migration 0002)
    ├── base.py
    ├── models.py                  Organization, User, Credits, Entitlement
    └── session.py                 async session factory
```

### Wiring into the production app

`main.py` (the production entrypoint per project CLAUDE.md) imports and mounts the router:

```python
from app.routers.auth_v2 import router as auth_v2_router
app.include_router(auth_v2_router, prefix="/api/auth/v2", tags=["auth-v2"])
```

This is the same pattern already used for `app/routers/chat.py` and `app/routers/books.py`. No change to legacy auth functions in `main.py` itself.

### Shared infrastructure

- `SECRET_KEY` and `ALGORITHM` continue to come from `agents/config.py` — single source.
- `ACCESS_TOKEN_EXPIRE_MINUTES` (currently 1440 min = 24h) reused for canonical tokens.
- Async DB access uses the existing `app/db/session.py` factory.

## 4. Token format

```json
{
  "sub":    "<user-uuid>",
  "email":  "user@example.com",
  "org_id": "<org-uuid>",
  "role":   "user",
  "jti":    "<random-uuid>",
  "iat":    <unix-ts>,
  "exp":    <unix-ts>
}
```

- **Algorithm:** HS256 (same as legacy; matches Continuity's current verification path).
- **`sub`:** canonical `users.id` as UUID string. Never email, never username.
- **`email`:** the user's canonical email (lowercase, trimmed). Continuity's `_extract_email` reads this preferentially.
- **`org_id`:** the user's `users.org_id` as UUID string. Forward-looking; not consumed by Continuity today but locked into the contract for later use.
- **`role`:** read from the legacy `users.role` column for now. Step 4+ may migrate this into the `entitlements` table.
- **`jti`:** random UUID. Reserved for future blocklist-based revocation (Step 4+); not enforced today, but every v2 token has one so that the blocklist can be wired in later without re-issuing tokens.
- **`iat` / `exp`:** standard. Expiry equals issuance + 24h, identical to legacy.

This matches the shape documented in Continuity's `apps/continuity-api/src/continuity_api/auth/brandista_core.py`. Continuity already accepts both this format and the legacy `{sub=email, role, exp, iat}` format.

## 5. Token issuance flow

Every v2 issuance endpoint follows this pattern:

```
1. Authenticate the request (Google id_token verify / magic-link verify / etc.)
   → produces a verified email address
2. Async DB lookup against canonical users table:
     SELECT id, org_id, role FROM users WHERE LOWER(email) = LOWER(?)
   → if found: use those values
   → if not found: AUTO-PROVISION (see §7)
3. create_canonical_token(user_id, org_id, email, role) → JWT string
4. Return { access_token, token_type: "bearer", user: CanonicalUser{...} }
```

`create_canonical_token` lives in `app/auth/canonical.py`. It does only the JWT encoding — it does not touch the database. Database lookup and provisioning are responsibilities of the endpoint code (or a shared helper that the endpoints call).

## 6. Endpoints

All under prefix `/api/auth/v2`.

### POST /google/native

**Ports** `main.py:7209` (`/auth/google/native`).

- **Request:** `{ "credential": "<google-id-token>" }`
- **Behavior:**
  1. Verify Google id_token against the configured Google client IDs (same verification logic as legacy — including iOS client-id audience already accepted by legacy per commit `72e8875`).
  2. Extract email from verified id_token claims.
  3. Lookup or auto-provision canonical user.
  4. Issue v2 token.
- **Response:** `{ "access_token": "...", "token_type": "bearer", "user": { user_id, org_id, email, role } }`
- **Errors:** 400 on missing credential, 401 on invalid Google token, 500 on DB issue.

### POST /magic-link/request

**Ports** `main.py:6845` (`/auth/magic-link/request`).

- **Request:** `{ "email": "user@example.com" }`
- **Behavior:** Reuses the existing magic-link generation and email-sending logic from `auth_magic_link.py` / `main.py`. The short-lived "magic link" token in the email is the same shape as today (single-use, ~15min expiry, signed with `SECRET_KEY`). The link points at the v2 verify endpoint.
- **Response:** `{ "status": "sent" }` (200) — the same minimal response as legacy; never confirm or deny the email exists.

### POST /magic-link/verify

**Ports** `main.py:6874` (`GET /auth/magic-link/verify`). Note on HTTP verb: the magic-link email points at the frontend URL `{frontend_url}/auth/magic-link/verify?token=...` (see `auth_magic_link.py:175`). The frontend extracts the token from the URL and calls the API. v2 keeps this pattern but the API call is `POST` with a JSON body — appropriate for the server-to-server XHR the frontend makes, and slightly safer than a GET (no token in API access logs as URL parameter).

- **Request:** `{ "token": "<magic-link-token>" }`
- **Behavior:**
  1. Verify magic-link token (same logic as legacy).
  2. Extract email from verified token.
  3. Lookup or auto-provision canonical user.
  4. Issue v2 access token.
- **Response:** identical to `/google/native`.

### GET /me

**New.** No legacy equivalent — frontends typically read the email out of the decoded JWT today.

- **Request:** `Authorization: Bearer <v2-token>`
- **Dependency:** `Depends(get_current_canonical_user)`
- **Behavior:** Returns the `CanonicalUser` derived from the validated token. Does not re-query the DB — the token's claims are the source of truth for this endpoint.
- **Response:** `{ user_id, org_id, email, role }`
- **Errors:** 401 on any token validation failure.

### POST /logout

**New.** No legacy equivalent.

- **Request:** `Authorization: Bearer <v2-token>` (optional — endpoint also accepts unauthenticated calls and returns 204)
- **Behavior:** No-op server-side. Returns 204. Frontend is responsible for deleting the token from local storage.
- **Forward compatibility:** When Step 4 adds the Redis blocklist, this endpoint becomes the place that extracts `jti` from the request token and adds it to the blocklist with TTL = remaining exp. The endpoint URL does not need to change.
- **Response:** 204 No Content.

### Endpoints NOT in v2

- `/auth/login` (password) — admin flow, not on cutover path.
- `/auth/refresh` — refresh tokens deferred to Step 4+.
- Stripe webhook endpoints — not user-auth.

## 7. Auto-provisioning

When step 5.2 ("DB lookup against canonical users") returns nothing for a verified email, the endpoint provisions a canonical user inline using a shared helper.

### `provision_canonical_user(email: str, source: str) -> User`

Lives in `app/auth/canonical.py`. Replicates the logic of migration 0002's backfill:

```python
async def provision_canonical_user(email: str, source: str) -> User:
    """Create canonical user + org + credits + growth_engine entitlement
    for a verified email. Single transaction.

    source: 'google' | 'magic_link' — used only in the log line emitted
            on successful provisioning. Not stored on any row today; the
            parameter exists so audit logs can attribute new orgs to
            their originating flow.
    """
    async with async_session() as session:
        async with session.begin():
            # 1. Create organization (named after the email, same as 0002 backfill)
            org = Organization(name=email)
            session.add(org)
            await session.flush()  # populate org.id

            # 2. Create user
            user = User(
                email=email.lower().strip(),
                org_id=org.id,
                is_active=True,
                role="user",
            )
            session.add(user)
            await session.flush()

            # 3. Seed credits row
            credits = Credits(org_id=org.id, balance=0, plan_monthly_limit=0)
            session.add(credits)

            # 4. Seed growth_engine entitlement
            ent = Entitlement(org_id=org.id, module="growth_engine")
            session.add(ent)

            await session.commit()
            await session.refresh(user)
            return user
```

### Race condition handling

If two concurrent requests provision the same new email, `users.email UNIQUE` causes the second insert to raise `IntegrityError`. The endpoint catches this and re-queries — the first request wins, the second gets the user that already exists. Net result: idempotent.

### Why auto-provision instead of refusing

- Matches the legacy Google native flow (which auto-creates a `user_store` row).
- Matches Continuity's own pattern (`_resolve_local_user_id` auto-creates a local UUID for a brandista email).
- Required for the production funnel: Free Scan → email captured → magic link → analyze, where the user has never logged in before.
- Same threat model as legacy: someone can spam Google tokens / magic-link requests, but legacy has run this exact pattern for months without abuse.

## 8. `get_current_canonical_user` dependency

```python
# app/auth/dependencies.py

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID
from app.auth.canonical import decode_canonical_token, CanonicalUser

security = HTTPBearer()

async def get_current_canonical_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CanonicalUser:
    """Validate a canonical v2 JWT and return the user.

    Rejects:
      - Legacy-shaped tokens (sub is email, no org_id, no jti).
      - Tokens where sub or org_id is not a valid UUID.
      - Expired or malformed tokens.
    """
    try:
        return decode_canonical_token(credentials.credentials)
    except CanonicalTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
```

`decode_canonical_token` and `CanonicalTokenError` both live in `app/auth/canonical.py`. `decode_canonical_token` validates the JWT signature, expiry, and the canonical claim shape (UUID sub, UUID org_id, email present, role present). It does **not** query the DB — the token is self-contained. Any failure (bad signature, expired, malformed UUID, missing claim) raises `CanonicalTokenError` with a message that does not leak token contents.

Legacy `get_current_user` in `main.py:2334` and `app/dependencies.py:29` are not touched. They continue to decode legacy tokens against the same `SECRET_KEY`. The two dependencies are independent; endpoints opt in to whichever shape they want.

## 9. Legacy coexistence

| Component | Legacy | v2 | Status after Step 3 |
|---|---|---|---|
| Token shape | `{sub=email, role, exp, iat}` | `{sub=uuid, email, org_id, role, jti, exp, iat}` | Both shapes live in production |
| `get_current_user` (main.py:2334) | Decodes legacy | — | Untouched |
| `get_current_user` (app/dependencies.py:29) | Decodes legacy | — | Untouched |
| `get_current_canonical_user` | — | Decodes v2 only | New |
| `/auth/*` endpoints | Issue legacy | — | Untouched |
| `/api/auth/v2/*` endpoints | — | Issue v2 | New |
| Continuity's `BrandistaCoreIdentityProvider` | Accepts both | Accepts both | No change needed |

Frontends pick which endpoint to call. There is no compatibility shim that converts between formats — they are parallel issuance paths sharing the same `SECRET_KEY`.

## 10. Testing

New file: `tests/unit/test_auth_v2.py`.

| Test | Purpose |
|---|---|
| `test_canonical_token_roundtrip` | Issue token → decode → assert all claims match input. |
| `test_canonical_dependency_rejects_legacy_token` | `get_current_canonical_user` returns 401 for `{sub=email}`-shaped token. |
| `test_legacy_dependency_still_works` | `main.py:get_current_user` decodes a legacy token unchanged. |
| `test_canonical_dependency_rejects_non_uuid_sub` | Token with `sub="bob@example.com"` → 401. |
| `test_canonical_dependency_rejects_non_uuid_org_id` | Token with `org_id="not-a-uuid"` → 401. |
| `test_canonical_dependency_rejects_expired` | `exp < now` → 401. |
| `test_canonical_dependency_rejects_missing_claim` | Missing `email` / `org_id` / `jti` → 401. |
| `test_provision_creates_full_set` | New email through `provision_canonical_user` → asserts user + org + credits + entitlement all created in one transaction. |
| `test_provision_idempotent_under_race` | Two concurrent calls for same email → only one user/org created, second call returns existing. |
| `test_logout_no_op_returns_204` | `/api/auth/v2/logout` returns 204 with or without Authorization header. |
| `test_me_returns_canonical_user` | `GET /api/auth/v2/me` with valid token returns the user claims. |

Mock external IdPs (Google verify, magic-link send) at the test boundary. Tests use SQLite in-memory or a test Postgres instance — match whatever the existing test suite uses (check `tests/conftest.py` before implementing).

Integration smoke test (later, not blocking Step 3): a small test that imports Continuity's `_extract_email` directly and runs it against a v2 token. Catches contract drift without needing a Continuity instance running.

## 11. Cutover plan (outside this repo)

Documented here as a forward reference; actual code lives elsewhere.

- **brandista-frontend** can switch the Google login button to call `/api/auth/v2/google/native` once Step 3 ships. Token storage shape (`access_token` string) is identical, so most call sites need no change.
- **Continuity iOS** already accepts both shapes — no change needed. When brandista-api starts issuing v2 tokens, Continuity transparently uses the explicit `email` claim instead of falling back to `sub`.
- Magic link emails: the email template's link URL needs to point at `/api/auth/v2/magic-link/verify` instead of `/auth/magic-link/verify`. This is a small content change in `auth_magic_link.py` once v2 ships and frontend is ready.

## 12. Risks and open questions

- **Risk:** `app/db/` async session vs `database.py` psycopg2 pool — these are independent. We must NOT share connections between them. The migration's CHANGELOG already calls this out and the v2 auth path uses only `app/db/`.
- **Risk:** Auto-provisioning creates an organization per user, named after the email. This matches migration 0002 but is not a great long-term default — a real user can later be merged into an existing organization, or organizations could be derived from email domains. Out of scope for Step 3; flagged for Step 4+.
- **Open:** Should v2 endpoints log issuance to a separate audit log? The legacy `/auth/google/native` logs via `logger.info`. Same pattern is fine for v2 in Step 3; structured audit logging is Step 4+.
- **Open:** Rate limiting — `app/dependencies.py:check_rate_limit` already exists but is per-IP not per-user. Same as legacy. Not touched here.

## 13. Acceptance criteria

Step 3 is done when:

1. All five endpoints exist and respond per §6.
2. `get_current_canonical_user` is implemented and rejects legacy/malformed tokens.
3. Auto-provisioning creates user + org + credits + growth_engine entitlement in a single transaction, idempotent under race.
4. All tests in `tests/unit/test_auth_v2.py` pass.
5. Existing test suite (`python3 -m pytest tests/ -x -q`) still passes.
6. CHANGELOG.md has an entry describing the new endpoints and the auto-provisioning behavior.
7. The production Google native flow (`/auth/google/native`, legacy) is verified untouched — a smoke test against the legacy endpoint succeeds.
8. No production deploy until Step 3.5 (Apple) decisions are made — Step 3 can sit on a feature branch waiting for cutover coordination with frontend.
