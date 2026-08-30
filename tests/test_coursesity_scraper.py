"""Comprehensive unit tests for CoursesityScraper."""

import asyncio
import json
import urllib.parse
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import CoursesityScraper

COURSE_URL_1 = "https://www.udemy.com/course/python-zero-to-hero/?couponCode=FREE100"
COURSE_URL_2 = "https://www.udemy.com/course/machine-learning-basics/"
COURSE_URL_3 = "https://www.udemy.com/course/docker-kubernetes-guide/"
OPAQUE_TRK_URL = "https://trk.udemy.com/4aM7DG"
EMBEDDED_TRK_URL = (
    "https://trk.udemy.com/t/t?a=123&u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Freact-mastery%2F"
)


def _resp(text="", status=200, headers=None, url=""):
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.content = text.encode("utf-8") if isinstance(text, str) else text
    mock.headers = headers or {}
    mock.url = url
    return mock


@pytest.fixture
def scraper():
    return CoursesityScraper(MagicMock(spec=AsyncHTTPClient))


def test_transfer_state_html_entities_unescape():
    """Test 1: Angular Universal TransferState HTML entity sanitization and decoding."""
    raw_entities = (
        "{&q;title&q;: &q;Python &a; AI &s; C++ &l;Beginner&g;&b;&q;, "
        "&q;url&q;: &q;https://www.udemy.com/course/python-ai/&q;}"
    )
    sanitized = CoursesityScraper._sanitize_angular_entities(raw_entities)
    assert "&q;" not in sanitized
    assert "&a;" not in sanitized
    assert "&s;" not in sanitized
    assert "&l;" not in sanitized
    assert "&g;" not in sanitized
    assert "&b;" not in sanitized
    assert '"title": "Python & AI \' C++ <Beginner>\\"' in sanitized

    # Standard HTML entities like &quot; &#39; &amp; &lt; &gt;
    standard_entities = '&quot;test&#39; &amp; &lt;tag&gt;'
    sanitized_std = CoursesityScraper._sanitize_angular_entities(standard_entities)
    assert sanitized_std == '"test\' & <tag>'

    # Embedded in script tag
    html_doc = f"""
    <html>
      <head>
        <script id="app-root-state" type="application/json">
          {{&q;COURSE_LIST&q;:{{&q;courseData&q;:[{{&q;title&q;:&q;Master Python &amp; SQL&q;,&q;course_url&q;:&q;{COURSE_URL_1}&q;}}],&q;totalCount&q;:100}}}}
        </script>
      </head>
      <body><div>Content</div></body>
    </html>
    """
    scraper_instance = CoursesityScraper(MagicMock(spec=AsyncHTTPClient))
    courses, total = scraper_instance._parse_transfer_state(html_doc)
    assert total == 100
    assert len(courses) == 1
    assert "Master Python & SQL" in courses[0]["title"]
    assert courses[0]["course_url"] == COURSE_URL_1


