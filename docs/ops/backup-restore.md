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

## Automated backup

```bash
# From the repo root (or app host with the project tree)
chmod +x scripts/backup_sqlite.sh   # once
./scripts/backup_sqlite.sh          # or: backup
```

The script:

1. **Detects** the DB path from `DB_PATH`, `DATABASE_URL`, `.env`, then common
   candidates (`data/udemy_enroller.db`, `udemy_enroller.db`, Docker
   `/app/data/…` mapped to host `data/…`).
2. Runs **`sqlite3 .backup`** (online-safe, WAL-aware) into
   `backups/udemy_enroller-<UTC-timestamp>.db`.
3. Runs **`PRAGMA integrity_check`** on the copy (fails closed if not `ok`).
4. Writes an optional **SHA-256** sidecar (`.sha256`).
5. Applies **retention**: default delete backups older than **14 days**, keep at
   most **30** newest files (`RETENTION_DAYS`, `RETENTION_COUNT`).

### Cron example (host)

```cron
# Daily 03:15 UTC; logs to syslog-friendly stdout
15 3 * * * cd /opt/udemy-enroller && DB_PATH=/opt/udemy-enroller/data/udemy_enroller.db ./scripts/backup_sqlite.sh backup >>/var/log/udemy-enroller-backup.log 2>&1
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
CONFIRM=YES ./scripts/backup_sqlite.sh restore backups/udemy_enroller-YYYYMMDDTHHMMSSZ.db

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
./scripts/backup_sqlite.sh drill
```

Run a drill after first deploy and after any change to volume mounts or
`DATABASE_URL`. Record the date in your ops checklist.

## Environment reference

| Variable | Default | Meaning |
|----------|---------|---------|
| `DB_PATH` | auto-detect | Explicit SQLite file path |
| `DATABASE_URL` | from env/`.env` | `sqlite:///…` used when `DB_PATH` unset |
| `BACKUP_DIR` | `./backups` | Output directory for `backup` |
| `RETENTION_DAYS` | `14` | Delete files older than N days (`0` disables) |
| `RETENTION_COUNT` | `30` | Keep newest N backups (`0` unlimited) |
| `CONFIRM` | (unset) | Must be `YES` for `restore` |
| `RESTORE_APP_MARKER` | (unset) | If set and path exists, restore refuses |

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
- Do **not** commit backups to git; keep `backups/` out of the deploy rsync
  payload if it sits under the app tree (add to excludes if needed).
- Never log or paste DB contents into tickets.
