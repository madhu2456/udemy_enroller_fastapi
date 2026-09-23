"""Tests for the ScraperService."""

import asyncio
from unittest.mock import MagicMock, patch

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
    assert "Real Discount" in scraper.sites
    assert "FreeCourseSites" in scraper.sites
    assert "OnlineCourses.ooo" in scraper.sites
    assert "FreebiesGlobal" in scraper.sites
    assert "GeeksGod" in scraper.sites
    assert "TutorialBar" in scraper.sites
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


def test_registry_keeps_frozen_ten_and_appends_seven():
    keys = list(SCRAPER_REGISTRY)
    defaults = list(UserSettings.default_sites())
    assert keys == defaults
    assert keys[:10] == FROZEN_10
    assert keys[10:] == [
        "Courson",
        "CouponScorpion",
        "Real Discount",
        "OnlineCourses.ooo",
        "FreebiesGlobal",
        "GeeksGod",
        "TutorialBar",
    ]
    assert len(keys) == 17
    assert len(SCRAPER_REGISTRY) == 17
    codes = [cls(MagicMock()).code_name for cls in SCRAPER_REGISTRY.values()]
    assert len(codes) == len(set(codes))
    assert set(codes) >= {"cr", "csc", "rd", "oc", "fg", "gg", "tb"}
    assert "Discudemy" not in keys
    assert "FreeWebCart" not in keys
    assert "Course Joiner" not in keys


@pytest.mark.asyncio
async def test_stream_results_one_shot_fleet_timeout_spares_queued():
    """Fleet timeout cancels in-flight scrapers once; queued workers still complete."""
    service = ScraperService(
        sites_to_scrape=["FreeCourseSites", "E-next", "Interview Gig", "UdemyXpert"]
    )
    assert len(service.scrapers) == 4

    acquire_n = 0

    async def gated_scrape(detail_sem):
        nonlocal acquire_n
        acquire_n += 1
        if acquire_n <= 2:
            await asyncio.sleep(2.0)
        else:
            await asyncio.sleep(0.05)

    for scraper in service.scrapers:
        scraper.scrape = gated_scrape
        scraper.error = None
        scraper.done = False

    mock_settings = MagicMock()
    mock_settings.MAX_SCRAPER_WORKERS = 2
    mock_settings.SCRAPER_RUN_TIMEOUT_SECONDS = 0.35
    mock_settings.SCRAPER_SITE_TIMEOUT_SECONDS = 5

    outcomes = []
    try:
        with patch("config.settings.get_settings", return_value=mock_settings):
            async for scraper, state in service.stream_results():
                outcomes.append(
                    {
                        "site": scraper.site_name,
                        "state": state,
                        "error": scraper.error,
                    }
                )
    finally:
        await service.close()

    assert len(outcomes) == 4
    timed_out = [row for row in outcomes if row["state"] == "timed_out"]
    completed = [row for row in outcomes if row["state"] == "completed"]
    assert timed_out, "expected in-flight scrapers to be cancelled as timed_out"
    assert completed, "expected queued scrapers to finish after acquiring a worker"
    assert all(
        "Run timed out overall" not in str(row["error"] or "") for row in completed
    )
    assert all(
        "Run timed out overall" not in str(row["error"] or "")
        for row in outcomes
        if row["state"] != "timed_out"
    )
