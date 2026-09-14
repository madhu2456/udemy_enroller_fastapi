"""T4-T1 playwright_get hardening — red-green proof (mocked Playwright only).

NO real browser is ever launched: async_playwright + Stealth are fully mocked.

Proves the mandatory critic guards:
  (a) missing binary/libs -> "" in <2s with BLOCKED_BY_ENV (reason=binary|libs),
      ImportError likewise; breaker state never mutated.
  (b) wall bound: goto timeout=15000 wait_until=commit, wait_for_selector
      timeout=5000 only-if-passed, single wait_for_timeout(2000), zero
      asyncio.sleep, max 2 loads (1 goto + <=1 reload).
  (c) Stealth() path (apply_stealth_async) used; legacy stealth_async gone.
  (d) "" on ANY failure, never raises; browser.close always runs; signature,
      headless=True and str|"" contract preserved.
"""

import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import scraper as scraper_mod
from app.services.scraper import RealDiscountScraper

CLEAN_HTML = "<html><body>coupon content</body></html>"
CF_HTML = "<html><head><title>Just a moment...</title></head><body>cf-browser-verification</body></html>"


def _make_scraper():
    http = MagicMock()
    sc = RealDiscountScraper(http)
    sc.consecutive_failures = 0
    sc.circuit_open = False
    return sc


def _mock_pw_stack(*, content=CLEAN_HTML, goto_exc=None, launch_exc=None,
                   content_exc=None, reload_exc=None):
    """Build a fully mocked async_playwright stack. Returns (factory, page, browser)."""
    page = MagicMock()
    page.goto = AsyncMock(side_effect=goto_exc) if goto_exc else AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    if content_exc is not None:
        page.content = AsyncMock(side_effect=content_exc)
    elif isinstance(content, list):
        page.content = AsyncMock(side_effect=content)
    else:
        page.content = AsyncMock(return_value=content)
    page.reload = AsyncMock(side_effect=reload_exc) if reload_exc else AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    chromium = MagicMock()
    chromium.launch = AsyncMock(side_effect=launch_exc) if launch_exc else AsyncMock(return_value=browser)
    pw = MagicMock()
    pw.chromium = chromium
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=pw)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory, page, browser


def _patch_pw(factory):
    return patch("playwright.async_api.async_playwright", factory)


def _warned_text(mock_logger) -> str:
    """Collect every warning message incl. logger.bind(...).warning(...) chains."""
    parts = [str(mock_logger.warning.call_args_list), str(mock_logger.bind.call_args_list)]
    try:
        parts.append(str(mock_logger.bind.return_value.warning.call_args_list))
    except Exception:
        pass
    return " ".join(parts)


def _patch_stealth_ok():
    stealth = MagicMock()
    stealth.apply_stealth_async = AsyncMock()
    cls = MagicMock(return_value=stealth)
    return patch("playwright_stealth.Stealth", cls), cls, stealth


# ---------------------------------------------------------------- (a) env probe


@pytest.mark.asyncio
async def test_a_missing_binary_returns_empty_fast_with_blocked_log():
    sc = _make_scraper()
    factory, _, _ = _mock_pw_stack(
        launch_exc=Exception("Executable doesn't exist at /root/.cache/ms-playwright/chromium-1200"))
    with _patch_pw(factory), patch.object(scraper_mod, "logger") as mock_logger:
        start = time.perf_counter()
        out = await sc.playwright_get("https://example.com/x/")
        elapsed = time.perf_counter() - start
    assert out == ""
    assert elapsed < 2.0, f"env probe must return in <2s, took {elapsed:.2f}s"
    warned = _warned_text(mock_logger)
    assert "BLOCKED_BY_ENV" in warned, f"must log BLOCKED_BY_ENV, got {warned!r}"
    assert "binary" in warned, f"reason must be binary, got {warned!r}"
    assert sc.circuit_open is False and sc.consecutive_failures == 0, "no breaker mutation"


@pytest.mark.asyncio
async def test_a_missing_libs_returns_empty_fast_with_blocked_log():
    sc = _make_scraper()
    factory, _, _ = _mock_pw_stack(
        launch_exc=Exception("Host system is missing dependencies to run browsers: libnss3 libatk"))
    with _patch_pw(factory), patch.object(scraper_mod, "logger") as mock_logger:
        start = time.perf_counter()
        out = await sc.playwright_get("https://example.com/x/")
        elapsed = time.perf_counter() - start
    assert out == ""
    assert elapsed < 2.0, f"env probe must return in <2s, took {elapsed:.2f}s"
    warned = _warned_text(mock_logger)
    assert "BLOCKED_BY_ENV" in warned, f"must log BLOCKED_BY_ENV, got {warned!r}"
    assert "libs" in warned, f"reason must be libs, got {warned!r}"
    assert sc.circuit_open is False and sc.consecutive_failures == 0, "no breaker mutation"


