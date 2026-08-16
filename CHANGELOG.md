# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses date-based notes until formal version tags are published.

## [Unreleased]

Work in the working tree since `e6bc1c2` (not necessarily committed yet).

### Docs — Alembic head / local apply (2026-08-16)

- Chain head is `c01d021a9e03` (not `c01d021a9e01`). Revisions `c01d021a9e01` (`users.cookies_salt`), `c01d021a9e02` (`enrollment_runs.last_heartbeat`), and `c01d021a9e03` (drop `user_settings.firecrawl_api_key` / `enable_headless`) are inspect-idempotent.
- `alembic/env.py` fail-closes when both `udemy_enroller.db` and `data/udemy_enroller.db` exist unless `sqlalchemy.url` is an explicit pin (`scripts/alembic_upgrade_pinned.py`).
- **Local** live DB (`./udemy_enroller.db`) upgraded to `c01d021a9e03` (`cookies_salt` + `last_heartbeat` present). Production named volume **not** upgraded.
- `scripts/migrate_cookies_per_session.py` **not** run. `AUTO_CREATE_TABLES` remains `False`.

### Docs — F004 residual accepted (2026-08-16)

- F004 residual accepted (ops/product); no key rotate. Not legal advice / not counsel-approved DPIA.

### Docs — F011 last-success proven (2026-08-16)

- Host proof recorded: named volume `app-data`, backups `/var/backups/udemy-enroller`, newest file age 6.16 h, integrity ok, 26 h freshness exit 0, cron present. Restore not run.
- F004 remains **open / UNSIGNED** (Defer). Owner may now Accept. F011 no longer blocks key rotation; still no rotate/purge unless the owner asks.
- Documented `--install-backup-cron` does **not** match this host — do not run it blindly.

### Docs — F004 owner decision = Defer until F011 (2026-08-16)

- **Not residual acceptance.** Decision ☑ Defer only (not Accept, not Redesign). Signature n/a — not accepted. F004 remains **open / UNSIGNED**.
- No key rotation or blob purge until F011 last-success is proven.

### Docs — unsigned F004 DPIA / D.3 wording (C1–C7)

- **Not a close:** F004 remains open. No key rotation or blob purge.
- `docs/dpia-enroller-cookies-skeleton.md` **0.6-draft-v1**: drop false DPDP SPD/s.7/s.7(c) cites; privacy **template exists** / per-session envelope **not** on `privacy.html` (HTML not edited); `security-trio-fix.md` labeled fail-closed validation; §2.6 Udemy **plus** optional GTM/GA4 after consent; **F019-plaintext** vs fleet F019 humans.txt; wipe is live-DB only vs 14d/30-file unencrypted backups.

### P3/P4 wave — last enroller items (F-ENRL-*, F-XSITE-*)

