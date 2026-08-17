# SQLite backup & restore (ops)

Runbook for **F065** automated SQLite backup/restore of the Udemy Enroller app
database. Prefer the scripted path over ad-hoc `cp` so backups are
WAL-safe, integrity-checked, and retention-pruned.

## What is backed up

| Asset | Path (local) | Path (Docker) |
|-------|----------------|---------------|
| App DB | `data/udemy_enroller.db` or `./udemy_enroller.db` | volume `app-data` → `/app/data/udemy_enroller.db` |
| Public coupon catalog | `public_deals.json` (optional; not in the SQLite script) | `/app/data/public_deals.json` |

User sessions, encrypted Udemy cookies, enrollment history, and settings live
in the SQLite DB. The backup script only copies the DB file.

## Pin Alembic to the inspected live file

If both `udemy_enroller.db` and `data/udemy_enroller.db` exist, do **not** run
bare `alembic upgrade head`. Inspect first, then set `DB_PATH` to the absolute
live path (`DB_PATH=$LIVE_ABS`) for backup and the pinned upgrade helper:

```bash
LIVE_ABS=/absolute/path/to/the/inspected/udemy_enroller.db
python scripts/inspect_sqlite_schema.py "$LIVE_ABS"
DB_PATH=$LIVE_ABS ./scripts/backup_sqlite.sh backup
python scripts/alembic_upgrade_pinned.py "$LIVE_ABS" head
```

## Production host layout (as of 2026-08-16)

On the production single host (Netcup/DO box), Enroller and Deals share the box.

- Live DB: Docker **named volume** `app-data` (`udemy-enroller_app-data`). There is **no** `/opt/udemy-enroller/data`.
- Backups: host `/var/backups/udemy-enroller`. Cron copies from the volume `_data` file (`…/udemy-enroller_app-data/_data/udemy_enroller.db`).
- F011 last-success **proven** ~2026-08-16T07:39:19Z: newest `/var/backups/udemy-enroller/udemy_enroller-20260816T013001Z.db`, age **6.16 h**, `PRAGMA integrity_check=ok`, `MAX_AGE_HOURS=26` freshness exit 0. Cron present (2026-08-15). Restore **not** run.
- Host `LAST_SUCCESS` stamp files are **absent** (deployed scripts predate the local stamp patch). Proof is newest-file mtime + integrity + freshness.
- Documented `deploy.sh --install-backup-cron` installs **host bind paths** (`/opt/udemy-enroller/data` → `/opt/udemy-enroller/backups`) and does **not** match this host. **Do not** run it blindly — leave the working `_data` → `/var/backups/udemy-enroller` cron in place.

## Automated backup

```bash
# From the repo root (or app host with the project tree)
chmod +x scripts/backup_sqlite.sh   # once
./scripts/backup_sqlite.sh backup --allow-plaintext   # plaintext (explicit flag, F235)
# …or with encryption:
# BACKUP_ENCRYPTION_KEY=<key> ./scripts/backup_sqlite.sh backup
```

The script:

1. **Detects** the DB path from `DB_PATH`, `DATABASE_URL`, `.env`, then common
   candidates (`data/udemy_enroller.db`, `udemy_enroller.db`, Docker
   `/app/data/…` mapped to host `data/…`).
2. Runs **`sqlite3 .backup`** (online-safe, WAL-aware) into a `.tmp` file
   under `backups/`.
3. Runs **`PRAGMA integrity_check`** on the tmp copy (fails closed if not `ok`).
4. **Encrypts when `BACKUP_ENCRYPTION_KEY` is set** (F235): `openssl enc
   -aes-256-cbc -pbkdf2 -salt`, key read via `-pass env:` (never logged,
   never in argv), output `backups/udemy_enroller-<UTC-timestamp>.db.enc`.
   **Without a key, plaintext writes are REFUSED unless `--allow-plaintext`
   is passed** (fail-closed). Then `mv` to the final artifact.
5. Writes **`LAST_SUCCESS`** in the same `BACKUP_DIR` (ISO-8601 UTC + backup
   path) immediately after the good `mv`.
6. Writes an optional **SHA-256** sidecar (`.sha256`, checksums the final
   artifact — plaintext or encrypted) best-effort; a checksum failure does not
   skip `LAST_SUCCESS`.
7. Applies **retention**: default delete backups older than **14 days**, keep at
   most **30** newest files (`RETENTION_DAYS`, `RETENTION_COUNT`). Retention
   counts **plain and encrypted** backups and removes their `.sha256`
   sidecars together with the backup (F235).

