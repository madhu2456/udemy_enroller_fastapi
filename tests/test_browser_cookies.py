"""Unit tests for universal browser cookie extraction service."""

import base64
import json
import os
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.padding import PKCS7

from app.services.browser_cookies import (
    UdemyBrowserCookies,
    _LINUX_KEYRING_LABELS,
    _decrypt_chromium_cookie_value,
    _extract_from_chromium_db,
    _extract_from_firefox_db,
    _find_chromium_cookie_dbs,
    _find_firefox_cookie_dbs,
    _get_chromium_master_key_linux,
    _safe_query_sqlite_cookies,
    extract_all_browsers,
    get_udemy_cookies,
)


def _encrypt_linux_cookie(plain_text: str) -> bytes:
    """Helper to encrypt a cookie using Linux Chromium v10 format."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=24,
    )
    key = kdf.derive(b"peanuts")
    iv = b" " * 16
    padder = PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return b"v10" + ciphertext


def _encrypt_gcm_fixture(plain_text: str, key: bytes, prefix: bytes = b"v10") -> bytes:
    """Encrypt a cookie with AES-GCM for Linux GCM-first tests (in-memory only)."""
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct_and_tag = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    return prefix + nonce + ct_and_tag


def test_linux_peanuts_still_works():
    """Regression: old Linux profiles using peanuts CBC still decrypt."""
    blob = _encrypt_linux_cookie("peanuts_regression_secret")
    with patch("sys.platform", "linux"):
        with patch(
            "app.services.browser_cookies._get_chromium_master_key_linux",
            return_value=None,
        ):
            decrypted, note = _decrypt_chromium_cookie_value(blob, master_key=None)
    assert decrypted == "peanuts_regression_secret"
    assert note is None


@pytest.mark.parametrize("prefix", [b"v10", b"v80"])
def test_linux_gcm_known_key(prefix):
    """GCM-first branch decrypts with known 32-byte master key (v10/v80 parity)."""
    key32 = b"K" * 32
    plain = "gcm_known_secret_123"
    blob = _encrypt_gcm_fixture(plain, key32, prefix=prefix)
    with patch("sys.platform", "linux"):
        decrypted, note = _decrypt_chromium_cookie_value(blob, master_key=key32)
    assert decrypted == plain
    assert note is None


def test_linux_no_keyring_note():
    """GCM blob without keyring key yields GNOME Keyring guidance, not bare padding."""
    key32 = b"K" * 32
    # 23-char plain -> 51-byte payload (not multiple of 16) forces CBC fallback to fail.
    blob = _encrypt_gcm_fixture("no_keyring_secret_value", key32, prefix=b"v10")
    with patch("sys.platform", "linux"):
        with patch(
            "app.services.browser_cookies._get_chromium_master_key_linux",
            return_value=None,
        ):
            decrypted, note = _decrypt_chromium_cookie_value(blob, master_key=None)
    assert decrypted == ""
    assert note is not None
    assert "GNOME Keyring" in note
    assert "Firefox" in note
    assert "manual" in note.lower() or "extension" in note.lower()
    assert "CBC decryption failed" not in note
    # v20 guidance still mentions Extension/Firefox.
    v_decrypted, v_note = _decrypt_chromium_cookie_value(
        b"v20" + b"\x00" * 32, browser_name="chrome"
    )
    assert v_decrypted == ""
    assert v_note is not None
    assert "Extension" in v_note or "Firefox" in v_note


def test_udemy_browser_cookies_dataclass():
    """Test UdemyBrowserCookies methods and dictionary conversions."""
    cookies = UdemyBrowserCookies(
        access_token="tok_1234567890",
        client_id="cid_1234567890",
        csrf_token="csrf_1234567890",
        browser_name="chrome",
        profile_name="Default",
        is_valid=True,
    )

    d = cookies.to_dict()
    assert d["access_token"] == "tok_1234..."
    assert d["client_id"] == "cid_1234..."
    assert d["csrf_token"] == "csrf_123..."
    assert d["browser_name"] == "chrome"
    assert d["is_valid"] is True

    cookie_dict = cookies.as_cookie_dict()
    assert cookie_dict["access_token"] == "tok_1234567890"
    assert cookie_dict["client_id"] == "cid_1234567890"
    assert cookie_dict["csrf_token"] == "csrf_1234567890"
    assert cookie_dict["csrftoken"] == "csrf_1234567890"


def test_firefox_plain_cookie_extraction(tmp_path):
    """Test extracting cookies from a Firefox moz_cookies database."""
    db_file = tmp_path / "cookies.sqlite"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE moz_cookies (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value TEXT,
            host TEXT,
            path TEXT
        )
        """
    )
    cursor.executemany(
        "INSERT INTO moz_cookies (name, value, host, path) VALUES (?, ?, ?, ?)",
        [
            ("access_token", "ff_test_token_xyz", ".udemy.com", "/"),
            ("client_id", "ff_client_id_123", ".udemy.com", "/"),
            ("csrftoken", "ff_csrf_token_abc", ".udemy.com", "/"),
            ("unrelated_cookie", "other_val", ".google.com", "/"),
        ],
    )
    conn.commit()
    conn.close()

    result = _extract_from_firefox_db("test_profile", db_file)
    assert result.is_valid is True
    assert result.access_token == "ff_test_token_xyz"
    assert result.client_id == "ff_client_id_123"
    assert result.csrf_token == "ff_csrf_token_abc"
    assert result.browser_name == "firefox"
    assert result.profile_name == "test_profile"


