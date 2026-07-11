# SEO residual checklist

What is fixed in code vs what still needs ops, content, or legal outside the repo.

Last updated: 2026-07-12

## Fixed in code (this residual pass)

| Area | Status | Notes |
|------|--------|--------|
| Claim drift (always-on / continuous / guaranteed auto-enroll) | Done | Softened FAQ schema+body, about, login, README, base banner, guides schema, llms “hourly” line |
| Deal page uniqueness | Done | Course-specific meta, how-to steps, category context, FAQ JSON-LD, LimitedAvailability offer |
| Sitemap quality filter | Done | Title min length, valid+code+slug, 30-day freshness when `last_checked_at` present |
| Hub Breadcrumb + CollectionPage | Done | Visible breadcrumb + JSON-LD on `/udemycoupons` |
| Internal links | Done | Footer link to `/guides/free-udemy-coupons`; deal pages link hub/category/guide |
| Auth surfaces noindex | Done earlier | `/dashboard`, `/settings`, `/history`, 404 |

## Still residual (not fully fixable from app code alone)

### Google Search Console / ops

- [ ] Submit or re-inspect `https://udemyenroller.madhudadi.in/sitemap.xml` after deploy
- [ ] Request indexing for pillar `/guides/free-udemy-coupons` and hub `/udemycoupons`
- [ ] Monitor Coverage / Page indexing for thin or soft-404 deal URLs after quality filter ships
- [ ] Confirm live `Cache-Control` on sitemap is 6h (`max-age=21600`) in production headers

### Content / product

- [ ] Category hubs with very few deals may still look thin — optional min-count noindex later
- [ ] External backlinks and portfolio case-study links (off-site)
- [ ] Keep public copy aligned if product behavior changes (scheduler, TTL, etc.)

### Legal / brand

- [ ] External counsel review of Udemy trademark use and automated-access posture (`docs/legal-counsel-review.md`)
- [ ] Residual ToS risk of CloudScraper/Playwright enrollment — owner decision to keep; not a code “fix”

### Measurement

- [ ] GTM/GA4 only after consent — verify events in production
- [ ] Optional: Search Console performance for “free udemy coupons” style queries over 4–8 weeks

## Quick verify after deploy

```bash
# Sitemap is on-site only (no udemy.com loc)
curl -sS https://udemyenroller.madhudadi.in/sitemap.xml | grep -c udemy.com || true

# Sample deal + hub
curl -sI https://udemyenroller.madhudadi.in/udemycoupons | head -5
curl -sI https://udemyenroller.madhudadi.in/guides/free-udemy-coupons | head -5

# Soft claims smoke (should not find always-on continuous auto language)
curl -sS https://udemyenroller.madhudadi.in/faq | grep -i 'continuously monitors' || echo 'ok'
```

## Related docs

- `docs/madhudadi-in-seo-aeo-geo-improvements.md` — broader SEO/AEO/GEO notes
- `docs/legal-counsel-review.md` — legal residual pack
- `docs/browser-smoke.md` / `docs/viewport-smoke.md` — UI smoke
