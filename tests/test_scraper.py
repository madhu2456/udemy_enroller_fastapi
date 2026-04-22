"""Tests for the ScraperService."""

import pytest
import asyncio
from app.services.scraper import ScraperService

@pytest.mark.asyncio
async def test_scraper_service_initialization():
    """Test that ScraperService initializes correctly with default sites."""
    scraper = ScraperService()
    assert len(scraper.sites) > 0
    assert "Real Discount" in scraper.sites
    await scraper.http.close()

@pytest.mark.asyncio
async def test_scraper_progress_structure():
    """Test that get_progress returns the expected structure."""
    scraper = ScraperService(sites_to_scrape=["Real Discount"])
    progress = scraper.get_progress()
    assert len(progress) == 1
    assert progress[0]["site"] == "Real Discount"
    assert "progress" in progress[0]
    assert "done" in progress[0]
    await scraper.http.close()

@pytest.mark.asyncio
async def test_tutorialbar_scraper_parsing():
    """Test that TutorialBarScraper can parse course links from WordPress API."""
    from app.services.scraper import TutorialBarScraper
    from unittest.mock import MagicMock, AsyncMock

    mock_http = MagicMock()
    # Mock get and safe_json as AsyncMocks
    mock_http.get = AsyncMock()
    mock_http.safe_json = AsyncMock()

    scraper = TutorialBarScraper(mock_http)

    # Mock the WordPress API response
    api_data = [
        {
            "title": {"rendered": "Course 1 | TutorialBar"},
            "content": {"rendered": '<a href="https://www.udemy.com/course/test1/?couponCode=FREE1">Link</a>'}
        },
        {
            "title": {"rendered": "Course 2 | TutorialBar"},
            "content": {"rendered": '<a href="https://www.udemy.com/course/test2/?couponCode=FREE2">Link</a>'}
        }
    ]

    mock_http.safe_json.return_value = api_data

    # Mock the initial API request
    mock_resp = MagicMock()
    mock_http.get.return_value = mock_resp

    semaphore = asyncio.Semaphore(1)
    await scraper.scrape(semaphore)

    assert len(scraper.data) >= 2
    assert scraper.data[0].title == "Course 1"
    assert "udemy.com/course/test1" in scraper.data[0].url

