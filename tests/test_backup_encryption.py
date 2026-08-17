"""F235: backup encryption + plaintext fail-closed + legacy restore.

Shell-script integration tests for scripts/backup_sqlite.sh and
scripts/verify_backup_freshness.sh. The encryption key is generated at
runtime (secrets.token_hex) — never a committed literal. All work happens in
temp dirs; the repo backups/ dir is never touched.
"""

import os
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_sqlite.sh"
FRESHNESS_SCRIPT = REPO_ROOT / "scripts" / "verify_backup_freshness.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl required for F235 tests"
)


def _run_script(script, args, env_extra=None, cwd=REPO_ROOT):
    env = dict(os.environ)
    env.pop("BACKUP_ENCRYPTION_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=120,
    )


@pytest.fixture
def scratch():
    """Temp dir with a small SQLite source DB containing one row."""
    with tempfile.TemporaryDirectory(prefix="ue-f235-") as tmp:
        tmp = Path(tmp)
        src = tmp / "src.db"
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('f235-roundtrip')")
        conn.commit()
        conn.close()
        yield tmp


def _read_value(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT v FROM t").fetchone()[0]
    finally:
        conn.close()


def _new_key() -> str:
    return secrets.token_hex(32)


class TestBackupEncryption:
    def test_plaintext_refused_without_key_or_flag(self, scratch):
        """Fail-closed: no key and no --allow-plaintext -> non-zero exit."""
        out = scratch / "out"
        result = _run_script(
            BACKUP_SCRIPT,
            ["backup"],
            {"DB_PATH": str(scratch / "src.db"), "BACKUP_DIR": str(out)},
        )
        assert result.returncode != 0
        assert "refusing plaintext backup" in result.stderr
        assert not out.exists()

    def test_plaintext_allowed_with_flag(self, scratch):
        """--allow-plaintext writes an unencrypted .db backup."""
        out = scratch / "out"
        result = _run_script(
            BACKUP_SCRIPT,
            ["backup", "--allow-plaintext"],
            {"DB_PATH": str(scratch / "src.db"), "BACKUP_DIR": str(out)},
        )
        assert result.returncode == 0, result.stderr
        backups = list(out.glob("udemy_enroller-*.db"))
        assert len(backups) == 1
        assert not list(out.glob("udemy_enroller-*.db.enc"))

    def test_encrypted_backup_round_trip(self, scratch):
        """Key set -> .db.enc written; restore with same key recovers data."""
        key = _new_key()
        out = scratch / "out"
        result = _run_script(
            BACKUP_SCRIPT,
            ["backup"],
            {
                "DB_PATH": str(scratch / "src.db"),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": key,
            },
        )
        assert result.returncode == 0, result.stderr
        enc = list(out.glob("udemy_enroller-*.db.enc"))
        assert len(enc) == 1
        # No plaintext backup produced alongside the encrypted one.
        assert not list(out.glob("udemy_enroller-*.db"))
        # The artifact is actually encrypted (not a plaintext SQLite copy).
        raw = enc[0].read_bytes()
        assert b"SQLite format 3" not in raw
        assert raw.startswith(b"Salted__")

        restored = scratch / "restored.db"
        result = _run_script(
            BACKUP_SCRIPT,
            ["restore", str(enc[0])],
            {
                "CONFIRM": "YES",
                "DB_PATH": str(restored),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": key,
            },
        )
        assert result.returncode == 0, result.stderr
        assert _read_value(restored) == "f235-roundtrip"

    def test_encrypted_restore_requires_key(self, scratch):
        """Restoring an .enc backup without the key fails closed."""
        key = _new_key()
        out = scratch / "out"
        _run_script(
            BACKUP_SCRIPT,
            ["backup"],
            {
                "DB_PATH": str(scratch / "src.db"),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": key,
            },
        )
        enc = list(out.glob("udemy_enroller-*.db.enc"))[0]
        result = _run_script(
            BACKUP_SCRIPT,
            ["restore", str(enc)],
            {"CONFIRM": "YES", "DB_PATH": str(scratch / "restored.db"), "BACKUP_DIR": str(out)},
        )
        assert result.returncode != 0
        assert "BACKUP_ENCRYPTION_KEY is not set" in result.stderr

    def test_encrypted_restore_wrong_key_fails_closed(self, scratch):
        """Wrong key -> decryption failure, non-zero exit, no restored DB."""
        key = _new_key()
        out = scratch / "out"
        _run_script(
            BACKUP_SCRIPT,
            ["backup"],
            {
                "DB_PATH": str(scratch / "src.db"),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": key,
            },
        )
        enc = list(out.glob("udemy_enroller-*.db.enc"))[0]
        restored = scratch / "restored.db"
        result = _run_script(
            BACKUP_SCRIPT,
            ["restore", str(enc)],
            {
                "CONFIRM": "YES",
                "DB_PATH": str(restored),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": _new_key(),
            },
        )
        assert result.returncode != 0
        assert "backup decryption failed" in result.stderr
        assert not restored.exists()

    def test_legacy_plaintext_restore(self, scratch):
        """Legacy plaintext backups still restore (backward compat, no key)."""
        out = scratch / "out"
        _run_script(
            BACKUP_SCRIPT,
            ["backup", "--allow-plaintext"],
            {"DB_PATH": str(scratch / "src.db"), "BACKUP_DIR": str(out)},
        )
        plain = list(out.glob("udemy_enroller-*.db"))[0]
        restored = scratch / "restored.db"
        result = _run_script(
            BACKUP_SCRIPT,
            ["restore", str(plain)],
            {"CONFIRM": "YES", "DB_PATH": str(restored), "BACKUP_DIR": str(out)},
        )
        assert result.returncode == 0, result.stderr
        assert _read_value(restored) == "f235-roundtrip"

    def test_retention_count_prunes_encrypted_backups(self, scratch):
        """RETENTION_COUNT counts .db.enc backups and prunes oldest ones."""
        out = scratch / "out"
        out.mkdir()
        for i in range(1, 6):
            (out / f"udemy_enroller-20260816T10000{i}Z.db.enc").write_bytes(b"x")
        result = _run_script(
            BACKUP_SCRIPT,
            ["backup", "--allow-plaintext"],
            {
                "DB_PATH": str(scratch / "src.db"),
                "BACKUP_DIR": str(out),
                "RETENTION_COUNT": "3",
            },
        )
        assert result.returncode == 0, result.stderr
        remaining = list(out.glob("udemy_enroller-*.db*"))
        # 5 seeded .enc + 1 new .db, keep 3 newest -> 4 remain.
        assert len(remaining) == 4

    def test_freshness_glob_matches_encrypted_backups(self, scratch):
        """verify_backup_freshness.sh default glob covers .db.enc."""
        out = scratch / "out"
        _run_script(
            BACKUP_SCRIPT,
            ["backup"],
            {
                "DB_PATH": str(scratch / "src.db"),
                "BACKUP_DIR": str(out),
                "BACKUP_ENCRYPTION_KEY": _new_key(),
            },
        )
        result = _run_script(
            FRESHNESS_SCRIPT,
            [],
            {"BACKUP_DIR": str(out), "MAX_AGE_HOURS": "26"},
        )
        assert result.returncode == 0, result.stderr
        assert ".db.enc" in result.stdout

    def test_freshness_mixed_plaintext_and_encrypted(self, scratch):
        """Mixed dir (one .db + one .db.enc, both fresh) passes the *.db* glob."""
        out = scratch / "out"
        out.mkdir()
        (out / "udemy_enroller-20260817T120000Z.db").write_bytes(b"x")
        (out / "udemy_enroller-20260817T120001Z.db.enc").write_bytes(b"x")
        result = _run_script(
            FRESHNESS_SCRIPT,
            [],
            {"BACKUP_DIR": str(out), "MAX_AGE_HOURS": "26"},
        )
        assert result.returncode == 0, result.stderr
        assert "OK:" in result.stdout