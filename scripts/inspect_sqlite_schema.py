#!/usr/bin/env python3
"""Print SQLite schema metadata only (PRAGMA, version, indexes, counts).

Never SELECTs udemy_cookies, email, password, or token columns.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

def _ident(name: str) -> str:
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError("unexpected identifier")
    return name


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: inspect_sqlite_schema.py /absolute/existing.db", file=sys.stderr)
        return 2
    db_path = Path(argv[1])
    if not db_path.is_file():
        print("database path does not exist", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        print(f"integrity_check: {integrity[0] if integrity else 'unknown'}")

        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [row[0] for row in table_rows]
        print("tables:")
        for table in table_names:
            ident = _ident(table)
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({ident})")]
            print(f"  {ident}: {', '.join(columns)}")

        if "alembic_version" in table_names:
            versions = [
                row[0]
                for row in conn.execute("SELECT version_num FROM alembic_version")
            ]
            print("alembic_version: " + (", ".join(versions) if versions else "(empty)"))
        else:
            print("alembic_version: (missing)")

        if "enrollment_runs" in table_names:
            indexes = [
                row[1] for row in conn.execute("PRAGMA index_list(enrollment_runs)")
            ]
            print("enrollment_runs indexes: " + (", ".join(indexes) if indexes else "(none)"))
            extra_active = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT user_id
                    FROM enrollment_runs
                    WHERE status IN ('pending', 'scraping', 'enrolling')
                    GROUP BY user_id
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()
            active = conn.execute(
                """
                SELECT COUNT(*)
                FROM enrollment_runs
                WHERE status IN ('pending', 'scraping', 'enrolling')
                """
            ).fetchone()
            print(f"active_runs: {active[0] if active else 0}")
            print(f"extra_active_run_users: {extra_active[0] if extra_active else 0}")

        if "users" in table_names:
            user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            print(
                "users.cookies_salt: "
                + ("present" if "cookies_salt" in user_cols else "missing")
            )
            users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()
            print(f"users_count: {users_count[0] if users_count else 0}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