@pytest.mark.asyncio
async def test_a_import_error_returns_empty_fast_with_blocked_log():
    sc = _make_scraper()
    with patch.dict("sys.modules", {"playwright.async_api": None}), \
            patch.object(scraper_mod, "logger") as mock_logger:
        start = time.perf_counter()
        out = await sc.playwright_get("https://example.com/x/")
        elapsed = time.perf_counter() - start
    assert out == ""
    assert elapsed < 2.0, f"import probe must return in <2s, took {elapsed:.2f}s"
    warned = _warned_text(mock_logger)
    assert "BLOCKED_BY_ENV" in warned, f"must log BLOCKED_BY_ENV, got {warned!r}"
    assert sc.circuit_open is False and sc.consecutive_failures == 0, "no breaker mutation"


# ---------------------------------------------------------------- (b) wall bound


@pytest.mark.asyncio
async def test_b_timeouts_settle_no_sleeps_max_two_loads():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack()
    patcher, _, _ = _patch_stealth_ok()
    with _patch_pw(factory), patcher, \
            patch("asyncio.sleep", new=AsyncMock(side_effect=AssertionError("asyncio.sleep forbidden"))) as no_sleep:
        out = await sc.playwright_get("https://example.com/x/", wait_selector="div.coupon")
    assert out == CLEAN_HTML
    assert page.goto.await_count == 1, "max 1 goto"
    _, gkw = page.goto.call_args
    assert gkw.get("timeout") == 15000, f"goto timeout must be 15000, got {gkw!r}"
    assert gkw.get("wait_until") == "commit", f"goto wait_until must be commit, got {gkw!r}"
    assert page.wait_for_selector.await_count == 1, "selector waited only because passed"
    _, skw = page.wait_for_selector.call_args
    assert skw.get("timeout") == 5000, f"selector timeout must be 5000, got {skw!r}"
    assert page.wait_for_timeout.await_count == 1, "single settle wait only"
    assert page.wait_for_timeout.call_args[0][0] == 2000
    assert page.reload.await_count == 0, "no CF -> no reload (max 2 loads)"
    assert no_sleep.await_count == 0, "asyncio.sleep must never be used"


@pytest.mark.asyncio
async def test_b_no_selector_means_no_selector_wait():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack()
    patcher, _, _ = _patch_stealth_ok()
    with _patch_pw(factory), patcher:
        out = await sc.playwright_get("https://example.com/x/")
    assert out == CLEAN_HTML
    assert page.wait_for_selector.await_count == 0, "no selector passed -> no selector wait"


@pytest.mark.asyncio
async def test_b_source_has_no_sleeps_or_legacy_timeouts():
    src = inspect.getsource(scraper_mod.Scraper.playwright_get)
    assert "asyncio.sleep" not in src, "sleep(20)+sleep(3)+sleep(1-3) must be deleted"
    assert "timeout=60000" not in src, "legacy 60s goto must go"
    assert "timeout=10000" not in src, "legacy 10s selector wait must go"


@pytest.mark.asyncio
async def test_b_cf_single_reload_then_clean():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack(content=[CF_HTML, CLEAN_HTML])
    patcher, _, _ = _patch_stealth_ok()
    with _patch_pw(factory), patcher:
        out = await sc.playwright_get("https://example.com/x/")
    assert out == CLEAN_HTML
    assert page.goto.await_count == 1 and page.reload.await_count == 1, "max 2 loads"
    _, rkw = page.reload.call_args
    assert rkw.get("timeout") == 15000 and rkw.get("wait_until") == "commit"


@pytest.mark.asyncio
async def test_b_cf_unresolved_returns_empty_never_raises():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack(content=CF_HTML)
    patcher, _, _ = _patch_stealth_ok()
    with _patch_pw(factory), patcher:
        out = await sc.playwright_get("https://example.com/x/")
    assert out == ""
    assert page.goto.await_count == 1 and page.reload.await_count == 1, "exactly 2 loads max"


# ---------------------------------------------------------------- (c) stealth migration


