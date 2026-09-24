"""Unit tests for High-Concurrency & Domain-Partitioned Scraper Scaling."""

import asyncio
import re
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import ScraperService
from config.settings import get_settings


@pytest.mark.asyncio
async def test_domain_partitioned_delay_non_blocking():
    """Verify concurrent requests to different domains finish without inter-domain delay stacking."""
    client = AsyncHTTPClient()
    try:
        # Simulate domain A having a recent request timestamp (e.g. right now)
        now = time.monotonic()
        client._domain_last_request_times["site-alpha.com"] = now

        # Request to domain B should not wait on domain A's pacing delay
        t0 = time.monotonic()
        await client._apply_human_like_delay("https://site-beta.com/page1")
        elapsed = time.monotonic() - t0

        # Domain B is on its first request, so it should finish almost instantaneously (< 0.2s)
        assert elapsed < 0.2
        assert "site-beta.com" in client._domain_locks
        assert "site-beta.com" in client._domain_last_request_times

        # Concurrent requests across 5 different new domains should all complete immediately without stacking
        domains = [f"https://site-{i}.com/page" for i in range(5)]
        t1 = time.monotonic()
        await asyncio.gather(*(client._apply_human_like_delay(d) for d in domains))
        elapsed_multi = time.monotonic() - t1
        assert elapsed_multi < 0.3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_domain_partitioned_delay_lock_isolation():
    """Verify lock on domain A does not block request processing on domain B."""
    client = AsyncHTTPClient()
    try:
        await client._apply_human_like_delay("https://lock-a.com/test")
        await client._apply_human_like_delay("https://lock-b.com/test")

        lock_a = client._domain_locks["lock-a.com"]
        lock_b = client._domain_locks["lock-b.com"]
        assert lock_a is not lock_b

        execution_order: List[str] = []

        async def slow_domain_a():
            async with lock_a:
                execution_order.append("a_start")
                await asyncio.sleep(0.15)
                execution_order.append("a_end")

        async def fast_domain_b():
            await asyncio.sleep(0.02)
            # lock_b must be acquired immediately without waiting on lock_a
            async with lock_b:
                execution_order.append("b_done")

        await asyncio.gather(slow_domain_a(), fast_domain_b())
        assert execution_order == ["a_start", "b_done", "a_end"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_domain_partitioned_delay_default_fallback():
    """Verify None or unparseable url safely falls back to 'default' domain lock."""
    client = AsyncHTTPClient()
    try:
        await client._apply_human_like_delay(None)
        assert "default" in client._domain_locks
        assert "default" in client._domain_last_request_times

        # Invalid or atypical URLs gracefully fall back
        await client._apply_human_like_delay("http://")
        assert "default" in client._domain_locks
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cloudscraper_semaphore_bounds_concurrency():
    """Verify CloudScraper semaphore bounds active threads to 12 (or CLOUDSCRAPER_MAX_CONCURRENCY)."""
    client = AsyncHTTPClient()
    try:
        # Default setting should be 12
        assert client._cloudscraper_semaphore._value == 12

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.content = b"<html>success</html>"
        fake_resp.headers = {}
        fake_resp.url = "https://mock-domain.com/coupon"
        fake_resp.cookies.get_dict.return_value = {}

        fake_scraper = MagicMock()

        active_in_sem = 0
        max_in_sem = 0
        sem_lock = asyncio.Lock()

        # Track semaphore occupancy directly
        orig_acquire = client._cloudscraper_semaphore.acquire
        orig_release = client._cloudscraper_semaphore.release

        async def tracked_acquire():
            nonlocal active_in_sem, max_in_sem
            res = await orig_acquire()
            async with sem_lock:
                active_in_sem += 1
                if active_in_sem > max_in_sem:
                    max_in_sem = active_in_sem
            return res

        def tracked_release():
            nonlocal active_in_sem
            active_in_sem -= 1
            orig_release()

        client._cloudscraper_semaphore.acquire = tracked_acquire
        client._cloudscraper_semaphore.release = tracked_release

        def slow_sync_get(*args, **kwargs):
            time.sleep(0.04)
            return fake_resp

        fake_scraper.get = slow_sync_get
        client._get_scraper = MagicMock(return_value=fake_scraper)
        client._is_safe_url = MagicMock(return_value=True)
        client._apply_human_like_delay = AsyncMock()

        # Launch 24 concurrent requests (double the semaphore capacity of 12)
        tasks = [
            client.get(
                f"https://mock-domain.com/coupon/{i}",
                use_cloudscraper=True,
                attempts=1,
            )
            for i in range(24)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 24
        assert all(r is not None and r.status_code == 200 for r in results)
        assert max_in_sem <= 12
        assert active_in_sem == 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_scraper_service_worker_sem_scaling():
    """Verify ScraperService creates worker_sem matching configured max_workers or setting, not hardcapped at 2."""
    captured_sem_values = []
    real_semaphore = asyncio.Semaphore

    def tracked_semaphore(value=1):
        captured_sem_values.append(value)
        return real_semaphore(value)

    # 1. Configured max_workers = 8
    service_custom = ScraperService(sites_to_scrape=["FreeCourseSites"], max_workers=8)
    assert service_custom.max_workers == 8

    async def dummy_scrape(detail_sem):
        pass

    for s in service_custom.scrapers:
        s.scrape = dummy_scrape
        s.error = None
        s.done = False

    with patch("asyncio.Semaphore", side_effect=tracked_semaphore):
        async for _ in service_custom.stream_results():
            pass
    await service_custom.close()

    # worker_sem should be 8, detail_sem should be 6 (settings.SCRAPER_DETAIL_CONCURRENCY)
    assert 8 in captured_sem_values
    assert 6 in captured_sem_values

    # 2. Default max_workers=None -> uses settings.MAX_SCRAPER_WORKERS (was previously hardcapped at 2)
    captured_sem_values.clear()
    service_default = ScraperService(sites_to_scrape=["FreeCourseSites", "E-next"])
    assert service_default.max_workers is None

    for s in service_default.scrapers:
        s.scrape = dummy_scrape
        s.error = None
        s.done = False

    expected_setting_workers = getattr(get_settings(), "MAX_SCRAPER_WORKERS", 6)
    with patch("asyncio.Semaphore", side_effect=tracked_semaphore):
        async for _ in service_default.stream_results():
            pass
    await service_default.close()

    assert captured_sem_values[0] == expected_setting_workers  # Matches setting, NOT hardcapped at 2!
    assert captured_sem_values[0] > 2
    assert len(captured_sem_values) >= 2
    assert captured_sem_values[0] == expected_setting_workers
    assert captured_sem_values.count(6) >= 2


@pytest.mark.asyncio
async def test_scraper_service_magicmock_settings_safety():
    """Verify stream_results defensively handles MagicMock settings without TypeError."""
    mock_settings = MagicMock()
    # Explicitly do NOT set MAX_SCRAPER_WORKERS or SCRAPER_DETAIL_CONCURRENCY as ints
    mock_settings.SCRAPER_RUN_TIMEOUT_SECONDS = 0.5
    mock_settings.SCRAPER_SITE_TIMEOUT_SECONDS = 0.5

    service = ScraperService(sites_to_scrape=["FreeCourseSites"])

    async def dummy_scrape(detail_sem):
        pass

    for s in service.scrapers:
        s.scrape = dummy_scrape
        s.error = None
        s.done = False

    with patch("config.settings.get_settings", return_value=mock_settings):
        # Must not raise "TypeError: 'MagicMock' object cannot be interpreted as an integer"
        async for _ in service.stream_results():
            pass
    await service.close()


@pytest.mark.asyncio
async def test_enrollment_manager_passes_max_workers():
    """Verify EnrollmentManager passes scraper_workers to ScraperService."""
    from app.models.database import EnrollmentRun
    from app.services.enrollment_manager import EnrollmentManager

    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrapers = []
    mock_instance.stream_results = MagicMock()
    async def empty_stream():
        if False:
            yield
    mock_instance.stream_results.return_value = empty_stream()
    mock_instance.close = AsyncMock()
    mock_scraper_cls.return_value = mock_instance

    run = EnrollmentRun(user_id=999, status="pending", currency="USD")

    manager = EnrollmentManager(
        user_id=999,
        run_id=888,
        udemy_client=MagicMock(),
        settings={"scraper_workers": 7, "sites": {"FreeCourseSites": True}},
    )

    with patch("app.services.enrollment_manager.ScraperService", mock_scraper_cls), \
         patch("app.services.enrollment_manager.SessionLocal") as mock_db:
        mock_session = MagicMock()
        mock_session.get.return_value = run
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_db.return_value.__enter__.return_value = mock_session

        # Run enrollment pipeline
        try:
            await asyncio.wait_for(manager.run_pipeline(), timeout=2.0)
        except Exception:
            pass

    # Verify max_workers=7 was passed to ScraperService
    assert mock_scraper_cls.called
    call_kwargs = mock_scraper_cls.call_args.kwargs
    assert call_kwargs.get("max_workers") == 7


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible(rendered: str) -> str:
    return _ANSI_RE.sub("", rendered)


def test_cli_scrape_help_displays_workers_option(monkeypatch):
    """Verify CLI scrape --help displays --workers and -w options."""
    import typer.rich_utils

    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", 120, raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["scrape", "--help"])
    assert result.exit_code == 0
    out = _visible(result.output)
    assert "--workers" in out
    assert "-w" in out
    assert "MAX_SCRAPER_WORKERS" in out


def test_cli_enroll_help_displays_workers_option(monkeypatch):
    """Verify CLI enroll --help displays --workers and -w options."""
    import typer.rich_utils

    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", 120, raising=False)
    runner = CliRunner()
    result = runner.invoke(app, ["enroll", "--help"])
    assert result.exit_code == 0
    out = _visible(result.output)
    assert "--workers" in out
    assert "-w" in out
    assert "MAX_SCRAPER_WORKERS" in out
