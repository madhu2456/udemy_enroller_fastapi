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
    assert "FreeCourseSites" in scraper.sites
    assert "FreeWebCart" in scraper.sites
    await scraper.http.close()


@pytest.mark.asyncio
async def test_scraper_progress_structure():
    """Test that get_progress returns the expected structure."""
    scraper = ScraperService(sites_to_scrape=["FreeWebCart", "FreeCourseSites"])
    progress = scraper.get_progress()
    assert len(progress) == 2

    fwc_progress = next(p for p in progress if p["site"] == "FreeWebCart")
    assert "progress" in fwc_progress
    assert "done" in fwc_progress
    await scraper.http.close()
