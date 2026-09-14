# Fix #11 — www subdomains + contact/terms pages (ops)

Runbook for the 2026-08-02 Fix #11 rollout: `www.deals.madhudadi.in` and
`www.udemyenroller.madhudadi.in` stopped resolving (NXDOMAIN), and both sites
gained `/contact` pages (plus `/terms` on Udemy Enroller). This runbook covers
the DNS, nginx, and Cloudflare SSL-mode work — the two sites require
**opposite** Cloudflare SSL modes, so read §2 before touching anything.

## 1. What changed and why

### Root cause

Neither Cloudflare zone had a `www` record. `www.deals.madhudadi.in` and
`www.udemyenroller.madhudadi.in` returned **NXDOMAIN** — a browser DNS error
for any user who typed or clicked the `www` host. The code and origin servers
were already capable of serving both hostnames; only the DNS was missing.

### Fix (code)

**Deals** (managed in `Discounts/`):

- `nginx/deals.conf` — the HTTP block now has
  `server_name __DOMAIN__ www.__DOMAIN__;` (both names share the port-80 block).
- `nginx/deals.ssl.conf` — three blocks:
  - Block 1 (port 80 → 443): `server_name __DOMAIN__ www.__DOMAIN__;`,
    ACME challenge location, then `return 301 https://$host$request_uri;`.
  - Apex 443 block: `server_name __DOMAIN__;` — the app vhost.
  - **New dedicated `www` 443 block** with the certbot snippets and a
    hardcoded `return 301 https://__DOMAIN__$request_uri;` — never `$host`
    (with `$host` the redirect target stays `www`, so the browser loops
    www → www forever).
- Templates are installed on every deploy by `install_nginx_from_repo`
  (deploy.sh:139-189): global `sed` substitutes `__DOMAIN__` / `__APP_PORT__`,
  and the `ssl_dhparam` / `options-ssl-nginx.conf` lines are dropped when the
  files are missing so `nginx -t` passes on a fresh box. The **SSL template is
  only selected when `/etc/letsencrypt/live/${DOMAIN}/fullchain.pem` exists**
  (deploy.sh:155) — the `www` 443 block references the apex cert paths, so the
  deploy succeeds only if an apex cert is already present.
- `app/contact/page.tsx` — new `/contact` (mailto `hello@madhudadi.in`),
  linked from the footer `Legal` section. **Not in the sitemap** — legal pages
  are omitted by convention (`app/sitemap.ts` static set is `/`, `/deals`,
  `/categories` only).
- `certbot` is **echo-only** in deploy.sh:380 — it prints the command as a
  hint and never runs it. The multi-SAN cert run is manual (§3).

**Udemy Enroller** (this repo):

- New `/contact` (`app/routers/seo.py` + `app/templates/pages/contact.html`):
  mailto `hello@madhudadi.in` plus GitHub Issues for bug reports and feature
  requests. **Intentionally static** — a form would need a backend route +
  CSRF (CSP is `form-action 'self'`, main.py:455) + rate limiting; documented
  out of scope so nobody "improves" it later (§6).
- New `/terms` (`app/routers/seo.py` + `app/templates/pages/terms.html`):
  formalizes the README disclaimers.
- Both pages are in the **public cache set** (main.py:353-354 —
  `public, max-age=120, s-maxage=300, stale-while-revalidate=600`), have
  footer links (base.html), and are in the sitemap at **0.30/monthly**
  (`app/services/public_deals_export.py:470-471`).
- **No nginx change on the UE box**: `scripts/deploy.sh:58-75` generates a
  port-80-only catch-all (`server_name _;`) — no 443, no origin certs. Any
  hostname already proxies to the app, and the canonical is hardcoded apex
  (base.html:48-51), so `www` served through the catch-all carries apex
  canonicals — no duplicate content.

### Why Cloudflare modes differ (§2 is critical)

- Deals origin **has** Let's Encrypt certs and listens on 443 → Cloudflare
  mode **Full or Full (strict)**.
- UE origin is **HTTP-only** (no 443 listener) → Cloudflare mode **must stay
  Flexible**.

---

## 2. Cloudflare SSL mode table (CRITICAL)

