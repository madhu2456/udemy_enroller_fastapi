import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.services.scraper import FreeCourseSitesScraper
from app.services.http_client import AsyncHTTPClient
from app.services.course import Course

@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "mocked"
    mock_resp.headers = {}
    client.get = AsyncMock(return_value=mock_resp)
    client.safe_json = AsyncMock()
    return client

@pytest.fixture
def scraper(http_client):
    return FreeCourseSitesScraper(http_client)

@pytest.mark.asyncio
async def test_category_id_resolution(scraper):
    # Success case
    scraper.http.safe_json.return_value = [{"id": 9999}]
    cat_id = await scraper._get_category_id("test-slug", 123)
    assert cat_id == 9999

    # Fallback case (empty)
    scraper.http.safe_json.return_value = []
    cat_id = await scraper._get_category_id("test-slug", 123)
    assert cat_id == 123

    # Fallback case (error/none)
    scraper.http.safe_json.return_value = None
    cat_id = await scraper._get_category_id("test-slug", 123)
    assert cat_id == 123

@pytest.mark.asyncio
async def test_rest_extraction_and_generic_titles(scraper):
    html = """
        <a class="mks_button" href="https://www.udemy.com/course/test-course/?couponCode=123">ENROLL NOW</a>
        <a href="https://www.udemy.com/course/test-course-2/">Get Course Now</a>
        <a href="https://www.udemy.com/course/test-course-3/">Specific Python Course</a>
        <a href="https://freecoursesites.com/internal-link/">Internal Link</a>
    """
    seen_urls = set()
    courses = await scraper._extract_courses_from_html(html, "WP Post Title", seen_urls)

    # Internal link ignored. ENROLL NOW and Get Course Now replaced by fallback title.
    assert len(courses) == 3
    assert courses[0] == ("WP Post Title", "https://www.udemy.com/course/test-course/?couponCode=123")
    assert courses[1] == ("WP Post Title", "https://www.udemy.com/course/test-course-2/")
    assert courses[2] == ("Specific Python Course", "https://www.udemy.com/course/test-course-3/")

@pytest.mark.asyncio
async def test_trk_link_unwrapping(scraper):
    # Long trk link
    html_long = '<a href="https://trk.udemy.com/?u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Fpython%2F%3FcouponCode%3D123">Get Deal</a>'

    # Short trk link (needs resolve)
    html_short = '<a href="https://trk.udemy.com/short123">Get Deal</a>'

    mock_resp = MagicMock()
    mock_resp.url = "https://www.udemy.com/course/java/"
    scraper.http.get = AsyncMock(return_value=mock_resp)

    seen_urls = set()
    courses_long = await scraper._extract_courses_from_html(html_long, "Title 1", seen_urls)
    assert len(courses_long) == 1
    assert courses_long[0][1] == "https://www.udemy.com/course/python/?couponCode=123"
    scraper.http.get.assert_not_called()

    seen_urls = set()
    courses_short = await scraper._extract_courses_from_html(html_short, "Title 2", seen_urls)
    assert len(courses_short) == 1
    assert courses_short[0][1] == "https://www.udemy.com/course/java/"
    scraper.http.get.assert_called_once()

@pytest.mark.asyncio
async def test_rest_pagination_and_deduplication(scraper):
    post1 = {
        "title": {"rendered": "Post 1"},
        "content": {"rendered": '<a href="https://www.udemy.com/course/course1/">Link</a>'}
    }
    post2 = {
        "title": {"rendered": "Post 2"},
        "content": {"rendered": '<a href="https://www.udemy.com/course/course2/">Link</a>'}
    }
    post3_dup = {
        "title": {"rendered": "Post 3"},
        "content": {"rendered": '<a href="http://udemy.com/course/course1/?otherparam=1">Link</a>'}
    }

    scraper._get_category_id = AsyncMock(return_value=123)

    def side_effect_json(*args, **kwargs):
        call_count = scraper.http.safe_json.call_count
        if call_count == 1:
            return [post1, post2, post3_dup] + [{"title": {"rendered": f"Post {i}"}, "content": {"rendered": f'<a href="https://www.udemy.com/course/c{i}/">Link</a>'}} for i in range(3, 300)]
        elif call_count == 2:
            return [{"title": {"rendered": f"Post {i}"}, "content": {"rendered": f'<a href="https://www.udemy.com/course/c{i}/">Link</a>'}} for i in range(300, 600)]
        return []

    scraper.http.safe_json.side_effect = side_effect_json

    seen_urls = set()
    await scraper._scrape_rest_api(seen_urls)

    assert len(scraper.data) == 500
    assert scraper.data[0].url == "https://www.udemy.com/course/course1/"
    assert scraper.data[1].url == "https://www.udemy.com/course/course2/"
    assert scraper.data[2].url == "https://www.udemy.com/course/c3/"

    calls = scraper.http.get.call_args_list
    assert len(calls) == 2
    assert "orderby=date&order=desc" in calls[0][0][0]

