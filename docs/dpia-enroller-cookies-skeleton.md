# DPIA draft — hosted Udemy session cookie processing (F004)

**Status:** DRAFT v1 — residual **accepted** 2026-08-16 (ops/product); still pending counsel review — **not a completed DPIA**, **not legal advice**, **not** counsel-approved. Review 2026-10-16.  
**Finding (cookie residual):** **F004** (v7.15) — hosted multi-tenant Fernet-encrypted Udemy session cookies.  
**Product:** Udemy Enroller — open source + optional hosted demo  
**Live demo (if operated):** https://udemyenroller.madhudadi.in  
**Audit ref:** master-audit v7.15 (`docs/audits/master-audit-v7.15-2026-08-16.md`); historical skeleton opened under v7.8  
**Date opened:** 2026-08-09  

### ID mapping (do not mix)

| Era | ID | Meaning |
|-----|----|---------|
| v7.8 (2026-08-09) | **F001** | This cookie residual — **same issue** as v7.15 F004 |
| v7.8 | **F004** | Blog `RagQueryLog` retention — **not** this residual |
| v7.8 | **F024** | Formal DPIA missing (this file is still that **unsigned skeleton**) |
| v7.13+ / v7.15 | **F001** | Adticks GHA SHA pins — **closed** — **not** cookies |
| v7.15 | **F004** | Current cookie residual (**this document**) |
| v7.15 | **F024** | CAA empty / DNS inventory — **unrelated** to this DPIA |
| v7.8 / Enroller-local | **F019** / **F019-plaintext** | Server rejects legacy **plaintext** cookie blobs (this product) |
| v7.15 fleet | **F019** | Adticks `humans.txt` — **closed** — **not** Enroller plaintext reject |

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
| Fail-closed `COOKIE_ENCRYPTION_KEY` validation (F011 proven 2026-08-16; still **do not** execute rotation/purge — Accept residual is **not** a rotate instruction) | [`security-trio-fix.md`](security-trio-fix.md) — boot-time Fernet **validation** is in scope; the same file’s rotate/wipe runbook is **not** an F004 close path and must not run |
| Backup / restore ops | [`ops/backup-restore.md`](ops/backup-restore.md) |
| D.3 residual-acceptance worksheet (v7.15 F004, **Accepted residual** ops/product) | Repo: `docs/audits/D3-F004-enroller-fernet-2026-08-16.md` — Decision ☑ **Accept residual** (2026-08-16); approver Madhu Dadi (owner); verbal Accept via orchestration (not wet-ink legal); review **2026-10-16**. **Not** lawful / **not** counsel-approved DPIA. F011 last-success **proven** 2026-08-16. No key rotate. |
| D.3 historical v7.8 template (F001 snapshot) | Repo: `docs/audits/2026-08-09-master-audit-v7.8/09-D3-accepted-risks-template.md` — do not sign as v7.15 F004 |
| Chrome extension privacy (if used) | [`chrome-extension/PRIVACY.md`](../chrome-extension/PRIVACY.md) |

---

## 1. Document control

| Field | Value |
|-------|--------|
| Title | DPIA draft — Udemy session cookies (hosted / multi-tenant capable) |
| Controller / operator | **Madhu Dadi** (individual operator; open-source maintainer) |
| Controller contact | https://madhudadi.in/profile/ (public profile — no personal contact details in this doc) |
| Version | 0.9-draft-v1 |
| Last updated | 2026-08-16 |
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

**DRAFT v1 fill (for counsel):** External flows are **not** Udemy-only. They include (1) the **user's own Udemy session cookie material sent to Udemy Inc.** (US) during enrollment HTTP flows — under the **user's own Udemy account**, at the user's direction — **and** (2) optional **GTM/GA4** page/event analytics after consent (privacy template). Host/analytics **regions, SCC, and adequacy** are **counsel questions** — do not invent findings here. **Cookie blobs / Udemy session material must not go to analytics.** The hosted demo is operated by the controller (India). Whether any of these is a "transfer" for GDPR Art. 44+ purposes is a **counsel question**. Do not invent SCCs or adequacy findings in this document.  
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
| DB backups | Script retention (see `scripts/backup_sqlite.sh` / ops backup doc) | Unencrypted SQLite copies; default **14 days** / **30** newest files. **Separate** from live-DB wipe. Last-success **F011 proven** 2026-08-16. Encryption/access and copy-restore drill still unproven | Backup ops (does **not** erase on logout) |

