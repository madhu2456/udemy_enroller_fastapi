# Responsive viewport matrix (#27)

**Purpose:** Catch horizontal overflow and missing critical controls from 320px to 1920px.  
**Not** pixel-perfect visual QA or device lab testing.

## How to run

```bash
BASE_URL=http://127.0.0.1:8000 SMOKE_TOKEN='<session_id>' npm run smoke:viewports
# or
node tests/viewport-smoke.js
```

Widths: **320, 375, 768, 1024, 1366, 1920**.

Pages:

- Public: `/`, `/about`, `/faq`, `/guides`, `/privacy`, `/udemycoupons`
- Auth (needs `SMOKE_TOKEN`): `/dashboard`, `/settings`, `/history`

Checks per cell: HTTP 200, document horizontal overflow ≤1px, visible `h1` / main, route-specific controls (`#start-btn`, Save Settings, coupon search).

## Lab result (2026-07-12, local Chromium)

After fixes: **0 failures** across 6×9 = 54 page×viewport checks.

### Issues found and fixed

| Viewport | Route | Issue | Fix |
|----------|-------|--------|-----|
| 320 / 375 | `/guides` | Flex steps + code blocks expanded past viewport (`min-width: auto`) | `min-w-0` on step flex children; `max-w-full` on `<pre>`; tighter mobile padding |
| 320 / 375 | `/settings` | Header Reset/Save row wider than viewport | Stack header (`flex-col` → `sm:flex-row`); full-width button group on small screens |

### Intentional patterns (not failures)

- Header `#nav-links` uses **horizontal scroll** for many links on narrow screens (contained with `overflow-x-auto` + `min-w-0`).

## Artifacts

- `tests/viewport-smoke-summary.json`
- `performance-report/viewport-smoke-latest.json` (may be gitignored under `performance-report/`)
