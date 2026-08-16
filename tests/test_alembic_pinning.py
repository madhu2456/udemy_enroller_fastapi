"""Targeted checks for inspect-idempotent revisions and pinned Alembic helpers.

All database work uses temporary files. Live workspace SQLite files are never opened.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

REPO = Path(__file__).resolve().parents[1]
PINNED = REPO / "scripts" / "alembic_upgrade_pinned.py"
INSPECT = REPO / "scripts" / "inspect_sqlite_schema.py"
ENV_PY = REPO / "alembic" / "env.py"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"
ENTRYPOINT = REPO / "docker-entrypoint.sh"

FORBIDDEN_SELECT = re.compile(
    r"select\s+(?:[\w.]+\s*,\s*)*(udemy_cookies|email|password|token)\b",
    re.IGNORECASE,
)


def _pinned_upgrade(db_path: Path, revision: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PINNED), str(db_path), revision],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def _inspect(db_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSPECT), str(db_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def test_revision_ids_unchanged():
    expected = {
        "0bd117e7d36c_change_udemy_cookies_column_from_json_.py": (
            "0bd117e7d36c",
            "1c7670167de7",
        ),
        "1c7670167de7_add_active_run_unique_index.py": ("1c7670167de7", "0cce47f261a1"),
        "0cce47f261a1_remove_bulk_checkout_columns.py": ("0cce47f261a1", "20260423_0001"),
        "c01d021a9e01_add_cookies_salt_to_users.py": ("c01d021a9e01", "0bd117e7d36c"),
        "c01d021a9e02_add_last_heartbeat_to_enrollment_runs.py": (
            "c01d021a9e02",
            "c01d021a9e01",
        ),
        "c01d021a9e03_drop_firecrawl_and_headless_from_user_settings.py": (
            "c01d021a9e03",
            "c01d021a9e02",
        ),
    }
    versions = REPO / "alembic" / "versions"
    for filename, (revision, down_revision) in expected.items():
        text = (versions / filename).read_text(encoding="utf-8")
        assert f"revision = '{revision}'" in text or f'revision = "{revision}"' in text
        assert (
            f"down_revision = '{down_revision}'" in text
            or f'down_revision = "{down_revision}"' in text
        )


def test_0bd117_docstring_does_not_claim_json_to_text():
    text = (
        REPO
        / "alembic"
        / "versions"
        / "0bd117e7d36c_change_udemy_cookies_column_from_json_.py"
    ).read_text(encoding="utf-8")
    assert "JSON to Text" not in text
    assert "json to text" not in text.lower()


def test_drop_revisions_never_batch_alter_users():
    for name in (
        "0cce47f261a1_remove_bulk_checkout_columns.py",
        "c01d021a9e03_drop_firecrawl_and_headless_from_user_settings.py",
        "c01d021a9e01_add_cookies_salt_to_users.py",
    ):
        text = (REPO / "alembic" / "versions" / name).read_text(encoding="utf-8")
        assert 'batch_alter_table("users"' not in text
        assert "batch_alter_table('users'" not in text


def test_env_py_resolves_url_only_at_runtime():
    text = ENV_PY.read_text(encoding="utf-8")
    preamble = text.split("def resolve_sqlalchemy_url", 1)[0]
    assert "get_settings()" not in preamble
    assert "set_main_option" not in preamble
    assert "def resolve_sqlalchemy_url" in text
    assert "def sqlite_fs_path" in text


def test_ci_does_not_rm_workspace_dbs_or_run_bare_upgrade():
    text = CI_YML.read_text(encoding="utf-8")
    assert "rm -f udemy_enroller.db" not in text
    assert "rm -f data/udemy_enroller.db" not in text
    assert "alembic upgrade head" not in text
    assert "alembic_upgrade_pinned.py" in text
    assert "RUNNER_TEMP" in text


def test_entrypoint_pins_upgrade_and_only_stamps_initial():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "command.upgrade(cfg, \"head\")" in text
    assert "command.stamp(cfg, \"20260411_0001\")" in text
    assert "0bd117" not in text
    assert "alembic upgrade head" not in text
    assert "alembic stamp 20260411_0001" not in text


def test_inspect_script_has_no_forbidden_selects():
    text = INSPECT.read_text(encoding="utf-8")
    assert FORBIDDEN_SELECT.search(text) is None
    lowered = text.lower()
    assert "select email" not in lowered
    assert "select password" not in lowered
    assert "select token" not in lowered
    assert "select udemy_cookies" not in lowered


def test_pinned_script_refuses_stamp_and_relative_paths(tmp_path):
    db_path = tmp_path / "ci.db"
    db_path.write_bytes(b"")
    stamp = _pinned_upgrade(db_path, "stamp")
    assert stamp.returncode == 2
    assert "refusing stamp" in stamp.stderr

    relative = subprocess.run(
        [sys.executable, str(PINNED), "relative.db", "head"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert relative.returncode == 2
    assert "absolute" in relative.stderr


def test_pinned_upgrade_head_twice_is_idempotent(tmp_path):
    db_path = tmp_path / "fresh.db"
    db_path.write_bytes(b"")
    first = _pinned_upgrade(db_path, "head")
    assert first.returncode == 0, first.stderr
    assert str(db_path) in first.stdout
    assert "sqlite:///" not in first.stdout

    second = _pinned_upgrade(db_path, "head")
    assert second.returncode == 0, second.stderr

    inspected = _inspect(db_path)
    assert inspected.returncode == 0, inspected.stderr
    out = inspected.stdout
    assert "alembic_version: c01d021a9e03" in out
    assert "users.cookies_salt: present" in out
    assert "idx_active_run_per_user" in out
    assert "last_checked_at" in out
    assert "is_coupon_valid" in out
    assert "last_heartbeat" in out
    assert "extra_active_run_users: 0" in out


def test_inspect_output_is_metadata_only(tmp_path):
    db_path = tmp_path / "meta.db"
    db_path.write_bytes(b"")
    assert _pinned_upgrade(db_path, "head").returncode == 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("secret-user@example.com", "not-a-real-hash"),
        )
        conn.commit()
    finally:
        conn.close()
    inspected = _inspect(db_path)
    assert inspected.returncode == 0, inspected.stderr
    assert "secret-user@example.com" not in inspected.stdout
    assert "not-a-real-hash" not in inspected.stdout
    assert "users_count: 1" in inspected.stdout


def test_0bd117_add_is_noop_when_coupon_columns_exist(tmp_path):
    db_path = tmp_path / "drift_coupon.db"
    db_path.write_bytes(b"")
    first = _pinned_upgrade(db_path, "1c7670167de7")
    assert first.returncode == 0, first.stderr
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(enrolled_courses)")}
        if "last_checked_at" not in cols:
            conn.execute("ALTER TABLE enrolled_courses ADD COLUMN last_checked_at DATETIME")
        if "is_coupon_valid" not in cols:
            conn.execute("ALTER TABLE enrolled_courses ADD COLUMN is_coupon_valid BOOLEAN")
        conn.commit()
    finally:
        conn.close()
    second = _pinned_upgrade(db_path, "0bd117e7d36c")
    assert second.returncode == 0, second.stderr


def test_1c767_skips_when_index_already_exists(tmp_path):
    db_path = tmp_path / "drift_index.db"
    db_path.write_bytes(b"")
    first = _pinned_upgrade(db_path, "0cce47f261a1")
    assert first.returncode == 0, first.stderr
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_run_per_user
            ON enrollment_runs(user_id)
            WHERE status IN ('pending', 'scraping', 'enrolling')
            """
        )
        conn.execute(
            """
            INSERT INTO users (email, password_hash, currency, is_active, created_at, updated_at)
            VALUES ('idx@example.com', 'x', 'usd', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        user_id = conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute(
            """
            INSERT INTO enrollment_runs (user_id, status, started_at)
            VALUES (?, 'pending', CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()
    second = _pinned_upgrade(db_path, "1c7670167de7")
    assert second.returncode == 0, second.stderr
    conn = sqlite3.connect(db_path)
    try:
        status = conn.execute("SELECT status FROM enrollment_runs").fetchone()[0]
    finally:
        conn.close()
    assert status == "pending"


def test_implicit_dual_db_fail_closed_does_not_touch_live_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "udemy_enroller.db").write_bytes(b"")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "udemy_enroller.db").write_bytes(b"")

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "alembic"))
    with pytest.raises(RuntimeError, match="pin sqlalchemy.url"):
        command.upgrade(cfg, "head")


