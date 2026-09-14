# Enroller PWA close-out — verification record (U5)

**Status:** Owner-decision recorded 2026-08-13 (`docs/ops/pwa-decision.md`);
this close-out record re-verified the posture against the repo on
**2026-09-04** (owner/verify lane — no code changes made or needed).
**Audit basis:** `enroller PWA no-SW` (hygiene batch, v8.3-r2 registry) —
the finding is the deliberate **absence** of a service worker, not a defect.

## Current state (verified 2026-09-04)

| PWA piece | State | Evidence |
|---|---|---|
| Web app manifest | **Present, wired** | `app/static/manifest.webmanifest`; served at `/manifest.webmanifest` by `app/routers/seo.py:29-33` (`application/manifest+json`); linked from every page via `app/templates/components/base.html:47` (`<link rel="manifest">`) |
| Manifest icons | Present | `/static/images/icon-512.png` + `.webp` exist in `app/static/images/` (any + maskable purposes declared) |
| Service worker | **Absent by decision** | `grep -rn "serviceWorker" app/` → 0 matches; no `sw.js` anywhere in `app/` |
| Offline/push | Absent (explicit non-goal) | `docs/ops/pwa-decision.md` non-goals §1–3 |

## Decision already made — no new owner action required

The keep/remove/stabilize decision was taken on 2026-08-13 and stands:
**manifest-only, no service worker** (stale-coupon risk + multi-tenant
session-security risk + ops complexity outweigh offline benefit; see the
decision doc's factor table). "Stabilize" = nothing to do: the manifest path
is fully wired and covered by the decision doc's verification curl block
(manifest content-type, `rel="manifest"` present, `sw.js` 404 expected).

Re-open conditions (from the decision doc's roadmap): meaningful repeat
mobile usage AND an offline-staleness policy — until then the close-out is
**done**: posture documented, verified consistent with code, no dangling
half-wired artifacts (the only PWA artifacts are the manifest + its link,
both intentional).
