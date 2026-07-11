# Legal / counsel review brief (#30)

**Status:** Process checklist for the project owner — **not legal advice**.  
**Date prepared:** 2026-07-12  
**Product:** Udemy Enroller (open source + optional hosted demo)  
**Live site (demo):** https://udemyenroller.madhudadi.in  
**Repository:** https://github.com/madhu2456/udemy_enroller_fastapi  

This document is for briefing **qualified counsel** (or a compliance review you commission).  
It does **not** conclude that the product is lawful, ToS-compliant, or trademark-safe.

---

## 1. Why this review exists

Owner decisions already made in the forensic audit (keep unless reversed):

| Topic | Owner decision (current) |
|-------|---------------------------|
| Project name / domain containing “Udemy” | **Keep** |
| Automated enrollment capability | **Keep**, with stronger user warnings |
| CloudScraper / Playwright-stealth stack | **Keep** (no stealth “upgrade”; no CAPTCHA bypass work) |
| Hosted multi-tenant demo with encrypted cookies | **Keep**, with short session TTL + cookie wipe on last session expiry / logout / clear-data |
| Public promotion intensity | Not blocked by engineering; legal risk remains |

Engineering cannot “fix” platform-policy or trademark risk with disclaimers alone. Counsel review is the residual **external** step.

---

## 2. Product facts counsel should verify against primary sources

### 2.1 What the product does (as implemented)

- Independent FastAPI app + optional Chrome extension for **cookie extraction** (user-initiated).
- User connects a Udemy session (cookies on hosted demo; email login only when `DEPLOYMENT_ENV=local`).
- On **user start**, the app scrapes **third-party coupon aggregator** sites and **attempts** enrollment via Udemy session-authenticated HTTP flows.
- Public page `/udemycoupons` lists free coupon links (validity can change).
- MIT-licensed open source; hosted demo is multi-user capable.

### 2.2 What the product claims not to be

Public copy and `SECURITY.md` state the tool is **not affiliated with, endorsed by, or authorized by Udemy**. Enrollment is **not guaranteed**.

### 2.3 Technical surfaces that often matter legally / contractually

| Surface | Evidence in repo / product |
|---------|----------------------------|
| Branding | Name “Udemy Enroller”, domain `udemyenroller.madhudadi.in`, extension name |
| Automation | `app/services/udemy_client.py`, CloudScraper client, enrollment manager |
| Anti-bot / stealth | `playwright-stealth` in `requirements.txt`; Playwright used for some aggregator fallbacks |
| Session data | Fernet-encrypted `udemy_cookies` on server when users connect to hosted demo |
| Scraping | Coupon aggregator scrapers under `app/services/` |
| Disclaimers | Login/connect UI, FAQ, privacy, README, llms/humans text |
| License | MIT (`LICENSE`) — governs **code** redistribution, not third-party platform rights |

### 2.4 Jurisdictions / audiences (owner to confirm with counsel)

- Global English audience; India may be relevant for owner residence / user base.
- Hosted demo processes user-supplied session cookies — privacy law analysis may apply depending on audience and hosting.

---

## 3. Residual risk themes (non-exhaustive, non-legal)

These are **engineering/audit themes** for counsel to analyze against Udemy Terms, aggregator ToS, trademark practice, and applicable law:

1. **Trademark / brand** — use of “Udemy” in product name, domain, extension, marketing.  
2. **Platform terms** — automated access, bulk enrollment, use of session cookies outside official apps/APIs.  
3. **Anti-bot tooling** — CloudScraper and playwright-stealth characterizations and purpose.  
4. **Scraping** — collection of coupon data from third-party sites.  
5. **Hosted cookie processing** — multi-tenant storage of encrypted Udemy session material.  
6. **Marketing accuracy** — residual overclaim risk if copy drifts (recent sweeps reduced this).  
7. **Third-party content** — course titles/thumbnails on public deals if any rights/attribution issues.  
8. **Extension store** — if published to Chrome Web Store, listing claims and privacy disclosures.

---

## 4. Questions to ask counsel (suggested agenda)

1. Is continued use of “Udemy” in the product name and subdomain acceptable for an independent tool with non-affiliation statements, or is rebranding advisable?  
2. Does automated enrollment using user session cookies create material ToS / account-ban / enforcement risk for **users**, **the host**, or both?  
3. Should the **hosted demo** disable enrollment and offer self-host only, from a risk perspective?  
4. Is continued use of CloudScraper / playwright-stealth consistent with a defensive “no CAPTCHA bypass” product policy, or should those dependencies be removed/quarantined?  
5. What privacy notices, DPIA-style analysis, or retention limits are advisable for hosted encrypted cookies (India / EU visitors / other)?  
6. Any required changes to privacy policy, security contact, or public promotion language?  
7. Can open-source MIT distribution continue while the hosted demo runs, or should distribution/hosting be separated?

---

## 5. Document pack to send counsel

| Item | Location / note |
|------|------------------|
| This brief | `docs/legal-counsel-review.md` |
| README (what it is / is not) | `README.md` |
| Privacy policy (user-facing) | live `/privacy` or `app/templates/pages/privacy.html` |
| Security policy | `SECURITY.md` |
| License | `LICENSE` |
| Extension privacy | `chrome-extension/PRIVACY.md` |
| Dependency list | `requirements.txt` (note cloudscraper, playwright-stealth) |
| Hosted posture | Session TTL 24h server / cookie wipe on last expiry; `MAX_SESSIONS_PER_USER` |
| Live site | https://udemyenroller.madhudadi.in |
| Optional: audit finding IDs | UE-LEGAL-001, UE-AUTO-*, UE-PRIV-001 from prior Phase 1 audit notes |

**Do not send:** production secrets, real user cookies, production `.env`, personal credentials.

---

## 6. Owner action checklist

- [ ] Choose counsel with software / platform / trademark experience in relevant jurisdictions  
- [ ] Send document pack + live URLs  
- [ ] Answer counsel’s factual questions without guessing (hosting region, user volume, promotion channels)  
- [ ] Record written advice and any required product changes  
- [ ] If advice requires product change, reopen optional **#31–35** (stealth out, host-only, enroll off, rename, account delete) as **owner decision reversals**  
- [ ] Until advice is received, avoid overstating “legal compliance” in marketing  

---

## 7. What this repository will not do without a new owner decision

- Rename product/domain or strip “Udemy” branding  
- Remove stealth/CloudScraper “for compliance” without explicit instruction  
- Disable hosted enrollment by default  
- Publish invented legal conclusions or “Udemy-approved” language  
- File trademarks or send cease-and-desist responses on the owner’s behalf  

---

## 8. Engineering status after this item

| Bucket | Status |
|--------|--------|
| #30 counsel review process pack | **Delivered** (this file) |
| Formal legal opinion | **External only** — not completed by engineering |
| Optional #31–35 | Dormant unless owner reverses prior decisions |

After counsel returns advice, open a focused engineering ticket (or re-run optionals #31–35) with explicit instructions.