@pytest.mark.asyncio
async def test_transfer_state_malformed_json_fallback_to_dom(scraper):
    """Test 2: Malformed TransferState JSON triggers safe fallback to DOM detail scraping."""
    # Malformed JSON in transfer state
    broken_html = """
    <html>
      <head>
        <script id="serverApp-state" type="application/json">
          { broken json: not valid ...
        </script>
      </head>
      <body>
        <a href="/course-detail/python-crash-course">Python Crash Course</a>
      </body>
    </html>
    """
    courses, total = scraper._parse_transfer_state(broken_html)
    assert courses == []
    assert total is None

    detail_html = f"""
    <html>
      <head>
        <meta property="og:title" content="Python Crash Course - Free Online Course">
      </head>
      <body>
        <script>
          var link = "{COURSE_URL_1}";
        </script>
      </body>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/course-detail/python-crash-course" in url:
            return _resp(detail_html)
        if "coursesity.com/provider/free/udemy-courses" in url:
            return _resp(broken_html)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(2))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL_1
    assert scraper.data[0].title == "Python Crash Course"


def test_recursive_state_key_search_variations():
    """Test 3: Recursive search across different key variations in TransferState."""
    # Variation A: COURSE_LIST + courseData + totalCount
    data_a = {
        "COURSE_LIST": {
            "courseData": [
                {"title": "Course A", "course_url": COURSE_URL_1},
                {"title": "Course A2", "course_url": COURSE_URL_2},
            ],
            "totalCount": 3075,
        }
    }
    courses_a, total_a = CoursesityScraper._find_courses_and_count_in_state(data_a)
    assert len(courses_a) == 2
    assert total_a == 3075

    # Variation B: serverApp-state + items + totalCourses (string)
    data_b = {
        "serverApp-state": {
            "items": [
                {"heading": "Course B", "url": COURSE_URL_2},
            ],
            "totalCourses": "150",
        }
    }
    courses_b, total_b = CoursesityScraper._find_courses_and_count_in_state(data_b)
    assert len(courses_b) == 1
    assert total_b == 150

    # Variation C: courses + total_count
    data_c = {
        "courses": [
            {"name": "Course C", "link": COURSE_URL_3},
        ],
        "total_count": 45,
    }
    courses_c, total_c = CoursesityScraper._find_courses_and_count_in_state(data_c)
    assert len(courses_c) == 1
    assert total_c == 45

    # Variation D: Deeply nested data with slug and count
    data_d = {
        "root": {
            "sub": {
                "results": [
                    {"title": "Course D", "slug": "course-d", "udemy_url": COURSE_URL_1}
                ],
                "count": 12,
            }
        }
    }
    courses_d, total_d = CoursesityScraper._find_courses_and_count_in_state(data_d)
    assert len(courses_d) == 1
    assert total_d == 12

    # Variation E: Direct list
    data_e = [{"title": "Course E", "url": COURSE_URL_1}]
    courses_e, total_e = CoursesityScraper._find_courses_and_count_in_state(data_e)
    assert len(courses_e) == 1
    assert total_e is None


@pytest.mark.asyncio
async def test_safe_pagination_and_bounding(scraper):
    """Test 4: Safe pagination calculation, totalCount parsing, and page limits."""
    # Test totalCount = 3075, per_page = 15 -> 205 pages
    state_html = f"""
    <script id="coursesity-state">
      {{"COURSE_LIST": {{"courseData": [{{"title": "P1 Course", "course_url": "{COURSE_URL_1}"}}], "totalCount": 3075}}}}
    </script>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "page=1" in url:
            return _resp(state_html)
        return _resp('<script id="coursesity-state">{"COURSE_LIST": {"courseData": []}}</script>')

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_COURSES = 500
    await scraper.scrape(asyncio.Semaphore(2))

    assert scraper.length == 205
    assert len(scraper.data) == 1

    # Test MAX_COURSES cap bounding max_pages
    scraper_capped = CoursesityScraper(MagicMock(spec=AsyncHTTPClient))
    scraper_capped.MAX_COURSES = 4
    scraper_capped.http.get = AsyncMock(side_effect=mock_get)
    await scraper_capped.scrape(asyncio.Semaphore(2))
    assert len(scraper_capped.data) == 1


