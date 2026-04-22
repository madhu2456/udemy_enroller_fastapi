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
    """Test that TutorialBarScraper can parse course links from blog page."""
    from app.services.scraper import TutorialBarScraper
    from unittest.mock import MagicMock, AsyncMock

    mock_http = MagicMock()
    # Mock get as AsyncMock for blog page scraping
    mock_http.get = AsyncMock()

    scraper = TutorialBarScraper(mock_http)
    scraper.enable_headless = False  # Use HTTP scraping, not Playwright

    # Mock the blog page HTML response with blog post links
    blog_html = '''
    <html>
        <body>
            <a href="https://www.tutorialbar.com/blog/course-1-tutorial/">Course 1</a>
            <a href="https://www.tutorialbar.com/blog/course-2-tutorial/">Course 2</a>
        </body>
    </html>
    '''
    
    # First call gets the blog listing page
    mock_blog_resp = MagicMock()
    mock_blog_resp.content = blog_html.encode()
    
    # Second and third calls get the individual blog post pages
    course1_html = '''
    <html>
        <head><title>Course 1 | TutorialBar</title></head>
        <body>
            <h1>Course 1 Tutorial</h1>
            <a href="https://www.udemy.com/course/test1/?couponCode=FREE1">Udemy Link</a>
        </body>
    </html>
    '''
    
    course2_html = '''
    <html>
        <head><title>Course 2 | TutorialBar</title></head>
        <body>
            <h1>Course 2 Tutorial</h1>
            <a href="https://www.udemy.com/course/test2/?couponCode=FREE2">Udemy Link</a>
        </body>
    </html>
    '''
    
    mock_course1_resp = MagicMock()
    mock_course1_resp.content = course1_html.encode()
    
    mock_course2_resp = MagicMock()
    mock_course2_resp.content = course2_html.encode()
    
    # Set up the mock to return different responses for different URLs
    mock_http.get.side_effect = [mock_blog_resp, mock_course1_resp, mock_course2_resp]

    semaphore = asyncio.Semaphore(1)
    await scraper.scrape(semaphore)

    assert len(scraper.data) >= 2
    titles = [c.title for c in scraper.data]
    assert any("Course 1" in t for t in titles)
    assert any("Course 2" in t for t in titles)
