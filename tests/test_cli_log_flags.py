"""CLI verbosity / unified logging flags (T5-T1).

Uses CliRunner + capfd + monkeypatched ScraperService (no live network).
Covers: flag parsing, level gating, stderr-vs-stdout separation, -v version.
"""

from __future__ import annotations

import inspect
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from app.cli.main import app
from app.services.course import Course

runner = CliRunner()

DEBUG_MARKER = "T5T1-DEBUG-MARKER-xyz"
INFO_MARKER = "T5T1-INFO-MARKER-xyz"
WARN_MARKER = "T5T1-WARN-MARKER-xyz"


def _dummy_course(title: str = "Log Gating Course") -> Course:
    c = Course(
        title=title,
        url="https://www.udemy.com/course/log-gating/?couponCode=FREELOG",
    )
    c.rating = 4.5
    c.language = "English"
    c.category = "Development"
    return c


async def _stream_with_markers(self):
    """Mocked stream that emits gated log records during the command."""
    from loguru import logger

    logger.debug(DEBUG_MARKER)
    logger.info(INFO_MARKER)
    logger.warning(WARN_MARKER)
    m = MagicMock()
    m.site_name = "TutorialBar"
    m.courses = [_dummy_course()]
    yield m, "completed"


async def _stream_quiet(self):
    m = MagicMock()
    m.site_name = "TutorialBar"
    m.courses = [_dummy_course()]
    yield m, "completed"


def test_version_short_flag_still_version():
    res = runner.invoke(app, ["-v"])
    assert res.exit_code == 0
    assert "v2.2.0" in res.output
    res2 = runner.invoke(app, ["--version"])
    assert res2.exit_code == 0
    assert "v2.2.0" in res2.output


# ANSI CSI stripper. typer renders --help through rich; when the runner exports
# FORCE_COLOR/TERM, rich emits styling codes that can split an option name across
# separate spans (e.g. "-" + "-verbose"), so a raw substring match on the
# rendered text is unreliable. Assert on the visible text, not the styling.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible(rendered: str) -> str:
    return _ANSI_RE.sub("", rendered)


def test_help_lists_logging_flags(monkeypatch):
    # rich also *truncates* option names with an ellipsis below ~40 columns, and
    # the captured console width on a CI runner is outside the test's control, so
    # pin the width: assert the flag set, not the host terminal's wrapping.
    import typer.rich_utils

    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", 120, raising=False)
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    out = _visible(res.output)
    assert "--verbose" in out
    assert "-V" in out
    assert "--debug" in out
    assert "--log-level" in out
    assert "--log-file" in out
    # -v stays version, distinct from -V verbose
    assert "-v" in out


def test_short_V_is_verbose_not_version():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_quiet,
    ):
        res = runner.invoke(app, ["-V", "scrape", "--format", "json"])
    assert res.exit_code == 0
    assert "v2.2.0" not in res.stdout
    # -V enables INFO (same as --verbose)
    assert INFO_MARKER not in (res.stderr or "")  # quiet stream emits nothing
    data = json.loads(res.stdout)
    assert data[0]["title"] == "Log Gating Course"


def test_invalid_log_level_exits_2():
    res = runner.invoke(app, ["--log-level", "VERBOSE", "scrape"])
    assert res.exit_code == 2
    res2 = runner.invoke(app, ["--log-level", "nonsense", "scrape"])
    assert res2.exit_code == 2


def test_default_hides_debug_and_info():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["scrape", "--format", "json"])
    assert res.exit_code == 0
    err = res.stderr or ""
    assert DEBUG_MARKER not in err
    assert INFO_MARKER not in err
    assert WARN_MARKER in err
    # stdout stays pure JSON
    assert DEBUG_MARKER not in res.stdout
    assert WARN_MARKER not in res.stdout
    json.loads(res.stdout)


def test_debug_flag_shows_debug():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["--debug", "scrape", "--format", "json"])
    assert res.exit_code == 0
    err = res.stderr or ""
    assert DEBUG_MARKER in err
    assert WARN_MARKER in err
    assert DEBUG_MARKER not in res.stdout
    json.loads(res.stdout)


