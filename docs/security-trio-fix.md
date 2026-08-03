# Fix #4 — Security trio (ops)

**Applies to:** uncommitted Fix #4 worktree changes on top of `ae5c5ff` (2026-08-01)
**Scope:** fail-closed key validation · consent-first tracking (no noscript iframe, single gtag loader) · static MIME types + cache-bust · `.do/app.yaml` removal
**Audience:** anyone running the Docker deploy (`/opt/udemy-enroller`), rotating secrets, or debugging boot/analytics issues

This is the operations companion to the Fix #4 code changes. It documents why the behavior changed, the **mandatory runbook for rotating secrets**, and how to verify the fix after deploy.

## 1. What changed and why

### 1.1 Server mode now fails closed on weak/invalid keys

`config/settings.py` (validator `validate_production_settings`) rejects, in `DEPLOYMENT_ENV=server`:

- `SECRET_KEY` shorter than **32 characters** → `SECRET_KEY must be at least 32 characters long in server mode. Generate one with: python -c "import secrets; print(secrets.token_hex(32))"`
- Known placeholder / example values (blocklist `_INSECURE_SECRET_KEYS`):
  - the **47-char default** `change-me-in-production-use-a-strong-secret-key` (the class default)
  - the **42-char `.env.example` sample** `change-me-to-a-random-string-in-production`
  - `change-me-in-production`, `change-me`, empty string
- **All-same-character** values (`len(set(SECRET_KEY)) == 1`, e.g. `aaaa…`)
  → `SECRET_KEY is a known placeholder or low-entropy value in server mode. Generate a strong random key with: python -c "import secrets; print(secrets.token_hex(32))"`
- `COOKIE_ENCRYPTION_KEY` that is not a **valid Fernet key** (44-char urlsafe base64) — checked with `Fernet(key)`, so empty, truncated, or garbage values all fail
  → `COOKIE_ENCRYPTION_KEY must be a valid Fernet key (44-char urlsafe base64) in server mode. Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

The previous gate only rejected an **empty** `COOKIE_ENCRYPTION_KEY` and accepted `change-me`-style `SECRET_KEY`s. Now any known placeholder or malformed key **prevents startup entirely** (fail closed), instead of booting with a trivially guessable secret.

Local mode is untouched in spirit: it auto-generates a random `SECRET_KEY` **only** for the truly-insecure markers (`change-me-in-production-use-a-strong-secret-key`, `change-me-in-production`, `change-me`, empty) and deliberately **keeps the 42-char `.env.example` placeholder stable** so dev sessions and the derived cookie key survive restarts (see §6).

### 1.2 Tracking: noscript iframe removed, single gtag loader

`app/templates/components/base.html`:

- The **GTM noscript iframe** (`https://www.googletagmanager.com/ns.html?id=…`) is **removed**. No-JS visitors are no longer tracked (they could not express consent anyway, so this is consent-first and matches the README/privacy claim that analytics load only after consent).
- The **direct GA4 loader** (`gtag/js?id=…`) now renders **only when no GTM container is configured**: `{% if request.app.state.ga4_measurement_id and not request.app.state.gtm_container_id %}`.
  - Why: with both set, the GTM container (which carries the **GA4 - Config** tag — see `gtm-container-export.json`, the single `googtag` tag) fires a page_view and the direct loader fired a second one → **double pageview**.
  - **Dependency to verify:** if the *live* GTM container lacks the GA4-Config tag, analytics stop entirely (the direct loader is now suppressed whenever `GTM_CONTAINER_ID` is set). Confirm the live container's tag set matches `gtm-container-export.json`, ideally with GTM **Preview** mode (load the site, check the GA4 tag fires with `page_view`).

Consent gating (no tracking until the consent banner is accepted) is unchanged.

### 1.3 Static MIME types registered at startup + `?v=2` cache-bust

- New `app/mime.py` (`register_extra_mimetypes()`) is called in `main.py` **before** `app.mount("/static", …)`. `python:3.11-slim` ships no `/etc/mime.types`, so Starlette's static file server served fonts/logos as `application/octet-stream`; the `X-Content-Type-Options: nosniff` header then blocked the self-hosted Inter font and the logo. Registered pairs:

  | Extension | MIME type |
  |-----------|-----------|
  | `.woff2` | `font/woff2` |
  | `.woff` | `font/woff` |
  | `.ttf` | `font/ttf` |
  | `.otf` | `font/otf` |
  | `.eot` | `application/vnd.ms-fontobject` |
  | `.webp` | `image/webp` |

