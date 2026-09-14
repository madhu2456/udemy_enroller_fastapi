# Legacy cookie-decrypt verify-off — owner checklist (U5)

**Status:** Owner-executes (no-claims lane) — recorded 2026-09-04. Nothing has
been flipped by agents; this doc is the runbook + evidence trail.
**Audit basis:** `UE legacy-decrypt env` (hygiene batch, master-audit v8.3-r2
`02-FINDINGS-REGISTRY-D1.md`) — runbook for the flag that closes the
F-ENRL-C01 migration window.

## What the mechanism is

Backward-compat decrypt for **pre-F-ENRL-C01 cookie blobs** in
`app/security.py` `decrypt_cookies`:

| Legacy format | Acceptance gate | Code |
|---|---|---|
| Master-key Fernet envelope (unsalted) | `ALLOW_LEGACY_COOKIE_DECRYPT` | `security.py:237-251` |
| Plaintext dict (pre-encryption) | `ALLOW_PLAINTEXT_COOKIES` | `security.py:191-198` |

Flag semantics (`security.py:147-188`): explicit env `1/true/yes/on` = ON,
`0/false/no/off` = OFF; unset → **ON for `DEPLOYMENT_ENV=local`, OFF for
`server`/`production`** (fail-closed). Server deployments already default to
verify-off — the flip is only needed where `ALLOW_LEGACY_COOKIE_DECRYPT=1` was
deliberately set (the migration window, see `scripts/migrate_cookies_per_session.py`
header) or a local env is being hardened.

"Verify-off" per the registry = confirm the legacy path is **unusable and
provably unused** in the target environment, not merely defaulted.

## Flip sequence (owner, in order)

1. **Preconditions** — verified backup exists (`docs/ops/backup-restore.md`
   drill; the migration script itself refuses `--apply` without
   `--backup-verified`) and the per-session migration is complete:
   ```bash
   python scripts/migrate_cookies_per_session.py        # dry-run report
   # Expect "legacy_remaining": 0 before you flip anything off.
   ```
2. **Flip** — in the target environment's env (host `.env` for containers,
   shell env for local):
   ```bash
   ALLOW_LEGACY_COOKIE_DECRYPT=0    # fail-closed; also remove any =1
   ALLOW_PLAINTEXT_COOKIES=0        # same fail-closed direction (F019 parity)
   ```
   Local-only note: unset defaults to ON in `DEPLOYMENT_ENV=local`, so local
   hardening requires the explicit `=0`.
   No restart-ordering constraint: the flag is read per-decrypt
   (`os.environ.get` inside `_allow_legacy_cookie_decrypt`), so a container
   needs `docker compose up -d` (env baked at container start), a local
   process needs a restart after the env change.
3. **Soak** — run normal traffic (login/enrollment) for one cycle.

## How to verify legacy path unused (owner evidence)

- **Unit proof (repo-side, runs anywhere):**
  ```bash
  venv/bin/python -m pytest tests/test_cookie_envelope.py -q
  # tail: 13 passed — covers flag-OFF rejection, defaults-by-env,
  # explicit-env overrides, salted path working with legacy OFF.
  ```
- **DB proof (no legacy rows remain):** re-run the migration dry-run (step 1)
  and keep the JSON report showing `"legacy_remaining": 0`.
- **Log proof (live):** with the flag off, any legacy blob attempt logs
  `Rejected legacy (unsalted) cookie ciphertext — ALLOW_LEGACY_COOKIE_DECRYPT is off`
  (WARNING, `security.py:239-242`). Zero such lines during soak + zero
  `Decrypting legacy (unsalted) cookie blob` lines = legacy path unused:
  ```bash
  grep -h "legacy" logs/app.log | sort | uniq -c     # local
  docker compose logs web 2>&1 | grep -c "legacy"    # container
  ```
  Expected after clean soak: `Decrypting legacy` count 0; `Rejected legacy`
  only if some stale client still presents an old blob (that user must log
  in again — expected 401 path, not an incident).
- **Behavioral spot-check:** log in with a migrated account — succeeds with
  the flag off (per-session envelope path, `security.py:225-231`).

## Rollback

Set `ALLOW_LEGACY_COOKIE_DECRYPT=1` + restart — legacy blobs decrypt again
(with the WARNING). Reversible without code changes or migrations.

## Compose caveat

`docker-compose.yml` does not pass `ALLOW_LEGACY_COOKIE_DECRYPT` through, so
for containers the flag comes from the host `.env` only if the entrypoint
loads it or the compose `environment:` list is extended — verify the env
inside the container before relying on it:
```bash
docker compose exec web printenv ALLOW_LEGACY_COOKIE_DECRYPT   # unset is expected-fine in server mode (defaults OFF)
```
