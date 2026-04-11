# Alembic Migrations Guide

## Setup

Alembic is configured in `alembic.ini` for database migrations. The migration scripts are stored in `alembic/versions/`.
The application defaults to `AUTO_CREATE_TABLES=false`, so schema creation should be handled through Alembic.

## Running Migrations

### Online Mode (Recommended)
```bash
# Apply all pending migrations
alembic upgrade head

# Apply N migrations
alembic upgrade +2

# Rollback N migrations
alembic downgrade -2

# Rollback to specific migration
alembic downgrade 001c8f0b25ba

# View current migration version
alembic current

# View history
alembic history
```

### Offline Mode (for CI/CD or read-only databases)
```bash
# Generate SQL without executing
alembic upgrade head --sql

# Upgrade to a specific version
alembic upgrade 001c8f0b25ba --sql > migrations.sql
```

## Creating New Migrations

### Automatic Migration (Recommended)
```bash
# Create automatic migration based on model changes
alembic revision --autogenerate -m "Add new feature"
```

### Manual Migration
```bash
# Create blank migration for manual SQL
alembic revision -m "Custom migration name"
```

## Initial Setup

This repository already includes:
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/20260411_0001_initial_schema.py`

For a fresh database, run:
```bash
alembic upgrade head
```

For an existing database that already has the schema but no Alembic history, stamp then continue:
```bash
alembic stamp 20260411_0001
```

## Migration Structure

Each migration file should:
1. Have a unique revision ID
2. Define `upgrade()` function - applies the migration
3. Define `downgrade()` function - reverts the migration
4. Use `op` commands from alembic for schema changes

### Common Operations

```python
from alembic import op
import sqlalchemy as sa

# Create table
op.create_table(
    'table_name',
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('name', sa.String(50), nullable=False)
)

# Add column
op.add_column('table_name', sa.Column('new_col', sa.String(50)))

# Drop column
op.drop_column('table_name', 'old_col')

# Create index
op.create_index('ix_col', 'table_name', ['col'])

# Add constraint
op.create_unique_constraint('uq_col', 'table_name', ['col'])

# Rename table
op.rename_table('old_name', 'new_name')
```

## Troubleshooting

### Migration conflicts
If you have conflicting migrations, resolve manually or use:
```bash
alembic stamp <revision>  # Mark DB as at specific migration
```

### Reset migrations (development only)
```bash
# Delete database and re-create
rm udemy_enroller.db
alembic upgrade head
```

## Best Practices

1. **Always create reversible migrations** - Test `downgrade()` thoroughly
2. **Keep migrations small** - One feature per migration for easier debugging
3. **Never edit applied migrations** - Create new ones instead
4. **Test in staging** - Before applying to production
5. **Back up database** - Before running migrations on production
6. **Document schema changes** - In migration messages for team clarity
