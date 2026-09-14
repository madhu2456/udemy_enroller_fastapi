# Coupon aggregator robots posture (F252)

Scraping posture for the coupon aggregator sources, effective 2026-08-16.

## Behavior

- Before the first fetch against a target host, the scraper fetches and caches
  that host's `robots.txt` (per-host cache, **24 h TTL**,
  `app/services/robots_gate.py`).
- `Disallow` rules are honored for the scraper's user-agent family (desktop
  Chrome — the same family the HTTP client randomizes between).
- The gate is wired into each scraper's **primary listing fetch** via
  `Scraper._http_get` (`app/services/scraper.py`). A disallowed host yields no
  data from that source; same-host detail fetches only run after a successful
  listing fetch, so a disallowed host is fully skipped.
- **Fail-open by design:** if the `robots.txt` fetch fails, times out, returns
  a non-200/5xx, or loops redirects (`ROBOTS_MAX_REDIRECTS = 3`), the fetch is
  ALLOWED. Rationale: a robots outage must never take every coupon source
  offline (availability > strictness). This tradeoff is deliberate and
  documented in `app/services/robots_gate.py`.
- The robots.txt fetch itself uses plain httpx (no CloudScraper) with a 10 s
  timeout and a single attempt.

## Policy notes for operators

- Sites that block automated Chrome UAs in `robots.txt` will stop contributing
  coupons; this is intended robots compliance, not a scraper defect.
- If a source becomes unreachable, check whether its `robots.txt` changed
  before debugging the scraper.
- The gate does not apply to Udemy enrollment traffic (the user's own session
  flow) — only to coupon aggregator hosts.

## Courson `/claim/`

Courson (`courson.xyz`) `robots.txt` includes `Disallow: /claim/` (verified
`User-agent: *`). Listing fetches go through `Scraper._http_get`, which honors
that Disallow (F252; fail-open only if the robots fetch itself fails). The
Courson scraper never requests `/claim/` paths.
