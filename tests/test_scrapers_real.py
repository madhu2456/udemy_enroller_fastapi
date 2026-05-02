"""Live integration tests for scrapers to ensure they work against real site structures."""

import pytest
import pytest_asyncio
import asyncio
from app.services.scraper import (
    RealDiscountScraper,
    ENextScraper,
    CourseCouponClubScraper,
    InterviewGigScraper,
    UdemyXpertScraper,
    CoursesityScraper,
    CourseFolderScraper,
    CouponamiScraper,
    KorshubScraper,
)
from app.services.http_client import AsyncHTTPClient

@pytest_asyncio.fixture(loop_scope="function")
async def http_client():
    client = AsyncHTTPClient()
    yield client
    await client.close()

@pytest.mark.asyncio(loop_scope="function")
async def test_real_discount_live(http_client):
    """Thoroughly check Real Discount scraper."""
    scraper = RealDiscountScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Real Discount found 0 courses. Error: {scraper.error}"
    print(f"\n[Real Discount] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_coursecouponclub_live(http_client):
    """Thoroughly check Course Coupon Club scraper."""
    scraper = CourseCouponClubScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"CourseCouponClub found 0 courses. Error: {scraper.error}"
    print(f"\n[CourseCouponClub] Found {len(scraper.data)} courses")

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
    """Thoroughly check Interview Gig scraper."""
    scraper = InterviewGigScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Interview Gig found 0 courses. Error: {scraper.error}"
    print(f"\n[InterviewGig] Found {len(scraper.data)} courses")


@pytest.mark.asyncio(loop_scope="function")
async def test_udemyxpert_live(http_client):
    """Thoroughly check UdemyXpert scraper."""
    scraper = UdemyXpertScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"UdemyXpert found 0 courses. Error: {scraper.error}"
    print(f"\n[UdemyXpert] Found {len(scraper.data)} courses")


@pytest.mark.asyncio(loop_scope="function")
async def test_coursesity_live(http_client):
    """Thoroughly check Coursesity scraper."""
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
    """Thoroughly check Korshub scraper."""
    scraper = KorshubScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Korshub found 0 courses. Error: {scraper.error}"
    print(f"\n[Korshub] Found {len(scraper.data)} courses")