| Zone | Origin TLS | Required CF SSL mode | Wrong choice → failure |
|---|---|---|---|
| `deals.madhudadi.in` | LE certs on origin 443 (apex + www SAN after §3) | **Full** or **Full (strict)** — verify current zone setting, don't assume | **Flexible** → CF reaches origin 80 → nginx `return 301 https://$host…` → CF follows back to origin 80 → **redirect loop** |
| `udemyenroller.madhudadi.in` | none — origin nginx is port-80-only (`server_name _;`, scripts/deploy.sh:58-75) | **Flexible** (edge TLS → origin HTTP) — must never change | **Full / Full (strict)** → CF tries origin 443 → nothing listening → **502/526 Cloudflare error** |

**The two sites require opposite Cloudflare SSL modes.** A change meant for
one zone must never be applied to the other. Do not "fix" UE's mode to match
Deals — nothing on the UE origin listens on 443.

HSTS is already sent by both apps
(`max-age=63072000; includeSubDomains; preload` — Deals
`next.config.ts`, UE main.py:429-430), so once `www` resolves, browsers force
HTTPS for it with no further configuration.

---

## 3. Rollout order (DNS → deploy → certbot → verify)

Do not skip the order: grey-cloud or missing CNAMEs break the edge-TLS
condition, and certbot must run after the deploy (the new `www` 443 block must
be live before the cert is issued for it).

### 3.1 DNS — add the CNAMEs in Cloudflare (both zones)

| Zone | Type | Name | Target | Proxy |
|---|---|---|---|---|
| `deals.madhudadi.in` | CNAME | `www` | `deals.madhudadi.in` | **Proxied (orange cloud)** |
| `udemyenroller.madhudadi.in` | CNAME | `www` | `udemyenroller.madhudadi.in` | **Proxied (orange cloud)** |

**Proxied is mandatory.** Grey-cloud (DNS only) bypasses Cloudflare: on Deals
the browser hits origin 80 and the `https://$host` redirect loops; on UE the
browser gets plain HTTP (and HSTS/preload then forces HTTPS against a
non-listening origin 443 → connection refused).

### 3.2 Deploy the code

Push and let the deploy pipelines run:

- **Deals** — `install_nginx_from_repo` (deploy.sh:139-189) installs the
  templates. Because `/etc/letsencrypt/live/deals.madhudadi.in/fullchain.pem`
  already exists, the SSL template is selected, the `www` 443 block references
  the existing apex cert paths, and `nginx -t` passes.
- **UE** — normal deploy; nginx config is unchanged (catch-all).

### 3.3 Certbot — multi-SAN for the www name (Deals only)

deploy.sh:380 only **echoes** the command — run it manually:

```bash
certbot --nginx -d deals.madhudadi.in -d www.deals.madhudadi.in
```

Then verify the certificate covers both names — a `www`-less cert fails with
**526** under Full (strict):

```bash
certbot certificates
# Domains: deals.madhudadi.in, www.deals.madhudadi.in  ← both must be listed
```

**UE: no certbot** — Flexible mode terminates TLS at the Cloudflare edge; the
origin stays HTTP.

### 3.4 Verify

Proceed to §4.

---

## 4. Verify

```bash
# Deals — www must 301 to apex over HTTPS (never 200, never 526)
curl -I https://www.deals.madhudadi.in
# expect: HTTP/2 301  Location: https://deals.madhudadi.in/...

# UE — www serves through the catch-all with apex canonical
curl -I https://www.udemyenroller.madhudadi.in/
# expect: 200; HTML canonical points at the apex

# Contact/terms pages return 200 on both sites
curl -s -o /dev/null -w "%{http_code}\n" https://deals.madhudadi.in/contact
curl -s -o /dev/null -w "%{http_code}\n" https://udemyenroller.madhudadi.in/contact
curl -s -o /dev/null -w "%{http_code}\n" https://udemyenroller.madhudadi.in/terms

# UE canonical is hardcoded apex (base.html:48-51)
curl -s https://udemyenroller.madhudadi.in/contact | grep -o 'rel="canonical" href="[^"]*"'

# UE /contact is in the public cache set → Cache-Control present
curl -sI https://udemyenroller.madhudadi.in/contact | grep -i cache-control
# expect: public, max-age=120, s-maxage=300, stale-while-revalidate=600

# On the Deals box — confirm no default_server surprise
nginx -T | grep -E "server_name|default_server"

# On the Deals box — the whole SSL template depends on the apex cert existing
ls /etc/letsencrypt/live/deals.madhudadi.in/
# expect: fullchain.pem privkey.pem cert.pem chain.pem
```

