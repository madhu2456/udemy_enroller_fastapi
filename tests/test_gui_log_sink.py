"""T5-T2: GUI bridge loguru sink + LogBox level filter (no network, no Tk mainloop)."""

from __future__ import annotations

import inspect
import time
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from app.gui.bridge import AsyncioBridge


def _logs(bridge, max_count=1000):
    return [e for e in bridge.poll_events(max_count=max_count) if e.get("event") == "LOG"]


@pytest.fixture
def bridge():
    b = AsyncioBridge()
    b.start()  # default WARNING filter
    try:
        yield b
    finally:
        b.stop()


def test_default_warning_hides_debug_info(bridge):
    bridge.poll_events()
    logger.debug("t5t2-debug-hidden")
    logger.info("t5t2-info-hidden")
    assert _logs(bridge) == []


def test_default_warning_shows_warning_error_success(bridge):
    bridge.poll_events()
    logger.warning("t5t2-warn")
    logger.error("t5t2-err")
    logger.success("t5t2-checkout")
    got = {(e["data"]["level"], e["data"]["message"]) for e in _logs(bridge)}
    assert ("WARNING", "t5t2-warn") in got
    assert ("ERROR", "t5t2-err") in got
    assert ("SUCCESS", "t5t2-checkout") in got


def test_set_log_level_debug_and_invalid_fallback(bridge):
    bridge.set_log_level("DEBUG")
    bridge.poll_events()
    logger.debug("t5t2-debug-shown")
    assert any(e["data"]["message"] == "t5t2-debug-shown" for e in _logs(bridge))
    bridge.set_log_level("BOGUS")
    assert bridge._log_level == "WARNING"
    bridge.poll_events()
    logger.debug("t5t2-debug-hidden-again")
    assert _logs(bridge) == []


def test_stop_removes_sink(bridge):
    assert bridge._log_sink_id is not None
    bridge.poll_events()
    bridge.stop()
    assert bridge._log_sink_id is None
    assert bridge.loop is None
    logger.warning("t5t2-after-stop")
    assert _logs(bridge) == []


def test_double_start_no_duplicates():
    b = AsyncioBridge()
    b.start()
    try:
        sid = b._log_sink_id
        b.start()  # early-return: same sink, no duplicate
        assert b._log_sink_id == sid
        b.poll_events()
        logger.warning("t5t2-single")
        assert len(_logs(b)) == 1
    finally:
        b.stop()


def test_rate_cap_1000_debugs_filtered_no_freeze(bridge):
    bridge.poll_events()
    t0 = time.monotonic()
    for i in range(1000):
        logger.debug(f"t5t2-flood-{i}")
    assert time.monotonic() - t0 < 5.0
    assert len(bridge.poll_events(max_count=1000)) == 0  # all filtered at emit


def test_rate_cap_debug_level_bounded():
    b = AsyncioBridge()
    b.start(log_level="DEBUG")
    try:
        b.poll_events()
        for i in range(1000):
            logger.debug(f"t5t2-dbg-{i}")
        emitted = _logs(b)
        assert len(emitted) <= 30  # burst 20 + minor refill
        assert b._log_dropped >= 900
        assert len(emitted) + b._log_dropped == 1000
        b._log_tokens = 20.0  # deterministic refill -> next emit carries counter
        logger.debug("t5t2-post-flood")
        tail = _logs(b)
        assert tail and "coalesced" in tail[-1]["data"]["message"]
    finally:
        b.stop()


def test_scraper_progress_coalesced(bridge):
    bridge.poll_events()
    for i in range(5):
        bridge.emit_event("SCRAPER_PROGRESS", {"seq": i})
    bridge.emit_event("LOG", {"level": "WARNING", "message": "t5t2-keep"})
    events = bridge.poll_events()
    prog = [e for e in events if e.get("event") == "SCRAPER_PROGRESS"]
    assert len(prog) == 1 and prog[0]["data"]["seq"] == 4  # newest wins
    assert any(e["data"].get("message") == "t5t2-keep" for e in events)


def test_poll_default_preserves_backcompat():
    assert inspect.signature(AsyncioBridge.poll_events).parameters["max_count"].default == 100


def test_sanitize_boundary_redacts_secrets(bridge):
    bridge.poll_events()
    logger.warning("login failed access_token=secret123 coupon=FREE99")
    got = _logs(bridge)
    assert len(got) == 1
    msg = got[0]["data"]["message"]
    assert "secret123" not in msg and "FREE99" not in msg
    assert "REDACTED" in msg


class _MockWidget:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return MagicMock()


def _make_logbox():
    with patch("customtkinter.CTkFrame", _MockWidget), \
         patch("customtkinter.CTkFont", MagicMock()), \
         patch("customtkinter.CTkLabel", MagicMock()), \
         patch("customtkinter.CTkButton", MagicMock()), \
         patch("customtkinter.CTkCheckBox", MagicMock()), \
         patch("customtkinter.CTkTextbox", MagicMock()):
        from app.gui.components.log_box import LogBox

        box = LogBox(MagicMock())  # mock master -> dropdown skipped, no Tk
    assert box.level_menu is None
    box.textbox = MagicMock()
    box.textbox.index.return_value = "1.0"
    return box


def test_logbox_default_warning_filter_buffers_all():
    box = _make_logbox()
    assert box.min_level == "WARNING"
    assert tuple(box.LEVEL_OPTIONS) == ("DEBUG", "INFO", "WARNING", "ERROR")
    box.append_log("info-line", level="INFO")  # buffered, not displayed
    assert len(box.log_buffer) == 1
    assert box.textbox.insert.call_count == 0
    box.append_log("warn-line", level="WARNING")
    box.append_log("checkout-line", level="SUCCESS")  # SUCCESS counts as WARNING-visible
    assert len(box.log_buffer) == 3
    assert box.textbox.insert.call_count == 2


def test_logbox_set_min_level_opt_in_and_refresh():
    box = _make_logbox()
    box.append_log("info-line", level="INFO")
    box.append_log("debug-line", level="DEBUG")
    assert box.textbox.insert.call_count == 0
    box.set_min_level("DEBUG")  # opt-in re-renders retained buffer
    assert box.min_level == "DEBUG"
    rendered = [c.args[1] for c in box.textbox.insert.call_args_list]
    assert any("info-line" in t for t in rendered) and any("debug-line" in t for t in rendered)
    box.set_min_level("BOGUS")
    assert box.min_level == "WARNING"