---

## 3. Implementation controls (evidence pointers — not legal adequacy)

Re-check before any “DPIA complete” claim:

| Control | Evidence | Verified? |
|---------|----------|-----------|
| Fernet encrypt/decrypt for stored cookies | `app/security.py:78-89` (legacy writer), `:138-144` (salted), `:201-254` (decrypt) | ☑ 2026-08-16 code+tests (`tests/test_security_features.py:33-40`; `tests/test_cookie_envelope.py:51-57`) |
| **Per-session Fernet envelope (HKDF-SHA256, per-session salt)** | `app/security.py:94-144` (`_SESSION_KEY_INFO = b"udemy-enroller-session-key-v1"`; HKDF SHA256 length 32); `app/models/database.py:81-83`; write `app/routers/auth.py:249-270`; migration `scripts/migrate_cookies_per_session.py` (**prod apply state unknown without SSH**) | ☑ 2026-08-16 code+tests (`tests/test_cookie_envelope.py:51-90` — round-trip, wrong-salt fail-closed, cross-session isolation) |
| Server mode requires valid Fernet `COOKIE_ENCRYPTION_KEY` | `config/settings.py:177-184` (`Fernet(self.COOKIE_ENCRYPTION_KEY)` fail-closed; no SECRET_KEY fallback in server); `docs/security-trio-fix.md:22-25` | ☑ 2026-08-16 code+tests (`tests/test_phase2_features.py:110-126`) |
| Server/production rejects legacy **plaintext** cookie blobs by default (**F019-plaintext** / F-ENRL; **not** v7.15 fleet F019 `humans.txt`) | `app/security.py:170-198`, `:215-216` (`decrypt_cookies` + `_allow_plaintext_cookies()`) | ☑ 2026-08-16 code+tests (`tests/test_security_features.py:84-121`; `tests/test_cookie_envelope.py:145-152`). Live image **not** re-verified (SSH) |
| **Server/production rejects legacy unsalted blobs by default (F-ENRL-C01)** | `app/security.py:147-168`, `:237-243` (`decrypt_cookies` + `_allow_legacy_cookie_decrypt()`, default OFF in server) | ☑ 2026-08-16 code+tests (`tests/test_cookie_envelope.py:103-127`; `tests/test_security_features.py:149-171`) |
| Server session TTL ~24h | `app/routers/auth.py:39-46` (`_SESSION_TTL_SERVER_SECONDS = 24 * 60 * 60`) | ☑ 2026-08-16 **code-verified** — **not** test-verified (no unit test asserts 86400) |
| Wipe encrypted cookies (and salt) when no active sessions remain | `app/session_lifecycle.py:140-147`; logout `app/routers/auth.py:415-427`; Clear All Data `app/routers/settings.py:198-211` | ☑ 2026-08-16 code+tests — logout salt wipe `tests/test_logout_multi_session.py:155-157`, `:191-192`; last-expiry test asserts **ciphertext** wipe only (`tests/test_session_lifecycle.py:52-66` — does **not** assert `cookies_salt is None`). Wipe is **live-DB only** (see backup row) |
| `MAX_SESSIONS_PER_USER` cap | `config/settings.py:129` (default 3); enforce `app/routers/auth.py:65-74`; `app/session_lifecycle.py:71-120` | ☑ 2026-08-16 code+tests (`tests/test_session_lifecycle.py:108-169`) |
| CSRF on state-changing routes (not cookie-login itself) | Session CSRF `app/security.py:491-504`; login CSRF `app/security.py:559-576`; logout `auth.py:391`; settings `settings.py:90,123,154`; enrollment CSRF deps | ☑ 2026-08-16 code+tests (`tests/test_security_features.py:197-240`; `tests/test_login_csrf.py`) |
| Secure cookie flags in server mode | Server forces `COOKIE_SECURE = True` `config/settings.py:185`; `set_cookie(..., httponly=True, samesite="lax"/"strict", secure=settings.COOKIE_SECURE)` `auth.py:102-119` | ☑ 2026-08-16 code+tests (`tests/test_phase2_features.py:51-61`, `:99-108`) |
| Vulnerability reporting | [`SECURITY.md`](../SECURITY.md) `:7-17` (advisory + profile + security.txt URL) | ☑ 2026-08-16 **document exists**. Live `/.well-known/security.txt` **not** re-fetched this run |
| User-facing privacy notice | Template `app/templates/pages/privacy.html` (What Data / How Stored / How to Delete / DPDP fiduciary / Affiliation) | ☑ 2026-08-16 **template exists** (existence only; **per-session envelope not disclosed** on that page; `privacy.html` not edited this pass) |
| Backup procedure | `docs/ops/backup-restore.md`; `scripts/backup_sqlite.sh` | ☑ 2026-08-16 **procedure documented**. Copies are **unencrypted** SQLite files (default retain **14 days** / **30** newest). Live-DB wipe (TTL/logout/clear-data) does **not** erase backup history. Host last-success **F011 proven** 2026-08-16. Backup encryption/access and copy-restore drill still unproven. F011 no longer blocks rotation; still **do not** rotate keys or purge blobs (Accept residual is **not** a rotate instruction) |
| No secrets in git | `.gitignore:13-15` (`.env` ignored, `!.env.example`); `.env.example` empty `COOKIE_ENCRYPTION_KEY=`; CI `Udemy Enroller/.github/workflows/ci.yml:15-16` (`scripts/verify-no-secrets.sh --tree`) | ☑ 2026-08-16 scan+ignore+CI (`.env` **not** opened; no key material in git) |

