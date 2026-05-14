# Canonical Identity — Production Deploy Runbook

> **Scope:** First-time rollout of alembic migrations to Railway production for `brandista-api`. After this, every subsequent schema change is a plain `alembic upgrade head` in the deploy command.
>
> **Why this runbook exists:** The `users` table predates migration control. Running `alembic upgrade head` directly would skip the 0001 baseline (which just records the legacy shape) and jump straight into 0002, but only if alembic_version is empty — which it is on first run. The risk is the reverse: if someone re-runs `alembic upgrade head` on a fresh DB without stamping, 0001 will try to `CREATE TABLE users` on top of the existing one. The stamp step prevents that.

---

## Pre-flight (do not skip)

- [ ] **Backup taken.** Railway → Postgres service → "Backups" tab → verify a recent automatic backup exists, or trigger a manual one. Note the backup ID.
- [ ] **Maintenance window announced** to anyone who relies on `api.brandista.eu`. Migration itself is fast (< 5 s on current row counts) but auth flows will briefly serve stale state if a session is mid-flight.
- [ ] **Confirm `pgcrypto` available.** Run on prod:
  ```sql
  SELECT * FROM pg_available_extensions WHERE name = 'pgcrypto';
  ```
  Expect one row. Railway Postgres supports it. The migration runs `CREATE EXTENSION IF NOT EXISTS pgcrypto` itself, so no manual `CREATE EXTENSION` is needed — this check just confirms it will succeed.
- [ ] **Confirm row count baseline.** Run on prod and note the numbers:
  ```sql
  SELECT count(*) AS users FROM users;
  SELECT count(*) FILTER (WHERE email IS NULL) AS users_without_email FROM users;
  SELECT count(*) FILTER (WHERE username !~ '@') AS users_username_no_at FROM users;
  ```
  The migration **refuses to proceed** if any user has no email AND a username that does not contain `@` (cannot be backfilled). Resolve those rows manually before continuing — either set `email`, or delete the row if it is a dead account.
- [ ] **DATABASE_URL points at production.** Triple-check. Easiest:
  ```bash
  railway run --service brandista-api -- python -c "import os; u=os.environ['DATABASE_URL']; print(u.split('@')[1].split('/')[0])"
  ```
  Expect the Railway Postgres host, not localhost, not a staging host.

---

## Step 1 — Stamp the baseline

This tells alembic "the current DB is already at revision `0001_baseline`" without running 0001's `op.create_table` statements. Required exactly once, on first migration rollout.

```bash
railway run --service brandista-api -- alembic stamp 0001_baseline
```

Verify:

```bash
railway run --service brandista-api -- alembic current
```

Expect `0001_baseline (head)` — actually no, after stamp alembic reports the stamped revision as current but `head` is 0002. Output will be something like `0001_baseline`. If it prints nothing, the stamp did not land — stop and investigate the alembic config before continuing.

---

## Step 2 — Upgrade to head (applies 0002)

```bash
railway run --service brandista-api -- alembic upgrade head
```

This wraps the entire 0002 migration in a single transaction. Either the whole thing lands or nothing does.

Expected log fragments (in order):
- `Running upgrade 0001_baseline -> 0002_canonical_id`
- (no errors)

Verify alembic state:

```bash
railway run --service brandista-api -- alembic current
```

Expect `0002_canonical_id (head)`.

---

## Step 3 — Data verification

Run all of these on prod and compare against the pre-flight baseline.

```sql
-- 1. Row count unchanged.
SELECT count(*) FROM users;
-- Should equal the pre-flight count exactly.

-- 2. Every user has an org.
SELECT count(*) AS users_without_org FROM users WHERE org_id IS NULL;
-- Should be 0.

-- 3. Every org has credits.
SELECT count(*) AS orgs_without_credits
  FROM organizations o
  LEFT JOIN credits c ON c.org_id = o.id
  WHERE c.org_id IS NULL;
-- Should be 0.

-- 4. Every org has a growth_engine entitlement.
SELECT count(*) AS orgs_without_growth_engine
  FROM organizations o
  LEFT JOIN entitlements e ON e.org_id = o.id AND e.module = 'growth_engine'
  WHERE e.org_id IS NULL;
-- Should be 0.

-- 5. UUIDs assigned to every row.
SELECT count(*) AS users_without_uuid FROM users WHERE id IS NULL;
-- Should be 0.

-- 6. Email backfilled where possible.
SELECT count(*) AS users_without_email FROM users WHERE email IS NULL;
-- Should be 0 (migration refuses to proceed otherwise).
```

If **any** of these fails, see "Rollback" below before doing anything else.

---

## Step 4 — Smoke test the app

The migration does not wire any new endpoint yet (that is the next phase). What we are verifying is that the legacy paths still work against the migrated schema.

- [ ] `GET https://api.brandista.eu/health` → 200.
- [ ] Magic-link login flow end-to-end with a known test account → succeeds, returns the existing JWT, `search_limit` / `searches_used` columns still readable.
- [ ] One Growth Engine analysis request against a known cheap target → completes, writes to `user_analysis_usage` as before.

If any of the above fails, rollback.

---

## Rollback

The migration is reversible end-to-end (validated locally with a full upgrade → downgrade → re-upgrade cycle).

```bash
railway run --service brandista-api -- alembic downgrade 0001_baseline
```

This:
- Drops `entitlements`, `credits`, `organizations` (in FK order).
- Removes the canonical columns from `users` (`id`, `org_id`, `google_id`, `full_name`, `is_active`, `last_login`).
- Restores `username` as `PRIMARY KEY` and `email` as nullable.
- Refuses to downgrade if any user has a NULL `username` — would otherwise lose rows. If you hit this, populate `username` manually first.

If the downgrade itself fails (should not happen, but if it does): restore from the Railway backup taken in pre-flight. Do not try to hand-patch the schema.

---

## After successful deploy

- [ ] Update `docs/value/00-source-of-truth.md` deployment table: brandista-api alembic head = `0002_canonical_id`.
- [ ] Update Railway deploy command for `brandista-api` service to include `alembic upgrade head &&` before the app start command, so future migrations apply automatically. (Do **not** do this in the same deploy as the stamp — do it as a separate config change after step 4 passes.)
- [ ] Tag the commit: `git tag -a identity-v1-prod -m "Canonical identity schema live in prod"` and push the tag.
