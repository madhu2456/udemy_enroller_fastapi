# PWA posture: manifest-only, no service worker (ops decision)

**Status:** Owner decision, recorded 2026-08-13.
**Scope:** Progressive-Web-App features for the hosted demo + self-host.
**Current state:** installable-manifest only (`app/static/manifest.webmanifest`,
served by `app/routers/seo.py` at `/manifest.webmanifest`, linked from
`app/templates/components/base.html`). **No service worker, no offline
support, no push.**

## Why manifest-only (no service worker today)

| Factor | Detail |
|--------|--------|
| Data freshness | Coupon data (`/udemycoupons`, `public_deals.json`) is time-sensitive; stale offline caches mislead users into expired coupons. SW caching raises stale-data risk with no user benefit for this workload. |
| Multi-tenant session security | The app stores session + CSRF cookies with `samesite=lax/strict`. A SW becomes another cacheable origin scope; a caching bug could serve authenticated shell pages from a stale copy after logout (cookie wipe on last session — F-ENRL-C08). |
| Ops complexity | SW versioning/update flow, cache invalidation, and `Cache-Control` interplay add deploy-time failure modes to a small self-hosted deploy (`deploy.sh`), for zero current feature need. |
| HTTP-cache equivalent | The public pages already benefit from ETag/`Cache-Control` headers and GZip middleware; the performance baseline (see `docs/performance-baseline.md`) shows no SW required. |

## What the manifest gives users

- "Add to Home Screen" / install affordance in Chromium browsers.
- Standalone-ish launch (`display: minimal-ui`), correct icon (512 any +
  maskable), theme color.
- No offline or push promises are made to the user.

## Explicit non-goals (do not add without a new owner decision)

1. **Service worker** (offline shell, precache, background sync) — revisit
   only if analytics show meaningful repeat mobile usage AND offline/cache
   staleness rules are designed (never cache authenticated shell pages or
   deal data older than the coupon validity window).
2. **Web Push** — requires VAPID keys, a push service, and notification
   permission UX; out of scope for a coupon automation tool.
3. **Install prompts / beforeinstallprompt interception** — the browser's
   native install affordance is enough; intercepting prompts adds tracking
   surface without consent value.

## Roadmap (if the owner later changes direction)

- [ ] Re-measure repeat-visit share and mobile installs (GTM/GA4 events on
      `appinstalled`).
- [ ] Draft SW update policy: `skipWaiting` + `clients.claim` with
      versioned cache names; no caching for `/api/`, `/dashboard`, `/#connect`,
      or any page while an authenticated session exists.
- [ ] Add `Cache-Control: no-store` assertions on authenticated routes before
      any SW lands.
- [ ] Owner decision on offline data staleness window for `/udemycoupons`
      (suggest: refuse to serve offline deals older than 6h).
- [ ] Security review of the SW scope (`./`, not `/`) and fetch handler
      before ship.

## Verification (current posture)

```bash
curl -sI https://your-domain/manifest.webmanifest | grep -i content-type   # application/manifest+json (or JSON)
curl -s https://your-domain/ | grep -c 'rel="manifest"'                    # >= 1
# No service worker must exist:
curl -s https://your-domain/sw.js -o /dev/null -w '%{http_code}\n'          # 404 expected
grep -rn "serviceWorker" app/ || true                                       # no matches expected
```
