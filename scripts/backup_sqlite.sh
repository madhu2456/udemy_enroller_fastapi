#!/usr/bin/env bash
#
# backup_sqlite.sh — SQLite online backup / restore with integrity check + retention.
#
# Usage:
#   scripts/backup_sqlite.sh [--allow-plaintext]   # backup (default)
#   scripts/backup_sqlite.sh backup --allow-plaintext
#   CONFIRM=YES scripts/backup_sqlite.sh restore <file>
#   scripts/backup_sqlite.sh drill --allow-plaintext   # backup → integrity_check → restore → discard
#
# Environment (optional):
#   DB_PATH              Explicit path to the SQLite file
#   DATABASE_URL         sqlite:///… URL (used when DB_PATH unset)
#   BACKUP_DIR           Destination directory (default: ./backups)
#   RETENTION_DAYS       Delete backups older than N days (default: 14)
#   RETENTION_COUNT      Keep at most N newest backups (default: 30; 0 = unlimited)
#   CONFIRM              Must be YES for restore (destructive)
#   RESTORE_APP_MARKER   If set and path exists, restore refuses (stop app first)
#   BACKUP_ENCRYPTION_KEY
#                        Key for openssl AES-256-CBC (pbkdf2) encryption. When
#                        SET, backups are written as *.db.enc and restore
#                        auto-decrypts *.db.enc (suffix or "Salted__" magic).
#                        When ABSENT, plaintext writes are REFUSED unless
#                        --allow-plaintext is passed (fail-closed, F235).
#                        The key VALUE is never logged or echoed; it is passed
#                        to openssl via -pass env: (never in argv/ps).
#                        Key loss = backup loss — keep a copy in a password
#                        manager.
#
# After integrity_check=ok and mv of the .tmp to the final *.db (or *.db.enc),
# writes LAST_SUCCESS (ISO-8601 UTC + backup path) immediately. sha256 sidecar
# is best-effort and must not skip the stamp. Not written if the check fails.
#
# Exit codes: 0 ok, 1 operational failure, 2 usage/config error.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

CMD="${1:-backup}"
case "$CMD" in
  --allow-plaintext) CMD="backup" ;;
esac
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
RETENTION_COUNT="${RETENTION_COUNT:-30}"

# Fail-closed plaintext policy (F235): explicit --allow-plaintext flag only.
ALLOW_PLAINTEXT=0
for arg in "$@"; do
  case "$arg" in
    --allow-plaintext) ALLOW_PLAINTEXT=1 ;;
  esac
done

# Encrypted output when a key is present; the key itself is never echoed.
ENCRYPT_BACKUP=0
if [[ -n "${BACKUP_ENCRYPTION_KEY:-}" ]]; then
  ENCRYPT_BACKUP=1
fi