@pytest.mark.asyncio
async def test_c_stealth_class_path_used_not_legacy_function():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack()
    patcher, cls, stealth = _patch_stealth_ok()
    with _patch_pw(factory), patcher:
        out = await sc.playwright_get("https://example.com/x/")
    assert out == CLEAN_HTML
    assert cls.called, "Stealth() must be instantiated"
    stealth.apply_stealth_async.assert_awaited_once_with(page)
    src = inspect.getsource(scraper_mod.Scraper.playwright_get)
    # NOTE: apply_stealth_async contains 'stealth_async' as a substring, so the
    # legacy check must target the old import/call forms, not the bare substring.
    assert "from playwright_stealth import stealth_async" not in src, \
        "legacy stealth_async import must be removed"
    assert "await stealth_async(" not in src, "legacy stealth_async() call must be removed"
    assert "Stealth" in src and "apply_stealth_async" in src


@pytest.mark.asyncio
async def test_c_stealth_missing_proceeds_without_it_and_warns():
    sc = _make_scraper()
    factory, _, _ = _mock_pw_stack()
    with _patch_pw(factory), patch.dict("sys.modules", {"playwright_stealth": None}), \
            patch.object(scraper_mod, "logger") as mock_logger:
        out = await sc.playwright_get("https://example.com/x/")
    assert out == CLEAN_HTML, "no-stealth fallback must still fetch"
    warned = str(mock_logger.warning.call_args_list)
    assert "without stealth" in warned.lower() or "proceeding without" in warned.lower(), \
        f"must warn no-stealth explicitly, got {warned!r}"


# ---------------------------------------------------------------- (d) never raises / lifecycle


@pytest.mark.asyncio
async def test_d_exceptions_return_empty_never_raise():
    for kw in (dict(goto_exc=RuntimeError("nav boom")),
               dict(content_exc=ValueError("content boom")),
               dict(reload_exc=RuntimeError("reload boom"), content=CF_HTML),
               dict(launch_exc=OSError("weird launch failure"))):
        sc = _make_scraper()
        factory, _, _ = _mock_pw_stack(**kw)
        patcher, _, _ = _patch_stealth_ok()
        with _patch_pw(factory), patcher:
            out = await sc.playwright_get("https://example.com/x/")  # must not raise
        assert out == "", f"expected '' for {kw}, got {out!r}"


@pytest.mark.asyncio
async def test_d_selector_failure_still_returns_content():
    sc = _make_scraper()
    factory, page, _ = _mock_pw_stack()
    page.wait_for_selector = AsyncMock(side_effect=Exception("bad selector timeout"))
    patcher, _, _ = _patch_stealth_ok()
    with _patch_pw(factory), patcher:
        out = await sc.playwright_get("https://example.com/x/", wait_selector="div.x")
    assert out == CLEAN_HTML


@pytest.mark.asyncio
async def test_d_browser_close_always_runs():
    for kw in ({}, dict(goto_exc=RuntimeError("nav boom"))):
        sc = _make_scraper()
        factory, _, browser = _mock_pw_stack(**kw)
        patcher, _, _ = _patch_stealth_ok()
        with _patch_pw(factory), patcher:
            await sc.playwright_get("https://example.com/x/")
        assert browser.close.await_count == 1, f"close must run even on failure {kw}"


def test_d_signature_headless_and_contract_preserved():
    sig = inspect.signature(scraper_mod.Scraper.playwright_get)
    assert list(sig.parameters) == ["self", "url", "wait_selector"]
    assert sig.parameters["wait_selector"].default is None
    assert sig.return_annotation is str or "str" in str(sig.return_annotation)
    src = inspect.getsource(scraper_mod.Scraper.playwright_get)
    assert '"headless": True' in src or "'headless': True" in src or "headless=True" in src
    # SSRF/robots gating belongs to the caller (T4-T2): no gate *calls* here.
    # (The docstring legitimately names _is_safe_url/_robots_allowed as caller duty.)
    assert "await self._robots_allowed" not in src and "self.robots_gate" not in src \
        and "Blocked unsafe URL" not in src, \
        "SSRF/robots gating belongs to the caller (T4-T2), not here"
    doc = scraper_mod.Scraper.playwright_get.__doc__ or ""
    assert "_is_safe_url" in doc and "_robots_allowed" in doc, \
        "docstring must document caller pre-check duty"


def test_d_no_which_cache_logic_and_no_breaker_mutation_in_source():
    src = inspect.getsource(scraper_mod.Scraper.playwright_get)
    assert "shutil" not in src and "which(" not in src, "no which() cache-path logic"
    assert "consecutive_failures" not in src and "circuit_open" not in src, \
        "playwright_get must never mutate the breaker"
