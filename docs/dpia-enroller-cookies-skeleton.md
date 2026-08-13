# DPIA draft — hosted Udemy session cookie processing (F024)

**Status:** DRAFT v1 — pending counsel review — **not a completed DPIA** and **not legal advice**.  
**Finding:** F024 (formal DPIA missing); supports residual risk discussion for F001 (hosted multi-tenant encrypted cookies).  
**Product:** Udemy Enroller — open source + optional hosted demo  
**Live demo (if operated):** https://udemyenroller.madhudadi.in  
**Audit ref:** master-audit v7.8 (`docs/audits/2026-08-09-master-audit-v7.8/`)  
**Date opened:** 2026-08-09  

### Hard disclaimers

- Completing blanks in this file does **not** establish compliance with DPDP, GDPR, or any other regime.  
- Do **not** treat “encrypted,” “24h TTL,” or “plaintext rejected” as a legal conclusion of adequacy or lawfulness.  
- Engineering mitigations reduce technical exposure; they do not decide platform Terms outcomes (see F002 / counsel brief).  
- No production secrets, real user cookies, or personal data samples belong in this document.

### Primary linked materials (read first)

| Document | Path / URL |
|----------|------------|
| Security policy | [`SECURITY.md`](../SECURITY.md) |
| Privacy policy (user-facing) | Template: [`app/templates/pages/privacy.html`](../app/templates/pages/privacy.html) · Live: https://udemyenroller.madhudadi.in/privacy |
| Counsel process brief (**not** advice) | [`legal-counsel-review.md`](legal-counsel-review.md) |
| Cookie encryption / key rotation ops | [`security-trio-fix.md`](security-trio-fix.md) |
| Backup / restore ops | [`ops/backup-restore.md`](ops/backup-restore.md) |
| D.3 acceptance template | Repo: `docs/audits/2026-08-09-master-audit-v7.8/09-D3-accepted-risks-template.md` |
| Chrome extension privacy (if used) | [`chrome-extension/PRIVACY.md`](../chrome-extension/PRIVACY.md) |

---

## 1. Document control

| Field | Value |
|-------|--------|
| Title | DPIA draft — Udemy session cookies (hosted / multi-tenant capable) |
| Controller / operator | **Madhu Dadi** (individual operator; open-source maintainer) |
| Controller contact | https://madhudadi.in/profile/ (public profile — no personal contact details in this doc) |
| Version | 0.4-draft-v1 |
| Last updated | 2026-08-12 |
| Review cadence | `[TODO: e.g. annual or on material change]` |
| Systems in scope | ☑ Self-hosted · ☑ Hosted demo `udemyenroller.madhudadi.in` · ☐ Other: ________ |
| Deployment mode in scope | ☑ `DEPLOYMENT_ENV=server` · ☑ local · ☐ both |

---

## 2. Processing description (facts — re-verify in code)

### 2.1 Purpose

Allow a user who controls a Udemy account to **attempt automated enrollment** in free / 100%-off courses using **their own** session cookies, and (on server deployments) to persist **encrypted** cookies so the user need not re-paste them every run.

**DRAFT v1 fill (code-verified at 2026-08-12):** the stored object is the **bearer Udemy session cookie set** (access token / client id / CSRF-equivalent session material) captured from the user's own browser session. The app session that carries it is **short-lived**: 24 h TTL on server deployments, 30 days local. Post-F-ENRL-C01, the stored blob is a **Fernet envelope keyed per session** via HKDF-SHA256 (master `COOKIE_ENCRYPTION_KEY` + per-session `users.cookies_salt`); legacy unsalted blobs are rejected in server mode (`ALLOW_LEGACY_COOKIE_DECRYPT` default OFF) until migrated by `scripts/migrate_cookies_per_session.py`.

### 2.2 What the product claims not to be

Public copy and [`SECURITY.md`](../SECURITY.md) state the tool is **not affiliated with, endorsed by, or authorized by Udemy**. Enrollment is **not guaranteed**.

### 2.3 Categories of personal data