@pytest.mark.asyncio
async def test_html_fallback_trigger(scraper):
    scraper._scrape_rest_api = AsyncMock()
    scraper._scrape_html_fallback = AsyncMock()

    scraper.data = []
    await scraper.scrape(asyncio.Semaphore(1))
    scraper._scrape_html_fallback.assert_called_once()

    scraper._scrape_html_fallback.reset_mock()
    scraper.data = [Course(title="mock", url=f"http://test.com/{i}", site="mock") for i in range(10)]
    await scraper.scrape(asyncio.Semaphore(1))
    scraper._scrape_html_fallback.assert_called_once()

    scraper._scrape_html_fallback.reset_mock()
    scraper.data = [Course(title="mock", url=f"http://test.com/{i}", site="mock") for i in range(500)]
    await scraper.scrape(asyncio.Semaphore(1))
    scraper._scrape_html_fallback.assert_not_called()

@pytest.mark.asyncio
async def test_scraper_cap(scraper):
    scraper.MAX_COURSES = 500
    scraper.data = [Course(title="mock", url=f"http://udemy.com/rest{i}", site="mock") for i in range(499)]

    scraper.http.get = AsyncMock()
    archive_html = '<h2><a href="https://freecoursesites.com/c1/">Post 1</a></h2>'
    archive_resp = MagicMock()
    archive_resp.status_code = 200
    archive_resp.text = archive_html

    detail1_resp = MagicMock()
    detail1_resp.status_code = 200
    detail1_resp.text = '<a href="https://www.udemy.com/course/new1/">L</a><a href="https://www.udemy.com/course/new2/">L</a>'

    async def mock_get(url, *args, **kwargs):
        if url == "https://freecoursesites.com/category/udemy-free-courses/":
            return archive_resp
        elif url == "https://freecoursesites.com/c1/":
            return detail1_resp
        return None

    scraper.http.get.side_effect = mock_get

    seen_urls = set()
    await scraper._scrape_html_fallback(asyncio.Semaphore(1), seen_urls)

    assert len(scraper.data) == 500
    assert scraper.data[-1].url == "https://www.udemy.com/course/new1/"

@pytest.mark.asyncio
async def test_html_fallback_ordering(scraper):
    scraper.MAX_COURSES = 1
    scraper._scrape_rest_api = AsyncMock(return_value=0)

    archive_html = '''
        <h2><a href="https://freecoursesites.com/c1/">Post 1</a></h2>
        <h2><a href="https://freecoursesites.com/c2/">Post 2</a></h2>
    '''
    archive_resp = MagicMock()
    archive_resp.status_code = 200
    archive_resp.text = archive_html

    detail1_resp = MagicMock()
    detail1_resp.status_code = 200
    detail1_resp.text = '<a href="https://www.udemy.com/course/course1/">Link</a>'

    detail2_resp = MagicMock()
    detail2_resp.status_code = 200
    detail2_resp.text = '<a href="https://www.udemy.com/course/course2/">Link</a>'

    async def mock_get(url, *args, **kwargs):
        if url == "https://freecoursesites.com/category/udemy-free-courses/":
            return archive_resp
        elif url == "https://freecoursesites.com/c1/":
            await asyncio.sleep(0.1) # slow, but should be processed first
            return detail1_resp
        elif url == "https://freecoursesites.com/c2/":
            return detail2_resp
        return None

    scraper.http.get.side_effect = mock_get

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == "https://www.udemy.com/course/course1/"

@pytest.mark.asyncio
async def test_multiple_categories_exhaustion(scraper):
    scraper._get_category_id = AsyncMock(side_effect=[78256, 137426])

    async def mock_get(url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = url
        mock_resp.headers = {"X-WP-TotalPages": "1"} # 1 page per category
        return mock_resp

    scraper.http.get.side_effect = mock_get

    async def side_effect_json(resp, *args, **kwargs):
        if "categories=78256" in resp.url:
            # 31 items from primary category
            return [{"title": {"rendered": f"Post A{i}"}, "content": {"rendered": f'<a href="https://www.udemy.com/course/a{i}/">Link</a>'}} for i in range(31)]
        elif "categories=137426" in resp.url:
            # 9 unique items, plus 1 cross-category duplicate
            return [{"title": {"rendered": f"Post B{i}"}, "content": {"rendered": f'<a href="https://www.udemy.com/course/b{i}/">Link</a>'}} for i in range(9)] + \
                   [{"title": {"rendered": "Post A0 Duplicate"}, "content": {"rendered": '<a href="https://www.udemy.com/course/a0/">Link</a>'}}]
        return []

    scraper.http.safe_json.side_effect = side_effect_json

    seen_urls = set()
    await scraper._scrape_rest_api(seen_urls)

    # 31 from first + 9 from second (1 skipped)
    assert len(scraper.data) == 40
    assert scraper.data[0].url == "https://www.udemy.com/course/a0/"
    assert scraper.data[-1].url == "https://www.udemy.com/course/b8/"

    # Verify both categories were fetched
    calls = scraper.http.get.call_args_list
    assert any("categories=78256" in c[0][0] for c in calls)
    assert any("categories=137426" in c[0][0] for c in calls)
