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
@pytest.mark.vcr()
async def test_scraper_real_discount_fetch():
    """Test that the Real Discount scraper can fetch data (mocked via VCR)."""
    scraper = ScraperService(sites_to_scrape=["Real Discount"])
    courses = await scraper.scrape_all()
    await scraper.http.close()
    
    assert isinstance(courses, list)
    # The list may be empty if the mocked HTTP response had no courses, 
    # but the scrape() should return a list without crashing.
