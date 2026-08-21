"""Live integration tests for scrapers to ensure they work against real site structures."""

import pytest
import pytest_asyncio
import asyncio
from app.services.scraper import (
    RealDiscountScraper,
    ENextScraper,
    InterviewGigScraper,
    UdemyXpertScraper,
    CoursesityScraper,
    CourseFolderScraper,
    CouponamiScraper,
    KorshubScraper,
    FreeCourseSitesScraper,
    DiscudemyScraper,
    CoursonScraper,
    CouponScorpionScraper,
    UdemyFreebiesScraper,
    IDownloadCouponScraper,
)
from app.services.http_client import AsyncHTTPClient
import os

# Live scraper tests require both an explicit marker selection and environment opt-in.
pytestmark = [
    pytest.mark.allow_network,
    pytest.mark.live_third_party,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_TESTS") != "true",
        reason="Live scraper tests require RUN_LIVE_TESTS=true",
    ),
]

@pytest_asyncio.fixture(loop_scope="function")
async def http_client():
    client = AsyncHTTPClient()
    yield client
    await client.close()

@pytest.mark.asyncio(loop_scope="function")
async def test_real_discount_live(http_client):
    """Unregistered class probe, not a live-fleet pin (C43)."""
    scraper = RealDiscountScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) <= 500
    print(f"\n[Real Discount] Found {len(scraper.data)} courses", flush=True)

@pytest.mark.asyncio(loop_scope="function")
async def test_freecoursesites_live(http_client):
    scraper = FreeCourseSitesScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    print(f"FreeCourseSites unique courses={len(scraper.data)}", flush=True)
    assert len(scraper.data) > 0, f"FreeCourseSites found 0 courses. Error: {scraper.error}"
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)


@pytest.mark.asyncio(loop_scope="function")
async def test_enext_live(http_client):
    """Thoroughly check E-next scraper."""
    scraper = ENextScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"E-next found 0 courses. Error: {scraper.error}"
    print(f"\n[E-next] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_interviewgig_live(http_client):
    """Interview Gig live: parser covered by unit tests; 0-ok this wave."""
    scraper = InterviewGigScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) <= 500
    print(f"\n[InterviewGig] Found {len(scraper.data)} courses", flush=True)


@pytest.mark.asyncio(loop_scope="function")
async def test_udemyxpert_live(http_client):
    """UdemyXpert live: parser covered by unit tests; 0-ok this wave."""
    scraper = UdemyXpertScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) <= 500
    print(f"\n[UdemyXpert] Found {len(scraper.data)} courses", flush=True)


@pytest.mark.asyncio(loop_scope="function")
async def test_coursesity_live(http_client):
    """Coursesity yields URLs without couponCode= by design (~498-class listing)."""
    scraper = CoursesityScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Coursesity found 0 courses. Error: {scraper.error}"
    print(f"\n[Coursesity] Found {len(scraper.data)} courses")


@pytest.mark.asyncio(loop_scope="function")
async def test_coursefolder_live(http_client):
    """Thoroughly check Course Folder scraper."""
    scraper = CourseFolderScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Course Folder found 0 courses. Error: {scraper.error}"
    print(f"\n[Course Folder] Found {len(scraper.data)} courses")


@pytest.mark.asyncio(loop_scope="function")
async def test_couponami_live(http_client):
    """Thoroughly check Couponami scraper."""
    scraper = CouponamiScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Couponami found 0 courses. Error: {scraper.error}"
    print(f"\n[Couponami] Found {len(scraper.data)} courses")


@pytest.mark.asyncio(loop_scope="function")
async def test_korshub_live(http_client):
    scraper = KorshubScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    print(f"\n[Korshub] Found {len(scraper.data)} courses", flush=True)
    assert len(scraper.data) > 0, f"Korshub found 0 courses. Error: {scraper.error}"
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)


@pytest.mark.asyncio(loop_scope="function")
async def test_discudemy_live(http_client):
    """Unregistered class probe, not a live-fleet pin (C43)."""
    scraper = DiscudemyScraper(http_client)
    await scraper.scrape(asyncio.Semaphore(5))
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)
    print(f"\n[Discudemy] Found {len(scraper.data)} courses", flush=True)


@pytest.mark.asyncio(loop_scope="function")
async def test_courson_live(http_client):
    scraper = CoursonScraper(http_client)
    await scraper.scrape(asyncio.Semaphore(5))
    assert len(scraper.data) <= 80
    assert all("couponCode=" in c.url for c in scraper.data)


@pytest.mark.asyncio(loop_scope="function")
async def test_couponscorpion_live(http_client):
    scraper = CouponScorpionScraper(http_client)
    await scraper.scrape(asyncio.Semaphore(5))
    print(f"\n[CouponScorpion] Found {len(scraper.data)} courses", flush=True)
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)


@pytest.mark.asyncio(loop_scope="function")
async def test_udemyfreebies_live(http_client):
    scraper = UdemyFreebiesScraper(http_client)
    await scraper.scrape(asyncio.Semaphore(5))
    print(f"\n[UdemyFreebies] Found {len(scraper.data)} courses", flush=True)
    assert len(scraper.data) > 0, f"UdemyFreebies found 0 courses. Error: {scraper.error}"
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)


@pytest.mark.asyncio(loop_scope="function")
async def test_idownloadcoupon_live(http_client):
    scraper = IDownloadCouponScraper(http_client)
    await scraper.scrape(asyncio.Semaphore(5))
    print(f"\n[IDownloadCoupon] Found {len(scraper.data)} courses", flush=True)
    assert len(scraper.data) <= 500
    assert all("udemy.com/course/" in c.url for c in scraper.data)
