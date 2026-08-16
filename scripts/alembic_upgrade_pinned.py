#!/usr/bin/env python3
"""Upgrade one existing SQLite file to a revision via a pinned Config URL.

Usage (from the repo root, after a WAL-safe backup):
    python scripts/alembic_upgrade_pinned.py /abs/path/to.db head
    python scripts/alembic_upgrade_pinned.py /abs/path/to.db c01d021a9e03

Refuses stamp. Prints the filesystem path, never the sqlalchemy URL.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _usage() -> None:
    print(
        "usage: alembic_upgrade_pinned.py /absolute/existing.db REVISION|head",
        file=sys.stderr,
    )


def main(argv: list[str]) -> int:
    if any(part.lower() == "stamp" for part in argv[1:]):
        print("refusing stamp; this script only runs command.upgrade", file=sys.stderr)
        return 2
    if len(argv) != 3:
        _usage()
        return 2

    db_path = Path(argv[1])
    revision = argv[2]
    if not db_path.is_absolute():
        print("database path must be an existing absolute filesystem path", file=sys.stderr)
        return 2
    if not db_path.is_file():
        print("database path does not exist", file=sys.stderr)
        return 2
    if not revision or revision.lower() == "stamp":
        print("refusing stamp; this script only runs command.upgrade", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    print(f"Pinned upgrade target: {db_path}")
    command.upgrade(cfg, revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
