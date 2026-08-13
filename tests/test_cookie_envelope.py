"""F-ENRL-C01: per-session Fernet cookie envelopes (HKDF-salted keys).

Covers: salt round-trip, wrong-session-key fail-closed (None -> 401 path),
cross-session isolation, legacy flag OFF/ON semantics, and the flag defaults.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

import app.security as security_mod
from app.security import (
    _allow_legacy_cookie_decrypt,
    decrypt_cookies,
    encrypt_cookies,
    encrypt_cookies_salted,
    generate_cookie_salt,
)

_COOKIES = {"access_token": "abc123", "client_id": "xyz", "csrf_token": "csrf"}


def _pin_settings(monkeypatch, deployment_env: str):
    """Pin settings to a known deployment env and reset lazy Fernet state."""
    key = Fernet.generate_key().decode()
    monkeypatch.delenv("ALLOW_PLAINTEXT_COOKIES", raising=False)
    monkeypatch.delenv("ALLOW_LEGACY_COOKIE_DECRYPT", raising=False)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            DEPLOYMENT_ENV=deployment_env,
            COOKIE_ENCRYPTION_KEY=key,
            SECRET_KEY="a" * 64,
        ),
    )
    security_mod._fernet = None
    security_mod._fernet_key_bytes = None
    return key


def _capture_warnings(monkeypatch):
    warnings = []
    fake_logger = MagicMock()
    fake_logger.warning = warnings.append
    monkeypatch.setattr(security_mod, "logger", fake_logger)
    return warnings


class TestPerSessionEnvelope:
    def test_salt_roundtrip(self, monkeypatch):
        _pin_settings(monkeypatch, "local")
        salt = generate_cookie_salt()
        encrypted = encrypt_cookies_salted(_COOKIES, salt)
        assert isinstance(encrypted, str)
        assert encrypted != str(_COOKIES)
        assert decrypt_cookies(encrypted, salt) == _COOKIES

    def test_generate_cookie_salt_is_unique_and_valid(self):
        salts = {generate_cookie_salt() for _ in range(50)}
        assert len(salts) == 50
        for salt in salts:
            assert len(salt) == 24  # 16 bytes -> 24 urlsafe base64 chars
            assert decrypt_cookies("garbage", salt) is None  # well-formed salt

    def test_wrong_session_salt_fails_closed_in_server(self, monkeypatch):
        """Wrong session key -> None (never ciphertext, never partial data)."""
        _pin_settings(monkeypatch, "server")
        salt_a = generate_cookie_salt()
        salt_b = generate_cookie_salt()
        encrypted = encrypt_cookies_salted(_COOKIES, salt_a)
        assert decrypt_cookies(encrypted, salt_b) is None

    def test_cross_session_isolation(self, monkeypatch):
        _pin_settings(monkeypatch, "server")
        salt_a, salt_b = generate_cookie_salt(), generate_cookie_salt()
        blob_a = encrypt_cookies_salted({"access_token": "session-a"}, salt_a)
        blob_b = encrypt_cookies_salted({"access_token": "session-b"}, salt_b)
        # Each blob decrypts only under its own session's salt
        assert decrypt_cookies(blob_a, salt_a) == {"access_token": "session-a"}
        assert decrypt_cookies(blob_b, salt_b) == {"access_token": "session-b"}
        assert decrypt_cookies(blob_a, salt_b) is None
        assert decrypt_cookies(blob_b, salt_a) is None

    def test_salted_path_works_in_server_without_legacy_flag(self, monkeypatch):
        """Post-C01 envelopes must decrypt in server mode with legacy OFF."""
        _pin_settings(monkeypatch, "server")
        salt = generate_cookie_salt()
        encrypted = encrypt_cookies_salted(_COOKIES, salt)
        assert decrypt_cookies(encrypted, salt) == _COOKIES

    def test_empty_inputs_are_none(self, monkeypatch):
        _pin_settings(monkeypatch, "local")
        salt = generate_cookie_salt()
        assert decrypt_cookies("", salt) is None
        assert decrypt_cookies(None, salt) is None
        assert decrypt_cookies("", None) is None
        assert encrypt_cookies_salted({}, salt) == ""
        assert encrypt_cookies_salted(None, salt) == ""


class TestLegacyDecryptFlag:
    def test_legacy_flag_off_rejects_legacy_blob_in_server(self, monkeypatch):
        """Server + flag off: a master-key (unsalted) blob is unusable (safe)."""
        _pin_settings(monkeypatch, "server")
        warnings = _capture_warnings(monkeypatch)
        legacy_blob = encrypt_cookies(_COOKIES)  # legacy writer: no salt
        assert decrypt_cookies(legacy_blob) is None
        assert decrypt_cookies(legacy_blob, generate_cookie_salt()) is None
        assert any("ALLOW_LEGACY_COOKIE_DECRYPT" in str(w) for w in warnings)

    def test_legacy_flag_on_decrypts_legacy_blob_with_warning(self, monkeypatch):
        """Flag ON: legacy blob works and logs a warning."""
        _pin_settings(monkeypatch, "server")
        monkeypatch.setenv("ALLOW_LEGACY_COOKIE_DECRYPT", "1")
        warnings = _capture_warnings(monkeypatch)
        legacy_blob = encrypt_cookies(_COOKIES)
        assert decrypt_cookies(legacy_blob) == _COOKIES
        assert any("legacy" in str(w).lower() for w in warnings)

    def test_legacy_flag_defaults_by_deployment_env(self, monkeypatch):
        _pin_settings(monkeypatch, "local")
        assert _allow_legacy_cookie_decrypt() is True
        _pin_settings(monkeypatch, "server")
        assert _allow_legacy_cookie_decrypt() is False
        _pin_settings(monkeypatch, "production")
        assert _allow_legacy_cookie_decrypt() is False

    def test_legacy_flag_explicit_env_overrides(self, monkeypatch):
        _pin_settings(monkeypatch, "server")
        monkeypatch.setenv("ALLOW_LEGACY_COOKIE_DECRYPT", "1")
        assert _allow_legacy_cookie_decrypt() is True
        monkeypatch.setenv("ALLOW_LEGACY_COOKIE_DECRYPT", "0")
        assert _allow_legacy_cookie_decrypt() is False
        _pin_settings(monkeypatch, "local")
        monkeypatch.setenv("ALLOW_LEGACY_COOKIE_DECRYPT", "off")
        assert _allow_legacy_cookie_decrypt() is False

    def test_local_mode_decrypts_legacy_blob_by_default(self, monkeypatch):
        """Local/dev keeps backward compatibility (flag defaults ON)."""
        _pin_settings(monkeypatch, "local")
        legacy_blob = encrypt_cookies(_COOKIES)
        assert decrypt_cookies(legacy_blob) == _COOKIES

    def test_plaintext_legacy_path_unchanged(self, monkeypatch):
        """Pre-encryption plaintext dicts keep their existing F019 behavior."""
        _pin_settings(monkeypatch, "local")
        assert decrypt_cookies(dict(_COOKIES)) == _COOKIES
        _pin_settings(monkeypatch, "server")
        assert decrypt_cookies(dict(_COOKIES)) is None
        monkeypatch.setenv("ALLOW_PLAINTEXT_COOKIES", "1")
        assert decrypt_cookies(dict(_COOKIES)) == _COOKIES

    def test_garbage_inputs_fail_closed(self, monkeypatch):
        _pin_settings(monkeypatch, "server")
        assert decrypt_cookies("totally-invalid-garbage") is None
        assert decrypt_cookies("totally-invalid-garbage", generate_cookie_salt()) is None
        assert decrypt_cookies(12345, generate_cookie_salt()) is None
