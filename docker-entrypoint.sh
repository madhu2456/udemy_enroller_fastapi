#!/bin/bash
set -e

# Load DATABASE_URL from environment or .env if present
# (Docker handles environment, but this is good for consistency)
DB_URL=${DATABASE_URL:-"sqlite:///./udemy_enroller.db"}

# Extract database path from DATABASE_URL
# Expecting: sqlite:////app/data/udemy_enroller.db or sqlite:///./udemy_enroller.db
DB_PATH=$(echo $DB_URL | sed 's|^sqlite:///||')

echo "------------------------------------------------"
echo " Database Initialization"
echo " Database configuration detected."
echo "------------------------------------------------"

# Ensure directory exists for SQLite
DB_DIR=$(dirname "$DB_PATH")
if [ "$DB_DIR" != "." ] && [ ! -d "$DB_DIR" ]; then
    echo "Creating database directory..."
    mkdir -p "$DB_DIR"
fi

if [ -f "$DB_PATH" ]; then
    echo "Found existing database file."
    
    # Use Python to check for tables and migration history
    # We use -u for unbuffered output to ensure logs appear in order
    # Disable exit on error temporarily to capture the custom exit code
    set +e
    python3 -u <<EOF
import sqlite3
import sys

db_path = "$DB_PATH"
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check for 'users' table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    has_users = cursor.fetchone() is not None
    
    # Check for 'alembic_version' table and its content
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
    has_alembic_table = cursor.fetchone() is not None
    
    is_version_empty = True
    if has_alembic_table:
        cursor.execute("SELECT COUNT(*) FROM alembic_version")
        count = cursor.fetchone()[0]
        if count > 0:
            is_version_empty = False
    
    conn.close()
    
    if has_users and is_version_empty:
        print("DETECTED: Existing 'users' table but Alembic version is missing or empty.")
        sys.exit(10) # Custom exit code for "needs stamping"
    elif has_users:
        print("INFO: Database already has 'users' table and migration history.")
    else:
        print("INFO: Database is empty or does not have 'users' table.")
        
except Exception as e:
    print(f"ERROR: Failed to check database: {e}")
    sys.exit(1)
EOF
    EXIT_CODE=$?
    set -e
    
    if [ $EXIT_CODE -eq 10 ]; then
        echo "Stamping database with initial revision (20260411_0001)..."
        alembic stamp 20260411_0001
    fi
else
    echo "No existing database found. A new one will be created."
fi

echo "Running migrations (alembic upgrade head)..."
alembic upgrade head

# Seed persistent public_deals.json on the data volume from the image copy
# (first boot / empty volume). Coupon-checker and enrollment keep it updated.
PUBLIC_DEALS_PATH="${PUBLIC_DEALS_PATH:-}"
if [ -n "$PUBLIC_DEALS_PATH" ] && [ ! -f "$PUBLIC_DEALS_PATH" ] && [ -f /app/public_deals.json ]; then
    echo "Seeding $PUBLIC_DEALS_PATH from image public_deals.json..."
    mkdir -p "$(dirname "$PUBLIC_DEALS_PATH")"
    cp /app/public_deals.json "$PUBLIC_DEALS_PATH"
fi

echo "Starting application with uvicorn..."
echo "------------------------------------------------"
# ---------------------------------------------------------------------------
# Resolve the Docker bridge gateway and export TRUSTED_PROXY_IPS with it.
# Compose publishes "127.0.0.1:8000:8000", so the app's TCP peer is the bridge
# gateway (e.g. 172.18.0.1), which varies per compose network (172.17/18/19.x.0.1).
# Without trusting it, _client_key() ignores X-Forwarded-For and keys EVERY
# request on the gateway IP -> one global bucket per limiter (an attacker
# exhausting login_rate_limiter would lock out every user).
# Fail-safe: if the gateway cannot be resolved, keep the loopback-only default
# (no spoofing hole; limiting falls back to coarse peer-keyed buckets).
# ---------------------------------------------------------------------------
GATEWAY=""
if command -v ip >/dev/null 2>&1; then
    GATEWAY="$(ip route 2>/dev/null | awk '/default/{print $3; exit}')" || true
fi
if [ -z "$GATEWAY" ]; then
    # python:3.11-slim ships no iproute2; parse /proc/net/route instead.
    GATEWAY="$(python3 -c '
import socket, struct
with open("/proc/net/route") as f:
    next(f, None)
    for line in f:
        p = line.split()
        if len(p) >= 3 and p[1] == "00000000":
            print(socket.inet_ntoa(struct.pack("<I", int(p[2], 16))))
            break
' 2>/dev/null)" || true
fi
if [ -n "$GATEWAY" ]; then
    export TRUSTED_PROXY_IPS="[\"127.0.0.1\", \"::1\", \"$GATEWAY\"]"
    echo "TRUSTED_PROXY_IPS=$TRUSTED_PROXY_IPS"
else
    export TRUSTED_PROXY_IPS='["127.0.0.1", "::1"]'
    echo "WARNING: could not resolve bridge gateway; TRUSTED_PROXY_IPS fallback=[\"127.0.0.1\", \"::1\"]"
fi

# Fix volume permissions and drop privileges
chown -R appuser:appuser /app/data /app/logs /app/Courses 2>/dev/null || true

# Start the application as non-root user
exec su appuser -c "uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1"