### Encryption key handling (F235 — read before enabling)

- Set `BACKUP_ENCRYPTION_KEY` **on the host only** (never in git, never in a
  committed `.env.example` value). The script never logs or echoes the key.
- **Duplicate the key** in your password manager (or equivalent offline
  vault) BEFORE enabling encryption. **Key loss = backup loss** — an
  encrypted backup cannot be restored without the exact key.
- Restore auto-detects encrypted backups (`.db.enc` suffix or the OpenSSL
  `Salted__` magic header) and decrypts them with the same environment
  variable. Legacy plaintext backups restore unchanged (backward compat).
- If you rotate the key, old `.db.enc` files remain restorable only with the
  old key — keep both during the transition, then re-encrypt or prune.

### Cron example (host) — copy-paste

Install a daily backup plus a freshness check (alerts if backups go stale).
Adjust paths, user, and log destinations for your host.

```cron
# Udemy Enroller — SQLite backup (daily 03:15 UTC)
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# 1) Online-safe backup + integrity check + retention prune
#    F235: BACKUP_ENCRYPTION_KEY unset on this host → pass --allow-plaintext
#    explicitly (fail-closed). Once the owner sets BACKUP_ENCRYPTION_KEY
#    (and duplicates it in the password manager), drop --allow-plaintext.
15 3 * * * cd /opt/udemy-enroller && DB_PATH=/opt/udemy-enroller/data/udemy_enroller.db BACKUP_DIR=/opt/udemy-enroller/backups ./scripts/backup_sqlite.sh backup --allow-plaintext >>/var/log/udemy-enroller-backup.log 2>&1

# 2) Freshness gate (fail if newest backup older than 26h; max age override via MAX_AGE_HOURS)
30 3 * * * BACKUP_DIR=/opt/udemy-enroller/backups MAX_AGE_HOURS=26 /opt/udemy-enroller/scripts/verify_backup_freshness.sh >>/var/log/udemy-enroller-backup.log 2>&1
```

> **F235 note:** the example above keeps `--allow-plaintext` until the owner
> sets `BACKUP_ENCRYPTION_KEY` on the host. Without the flag (and without a
> key) the backup command now **refuses to run** — that is intentional
> fail-closed behavior. See **Encryption key handling** above. The freshness
> glob covers both `*.db` and `*.db.enc`.

**One-shot install (F-ENRL-K01):** on a **fresh** droplet whose live DB is a
host file at `/opt/udemy-enroller/data/udemy_enroller.db`, `deploy.sh` can
install those two entries idempotently — re-running never duplicates them.
**Do not** run this on the 2026-08-16 production host (named volume `app-data`,
backups at `/var/backups/udemy-enroller`) — see **Production host layout**.

```bash
./scripts/deploy.sh --install-backup-cron
# → "Installed backup + freshness cron entries for crontab of: root"
# Re-run → "Backup cron already installed — nothing to do (idempotent)."
crontab -l | grep udemy-enroller-backup
```

The installed entries use host paths (`/opt/udemy-enroller/data/udemy_enroller.db`).
If the DB lives inside the Docker named volume (`app-data`), sync it out first
or point `DB_PATH` at your bind-mounted copy — see "Docker volume" below.
`deploy.sh --install-backup-cron` exits after installing; it does not deploy.

One-shot install helpers (as root or with sudo; edit paths first):

```bash
# Ensure executable + log file
chmod +x /opt/udemy-enroller/scripts/backup_sqlite.sh \
         /opt/udemy-enroller/scripts/verify_backup_freshness.sh
touch /var/log/udemy-enroller-backup.log
chown deploy:deploy /var/log/udemy-enroller-backup.log   # or your app user

# Install crontab for the app user (example: deploy)
sudo -u deploy crontab -e
# paste the two cron lines above, save

# Or system-wide drop-in:
# sudo tee /etc/cron.d/udemy-enroller-backup <<'EOF'
# 15 3 * * * deploy cd /opt/udemy-enroller && DB_PATH=... BACKUP_DIR=... ./scripts/backup_sqlite.sh backup --allow-plaintext >>/var/log/udemy-enroller-backup.log 2>&1
# 30 3 * * * deploy BACKUP_DIR=/opt/udemy-enroller/backups MAX_AGE_HOURS=26 /opt/udemy-enroller/scripts/verify_backup_freshness.sh >>/var/log/udemy-enroller-backup.log 2>&1
# EOF
```