def test_chromium_linux_decryption(tmp_path):
    """Test extracting and decrypting cookies from a Chromium SQLite database."""
    db_file = tmp_path / "Cookies"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE cookies (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value TEXT,
            encrypted_value BLOB,
            host_key TEXT,
            path TEXT
        )
        """
    )

    encrypted_token = _encrypt_linux_cookie("linux_token_secret_123")
    encrypted_cid = _encrypt_linux_cookie("linux_cid_secret_456")
    encrypted_csrf = _encrypt_linux_cookie("linux_csrf_secret_789")

    cursor.executemany(
        "INSERT INTO cookies (name, value, encrypted_value, host_key, path) VALUES (?, ?, ?, ?, ?)",
        [
            ("access_token", "", encrypted_token, ".udemy.com", "/"),
            ("client_id", "", encrypted_cid, ".udemy.com", "/"),
            ("csrf_token", "", encrypted_csrf, ".udemy.com", "/"),
        ],
    )
    conn.commit()
    conn.close()

    with patch("sys.platform", "linux"):
        result = _extract_from_chromium_db("chrome", "Default", db_file, None)
        assert result.is_valid is True
        assert result.access_token == "linux_token_secret_123"
        assert result.client_id == "linux_cid_secret_456"
        assert result.csrf_token == "linux_csrf_secret_789"


def test_windows_v20_detection():
    """Test that Windows Chrome 127+ App-Bound v20 encryption returns descriptive guidance."""
    v20_blob = b"v20" + b"\x00" * 32
    decrypted, note = _decrypt_chromium_cookie_value(v20_blob, browser_name="chrome")
    assert decrypted == ""
    assert note is not None
    assert "v20" in note
    assert "Extension" in note or "Firefox" in note


def test_missing_database_handling():
    """Test safe query when file does not exist."""
    non_existent = Path("/path/to/nowhere/cookies.sqlite")
    rows = _safe_query_sqlite_cookies(non_existent, "SELECT 1")
    assert rows == []


def test_profile_discovery(tmp_path):
    """Test discovering profiles in a simulated browser directory."""
    # Create Chromium structure
    chrome_dir = tmp_path / "chrome"
    default_dir = chrome_dir / "Default" / "Network"
    default_dir.mkdir(parents=True)
    (default_dir / "Cookies").touch()

    prof1_dir = chrome_dir / "Profile 1" / "Network"
    prof1_dir.mkdir(parents=True)
    (prof1_dir / "Cookies").touch()

    (chrome_dir / "Local State").touch()

    found = _find_chromium_cookie_dbs(chrome_dir)
    assert len(found) == 2
    profile_names = [f[0] for f in found]
    assert "Default" in profile_names
    assert "Profile 1" in profile_names

    # Create Firefox structure
    ff_dir = tmp_path / "firefox"
    ff_prof = ff_dir / "abc.default-release"
    ff_prof.mkdir(parents=True)
    (ff_prof / "cookies.sqlite").touch()

    ff_found = _find_firefox_cookie_dbs(ff_dir)
    assert len(ff_found) == 1
    assert ff_found[0][0] == "abc.default-release"


def test_extract_all_browsers_mock():
    """Test extract_all_browsers returns results dictionary for all supported browsers."""
    with patch("app.services.browser_cookies._get_browser_base_paths") as mock_paths:
        mock_paths.return_value = {
            "chrome": [],
            "edge": [],
            "firefox": [],
            "brave": [],
            "opera": [],
            "chromium": [],
        }
        results = extract_all_browsers()
        assert len(results) == 6
        for b in ["chrome", "edge", "firefox", "brave", "opera", "chromium"]:
            assert b in results
            assert isinstance(results[b], UdemyBrowserCookies)


def test_get_udemy_cookies_auto_fallback():
    """Test get_udemy_cookies falls back across browsers until valid session is found."""
    with patch("app.services.browser_cookies.extract_browser_cookies") as mock_extract:
        # Firefox returns invalid, Edge returns valid
        mock_extract.side_effect = [
            UdemyBrowserCookies(browser_name="firefox", is_valid=False, error="None found"),
            UdemyBrowserCookies(
                browser_name="edge",
                is_valid=True,
                access_token="edge_valid_token",
            ),
        ]

        cookies = get_udemy_cookies("auto")
        assert cookies.is_valid is True
        assert cookies.browser_name == "edge"
        assert cookies.access_token == "edge_valid_token"


def test_linux_label_map_covers_brave():
    assert set(_LINUX_KEYRING_LABELS) == {"chrome", "chromium", "brave", "edge", "opera"}
    assert _LINUX_KEYRING_LABELS["brave"][0] == "Brave Safe Storage"


def test_linux_unwrap_with_secret_known_vector(tmp_path):
    sec = b"fake-keyring-secret"
    exp = b"V" * 32
    wk = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1).derive(sec)
    p = PKCS7(128).padder()
    padded = p.update(exp) + p.finalize()
    enc = Cipher(algorithms.AES(wk), modes.CBC(b" " * 16)).encryptor()
    blob = b"v10" + enc.update(padded) + enc.finalize()
    (tmp_path / "Local State").write_text(json.dumps({"os_crypt": {"encrypted_key": base64.b64encode(blob).decode()}}), encoding="utf-8")
    mod = types.ModuleType("secretstorage")
    mod.dbus_init = lambda *a, **k: object()
    class _Item:
        def get_label(self):
            return "Brave Safe Storage"
        def get_secret(self):
            return sec
    class _Col:
        def is_locked(self):
            return False
        def get_all_items(self):
            return [_Item()]
    mod.get_default_collection = lambda bus: _Col()
    with patch.dict(sys.modules, {"secretstorage": mod}):
        with patch("sys.platform", "linux"):
            got = _get_chromium_master_key_linux(tmp_path, "brave")
    assert got == exp
    gcm = _encrypt_gcm_fixture("brave_gcm_secret_xyz", got)
    with patch("sys.platform", "linux"):
        dec, note = _decrypt_chromium_cookie_value(gcm, master_key=got, browser_name="brave")
    assert dec == "brave_gcm_secret_xyz"
    assert note is None


def test_linux_missing_key_brave_guidance(tmp_path):
    (tmp_path / "Local State").write_text(json.dumps({"os_crypt": {}}), encoding="utf-8")
    assert _get_chromium_master_key_linux(tmp_path, "brave") is None
    blob = _encrypt_gcm_fixture("no_keyring_secret_value", b"K" * 32)
    with patch("sys.platform", "linux"):
        dec, note = _decrypt_chromium_cookie_value(blob, master_key=None, browser_name="brave")
    assert dec == ""
    assert "quit Brave" in note and "Firefox" in note
    assert ("extension" in note.lower() or "manual" in note.lower()) and "CBC decryption failed" not in note
