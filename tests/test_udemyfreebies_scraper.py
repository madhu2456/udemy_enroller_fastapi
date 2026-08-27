import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import UdemyFreebiesScraper


@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html></html>"
    mock_resp.content = b"<html></html>"
    mock_resp.headers = {}
    client.get = AsyncMock(return_value=mock_resp)
    client.safe_json = AsyncMock()
    return client


@pytest.fixture
def scraper(http_client):
    return UdemyFreebiesScraper(http_client)


def test_class_attributes():
    assert UdemyFreebiesScraper.MAX_COURSES == 500
    assert UdemyFreebiesScraper.COURSES_PER_PAGE == 12
    assert UdemyFreebiesScraper.MAX_LISTING_PAGES == 85
    assert UdemyFreebiesScraper.LISTING_CONCURRENCY == 6
    assert (
        UdemyFreebiesScraper.LISTING_ENDPOINT
        == "https://www.udemyfreebies.com/free-udemy-courses"
    )
    assert isinstance(UdemyFreebiesScraper.UDEMY_RESERVED_SLUGS, frozenset)
    expected_slugs = {
        "course",
        "courses",
        "cart",
        "join",
        "user",
        "topic",
        "topics",
        "certificate",
        "support",
        "terms",
        "privacy",
        "affiliate",
        "instructor",
        "teaching",
        "mobile",
        "gift",
        "featured",
        "api",
        "organization",
        "home",
        "search",
        "explore",
        "collection",
        "category",
    }
    assert expected_slugs.issubset(UdemyFreebiesScraper.UDEMY_RESERVED_SLUGS)


@pytest.mark.asyncio
async def test_html_listing_extraction(scraper):
    html_content = """
    <html>
        <div class="coupon-name">
            <a href="https://www.udemyfreebies.com/free-udemy-course/python-course-2026">Complete Python Bootcamp</a>
        </div>
        <div class="coupon-name">
            <a href="/free-udemy-course/react-mastery">React Mastery</a>
        </div>
        <div class="coupon-name">
            <a href="/other-path/invalid">Invalid Path</a>
        </div>
        <div class="coupon-name">
            <a href="/free-udemy-course/">Empty Slug</a>
        </div>
        <div class="coupon-name">
            <a href="/free-udemy-course/ab">AB</a>
        </div>
        <div class="coupon-name">
            <span>No Link</span>
        </div>
    </html>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        url_str = str(url)
        if "/out/" in url_str:
            slug = url_str.split("/out/")[-1]
            resp.status_code = 302
            resp.headers = {
                "Location": f"https://www.udemy.com/course/{slug}/?couponCode=FREE100"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    # Only "python-course-2026" and "react-mastery" should be extracted
    assert len(scraper.data) == 2
    titles = [c.title for c in scraper.data]
    assert "Complete Python Bootcamp" in titles
    assert "React Mastery" in titles


@pytest.mark.asyncio
async def test_out_redirect_resolution_success(scraper):
    html_content = """
    <div class="coupon-name">
        <a href="/free-udemy-course/golang-deep-dive">Golang Deep Dive</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/golang-deep-dive" in str(url):
            resp.status_code = 302
            resp.headers = {
                "location": "https://www.udemy.com/course/golang-deep-dive/?couponCode=GOFREE"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Golang Deep Dive"
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/golang-deep-dive/?couponCode=GOFREE"
    )


@pytest.mark.asyncio
async def test_out_redirect_reserved_slug_rejected(scraper):
    html_content = """
    <div class="coupon-name">
        <a href="/free-udemy-course/cart">Cart Promo</a>
    </div>
    <div class="coupon-name">
        <a href="/free-udemy-course/terms">Terms Promo</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/cart" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/cart/?couponCode=FREE"
            }
            return resp
        if "/out/terms" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/terms/?couponCode=FREE"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    # Reserved slugs must be rejected
    assert len(scraper.data) == 0


@pytest.mark.asyncio
async def test_out_redirect_single_segment_normalized(scraper):
    html_content = """
    <div class="coupon-name">
        <a href="/free-udemy-course/machine-learning-zero-to-hero">ML Zero to Hero</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/machine-learning-zero-to-hero" in str(url):
            resp.status_code = 302
            resp.headers = {
                "location": "https://www.udemy.com/machine-learning-zero-to-hero/?couponCode=MLFREE2026"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "ML Zero to Hero"
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/machine-learning-zero-to-hero/?couponCode=MLFREE2026"
    )


@pytest.mark.asyncio
async def test_out_redirect_trk_udemy_resolved(scraper):
    html_content = """
    <div class="coupon-name">
        <a href="/free-udemy-course/docker-k8s">Docker & Kubernetes</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/docker-k8s" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://trk.udemy.com/trk-docker?couponCode=FREE"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1
    scraper._resolve_trk_redirect = AsyncMock(
        return_value="https://www.udemy.com/course/docker-k8s/?couponCode=FREE"
    )

    await scraper.scrape(asyncio.Semaphore(5))

    scraper._resolve_trk_redirect.assert_awaited_once_with(
        "https://trk.udemy.com/trk-docker?couponCode=FREE"
    )
    assert len(scraper.data) == 1
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/docker-k8s/?couponCode=FREE"
    )


@pytest.mark.asyncio
async def test_out_redirect_hostile_domain_rejected(scraper):
    html_content = """
    <div class="coupon-name">
        <a href="/free-udemy-course/phishing">Phishing Attack</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/phishing" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://evil.com/course/phishing/?couponCode=EVIL"
            }
            return resp
        resp.status_code = 200
        resp.content = html_content
        resp.text = html_content.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 0


@pytest.mark.asyncio
async def test_deduplication_and_max_courses_cap(scraper):
    html_page1 = """
    <div class="coupon-name">
        <a href="/free-udemy-course/course-1">Course 1</a>
    </div>
    <div class="coupon-name">
        <a href="/free-udemy-course/course-2">Course 2</a>
    </div>
    <div class="coupon-name">
        <a href="/free-udemy-course/course-1">Course 1 Duplicate</a>
    </div>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        if "/out/course-1" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/course-1/?couponCode=C1"
            }
            return resp
        if "/out/course-2" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/course-2/?couponCode=C2"
            }
            return resp
        resp.status_code = 200
        resp.content = html_page1
        resp.text = html_page1.decode()
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_LISTING_PAGES = 1
    scraper.MAX_COURSES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
