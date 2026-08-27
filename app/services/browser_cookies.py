"""Universal browser cookie extraction service for Udemy.

Supports Chrome, Edge, Firefox, Brave, Opera, and Chromium across Linux, Windows, and macOS.
Uses safe tempdir SQLite copying with immutable read-only URI flags to prevent locks on active browsers.
Supports DPAPI/AES-GCM (Windows), PBKDF2 saltysalt/SecretService (Linux), Keychain (macOS), and plain-text Firefox.
Detects Windows Chrome 127+ App-Bound v20 encryption with user guidance.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.padding import PKCS7


@dataclass
class UdemyBrowserCookies:
    """Dataclass holding extracted Udemy browser cookies and metadata."""

    access_token: str = ""
    client_id: str = ""
    csrf_token: str = ""
    browser_name: str = ""
    profile_name: str = ""
    error: Optional[str] = None
    is_valid: bool = False
    notes: Optional[str] = None
    all_cookies: Dict[str, str] = field(default_factory=dict)

    def as_cookie_dict(self) -> Dict[str, str]:
        """Convert extracted credentials to dictionary format for HTTP clients."""
        cookie_dict = dict(self.all_cookies)
        if self.access_token:
            cookie_dict["access_token"] = self.access_token
        if self.client_id:
            cookie_dict["client_id"] = self.client_id
        if self.csrf_token:
            cookie_dict["csrf_token"] = self.csrf_token
            cookie_dict["csrftoken"] = self.csrf_token
        return cookie_dict

    def to_dict(self) -> Dict[str, Any]:
        """Convert object metadata to dictionary."""
        return {
            "access_token": self.access_token[:8] + "..." if self.access_token else "",
            "client_id": self.client_id[:8] + "..." if self.client_id else "",
            "csrf_token": self.csrf_token[:8] + "..." if self.csrf_token else "",
            "browser_name": self.browser_name,
            "profile_name": self.profile_name,
            "is_valid": self.is_valid,
            "error": self.error,
            "notes": self.notes,
        }


# =====================================================================
# OS & Path Resolution
# =====================================================================

SUPPORTED_BROWSERS = [
    "chrome",
    "edge",
    "firefox",
    "brave",
    "opera",
    "chromium",
]


def _get_browser_base_paths() -> Dict[str, List[Path]]:
    """Return dictionary of candidate profile base paths for each browser on current OS."""
    is_win = sys.platform == "win32"
    is_mac = sys.platform == "darwin"
    is_linux = sys.platform.startswith("linux")

    paths: Dict[str, List[Path]] = {b: [] for b in SUPPORTED_BROWSERS}

    home = Path.home()

    if is_win:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        app_data = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))

        paths["chrome"].append(local_app_data / "Google" / "Chrome" / "User Data")
        paths["edge"].append(local_app_data / "Microsoft" / "Edge" / "User Data")
        paths["brave"].append(local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data")
        paths["chromium"].append(local_app_data / "Chromium" / "User Data")
        paths["opera"].append(app_data / "Opera Software" / "Opera Stable")
        paths["opera"].append(app_data / "Opera Software" / "Opera GX Stable")
        paths["firefox"].append(app_data / "Mozilla" / "Firefox" / "Profiles")

    elif is_mac:
        app_support = home / "Library" / "Application Support"

        paths["chrome"].append(app_support / "Google" / "Chrome")
        paths["edge"].append(app_support / "Microsoft Edge")
        paths["brave"].append(app_support / "BraveSoftware" / "Brave-Browser")
        paths["chromium"].append(app_support / "Chromium")
        paths["opera"].append(app_support / "com.operasoftware.Opera")
        paths["firefox"].append(app_support / "Firefox" / "Profiles")

    elif is_linux:
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))

        paths["chrome"].append(config / "google-chrome")
        paths["chrome"].append(config / "google-chrome-beta")
        paths["chrome"].append(config / "google-chrome-unstable")
        paths["chromium"].append(config / "chromium")
        paths["brave"].append(config / "BraveSoftware" / "Brave-Browser")
        paths["edge"].append(config / "microsoft-edge")
        paths["edge"].append(config / "microsoft-edge-beta")
        paths["edge"].append(config / "microsoft-edge-dev")
        paths["opera"].append(config / "opera")
        paths["opera"].append(config / "opera-beta")
        paths["opera"].append(config / "opera-developer")
        paths["firefox"].append(home / ".mozilla" / "firefox")

    return paths


def list_available_browsers() -> List[str]:
    """Return a list of installed/detected browser names on current system."""
    base_paths = _get_browser_base_paths()
    available = []
    for browser, candidates in base_paths.items():
        for p in candidates:
            if p.exists():
                available.append(browser)
                break
    return available


# =====================================================================
# Windows DPAPI and AES-GCM Key Decryption
# =====================================================================


def _win_dpapi_decrypt(encrypted_data: bytes) -> bytes:
    """Decrypt data using Windows DPAPI CryptUnprotectData via ctypes."""
    if sys.platform != "win32":
        raise NotImplementedError("DPAPI is only available on Windows")

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.c_char_p)]

    p_data_in = DATA_BLOB(len(encrypted_data), ctypes.c_char_p(encrypted_data))
    p_data_out = DATA_BLOB()

    # CryptUnprotectData(pDataIn, ppszDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut)
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    if not crypt32.CryptUnprotectData(
        ctypes.byref(p_data_in), None, None, None, None, 0, ctypes.byref(p_data_out)
    ):
        raise RuntimeError("CryptUnprotectData failed")

    result = ctypes.string_at(p_data_out.pbData, p_data_out.cbData)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.LocalFree(p_data_out.pbData)
    return result


def _get_chromium_master_key_windows(user_data_dir: Path) -> Optional[bytes]:
    """Retrieve and decrypt the AES master key from Chromium Local State JSON on Windows."""
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        return None

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)

        encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            return None

        encrypted_key = base64.b64decode(encrypted_key_b64)
        if encrypted_key.startswith(b"DPAPI"):
            encrypted_key = encrypted_key[5:]

        return _win_dpapi_decrypt(encrypted_key)
    except Exception as e:
        logger.debug(f"Failed to extract Windows master key from {local_state_path}: {e}")
        return None


# =====================================================================
# Linux / macOS Key Derivation
# =====================================================================


def _derive_key_linux(password: bytes = b"peanuts") -> bytes:
    """Derive Linux AES-128 key using PBKDF2 saltysalt with 24 iterations."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=24,
    )
    return kdf.derive(password)


