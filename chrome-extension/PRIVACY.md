# Privacy Policy - Udemy Enroller Chrome Extension

Last updated: July 4, 2026

## Overview

The Udemy Enroller Chrome Extension ("Extension") extracts Udemy session cookies for use with the Udemy Enroller web application. This privacy policy explains what data the Extension accesses and how it is used.

## Data Accessed

The Extension reads the following Udemy cookies:
- `access_token` - Udemy session token
- `client_id` - Udemy client identifier
- `csrftoken` - Udemy CSRF token

These cookies are accessed solely to copy them to your clipboard for use with the Udemy Enroller web application.

## Data Storage

The Extension does **not** store any of your data persistently. Cookie values are held in memory only while the popup is open and are discarded when the popup closes.

## Data Transmission

The Extension makes one optional network request:
- **Coupon count fetch:** `GET https://udemyenroller.madhudadi.in/udemycoupons/api/coupons?limit=1`
- **Purpose:** Display the number of available free coupons
- **Data transmitted:** None (only standard HTTP headers)
- **Data received:** `{ total: <number> }`

No cookie values, personal data, or identifying information is transmitted in this request.

## Clipboard Usage

When you click "Copy Cookies", the Extension copies the following string to your clipboard:
```
access_token=xxx&client_id=yyy&csrf_token=zzz
```

This data remains on your device and is not transmitted anywhere by the Extension.

## Third-Party Services

The Extension does not use any third-party analytics, tracking, or advertising services.

## Permissions

| Permission | Purpose |
|------------|---------|
| `cookies` | Read Udemy session cookies |
| `host_permissions: https://*.udemy.com/*` | Limited to Udemy domain only |

## Changes to This Policy

We may update this privacy policy from time to time. Any changes will be reflected in the "Last updated" date above.

## Contact

If you have questions about this privacy policy, please open an issue on [GitHub](https://github.com/madhu2456/udemy_enroller_fastapi/issues).
