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


def test_generic_course_title_rejection():
    """Test that generic and localized CTA titles are rejected."""
    service = ScraperService(sites_to_scrape=["FreeWebCart"])
    scraper = service.site_to_scraper["FreeWebCart"]

    # Valid titles
    assert scraper._is_generic_course_title("Python for Beginners") is False
    assert scraper._is_generic_course_title("Complete Web Development Bootcamp 2024") is False

    # Generic English titles
    assert scraper._is_generic_course_title("Get Course Now") is True
    assert scraper._is_generic_course_title("Enroll for Free") is True
    assert scraper._is_generic_course_title("Start Course") is True
    assert scraper._is_generic_course_title("Grab Discount") is True

    # Localized titles
    assert scraper._is_generic_course_title("Enroll Here") is True
    assert scraper._is_generic_course_title("Obtener el Curso") is True
    assert scraper._is_generic_course_title("Kursu İncele") is True