| Category | Examples | Source | Notes |
|----------|----------|--------|--------|
| Account identifiers | App username / email (if registered) | User | Confirm fields actually stored |
| Session secrets | Udemy session cookie material (bearer-equivalent) | User paste / extension | **High sensitivity** |
| Usage / job metadata | Enrollment run status, course titles/URLs processed | App-generated | |
| Technical | IP (rate limiting), optional logs | HTTP request | Confirm log contents |
| Optional analytics | GTM/GA4 after consent (hosted privacy copy) | Browser | Per privacy page — re-read live copy |

**Not intended to process:** Udemy account **password** on server mode (cookie login path); payment card data (N/A).

### 2.4 Data subjects

- End users of self-hosted or hosted demo who connect a Udemy session.

### 2.5 Recipients / processors (owner fills roles)

| Party | Role (fill) | Data shared |
|-------|-------------|-------------|
| Instance operator (self-host or demo host) | `[TODO: controller / processor]` | DB including encrypted cookies |
| Hosting / CDN / backup storage | `[TODO]` | Disk images, backups, edge logs |
| Udemy | Independent platform | Session cookies presented **to Udemy** during enrollment HTTP flows |
| Analytics vendors (if consent) | `[TODO]` | Analytics events — **must not** include Udemy cookies |
| Coupon aggregator sites | Traffic as product behavior | Scraping residual (counsel / F002 theme) |

### 2.6 Cross-border transfers

**DRAFT v1 fill (for counsel):** the only external data flow is the **user's own Udemy session cookie material sent to Udemy Inc.** (US) during enrollment HTTP flows — under the **user's own Udemy account**, at the user's direction, to the platform that issued the session. The operator does not transfer stored personal data to third countries beyond that flow: the hosted demo is operated by the controller (India), no additional analytics/backup vendor transfers are claimed, and cookies are encrypted at rest. Whether the Udemy-directed flow is a "transfer" for GDPR Art. 44+ purposes is a **counsel question** (data is disclosed by the data subject to the same controller of the account). Do not invent SCCs or adequacy findings in this document.  
- `[TODO with counsel: host region, backup region, analytics regions]`

### 2.7 Retention (DRAFT v1 — owner confirms)

| Data | Working proposal | Owner decision (draft) | Deletion mechanism |
|------|------------------|------------------------|--------------------|
| Encrypted Udemy cookies | No longer than needed for active app sessions; wipe when last session ends / logout / clear-data | **24 h TTL on server; wipe on logout, last-session expiry, and Clear-All-Data** | Session lifecycle (`app/session_lifecycle.py`), `logout`, `settings` clear-data — salt wiped together (F-ENRL-C01) |
| App sessions (server) | ~**24 hours** TTL | **Confirmed** — `_SESSION_TTL_SERVER_SECONDS` | Auth session expiry |
| App sessions (local) | Longer (code uses multi-day local TTL) | Local only, owner convenience | Confirm if local in scope |
| DB rows holding cookies | Until session expiry (cookies + salt rows) | **Rows survive until expiry; values wiped at the events above** | Lifecycle wipe sets `udemy_cookies=NULL`, `cookies_salt=NULL` |
| Enrollment history | Until account deletion or operator policy | `[TODO]` | `[TODO]` |
| App logs | Host rotation policy | Redact tokens; never log raw cookies | Sanitize logging |
| DB backups | Script retention (see `scripts/backup_sqlite.sh` / ops backup doc) | Prune + access control | Backup ops |

---

## 3. Implementation controls (evidence pointers — not legal adequacy)

Re-check before any “DPIA complete” claim:

