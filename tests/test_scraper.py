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
    """Test that TutorialBarScraper can parse course links from HTML."""
    from app.services.scraper import TutorialBarScraper
    from unittest.mock import MagicMock
    
    mock_http = MagicMock()
    scraper = TutorialBarScraper(mock_http)
    
    html = """
    <html>
        <body>
            <a href="https://www.tutorialbar.com/python-programming-for-beginners-free-course-2026/">Course 1</a>
            <a href="https://www.tutorialbar.com/category/ignore-me/">Category</a>
            <a href="https://www.tutorialbar.com/complete-java-masterclass-zero-to-hero-2026-edition/">Course 2</a>
        </body>
    </html>
    """
    
    # Mock the detail fetch
    detail_html = '<html><head><title>Test Course | TutorialBar</title></head><body><a href="https://www.udemy.com/course/test/?couponCode=FREE">Get Link</a></body></html>'
    detail_resp = MagicMock()
    detail_resp.content = detail_html.encode()
    
    # Mock the home page fetch
    home_resp = MagicMock()
    home_resp.content = html.encode()

    async def side_effect(url, **kwargs):
        if url == "https://www.tutorialbar.com/":
            return home_resp
        if "udemy.com" in url: 
            return None
        return detail_resp
        
    mock_http.get.side_effect = side_effect
    
    semaphore = asyncio.Semaphore(1)
    await scraper.scrape(semaphore)
    
    assert len(scraper.data) >= 2
    assert "udemy.com/course/test/" in scraper.data[0].url
