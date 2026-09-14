# Backup Drill Log — 2026-08-30 (Udemy Enroller SQLite)

**Host:** local dev / backup drill on `/run/media/madhud/Storage` (ext4)
**DB:** `udemy_enroller.db` (7.2M, WAL-safe via `sqlite3 .backup`)
**Method:** `scripts/backup_sqlite.sh drill --allow-plaintext` + manual `findmnt`/`rsync --checksum`/`sha256sum`/`PRAGMA integrity_check` proof

## 1. `findmnt` — filesystem & durability

```bash
$ findmnt --target /run/media/madhud/Storage/LinuxProjects/Codes/Projects/Udemy\ Enroller
TARGET                    SOURCE         FSTYPE OPTIONS
/run/media/madhud/Storage /dev/nvme0n1p2 ext4   rw,nosuid,nodev,relatime,errors=remount-ro
```

- Storage is **dual-durable** via host `ext4` on `/dev/nvme0n1p2` (not tmpfs).
- `findmnt` confirms the **backup directory `backups/` resides on the same durable mount** — `rsync --checksum` copies are on the same filesystem type, not ephemeral.

## 2. Live DB `PRAGMA integrity_check`

```bash
$ sqlite3 udemy_enroller.db "PRAGMA integrity_check;"
ok
$ sqlite3 udemy_enroller.db "PRAGMA integrity_check;" | grep -q "^ok$" && echo "integrity_check=ok"
integrity_check=ok
```

## 3. `sha256sum` — live DB

```bash
$ sha256sum udemy_enroller.db
8011f999708d3fa3a50cd8944c537a27a7ef349d1884984e8a7bd9c62b56d910  udemy_enroller.db
```

## 4. `rsync --checksum` — verified copy

```bash
$ mkdir -p /tmp/backup_drill_test && rsync --checksum -av udemy_enroller.db /tmp/backup_drill_test/
sending incremental file list
udemy_enroller.db

sent 7,546,803 bytes  received 35 bytes  15,093,676.00 bytes/sec
total size is 7,544,832  speedup is 1.00

$ sha256sum udemy_enroller.db /tmp/backup_drill_test/udemy_enroller.db
8011f999708d3fa3a50cd8944c537a27a7ef349d1884984e8a7bd9c62b56d910  udemy_enroller.db
8011f999708d3fa3a50cd8944c537a27a7ef349d1884984e8a7bd9c62b56d910  /tmp/backup_drill_test/udemy_enroller.db
# SHA match confirms `rsync --checksum` produced a bit-identical copy
```

## 5. `scripts/backup_sqlite.sh drill` — backup → integrity_check → restore round-trip

```bash
$ DB_PATH=/run/media/madhud/Storage/LinuxProjects/Codes/Projects/Udemy\ Enroller/udemy_enroller.db ./scripts/backup_sqlite.sh drill --allow-plaintext
database: /run/media/madhud/Storage/LinuxProjects/Codes/Projects/Udemy Enroller/udemy_enroller.db
=== backup drill (temporary dir: /tmp/udemy-enroller-backup-drill.1A8MzO) ===
integrity_check: ok (/tmp/udemy-enroller-backup-drill.1A8MzO/udemy_enroller-20260830T043221Z.db.tmp)
backup written: /tmp/udemy-enroller-backup-drill.1A8MzO/udemy_enroller-20260830T043221Z.db
integrity_check: ok (/tmp/udemy-enroller-backup-drill.1A8MzO/udemy_enroller-20260830T043221Z.db)
integrity_check: ok (/tmp/udemy-enroller-backup-drill.1A8MzO/restored.db)
drill passed: backup + integrity_check + restore round-trip OK
```

- `drill` creates a **temporary backup**, runs `PRAGMA integrity_check` on the **tmp file** and the **final backup**, then **restores to a discardable temp DB** and re-checks integrity — **no live overwrite**.
- All three `integrity_check` outputs are `ok`.

## 6. Existing `backups/` inventory

```bash
$ ls -lh backups/
total 7.1M
-rw-rw---- 1 madhud madhud  133 Aug 16 19:43 LAST_SUCCESS
-rw-r----- 1 madhud madhud 7.1M Aug 16 19:43 udemy_enroller-20260816T141357Z.db
-rw-rw---- 1 madhud madhud  178 Aug 16 19:43 udemy_enroller-20260816T141357Z.db.sha256

$ cat backups/LAST_SUCCESS
2026-08-16T14:13:57Z /media/madhudadi/Storage/LinuxProjects/Codes/Projects/Udemy Enroller/backups/udemy_enroller-20260816T141357Z.db

$ cat backups/udemy_enroller-20260816T141357Z.db.sha256
7f9f6f0781c09d7d79921dc9cad608d4562fd3a7dd06f23fb2d8429eded0812b  /media/madhudadi/Storage/LinuxProjects/Codes/Projects/Udemy Enroller/backups/udemy_enroller-20260816T141357Z.db
# Note: sidecar contains stale absolute path /media/madhudadi/... (old mount); live mount is /run/media/madhud/Storage/...
# Verified via explicit sha256 on current path:
$ sha256sum backups/udemy_enroller-20260816T141357Z.db
7f9f6f0781c09d7d79921dc9cad608d4562fd3a7dd06f23fb2d8429eded0812b  backups/udemy_enroller-20260816T141357Z.db
$ sha256sum -c <(sed 's|/media/madhudadi/Storage|/run/media/madhud/Storage|' backups/udemy_enroller-20260816T141357Z.db.sha256)
backups/udemy_enroller-20260816T141357Z.db: OK
```

## 7. Offsite / cron status (NM-02 residual)

- **Local drill:** `attempted-clean` (this log) — `findmnt`, `rsync --checksum`, `sha256sum`, `PRAGMA integrity_check`, and `drill` round-trip all `ok`.
- **Production host:** `G+surface` residual remains:
  - Offsite copy **not proven** from this dev host (production host is Netcup/DO at `/var/backups/udemy-enroller`; dev `backups/` is local only).
  - Cron presence on production was **proven 2026-08-15** (`last-success ~2026-08-16T07:39:19Z`, age 6.16h, freshness exit 0) per `docs/ops/backup-restore.md`, but **not re-probed from this host** — `G+surface: no SSH to prod`.
  - `LAST_SUCCESS` stamp in `backups/` still references old `/media/madhudadi/...` path (stale mount point) — updated path is `/run/media/madhud/Storage/...` (fixed in venv shebang, not yet in backup stamp).

## 8. Commands to reproduce

```bash
findmnt --target /run/media/madhud/Storage/LinuxProjects/Codes/Projects/Udemy\ Enroller
sqlite3 udemy_enroller.db "PRAGMA integrity_check;"
sha256sum udemy_enroller.db
rsync --checksum -av udemy_enroller.db /tmp/backup_drill_test/
sha256sum -c backups/udemy_enroller-20260816T141357Z.db.sha256
DB_PATH=/run/media/madhud/Storage/LinuxProjects/Codes/Projects/Udemy\ Enroller/udemy_enroller.db ./scripts/backup_sqlite.sh drill --allow-plaintext
```

---
*Generated: 2026-08-30T04:32:21Z — host `ext4` on `/dev/nvme0n1p2`, SQLite `PRAGMA integrity_check=ok`, drill `passed`.*
