import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.scraper import Scraper

class FakeHTTPClient:
    def __init__(self):
        self.get = AsyncMock()
        self.head = AsyncMock()

class DummyScraper(Scraper):
    @property
    def site_name(self): return "Dummy"
    
    @property
    def code_name(self): return "dummy"

    async def scrape(self, detail_semaphore):
        pass

@pytest.fixture
def fake_http():
    return FakeHTTPClient()

@pytest.fixture
def scraper(fake_http):
    return DummyScraper(fake_http)


@pytest.mark.asyncio
async def test_resolve_trk_redirect_long_link(scraper):
    long_link = "https://trk.udemy.com/?u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Ftest-course%2F%3FcouponCode%3DFREE"
    # It should resolve without calling get or head
    
    result = await scraper._resolve_trk_redirect(long_link)
    
    assert result == "https://www.udemy.com/course/test-course/?couponCode=FREE"
    scraper.http.get.assert_not_called()

@pytest.mark.asyncio
async def test_resolve_trk_redirect_long_link_with_outer_coupon(scraper):
    long_link = "https://trk.udemy.com/?link=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Ftest-course%2F&couponCode=SAVE50"
    
    result = await scraper._resolve_trk_redirect(long_link)
    
    assert result == "https://www.udemy.com/course/test-course/?couponCode=SAVE50"
    scraper.http.get.assert_not_called()

@pytest.mark.asyncio
async def test_resolve_trk_redirect_short_link(scraper):
    short_link = "https://trk.udemy.com/abc12345"
    
    scraper.http.get = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.url = "https://www.udemy.com/course/test-course/?couponCode=123"
    scraper.http.get.return_value = mock_resp
    
    result = await scraper._resolve_trk_redirect(short_link)
    
    assert result == "https://www.udemy.com/course/test-course/?couponCode=123"
    scraper.http.get.assert_called_once_with(
        short_link,
        use_cloudscraper=True,
        follow_redirects=True,
        raise_for_status=False,
        log_failures=False,
        randomize_headers=True,
        timeout=15,
        attempts=2
    )

@pytest.mark.asyncio
async def test_resolve_trk_redirect_short_link_with_outer_coupon(scraper):
    short_link = "https://trk.udemy.com/abc?couponCode=OUTER"
    
    scraper.http.get = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.url = "https://www.udemy.com/course/test-course/"
    scraper.http.get.return_value = mock_resp
    
    result = await scraper._resolve_trk_redirect(short_link)
    
    assert result == "https://www.udemy.com/course/test-course/?couponCode=OUTER"
    scraper.http.get.assert_called_once()

@pytest.mark.asyncio
async def test_resolve_trk_redirect_failure(scraper):
    short_link = "https://trk.udemy.com/fail"
    
    scraper.http.get = AsyncMock(return_value=None)
    result = await scraper._resolve_trk_redirect(short_link)
    assert result is None

@pytest.mark.asyncio
async def test_is_generic_course_title(scraper):
    assert scraper._is_generic_course_title("Get Course Noe") is True
    assert scraper._is_generic_course_title("enroll now") is True
    assert scraper._is_generic_course_title("Download Now") is True
    assert scraper._is_generic_course_title("claim coupon") is True
    assert scraper._is_generic_course_title("view course") is True
    assert scraper._is_generic_course_title("Get This Course") is True
    assert scraper._is_generic_course_title("Get The Course") is True
    assert scraper._is_generic_course_title("Specific Python Course") is False
    assert scraper._is_generic_course_title("Get This Awesome Course Today But Keep It Long") is False

@pytest.mark.asyncio
async def test_append_to_list_generic_title(scraper):
    scraper.append_to_list("Get Course Noe", "https://www.udemy.com/course/python-masterclass/?couponCode=X")
    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Python Masterclass"
    assert scraper.data[0].url == "https://www.udemy.com/course/python-masterclass/?couponCode=X"

@pytest.mark.asyncio
async def test_append_to_list_valid_title(scraper):
    scraper.append_to_list("Advanced React Patterns", "https://www.udemy.com/course/advanced-react/?couponCode=X")
    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Advanced React Patterns"

@pytest.mark.asyncio
async def test_http_client_403_warning_suppression():
    from app.services.http_client import AsyncHTTPClient
    http_client = AsyncHTTPClient()
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.cookies = {}
        
        http_client.client.get = AsyncMock(return_value=mock_resp)
        
        with patch("app.services.http_client.logger") as mock_logger:
            await http_client.get("https://example.com", log_failures=False, raise_for_status=False, attempts=1)
            mock_logger.warning.assert_not_called()
    finally:
        await http_client.close()