Known and accepted: 404s under `/contact//terms` paths get **no**
Cache-Control header (the UE cache middleware matches exact paths only,
main.py) → Cloudflare heuristic caching applies. Conscious choice (§6).

---

## 5. Rollback

Order matters — kill traffic first, then revert code:

1. **Remove the `www` CNAMEs in Cloudflare** (both zones). Traffic to `www`
   stops immediately (back to NXDOMAIN) — this is the instant rollback
   regardless of origin state.
2. **`git revert` the code** in both repos:
   - Deals: the next deploy re-installs the reverted templates (with the
     original single-name config). The apex cert keeps the now-unused `www`
     SAN — harmless; it expires on the normal renewal schedule.
   - UE: revert the pages/routes/sitemap/cache-set changes. The `docs/ops/`
     `.gitignore` rule lives in the same revert — removing it makes
     `docs/ops/www-and-contact-fix.md` untracked again; `rm -rf docs/ops` to
     clean up. Until then the file is ignored and survives `git clean -fd`.

---

## 6. Documented decisions

| Decision | Rule |
|---|---|
| Opposite Cloudflare SSL modes | Deals = Full/Full(strict) (origin 443 + LE certs); UE = Flexible forever (origin is a port-80-only catch-all; nothing listens on 443) |
| Hardcoded-apex redirect | `www` 443 block uses `return 301 https://__DOMAIN__$request_uri;` — never `$host` (www → www redirect loop) |
| Apex-first canonicalization | Deals: 301 at nginx, before the app; UE: hardcoded apex canonical in base.html:48-51 — the catch-all proxies `www` with apex canonicals, no duplicate content |
| UE catch-all without redirect | UE origin accepts any Host (`server_name _;`) and does not redirect; canonicalization only. Edge (Cloudflare CNAME + HSTS preload) handles the redirect behavior |
| Contact pages static | UE `/contact` is mailto-only by design; a form needs a backend route + CSRF (CSP `form-action 'self'`, main.py:455) + rate limiting — out of scope, do not "improve" it |
| Sitemap asymmetry | Deals omits `/contact` and all legal pages (static set = `/`, `/deals`, `/categories`); UE includes `/contact` + `/terms` at 0.30/monthly (public_deals_export.py:470-471) |
| 404 heuristic caching | 404s under `/contact//terms` get no Cache-Control (exact-path cache set) → Cloudflare heuristic caching — conscious, accepted |
| Performance baseline untouched | Existing cache sets unchanged; only `/contact` + `/terms` added to the UE public cache set (main.py:353-354) |

---

## 7. Future guidance

- **Any new subdomain** follows this pattern: CNAME → apex, **Proxied**;
  deploy the code (add the name to the nginx templates with a hardcoded-apex
  redirect if it should redirect, or rely on the UE catch-all + apex
  canonicals); re-run `certbot --nginx -d <apex> -d www.<apex>` if origin TLS
  is in play; then verify per §4.
- **Deals cert renewal** must keep the `www` SAN — if `certbot certificates`
  ever shows only the apex name, renew with `-d deals.madhudadi.in -d
  www.deals.madhudadi.in` or Full (strict) serves **526** for `www`.
- **UE Cloudflare mode must stay Flexible.** Any Full/Full-strict change on
  the UE zone breaks the site (502/526 — no origin 443). Record this in the
  Cloudflare zone notes so future operators don't "align" it with Deals.
- **Contact page stays static** — see the decision table; any form work needs
  a backend route + CSRF + rate limiting and is a separate project.
- **Ops runbooks live in `docs/ops/`**, which is gitignored so runbooks
  survive `git clean -fd` without `-x` (they are not committed; keep them
  local to the server checkout).
- The Cloudflare edge-rule backstop (if origin config can't be trusted):
  `www.deals.madhudadi.in/* → 301 https://deals.madhudadi.in/$1`.
