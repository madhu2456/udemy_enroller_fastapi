# Operational Runbook: Edge Headers Hygiene & Telemetry

## 1. Overview & Context

This runbook documents operational procedures for maintaining HTTP security headers at the edge (Cloudflare / Host Nginx) and explains client-side telemetry behavior for `udemyenroller.madhudadi.in`.

---

## 2. Permissions-Policy Header Hygiene

### Problem Statement
Browser consoles (Chromium, Firefox, Safari, Brave) may report:
```
Error with Permissions-Policy header: Unrecognized feature: 'attribution-reporting'.
Error with Permissions-Policy header: Unrecognized feature: 'private-aggregation'.
Error with Permissions-Policy header: Unrecognized feature: 'private-state-token-issuance'.
Error with Permissions-Policy header: Unrecognized feature: 'private-state-token-redemption'.
Error with Permissions-Policy header: Unrecognized feature: 'join-ad-interest-group'.
Error with Permissions-Policy header: Unrecognized feature: 'run-ad-auction'.
Error with Permissions-Policy header: Unrecognized feature: 'browsing-topics'.
```

### Root Cause
The FastAPI origin server in `main.py` emits only clean W3C-standard directives:
```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```
The 7 reported features belong to Google's proprietary Privacy Sandbox proposal. They are typically injected upstream at the **Cloudflare Transform Rules** layer or in a host-level **Nginx reverse proxy** configuration intended to opt out of ad-tech tracking. When browsers with Privacy Sandbox disabled, or non-Chromium browsers (Firefox, Safari), or privacy-focused browsers (Brave) encounter these non-standard directives, they emit console errors.

### Resolution Steps

#### Option A: In Cloudflare Dashboard (Recommended)
1. Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com).
2. Select the zone/domain for `madhudadi.in`.
3. In the left navigation, go to **Rules** -> **Transform Rules**.
4. Select the **Modify Response Header** tab.
5. Look for any rule modifying `Permissions-Policy`.
6. Either:
   - **Delete the rule**: Allow the origin server's clean `Permissions-Policy` header to pass through untouched.
   - **Edit the rule**: Remove the 7 Privacy Sandbox tokens (`attribution-reporting`, `private-aggregation`, `private-state-token-issuance`, `private-state-token-redemption`, `join-ad-interest-group`, `run-ad-auction`, `browsing-topics`), retaining only standard directives (e.g., `camera=(), microphone=(), geolocation=()`).
7. Save and deploy the rule.

#### Option B: In Host Nginx Configuration
If an Nginx reverse proxy sits between Cloudflare and the Docker container:
1. Inspect the site configuration:
   ```bash
   grep -rn "Permissions-Policy" /etc/nginx/
   ```
2. If `add_header Permissions-Policy "...";` exists with Privacy Sandbox tokens, update it to match origin parity:
   ```nginx
   add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
   ```
   Or remove the directive to allow the FastAPI application's header to pass through.
3. Reload Nginx:
   ```bash
   nginx -t && systemctl reload nginx
   ```

---

## 3. Cloudflare Insights Beacon (`net::ERR_BLOCKED_BY_CLIENT`)

### Observation
```
GET https://static.cloudflareinsights.com/beacon.min.js/... net::ERR_BLOCKED_BY_CLIENT
```

### Explanation
- **Source**: Injected dynamically at the Cloudflare edge proxy when **Cloudflare Web Analytics** or **Browser Insights** is enabled for the zone.
- **Root Cause**: Client-side content blockers (uBlock Origin, Brave Shields, AdBlock Plus, Privacy Badger, Pi-hole) contain the standard EasyPrivacy filter rule:
  ```
  ||static.cloudflareinsights.com/beacon.min.js^
  ```
- **Impact**: **Zero impact** on site functionality, account connections, scraping, or coupon enrollments. The beacon is purely passive, privacy-preserving performance telemetry.

### Operational Options
- **Leave as-is (Recommended)**: This is standard industry behavior on sites behind Cloudflare. No user-facing functionality is impaired.
- **Disable if pristine console is required**:
  1. In Cloudflare Dashboard, go to **Analytics & Logs** -> **Web Analytics**.
  2. Select Manage Site -> Disable Web Analytics (or disable automatic JavaScript snippet injection).

---

## 4. Mobile Web App Capabilities Meta Tags

### Modern Standard
In `app/templates/components/base.html`, both modern and legacy capability meta tags are maintained:
```html
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="default" />
<meta name="apple-mobile-web-app-title" content="Udemy Enroller" />
```
- `<meta name="mobile-web-app-capable" content="yes" />`: Satisfies modern Chromium / Blink and Web App Manifest specifications, eliminating the deprecation warning.
- `<meta name="apple-mobile-web-app-capable" content="yes" />`: Retains 100% backward compatibility for iOS Safari Home Screen standalone launches.