---

## 4. Necessity & proportionality (engineering narrative only)

- **Necessity (product):** On `DEPLOYMENT_ENV=server`, cookie login is the supported path for Udemy session material; password login is intended for non-server/local deployments (confirm settings).  
- **Minimisation (product):** Only cookies the user provides; encrypt-at-rest when configured; short server session TTL; wipe paths.  
- **Proportionality residual:** Cookies are **bearer credentials** — compromise of DB **and** encryption key (or memory decryption path) can equal full session takeover of the linked Udemy account. Multi-tenant hosted demo increases blast radius (**F004** / v7.15; historically v7.8 F001). Host `COOKIE_ENCRYPTION_KEY` + DB (ciphertext **and** `users.cookies_salt`) decrypts every tenant envelope; HKDF salt only blocks cross-session decrypt **without** that row’s salt. Session wipe is **live-DB only**; unencrypted SQLite backups (default 14d / 30 files) are a **separate** window until backup encryption/access (and a copy-restore drill) are proven. **F011 last-success proven** 2026-08-16.

Lawful basis, consent, and "legitimate interest" analyses are **counsel territory** — the options below are a **DRAFT v1 engineering framing only**, explicitly not a legal conclusion (section 8).

---

## 4a. Lawful-basis analysis — DRAFT v1 (for counsel, not advice)

> **DRAFT FOR COUNSEL.** These are candidate framings with their trade-offs, not a determination that any basis applies. Marker: `docs/legal-counsel-review.md`.

**Option A — Consent (candidate for hosted demo — not selected).**
- The user affirmatively pastes their own Udemy session cookies and starts a run; the privacy notice (`/privacy`) describes storage, retention and wipe. Counsel may consider consent as one candidate framing for **bearer-credential** processing (e.g. GDPR Art. 6(1)(a) as a counsel question only). This draft does **not** classify the cookies under any DPDP special/sensitive category and does **not** map them to DPDP s.7.
- Trade-offs: must be freely given, specific, informed, unambiguous and **withdrawable with the same ease** (logout / clear-data / revoke session); consent fatigue; a per-purpose tick-box may be needed in addition to the notice.

**Option B — Legitimate interest (candidate for self-host / personal use — not selected).**
- Processing serves the **user's own interest** (enrolling in free courses with their own session); for a purely self-hosted single-user instance there may be no separate "controller" interest beyond the user's own task (cf. GDPR Art. 6(1)(f) — counsel to confirm whether any analogue applies and to whom). This draft does **not** treat DPDP s.7 as a private “own purpose” / legitimate-interest analogue.
- Trade-offs: requires a documented LIA, an expectation check ("would the user expect their own session cookies to be stored on the instance they connect to?"), and a balancing test; weaker fit for **third parties'** data — none processed here by design.

