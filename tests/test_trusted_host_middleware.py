"""F049: TrustedHostMiddleware host-header pinning (spoofed-Host precheck).

Mirrors the TestClient render-assertion pattern from tests/test_cache_headers.py
and the docstring/safety-hygiene pattern from tests/test_error_pages_5xx.py.
The real app wires the middleware at import time (app factory), so:

- Spoofed/allowed-host behavior is asserted against the REAL app (default
  .env on this machine disables via "*", so tests set env BEFORE the
  conftest-independent import below and against a scoped rebuild when the
  default is "*" — see _app_with_hosts()).
- Parser unit tests hit config.settings.allowed_hosts_list directly.
"""

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config.settings import DEFAULT_ALLOWED_HOSTS, allowed_hosts_list


def _app_with_hosts(allowed_hosts):
    """Scoped FastAPI app with TrustedHost wired exactly like main.py (F049).

    Uses a minimal route so assertions are independent of the real app's
    import-time .env ALLOWED_HOSTS value (the factory pins at import).
    www_redirect=False matches the production wiring (apex is canonical).
    """
    scoped = FastAPI()

    @scoped.get("/api/health")
    def _health():
        return {"status": "healthy"}

    if allowed_hosts != ["*"]:
        scoped.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts,
            www_redirect=False,
        )
    return scoped


def test_spoofed_host_header_is_rejected_with_400():
    """A spoofed Host header must fail closed BEFORE routing (400, not 404)."""
    client = TestClient(_app_with_hosts(list(DEFAULT_ALLOWED_HOSTS)))
    try:
        response = client.get("/api/health", headers={"Host": "evil.example"})
    finally:
        client.close()

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_allowed_canonical_host_is_served_200():
    """The canonical production host (nginx forwards Host: $host) passes."""
    client = TestClient(_app_with_hosts(list(DEFAULT_ALLOWED_HOSTS)))
    try:
        response = client.get(
            "/api/health", headers={"Host": "udemyenroller.madhudadi.in"}
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_case_variant_canonical_host_is_rejected_fail_closed():
    """A case-variant of the canonical host fails closed (400).

    Starlette's TrustedHostMiddleware does NOT lowercase the Host header
    before its exact-match comparison ("UdemyEnroller.Madhudadi.IN" !=
    "udemyenroller.madhudadi.in"), so the mismatched case is rejected —
    the secure fail-closed posture. Verified against Starlette 1.3.1.
    """
    client = TestClient(_app_with_hosts(list(DEFAULT_ALLOWED_HOSTS)))
    try:
        response = client.get(
            "/api/health", headers={"Host": "UdemyEnroller.Madhudadi.IN"}
        )
    finally:
        client.close()

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_port_bearing_canonical_host_is_served_200():
    """A port-bearing canonical Host (nginx may forward $host:$port, the
    Docker HEALTHCHECK uses Host: localhost:8000) passes: the middleware
    strips the port ("host".split(":")[0]) before matching."""
    client = TestClient(_app_with_hosts(list(DEFAULT_ALLOWED_HOSTS)))
    try:
        response = client.get(
            "/api/health", headers={"Host": "udemyenroller.madhudadi.in:8080"}
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_default_allowlist_is_the_secure_pinned_set():
    """Unset ALLOWED_HOSTS env -> pinned default incl. localhost + canonical."""
    hosts = allowed_hosts_list(type("S", (), {"ALLOWED_HOSTS": ""})())
    assert hosts == list(DEFAULT_ALLOWED_HOSTS)
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts
    assert "udemyenroller.madhudadi.in" in hosts
    assert "www.udemyenroller.madhudadi.in" in hosts
    # Docker HEALTHCHECK (Host: localhost:8000) must never break under the
    # default. "testserver" (TestClient's default Host) is deliberately
    # EXCLUDED from the shipped default — the test suite injects it via
    # tests/conftest.py instead.
    assert "localhost" in hosts
    assert "testserver" not in hosts


def test_star_wildcard_disables_middleware_and_serves_spoofed_host():
    """ALLOWED_HOSTS=* is the env-overridable safe-disable: no 400 even for a
    spoofed Host (local GUI dev posture; the middleware is not added at all)."""
    scoped = _app_with_hosts(["*"])
    assert not any(
        m.cls is TrustedHostMiddleware for m in scoped.user_middleware
    )
    client = TestClient(scoped)
    try:
        response = client.get("/api/health", headers={"Host": "evil.example"})
    finally:
        client.close()

    assert response.status_code == 200


def test_override_list_is_comma_separated_deduped_with_localhost_kept():
    """Operator override parses comma-separated values, de-dupes, and always
    keeps localhost so the Docker HEALTHCHECK keeps passing."""
    hosts = allowed_hosts_list(type("S", (), {"ALLOWED_HOSTS": "a.example, b.example ,a.example,custom.internal"})())
    assert hosts == ["a.example", "b.example", "custom.internal", "localhost"]


def test_real_app_rejects_spoofed_host_under_default_env(monkeypatch):
    """End-to-end against the REAL main.app: with the middleware active
    (pinned default), a spoofed Host gets 400 while canonical/localhost pass.

    The app pins hosts at import time from Settings(); when the ambient .env
    carries ALLOWED_HOSTS=* (explicit safe-disable, as on dev machines), the
    real app has no middleware — so this test reloads main under an env
    override (env vars rank above the .env file in pydantic-settings) to
    exercise the wired default, then restores the ambient module state.
    """
    pinned = ",".join(DEFAULT_ALLOWED_HOSTS)
    monkeypatch.setenv("ALLOWED_HOSTS", pinned)

    # get_settings() is lru_cached and survives a main reload; clear it so the
    # reload really re-reads ALLOWED_HOSTS (env vars rank above the .env file
    # in pydantic-settings, so setenv alone overrides the ambient .env).
    import config.settings as settings_mod

    settings_mod.get_settings.cache_clear()

    import main as main_mod

    main_mod = importlib.reload(main_mod)
    try:
        wired = getattr(main_mod, "_allowed_hosts", None)
        assert wired == list(DEFAULT_ALLOWED_HOSTS), (
            "reload must wire the pinned default allowlist"
        )
        assert any(
            m.cls is TrustedHostMiddleware for m in main_mod.app.user_middleware
        )
        client = TestClient(main_mod.app)
        try:
            spoofed = client.get("/", headers={"Host": "evil.example"})
            allowed = client.get(
                "/", headers={"Host": "udemyenroller.madhudadi.in"}
            )
            local = client.get("/", headers={"Host": "localhost:8000"})
        finally:
            client.close()
        assert spoofed.status_code == 400
        assert spoofed.text == "Invalid host header"
        assert allowed.status_code == 200
        assert local.status_code == 200
    finally:
        # Restore the ambient module + settings-cache state (original env)
        monkeypatch.undo()
        settings_mod.get_settings.cache_clear()
        importlib.reload(main_mod)
