"""Live integration tests for scrapers to ensure they work against real site structures."""

import pytest
import pytest_asyncio
import asyncio
from app.services.scraper import (
    UdemyFreebiesScraper,
    RealDiscountScraper,
    IDownloadCouponsScraper,
    CourseJoinerScraper,
    ENextScraper,
    CouponamiScraper,
    CourseCouponClubScraper,
    CouponScorpionScraper,
    FreeWebCartScraper,
    EasyLearnScraper
)
from app.services.http_client import AsyncHTTPClient

@pytest_asyncio.fixture(loop_scope="function")
async def http_client():
    client = AsyncHTTPClient()
    yield client
    await client.close()

@pytest.mark.asyncio(loop_scope="function")
async def test_easylearn_live(http_client):
    """Thoroughly check EasyLearn scraper."""
    scraper = EasyLearnScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"EasyLearn found 0 courses. Error: {scraper.error}"
    print(f"\n[EasyLearn] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_freewebcart_live(http_client):
    """Thoroughly check FreeWebCart scraper."""
    scraper = FreeWebCartScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"FreeWebCart found 0 courses. Error: {scraper.error}"
    print(f"\n[FreeWebCart] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_couponscorpion_live(http_client):
    """Thoroughly check Coupon Scorpion scraper (aliased to Real Discount)."""
    scraper = RealDiscountScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"CouponScorpion found 0 courses. Error: {scraper.error}"
    print(f"\n[CouponScorpion] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_coursecouponclub_live(http_client):
    """Thoroughly check Course Coupon Club scraper."""
    scraper = CourseCouponClubScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"CourseCouponClub found 0 courses. Error: {scraper.error}"
    print(f"\n[CourseCouponClub] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_couponami_live(http_client):
    """Thoroughly check Couponami scraper."""
    scraper = CouponamiScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Couponami found 0 courses. Error: {scraper.error}"
    print(f"\n[Couponami] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_real_discount_live(http_client):
    """Thoroughly check Real Discount scraper."""
    scraper = RealDiscountScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Real Discount found 0 courses. Error: {scraper.error}"
    print(f"\n[Real Discount] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_udemy_freebies_live(http_client):
    """Thoroughly check Udemy Freebies scraper."""
    scraper = UdemyFreebiesScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Udemy Freebies found 0 courses. Error: {scraper.error}"
    print(f"\n[Udemy Freebies] Found {len(scraper.data)} courses")
    for item in scraper.data[:5]:
        print(f"  - {item.title}: {item.url}")

@pytest.mark.asyncio(loop_scope="function")
async def test_idownloadcoupons_live(http_client):
    """Thoroughly check IDownloadCoupons scraper."""
    scraper = IDownloadCouponsScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"IDownloadCoupons found 0 courses. Error: {scraper.error}"
    print(f"\n[IDownloadCoupons] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_coursejoiner_live(http_client):
    """Thoroughly check Course Joiner scraper."""
    scraper = CourseJoinerScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"Course Joiner found 0 courses. Error: {scraper.error}"
    print(f"\n[Course Joiner] Found {len(scraper.data)} courses")

@pytest.mark.asyncio(loop_scope="function")
async def test_enext_live(http_client):
    """Thoroughly check E-next scraper."""
    scraper = ENextScraper(http_client)
    semaphore = asyncio.Semaphore(5)
    await scraper.scrape(semaphore)
    assert len(scraper.data) > 0, f"E-next found 0 courses. Error: {scraper.error}"
    print(f"\n[E-next] Found {len(scraper.data)} courses")
