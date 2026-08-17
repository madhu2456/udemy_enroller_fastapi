#!/usr/bin/env bash
#
# verify_backup_freshness.sh — fail if the newest backup is older than MAX_AGE_HOURS.
#
# Usage:
#   scripts/verify_backup_freshness.sh
#   BACKUP_DIR=/path/to/backups MAX_AGE_HOURS=26 scripts/verify_backup_freshness.sh
#   BACKUP_GLOB='udemy_enroller-*.db' scripts/verify_backup_freshness.sh
#
# Environment:
#   BACKUP_DIR      Directory of backup files (default: ./backups)
#   MAX_AGE_HOURS   Maximum age of newest matching file (default: 26)
#   BACKUP_GLOB     Filename glob under BACKUP_DIR (default: udemy_enroller-*.db*)
#                   Matches plaintext (*.db), encrypted (*.db.enc) backups and
#                   their *.sha256 sidecars; the newest artifact wins.
#
# Exit codes: 0 fresh, 1 stale/missing/error, 2 usage.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"
BACKUP_GLOB="${BACKUP_GLOB:-udemy_enroller-*.db*}"

usage() {
  cat <<'EOF' >&2
usage:
  BACKUP_DIR=./backups MAX_AGE_HOURS=26 scripts/verify_backup_freshness.sh

Environment:
  BACKUP_DIR      Backup directory (default: <repo>/backups)
  MAX_AGE_HOURS   Fail if newest backup older than this many hours (default: 26)
  BACKUP_GLOB     Glob for backup files (default: udemy_enroller-*.db* — covers
                  plaintext .db and encrypted .db.enc backups plus sidecars)
EOF
  exit 2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

if ! [[ "$MAX_AGE_HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERROR: MAX_AGE_HOURS must be a non-negative number (got: $MAX_AGE_HOURS)" >&2
  exit 2
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "ERROR: BACKUP_DIR does not exist: $BACKUP_DIR" >&2
  exit 1
fi

# shellcheck disable=SC2086
mapfile -t candidates < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name "$BACKUP_GLOB" 2>/dev/null | sort || true)

if [[ ${#candidates[@]} -eq 0 ]]; then
  echo "ERROR: no backups matching '$BACKUP_GLOB' in $BACKUP_DIR" >&2
  exit 1
fi

newest=""
newest_mtime=0
for f in "${candidates[@]}"; do
  # Prefer GNU/BSD stat; fall back to python for portability.
  if mtime=$(stat -c %Y "$f" 2>/dev/null); then
    :
  elif mtime=$(stat -f %m "$f" 2>/dev/null); then
    :
  else
    mtime=$(python3 -c 'import os,sys; print(int(os.path.getmtime(sys.argv[1])))' "$f")
  fi
  if [[ "$mtime" -gt "$newest_mtime" ]]; then
    newest_mtime=$mtime
    newest=$f
  fi
done

now=$(date +%s)
age_sec=$((now - newest_mtime))
max_sec=$(python3 -c "print(int(float('$MAX_AGE_HOURS') * 3600))")
age_hours=$(python3 -c "print(round($age_sec / 3600.0, 2))")

if [[ "$age_sec" -gt "$max_sec" ]]; then
  echo "FAIL: newest backup is ${age_hours}h old (limit ${MAX_AGE_HOURS}h): $newest" >&2
  exit 1
fi

echo "OK: newest backup age ${age_hours}h (limit ${MAX_AGE_HOURS}h): $newest"
exit 0