Manual smoke after install:

```bash
cd /opt/udemy-enroller
DB_PATH=/opt/udemy-enroller/data/udemy_enroller.db BACKUP_DIR=/opt/udemy-enroller/backups ./scripts/backup_sqlite.sh backup --allow-plaintext
BACKUP_DIR=/opt/udemy-enroller/backups MAX_AGE_HOURS=26 ./scripts/verify_backup_freshness.sh
# expect exit 0 and a line like: OK: newest backup age …
```

### Docker volume (host-side)

If the compose data volume is bind-mounted or you copy the file out first:

```bash
# One-shot copy from the running container, then scripted backup of the host file
docker compose cp web:/app/data/udemy_enroller.db ./data/udemy_enroller.db
DB_PATH=./data/udemy_enroller.db ./scripts/backup_sqlite.sh backup
```

Or run the script **inside** the container (needs `sqlite3` in the image):

```bash
docker compose exec web bash -lc 'DB_PATH=/app/data/udemy_enroller.db BACKUP_DIR=/app/data/backups scripts/backup_sqlite.sh backup'
```

> The production slim image may not include `sqlite3` or the script path until
> you add them. Host-side backup of a `docker compose cp` snapshot is the
> simplest default.

## Restore

**Always stop writers** before replacing the live DB (app process and/or
`docker compose stop web coupon-checker`).

`CONFIRM=YES` is **required**. Without it the script refuses (critic C3).
Optional: set `RESTORE_APP_MARKER=/path/to/marker` and leave that file in place
while the app is running; remove it after stop — restore refuses while the
marker exists.

```bash
# Integrity-check the chosen backup, write a pre-restore copy of the live DB,
# then replace the DB and drop stale -wal/-shm sidecars (WAL only after replace).
# Encrypted backups (*.db.enc) are auto-detected and decrypted with
# BACKUP_ENCRYPTION_KEY (F235); legacy plaintext backups restore unchanged.
CONFIRM=YES ./scripts/backup_sqlite.sh restore backups/udemy_enroller-YYYYMMDDTHHMMSSZ.db
# encrypted: CONFIRM=YES BACKUP_ENCRYPTION_KEY=<key> ./scripts/backup_sqlite.sh restore backups/udemy_enroller-YYYYMMDDTHHMMSSZ.db.enc

# Restart
# local:  python run.py
# docker: docker compose start web coupon-checker
#         or: docker compose up -d
```

Verify:

```bash
sqlite3 "$DB_PATH" "PRAGMA integrity_check;"
# expect: ok
curl -sf http://127.0.0.1:8000/api/health
```

## Restore drill (non-destructive)

Proves backup + integrity + restore round-trip without touching the live DB:

```bash
# F235: pass --allow-plaintext when BACKUP_ENCRYPTION_KEY is unset
./scripts/backup_sqlite.sh drill --allow-plaintext
# encrypted drill: BACKUP_ENCRYPTION_KEY=<key> ./scripts/backup_sqlite.sh drill
```

Run a drill after first deploy and after any change to volume mounts or
`DATABASE_URL`. Record the date in the drill log below.

### Drill log (owner checklist — F-ENRL-K01 / F210)

| Date (UTC) | Environment | Result | Offsite copy verified | Notes |
|------------|-------------|--------|-----------------------|-------|
| 2026-08-16T17:38:29Z | local scratch copy of host backup `udemy_enroller-20260816T141357Z.db` | **passed** — `CONFIRM=YES BACKUP_DIR=/tmp/ue-drill-20260816T173829Z/ DB_PATH=/tmp/ue-drill-20260816T173829Z/restored.db restore <scratch>`; integrity ok; restored DB sane (19 users / 229 runs / 17704 courses); repo backup sha256 `7f9f6f07…0812b` unchanged before/after | ☐ | F210 restore-on-copy drill; measured RTO **0.39 s** |
|            | droplet     |        |                       | first drill after deploy |
|            |             |        |                       | after any volume/DATABASE_URL change |

> A drill that fails (non-`ok` integrity, restore error) is a **P1**: do not
> rely on backups until the cause is found and the drill passes twice in a row.

## Offsite copies (F-ENRL-K01)

On-site backups protect against file loss, not droplet failure. Maintain at
least one offsite copy of the backup directory, refreshed at least daily.
Two supported patterns — pick one (or both):

