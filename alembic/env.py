"""Alembic environment configuration."""

import configparser
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import url as sa_url

from app.models.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False (standard Alembic template guidance):
    # with the default True, running alembic in-process (e.g. the pinned
    # upgrade helper used by tests/CI) disables every logger that already
    # exists, silently silencing later application logging in the process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

_INI_DEFAULT_SQLITE_URL = "sqlite:///./data/udemy_enroller.db"
_ROOT_DB = Path("udemy_enroller.db")
_DATA_DB = Path("data") / "udemy_enroller.db"


def sqlite_fs_path(url: str):
    """Resolved filesystem path for a SQLite URL, or None if not a file URL."""
    if not url:
        return None
    try:
        parsed = sa_url.make_url(url)
    except Exception:
        return None
    database = parsed.database
    if not database:
        return None
    return Path(database).resolve()


def _ini_default_url(alembic_config) -> str:
    """sqlalchemy.url from the raw ini file (not a mutated Config)."""
    default_url = _INI_DEFAULT_SQLITE_URL
    ini_path = getattr(alembic_config, "config_file_name", None)
    if not ini_path:
        return default_url
    parser = configparser.ConfigParser()
    try:
        read_ok = parser.read(ini_path)
    except (OSError, configparser.Error):
        return default_url
    if not read_ok or not parser.has_option("alembic", "sqlalchemy.url"):
        return default_url
    return parser.get("alembic", "sqlalchemy.url")


def resolve_sqlalchemy_url(alembic_config) -> str:
    """Choose sqlalchemy.url at migration runtime (never at import).

    A non-empty Config URL that is not the raw ini default string is an
    explicit pin (set_main_option / pinned helper) and is returned unchanged.
    Path-normalized compare is not used to classify pins: an absolute pin
    that resolves to data/udemy_enroller.db stays explicit.
    Implicit empty/ini-default: fail closed if both candidate SQLite files
    exist; otherwise use Settings.
    """
    configured = (alembic_config.get_main_option("sqlalchemy.url") or "").strip()
    ini_default = (_ini_default_url(alembic_config) or "").strip()

    # Explicit pin: any non-empty Config URL other than the raw ini string.
    # Path-normalized compare is not used here — a pin to
    # sqlite:////abs/data/udemy_enroller.db stays explicit even when it
    # resolves to the same file as sqlite:///./data/udemy_enroller.db.
    if configured and configured != ini_default:
        return configured

    if _ROOT_DB.is_file() and _DATA_DB.is_file():
        raise RuntimeError(
            "Both udemy_enroller.db and data/udemy_enroller.db exist; "
            "pin sqlalchemy.url to the inspected absolute SQLite path "
            "(scripts/alembic_upgrade_pinned.py) before upgrading."
        )

    from config.settings import get_settings

    return get_settings().DATABASE_URL


def _ensure_sqlite_parent(url: str) -> None:
    if url and "sqlite" in url:
        parsed = sa_url.make_url(url)
        if parsed.database:
            db_dir = os.path.dirname(parsed.database)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = resolve_sqlalchemy_url(config)
    config.set_main_option("sqlalchemy.url", url)
    _ensure_sqlite_parent(url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = resolve_sqlalchemy_url(config)
    config.set_main_option("sqlalchemy.url", url)
    _ensure_sqlite_parent(url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
