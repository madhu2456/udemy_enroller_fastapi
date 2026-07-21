# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses date-based notes until formal version tags are published.

## [Unreleased]

Work in the working tree since `e6bc1c2` (not necessarily committed yet).

### Added

- **Production coupon checker every 2 hours** — Docker Compose `coupon-checker` service runs `scripts/coupon_checker_loop.py`, shares the data volume with `web`, and rewrites `PUBLIC_DEALS_PATH` (`/app/data/public_deals.json`) so `/udemycoupons` stays fresh without local runs + git push.
- `PUBLIC_DEALS_PATH` / `COUPON_CHECKER_INTERVAL_SECONDS` settings; empty-DB export safety (won't wipe an existing catalog when the DB has no coupon rows).
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

### Security

- See `SECURITY.md` and `/.well-known/security.txt`.
- Hosted multi-tenant cookie storage remains a residual risk; prefer self-hosting for full control. Stealth/Playwright and CloudScraper enrollment posture unchanged by explicit owner decision.

## [2026-07-06] — baseline `e6bc1c2`

### Summary

Last published commit on `main` at the start of the forensic audit / implementation pass:

- Phase 4 trust copy, SEO, a11y, stats, lint, and hosted-demo login work (see git history for detail).

---

[Unreleased]: https://github.com/madhu2456/udemy_enroller_fastapi/compare/e6bc1c2...HEAD