def test_url_resolution_tier1_static_query_unwrap_no_network():
    """Test 5: Tier 1 static query unwrap without making network requests."""
    # Direct Udemy URL
    direct = COURSE_URL_1
    assert CoursesityScraper._unwrap_udemy_url(direct) == Course.normalize_link(direct)

    # trk.udemy.com with u= param
    trk_with_u = f"https://trk.udemy.com/t/t?a=123&u={urllib.parse.quote(COURSE_URL_1)}"
    unwrapped = CoursesityScraper._unwrap_udemy_url(trk_with_u)
    assert unwrapped == Course.normalize_link(COURSE_URL_1)

    # Linksynergy affiliate redirect with murl= param
    murl = f"https://click.linksynergy.com/deeplink?id=xyz&murl={urllib.parse.quote(COURSE_URL_2)}"
    assert CoursesityScraper._unwrap_udemy_url(murl) == Course.normalize_link(COURSE_URL_2)

    # Double-encoded URL
    double_encoded = f"https://trk.udemy.com/t/t?u={urllib.parse.quote(urllib.parse.quote(COURSE_URL_3))}"
    assert CoursesityScraper._unwrap_udemy_url(double_encoded) == Course.normalize_link(COURSE_URL_3)

    # Destination / target / dest params
    dest_url = f"https://redirect.example.com/?dest={urllib.parse.quote(COURSE_URL_1)}"
    assert CoursesityScraper._unwrap_udemy_url(dest_url) == Course.normalize_link(COURSE_URL_1)

    # Non-Udemy URL returns None
    assert CoursesityScraper._unwrap_udemy_url("https://example.com/not-udemy") is None

    # Opaque trk URL without query parameter returns None (triggers Tier 2)
    assert CoursesityScraper._unwrap_udemy_url(OPAQUE_TRK_URL) is None
    assert CoursesityScraper._unwrap_udemy_url("") is None


@pytest.mark.asyncio
async def test_url_resolution_tier2_trk_network_fallback(scraper):
    """Test 6: Tier 2 network resolution fallback for opaque trk.udemy.com URLs."""
    state_html = f"""
    <script id="app-root-state">
      {{"courseData": [{{"title": "Opaque Trk Course", "course_url": "{OPAQUE_TRK_URL}"}}], "totalCount": 1}}
    </script>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "page=1" in url:
            return _resp(state_html)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper._resolve_trk_redirect = AsyncMock(return_value=COURSE_URL_1)

    await scraper.scrape(asyncio.Semaphore(2))

    scraper._resolve_trk_redirect.assert_called_once_with(OPAQUE_TRK_URL)
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL_1


@pytest.mark.asyncio
async def test_listing_concurrency_semaphore_and_circuit_breaker(scraper):
    """Test 7: Listing concurrency semaphore control and circuit breaker tripping."""
    # Part A: Concurrency tracking
    max_active = 0
    curr_active = 0
    lock = asyncio.Lock()

    state_p1 = f"""
    <script id="app-root-state">
      {{"COURSE_LIST": {{"courseData": [{{"title": "P1", "course_url": "{COURSE_URL_1}"}}], "totalCount": 150}}}}
    </script>
    """
    other_page = f"""
    <script id="app-root-state">
      {{"COURSE_LIST": {{"courseData": [{{"title": "PX", "course_url": "{COURSE_URL_2}"}}]}}}}
    </script>
    """

    async def mock_concurrent_get(url, *args, **kwargs):
        nonlocal max_active, curr_active
        if "robots.txt" in url:
            return _resp("", status=404)
        async with lock:
            curr_active += 1
            if curr_active > max_active:
                max_active = curr_active
        await asyncio.sleep(0.01)
        async with lock:
            curr_active -= 1
        if "page=1" in url:
            return _resp(state_p1)
        return _resp(other_page)

    scraper.http.get = AsyncMock(side_effect=mock_concurrent_get)
    scraper.LISTING_CONCURRENCY = 3
    scraper.MAX_COURSES = 500
    await scraper.scrape(asyncio.Semaphore(2))

    assert max_active <= 3
    assert len(scraper.data) >= 1

    # Part B: Circuit breaker tripping on consecutive failures during pagination
    scraper_cb = CoursesityScraper(MagicMock(spec=AsyncHTTPClient))
    scraper_cb.max_consecutive_failures = 3

    async def mock_fail_pages(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "page=1" in url:
            return _resp(state_p1)
        return _resp("Server Error", status=500)

    scraper_cb.http.get = AsyncMock(side_effect=mock_fail_pages)
    await scraper_cb.scrape(asyncio.Semaphore(2))

    assert scraper_cb.circuit_open is True
    assert scraper_cb.consecutive_failures >= 3


@pytest.mark.asyncio
async def test_tiered_fallback_dom_detail_when_ssr_absent(scraper):
    """Test 8: Complete DOM-based fallback when TransferState SSR script is absent."""
    listing_html = """
    <html>
      <head><title>Coursesity Free Udemy Courses</title></head>
      <body>
        <div class="course-list">
          <a href="/course-detail/python-masterclass">Python Masterclass</a>
          <a href="/course-detail/docker-kubernetes">Docker &amp; K8s</a>
        </div>
      </body>
    </html>
    """

    detail_1 = f"""
    <html>
      <head><meta property="og:title" content="Python Masterclass - Free Online Course"></head>
      <body>
        <a href="{COURSE_URL_1}">Go to Course</a>
      </body>
    </html>
    """

    detail_2 = f"""
    <html>
      <head><title>Docker &amp; Kubernetes | Free Online Course</title></head>
      <body>
        <script>
          const enroll = "{COURSE_URL_3}";
        </script>
      </body>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/course-detail/python-masterclass" in url:
            return _resp(detail_1)
        if "/course-detail/docker-kubernetes" in url:
            return _resp(detail_2)
        if "coursesity.com/provider/free/udemy-courses" in url:
            return _resp(listing_html)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.MAX_COURSES = 500
    await scraper.scrape(asyncio.Semaphore(2))

    assert len(scraper.data) == 2
    titles = [c.title for c in scraper.data]
    urls = [c.url for c in scraper.data]
    assert "Python Masterclass" in titles
    assert "Docker & Kubernetes" in titles
    assert COURSE_URL_1 in urls
    assert COURSE_URL_3 in urls


