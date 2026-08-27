"""Unit tests for universal browser cookie extraction service."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.padding import PKCS7

from app.services.browser_cookies import (
    UdemyBrowserCookies,
    _decrypt_chromium_cookie_value,
    _extract_from_chromium_db,
    _extract_from_firefox_db,
    _find_chromium_cookie_dbs,
    _find_firefox_cookie_dbs,
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
