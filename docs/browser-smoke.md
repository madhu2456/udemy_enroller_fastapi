# Multi-browser smoke (#26)

**Purpose:** Basic load + auth shell confidence beyond Chromium-only lab work.  
**Not** full visual regression or real Udemy enrollment.

## How to run

```bash
# App on :8000, with a local session cookie (fake Udemy cookies for UI shell only)
export BASE_URL=http://127.0.0.1:8000
export SMOKE_TOKEN='<session_id cookie value>'

npm run smoke:browsers
# or
BROWSERS=chromium,firefox,webkit node tests/browser-smoke.js
```

Create a short-lived local session via the app DB (or your usual connect flow).  
**Never** use production user cookies or real Udemy credentials in automation.

## What is checked

| Area | Checks |
|------|--------|
| Public routes | `/`, `/about`, `/faq`, `/guides`, `/privacy`, `/udemycoupons` — HTTP 200, `h1`, main landmark, `lang`, title |
| Auth shell | `/dashboard`, `/settings`, `/history` — stay on route, key controls present |
| Dashboard keyboard | Start Enrollment → accessible confirm opens → Escape closes |

## Lab result (2026-07-12, local)

| Browser | Public | Auth + confirm | Notes |
|---------|--------|----------------|-------|
| **Chromium** | 6/6 | 4/4 | Pass |
| **Firefox** | 6/6 | 4/4 | Pass |
| **WebKit** | — | — | **Skipped**: host missing shared libs (`libavif16` / `playwright install-deps`) |

Artifacts:

- `tests/browser-smoke-summary.json` — compact result  
- `performance-report/browser-smoke-latest.json` — full detail (dir may be gitignored)

## Host deps for WebKit

On Ubuntu/Mint, after installing Playwright browsers:

```bash
npx playwright install firefox webkit
sudo npx playwright install-deps   # or: sudo apt-get install libavif16
```

Then re-run `npm run smoke:browsers`.

## App defects found

None in Chromium/Firefox for this smoke matrix. No product code changes required for #26.
