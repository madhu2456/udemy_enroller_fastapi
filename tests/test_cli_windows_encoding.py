"""Regression tests for Windows console Unicode encoding safety (CP1252 / CP437)."""

import io
from unittest.mock import MagicMock, patch

from rich.console import Console

from app.cli.main import app
from app.cli.ui import (
    GLYPH_ARROW,
    GLYPH_ERROR,
    GLYPH_INFO,
    GLYPH_STAR,
    GLYPH_SUCCESS,
    GLYPH_WARNING,
    _supports_unicode,
    configure_stream_encoding,
    print_banner,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


def test_typer_help_strings_are_ascii_and_cp437_encodable():
    """Verify that root Typer help and all subcommand/option help strings encode cleanly to ASCII and CP437."""
    # Root help
    assert app.info.help is not None
    root_help = app.info.help
    root_help.encode("ascii")
    root_help.encode("cp437")
    root_help.encode("cp1252")
    assert "🎓" not in root_help
    assert "—" not in root_help

    # Subcommands
    for cmd in app.registered_commands:
        if cmd.help:
            cmd.help.encode("ascii")
            cmd.help.encode("cp437")
            cmd.help.encode("cp1252")
        for param in getattr(cmd, "params", []):
            if getattr(param, "help", None):
                param.help.encode("ascii")
                param.help.encode("cp437")
                param.help.encode("cp1252")


def test_configure_stream_encoding_safe_on_headless_and_custom_streams():
    """Verify that configure_stream_encoding does not raise on None or custom streams."""
    # Headless / daemon mode (sys.stdout is None)
    with patch("sys.stdout", None), patch("sys.stderr", None):
        configure_stream_encoding()

    # Custom stream without reconfigure (e.g. io.StringIO)
    string_stream = io.StringIO()
    with patch("sys.stdout", string_stream), patch("sys.stderr", string_stream):
        configure_stream_encoding()

    # Stream whose reconfigure raises an exception
    failing_stream = MagicMock()
    failing_stream.reconfigure.side_effect = OSError("Access denied")
    with patch("sys.stdout", failing_stream), patch("sys.stderr", failing_stream):
        configure_stream_encoding()


def test_ui_banner_and_helpers_render_on_strict_cp1252_stream():
    """Verify that UI banner and all status helpers execute cleanly on strict cp1252 stream."""
    buffer = io.BytesIO()
    charmap_stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    test_console = Console(file=charmap_stream, force_terminal=True, legacy_windows=False)
    test_err_console = Console(file=charmap_stream, stderr=True, force_terminal=True, legacy_windows=False)

    with patch("app.cli.ui.console", test_console), patch("app.cli.ui.err_console", test_err_console):
        print_banner()
        print_header("Test Header", "Test Subtitle")
        print_success("Operation completed successfully")
        print_warning("Caution: rate limit reached")
        print_error("Failed to connect to host")
        print_info("Processing background batch")

    charmap_stream.flush()
    output = buffer.getvalue().decode("cp1252")
    assert "Udemy Course Enroller" in output
    assert "Test Header" in output
    assert "Operation completed successfully" in output
    assert "Failed to connect to host" in output


def test_adaptive_glyphs_fallback():
    """Verify that _supports_unicode correctly falls back when stream cannot encode Unicode."""
    # Simulated CP1252 stream
    fake_stream = MagicMock()
    fake_stream.encoding = "cp1252"
    with patch("sys.stdout", fake_stream):
        # In CP1252, glyphs like ⚠, ✗, ℹ, ⭐ raise UnicodeEncodeError
        assert not _supports_unicode()

    # Simulated UTF-8 stream
    fake_utf_stream = MagicMock()
    fake_utf_stream.encoding = "utf-8"
    with patch("sys.stdout", fake_utf_stream):
        assert _supports_unicode()

    # Verify glyph types are non-empty strings
    for g in (GLYPH_SUCCESS, GLYPH_WARNING, GLYPH_ERROR, GLYPH_INFO, GLYPH_ARROW, GLYPH_STAR):
        assert isinstance(g, str) and len(g) > 0
