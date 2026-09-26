"""Shared pytest fixtures.

Ensures tests that use the app engine / SessionLocal run against an isolated
temporary SQLite database rather than an ambient application database.
"""

import ipaddress
import os
import socket
import tempfile
from pathlib import Path

import pytest

# Configure application-owned files before importing modules that cache settings
# or create the global SQLAlchemy engine.
_test_database_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-tests-")
_test_database_path = Path(_test_database_dir.name) / "test_app.db"
_test_log_path = Path(_test_database_dir.name) / "test_app.log"
os.environ["DATABASE_URL"] = f"sqlite:///{_test_database_path}"
os.environ["LOG_FILE"] = str(_test_log_path)

# Test-only host allowlist (F049): "testserver" is the default Host sent by
# starlette/httpx TestClient. The shipped secure default
# (config.settings.DEFAULT_ALLOWED_HOSTS) deliberately excludes it, so the
# suite injects it here — BEFORE any app import pins the middleware — via the
# same env-var mechanism as DATABASE_URL above. Env vars rank above the .env
# file in pydantic-settings, so this also overrides an ambient .env value.
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver,udemyenroller.madhudadi.in,www.udemyenroller.madhudadi.in"


def _load_database_bind():
    from app.models.database import Base, engine

    return Base, engine


Base, engine = _load_database_bind()


def _is_loopback_host(host) -> bool:
    if host in (None, "", b""):
        return True
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False

    normalized = str(host).rstrip(".").lower()
    if normalized == "localhost":
        return True

    # IPv6 scope identifiers are not accepted by ipaddress.ip_address().
    normalized = normalized.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    return bool(
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped
        and address.ipv4_mapped.is_loopback
    )


def _require_loopback(host) -> None:
    if not _is_loopback_host(host):
        pytest.fail(
            f"External network access blocked during tests: {host!r}. "
            "Use @pytest.mark.allow_network only with explicit authorization.",
            pytrace=False,
        )


def _require_loopback_address(sock, address) -> None:
    if sock.family == socket.AF_UNIX:
        return
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        pytest.fail(
            f"External network access blocked for family {sock.family!r}.",
            pytrace=False,
        )
    if not isinstance(address, tuple) or not address:
        pytest.fail("Invalid network address blocked during tests.", pytrace=False)
    _require_loopback(address[0])


@pytest.fixture(scope="session", autouse=True)
def ensure_app_schema():
    """Create the schema on the isolated test bind and clean it up afterward."""
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        engine.dispose()
        _test_database_dir.cleanup()


@pytest.fixture(autouse=True)
def block_external_network(request, monkeypatch):
    """Block non-loopback DNS and socket traffic unless explicitly authorized."""
    if request.node.get_closest_marker("allow_network") is not None:
        return

    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex
    original_gethostbyaddr = socket.gethostbyaddr
    original_getnameinfo = socket.getnameinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto

    def guarded_getaddrinfo(host, *args, **kwargs):
        _require_loopback(host)
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host):
        _require_loopback(host)
        return original_gethostbyname(host)

    def guarded_gethostbyname_ex(host):
        _require_loopback(host)
        return original_gethostbyname_ex(host)

    def guarded_gethostbyaddr(host):
        _require_loopback(host)
        return original_gethostbyaddr(host)

    def guarded_getnameinfo(address, flags):
        _require_loopback(address[0])
        return original_getnameinfo(address, flags)

    def guarded_connect(sock, address):
        _require_loopback_address(sock, address)
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        _require_loopback_address(sock, address)
        return original_connect_ex(sock, address)

    def guarded_sendto(sock, data, *args):
        if args:
            _require_loopback_address(sock, args[-1])
        return original_sendto(sock, data, *args)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", guarded_gethostbyname)
    monkeypatch.setattr(socket, "gethostbyname_ex", guarded_gethostbyname_ex)
    monkeypatch.setattr(socket, "gethostbyaddr", guarded_gethostbyaddr)
    monkeypatch.setattr(socket, "getnameinfo", guarded_getnameinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)


def _apply_customtkinter_defenses() -> None:
    """Defensive monkeypatches for CustomTkinter tracker upward traversal loops and DPI polling."""
    try:
        import tkinter
        import unittest.mock
        from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import (
            AppearanceModeTracker,
        )
        from customtkinter.windows.widgets.scaling.scaling_tracker import (
            ScalingTracker,
        )

        # Layer 3: Deactivate automatic DPI awareness polling loop
        ScalingTracker.deactivate_automatic_dpi_awareness = True

        # Layer 2: Safe bounded widget tree traversal with variadic unpacking
        def _safe_get_tk_root(*args, **kwargs):
            widget = args[-1] if args else kwargs.get("widget")
            current = widget
            visited = set()
            depth = 0
            while current is not None and depth < 50:
                if id(current) in visited:
                    break
                visited.add(id(current))
                if isinstance(current, (tkinter.Tk, tkinter.Toplevel)):
                    return current
                if isinstance(current, (unittest.mock.NonCallableMock, unittest.mock.Mock)):
                    return current
                current = getattr(current, "master", None)
                depth += 1
            return None

        AppearanceModeTracker.get_tk_root_of_widget = staticmethod(_safe_get_tk_root)
        ScalingTracker.get_window_root_of_widget = staticmethod(_safe_get_tk_root)
    except ImportError:
        pass


_apply_customtkinter_defenses()


@pytest.fixture(autouse=True)
def clean_customtkinter_state():
    """Reset CustomTkinter tracker registries before and after each test to prevent state pollution."""
    def _reset_ctk():
        try:
            from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import (
                AppearanceModeTracker,
            )
            from customtkinter.windows.widgets.scaling.scaling_tracker import (
                ScalingTracker,
            )

            AppearanceModeTracker.callback_list.clear()
            AppearanceModeTracker.app_list.clear()
            AppearanceModeTracker.update_loop_running = False

            ScalingTracker.window_widgets_dict.clear()
            ScalingTracker.window_dpi_scaling_dict.clear()
            ScalingTracker.update_loop_running = False
        except ImportError:
            pass

    _reset_ctk()
    try:
        yield
    finally:
        _reset_ctk()


@pytest.fixture(autouse=True)
def guard_memory_ceiling():
    """Verify peak RSS memory usage remains strictly below 2048 MB."""
    yield
    try:
        import resource
        import sys

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Darwin (macOS) reports ru_maxrss in bytes; Linux and BSD report in kilobytes.
        if sys.platform == "darwin":
            peak_rss_mb = usage.ru_maxrss / (1024 * 1024)
        else:
            peak_rss_mb = usage.ru_maxrss / 1024

        if peak_rss_mb > 2048:
            pytest.fail(
                f"Test process exceeded 2048 MB memory ceiling: peak RSS was {peak_rss_mb:.1f} MB",
                pytrace=False,
            )
    except ImportError:
        # resource module is unavailable on Windows environments
        pass
