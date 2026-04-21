# Alembic Migrations Guide

## Setup

Alembic is configured in `alembic.ini` for database migrations. The migration scripts are stored in `alembic/versions/`.
The application defaults to `AUTO_CREATE_TABLES=false`, so schema creation should be handled through Alembic.

## Key Features

### 1. Automated Schema Repair
The system includes a specialized "Master Repair" migration (`eb426d9d141e` and later). This migration performs a rigorous check of all core tables and automatically adds any missing columns defined in the SQLAlchemy models. This ensures that even legacy databases or databases partially initialized without Alembic are brought into full 100% column parity with the application code.

### 2. Idempotent Migrations
All migration scripts are designed to be idempotent. They use `sqlalchemy.inspect` to check for the existence of tables or columns before attempting to create or modify them. This prevents common errors like `OperationalError: table ... already exists` during upgrades.

### 3. Automated Directory Management
The `alembic/env.py` has been enhanced to automatically create the parent directory for SQLite databases (e.g., the `data/` folder) if it doesn't exist.

## Running Migrations

### Online Mode (Recommended)
```bash
# Apply all pending migrations
alembic upgrade head

# View current migration version
alembic current

# View history
alembic history
```

## Docker Integration

The Docker entrypoint script (`docker-entrypoint.sh`) handles migrations automatically on container startup:
1. It checks if the database exists.
2. If the database has tables but no Alembic history, it runs `alembic stamp` to synchronize the version.
3. It runs `alembic upgrade head` to apply all migrations and repair any missing columns.

## Troubleshooting

### "no such column" Errors
If you see an error about a missing column, simply restart the application or run:
```bash
alembic upgrade head
```
The "Master Repair" logic will detect the missing column and add it automatically.

### "unable to open database file"
This usually indicates a permissions issue or a missing directory. The latest version of `alembic/env.py` automatically attempts to create missing directories for SQLite.

## Best Practices

1. **Always use HEAD** - The application code expects the schema to be at the latest version.
2. **Back up database** - Before running migrations on production, especially when repairing legacy schemas.
3. **Don't use metadata.create_all()** - Use Alembic instead to maintain version history and support automated repairs.
