"""Test credential sanitization in logging."""

from app.logging_config import sanitize_log_message
from app.services.http_client import _log_safe_url


def test_sanitize_coupon_code_equals():
    """Test coupon_code redaction with equals sign."""
    msg = "coupon_code=ABC123XYZ"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "ABC123XYZ" not in sanitized


def test_sanitize_coupon_code_colon():
    """Test coupon_code redaction with colon."""
    msg = "coupon_code: ABC123XYZ"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "ABC123XYZ" not in sanitized


def test_sanitize_coupon_in_query_string():
    """Test coupon redaction in query string format."""
    msg = "coupon=TESTCOUPON123"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "TESTCOUPON123" not in sanitized


def test_sanitize_access_token():
    """Test access_token redaction."""
    msg = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized


def test_sanitize_client_id():
    """Test client_id redaction."""
    msg = "client_id=1234567890abcdef"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "1234567890abcdef" not in sanitized


def test_sanitize_csrf_token():
    """Test csrf_token redaction."""
    msg = "csrf_token=abc123xyz789"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "abc123xyz789" not in sanitized


def test_sanitize_csrftoken():
    """Test csrftoken (no underscore) redaction."""
    msg = "csrftoken=def456uvw012"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "def456uvw012" not in sanitized


def test_sanitize_password():
    """Test password redaction."""
    msg = "password=SuperSecret123!"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "SuperSecret123!" not in sanitized


def test_sanitize_email():
    """Test email address redaction."""
    msg = "email=user@example.com"
    sanitized = sanitize_log_message(msg)
    assert "***EMAIL_REDACTED***" in sanitized
    assert "user@example.com" not in sanitized


def test_sanitize_email_in_sentence():
    """Test email redaction in natural language."""
    msg = "New user registered: john.doe@company.com"
    sanitized = sanitize_log_message(msg)
    assert "***EMAIL_REDACTED***" in sanitized
    assert "john.doe@company.com" not in sanitized


def test_sanitize_multiple_emails():
    """Test multiple email addresses in one message."""
    msg = "User admin@site.com updated test@example.org"
    sanitized = sanitize_log_message(msg)
    assert sanitized.count("***EMAIL_REDACTED***") == 2
    assert "admin@site.com" not in sanitized
    assert "test@example.org" not in sanitized


def test_sanitize_authorization_header():
    """Test Authorization header redaction."""
    msg = "Authorization: [REDACTED]"
    sanitized = sanitize_log_message(msg)
    assert "***REDACTED***" in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized


def test_sanitize_json_payload():
    """Test sanitization of JSON-like payloads."""
    msg = '{"coupon_code": "ABC123", "access_token": "secret123"}'
    sanitized = sanitize_log_message(msg)
    assert "ABC123" not in sanitized
    assert "secret123" not in sanitized
    assert "***REDACTED***" in sanitized


def test_sanitize_mixed_sensitive_data():
    """Test multiple sensitive fields in one message."""
    msg = "Login: user@test.com | coupon=PROMO2024 | access_token=xyz789"
    sanitized = sanitize_log_message(msg)
    assert "user@test.com" not in sanitized
    assert "PROMO2024" not in sanitized
    assert "xyz789" not in sanitized
    assert "***EMAIL_REDACTED***" in sanitized
    assert sanitized.count("***REDACTED***") >= 2


def test_sanitize_case_insensitive():
    """Test case-insensitive pattern matching."""
    msg = "COUPON_CODE=TEST123 | Access_Token=secret | CLIENT_ID=abc"
    sanitized = sanitize_log_message(msg)
    assert "TEST123" not in sanitized
    assert "secret" not in sanitized
    assert "abc" not in sanitized


def test_sanitize_preserves_safe_content():
    """Test that non-sensitive content is preserved."""
    msg = "[CHECKOUT_SINGLE] Course Title | free=True | price=0.0"
    sanitized = sanitize_log_message(msg)
    assert "[CHECKOUT_SINGLE]" in sanitized
    assert "Course Title" in sanitized
    assert "free=True" in sanitized
    assert "price=0.0" in sanitized


def test_sanitize_empty_string():
    """Test sanitization of empty string."""
    msg = ""
    sanitized = sanitize_log_message(msg)
    assert sanitized == ""


def test_sanitize_no_sensitive_data():
    """Test message with no sensitive data."""
    msg = "[INFO] Processing course enrollment | status=success"
    sanitized = sanitize_log_message(msg)
    assert sanitized == msg


def test_sanitize_url_with_coupon():
    """Test URL with coupon code in query string."""
    msg = "URL: https://example.com/course?couponCode=DISCOUNT50"
    sanitized = sanitize_log_message(msg)
    assert "DISCOUNT50" not in sanitized
    assert "***REDACTED***" in sanitized


def test_sanitize_dict_str_representation():
    """Test sanitization of dictionary string representation."""
    msg = "checkout_state={'coupon_code': 'PROMO123', 'price': 0.0}"
    sanitized = sanitize_log_message(msg)
    assert "PROMO123" not in sanitized
    assert "***REDACTED***" in sanitized
    assert "price" in sanitized  # Non-sensitive key preserved


class TestLogSafeUrl:
    """F-ENRL-C10: _log_safe_url redacts the query string before logging."""

    def test_strips_coupon_code_query(self):
        url = "https://www.udemy.com/course/slug/learn/?couponCode=SUPERDISCOUNT50"
        safe = _log_safe_url(url)
        assert "SUPERDISCOUNT50" not in safe
        assert "couponCode" not in safe
        assert "https://www.udemy.com/course/slug/learn/" in safe

    def test_strips_access_token_query(self):
        url = "https://www.udemy.com/api-2.0/courses/?access_token=SECRETTOKEN123"
        safe = _log_safe_url(url)
        assert "SECRETTOKEN123" not in safe
        assert "access_token" not in safe
        assert "https://www.udemy.com/api-2.0/courses/" in safe

    def test_strips_fragment(self):
        url = "https://www.udemy.com/course/slug/?couponCode=FRAG123#reviews"
        safe = _log_safe_url(url)
        assert "FRAG123" not in safe
        assert "#reviews" not in safe

    def test_preserves_path(self):
        url = "https://www.udemy.com/course/another-slug/learn/"
        assert _log_safe_url(url) == url

    def test_preserves_bare_queryless_url(self):
        url = "https://www.udemy.com"
        assert _log_safe_url(url) == "https://www.udemy.com"

    def test_handles_non_url_input(self):
        safe = _log_safe_url("not a url at all")
        assert "not a url at all" in safe

    def test_empty_string(self):
        assert _log_safe_url("") == ""

    def test_url_with_userinfo_keeps_path_redacts_other_secrets(self):
        url = "https://user:pass@proxy.example:8080/api?couponCode=HIDDEN&client_id=abc123"
        safe = _log_safe_url(url)
        assert "HIDDEN" not in safe
        assert "couponCode" not in safe
        assert "client_id" not in safe