- **C11**: Alembic migration `alembic/versions/c01d021a9e03_drop_firecrawl_and_headless_from_user_settings.py` (head `c01d021a9e03`) drops `firecrawl_api_key` / `enable_headless` from `user_settings` (inspect-idempotent). Applied on the **local** live DB; production **not** upgraded.
- **C13**: `scripts/deploy.sh` hardened — `set -euo pipefail` fail-fast, `chmod 600` on the generated `.env`; `bash -n` clean.
- **C15**: coupon-checker loop now serves a loopback `/health` endpoint (default port 8001, `COUPON_CHECKER_HEALTH_PORT` override) reporting `last_run_age_seconds`; 200 `ok` while a cycle finished within 26h, 503 `stale` otherwise (incl. before the first run). Docker Compose `coupon-checker` healthcheck wired to it. `COUPON_CHECKER_HEALTH_PORT` is also documented in the compose service comment (`.env.example` editing is blocked by the repo's `*.env.*` policy; compose is the reference).
- **Tests**: `tests/test_coupon_checker_health.py` — /health 200 + age, 503 stale >26h / never-run, 404 unknown path (ephemeral port 0, importlib-by-path).
- **F-XSITE-001**: seo.py FAQ + ai-profile.json `Person`/`author` descriptions now use `config.settings.experience_years_label()` (SSOT from `EXPERIENCE_START`); zero `10+ years` literals remain in `app/`.
- **F-XSITE-002**: base.html footer copyright `© {{ current_year }} Enroller by Madhu Dadi`; `current_year` global registered on all four Jinja2Templates instances (main/dashboard/public_deals/seo) in main.py's template-globals loop.
- **F-XSITE-009**: `twitter:creator` meta added after `twitter:site` in base.html (deviation from plan: base.html is the shared head template, not seo.py).
- **F-ENRL-J03**: **CLOSED** — `docs/legal-counsel-review.md` §4a (India IT Act / intermediary draft rationale) verified against repo facts: no user-to-user content hosting/transmission, session cookies per-user for own automation runs, DPDP-not-IT-Act identified as the relevant Indian framework for cookie processing; still explicitly draft-for-counsel, not legal advice.

### Coupon-checker hardening (resolver tiers + safety valve)

- _resolve_course_id(http, url, slug=None): fields → bare → raw-verbatim-path-slug → HTML tiers;
  fixed _BROWSER_UA + req_type="api" + log_failures=False on all five JSON call sites.
- _fetch_pricing_json: plain-httpx-first (status 200 + dict), cloudscraper fallback; discountCode
  quote()-encoded; _coerce_valid_course_id predicate (rejects 0/junk/unicode digits).
- Slug tiers: attempts=2 (transport) + single 2s backoff on 429, then fall through.
- main(): atomic snapshot every 10 deals (refresh_sitemap=False), empty-snapshot guard,
  safety valve (expired > 75% done AND error < 5% done → skip snapshot AND final save;
  preserves last known-good file). Residual floor ~1.6% (6 collision-slug deals) accepted.
- DEPLOY (run before `git checkout .`): backup dirty tree (git diff > /root/predeploy-<ts>.diff;
  cp -a each dirty path to /root/predeploy-backup/), reconcile each dirty path against this
  batch's file list, then: git checkout . && git pull origin main && docker compose up -d --build.
  Post-deploy: git rev-parse HEAD == pushed sha; docker compose ps (new Started time);
  first "=== Coupon check cycle start ===" after Started; grep -c discountCode == 0.
  Pass criteria: error <= 10% (<= 38/380); expired within ±5 pts of baseline; zero discountCode
  in logs; 6 collision slugs + situational_leadership + >55-char slugs resolve via any tier.

### P2 wave — review fixes (R1–R6)

- **Fixed**: login CSRF origin gate now compares netloc (`host[:port]`, case-insensitive) only, ignoring scheme — behind Cloudflare Flexible SSL the browser sends an `https` Origin while nginx forwards `X-Forwarded-Proto: http` ($scheme), which previously 403'd every login POST. The `samesite=strict` double-submit cookie remains the primary control; optional `PUBLIC_BASE_URL` overrides the expected origin netloc when set.
- **Fixed**: stale-run sweeper catches transient exceptions (e.g. SQLite lock contention) inside the loop, logs, and continues instead of killing the recovery sweeper.
- **Changed**: `.env.example` documents `STALE_RUN_TIMEOUT_MINUTES=15` / `STALE_RUN_SWEEP_SECONDS=60` (F-ENRL-O01).
- **Docs**: corrected `pyproject.toml` typing-baseline comment (mypy `app/services/enrollment_manager.py` measured 21 errors incl. P2 lines, not 27).

### Added

- **Production coupon checker every 2 hours** — Docker Compose `coupon-checker` service runs `scripts/coupon_checker_loop.py`, shares the data volume with `web`, and rewrites `PUBLIC_DEALS_PATH` (`/app/data/public_deals.json`) so `/udemycoupons` stays fresh without local runs + git push.
- Coupon checker validates **`public_deals.json` only** (not the multi-tenant user DB); enrollment **merges** free finds into the catalog instead of full DB export replace.
- `PUBLIC_DEALS_PATH` / `COUPON_CHECKER_INTERVAL_SECONDS` settings; `save_public_deals` / `merge_deals_into_public_catalog` helpers.
- `CONTRIBUTING.md` — setup, tests, PR expectations, and contribution safety rules.
- GitHub issue templates (bug/feature) and pull request template under `.github/`.
- Issue template config links to `SECURITY.md` / security.txt.
- README **Updating** and **Uninstall / remove** sections (local, Docker, hosted demo).
- Clearer security contacts in `SECURITY.md` and `security.txt` (GitHub advisories + profile; no invented public email).
- Accessible confirm dialog (`window.accessibleConfirm`) for enrollment start, delete run, settings reset/clear (focus trap, Escape, restore focus).
- `docs/wcag-audit.md` — WCAG 2.2 AA **target** audit notes (axe + keyboard smoke); `npm run audit:wcag` with optional `BASE_URL`.
- `docs/performance-baseline.md` — lab CWV + Lighthouse baseline before perf trim; refreshed `tests/performance-baseline.json` and `performance-report/` snapshots.
- `/static/css/site.css` — shared chrome styles extracted from base template (cacheable).
- `tests/browser-smoke.js` + `docs/browser-smoke.md` — Chromium/Firefox/WebKit public + auth shell smoke (`npm run smoke:browsers`).
- `tests/viewport-smoke.js` + `docs/viewport-smoke.md` — 320–1920 responsive matrix (`npm run smoke:viewports`).
- `SECURITY.md` — private vulnerability reporting guidance.
- `/.well-known/security.txt` and `/security.txt` (RFC 9116-style contact/policy).
- Session expiry metadata on `GET /api/auth/status` (`session_expires_at`, remaining seconds, deployment env).
- Dashboard and settings UI notes for session lifetime (hosted ~24h, local longer).
- `app/session_lifecycle.py` — shared cleanup when sessions expire.
- `tests/conftest.py` — ensure DB schema exists for app-engine tests.
- `tests/test_session_lifecycle.py` — cookie wipe on last session expiry.

### Changed

- **Security / sessions**
  - Server-side auth gate for `/dashboard` HTML (redirect to connect if unauthenticated).
  - Logout closes cached Udemy client and clears CSRF cookie; wipes stored Udemy cookies.
  - Clear All Data also clears sessions and Udemy cookies (keeps user row + settings); signs the browser out.
  - Hosted demo app sessions: **24 hour** TTL; local: **30 days**.
  - On last session expiry, wipe encrypted `udemy_cookies` when no other active sessions remain.
  - Deploy workflow Actions pinned to full commit SHAs (no `@master`).
  - Analytics event endpoint rate-limited; health check no longer returns raw DB exception text.
  - Default `GTM_CONTAINER_ID` / `GA4_MEASUREMENT_ID` empty (set in production `.env`).

- **Product safety / trust copy**
  - Enrollment start requires browser confirmation.
  - Stronger hosted-demo and Terms disclaimers on connect UI.
  - Public marketing and meta copy softened: attempt enrollment when you start a run; not guaranteed; not affiliated with Udemy (home, about, FAQ, guides, coupons, llms/seo text).
  - Privacy policy text aligned with clear-data and hosted cookie retention.

- **SEO / structured data**
  - Homepage JSON-LD: single canonical `SoftwareApplication` (`#softwareapplication`); page graph uses `WebPage` + `SoftwareSourceCode` references.
  - `/login` compatibility redirect to `/#connect`.
  - humans.txt: accessibility **target** WCAG 2.2 AA (not a conformance claim).

### Removed

- **Removed**: stale, non-bootable `.do/app.yaml`.

### Fixed

- Misleading privacy claim that Clear All Data deleted account/settings/cookies without doing so (behavior + copy aligned).
- Residual “24/7 always-on auto-enroll” style claims on key public surfaces.
- Public-page a11y (axe WCAG 2.2 AA tags): contrast on muted labels / coupon prices / privacy code; always-underline body links; footer 24px min touch targets; keyboard-focusable privacy cookie table scroller.
- Auth UI keyboard a11y: settings switches (`role="switch"`, labels, 24px targets), form label `for` wiring, dashboard tablist/panels, history expandable run cards, stats modal focus trap/Escape, clearer contrast and control names.
- Performance trim (#25): coupons page SSR first 12 cards only; skip duplicate tojson + API re-fetch when SSR present; compact JSON-LD; scoped transitions; site chrome CSS externalized.
- Narrow-viewport overflow: guides step/code flex `min-w-0`; settings header stacks on small screens.
- Rate limits on more unauthenticated edges: CSP reports, public coupons API, auth status (login/analytics already limited; health stays open).
- Concurrent session cap (`MAX_SESSIONS_PER_USER`, default 3): oldest app sessions revoked when a new login exceeds the limit.
- Enrollment saves `is_coupon_valid` / `last_checked_at` and regenerates `public_deals.json` when a run finishes (same export as coupon checker).
- `docs/legal-counsel-review.md` — owner process pack for external legal/trademark/ToS review (not legal advice).
- Shared `public_deals.json` export: enrollment runs and `scripts/coupon_checker` both refresh the public coupons list.
- Indexable coupon detail pages `/udemycoupons/c/{slug}` (readable course name/slug; numeric IDs 301 to slug) + sitemap entries for valid deals (on-site URLs only).
- Sitemap deal URLs rebuild whenever enrollment or coupon_checker exports `public_deals.json` (`write_sitemap_files` + live `GET /sitemap.xml`).
- SEO/AEO/GEO: hub freshness + categories, `/udemycoupons/category/{slug}`, pillar guide `/guides/free-udemy-coupons`, related deals + BreadcrumbList on deal pages, softened `llms.txt` Key facts, no Crawl-delay for major bots.
- Residual SEO code pass: claim/copy sweep (FAQ schema+body, about, login, README, base banner, guides, llms); deal pages with unique how-to + FAQ JSON-LD + LimitedAvailability; sitemap quality filter (title length, 30-day freshness); hub Breadcrumb/CollectionPage; footer link to coupon guide; `docs/seo-residual-checklist.md` for remaining GSC/legal/ops items.
- **Fixed**: fonts and webp images were served as `application/octet-stream` on the slim production image (blocked by `nosniff`); MIME types now registered at startup and static asset URLs cache-busted (`?v=2`).

### Security

- See `SECURITY.md` and `/.well-known/security.txt`.
- Hosted multi-tenant cookie storage remains a residual risk; prefer self-hosting for full control. Stealth/Playwright and CloudScraper enrollment posture unchanged by explicit owner decision.
- **Security**: server-mode `SECRET_KEY` validation now rejects known placeholder and low-entropy values; `COOKIE_ENCRYPTION_KEY` must be a valid Fernet key in server mode (fail-closed at boot with actionable errors).
- **Security**: removed the unconditional GTM `<noscript>` analytics iframe (pre-consent tracking for no-JS visitors); direct GA4 loader now only renders when no GTM container is configured (fixes duplicate pageviews).

### Ops

- **Ops**: `scripts/deploy.sh` now generates a Fernet `COOKIE_ENCRYPTION_KEY`; coupon-checker fails fast on invalid settings; see `docs/security-trio-fix.md` for the SECRET_KEY rotation runbook.

### Security — F-ENRL-C01 (per-session cookie envelopes)

- **Security**: hosted cookie blobs now encrypt under a per-session key — HKDF-SHA256 (info `udemy-enroller-session-key-v1`) derived from the master Fernet key plus a per-user `cookies_salt` (16 random bytes), rotated on every write site (login, save, refresh, connect). A blob decrypts only under the salt of the session that wrote it; wrong/missing salt fails closed (None → 401 → re-login).
- Legacy (unsalted master-key Fernet) blobs and plaintext dicts keep their prior behavior behind two independent flags: `ALLOW_LEGACY_COOKIE_DECRYPT` (default ON for local/dev with a warning, OFF for server/production) and the existing `ALLOW_PLAINTEXT_COOKIES`.
- Logout, session expiry, and Clear All Data now wipe `cookies_salt` as well, making old blobs undecryptable.
- Migration `alembic/versions/c01d021a9e01_add_cookies_salt_to_users.py` adds the `cookies_salt` column (inspect-idempotent ALTER; down_revision `0bd117e7d36c`). It is **not** the chain head — head is `c01d021a9e03` (via `c01d021a9e02` `last_heartbeat`). Applied on the **local** live DB; production **not** upgraded.
- `scripts/migrate_cookies_per_session.py` re-encrypts existing blobs per session (dry-run by default; `--apply` requires `--backup-verified`; JSON report) — **not run**.
- `.env.example` documents the new flag.

### Security — F-ENRL-C07 (host-validation gate)

- **Security**: all "is this Udemy?" checks in `app/services` now use parse-based allowlist helpers in `app/services/udemy_validation.py` (`is_udemy_netloc`, `is_udemy_url`, `is_udemy_course_url`, `is_trk_udemy_url` — exact netloc match). Substring/regex checks on the literal `udemy.com` (which accept hostile hosts like `udemy.com.evil.com`, `eviludemy.com`, `user@udemy.com`) were removed.
- `scripts/verify-no-udemy-substring.sh` regression gate runs in CI (`--tree` mode) and can run on the staged diff as a pre-commit check; fails on any new substring check in `app/services` (allowlist file exempt).

### Docs — F-ENRL-J01 (DPIA draft)

- `docs/dpia-enroller-cookies-skeleton.md` — draft DPIA skeleton **v0.4-draft-v1** for hosted encrypted cookie processing: controller, lawful basis (§4a options), retention, cross-border, DPDP Act 2023 pointers; sign-off DATE-PENDING (counsel review required).
- `docs/legal-counsel-review.md` — added draft IT Act / intermediary N/A rationale (marked draft-for-counsel, not legal advice).

## [2026-07-06] — baseline `e6bc1c2`

### Summary

Last published commit on `main` at the start of the forensic audit / implementation pass:

- Phase 4 trust copy, SEO, a11y, stats, lint, and hosted-demo login work (see git history for detail).

---

[Unreleased]: https://github.com/madhu2456/udemy_enroller_fastapi/compare/e6bc1c2...HEAD