def test_title_cleaning_and_deduplication(scraper):
    """Test 9: Title cleaning, entity unescaping, slug recovery, and course deduplication."""
    # Suffix removal
    assert (
        scraper._clean_title("Python Bootcamp 2024 - Free Online Course | Coursesity")
        == "Python Bootcamp 2024"
    )
    assert (
        scraper._clean_title("Machine Learning A-Z | Free Online Course")
        == "Machine Learning A-Z"
    )

    # HTML entity unescape
    assert (
        scraper._clean_title("Web Development &amp; Design &lt;Master&gt;")
        == "Web Development & Design <Master>"
    )

    # Generic CTA title recovery from fallback slug
    assert scraper._clean_title("Enroll Now", fallback_slug="python-for-beginners") == "Python For Beginners"
    assert scraper._clean_title("Get Course", fallback_slug="/course-detail/deep-learning-intro") == "Deep Learning Intro"
    assert scraper._clean_title("", fallback_slug="modern-cpp-programming") == "Modern Cpp Programming"

    # Deduplication in append_to_list
    scraper.append_to_list("Course A", COURSE_URL_1)
    scraper.append_to_list("Course A Duplicate", COURSE_URL_1)
    assert len(scraper.data) == 1


@pytest.mark.asyncio
async def test_scraper_contract_and_max_courses_cap(scraper):
    """Test 10: Standard scraper contract properties and MAX_COURSES cap enforcement."""
    # Contract attributes
    assert scraper.site_name == "Coursesity"
    assert scraper.code_name == "cs"
    assert scraper.MAX_COURSES == 500
    assert scraper.COURSES_PER_PAGE == 15
    assert scraper.MAX_LISTING_PAGES == 205
    assert scraper.LISTING_CONCURRENCY == 2
    assert scraper.LISTING_ENDPOINT == "https://coursesity.com/provider/free/udemy-courses"

    # Cap enforcement
    courses_payload = [
        {"title": f"Course {i}", "course_url": f"https://www.udemy.com/course/course-{i}/"}
        for i in range(10)
    ]
    state_html = f"""
    <script id="app-root-state">
      {{"COURSE_LIST": {{"courseData": {json.dumps(courses_payload)}, "totalCount": 10}}}}
    </script>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "page=1" in url:
            return _resp(state_html)
        return _resp("")

    scraper.MAX_COURSES = 4
    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(2))

    assert len(scraper.data) == 4