- Font/icon/CSS references now carry `?v=2` (`/static/fonts/inter-latin.woff2?v=2`, `/static/images/icon-512.webp?v=2`, `/static/fonts/inter.css?v=2` — in `base.html` and `inter.css`) so clients refetch the now-correctly-served assets once. Cache-bust strings are harmless to keep.

### 1.4 `.do/app.yaml` deleted

`.do/app.yaml` (stale DigitalOcean App Platform spec) was deleted. It was non-bootable under the new rules: it only set `SECRET_KEY`, never `COOKIE_ENCRYPTION_KEY`, and pointed `DATABASE_URL` at a container-local path (`sqlite:///./udemy_enroller.db`) — no persistent volume. The supported deployment path is Docker Compose (`docker-compose.yml`, `scripts/deploy.sh`).

## 2. CRITICAL — Rotating `SECRET_KEY` (CSRF invalidation runbook)

**Why it's critical:** CSRF tokens are **HMAC-bound to `SECRET_KEY`** — `generate_csrf_token` = `HMAC-SHA256(SECRET_KEY, session_token)` truncated to 32 hex (`app/security.py:152-159`). Rotating `SECRET_KEY` invalidates **every outstanding CSRF token at once**: all POST requests for logged-in users return `403 CSRF token invalid` — **including logout itself** (logout depends on `verify_csrf_token`). Meanwhile sessions themselves survive (they are DB rows keyed by a random `session_token`, not the CSRF HMAC) up to the **24-hour server-mode TTL** (`_SESSION_TTL_SERVER_SECONDS = 24 * 60 * 60`, `app/routers/auth.py:33`).

Perform rotation in a **maintenance window**, in this order:

```bash
# (a) Rotate keys on the server BEFORE pulling/deploying.
#     If you deploy first, the container crash-loops: alembic/env.py imports
#     get_settings() at module level, the validator raises, and
#     docker-entrypoint.sh dies at "alembic upgrade head" (restart: unless-stopped).
cd /opt/udemy-enroller   # or your app dir
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "from cryptography.fernet import Fernet; print('COOKIE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
# Edit .env with both new values, then deploy:
git pull origin main
docker compose up -d --build
```

```bash
# (b) After the containers are healthy, wipe app sessions so old, CSRF-broken
#     sessions die cleanly and users re-login.
#     Compose service: web  (container_name: udemy-enroller)
#     App DB: sqlite:////app/data/udemy_enroller.db  (app-data volume).
#     The image is python:3.11-slim — the sqlite3 CLI is NOT installed,
#     so use Python's stdlib sqlite3 module inside the container:
docker compose exec -T web python -c "import sqlite3; con = sqlite3.connect('/app/data/udemy_enroller.db'); n = con.execute('DELETE FROM user_sessions;').rowcount; con.commit(); con.close(); print(f'Deleted {n} sessions')"
```

  Equivalent, if you prefer a host-side CLI (sqlite3 on the host, volume copied in/out):

```bash
docker compose cp web:/app/data/udemy_enroller.db ./udemy_enroller.db
sqlite3 ./udemy_enroller.db "DELETE FROM user_sessions;"
docker compose cp ./udemy_enroller.db web:/app/data/udemy_enroller.db
```

  Re-login works immediately after the wipe: cookie login (`POST /login/cookies`) is **not CSRF-protected** (rate-limiter only), so the flow only needs a fresh `session_token` + fresh CSRF token from the login response.

```bash
# (c) Expect a short spike of:
#       - 403 "CSRF token invalid" on POSTs from users still holding old pages
#       - "Failed to decrypt cookies — possible key rotation or tampering" warnings
#         (app/security.py:97) — see §3
# (d) Monitor:
docker compose logs -f web
docker compose exec -T web tail -f /app/logs/app.log   # LOG_FILE=logs/app.log
```

## 3. Rotating `COOKIE_ENCRYPTION_KEY` (stored cookies become undecryptable)

Stored **encrypted Udemy cookies** in `users.udemy_cookies` are Fernet-encrypted with the (explicit or derived) `COOKIE_ENCRYPTION_KEY`. Rotating it makes every stored ciphertext undecryptable: `decrypt_cookies()` returns `None` and logs `Failed to decrypt cookies — possible key rotation or tampering` (`app/security.py:75-98`). This is **documented behavior**, not an error:

- Users must **re-paste their Udemy cookies** on the login page (their previous stored cookies cannot be recovered).
- App sessions (login) keep working — session cookies are not encrypted with this key.
- The `DELETE FROM user_sessions;` wipe from §2(b) is still recommended if you rotate both keys, so users start from a clean re-login.