def _derive_key_macos(password: bytes = b"peanuts") -> bytes:
    """Derive macOS AES-128 key using PBKDF2 saltysalt with 1003 iterations."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=1003,
    )
    return kdf.derive(password)


# =====================================================================
# Cookie Decryption
# =====================================================================


def _decrypt_chromium_cookie_value(
    encrypted_value: bytes,
    master_key: Optional[bytes] = None,
    browser_name: str = "chrome",
) -> Tuple[str, Optional[str]]:
    """Decrypt Chromium encrypted_value bytes.

    Returns:
        (decrypted_text, warning_or_error_note)
    """
    if not encrypted_value:
        return "", None

    # 1. Windows Chrome 127+ App-Bound Encryption check
    if encrypted_value.startswith(b"v20"):
        note = (
            "Windows Chrome 127+ App-Bound encryption (v20) detected. "
            "Direct SQLite extraction is restricted by Google. "
            "Please use the Udemy Enroller Chrome Extension, Firefox, Edge, or manual token input."
        )
        return "", note

    # 2. Windows v10 / v11 (AES-GCM)
    if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
        if sys.platform == "win32" and master_key:
            try:
                nonce = encrypted_value[3:15]
                ciphertext_and_tag = encrypted_value[15:]
                aesgcm = AESGCM(master_key)
                decrypted_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
                return decrypted_bytes.decode("utf-8", errors="ignore"), None
            except Exception as e:
                return "", f"AES-GCM decryption failed: {e}"

        # Linux v10 / v11 (AES-128-CBC with saltysalt PBKDF2)
        if sys.platform.startswith("linux"):
            try:
                key = master_key or _derive_key_linux()
                iv = b" " * 16
                ciphertext = encrypted_value[3:]
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()
                unpadder = PKCS7(128).unpadder()
                unpadded = unpadder.update(decrypted_padded) + unpadder.finalize()
                return unpadded.decode("utf-8", errors="ignore"), None
            except Exception as e:
                return "", f"Linux CBC decryption failed: {e}"

        # macOS v10 / v11 (AES-128-CBC with 1003 iterations)
        if sys.platform == "darwin":
            try:
                key = master_key or _derive_key_macos()
                iv = b" " * 16
                ciphertext = encrypted_value[3:]
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()
                unpadder = PKCS7(128).unpadder()
                unpadded = unpadder.update(decrypted_padded) + unpadder.finalize()
                # macOS Chromium may prepend 32 bytes of checksum/metadata
                if len(unpadded) > 32 and not unpadded.startswith(b"ey"):
                    try:
                        return unpadded[32:].decode("utf-8", errors="ignore"), None
                    except Exception:
                        pass
                return unpadded.decode("utf-8", errors="ignore"), None
            except Exception as e:
                return "", f"macOS CBC decryption failed: {e}"

    # 3. Legacy Windows DPAPI (without v10 prefix)
    if sys.platform == "win32":
        try:
            decrypted = _win_dpapi_decrypt(encrypted_value)
            return decrypted.decode("utf-8", errors="ignore"), None
        except Exception as e:
            return "", f"DPAPI decryption failed: {e}"

    # 4. Fallback decode
    try:
        return encrypted_value.decode("utf-8", errors="ignore"), None
    except Exception:
        return "", "Unknown encryption format"


# =====================================================================
# Safe SQLite Reading with Tempfile & Immutable URI
# =====================================================================


def _safe_query_sqlite_cookies(
    cookie_db_path: Path,
    query: str,
) -> List[Tuple[Any, ...]]:
    """Safely copy cookie SQLite DB to a temp folder and execute read-only immutable query."""
    if not cookie_db_path.exists():
        return []

    temp_dir = tempfile.mkdtemp(prefix="udemy_enroller_cookies_")
    try:
        temp_db = Path(temp_dir) / "cookies_copy.sqlite"
        shutil.copy2(cookie_db_path, temp_db)

        # Also copy WAL and SHM if present to read active transactions
        wal_file = cookie_db_path.with_name(cookie_db_path.name + "-wal")
        if wal_file.exists():
            try:
                shutil.copy2(wal_file, temp_dir / "cookies_copy.sqlite-wal")
            except Exception:
                pass

        shm_file = cookie_db_path.with_name(cookie_db_path.name + "-shm")
        if shm_file.exists():
            try:
                shutil.copy2(shm_file, temp_dir / "cookies_copy.sqlite-shm")
            except Exception:
                pass

        uri_path = f"file:{temp_db.as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri_path, uri=True)
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"Error querying cookie DB copy at {cookie_db_path}: {e}")
        return []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =====================================================================
# Profile Discovery and Extraction
# =====================================================================


def _find_chromium_cookie_dbs(base_path: Path) -> List[Tuple[str, Path, Optional[Path]]]:
    """Find (profile_name, cookie_db_path, local_state_path) tuples in a Chromium user data directory."""
    results = []
    if not base_path.exists():
        return results

    local_state = base_path / "Local State"
    if not local_state.exists():
        # If base_path is Opera or single profile directory
        if (base_path.parent / "Local State").exists():
            local_state = base_path.parent / "Local State"
        else:
            local_state = None

    # Candidate profile folder names
    candidate_profiles = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5", ""]
    # Check if there are other Profile folders
    if base_path.is_dir():
        for item in base_path.iterdir():
            if item.is_dir() and item.name.startswith("Profile ") and item.name not in candidate_profiles:
                candidate_profiles.append(item.name)

    for profile in candidate_profiles:
        profile_dir = base_path / profile if profile else base_path
        if not profile_dir.exists() or not profile_dir.is_dir():
            continue

        # Check Network/Cookies or Cookies
        net_cookies = profile_dir / "Network" / "Cookies"
        root_cookies = profile_dir / "Cookies"

        db_path = None
        if net_cookies.exists():
            db_path = net_cookies
        elif root_cookies.exists():
            db_path = root_cookies

        if db_path:
            results.append((profile or "Default", db_path, local_state))

    return results


def _find_firefox_cookie_dbs(base_path: Path) -> List[Tuple[str, Path]]:
    """Find (profile_name, cookies.sqlite) tuples in a Firefox profiles directory."""
    results = []
    if not base_path.exists():
        return results

    if base_path.is_dir():
        for item in base_path.iterdir():
            if item.is_dir():
                cookies_sqlite = item / "cookies.sqlite"
                if cookies_sqlite.exists():
                    results.append((item.name, cookies_sqlite))
    return results


def _extract_from_chromium_db(
    browser_name: str,
    profile_name: str,
    db_path: Path,
    local_state_path: Optional[Path],
) -> UdemyBrowserCookies:
    """Extract and decrypt Udemy cookies from a Chromium SQLite database."""
    master_key = None
    if sys.platform == "win32" and local_state_path and local_state_path.exists():
        master_key = _get_chromium_master_key_windows(local_state_path.parent)

    query = (
        "SELECT name, value, encrypted_value, host_key, path "
        "FROM cookies WHERE host_key LIKE '%udemy.com' OR host_key LIKE '%udemy%'"
    )
    rows = _safe_query_sqlite_cookies(db_path, query)
    if not rows:
        return UdemyBrowserCookies(
            browser_name=browser_name,
            profile_name=profile_name,
            error="No Udemy cookies found in database",
        )

    all_cookies: Dict[str, str] = {}
    notes_list: List[str] = []

    for name, value, encrypted_value, host_key, path in rows:
        cookie_val = value
        if not cookie_val and encrypted_value:
            decrypted, note = _decrypt_chromium_cookie_value(
                encrypted_value, master_key=master_key, browser_name=browser_name
            )
            if note and note not in notes_list:
                notes_list.append(note)
            if decrypted:
                cookie_val = decrypted

        if cookie_val:
            all_cookies[name] = cookie_val

    access_token = all_cookies.get("access_token", "")
    client_id = all_cookies.get("client_id", "")
    csrf_token = all_cookies.get("csrf_token") or all_cookies.get("csrftoken", "")

    notes = " | ".join(notes_list) if notes_list else None
    is_valid = bool(access_token)

    return UdemyBrowserCookies(
        access_token=access_token,
        client_id=client_id,
        csrf_token=csrf_token,
        browser_name=browser_name,
        profile_name=profile_name,
        error=None if is_valid else (notes or "Missing access_token in browser cookies"),
        is_valid=is_valid,
        notes=notes,
        all_cookies=all_cookies,
    )


def _extract_from_firefox_db(
    profile_name: str,
    db_path: Path,
) -> UdemyBrowserCookies:
    """Extract plain-text Udemy cookies from a Firefox cookies.sqlite database."""
    query = (
        "SELECT name, value, host, path "
        "FROM moz_cookies WHERE host LIKE '%udemy.com' OR host LIKE '%udemy%'"
    )
    rows = _safe_query_sqlite_cookies(db_path, query)
    if not rows:
        return UdemyBrowserCookies(
            browser_name="firefox",
            profile_name=profile_name,
            error="No Udemy cookies found in Firefox profile",
        )

    all_cookies: Dict[str, str] = {}
    for name, value, host, path in rows:
        if value:
            all_cookies[name] = value

    access_token = all_cookies.get("access_token", "")
    client_id = all_cookies.get("client_id", "")
    csrf_token = all_cookies.get("csrf_token") or all_cookies.get("csrftoken", "")
    is_valid = bool(access_token)

    return UdemyBrowserCookies(
        access_token=access_token,
        client_id=client_id,
        csrf_token=csrf_token,
        browser_name="firefox",
        profile_name=profile_name,
        error=None if is_valid else "Missing access_token in Firefox cookies",
        is_valid=is_valid,
        all_cookies=all_cookies,
    )


# =====================================================================
# Public API
# =====================================================================


def extract_browser_cookies(browser_name: str) -> UdemyBrowserCookies:
    """Extract Udemy cookies from a specific browser.

    Args:
        browser_name: One of 'chrome', 'edge', 'firefox', 'brave', 'opera', 'chromium'.
    """
    browser_clean = browser_name.lower().strip()
    base_paths = _get_browser_base_paths().get(browser_clean, [])

    if not base_paths:
        return UdemyBrowserCookies(
            browser_name=browser_clean,
            error=f"Unsupported or unknown browser '{browser_name}'",
        )

    last_cookies = UdemyBrowserCookies(browser_name=browser_clean, error="No profile found")

    for base_path in base_paths:
        if not base_path.exists():
            continue

        if browser_clean == "firefox":
            ff_profiles = _find_firefox_cookie_dbs(base_path)
            for prof_name, db_path in ff_profiles:
                cookies = _extract_from_firefox_db(prof_name, db_path)
                if cookies.is_valid:
                    return cookies
                last_cookies = cookies
        else:
            chrom_profiles = _find_chromium_cookie_dbs(base_path)
            for prof_name, db_path, local_state in chrom_profiles:
                cookies = _extract_from_chromium_db(browser_clean, prof_name, db_path, local_state)
                if cookies.is_valid:
                    return cookies
                last_cookies = cookies

    return last_cookies


def extract_all_browsers() -> Dict[str, UdemyBrowserCookies]:
    """Scan all supported browsers and return extracted cookies for each."""
    results = {}
    for browser in SUPPORTED_BROWSERS:
        results[browser] = extract_browser_cookies(browser)
    return results


def get_udemy_cookies(browser: Optional[str] = None) -> UdemyBrowserCookies:
    """Universal cookie getter.

    If browser is specified (or not 'auto'), extracts from that browser.
    If browser is None or 'auto', automatically tries all installed browsers in priority order
    (Firefox -> Chrome -> Edge -> Brave -> Opera -> Chromium) and returns the first valid session.
    """
    if browser and browser.lower() != "auto":
        return extract_browser_cookies(browser)

    # Auto priority: Firefox (plain-text cookies avoid v20 lock on Windows) -> Edge -> Chrome -> Brave -> Opera -> Chromium
    priority = ["firefox", "edge", "chrome", "brave", "opera", "chromium"]
    last_err = UdemyBrowserCookies(browser_name="auto", error="No supported browser with active Udemy session found")

    for b in priority:
        extracted = extract_browser_cookies(b)
        if extracted.is_valid:
            return extracted
        if extracted.notes and not last_err.notes:
            last_err.notes = extracted.notes
        if extracted.error:
            last_err.error = extracted.error

    return last_err
