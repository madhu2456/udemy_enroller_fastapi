#!/usr/bin/env bash
#
# backup_sqlite.sh — SQLite online backup / restore with integrity check + retention.
#
# Usage:
#   scripts/backup_sqlite.sh                 # backup (default)
#   scripts/backup_sqlite.sh backup
#   CONFIRM=YES scripts/backup_sqlite.sh restore <file>
#   scripts/backup_sqlite.sh drill           # backup → integrity_check → discard
#
# Environment (optional):
#   DB_PATH              Explicit path to the SQLite file
#   DATABASE_URL         sqlite:///… URL (used when DB_PATH unset)
#   BACKUP_DIR           Destination directory (default: ./backups)
#   RETENTION_DAYS       Delete backups older than N days (default: 14)
#   RETENTION_COUNT      Keep at most N newest backups (default: 30; 0 = unlimited)
#   CONFIRM              Must be YES for restore (destructive)
#   RESTORE_APP_MARKER   If set and path exists, restore refuses (stop app first)
#
# Exit codes: 0 ok, 1 operational failure, 2 usage/config error.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

CMD="${1:-backup}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
RETENTION_COUNT="${RETENTION_COUNT:-30}"

usage() {
  cat <<'EOF' >&2
usage:
  scripts/backup_sqlite.sh [backup]
  CONFIRM=YES scripts/backup_sqlite.sh restore <backup-file>
  scripts/backup_sqlite.sh drill

Restore requires CONFIRM=YES. Stop the app first (e.g. docker compose stop web).
Optional: RESTORE_APP_MARKER=/path/to/marker — refuse while that file exists.
EOF
  exit 2
}

# Prefer sqlite3 CLI; fall back to Python's sqlite3.Connection.backup (same API).
SQLITE_BACKEND=""

require_sqlite() {
  if command -v sqlite3 >/dev/null 2>&1; then
    SQLITE_BACKEND="cli"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    SQLITE_BACKEND="python"
    return 0
  fi
  echo "error: need sqlite3 CLI or python3 for SQLite backup" >&2
  exit 2
}

sqlite_backup() {
  # Copy src -> dest via SQLite backup API (WAL-safe).
  local src="$1" dest="$2"
  if [[ "$SQLITE_BACKEND" == "cli" ]]; then
    sqlite3 "$src" ".backup '${dest}'"
  else
    python3 - "$src" "$dest" <<'PY'
import sqlite3, sys
src, dest = sys.argv[1], sys.argv[2]
src_conn = sqlite3.connect(src)
try:
    dest_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
finally:
    src_conn.close()
PY
  fi
}

sqlite_integrity() {
  local db="$1"
  if [[ "$SQLITE_BACKEND" == "cli" ]]; then
    sqlite3 "$db" "PRAGMA integrity_check;"
  else
    python3 - "$db" <<'PY'
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    print(conn.execute("PRAGMA integrity_check;").fetchone()[0])
finally:
    conn.close()
PY
  fi
}

# Resolve DATABASE_URL sqlite path (handles 3 or 4 slashes after sqlite:).
path_from_database_url() {
  local url="$1"
  case "$url" in
    sqlite:////*)
      # Absolute: sqlite:////app/data/x.db -> /app/data/x.db
      printf '%s\n' "/${url#sqlite:////}"
      ;;
    sqlite:///*)
      # Relative or absolute with 3 slashes: sqlite:///./x.db or sqlite:////a
      local rest="${url#sqlite:///}"
      if [[ "$rest" == /* ]]; then
        printf '%s\n' "$rest"
      else
        # Relative to project root
        printf '%s\n' "$ROOT/$rest"
      fi
      ;;
    *)
      return 1
      ;;
  esac
}

detect_db_path() {
  if [[ -n "${DB_PATH:-}" ]]; then
    printf '%s\n' "$DB_PATH"
    return 0
  fi

  if [[ -n "${DATABASE_URL:-}" ]]; then
    if path="$(path_from_database_url "$DATABASE_URL")"; then
      printf '%s\n' "$path"
      return 0
    fi
  fi

  # Load DATABASE_URL from .env without sourcing secrets into the shell namespace.
  if [[ -f "$ROOT/.env" ]]; then
    local env_url
    env_url="$(grep -E '^[[:space:]]*DATABASE_URL=' "$ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'")" || true
    if [[ -n "${env_url:-}" ]]; then
      if path="$(path_from_database_url "$env_url")"; then
        # Docker in-container path is not useful on the host; map common volume path.
        if [[ "$path" == /app/data/* ]] && [[ ! -f "$path" ]]; then
          local host_mapped="$ROOT/data/${path##*/}"
          if [[ -f "$host_mapped" ]]; then
            printf '%s\n' "$host_mapped"
            return 0
          fi
        else
          printf '%s\n' "$path"
          return 0
        fi
      fi
    fi
  fi

  # Common local / Docker-volume host paths (first existing wins).
  local candidate
  for candidate in \
    "$ROOT/data/udemy_enroller.db" \
    "$ROOT/udemy_enroller.db" \
    "/app/data/udemy_enroller.db"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  # Prefer data/ for new installs (matches docker-compose volume layout).
  printf '%s\n' "$ROOT/data/udemy_enroller.db"
}

integrity_check() {
  local db="$1"
  local result
  result="$(sqlite_integrity "$db")"
  if [[ "$result" != "ok" ]]; then
    echo "error: integrity_check failed for $db: $result" >&2
    return 1
  fi
  echo "integrity_check: ok ($db)"
}

apply_retention() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0

  if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [[ "$RETENTION_DAYS" -gt 0 ]]; then
    find "$dir" -maxdepth 1 -type f -name 'udemy_enroller-*.db' -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null || true
  fi

  if [[ "$RETENTION_COUNT" =~ ^[0-9]+$ ]] && [[ "$RETENTION_COUNT" -gt 0 ]]; then
    # shellcheck disable=SC2012
    local count
    count="$(ls -1t "$dir"/udemy_enroller-*.db 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "$count" -gt "$RETENTION_COUNT" ]]; then
      ls -1t "$dir"/udemy_enroller-*.db | tail -n +"$((RETENTION_COUNT + 1))" | while read -r old; do
        rm -f -- "$old"
        echo "retention: removed $old"
      done
    fi
  fi
}