def test_verbose_enables_info_hides_debug():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["--verbose", "scrape", "--format", "json"])
    assert res.exit_code == 0
    err = res.stderr or ""
    assert DEBUG_MARKER not in err
    assert INFO_MARKER in err
    assert WARN_MARKER in err
    assert INFO_MARKER not in res.stdout


def test_debug_wins_over_verbose():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["--verbose", "--debug", "scrape", "--format", "json"])
    assert res.exit_code == 0
    assert DEBUG_MARKER in (res.stderr or "")


def test_log_level_override_wins_and_gates():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(
            app, ["--log-level", "ERROR", "scrape", "--format", "json"]
        )
    assert res.exit_code == 0
    assert WARN_MARKER not in (res.stderr or "")
    json.loads(res.stdout)
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res2 = runner.invoke(
            app, ["--verbose", "--debug", "--log-level", "ERROR", "scrape", "--format", "json"]
        )
    assert res2.exit_code == 0
    assert WARN_MARKER not in (res2.stderr or "")


def test_json_stdout_clean_no_progress():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["scrape", "--format", "json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list) and len(data) == 1
    assert "Scraping" not in res.stdout
    assert "WARN" not in res.stdout


def test_csv_stdout_clean_stderr_separate():
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["scrape", "--format", "csv"])
    assert res.exit_code == 0
    assert "title" in res.stdout.lower()
    assert WARN_MARKER not in res.stdout
    assert WARN_MARKER in (res.stderr or "")


def test_log_file_option_writes_file(tmp_path):
    log_file = str(tmp_path / "custom.log")
    with patch(
        "app.cli.commands.scrape.ScraperService.stream_results",
        new=_stream_with_markers,
    ):
        res = runner.invoke(app, ["--log-file", log_file, "scrape", "--format", "json"])
    assert res.exit_code == 0
    with open(log_file, encoding="utf-8") as f:
        content = f.read()
    assert WARN_MARKER in content


def test_setup_logging_signature_and_defaults(capfd, tmp_path):
    from app.logging_config import _SINK_IDS, setup_logging
    from loguru import logger

    assert "level" in inspect.signature(setup_logging).parameters
    assert "log_file" in inspect.signature(setup_logging).parameters
    # Default WARNING: debug hidden, warning on stderr only
    tmp_log = str(tmp_path / "sig.log")
    setup_logging(level=None, log_file=tmp_log)
    logger.debug("SIG-DEBUG-HIDDEN-1")
    logger.warning("SIG-WARN-SHOWN-1")
    out, err = capfd.readouterr()
    assert "SIG-DEBUG-HIDDEN-1" not in err
    assert "SIG-WARN-SHOWN-1" in err
    assert "SIG-WARN-SHOWN-1" not in out
    # Idempotent: repeated setup does not duplicate sinks
    before = list(_SINK_IDS)
    setup_logging(level="WARNING", log_file=tmp_log)
    logger.warning("SIG-WARN-ONCE-1")
    out2, err2 = capfd.readouterr()
    assert err2.count("SIG-WARN-ONCE-1") == 1
    assert len(_SINK_IDS) == len(before)
    # sanitize/redaction path preserved
    from app.logging_config import sanitize_log_message

    redacted = sanitize_log_message("coupon_code=SECRET123 user@example.com")
    assert "***REDACTED***" in redacted


def test_commands_honor_global_flags(tmp_path):
    # stats honors --debug
    out = str(tmp_path / "stats.json")
    res = runner.invoke(app, ["--debug", "stats", "--output", out])
    assert res.exit_code == 0
    # server honors --verbose (mock uvicorn)
    with patch("uvicorn.run") as mock_run:
        res2 = runner.invoke(app, ["--verbose", "server", "--host", "127.0.0.1", "--port", "9000"])
        assert res2.exit_code == 0
        assert mock_run.called
    # check honors --debug (mock client, no network)
    with patch("app.cli.commands.check.UdemyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.close = AsyncMock()
        mock_client.display_name = "Flag Learner"
        mock_client.currency = "USD"
        mock_client.udemy_user_id = "1"
        mock_client.enrolled_courses = {}
        mock_cls.return_value = mock_client
        res3 = runner.invoke(app, ["--debug", "check", "--token", "tok123"])
        assert res3.exit_code == 0
