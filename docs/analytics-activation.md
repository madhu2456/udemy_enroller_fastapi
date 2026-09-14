# Analytics Activation Checklist (F008 — owner-operated)

**Date drafted:** 2026-09-04
**Scope:** `window.ueEvent` dataLayer events wired in `app/templates/components/base.html`, `app/static/js/app.js`, and page templates. All events are client-side buffered `dataLayer.push({event, ...params})` calls — **zero new network calls, pixels, or loaders**. GTM still loads only after consent (`cookie_consent === 'accepted'`, existing pattern); pre-consent events stay in the buffer.

## 0. Env vars gating the loaders (already wired — no change needed)

| Env var | Read at | Effect |
| --- | --- | --- |
| `GTM_CONTAINER_ID` | `config/settings.py:53` → `main.py:166` (`app.state.gtm_container_id`) | Renders the consent-gated GTM loader (`window._loadGTM`) in `base.html` |
| `GA4_MEASUREMENT_ID` | `config/settings.py:56` → `main.py:167` (`app.state.ga4_measurement_id`) | Renders the direct GA4 loader only when `GTM_CONTAINER_ID` is empty |
| (both empty) | — | `ueEvent` helper, consent block, and banner are not rendered at all → zero analytics |

Set them in `.env` (see `.env.example:105-110`) and restart the server.

## 1. GTM container triggers to create (per event)

The current container (`gtm-container-export.json`, `GTM-5JHNVN6K`) has **one tag** (GA4 - Config on the built-in Initialization trigger, id `2147479573`) and **zero custom triggers** (`"trigger": []`). Every event below needs a **Custom Event trigger** in the container UI (Triggers → New → Custom Event, event name = the name below), plus a GA4 Event tag firing on it.

| Event name | Fired from (site) | Params | Container trigger needed? | Suggested trigger type |
| --- | --- | --- | --- | --- |
| `page_view` | GTM native (GA4 Config tag already sends it) | — | No (already firing) | — |
| `consent_granted` | Cookie banner **Accept** (base.html) | `banner` | **Yes** | Custom Event `consent_granted` |
| `consent_denied` | Cookie banner **Decline** (base.html) | `banner` | **Yes** | Custom Event `consent_denied` |
| `nav_click` | Header/mobile/footer nav links (base.html) | `nav_path` | **Yes** | Custom Event `nav_click` |
| `outbound_click` | Any `a[target="_blank"]` click (app.js) | `link_url`, `link_text` | **Yes** | Custom Event `outbound_click` |
| `cta_click` | `#get-started-btn`, `[href="#connect"]` (app.js) | `cta_id`, `cta_text` | **Yes** | Custom Event `cta_click` |
| `coupon_click` | Any udemy.com link on `/udemycoupons` grid (public_deals.html) | `link_url`, `link_text` | **Yes** | Custom Event `coupon_click` |
| `course_enroll_click` | "Open on Udemy" CTA (coupon_detail.html) | `course_slug` | **Yes** | Custom Event `course_enroll_click` |
| `coupon_code_copy` | Copy button (public_deals grid + coupon_detail) | `source` (`grid`/`detail`) | **Yes** | Custom Event `coupon_code_copy` |
| `search_filter_use` | Search box / category / status / clear-filters (public_deals.html) | `filter_type` (`search`/`category`/`status`/`clear_all`) | **Yes** | Custom Event `search_filter_use` |
| `page_change` | Prev/Next pagination buttons (public_deals.html) | `direction`, `page` | **Yes** | Custom Event `page_change` |
| `enrollment_start` | Successful "Start Enrollment" (dashboard.html, via `trackEvent`) | — | **Yes** | Custom Event `enrollment_start` |
| `enrollment_stop` | Successful "Stop Enrollment" (dashboard.html, via `trackEvent`) | — | **Yes** | Custom Event `enrollment_stop` |
| `enroll_result` | Start-enrollment outcome (dashboard.html) | `outcome` (`start_success`/`start_fail`/`start_error`) | **Yes** | Custom Event `enroll_result` |
| `login` | Email/cookie login success (login.html, via `trackEvent`) | `method` | **Yes** | Custom Event `login` |
| `file_download` | CSV export links (app.js) | `file_name`, `file_extension` | **Yes** | Custom Event `file_download` |
| `scroll_depth` | 25/50/75/100% scroll marks (app.js) | `percent_scrolled` | **Yes** | Custom Event `scroll_depth` |
| `error_view` | 404 page render (404.html) | `error_code` | **Yes** | Custom Event `error_view` |

Notes:
- `outbound_click` fires for external opens (udemy.com, GitHub, blog) — kept as the single external-navigation event to avoid double-firing; no separate `external_open` event was added.
- `enroll_result` covers engine start outcomes only; per-course enroll success/fail happens server-side inside the automation run and is intentionally NOT pushed (would require server-side emission; deferred to owner decision).
- `file_download`: before wiring it, disable GA4 **Enhanced Measurement → File downloads** (GA4 Admin → Data streams → web stream → Configure tag settings → Enhanced measurement → uncheck "File downloads"). Otherwise CSV exports double-count — our `file_download` event is the authoritative one.

## 2. GA4 registration (Admin → Custom definitions)

For each event you want as a **conversion** (suggested: `course_enroll_click`, `coupon_click`, `enrollment_start`, `cta_click`): Admin → Events → toggle **Mark as conversion** once it appears (or create via Admin → Conversions with the exact name).
Custom **event parameters/properties** to register (Admin → Custom definitions → Event) so they appear in reports:
`nav_path`, `filter_type`, `direction`, `page`, `outcome`, `source`, `course_slug`, `banner`, `error_code`, `cta_id`, `link_url`, `link_text`, `file_name`, `percent_scrolled`.

## 3. Verification via Tag Assistant (preview steps)

1. Tag Assistant → enter `https://udemyenroller.madhudadi.in` → **Connect**.
2. Before consent: **Consent Overview** tab shows `analytics_storage: denied`; **Tags fired = GA4 Config blocked / not fired**; Network tab shows no `collect` request. dataLayer shows buffered `event: ...` entries only.
3. Click **Accept** on the banner → Tag Assistant: `consent_granted` event fires, GTM loads (`gtm.js` request visible), GA4 Config fires `page_view`, `_ga` cookie set.
4. Exercise each flow: navigate (nav_click) → open `/udemycoupons`, use search/filters (search_filter_use) → paginate (page_change) → copy a code (coupon_code_copy) → open a detail page → click "Open on Udemy" (course_enroll_click + outbound_click) → dashboard start/stop (enrollment_start/stop, enroll_result) → visit a bogus URL (error_view).
5. Confirm each appears in Tag Assistant **Data Layer** tab with the exact event name, then in GA4 **Realtime** within ~30s of consent-granted traffic.
6. Decline path: clear site data → Decline → `consent_denied` buffered, no `gtm.js` request, banner returns after 30 days.

## 4. Consent interplay

- Events pushed before consent **buffer in `window.dataLayer`** and are replayed to GTM when it loads after Accept — nothing is discarded.
- GTM loads **only** on Accept (existing `_loadGTM` gate; unchanged).
- All parameters are coarse (paths, slugs, outcomes) — no link text with PII beyond the existing `link_text` truncation, no search queries (`nav_path` strips query strings).

*Activation is an owner operation: creating container triggers, GA4 registrations, and the live Tag Assistant session are all done in the Google Tag Manager / GA4 UIs, not in this repo.*
