# Performance lab baseline (#24)

**Recorded:** 2026-07-12 (lab date in environment: 2026-07-11–12 UTC)  
**Purpose:** Capture mobile/desktop lab metrics **before** any #25 payload/perf tuning.  
**Not field RUM / CrUX.** Lab only; production numbers vary with CDN, region, and load.

## How to re-run

```bash
# Playwright CWV-style metrics (mobile 375 + desktop 1366), 6 public routes
# Production (also updates tests/performance-baseline.json when using --write-baseline)
npm run audit:performance
npm run audit:performance:baseline   # write tests/performance-baseline.json
npm run audit:performance:check      # fail on large regressions vs baseline

# Local app
PERF_BASE_URL=http://127.0.0.1:8000 npm run audit:performance

# Lighthouse (needs global or local lighthouse + Chrome)
lighthouse https://udemyenroller.madhudadi.in/ \
  --only-categories=performance,accessibility,best-practices,seo \
  --form-factor=mobile --output=json --output=html \
  --output-path=performance-report/lighthouse/home-mobile \
  --chrome-flags="--headless --no-sandbox"
```

Artifacts:

| Path | Meaning |
|------|---------|
| `tests/performance-baseline.json` | Official regression baseline (production, Playwright audit) |
| `performance-report/performance-latest.json` | Last Playwright run (production if last run was prod) |
| `performance-report/performance-local-latest.json` | Lab run against local `:8000` |
| `performance-report/lighthouse/*.report.{json,html}` | Lighthouse snapshots |

## Thresholds used (Playwright script)

| Metric | Good | Poor |
|--------|------|------|
| LCP | ≤ 2500 ms | > 4000 ms |
| FCP | ≤ 1800 ms | > 3000 ms |
| CLS | ≤ 0.1 | > 0.25 |
| TTFB | ≤ 800 ms | > 1800 ms |

## A. Local lab (`http://127.0.0.1:8000`)

**Tool:** `tests/performance-audit.js` · **File:** `performance-report/performance-local-latest.json`

| Path | Viewport | TTFB | FCP | LCP | CLS | Transfer* | Reqs |
|------|----------|-----:|----:|----:|----:|----------:|-----:|
| `/` | mobile | 10 | 628 | 628 | 0 | ~85 KiB | 7 |
| `/` | desktop | 9 | 660 | 660 | 0 | ~85 KiB | 7 |
| `/udemycoupons` | mobile | 26 | 724 | 724 | 0 | ~94 KiB | 9 |
| `/udemycoupons` | desktop | 13 | 640 | 640 | 0 | ~94 KiB | 9 |
| `/faq` | both | ~8–30 | ~580–640 | same | 0 | ~91 KiB | 8 |
| `/about`, `/guides`, `/privacy` | both | ~8–9 | ~608–632 | same | 0 | ~91 KiB | 8 |

\*Resource timing transfer totals from the page context (not full HTML document size).

**Summary:** 12/12 LCP good · 0 CLS poor · 0 TTFB needs-improvement.

**Raw HTML document size (uncompressed GET):** home ~147 KB · coupons ~174 KB · about ~66 KB.

## B. Production lab (`https://udemyenroller.madhudadi.in`)

**Tool:** same Playwright script · **Baseline:** `tests/performance-baseline.json`  
**Generated:** 2026-07-11T20:42:18Z

| Path | Viewport | TTFB | FCP/LCP | CLS | Rating notes |
|------|----------|-----:|--------:|----:|--------------|
| `/` | mobile | 885 | 1544 | 0 | TTFB NI · LCP/CLS good |
| `/` | desktop | 946 | 1516 | 0 | TTFB NI · LCP/CLS good |
| `/udemycoupons` | mobile | 605 | 1248 | 0 | all good |
| `/udemycoupons` | desktop | 877 | 1528 | 0 | TTFB NI |
| `/faq` | mobile | 617 | 1252 | 0 | all good |
| `/faq` | desktop | 834 | 1500 | 0 | TTFB NI |
| `/about` | both | ~613–620 | ~1264–1276 | 0 | all good |
| `/guides` | mobile | 882 | 1536 | 0 | TTFB NI |
| `/guides` | desktop | 618 | 1288 | 0 | all good |
| `/privacy` | both | ~912–957 | ~1576–1604 | 0 | TTFB NI |

