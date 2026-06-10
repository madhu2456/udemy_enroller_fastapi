import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.services.scraper import FreeWebCartScraper
from app.services.http_client import AsyncHTTPClient

@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "mocked"
    mock_resp.headers = {}
    client.get = AsyncMock(return_value=mock_resp)
    return client

@pytest.fixture
def scraper(http_client):
    s = FreeWebCartScraper(http_client)
    s.diagnostics = {
        "listing_fetch_failures": 0,
        "non_200_statuses": 0,
        "empty_bodies": 0,
        "zero_candidate_pages": 0,
        "total_candidates": 0,
        "detail_fetch_failures": 0,
        "no_udemy_link_details": 0,
        "invalid_normalized_urls": 0,
        "duplicates": 0,
        "appended_courses": 0
    }
    return s

@pytest.mark.asyncio
async def test_listing_parser_extracts_ordered_candidates(scraper):
    html = """
        <a class="course-card-link" href="/course/slug-1">
            <h3 class="title-modern">Title 1</h3>
        </a>
        <a class="course-card-link" href="/course/slug-2">
            <img alt="Title 2 - Free Udemy Course" />
        </a>
        <a class="course-card-link" href="/course/slug-3"></a>
        <a href="/other">Ignore</a>
    """
    candidates = scraper._parse_listing_candidates(html)
    assert len(candidates) == 3

    assert candidates[0]["slug"] == "slug-1"
    assert candidates[0]["title"] == "Title 1"
    assert candidates[0]["detail_url"] == "https://freewebcart.com/course/slug-1"

    assert candidates[1]["slug"] == "slug-2"
    assert candidates[1]["title"] == "Title 2"
    assert candidates[1]["detail_url"] == "https://freewebcart.com/course/slug-2"

    assert candidates[2]["slug"] == "slug-3"
    assert candidates[2]["title"] == "Slug 3"
    assert candidates[2]["detail_url"] == "https://freewebcart.com/course/slug-3"

@pytest.mark.asyncio
async def test_detail_extracts_source_url(scraper):
    html = '<html>Some NextJS JSON: "sourceUrl":"https://www.udemy.com/course/test/?couponCode=ABC" </html>'
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Test Title", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert title == "Test Title"
    assert url == "https://www.udemy.com/course/test/?couponCode=ABC"

@pytest.mark.asyncio
async def test_detail_anchor_fallback(scraper):
    html = 'No sourceUrl here. <a href="https://www.udemy.com/course/test/?couponCode=XYZ">Get</a>'
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Anchor Test", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert title == "Anchor Test"
    assert url == "https://www.udemy.com/course/test/?couponCode=XYZ"

@pytest.mark.asyncio
async def test_invalid_detail_is_skipped(scraper):
    scraper.http.get.return_value.text = "Empty body without udemy links"

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Empty", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is None

