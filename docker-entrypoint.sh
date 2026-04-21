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
echo " URL:  $DB_URL"
echo " Path: $DB_PATH"
echo "------------------------------------------------"

# Ensure directory exists for SQLite
DB_DIR=$(dirname "$DB_PATH")
if [ "$DB_DIR" != "." ] && [ ! -d "$DB_DIR" ]; then
    echo "Creating directory $DB_DIR..."
    mkdir -p "$DB_DIR"
fi

if [ -f "$DB_PATH" ]; then
    echo "Found existing database file."
    
    # Use Python to check for tables and migration history
    # We use -u for unbuffered output to ensure logs appear in order
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
    
    # Check for 'alembic_version' table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
    has_alembic = cursor.fetchone() is not None
    
    conn.close()
    
    if has_users and not has_alembic:
        print("DETECTED: Existing 'users' table without Alembic version table.")
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
    
    if [ $EXIT_CODE -eq 10 ]; then
        echo "Stamping database with initial revision (20260411_0001)..."
        alembic stamp 20260411_0001
    fi
else
    echo "No existing database found at $DB_PATH. A new one will be created."
fi

echo "Running migrations (alembic upgrade head)..."
alembic upgrade head

echo "Starting application with uvicorn..."
echo "------------------------------------------------"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
