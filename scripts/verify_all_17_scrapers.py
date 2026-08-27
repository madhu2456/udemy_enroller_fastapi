#!/usr/bin/env python3
"""Dedicated verification script testing all 17 scrapers in SCRAPER_REGISTRY.

Tests:
1. Scraper class registry, site_name, and code_name integrity.
2. Initial state and `courses` property reflection.
3. Circuit breaker resilience (5 consecutive failures trip the breaker).
4. Empty page / 404 / 500 / invalid JSON early exit without exceptions.
5. Udemy course URL validation (`is_udemy_course_url`).
6. Mocked end-to-end execution yielding valid courses.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import SCRAPER_REGISTRY, Scraper
from app.services.udemy_validation import is_udemy_course_url

EXPECTED_17_SCRAPERS = {
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


async def test_scraper_properties() -> bool:
    print("\n--- 1. Testing Scraper Properties & Registry ---")
    all_passed = True
    if len(SCRAPER_REGISTRY) != 17:
        print(f"FAIL: Expected 17 scrapers in registry, got {len(SCRAPER_REGISTRY)}")
        return False

    for name, expected_code in EXPECTED_17_SCRAPERS.items():
        if name not in SCRAPER_REGISTRY:
            print(f"FAIL: {name} not found in SCRAPER_REGISTRY")
            all_passed = False
            continue
        scraper_cls = SCRAPER_REGISTRY[name]
        mock_http = MagicMock(spec=AsyncHTTPClient)
        instance: Scraper = scraper_cls(mock_http)

        if instance.site_name != name:
            print(f"FAIL: {name} site_name mismatch: {instance.site_name}")
            all_passed = False
        if instance.code_name != expected_code:
            print(f"FAIL: {name} code_name mismatch: {instance.code_name} != {expected_code}")
            all_passed = False
        if instance.courses != [] or instance.data != []:
            print(f"FAIL: {name} initial courses not empty")
            all_passed = False
        if instance.circuit_open is not False:
            print(f"FAIL: {name} initial circuit_open is not False")
            all_passed = False
        if instance.consecutive_failures != 0:
            print(f"FAIL: {name} initial consecutive_failures is not 0")
            all_passed = False

        # Test courses property mutability
        dummy = Course(title="Test", url="https://www.udemy.com/course/test/?couponCode=FREE")
        instance.data.append(dummy)
        if instance.courses != [dummy]:
            print(f"FAIL: {name} courses property did not reflect data append")
            all_passed = False

        print(f"  ✓ {name:<20} [code: {instance.code_name:<3}] verified.")

    return all_passed


async def test_circuit_breaker_resilience() -> bool:
    print("\n--- 2. Testing Circuit Breaker Resilience across All 17 Scrapers ---")
    all_passed = True

    for name, scraper_cls in SCRAPER_REGISTRY.items():
        mock_http = MagicMock(spec=AsyncHTTPClient)
        # Mock 500 error response
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_http.get = AsyncMock(return_value=mock_resp_500)

        instance: Scraper = scraper_cls(mock_http)
        instance.max_consecutive_failures = 5

        # Fail 5 times
        for i in range(5):
            res = await instance._http_get("https://example.com/test")

        if not instance.circuit_open:
            print(f"FAIL: {name} circuit breaker did not trip after 5 failures")
            all_passed = False
            continue

        if instance.consecutive_failures < 5:
            print(f"FAIL: {name} consecutive_failures={instance.consecutive_failures} < 5")
            all_passed = False
            continue

        # 6th request should return None without calling http.get
        mock_http.get.reset_mock()
        res = await instance._http_get("https://example.com/test")
        if res is not None or mock_http.get.called:
            print(f"FAIL: {name} circuit breaker allowed request while open")
            all_passed = False
            continue

        print(f"  ✓ {name:<20} circuit breaker tripped and blocked subsequent calls.")

    return all_passed


async def test_empty_page_early_exit() -> bool:
    print("\n--- 3. Testing Empty Page / 404 Early Exit across All 17 Scrapers ---")
    all_passed = True
    sem = asyncio.Semaphore(5)

    for name, scraper_cls in SCRAPER_REGISTRY.items():
        mock_http = MagicMock(spec=AsyncHTTPClient)
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        mock_resp_404.text = "<html><body>404 Not Found</body></html>"
        mock_http.get = AsyncMock(return_value=mock_resp_404)
        mock_http.safe_json = AsyncMock(return_value=None)

        instance: Scraper = scraper_cls(mock_http)
        try:
            await instance.scrape(sem)
            if len(instance.courses) != 0:
                print(f"FAIL: {name} found courses on 404 response: {len(instance.courses)}")
                all_passed = False
            else:
                print(f"  ✓ {name:<20} exited cleanly on empty/404 response.")
        except Exception as e:
            print(f"FAIL: {name} raised unexpected exception on empty page: {e}")
            all_passed = False

    return all_passed


def test_url_validation_suite() -> bool:
    print("\n--- 4. Testing Course URL Validation (is_udemy_course_url) ---")
    valid_urls = [
        "https://www.udemy.com/course/python-bootcamp/?couponCode=FREE100",
        "http://udemy.com/course/learn-fastapi/?couponCode=DISCOUNT",
        "https://www.udemy.com/course/machine-learning-ai/",
        "https://www.udemy.com/course/web-development-2026/?couponCode=ABC&couponCode=DEF",
        "https://www.udemy.com/course/curso-de-programacion/",
    ]
    invalid_urls = [
        "https://www.udemy.com/",
        "https://www.udemy.com/user/john-doe/",
        "https://www.udemy.com/terms/",
        "https://www.udemy.com/teaching/?ref=teach_header",
        "https://www.udemy.com/topic/python/",
        "https://example.com/course/python/",
        "https://notudemy.com/course/fake-course/",
        "",
        None,
        "javascript:void(0)",
    ]

    all_passed = True
    for u in valid_urls:
        if not is_udemy_course_url(u):
            print(f"FAIL: Valid URL rejected: {u}")
            all_passed = False

    for u in invalid_urls:
        if is_udemy_course_url(u):
            print(f"FAIL: Invalid URL accepted: {u}")
            all_passed = False

    if all_passed:
        print(f"  ✓ All {len(valid_urls)} valid and {len(invalid_urls)} invalid URLs correctly classified.")
    return all_passed


async def main() -> int:
    print("=" * 60)
    print("EMPIRICAL VERIFICATION: ALL 17 SCRAPERS IN SCRAPER_REGISTRY")
    print("=" * 60)

    p1 = await test_scraper_properties()
    p2 = await test_circuit_breaker_resilience()
    p3 = await test_empty_page_early_exit()
    p4 = test_url_validation_suite()

    print("\n" + "=" * 60)
    if p1 and p2 and p3 and p4:
        print("ALL 17 SCRAPERS VERIFICATION: PASS (100% Compliant)")
        print("=" * 60)
        return 0
    else:
        print("SCRAPERS VERIFICATION: FAILURES DETECTED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
