"""Tests for the ScraperService."""

from unittest.mock import MagicMock

import pytest

from app.models.database import UserSettings
from app.services.scraper import SCRAPER_REGISTRY, ScraperService

FROZEN_10 = [
    "FreeCourseSites",
    "E-next",
    "Interview Gig",
    "UdemyXpert",
    "Coursesity",
    "Course Folder",
    "Couponami",
    "Korshub",
    "UdemyFreebies",
    "iDownloadCoupon",
]


@pytest.mark.asyncio
async def test_scraper_service_initialization():
    """Test that ScraperService initializes correctly with default sites."""
    scraper = ScraperService()
    assert len(scraper.sites) > 0
    assert "Real Discount" not in scraper.sites
    assert "FreeCourseSites" in scraper.sites
    assert "FreeWebCart" not in scraper.sites
    assert "Course Joiner" not in scraper.sites
    await scraper.http.close()


@pytest.mark.asyncio
async def test_scraper_progress_structure():
    """Test that get_progress returns the expected structure."""
    scraper = ScraperService(sites_to_scrape=["FreeCourseSites", "Couponami"])
    progress = scraper.get_progress()
    assert len(progress) == 2

    fcs_progress = next(p for p in progress if p["site"] == "FreeCourseSites")
    assert "progress" in fcs_progress
    assert "done" in fcs_progress
    await scraper.http.close()


def test_generic_course_title_rejection():
    """Test that generic and localized CTA titles are rejected."""
    service = ScraperService(sites_to_scrape=["FreeCourseSites"])
    scraper = service.site_to_scraper["FreeCourseSites"]

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


def test_registry_keeps_frozen_ten_and_appends_two():
    keys = list(SCRAPER_REGISTRY)
    defaults = list(UserSettings.default_sites())
    assert keys == defaults
    assert keys[:10] == FROZEN_10
    assert keys[-2:] == ["Courson", "CouponScorpion"]
    assert len(keys) == 12
    assert len(SCRAPER_REGISTRY) == 12
    codes = [cls(MagicMock()).code_name for cls in SCRAPER_REGISTRY.values()]
    assert len(codes) == len(set(codes))
    assert set(codes) >= {"cr", "csc"}
    assert "Real Discount" not in keys
    assert "Discudemy" not in keys
    assert "FreeWebCart" not in keys
    assert "Course Joiner" not in keys
