# Ops runbooks index — Udemy Enroller

Local-only ops docs (see note below on gitignore). Hosted canonical runbook:
[backup-restore.md](backup-restore.md).

## UE ops docs

- [backup-restore.md](backup-restore.md) — canonical backup/restore runbook
  (F210/F235; encrypted `*.db.enc`, restore drill).
- [backup-drill-2026-08-30.md](backup-drill-2026-08-30.md) — executed drill
  log (RTO 0.39 s, sha256-verified).
- [legacy-decrypt-verify-off.md](legacy-decrypt-verify-off.md) — owner flip
  checklist for `ALLOW_LEGACY_COOKIE_DECRYPT` (U5, F-ENRL-C01 window).
- [alerting.md](alerting.md) — F230 alert webhook (`ALERT_WEBHOOK_URL`).
- [alert-test-fire.md](alert-test-fire.md) — owner safe test-fire runbook
  (A09/F230; `scripts/test_fire_alert.py`).
- [pwa-decision.md](pwa-decision.md) — manifest-only PWA decision (2026-08-13).
- [pwa-close-out.md](pwa-close-out.md) — U5 close-out verification record.
- [indexnow.md](indexnow.md) — IndexNow ping key + env gating.
- [scraping-robots.md](scraping-robots.md) — aggregator robots posture (F252).
- [consent-sheet.md](consent-sheet.md) — NM-05 Consent Mode HAR matrix.
- [www-and-contact-fix.md](www-and-contact-fix.md) — apex/www + contact-page fix.

## Cross-repo owner flips (executed in their own repos)

- **Deals admin 2FA/Turnstile flip (F021, batch D2)** — env-gated
  DEFAULT-OFF; the full dated owner flip checklist lives in the Deals repo:
  `Discounts/docs/ops/admin-2fa.md` (repo `Discounts`, path
  `docs/ops/admin-2fa.md`). UE-side has no code surface for it — this
  pointer is the only UE deliverable. Precondition order matters there:
  Turnstile keys → encryption key → deploy → enroll TOTP → verify → flip.