def test_pin_to_ini_default_path_not_overwritten_by_settings(tmp_path, monkeypatch):
    """An absolute pin to …/data/udemy_enroller.db is explicit even if that
    path is the ini default after resolve. Settings/DATABASE_URL must not win.
    """
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pin = data_dir / "udemy_enroller.db"
    pin.write_bytes(b"")
    (tmp_path / "udemy_enroller.db").write_bytes(b"")
    settings_db = tmp_path / "settings_other.db"
    settings_db.write_bytes(b"")

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{settings_db}")
    result = subprocess.run(
        [sys.executable, str(PINNED), str(pin), "head"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert str(pin) in result.stdout

    conn = sqlite3.connect(pin)
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        conn.close()
    assert version == "c01d021a9e03"

    assert settings_db.stat().st_size == 0
    settings_conn = sqlite3.connect(settings_db)
    try:
        tables = {
            row[0]
            for row in settings_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        settings_conn.close()
    assert "alembic_version" not in tables
    assert (tmp_path / "udemy_enroller.db").stat().st_size == 0


def test_explicit_pin_kept_when_both_candidate_files_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "udemy_enroller.db").write_bytes(b"")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "udemy_enroller.db").write_bytes(b"")

    pinned = tmp_path / "explicit.db"
    pinned.write_bytes(b"")
    result = _pinned_upgrade(pinned, "head")
    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(pinned)
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert version == "c01d021a9e03"
    assert "users" in tables
    # Dummy candidates must remain empty files (not migrated).
    assert (tmp_path / "udemy_enroller.db").stat().st_size == 0
    assert (data_dir / "udemy_enroller.db").stat().st_size == 0


def test_docs_and_setup_no_longer_document_bare_upgrade_head():
    for path in (
        REPO / "README.md",
        REPO / "CONTRIBUTING.md",
        REPO / "setup.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^alembic upgrade head$", text, re.MULTILINE)
        assert "alembic_upgrade_pinned.py" in text
    backup = (REPO / "docs" / "ops" / "backup-restore.md").read_text(encoding="utf-8")
    assert "DB_PATH=$LIVE_ABS" in backup
