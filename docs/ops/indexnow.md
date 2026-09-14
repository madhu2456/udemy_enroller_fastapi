# IndexNow ping + verification key (SEO)

**Status:** Implemented (env-gated, OFF by default). Mirrors the portfolio
reference implementation (`madhud_portfolio` `src/app/[key].txt/route.ts` +
`src/app/api/indexnow/route.ts`, pattern F207), adapted to FastAPI/Python.

**Date:** 2026-09-04

## What it is

[IndexNow](https://www.indexnow.org/) lets a site tell participating search
engines (Bing, Yandex, and others) that URLs changed, for immediate
re-crawling. Two pieces:

1. **Ownership verification key file** — engines fetch
   `https://udemyenroller.madhudadi.in/<key>.txt` and compare it with the key
   submitted in pings.
2. **Ping** — a `POST {host, key, urlList}` to `https://api.indexnow.org/IndexNow`
   (the same endpoint the portfolio uses) listing changed URLs.

## Configuration

`INDEXNOW_KEY` — the 32-hex verification key (generate in
[Bing Webmaster Tools → IndexNow](https://www.bing.com/webmasters/indexnow)):
set it in the host `.env` (never in the repo — `INDEXNOW_KEY` is a per-host
credential; committing it would require history scrub on rotation, exactly the
situation documented for the portfolio in its `docs/ops/indexnow.md`).

> **Why not `.env.example`:** repo tool policy blocks edits to `*.env.*`
> files (see the same note on `docker-compose.yml` → `COUPON_CHECKER_*`).
> This document is the reference home, following `ALERT_WEBHOOK_URL`'s
> documentation pattern (`docs/ops/alerting.md`).

```bash
# host .env (owner-only)
INDEXNOW_KEY=4987000e306144ec8609ede9a23f9b4b   # <- your own 32-hex key
```

**Default behavior: OFF.** With `INDEXNOW_KEY` unset (or malformed), the key
route 404s and every ping is a no-op — no network, no behavior change. This
matches the env-gating posture of `GTM_CONTAINER_ID` and `ALERT_WEBHOOK_URL`.

## Wiring

| Piece | Location |
| :--- | :--- |
| Service (key gate, payload builder, ping) | `app/services/indexnow.py` |
| Verification route `GET /{key}.txt` | `app/routers/seo.py` (fail-closed 404) |
| Ping trigger | `app/services/public_deals_export.py` → `save_public_deals(refresh_sitemap=True)` |

**Trigger site:** the catalog *publish* path. `save_public_deals` with
`refresh_sitemap=True` runs at the end of every coupon-checker cycle
(`scripts/coupon_checker.py` → Docker `coupon-checker` service, every 2 h)
and after every enrollment-run merge (`enrollment_manager.py`
`_merge_run_into_public_catalog`). Mid-run crash-safety snapshots deliberately
use `refresh_sitemap=False` and do **not** ping (only a finished, atomically
published catalog is worth re-crawling).

**What gets pinged:** the two catalog hubs whose content is the deal list
(`/udemycoupons`, `/`) plus every exported deal detail page
(`/udemycoupons/c/{slug}`, bounded by the export's 500-deal cap) — capped at
1000 URLs per submission (IndexNow's protocol maximum is 10,000).

## Guarantees / limitations

- **Fire-and-forget:** 5-second timeout, transport failures and non-2xx
  responses logged at WARNING and never raised — an IndexNow outage can never
  break the export pipeline.
- **Fail-closed key route:** unset key, malformed (non-32-hex) request, or
  request≠configured → 404. Rotation is owner-ops: update the env var and the
  new key serves immediately (read at request time, zero code change).
- **Key never logged; never committed.** Pings carry only canonical-origin
  URLs (same-host enforced).
- Ping success ≠ indexing; IndexNow is a hint, not a guarantee.

## Verification

```bash
python -m pytest tests/test_indexnow.py tests/test_public_deals_export.py -q
```

Tests use mocked HTTP transports (no live pings) and the isolated test app.