| Control | Evidence | Verified? |
|---------|----------|-----------|
| Fernet encrypt/decrypt for stored cookies | `app/security.py` (`encrypt_cookies` / `decrypt_cookies`) | ☐ |
| **Per-session Fernet envelope (HKDF-SHA256, per-session salt)** | `app/security.py` (`generate_cookie_salt` / `encrypt_cookies_salted` / `decrypt_cookies(…, salt)`); `users.cookies_salt`; migration `scripts/migrate_cookies_per_session.py` | ☑ 2026-08-12 (tests `tests/test_cookie_envelope.py`) |
| Server mode requires valid Fernet `COOKIE_ENCRYPTION_KEY` | settings / startup validation; `docs/security-trio-fix.md` | ☐ |
| Server/production rejects legacy **plaintext** cookie blobs by default (F019) | `decrypt_cookies` + `_allow_plaintext_cookies()` | ☐ |
| **Server/production rejects legacy unsalted blobs by default (F-ENRL-C01)** | `decrypt_cookies` + `_allow_legacy_cookie_decrypt()` (default OFF in server) | ☑ 2026-08-12 |
| Server session TTL ~24h | `app/routers/auth.py` (`_SESSION_TTL_SERVER_SECONDS`) | ☐ |
| Wipe encrypted cookies (and salt) when no active sessions remain | `app/session_lifecycle.py` | ☑ 2026-08-12 |
| `MAX_SESSIONS_PER_USER` cap | settings + auth session create path | ☐ |
| CSRF on state-changing routes (not cookie-login itself) | `app/security.py` / routers | ☐ |
| Secure cookie flags in server mode | settings / tests | ☐ |
| Vulnerability reporting | [`SECURITY.md`](../SECURITY.md) | ☐ |
| User-facing privacy notice | `/privacy` + template | ☐ |
| Backup procedure | `docs/ops/backup-restore.md`, `scripts/backup_sqlite.sh` | ☐ |
| No secrets in git | `scripts/verify-no-secrets.sh` (if used in CI) | ☐ |

---

## 4. Necessity & proportionality (engineering narrative only)

- **Necessity (product):** On `DEPLOYMENT_ENV=server`, cookie login is the supported path for Udemy session material; password login is intended for non-server/local deployments (confirm settings).  
- **Minimisation (product):** Only cookies the user provides; encrypt-at-rest when configured; short server session TTL; wipe paths.  
- **Proportionality residual:** Cookies are **bearer credentials** — compromise of DB **and** encryption key (or memory decryption path) can equal full session takeover of the linked Udemy account. Multi-tenant hosted demo increases blast radius (F001).

Lawful basis, consent, and "legitimate interest" analyses are **counsel territory** — the options below are a **DRAFT v1 engineering framing only**, explicitly not a legal conclusion (section 8).

---

## 4a. Lawful-basis analysis — DRAFT v1 (for counsel, not advice)

> **DRAFT FOR COUNSEL.** These are candidate framings with their trade-offs, not a determination that any basis applies. Marker: `docs/legal-counsel-review.md`.

**Option A — Consent (primary candidate for hosted demo).**
- The user affirmatively pastes their own Udemy session cookies and starts a run; the privacy notice (`/privacy`) describes storage, retention and wipe. Consent is the easiest fit for a **bearer-credential, high-sensitivity** category under DPDP (sensitive personal data, s.7 DPDP grounds) and GDPR Art. 6(1)(a).
- Trade-offs: must be freely given, specific, informed, unambiguous and **withdrawable with the same ease** (logout / clear-data / revoke session); consent fatigue; a per-purpose tick-box may be needed in addition to the notice.

