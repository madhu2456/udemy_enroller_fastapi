# NM-05 Consent Mode Sheet — 5-state HAR matrix (Basic vs Advanced)

**Scope:** `madhudadi.in` (portfolio), `madhudadi.in/blog`, `deals.madhudadi.in`, `udemyenroller.madhudadi.in`, `adticks.com`
**Standard:** GDPR Art. 7 + ePrivacy, IAB TCF 2.2, Google Consent Mode v2
**Tool:** [Tag Assistant](https://tagassistant.google.com/) + Chrome DevTools Network (HAR) + `Application > Storage`
**Date of this sheet:** 2026-08-30
**Status:** `G+surface` — no interactive Tag Assistant session captured this run; procedure + expected storage/payload + residual surface documented. Previous runs exported `gtm-container-export.json` only — `export JSON ≠ live container` per NM-05 blocked-G rule.

---

## 1. Consent Mode Implementation per Property

| Property | GTM Container | Consent Gate | Storage Key | Mode | Source Evidence |
|---|---|---|---|---|---|
| madhudadi.in | `GTM-XXXX` (portfolio) | `AnalyticsConsentBanner` → `madhu_analytics_consent_v1` (`localStorage`, values `granted`/`denied`/`null`) | `madhu_analytics_consent_v1` | **Basic** — `gtag('consent','default', {analytics_storage: 'denied', ad_storage: 'denied'})` on first load; GTM **not injected** until `granted` (`DeferredGTM` checks `typeof window.gtag === 'function'` only after consent update) | `madhu_portfolio/src/lib/analytics-consent.ts`, `src/components/DeferredGTM.tsx:41-42`, `AnalyticsConsentBanner.tsx` |
| madhudadi.in/blog | same as portfolio (blog platform shares domain) | `madhu_analytics_consent_v1` on `madhudadi.in` origin — blog reads same `localStorage` key (same host) | `madhu_analytics_consent_v1` | **Basic** — same gate as portfolio | `blog_platform` shares `madhudadi.in` host |
| deals.madhudadi.in | (Deals GTM) | `deals_cookie_consent` (`localStorage`, `accepted`/`declined`/`null`) + `deals-cookie-consent` event | `deals_cookie_consent` | **Basic** — `gtag('consent','update', {analytics_storage: 'granted'/'denied'})` + **GTM component returns `null` when `consent !== 'accepted'`** (`GoogleTagManager.tsx:18`) — tags blocked before grant | `Discounts/app/components/CookieConsent.tsx:15-16`, `GoogleTagManager.tsx:14-18` |
| udemyenroller.madhudadi.in | `GTM-5JHNVN6K` (enroller) | `gtm-container-export.json` — GA4 `googtag` config | (GTM container `GTM-5JHNVN6K`) | **Basic** — `gtag('consent','default', ... denied)` expected before GTM; container `googtag` tag fires GA4 `config` only after consent (verify via Tag Assistant) | `Udemy Enroller/gtm-container-export.json` (container `GTM-5JHNVN6K`, `googtag` GA4) |
| adticks.com | (Adticks GA4) | `Analytics` component — `gtag('consent','default', {analytics_storage: 'denied' even when env is granted})` | (Adticks `Analytics` inline) | **Basic (strict)** — `hardcodes analytics_storage denied even when consent env is granted (F204)` — never ships GA4 before explicit grant; `never ships GTM noscript iframe when consent env is granted` | `Adticks/src/components/Analytics.test.tsx:102-103`, `Adticks/src/components/Analytics.tsx` |

**Key distinction — Basic vs Advanced:**

- **Basic** (all five properties, as implemented): Consent Mode `default` is `denied`; **tags are not loaded** before `granted`. Network shows **no `collect` / `g/collect` pings** before Accept. After Accept, `consent` update to `granted` and tags fire.
- **Advanced** (alternative, **not** used here but documented for audit completeness): GTM **is** loaded with `denied` defaults; it sends **cookieless pings** (`gcs`, `gcd`, `consent`) even before grant, with `analytics_storage: denied`. Network shows `https://www.google-analytics.com/g/collect?gcs=...&gcd=...&npa=1` pings before grant. Storage still `denied`, but payload is restricted. **Our properties use Basic (no pings before grant)** — Tag Assistant should show `Consent denied` + `No tags fired` on default.

---

## 2. 5-State HAR Matrix (to be captured via Tag Assistant)

Record **HAR + Application > Storage screenshot** for each state, per property. Use **Chrome Guest profile** (clean storage) for `Default`.

| # | State | User Action | Expected `localStorage` | Expected `dataLayer` / `gtag('consent')` | Expected Network (HAR) | Regional Approval |
|---|---|---|---|---|---|---|
| 1 | **Default (first visit, no interaction)** | Open site in clean profile, **do not click** banner | Portfolio/Blog: `madhu_analytics_consent_v1 = null` (key absent); Deals: `deals_cookie_consent = null`; Adticks: no consent grant; Enroller: GTM container loads but `consent default denied` | `dataLayer.push({consent: {analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied'}})` on page head (before GTM) | **No** `https://www.googletagmanager.com/gtm.js` **before** consent (Basic) or GTM loads but **no** `https://www.google-analytics.com/g/collect` with `analytics_storage:1` (Advanced cookieless ping would still be `denied`). **Verify:** `Storage > Cookies` shows no `_ga`/`_gid`; `Network` shows no `collect` before banner click. Tag Assistant: `Consent: denied` | Should respect EEA/UK `consent_default` region if `region` param set; otherwise default `denied` globally |
| 2 | **Accept** | Click **Accept** / **Allow** on banner | Portfolio: `madhu_analytics_consent_v1 = "granted"`; Deals: `deals_cookie_consent = "accepted"`; Adticks: consent grant stored per `Analytics` | `gtag('consent','update', {analytics_storage: 'granted', ad_storage: 'granted', ...})` fires; `dataLayer` shows `consent_update` event | GTM `gtm.js` loads now (if Basic); subsequent `g/collect` / `ga4` `collect` fires with `gcs=G111`/`gcd=...` indicating consent granted; `_ga` cookie set (`_ga`, `_gid`); `Network` shows `200` on `collect`. Tag Assistant: `Consent: granted`, `Tags fired: GA4 Config` | Region `EEA` lists should now show granted; non-EEA same |
| 3 | **Reject** | Reload in clean profile, click **Reject** / **Decline** | Portfolio: `madhu_analytics_consent_v1 = "denied"`; Deals: `deals_cookie_consent = "declined"`; Adticks: remains `denied` | `gtag('consent','update', {analytics_storage: 'denied', ad_storage: 'denied'})` or no update (remains default `denied`) | **No** `collect` pings after Reject (Basic); if Advanced, only cookieless pings with `gcs=G100`/`npa=1`. No `_ga` cookie. Tag Assistant: `Consent: denied`, `Tags blocked` | Same as Default, but explicit `denied` update |
| 4 | **Withdrawal (revoke after Accept)** | After Accept, click **Withdraw** / **Cookie settings → Revoke** (re-open banner, click Decline) | Portfolio: `madhu_analytics_consent_v1` flips `granted` → `denied`; Deals: `accepted` → `declined` | `gtag('consent','update', {analytics_storage: 'denied'})` fires again; `dataLayer` shows second `consent_update` | No new `collect` after withdrawal; existing `_ga` should be **cleared or not sent** on next navigation (verify `Application > Cookies` `_ga` removed or `Network` shows no `_ga` cookie header). Tag Assistant: `Consent: denied (updated)` | Must work without reload if `update` is used; verify storage + payload |
| 5 | **Return Visit (persisted)** | Close tab, reopen site (same profile, no clear) | Portfolio: `madhu_analytics_consent_v1` persists (`granted` or `denied` as last set); Deals: same | On next load, `gtag('consent','default', ...)` reads **stored** value via `getConsent()` before GTM loads — `default` should be `granted` if previously Accepted, `denied` if Rejected/Withdrawn | If `granted` persisted: GTM loads immediately + `collect` fires on pageview. If `denied` persisted: no GTM/`collect` until banner re-shown (banner stays hidden because `consent !== null`). Tag Assistant shows `Consent: <persisted>` on reload. | Verify 1-day+ persistence; check `localStorage` survives navigation |

**What to capture per state (HAR + screenshots):**

1. **HAR file:** Chrome DevTools → Network → Export HAR (include `collect`, `gtm.js`, `consent` requests).
2. **Tag Assistant recording:** `https://tagassistant.google.com` → Connect → Navigate through 5 states → Export.
3. **Storage screenshot:** `Application > Local Storage` (show `madhu_analytics_consent_v1` / `deals_cookie_consent`) + `Cookies` (show `_ga` presence/absence).
4. **Payload snippet:** Copy one `g/collect` request URL and highlight `gcs=`, `gcd=`, `npa=` params; copy `dataLayer` `consent` push from `Console`.
5. **Region check:** Tag Assistant → `Consent` → `Region` (if `region: ['EEA']` configured).

---

## 3. Current Verification Status — `G+surface`

**This run:** No interactive Tag Assistant session executed — `G+surface` for NM-05 per blocked-G rule (`No interactive session → G; export JSON ≠ live container`).

- **Residual surface:**
  - **All five properties** need a **live HAR per state** (5 × 5 = 25 HARs, or at least **one property’s full 5-state HAR as sample + screenshot per other property**).
  - **No `HAR/screenshot` on disk** — `docs/ops/` contains this sheet only; no `*.har` files.
  - **GTM container `GTM-5JHNVN6K` export** exists on disk (`Udemy Enroller/gtm-container-export.json`) but **is not a live network proof** — Tag Assistant must still show `consent default denied` before grant.
  - **Regional approval** (`region: ['EEA']` + `ad_user_data`/`ad_personalization`) not verified live.

**To attain `attempted-clean`:**

```bash
# 1. Open Chrome Guest → tagassistant.google.com → Connect → https://madhudadi.in
# 2. Step through 5 states above, export HAR + screenshot per state
# 3. Save to docs/ops/har/madhudadi-in-{default,accept,reject,withdrawal,return}.har
# 4. Repeat for deals, enroller (GTM-5JHNVN6K), adticks
```

**Stored HARs (when captured):**

```bash
$ ls -lh docs/ops/har/
# (to be populated after Tag Assistant session)
$ cat docs/ops/har/madhudadi-in-default.har | jq '.log.entries[] | select(.request.url | contains("collect")) | .request.url' | head
```

---

## 4. Basic vs Advanced — How to Tell from HAR

| Signal | Basic (our impl) | Advanced (not used) |
|---|---|---|
| `gtm.js` before consent | **Not loaded** | Loaded (with `denied` defaults) |
| `g/collect` before Accept | **0 requests** | 1+ cookieless pings (`gcs=G100`, `npa=1`, no `_ga`) |
| `Storage: _ga` before Accept | **Absent** | Absent (cookieless) but `FPLC`/`_gcl_au` may still be absent |
| `gcs` param | `G111` only after `granted` | `G100` (denied) before, `G111` after |
| Tag Assistant badge | `Consent denied — No tags fired` | `Consent denied — Tags fired (cookieless)` |

Our code asserts **Basic** (no tags before grant) — HAR should confirm `0 collect` on Default/ Reject / Withdrawal.

---

## 5. References

- Google Consent Mode v2: https://developers.google.com/tag-platform/security/guides/consent
- Tag Assistant: https://tagassistant.google.com/
- IAB TCF 2.2: https://iabeurope.eu/transparency-consent-framework-policies/
- Portfolio consent lib: `madhu_portfolio/src/lib/analytics-consent.ts`
- Deals consent: `Discounts/app/components/CookieConsent.tsx`
- Enroller GTM: `Udemy Enroller/gtm-container-export.json` (`GTM-5JHNVN6K`)
- Adticks strict: `Adticks/src/components/Analytics.test.tsx` (F204: `analytics_storage denied even when env granted`)

---
*This sheet is procedure + code evidence + G+surface residual; it is not a live HAR. Run Tag Assistant to close NM-05.*
