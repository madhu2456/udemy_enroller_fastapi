# DPIA skeleton — hosted Udemy session cookie processing (F024)

**Status:** Skeleton / working draft for owner and counsel — **not a completed DPIA** and **not legal advice**.  
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
| Title | DPIA skeleton — Udemy session cookies (hosted / multi-tenant capable) |
| Controller / operator | `[TODO: legal name / role]` |
| Version | 0.2-skeleton |
| Last updated | 2026-08-09 |
| Review cadence | `[TODO: e.g. annual or on material change]` |
| Systems in scope | ☐ Self-hosted · ☐ Hosted demo `udemyenroller.madhudadi.in` · ☐ Other: ________ |
| Deployment mode in scope | ☐ `DEPLOYMENT_ENV=server` · ☐ local · ☐ both |

---

## 2. Processing description (facts — re-verify in code)

### 2.1 Purpose

Allow a user who controls a Udemy account to **attempt automated enrollment** in free / 100%-off courses using **their own** session cookies, and (on server deployments) to persist **encrypted** cookies so the user need not re-paste them every run.

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

- `[TODO: host region, backup region, analytics regions — document with counsel]`  
- Do not invent transfer mechanisms (SCCs, etc.) in this skeleton.

### 2.7 Retention (proposed — owner must confirm)

| Data | Working proposal | Owner decision | Deletion mechanism |
|------|------------------|----------------|--------------------|
| Encrypted Udemy cookies | No longer than needed for active app sessions; wipe when last session ends / logout / clear-data | ________ | Session lifecycle (`app/session_lifecycle.py`) — re-verify behavior |
| App sessions (server) | ~**24 hours** TTL | ________ | Auth session expiry |
| App sessions (local) | Longer (code uses multi-day local TTL) | ________ | Confirm if local in scope |
| Enrollment history | Until account deletion or operator policy | ________ | `[TODO]` |
| App logs | Host rotation policy | ________ | Redact tokens; never log raw cookies |
| DB backups | Script retention (see `scripts/backup_sqlite.sh` / ops backup doc) | ________ | Prune + access control |

---

## 3. Implementation controls (evidence pointers — not legal adequacy)

Re-check before any “DPIA complete” claim:

| Control | Evidence | Verified? |
|---------|----------|-----------|
| Fernet encrypt/decrypt for stored cookies | `app/security.py` (`encrypt_cookies` / `decrypt_cookies`) | ☐ |
| Server mode requires valid Fernet `COOKIE_ENCRYPTION_KEY` | settings / startup validation; `docs/security-trio-fix.md` | ☐ |
| Server/production rejects legacy **plaintext** cookie blobs by default (F019) | `decrypt_cookies` + `_allow_plaintext_cookies()` | ☐ |
| Server session TTL ~24h | `app/routers/auth.py` (`_SESSION_TTL_SERVER_SECONDS`) | ☐ |
| Wipe encrypted cookies when no active sessions remain | `app/session_lifecycle.py` | ☐ |
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

Lawful basis, consent, and “legitimate interest” analyses are **out of scope for engineering fill-in** — complete only with qualified counsel (section 8).

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

| Role | Name | Date | Outcome |
|------|------|------|---------|
| Product owner | | | ☐ Proceed · ☐ Redesign · ☐ Pause hosted cookies |
| Engineering | | | Controls table §3 verified: ☐ |
| Counsel / privacy advisor | | | Memo ref: ________ — **required before claiming legal compliance** |
| Security review | | | |

### Explicit non-conclusions

Signatories acknowledge:

1. This skeleton is incomplete until counsel input and risk ratings are filled.  
2. Nothing herein asserts that processing is lawful, ToS-compliant, DPIA-approved, or “low residual risk.”  
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

## 10. Related audit findings

| ID | Topic | Linkage |
|----|--------|---------|
| F001 | Hosted multi-tenant encrypted cookies residual | D.3 accept or redesign |
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