**Option B — Legitimate interest (candidate for self-host / personal use).**
- Processing serves the **user's own interest** (enrolling in free courses with their own session); for a purely self-hosted single-user instance there may be no separate "controller" interest beyond the user's own task (cf. GDPR Art. 6(1)(f); DPDP s.7(c) processing for the individual's own purpose — counsel to confirm scope).
- Trade-offs: requires a documented LIA, an expectation check ("would the user expect their own session cookies to be stored on the instance they connect to?"), and a balancing test; weaker fit for **third parties'** data — none processed here by design.

**Not relied upon:** performance of a contract (no contract with Udemy), legal obligation, vital interests. **Not processed:** children's data (N/A), special categories beyond session material (N/A).

Engineering implications for either basis: minimize (only the user's own cookie set), encrypt per-session (F-ENRL-C01), 24 h server TTL, wipe on logout / last-session expiry / clear-data, and keep consent signals (cookie banner, privacy page, connect-time notice) honest and current.

---

## 4b. DPDP notice alignment pointers (DRAFT v1)

The user-facing privacy page (template `app/templates/pages/privacy.html`, live `/privacy`) already carries the sections the DPDP notice obligations map onto; keep each pointer in sync with this document when either changes:

| DPDP notice element (s.5) | Privacy page section (pointer) |
|---------------------------|--------------------------------|
| What data is collected | "What Data Is Collected" |
| How data is stored / security | "How Data Is Stored" (encryption at rest, per-session envelopes) |
| What is **not** collected | "What Data Is Not Collected" (no password, no payment data on server) |
| Erasure / withdrawal | "How to Delete Your Data" (+ logout / clear-data wipe) |
| App-level cookies | "Browser Cookies" |
| Data fiduciary identity + contact | "India DPDP Act — Data Fiduciary" (operator contact) |
| Non-affiliation / third-party flow to Udemy | "Affiliation" |

Gap (open): the page's contact channel and the DPIA controller contact (https://madhudadi.in/profile/) must be cross-checked to the same mailbox; grievance channel wording to be confirmed with counsel.

---

## 5. Risk register (qualitative — fill L/I after discussion)

| Risk ID | Description | L | I | Mitigations (current / planned) | Treatment |
|---------|-------------|---|---|----------------------------------|-----------|
| R1 | Host/DB leak of Fernet ciphertext; offline attack if key also exposed | | | Fernet; key not in git; server key validation | ☐ Accept (D.3 F001) · ☐ Redesign |
| R2 | Key + backup stolen | | | Backup access control; rotation runbook | ☐ |
| R3 | XSS/CSRF → app session → cookie use | | | CSRF, CSP, secure cookies (as deployed) | ☐ |
| R4 | User pastes cookies into untrusted clone | | | HTTPS, education, self-host preference in SECURITY.md | ☐ |
| R5 | Over-retention after user leaves | | | TTL + wipe; confirm product UX | ☐ |
| R6 | Logs contain tokens | | | Sanitize logging; secret-scan | ☐ |
| R7 | Platform Terms / automation enforcement | | | Disclaimers; counsel pack — **not fixed by DPIA** | ☐ F002 counsel |
| R8 | `[TODO]` | | | | |

---

## 6. Data subject rights (process design — not a guarantee of law)

| Request type | Public channel | Owner SLA | Technical steps | Tested? |
|--------------|----------------|-----------|-----------------|---------|
| Access | `[TODO]` | `[TODO]` | Describe stored fields; no raw cookie export to email without care | ☐ |
| Delete / wipe cookies | Privacy UX + logout / clear-data | `[TODO]` | Wipe path + session revoke | ☐ |
| Account deletion | `[TODO]` | `[TODO]` | Cascade sessions, cookies, history | ☐ |
| Object / stop hosted processing | `[TODO]` | `[TODO]` | Disable connect / leave hosted demo | ☐ |

Align wording with the live privacy page before publication.

---

## 7. Alternatives considered

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Local / self-host only (no multi-tenant hosted cookies) | Smaller blast radius | Weaker public demo | ☐ |
| Extension holds cookies; server never stores | No server cookie store | UX / product change | ☐ |
| Keep hosted encrypted cookies | Demo convenience | F001 residual + DPIA burden | ☐ Historical owner “Keep” — reconfirm |
| Disable enrollment on hosted demo | Lower automation risk | Demo less useful | ☐ |
| Official APIs only | Cleaner Terms posture | May not exist / fit | ☐ |

---

## 8. Consultation and sign-off

**Status: DATE-PENDING — this draft is NOT signed off.** Counsel review required before any compliance claim; see `docs/legal-counsel-review.md`.

| Role | Name | Date | Outcome |
|------|------|------|---------|
| Product owner | Madhu Dadi | DATE-PENDING | ☐ Proceed · ☐ Redesign · ☐ Pause hosted cookies |
| Engineering | — | 2026-08-12 | Controls table §3 partially verified (C01 rows ☑) |
| Counsel / privacy advisor | **PENDING** | DATE-PENDING | Memo ref: ________ — **required before claiming legal compliance** |
| Security review | — | ☐ | |

### Explicit non-conclusions

Signatories acknowledge:

1. This document is a **DRAFT v1 pending counsel review** — incomplete until counsel input and risk ratings are filled.  
2. Nothing herein asserts that processing is lawful, ToS-compliant, DPIA-approved, or "low residual risk."  
3. D.3 acceptance of F001 (and F002 counsel path) remains a **separate** control:  
   `docs/audits/2026-08-09-master-audit-v7.8/09-D3-accepted-risks-template.md`.

---

## 9. Open actions

- [ ] Confirm controller/processor roles for hosted demo  
- [ ] Align privacy page with actual retention / wipe behavior  
- [ ] Confirm backup encryption and access control on production host  
- [ ] Schedule restore drill (see `docs/ops/backup-restore.md`)  
- [ ] Complete D.3 for F001 (and F002 with counsel)  
- [ ] Counsel review of automation / Terms residual (see [`legal-counsel-review.md`](legal-counsel-review.md)) — separate from technical DPIA  
- [ ] Re-verify F019 plaintext reject on the running server image  

---

## 9a. Residual-risk acceptance checklist (F004 / F001)

**Purpose:** Owner sign-off that residual risk of **hosted multi-tenant Fernet-encrypted Udemy session cookies** is understood and accepted (or redesign chosen). Engineering mitigations (Fernet, TTL, wipe, plaintext reject) reduce exposure; they do **not** eliminate bearer-credential compromise if DB **and** `COOKIE_ENCRYPTION_KEY` (or a live decryption path) are both breached.

| Check | Owner | Date | Notes |
|-------|-------|------|-------|
| Read §4 necessity residual + risk R1/R2 in this skeleton | ☐ | | |
| Confirmed deployment mode in scope (hosted demo vs self-host only) | ☐ | | |
| Accept residual multi-tenant Fernet risk **or** choose redesign (local-only / no server cookie store) | ☐ Accept · ☐ Redesign | | Decision: ________ |
| D.3 accepted-risks template filled for F001 | ☐ | | Path: `docs/audits/…/09-D3-accepted-risks-template.md` if present |
| Counsel path opened for F002 (Terms/automation) if still operating enrollment automation | ☐ N/A · ☐ Opened | | Separate from technical residual |

**Explicit residual (non-legal):** On a multi-tenant hosted instance, ciphertext for many users’ session cookies may coexist in one DB; key material is a single blast-radius control. Prefer self-host when session confidentiality is paramount. Sign-off here is an **ops/product acceptance record**, not a compliance certificate.

Owner sign-off: _________________ Date: ________ Role: ________

---

## 10. Related audit findings

| ID | Topic | Linkage |
|----|--------|---------|
| F001 | Hosted multi-tenant encrypted cookies residual | D.3 accept or redesign |
| F004 | Residual-risk acceptance stub | **§9a checklist** (this doc) |
| F002 | Automation / ToS residual | Counsel — not closed by this DPIA |
| F019 | Plaintext cookie path | Code default rejects in server mode — re-verify deploy |
| F024 | Formal DPIA missing | **This document** (skeleton only until signed) |
| F065 | Backup automation residual | Ops backup doc |

---

## Document control history

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-08-09 | Initial skeleton draft |
| 0.2 | 2026-08-09 | Expanded checklist; explicit non-conclusions; SECURITY + privacy links; no fabricated lawful-basis conclusions |
| 0.3 | 2026-08-10 | F004 residual-risk acceptance checklist (§9a) for Fernet multi-tenant residual |
| 0.4-draft-v1 | 2026-08-12 | **DRAFT v1 (F-ENRL-J01)**: controller identified (Madhu Dadi / https://madhudadi.in/profile/); processing description (bearer cookies, short-lived, per-session encryption post-C01); lawful-basis options (consent / legitimate interest — for counsel); retention confirmed (24h TTL, wipe incl. salt); cross-border fill; DPDP notice pointers; DATE-PENDING sign-off + counsel-review marker |