**Summary:** 12/12 LCP good · 0 CLS poor · **7** TTFB needs-improvement (800–1800 ms).  
**Finding:** TTFB is the main lab gap on production (edge/origin/network), not LCP/CLS under this Playwright method.

**Raw HTML (uncompressed GET):** home ~142 KB · coupons ~171 KB.

### Compare to prior baseline (2026-07-06)

Older baseline showed 2 CLS-poor viewports and 5 TTFB NI. **This refresh:** CLS poor **0**, TTFB NI **7** (lab variance + code changes). Do not treat single-run TTFB as a hard SLA.

## C. Lighthouse (production)

| Page | Form factor | Perf | Other (if collected) | Highlights |
|------|-------------|-----:|----------------------|------------|
| `/` | mobile | **94** | A11y 93 · BP 96 · SEO 100 | LCP ~2.4 s · TBT 40 ms · CLS 0.005 · ~192 KiB · TTFB ~460 ms |
| `/` | desktop | **100** | — | LCP ~0.7 s · TBT 0 · CLS 0 · ~193 KiB |
| `/udemycoupons` | mobile | **78** | — | LCP ~2.0 s · **TBT 860 ms** · CLS 0.026 · ~199 KiB |

Lighthouse mobile throttling is stricter than the Playwright script’s unthrottled local Chromium, so scores are not 1:1 with section A/B.

## Opportunities for #25 (do not implement here)

Ranked for later work only:

1. **Coupons page main-thread / TBT** (Lighthouse mobile 78) — list rendering, icons, client filters.  
2. **HTML document weight** — home ~142–147 KB, coupons ~171–174 KB uncompressed (JSON-LD, long templates).  
3. **Production TTFB** — hosting/CDN/cache, not frontend-only.  
4. Avoid blind minification that breaks CSP nonces or a11y.

## #25 applied (lab, 2026-07-12)

Implemented after this baseline was recorded. Re-measure production with Lighthouse after deploy.

### Code changes

| Change | Why |
|--------|-----|
| Coupons SSR first page **12** cards (was 24) | Cut HTML bulk |
| **No double load** on coupons: removed always-on `fetchCoupons()` + `tojson` re-render when SSR HTML exists | Main-thread / TBT |
| Compact sitewide JSON-LD (`@id` refs) | Smaller head on every page |
| Compact coupons CollectionPage + honest FAQ schema | Payload + claim accuracy |
| Move base chrome CSS → `/static/css/site.css` | Cacheable, smaller HTML |
| Drop universal `* { transition }` → scoped controls | Layout/paint thrash |

### Uncompressed HTML document size (local)

| Page | Before #25 | After #25 | Δ |
|------|-----------:|----------:|--:|
| `/` | ~147 KB | ~141 KB | **−6 KB** |
| `/udemycoupons` | ~174 KB | ~107 KB | **−67 KB (~39%)** |
| `/about` | ~66 KB | ~59 KB | **−7 KB** |

### Local Playwright LCP (mobile, unthrottled)

| Path | Before | After |
|------|-------:|------:|
| `/` | 628 ms | 580 ms |
| `/udemycoupons` | 724 ms | 616 ms |

Transfer totals can rise slightly because `site.css` is a separate request (cacheable). HTML weight is the intended win.

### Coupon SEO pages (related)

Valid free coupons get on-site detail URLs (`/udemycoupons/c/{slug}`, e.g. course name slug) listed in `sitemap.xml` so Google can crawl your domain for coupon-related queries. External Udemy URLs are **not** put in the sitemap.

### Still open (post-#25)

- Full Lucide UMD from unpkg (shared cost)  
- Production TTFB / CDN  
- Coupons Lighthouse TBT re-check after deploy  
- Field CrUX  

## Explicit non-goals of this baseline

- No field Core Web Vitals (CrUX / GA).  
- No auth dashboard perf.  
- No formal pass/fail “production is fast enough” claim.