usage() {
  cat <<'EOF' >&2
usage:
  scripts/backup_sqlite.sh [--allow-plaintext]   # backup
  CONFIRM=YES scripts/backup_sqlite.sh restore <backup-file>
  scripts/backup_sqlite.sh drill --allow-plaintext

Restore requires CONFIRM=YES. Stop the app first (e.g. docker compose stop web).
Optional: RESTORE_APP_MARKER=/path/to/marker — refuse while that file exists.

Plaintext policy (F235): with BACKUP_ENCRYPTION_KEY set, backups are written
encrypted (*.db.enc). Without a key, plaintext writes are refused unless the
--allow-plaintext flag is passed. Encrypted backups restore automatically when
BACKUP_ENCRYPTION_KEY is set; legacy plaintext backups still restore.
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

require_openssl() {
  if ! command -v openssl >/dev/null 2>&1; then
    echo "error: BACKUP_ENCRYPTION_KEY is set but openssl is not installed" >&2
    exit 2
  fi
}

# Encrypt a plaintext SQLite file to *.db.enc. The key is read from the
# environment via `-pass env:BACKUP_ENCRYPTION_KEY` so it never appears in the
# process list, argv, or logs (F235). Never log the key value.
encrypt_backup_file() {
  local src="$1" dest="$2"
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_ENCRYPTION_KEY \
    -in "$src" -out "$dest"
}

decrypt_backup_file() {
  local src="$1" dest="$2"
  openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_KEY \
    -in "$src" -out "$dest"
}

# Auto-detect an encrypted backup by suffix (*.db.enc / *.enc) or by the
# OpenSSL salted magic header ("Salted__"). Legacy plaintext SQLite backups
# start with "SQLite format 3" and are never misdetected.
is_encrypted_backup() {
  local file="$1"
  case "$file" in
    *.db.enc|*.enc) return 0 ;;
  esac
  if [[ "$(head -c 8 "$file" 2>/dev/null)" == "Salted__" ]]; then
    return 0
  fi
  return 1
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

  # F235: retention covers plaintext (.db) AND encrypted (.db.enc) backups,
  # plus their .sha256 sidecars (deleted with the backup they checksum).
  if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [[ "$RETENTION_DAYS" -gt 0 ]]; then
    find "$dir" -maxdepth 1 -type f \
      \( -name 'udemy_enroller-*.db' \
         -o -name 'udemy_enroller-*.db.enc' \
         -o -name 'udemy_enroller-*.db.sha256' \
         -o -name 'udemy_enroller-*.db.enc.sha256' \) \
      -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null || true
  fi

  if [[ "$RETENTION_COUNT" =~ ^[0-9]+$ ]] && [[ "$RETENTION_COUNT" -gt 0 ]]; then
    # shellcheck disable=SC2012
    # Single glob (plain + .enc + sidecars) filtered to backups only: a
    # multi-glob `ls` exits non-zero when one glob misses, which under
    # `set -euo pipefail` would abort the script AFTER a successful backup
    # write. grep never fails on non-empty input, so this pipeline survives.
    local count
    count="$(ls -1t "$dir"/udemy_enroller-*.db* 2>/dev/null | grep -v '\.sha256$' | wc -l | tr -d ' ')"
    if [[ "$count" -gt "$RETENTION_COUNT" ]]; then
      ls -1t "$dir"/udemy_enroller-*.db* 2>/dev/null \
        | grep -v '\.sha256$' | tail -n +"$((RETENTION_COUNT + 1))" | while read -r old; do
          rm -f -- "$old" "$old.sha256"
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
  if [[ "$ENCRYPT_BACKUP" -eq 1 ]]; then
    require_openssl
  elif [[ "$ALLOW_PLAINTEXT" -ne 1 ]]; then
    # F235 fail-closed: never write an unencrypted backup silently. Existing
    # host cron must add --allow-plaintext until BACKUP_ENCRYPTION_KEY is set.
    echo "error: refusing plaintext backup — BACKUP_ENCRYPTION_KEY is not set" >&2
    echo "hint: set BACKUP_ENCRYPTION_KEY for encrypted .db.enc output, or pass --allow-plaintext for an unencrypted copy" >&2
    exit 1
  fi

  mkdir -p "$out_dir"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_path="${out_dir}/udemy_enroller-${stamp}.db"
  [[ "$ENCRYPT_BACKUP" -eq 1 ]] && backup_path="${backup_path}.enc"
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

  if [[ "$ENCRYPT_BACKUP" -eq 1 ]]; then
    local enc_tmp="${backup_path}.enc.tmp"
    if ! encrypt_backup_file "$tmp_path" "$enc_tmp"; then
      rm -f -- "$tmp_path" "$enc_tmp"
      echo "error: backup encryption failed" >&2
      exit 1
    fi
    rm -f -- "$tmp_path"
    mv -f -- "$enc_tmp" "$backup_path"
  else
    mv -f -- "$tmp_path" "$backup_path"
  fi

  # LAST_SUCCESS immediately after the good mv so a later checksum failure
  # cannot skip the stamp. Same BACKUP_DIR as the backup file.
  {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$backup_path"
  } >"${out_dir}/LAST_SUCCESS.tmp"
  mv -f -- "${out_dir}/LAST_SUCCESS.tmp" "${out_dir}/LAST_SUCCESS"

  # Best-effort sidecar checksum of the final artifact (plaintext or encrypted,
  # never the key). Failure must not skip LAST_SUCCESS.
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$backup_path" >"${backup_path}.sha256" || true
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

  # F235: auto-detect encrypted backups (suffix or "Salted__" magic) and
  # decrypt to a temp file first. Legacy plaintext backups restore unchanged.
  local decrypt_tmp=""
  local restore_source="$backup_file"
  if is_encrypted_backup "$backup_file"; then
    if [[ "$ENCRYPT_BACKUP" -ne 1 ]]; then
      echo "error: $backup_file is encrypted but BACKUP_ENCRYPTION_KEY is not set" >&2
      echo "hint: set BACKUP_ENCRYPTION_KEY to restore encrypted backups" >&2
      exit 1
    fi
    require_openssl
    decrypt_tmp="$(mktemp "${TMPDIR:-/tmp}/udemy-enroller-restore.XXXXXX")"
    # shellcheck disable=SC2064
    trap "rm -f -- '$decrypt_tmp'" RETURN
    if ! decrypt_backup_file "$backup_file" "$decrypt_tmp"; then
      rm -f -- "$decrypt_tmp"
      echo "error: backup decryption failed (wrong BACKUP_ENCRYPTION_KEY or corrupt file?)" >&2
      exit 1
    fi
    restore_source="$decrypt_tmp"
  fi

  integrity_check "$restore_source"

  mkdir -p "$(dirname "$db")"
  local restore_tmp="${db}.restore.tmp"
  rm -f -- "$restore_tmp"

  # Prefer .backup into a temp file then atomic replace so a failed restore
  # never truncates the live DB mid-write.
  if ! sqlite_backup "$restore_source" "$restore_tmp"; then
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
  latest="$(ls -1t "$drill_dir"/udemy_enroller-*.db* 2>/dev/null | grep -v '\.sha256$' | head -n1)"
  if [[ -z "$latest" ]]; then
    echo "error: drill could not find the produced backup" >&2
    exit 1
  fi
  # Round-trip restore into a throwaway file — decrypt first when the backup
  # is encrypted (exercises the same path as a real restore).
  local roundtrip_src="$latest"
  local decrypt_tmp=""
  if is_encrypted_backup "$latest"; then
    if [[ "$ENCRYPT_BACKUP" -ne 1 ]]; then
      echo "error: drill produced an encrypted backup but BACKUP_ENCRYPTION_KEY is not set" >&2
      exit 1
    fi
    require_openssl
    decrypt_tmp="$(mktemp "${TMPDIR:-/tmp}/udemy-enroller-drill.XXXXXX")"
    if ! decrypt_backup_file "$latest" "$decrypt_tmp"; then
      rm -f -- "$decrypt_tmp"
      echo "error: drill decryption failed" >&2
      exit 1
    fi
    roundtrip_src="$decrypt_tmp"
  fi
  integrity_check "$roundtrip_src"
  local drill_restore="$drill_dir/restored.db"
  sqlite_backup "$roundtrip_src" "$drill_restore"
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