### Pattern A — rclone (simple, any object store)

```bash
# One-time setup (on the droplet):
apt-get install -y rclone
rclone config   # remote name, e.g. "s3-backups" (S3/B2/Drive/…)

# Sync today's backups (add to the same crontab, after the backup job):
30 3 * * * rclone sync /opt/udemy-enroller/backups s3-backups:udemy-enroller-backups --include "udemy-enroller-*.db" --include "*.sha256" --transfers 4 >>/var/log/udemy-enroller-backup.log 2>&1

# Restore from offsite:
rclone copy s3-backups:udemy-enroller-backups/udemy-enroller-<timestamp>.db ./backups/
# then run the normal restore flow (CONFIRM=YES … restore <file>)
```

### Pattern B — restic (encrypted, versioned, deduplicated)

```bash
# One-time setup:
apt-get install -y restic
restic init --repo sftp:backup-host:/srv/restic/udemy-enroller   # or s3:…, b2:…
# RESTIC_PASSWORD must live in root's environment (e.g. /root/.restic-env, mode 600)

# Daily snapshot (after the backup job):
30 3 * * * . /root/.restic-env && restic backup /opt/udemy-enroller/backups --tag udemy-enroller --quiet >>/var/log/udemy-enroller-backup.log 2>&1

# Restore from offsite:
restic snapshots --tag udemy-enroller
restic restore latest --target /opt/udemy-enroller/restore
# then run the normal restore flow with the restored file
```

Security: backups contain **encrypted** session cookies and PII-ish account
metadata — the offsite target must have the same access controls as
production (private bucket, SSE/encryption at rest, credentials in
root-only files, never in git).

## Environment reference

| Variable | Default | Meaning |
|----------|---------|---------|
| `DB_PATH` | auto-detect | Explicit SQLite file path |
| `DATABASE_URL` | from env/`.env` | `sqlite:///…` used when `DB_PATH` unset |
| `BACKUP_DIR` | `./backups` | Output directory for `backup` (`LAST_SUCCESS` is written here after integrity_check=ok) |
| `RETENTION_DAYS` | `14` | Delete files older than N days (`0` disables) |
| `RETENTION_COUNT` | `30` | Keep newest N backups (`0` unlimited) |
| `CONFIRM` | (unset) | Must be `YES` for `restore` |
| `RESTORE_APP_MARKER` | (unset) | If set and path exists, restore refuses |
| `BACKUP_ENCRYPTION_KEY` | (unset) | F235: when set, backups are encrypted `*.db.enc` (openssl AES-256-CBC pbkdf2; key via `-pass env:`, never logged). When unset, plaintext writes require `--allow-plaintext` (fail-closed). Encrypted restores auto-decrypt with this key; legacy plaintext restores always work |
| `--allow-plaintext` | — | Explicit flag to write an unencrypted backup when `BACKUP_ENCRYPTION_KEY` is unset |
| `MAX_AGE_HOURS` | `26` | Freshness check only (`verify_backup_freshness.sh`) |
| `BACKUP_GLOB` | `udemy_enroller-*.db*` | Freshness check filename glob — covers plaintext `*.db` and encrypted `*.db.enc` backups (plus sidecars) |

## Freshness verification

```bash
# Exit 0 if newest backup under BACKUP_DIR is younger than MAX_AGE_HOURS
BACKUP_DIR=./backups MAX_AGE_HOURS=26 ./scripts/verify_backup_freshness.sh
```

Wire this into cron after the backup job (see Cron example above) so silent backup failures surface as non-zero exit codes in logs/monitoring.

## Manual fallback (not preferred)

```bash
# Local
cp udemy_enroller.db udemy_enroller.db.backup

# Docker
docker compose cp web:/app/data/udemy_enroller.db ./udemy_enroller.db.backup
```

Manual copies can race with WAL writers. Prefer `scripts/backup_sqlite.sh`.

## Security notes

- Backup files contain **encrypted** session cookies and PII-ish account
  metadata — store them with the same access controls as production data.
- F235: set `BACKUP_ENCRYPTION_KEY` and **duplicate it in the password
  manager before enabling encryption** — key loss = backup loss. Plaintext
  copies require the explicit `--allow-plaintext` flag.
- Do **not** commit backups to git; keep `backups/` out of the deploy rsync
  payload if it sits under the app tree (add to excludes if needed).
- Never log or paste DB contents into tickets.
