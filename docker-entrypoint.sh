#!/bin/bash
set -e

# Extract database path from DATABASE_URL
# Expecting: sqlite:////app/data/udemy_enroller.db
DB_PATH=$(echo $DATABASE_URL | sed 's|sqlite:///||')

echo "Checking database state at $DB_PATH..."

# If the database file exists, check if it has tables but no migration history
if [ -f "$DB_PATH" ]; then
    # Use a small python script to check table existence
    HAS_USERS=$(python3 -c "import sqlite3; conn = sqlite3.connect('$DB_PATH'); cursor = conn.cursor(); cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='users'\"); print('true' if cursor.fetchone() else 'false'); conn.close()")
    HAS_ALEMBIC=$(python3 -c "import sqlite3; conn = sqlite3.connect('$DB_PATH'); cursor = conn.cursor(); cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'\"); print('true' if cursor.fetchone() else 'false'); conn.close()")

    if [ "$HAS_USERS" == "true" ] && [ "$HAS_ALEMBIC" == "false" ]; then
        echo "Detected existing tables but no migration history. Stamping to initial revision..."
        alembic stamp 20260411_0001
    fi
fi

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
