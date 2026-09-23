"""Targeted security tests for proxy validation and SSRF fencing (WP-UDEMY-03)."""

from app.security import validate_proxy_url


def test_proxy_url_ssrf():
    """Test proxy URL validation rejects private, loopback, and link-local IPs (SEC-UDEMY-03)."""
    # Loopback
    assert validate_proxy_url("http://127.0.0.1:8080") is False
    assert validate_proxy_url("http://localhost:8080") is False
    assert validate_proxy_url("socks5://127.0.0.1:1080") is False
    assert validate_proxy_url("socks5://localhost:1080") is False

    # Link-local / metadata service
    assert validate_proxy_url("http://169.254.169.254/latest/meta-data/") is False

    # RFC 1918 Private ranges
    assert validate_proxy_url("http://10.0.0.1:8080") is False
    assert validate_proxy_url("http://172.16.0.1:8080") is False
    assert validate_proxy_url("http://192.168.1.1:8080") is False

    # Valid public proxy
    assert validate_proxy_url("http://proxy.example.com:8080") is True
    assert validate_proxy_url("socks5://proxy.example.com:1080") is True