@pytest.mark.asyncio
async def test_deduplicates_udemy_urls(scraper):
    # Setup candidates
    candidates = [
        {"detail_url": "https://freewebcart.com/course/c1", "title": "Course 1", "slug": "c1"},
        {"detail_url": "https://freewebcart.com/course/c2", "title": "Course 1 Duplicate", "slug": "c2"}
    ]

    # Mock extract to return the SAME udemy url
    scraper._extract_course_from_detail = AsyncMock(side_effect=[
        ("Course 1", "https://www.udemy.com/course/target/"),
        ("Course 1 Duplicate", "https://www.udemy.com/course/target/")
    ])

    await scraper._process_detail_candidates(candidates, asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == "https://www.udemy.com/course/target/"

@pytest.mark.asyncio
async def test_exact_500_cap(scraper):
    # Over 500 candidates
    candidates = [{"detail_url": f"https://freewebcart.com/course/c{i}", "title": f"C{i}", "slug": f"c{i}"} for i in range(600)]

    async def mock_extract(candidate):
        i = candidate["slug"].replace("c", "")
        return (candidate["title"], f"https://www.udemy.com/course/udemy{i}/")

    scraper._extract_course_from_detail = AsyncMock(side_effect=mock_extract)

    await scraper._process_detail_candidates(candidates, asyncio.Semaphore(5))

    assert len(scraper.data) == 500

@pytest.mark.asyncio
async def test_order_preserved_with_slow_first_detail(scraper):
    scraper.MAX_COURSES = 1

    candidates = [
        {"detail_url": "https://freewebcart.com/course/c1", "title": "C1", "slug": "c1"},
        {"detail_url": "https://freewebcart.com/course/c2", "title": "C2", "slug": "c2"}
    ]

    async def mock_extract(candidate):
        if candidate["slug"] == "c1":
            await asyncio.sleep(0.1)
            return ("C1", "https://www.udemy.com/course/udemy1/")
        return ("C2", "https://www.udemy.com/course/udemy2/")

    scraper._extract_course_from_detail = AsyncMock(side_effect=mock_extract)

    await scraper._process_detail_candidates(candidates, asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == "https://www.udemy.com/course/udemy1/"

@pytest.mark.asyncio
async def test_backfills_after_empty_or_duplicate_details(scraper):
    scraper.MAX_COURSES = 2

    candidates = [
        {"detail_url": "https://freewebcart.com/course/c1", "title": "Empty", "slug": "c1"},
        {"detail_url": "https://freewebcart.com/course/c2", "title": "Valid 1", "slug": "c2"},
        {"detail_url": "https://freewebcart.com/course/c3", "title": "Duplicate", "slug": "c3"},
        {"detail_url": "https://freewebcart.com/course/c4", "title": "Valid 2", "slug": "c4"}
    ]

    async def mock_extract(candidate):
        if candidate["slug"] == "c1":
            return None
        elif candidate["slug"] == "c2":
            return ("Valid 1", "https://www.udemy.com/course/v1/")
        elif candidate["slug"] == "c3":
            return ("Duplicate", "https://www.udemy.com/course/v1/")
        elif candidate["slug"] == "c4":
            return ("Valid 2", "https://www.udemy.com/course/v2/")

    scraper._extract_course_from_detail = AsyncMock(side_effect=mock_extract)

    await scraper._process_detail_candidates(candidates, asyncio.Semaphore(5))

    assert len(scraper.data) == 2
    assert scraper.data[0].url == "https://www.udemy.com/course/v1/"
    assert scraper.data[1].url == "https://www.udemy.com/course/v2/"

@pytest.mark.asyncio
async def test_does_not_request_disallowed_paths(scraper):
    # Simulate a full scrape cycle
    html_listing = '<a class="course-card-link" href="/course/c1"></a>'

    async def mock_get(url, *args, **kwargs):
        if "courses" in url:
            mock = MagicMock()
            mock.status_code = 200
            mock.text = html_listing if "page=" not in url else ""
            return mock
        elif "/course/c1" in url:
            mock = MagicMock()
            mock.status_code = 200
            mock.text = '<html>"sourceUrl":"https://www.udemy.com/course/x/"</html>'
            return mock
        return None

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(1))

    for call in scraper.http.get.call_args_list:
        url = call[0][0]
        assert "/api" not in url
        assert "/_next" not in url
        assert "/redirect" not in url

@pytest.mark.asyncio
async def test_full_scrape_collects_all_pages_to_fill_cap(scraper):
    scraper.MAX_COURSES = 2
    scraper.MAX_LISTING_PAGES = 3
    scraper.DETAIL_CHUNK_SIZE = 1

    async def mock_get(url, *args, **kwargs):
        mock = MagicMock()
        mock.status_code = 200
        if "courses" in url:
            if "page=2" in url:
                mock.text = '<a class="course-card-link" href="/course/c2"></a>'
            elif "page=3" in url:
                mock.text = '<a class="course-card-link" href="/course/c3"></a><a class="course-card-link" href="/course/c4"></a>'
            else:
                mock.text = '<a class="course-card-link" href="/course/c1"></a>'
            return mock
        elif "/course/c1" in url:
            mock.text = 'invalid'
            return mock
        elif "/course/c2" in url:
            mock.text = '<html>"sourceUrl":"https://www.udemy.com/course/u2/"</html>'
            return mock
        elif "/course/c3" in url:
            mock.text = '<html>"sourceUrl":"https://www.udemy.com/course/u3/"</html>'
            return mock
        elif "/course/c4" in url:
            mock.text = '<html>"sourceUrl":"https://www.udemy.com/course/u4/"</html>'
            return mock
        return None

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 2
    assert scraper.data[0].url == "https://www.udemy.com/course/u2/"
    assert scraper.data[1].url == "https://www.udemy.com/course/u3/"

@pytest.mark.asyncio
async def test_sourceurl_skips_non_udemy_matches(scraper):
    html = '''<html>
        "sourceUrl":"https://www.google.com/"
        "sourceUrl":"https://www.udemy.com/course/real/"
    </html>'''
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Test Title", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert url == "https://www.udemy.com/course/real/"


@pytest.mark.asyncio
async def test_page_1_fallback_success(scraper):
    scraper.MAX_LISTING_PAGES = 1

    async def mock_get(url, use_cloudscraper=True, **kwargs):
        mock = MagicMock()
        mock.status_code = 200
        if use_cloudscraper:
            mock.text = "empty"
        else:
            mock.text = '<a class="course-card-link" href="/course/c1"></a>'
        return mock

    scraper.http.get = AsyncMock(side_effect=mock_get)
    candidates = await scraper._collect_listing_candidates()

    assert len(candidates) == 1
    assert candidates[0]["slug"] == "c1"

@pytest.mark.asyncio
async def test_page_2_empty_ends_pagination_without_fallback(scraper):
    scraper.MAX_LISTING_PAGES = 3

    async def mock_get(url, use_cloudscraper=True, **kwargs):
        mock = MagicMock()
        mock.status_code = 200
        if "page=2" in url:
            mock.text = "empty body for page 2"
        else:
            mock.text = '<a class="course-card-link" href="/course/c1"></a>'
        return mock

    scraper.http.get = AsyncMock(side_effect=mock_get)
    candidates = await scraper._collect_listing_candidates()

    assert len(candidates) == 1
    assert scraper.progress == 2
    for call in scraper.http.get.call_args_list:
        kwargs = call[1]
        assert kwargs.get("use_cloudscraper") is True

@pytest.mark.asyncio
async def test_diagnostics_counters(scraper):
    scraper.MAX_LISTING_PAGES = 1

    scraper.http.get = AsyncMock(return_value=MagicMock(status_code=500))
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.diagnostics["non_200_statuses"] == 1

    scraper.http.get = AsyncMock(return_value=MagicMock(status_code=200, text="   "))
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.diagnostics["empty_bodies"] == 1

    scraper.http.get = AsyncMock(return_value=MagicMock(status_code=200, text="<html>No cards here</html>"))
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.diagnostics["zero_candidate_pages"] == 1

    async def mock_get(url, **kwargs):
        if "courses" in url:
            return MagicMock(status_code=200, text='<a class="course-card-link" href="/course/c1"></a>')
        return MagicMock(status_code=500)
    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.diagnostics["total_candidates"] == 1
    assert scraper.diagnostics["detail_fetch_failures"] == 1

@pytest.mark.asyncio
async def test_detail_extraction_raw_url_fallback(scraper):
    html = 'Check out the course here: https://www.udemy.com/course/raw-course-name/'
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Test Title", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert url == "https://www.udemy.com/course/raw-course-name/"

@pytest.mark.asyncio
async def test_detail_extraction_escaped_sourceurl(scraper):
    html = '<html>"sourceUrl":"https:\\/\\/www.udemy.com\\/course\\/escaped-course\\/?couponCode=123"</html>'
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Test Title", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert url == "https://www.udemy.com/course/escaped-course/?couponCode=123"

@pytest.mark.asyncio
async def test_detail_skips_non_udemy_sourceurl(scraper):
    html = '''
    "sourceUrl":"https://example.com/not-udemy"
    "sourceUrl":"https://www.udemy.com/course/valid-course/"
    '''
    scraper.http.get.return_value.text = html

    candidate = {"detail_url": "https://freewebcart.com/course/test", "title": "Test Title", "slug": "test"}
    result = await scraper._extract_course_from_detail(candidate)

    assert result is not None
    title, url = result
    assert url == "https://www.udemy.com/course/valid-course/"

@pytest.mark.asyncio
async def test_full_scrape_invalid_details_logs_diagnostics(scraper):
    scraper.MAX_LISTING_PAGES = 1

    async def mock_get(url, **kwargs):
        if "courses" in url:
            return MagicMock(status_code=200, text='<a class="course-card-link" href="/course/c1"></a>')
        return MagicMock(status_code=200, text='No udemy links here')

    scraper.http.get = AsyncMock(side_effect=mock_get)

    from unittest.mock import patch
    with patch("app.services.scraper.logger.warning") as mock_warning:
        await scraper.scrape(asyncio.Semaphore(1))

        assert len(scraper.data) == 0
        assert scraper.diagnostics["total_candidates"] == 1
        assert scraper.diagnostics["no_udemy_link_details"] == 1

        # Check if the warning was logged with correct text
        warning_calls = [call[0][0] for call in mock_warning.call_args_list]
        found_warning = any("FreeWebCart scrape ended with 0 courses" in call_text for call_text in warning_calls)
        assert found_warning
        found_diag = any("'no_udemy_link_details': 1" in call_text for call_text in warning_calls)
        assert found_diag