do_backup() {
  local db="$1"
  local out_dir="${2:-$BACKUP_DIR}"
  local stamp backup_path tmp_path

  if [[ ! -f "$db" ]]; then
    echo "error: database not found: $db" >&2
    echo "hint: set DB_PATH or DATABASE_URL, or create data/udemy_enroller.db" >&2
    exit 1
  fi

  require_sqlite
  mkdir -p "$out_dir"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_path="${out_dir}/udemy_enroller-${stamp}.db"
  tmp_path="${backup_path}.tmp"

  # Online-safe copy via SQLite backup API (handles WAL).
  if ! sqlite_backup "$db" "$tmp_path"; then
    rm -f -- "$tmp_path"
    echo "error: sqlite backup failed" >&2
    exit 1
  fi

  if ! integrity_check "$tmp_path"; then
    rm -f -- "$tmp_path"
    exit 1
  fi

  mv -f -- "$tmp_path" "$backup_path"
  # Best-effort sidecar checksum (no secrets).
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$backup_path" >"${backup_path}.sha256"
  fi

  echo "backup written: $backup_path"
  apply_retention "$out_dir"
}

do_restore() {
  local backup_file="$1"
  local db="$2"

  # Critic C3: explicit confirmation required before any restore work.
  if [[ "${CONFIRM:-}" != "YES" ]]; then
    echo "error: refusing restore without CONFIRM=YES" >&2
    echo "hint: stop the app first, then: CONFIRM=YES $0 restore <backup-file>" >&2
    exit 2
  fi

  # Optional marker: refuse while app is still considered running.
  if [[ -n "${RESTORE_APP_MARKER:-}" && -e "${RESTORE_APP_MARKER}" ]]; then
    echo "error: app marker present (${RESTORE_APP_MARKER}) — stop the app and remove the marker before restore" >&2
    exit 1
  fi

  if [[ -z "$backup_file" ]]; then
    usage
  fi
  if [[ ! -f "$backup_file" ]]; then
    echo "error: backup file not found: $backup_file" >&2
    exit 1
  fi

  require_sqlite
  integrity_check "$backup_file"

  mkdir -p "$(dirname "$db")"
  local restore_tmp="${db}.restore.tmp"
  rm -f -- "$restore_tmp"

  # Prefer .backup into a temp file then atomic replace so a failed restore
  # never truncates the live DB mid-write.
  if ! sqlite_backup "$backup_file" "$restore_tmp"; then
    rm -f -- "$restore_tmp"
    echo "error: restore backup failed" >&2
    exit 1
  fi
  integrity_check "$restore_tmp"

  # Pre-restore copy before any live replace / WAL drop.
  if [[ -f "$db" ]]; then
    local pre_stamp
    pre_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a -- "$db" "${db}.pre-restore-${pre_stamp}"
    echo "pre-restore copy: ${db}.pre-restore-${pre_stamp}"
  fi

  # Confirmed replace of main file first; only then drop WAL/SHM.
  mv -f -- "$restore_tmp" "$db"
  # Drop stale WAL/SHM so the restored main file is authoritative.
  rm -f -- "${db}-wal" "${db}-shm"
  echo "restored: $db from $backup_file"
  echo "note: restart the app (e.g. docker compose start web) after restore."
}

do_drill() {
  local db="$1"
  local drill_dir
  drill_dir="$(mktemp -d "${TMPDIR:-/tmp}/udemy-enroller-backup-drill.XXXXXX")"
  # shellcheck disable=SC2064
  trap "rm -rf -- '$drill_dir'" RETURN

  echo "=== backup drill (temporary dir: $drill_dir) ==="
  do_backup "$db" "$drill_dir"
  local latest
  latest="$(ls -1t "$drill_dir"/udemy_enroller-*.db | head -n1)"
  integrity_check "$latest"
  # Round-trip restore into a throwaway file
  local drill_restore="$drill_dir/restored.db"
  sqlite_backup "$latest" "$drill_restore"
  integrity_check "$drill_restore"
  echo "drill passed: backup + integrity_check + restore round-trip OK"
}

DB="$(detect_db_path)"
echo "database: $DB"

case "$CMD" in
  backup)
    do_backup "$DB"
    ;;
  restore)
    do_restore "${2:-}" "$DB"
    ;;
  drill)
    do_drill "$DB"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "error: unknown command: $CMD" >&2
    usage
    ;;
esac