## 4. `scripts/deploy.sh` — key generation

When `.env` does not exist yet, `deploy.sh` now writes **both** keys:

```bash
SECRET_KEY=$(openssl rand -hex 32)
COOKIE_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

This requires **`python3` + `python3-cryptography`** on the droplet host (the command imports `cryptography.fernet`). If `python3-cryptography` is missing, the command fails and `.env` is left without the Fernet key — install it (`apt-get install -y python3-cryptography`) or set `COOKIE_ENCRYPTION_KEY` manually before running the stack. `deploy.sh` never overwrites an existing `.env`, so rotated keys are preserved across deploys.

## 5. `coupon-checker` — fails fast on invalid settings

`scripts/coupon_checker_loop.py` now validates settings **at startup** (`get_settings()` in a try/except). On failure it logs `Settings validation failed: …`, prints `Coupon checker aborting: settings validation failed — check SECRET_KEY/COOKIE_ENCRYPTION_KEY/DEPLOYMENT_ENV` to stderr, and `sys.exit(1)`. Previously the loop kept retrying every cycle with a stale catalog, hiding the misconfiguration. Because the compose `coupon-checker` service shares the same `SECRET_KEY`/`COOKIE_ENCRYPTION_KEY` environment as `web`, an invalid key now fails the whole stack loudly instead of silently degrading.

## 6. Local development — placeholder key is STABLE

In `DEPLOYMENT_ENV=local`, the 42-char `.env.example` placeholder (`change-me-to-a-random-string-in-production`) is **not** in the local autogen blocklist, so it is kept as-is across restarts → no per-restart `SECRET_KEY` churn, a stable derived cookie key, and dev sessions persist. Only the truly-insecure markers (`change-me-in-production-use-a-strong-secret-key`, `change-me-in-production`, `change-me`, empty) still auto-generate a fresh random `SECRET_KEY` on every start (covered by `tests/test_phase2_features.py::TestSettingsValidation::test_local_env_keeps_env_example_placeholder_stable`).

## 7. Verification

```bash
# 7.1 Weak/invalid keys must be rejected at boot with the actionable message.
#     Set SECRET_KEY=change-me (or COOKIE_ENCRYPTION_KEY=) in .env, then:
cd /opt/udemy-enroller
docker compose up -d --build
docker compose logs web
#   → "SECRET_KEY is a known placeholder or low-entropy value in server mode. …"
#   → or "COOKIE_ENCRYPTION_KEY must be a valid Fernet key (44-char urlsafe base64) in server mode. …"
#     (raised during the entrypoint's "alembic upgrade head" step — see §2(a))
docker compose down   # restore real keys afterwards

# 7.2 Rendered HTML: no noscript iframe, exactly one analytics loader path.
#     With GTM configured: 0 direct gtag/js loaders + 1 gtm.js loader.
#     With GA4 only:       exactly 1 direct gtag/js loader.
curl -s https://your-domain/ | grep -c "ns.html"                                   # 0
curl -s https://your-domain/ | grep -o "googletagmanager.com/gtm.js" | wc -l        # 1 (GTM) or 0
curl -s https://your-domain/ | grep -o "googletagmanager.com/gtag/js" | wc -l       # 0 (GTM) or 1 (GA4-only)

# 7.3 MIME types — use the cache-busted ?v=2 URLs (the /static URLs are unchanged
#     on disk; ?v=2 only changes the request URL):
curl -sI https://your-domain/static/fonts/inter-latin.woff2?v=2 | grep -i content-type   # font/woff2
curl -sI https://your-domain/static/images/icon-512.webp?v=2 | grep -i content-type    # image/webp

# 7.4 Regression suite:
pytest tests/test_phase2_features.py -k "secret or placeholder or cookie_encryption"
pytest tests/test_analytics_consent.py
pytest tests/test_static_mime.py
```

## 8. Rollback

- **Code:** `git revert` the Fix #4 commit (or discard the worktree changes if not yet committed). This restores the **old validator** — empty-only `COOKIE_ENCRYPTION_KEY` check and no placeholder gate — which **re-opens the weak-key hole**. Treat any revert as incident response: rotate to strong keys immediately afterward (see §2) rather than leaving the old validator in place.
- **Keys:** reverting code does not un-rotate `.env` values — keep the rotated keys; they are valid under the old validator too.
- **Assets:** the `?v=2` query strings are harmless if left in place (they are plain query params on static URLs); no cleanup needed.
- **Tracking:** the GTM noscript iframe and double loader return only if the `base.html` revert is deployed; no data migration involved.
