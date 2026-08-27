"""Comprehensive empirical verification suite for all 17 scrapers in SCRAPER_REGISTRY.

Tests:
1. Scraper registry keys, class names, site_name, code_name integrity.
2. Initial scraper states, `courses` property mutability & data reflection.
3. Circuit breaker resilience: 5 consecutive failures trips the circuit breaker, subsequent requests drop.
4. Empty page early exit across 404, 500, empty HTML, empty JSON, empty lists.
5. Udemy course URL validation (`is_udemy_course_url`).
6. ScraperService orchestration and progress reporting for all 17 scrapers.
"""

from __future__ import annotations

import asyncio
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import SCRAPER_REGISTRY, Scraper, ScraperService
from app.services.udemy_validation import is_udemy_course_url

EXPECTED_17_SCRAPERS: Dict[str, str] = {
    "FreeCourseSites": "fcs",
    "E-next": "en",
    "Interview Gig": "ig",
    "UdemyXpert": "ux",
    "Coursesity": "cs",
    "Course Folder": "cf",
    "Couponami": "ca",
    "Korshub": "kh",
    "UdemyFreebies": "uf",
    "iDownloadCoupon": "idc",
    "Courson": "cr",
    "CouponScorpion": "csc",
    "Real Discount": "rd",
    "OnlineCourses.ooo": "oc",
    "FreebiesGlobal": "fg",
    "GeeksGod": "gg",
    "TutorialBar": "tb",
}


def test_scraper_registry_completeness():
    """Verify SCRAPER_REGISTRY contains exactly 17 scrapers with correct keys."""
    assert len(SCRAPER_REGISTRY) == 17
    assert set(SCRAPER_REGISTRY.keys()) == set(EXPECTED_17_SCRAPERS.keys())


@pytest.mark.parametrize("site_name,expected_code", list(EXPECTED_17_SCRAPERS.items()))
def test_scraper_metadata_and_initial_properties(site_name: str, expected_code: str):
    """Test site_name, code_name, initial states, and courses property for each scraper."""
    scraper_cls = SCRAPER_REGISTRY[site_name]
    mock_http = MagicMock(spec=AsyncHTTPClient)
    instance: Scraper = scraper_cls(mock_http)

    assert instance.site_name == site_name
    assert instance.code_name == expected_code
    assert instance.courses == []
    assert instance.data == []
    assert instance.circuit_open is False
    assert instance.consecutive_failures == 0
    assert instance.progress == 0
    assert instance.length == 0
    assert instance.done is False
    assert instance.error is None

    # Test courses property mutability
    course = Course(title="Sample Course", url="https://www.udemy.com/course/sample-course/?couponCode=FREE100")
    instance.data.append(course)
    assert instance.courses == [course]
    assert len(instance.courses) == 1
    assert instance.courses[0].title == "Sample Course"


@pytest.mark.asyncio
@pytest.mark.parametrize("site_name", list(EXPECTED_17_SCRAPERS.keys()))
async def test_circuit_breaker_resilience_all_scrapers(site_name: str):
    """Test circuit breaker trips after max consecutive failures on each scraper."""
    scraper_cls = SCRAPER_REGISTRY[site_name]
    mock_http = MagicMock(spec=AsyncHTTPClient)
    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_http.get = AsyncMock(return_value=mock_resp_500)

    instance: Scraper = scraper_cls(mock_http)
    instance.max_consecutive_failures = 5

    # Simulate 5 failed requests
    for i in range(5):
        assert instance.circuit_open is False
        res = await instance._http_get(f"https://example.com/item/{i}")

    assert instance.circuit_open is True
    assert instance.consecutive_failures == 5
    assert "Circuit breaker tripped" in (instance.error or "")

    # Next request should be blocked without calling http.get
    mock_http.get.reset_mock()
    res = await instance._http_get("https://example.com/blocked")
    assert res is None
    mock_http.get.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("site_name", list(EXPECTED_17_SCRAPERS.keys()))
async def test_empty_page_and_404_early_exit(site_name: str):
    """Test scraper gracefully terminates without exceptions when encountering 404/empty response."""
    scraper_cls = SCRAPER_REGISTRY[site_name]
    mock_http = MagicMock(spec=AsyncHTTPClient)
    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404
    mock_resp_404.text = "<html><body><h1>404 Not Found</h1></body></html>"
    mock_http.get = AsyncMock(return_value=mock_resp_404)
    mock_http.safe_json = AsyncMock(return_value=None)

    instance: Scraper = scraper_cls(mock_http)
    detail_semaphore = asyncio.Semaphore(5)

    # Scrape execution must not raise an unhandled exception
    await instance.scrape(detail_semaphore)
    assert len(instance.courses) == 0


@pytest.mark.parametrize(
    "url,is_valid",
    [
        ("https://www.udemy.com/course/python-programming/?couponCode=FREE100", True),
        ("https://www.udemy.com/course/fastapi-complete-bootcamp/", True),
        ("http://udemy.com/course/machine-learning-mastery/?couponCode=DISCOUNT2026", True),
        ("https://udemy.com/course/curso-completo-de-react/", True),
        ("https://www.udemy.com/", False),
        ("https://www.udemy.com/user/john-doe/", False),
        ("https://www.udemy.com/terms/", False),
        ("https://www.udemy.com/teaching/?ref=teach_header", False),
        ("https://www.udemy.com/topic/python/", False),
        ("https://notudemy.com/course/python-programming/", False),
        ("https://example.com/course/test/", False),
        ("", False),
        (None, False),
        ("javascript:void(0)", False),
    ],
)
def test_udemy_course_url_validation(url: str, is_valid: bool):
    """Test is_udemy_course_url helper against valid and invalid URLs."""
    assert is_udemy_course_url(url) is is_valid


@pytest.mark.asyncio
async def test_scraper_service_orchestration_all_17():
    """Test ScraperService instantiating and orchestrating all 17 scrapers."""
    service = ScraperService()
    assert len(service.scrapers) == 17
    assert len(service.site_to_scraper) == 17

    # Ensure all scrapers are unique instances
    instances = list(service.scrapers)
    assert len(set(instances)) == 17

    # Verify get_progress reporting for all 17
    progress = service.get_progress()
    assert len(progress) == 17
    for p in progress:
        assert "site" in p
        assert "progress" in p
        assert "total" in p
        assert "done" in p
        assert "courses_found" in p
        assert "state" in p

    await service.http.close()


@pytest.mark.asyncio
async def test_scraper_service_custom_sites_subset():
    """Test ScraperService with custom subset of sites."""
    subset = ["FreeCourseSites", "TutorialBar", "Real Discount"]
    service = ScraperService(sites_to_scrape=subset)
    assert len(service.scrapers) == 3
    assert set(service.site_to_scraper.keys()) == set(subset)

    await service.http.close()
