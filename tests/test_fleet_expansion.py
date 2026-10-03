"""Empirical test suite for Wave 4 Scraper Fleet Expansion (Task 4.4).

Tests:
1. TelegramDealsScraper: anchor tags, plain text links, coupon parsing, non-200,
   empty response, and deduplication.
2. WordPressFeedsScraper [FM-006]: RSS/Atom feed parsing, 45-min freshness guard,
   and _parse_feed_item_date with RFC 2822 / ISO 8601.
3. SCRAPER_REGISTRY & UserSettings: registration, instantiation, and default_sites.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import UserSettings
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import (
    SCRAPER_REGISTRY,
    TelegramDealsScraper,
    WordPressFeedsScraper,
    _parse_feed_item_date,
)


@pytest.mark.asyncio
async def test_telegram_deals_scraper_parsing_and_resilience():
    """Test TelegramDealsScraper parses web preview HTML and handles errors."""
    mock_http = MagicMock(spec=AsyncHTTPClient)
    html_content = """
    <div class="tgme_widget_message_text">
        <a href="https://www.udemy.com/course/telegram-course/?couponCode=TG2026">Telegram Course</a>
    </div>
    <div class="tgme_widget_message_text">
        Plain text deal: https://www.udemy.com/course/plain-deal/ coupon: PLAIN100
    </div>
    <div class="tgme_widget_message_text">
        Duplicate deal: https://www.udemy.com/course/telegram-course/?couponCode=TG2026
    </div>
    """
    resp_ok = MagicMock(status_code=200, text=html_content)
    resp_empty = MagicMock(status_code=500, text="")
    mock_http.get = AsyncMock(side_effect=[resp_ok, resp_empty])

    scraper = TelegramDealsScraper(mock_http)
    assert scraper.site_name == "Telegram Deals"
    assert scraper.code_name == "td"

    await scraper.scrape(asyncio.Semaphore(2))
    assert scraper.done is True
    assert len(scraper.data) == 2
    urls = [c.url for c in scraper.data]
    assert any("telegram-course" in u and "couponCode=TG2026" in u for u in urls)
    assert any("plain-deal" in u and "couponCode=PLAIN100" in u for u in urls)


@pytest.mark.asyncio
async def test_wordpress_feeds_scraper_freshness_guard():
    """Test WordPressFeedsScraper accepts fresh items (<= 45m) and discards stale (FM-006)."""
    now = datetime.now(timezone.utc)
    fresh_date = (now - timedelta(minutes=15)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    stale_date = (now - timedelta(minutes=60)).strftime("%a, %d %b %Y %H:%M:%S +0000")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Fresh Course</title>
          <pubDate>{fresh_date}</pubDate>
          <description><![CDATA[<a href="https://www.udemy.com/course/fresh-course/?couponCode=FRESH">Link</a>]]></description>
        </item>
        <item>
          <title>Stale Course</title>
          <pubDate>{stale_date}</pubDate>
          <description><![CDATA[<a href="https://www.udemy.com/course/stale-course/?couponCode=STALE">Link</a>]]></description>
        </item>
      </channel>
    </rss>"""

    mock_http = MagicMock(spec=AsyncHTTPClient)
    resp = MagicMock(status_code=200, text=rss_xml)
    mock_http.get = AsyncMock(return_value=resp)

    scraper = WordPressFeedsScraper(mock_http)
    assert scraper.site_name == "WordPress Feeds"
    assert scraper.code_name == "wp"
    assert scraper.MAX_ITEM_AGE_MINUTES == 45

    await scraper.scrape(asyncio.Semaphore(2))
    assert scraper.done is True
    assert len(scraper.data) == 1
    assert "fresh-course" in scraper.data[0].url
    assert "stale-course" not in [c.url for c in scraper.data]


def test_parse_feed_item_date():
    """Test _parse_feed_item_date parses RFC 2822, ISO 8601, and rejects invalid."""
    rfc_date = "Sat, 03 Oct 2026 12:00:00 +0000"
    dt_rfc = _parse_feed_item_date(rfc_date)
    assert dt_rfc is not None
    assert dt_rfc.year == 2026 and dt_rfc.month == 10 and dt_rfc.day == 3
    assert dt_rfc.tzinfo == timezone.utc

    iso_date = "2026-10-03T12:00:00Z"
    dt_iso = _parse_feed_item_date(iso_date)
    assert dt_iso is not None
    assert dt_iso.year == 2026 and dt_iso.hour == 12

    assert _parse_feed_item_date("") is None
    assert _parse_feed_item_date("not-a-valid-date") is None


def test_scraper_registry_and_user_settings_expansion():
    """Verify expanded scrapers exist in SCRAPER_REGISTRY and UserSettings."""
    expected_scrapers = {
        "Telegram Deals": (TelegramDealsScraper, "td"),
        "WordPress Feeds": (WordPressFeedsScraper, "wp"),
    }
    mock_http = MagicMock(spec=AsyncHTTPClient)

    for name, (cls, code) in expected_scrapers.items():
        assert name in SCRAPER_REGISTRY
        assert SCRAPER_REGISTRY[name] is cls
        instance = cls(mock_http)
        assert instance.site_name == name
        assert instance.code_name == code

    default_sites = UserSettings.default_sites()
    for name in expected_scrapers:
        assert name in default_sites
        assert default_sites[name] is True