**Not relied upon:** performance of a contract (no contract with Udemy), legal obligation, vital interests. **Not processed:** children's data (N/A), special categories beyond session material (N/A).

Engineering implications for either basis: minimize (only the user's own cookie set), encrypt per-session (F-ENRL-C01), 24 h server TTL, wipe on logout / last-session expiry / clear-data, and keep consent signals (cookie banner, privacy page, connect-time notice) honest and current.

---

## 4b. DPDP notice alignment pointers (DRAFT v1)

The privacy **template exists** (`app/templates/pages/privacy.html`; live `/privacy`). The table below is a **section-title pointer only**. It is **not** a determination that DPDP s.5 (or any other notice duty) is satisfied. **`privacy.html` is not edited in this pass.**

**Gap (copy):** “How Data Is Stored” describes Fernet encryption. The **per-session** HKDF envelope / `users.cookies_salt` control is **not** disclosed on the template (no `per-session`, `HKDF`, or `cookies_salt` text). Do not treat user-facing copy as describing that control.

| DPDP notice element (s.5) — pointer only | Privacy page section (template headings) |
|------------------------------------------|------------------------------------------|
| What data is collected | "What Data Is Collected" |
| How data is stored / security | "How Data Is Stored" (template: Fernet at rest; **per-session envelope not disclosed**) |
| What is **not** collected | "What Data Is Not Collected" (no password, no payment data on server) |
| Erasure / withdrawal | "How to Delete Your Data" (+ logout / clear-data wipe — **live DB**; backups are a separate window) |
| App-level cookies | "Browser Cookies" |
| Data fiduciary identity + contact | "India DPDP Act — Data Fiduciary" (operator contact) |
| Non-affiliation / third-party flow to Udemy | "Affiliation" |

Gap (open): the page's contact channel and the DPIA controller contact (https://madhudadi.in/profile/) must be cross-checked to the same mailbox; grievance channel wording to be confirmed with counsel.

---

## 5. Risk register (qualitative — fill L/I after discussion)

| Risk ID | Description | L | I | Mitigations (current / planned) | Treatment |
|---------|-------------|---|---|----------------------------------|-----------|
| R1 | Host/DB leak of Fernet ciphertext; offline attack if key also exposed | | | Fernet + HKDF per-session salt; key not in git; server key validation | ☑ Accept (D.3 **F004**, 2026-08-16) · ☐ Redesign |
| R2 | Key + backup stolen | | | Backup access control; F011 last-success **proven** 2026-08-16; rotation runbook **must not** be executed (Accept residual is **not** a rotate instruction); backups are unencrypted SQLite copies (14d/30 files) | ☐ |
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
| Keep hosted encrypted cookies | Demo convenience | F004 residual + DPIA burden | ☐ Historical owner “Keep” — reconfirm |
| Disable enrollment on hosted demo | Lower automation risk | Demo less useful | ☐ |
| Official APIs only | Cleaner Terms posture | May not exist / fit | ☐ |

---

## 8. Consultation and sign-off

**Status: residual accepted (ops/product) 2026-08-16 — DPIA still DRAFT / not legal advice / not counsel-approved.** Counsel review still **PENDING** before any compliance claim; see `docs/legal-counsel-review.md`.

| Role | Name | Date | Outcome |
|------|------|------|---------|
| Product owner | Madhu Dadi | 2026-08-16 | ☑ **Proceed** (residual accepted) · ☐ Redesign · ☐ Pause hosted cookies |
| Engineering | — | 2026-08-16 | §3 engineering rows code/test verified (TTL **code-only**; backup last-success **F011 proven** 2026-08-16). **Not** a legal sign-off |
| Counsel / privacy advisor | **PENDING** | DATE-PENDING | Memo ref: ________ — **required before claiming legal compliance** |
| Security review | — | ☐ | |

### Explicit non-conclusions

Signatories acknowledge:

1. This document is a **DRAFT v1 pending counsel review** — incomplete until counsel input and risk ratings are filled. Residual acceptance does **not** complete the DPIA. **Not legal advice. Not a counsel-approved DPIA.**  
2. Nothing herein asserts that processing is lawful, ToS-compliant, DPIA-approved, or "low residual risk."  
3. D.3 **Accept residual** of **F004** (v7.15 cookie residual; historically v7.8 F001) is an **ops/product** record, separate from F002 counsel:  
   `docs/audits/D3-F004-enroller-fernet-2026-08-16.md` (Decision ☑ **Accept residual**, 2026-08-16; review **2026-10-16**; verbal Accept via orchestration — not wet-ink legal). Historical v7.8 F001 snapshot: `docs/audits/2026-08-09-master-audit-v7.8/09-D3-accepted-risks-template.md`. §8 product owner **Proceed (residual accepted)**; counsel still **PENDING**.

---

## 9. Open actions

- [ ] Confirm controller/processor roles for hosted demo  
- [ ] Align privacy page with actual retention / wipe behavior  
- [ ] Confirm backup encryption and access control on production host  
- [ ] Schedule restore drill (see `docs/ops/backup-restore.md`)  
- [x] **F011** last-success **proven** 2026-08-16. Owner **Accept residual** for **F004** on 2026-08-16 (`docs/audits/D3-F004-enroller-fernet-2026-08-16.md`); review **2026-10-16**. **Not** a crypto change. Still **do not** rotate `COOKIE_ENCRYPTION_KEY` or purge blobs. F002 remains counsel.  
- [ ] Counsel review of automation / Terms residual (see [`legal-counsel-review.md`](legal-counsel-review.md)) — separate from technical DPIA  
- [ ] Re-verify **F019-plaintext** (Enroller-local; **not** fleet v7.15 F019) reject on the running server image  

---

## 9a. Residual-risk acceptance checklist (**F004**)

**Purpose:** Owner sign-off that residual risk of **hosted multi-tenant Fernet-encrypted Udemy session cookies** is understood and accepted (or redesign chosen). Engineering mitigations (Fernet + HKDF per-session salt, TTL, wipe, plaintext/legacy reject) reduce exposure; they do **not** eliminate bearer-credential compromise if DB (blobs **and** salts) **and** `COOKIE_ENCRYPTION_KEY` (or a live decryption path) are both breached.

v7.8 labeled this residual **F001**. v7.15 **F001** is closed GHA pins. v7.8 **F004** was RAG logs. Use **F004** only.

| Check | Owner | Date | Notes |
|-------|-------|------|-------|
| Read §4 necessity residual + risk R1/R2 in this skeleton | ☐ | | |
| Confirmed deployment mode in scope (hosted demo vs self-host only) | ☐ | | |
| Accept residual multi-tenant Fernet risk **or** choose redesign (local-only / no server cookie store) | ☑ **Accept residual** · ☐ Redesign · ☐ Defer until F011 | 2026-08-16 | Owner **Accept residual**. **Not** a claim that processing is lawful. **Not** counsel-complete DPIA. F011 remains **proven**. Review **2026-10-16**. No key rotate. |
| D.3 accepted-risks form filled for **F004** | ☑ | 2026-08-16 | Path: `docs/audits/D3-F004-enroller-fernet-2026-08-16.md` — Decision ☑ **Accept residual**; approver Madhu Dadi (owner); verbal Accept via orchestration (not wet-ink legal); effective 2026-08-16; review 2026-10-16; still do not rotate keys |
| Counsel path opened for F002 (Terms/automation) if still operating enrollment automation | ☐ N/A · ☐ Opened | | Separate from technical residual |

**Explicit residual (non-legal):** On a multi-tenant hosted instance, ciphertext **and** `users.cookies_salt` for many users may coexist in one DB with one host master key. HKDF stops cross-session decrypt without that salt; it does **not** stop host-key + DB compromise. TTL/logout/clear-data wipe is **live-DB only**; unencrypted SQLite backup copies (default **14 days** / **30** newest files) remain a **separate** window until backup encryption/access (and a copy-restore drill) are proven. **F011 last-success proven** 2026-08-16. Prefer self-host when session confidentiality is paramount. Sign-off here is an **ops/product acceptance record**, not a compliance certificate. **Not legal advice. Not a counsel-approved DPIA.** Review **2026-10-16**.

Owner sign-off: Madhu Dadi (owner) — verbal Accept via orchestration (**not** a wet-ink legal signature) Date: 2026-08-16 Role: owner

---

## 10. Related audit findings

| ID | Topic | Linkage |
|----|--------|---------|
| **F004** (v7.15) | Hosted multi-tenant Fernet cookie residual (v7.8 **F001**) | D.3 **Accept residual** 2026-08-16 (ops/product); review **2026-10-16**; §9a residual accepted — **not** lawful / **not** counsel-complete DPIA |
| F001 (v7.15) | Adticks GHA SHA pins | **Closed** — **not** this cookie residual |
| F001 (v7.8 historical) | Same cookie residual as v7.15 F004 | Do not reuse this ID in v7.15 |
| F004 (v7.8 historical) | Blog `RagQueryLog` retention | **Not** this residual |
| F002 | Automation / ToS residual | Counsel — not closed by this DPIA |
| F011 | Host backup last-success **proven** 2026-08-16 | No longer blocks key rotation; still **do not** rotate/purge (Accept residual is **not** a rotate instruction) |
| F019-plaintext (v7.8 F019 / F-ENRL) | Enroller plaintext cookie path | Code default rejects in server mode — re-verify deploy. **Not** v7.15 fleet F019 (`humans.txt`, closed) |
| F024 (v7.8) | Formal DPIA missing | **This document** still DRAFT / DATE-PENDING |
| F024 (v7.15) | CAA empty / DNS inventory | **Unrelated** to cookie DPIA |
| F065 | Backup automation residual | Ops backup doc (procedure only; last-success is F011) |

---

## Document control history

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-08-09 | Initial skeleton draft |
| 0.2 | 2026-08-09 | Expanded checklist; explicit non-conclusions; SECURITY + privacy links; no fabricated lawful-basis conclusions |
| 0.3 | 2026-08-10 | F004 residual-risk acceptance checklist (§9a) for Fernet multi-tenant residual |
| 0.4-draft-v1 | 2026-08-12 | **DRAFT v1 (F-ENRL-J01)**: controller identified (Madhu Dadi / https://madhudadi.in/profile/); processing description (bearer cookies, short-lived, per-session encryption post-C01); lawful-basis options (consent / legitimate interest — for counsel); retention confirmed (24h TTL, wipe incl. salt); cross-border fill; DPDP notice pointers; DATE-PENDING sign-off + counsel-review marker |
| 0.5-draft-v1 | 2026-08-16 | Remap cookie residual **F001 → F004** (v7.15); ID-mapping note (v7.8 F001 ≡ this residual; v7.15 F001 = closed GHA pins; v7.8 F004 = RAG logs). Tick §3 engineering rows with 2026-08-16 path:line evidence (TTL **code-verified** only; backup procedure documented, F011 last-success unproven). Point D.3 to unsigned `docs/audits/D3-F004-enroller-fernet-2026-08-16.md`. Signatures / Accept / Redesign / counsel remain blank. **F004 not closed.** |
| 0.6-draft-v1 | 2026-08-16 | Critic C1–C7: drop false DPDP SPD/s.7/s.7(c) cites in §4a (still **DRAFT FOR COUNSEL**, no basis selected); §4b = template exists, per-session envelope **not** on `privacy.html` (HTML not edited); relabel `security-trio-fix.md` as fail-closed validation / no rotate until F011; §2.6 Udemy **plus** optional GTM/GA4 after consent; F019-plaintext vs fleet humans.txt; wipe = live-DB only vs 14d/30-file unencrypted backups. **F004 not closed.** |
| 0.7-draft-v1 | 2026-08-16 | Owner decision log: §9a **Defer until F011** (not Accept, not Redesign). DATE 2026-08-16. Sign-off line **n/a — not accepted**. D.3 still UNSIGNED. **F004 not closed.** No key rotate. |
| 0.8-draft-v1 | 2026-08-16 | **F011 proven** (single host, deals + enroller). §9a still **Defer** / **not** Accept. Owner may now sign Accept or pick Redesign. F011 no longer blocks rotation; still no rotate/purge unless the owner asks. **F004 not closed.** |
| 0.9-draft-v1 | 2026-08-16 | Owner **Accept residual** DATE 2026-08-16. §8 product owner **Proceed (residual accepted)**; counsel still **PENDING**. Review 2026-10-16. DPIA still draft / not legal advice / not counsel-approved. **Not** a crypto change. No key rotate. |
