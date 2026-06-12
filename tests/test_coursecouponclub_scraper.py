import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.scraper import CourseCouponClubScraper
from app.services.http_client import AsyncHTTPClient
from app.services.course import Course

@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    return client

@pytest.fixture
def scraper(http_client):
    return CourseCouponClubScraper(http_client)

@pytest.mark.asyncio
async def test_rest_plus_fallback_reaches_cap(scraper):
    scraper.MAX_COURSES = 500
    scraper.MAX_REST_PAGES = 1
    scraper.MAX_FALLBACK_PAGES = 30

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "wp/v2/posts" in url:
            import json
            posts = []
            for i in range(200):
                posts.append({
                    "title": {"rendered": f"Post {i}"},
                    "content": {"rendered": f'<a href="https://www.udemy.com/course/course-{i}/?couponCode=123">Link</a>'}
                })
            resp.text = json.dumps(posts)
            return resp
        
        if "coursecouponclub.com" in url and ("page" in url or url == "https://coursecouponclub.com/"):
            page = 1
            if "page/" in url:
                page = int(url.split("/")[-2])
            
            html = "<html>"
            for i in range(50):
                html += f'<h3 class="rh-post-title"><a href="https://coursecouponclub.com/post-{page}-{i}/">Detail</a></h3>'
            html += "</html>"
            resp.content = html.encode("utf-8")
            return resp
            
        if "post-" in url:
            parts = url.strip('/').split('/')
            post_id = parts[-1]
            html = f'<html><h1>Title</h1><a href="https://www.udemy.com/course/fallback-{post_id}/?couponCode=456">Link</a></html>'
            resp.content = html.encode("utf-8")
            return resp
            
        return None

    scraper.http.get.side_effect = mock_get
    
    async def mock_resolve(href):
        return href
    scraper._resolve_trk_redirect = mock_resolve
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 500

@pytest.mark.asyncio
async def test_rest_reaches_cap_skips_fallback(scraper):
    scraper.MAX_COURSES = 100
    scraper.MAX_REST_PAGES = 1

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "wp/v2/posts" in url:
            import json
            posts = []
            for i in range(200):
                posts.append({
                    "title": {"rendered": f"Post {i}"},
                    "content": {"rendered": f'<a href="https://www.udemy.com/course/course-{i}/?couponCode=123">Link</a>'}
                })
            resp.text = json.dumps(posts)
            return resp
            
        assert False, "Fallback was called but shouldn't be"

    scraper.http.get.side_effect = mock_get
    
    async def mock_resolve(href):
        return href
    scraper._resolve_trk_redirect = mock_resolve
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 100

@pytest.mark.asyncio
async def test_empty_fallback_stops_gracefully(scraper):
    scraper.MAX_COURSES = 500
    scraper.MAX_REST_PAGES = 1

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "wp/v2/posts" in url:
            import json
            resp.text = json.dumps([])
            return resp
            
        if "coursecouponclub.com" in url:
            resp.content = b"<html></html>"
            return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 0

@pytest.mark.asyncio
async def test_ccc_listicle_bypass(scraper):
    """Test that Course Coupon Club listicles are bypassed and sorted properly."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    post1_html = "<a href='https://www.udemy.com/course/one/'>1</a><a href='https://www.udemy.com/course/two/'>2</a>"
    post2_html = "<a href='https://www.udemy.com/course/three/'>3</a><a href='https://www.udemy.com/course/three/?couponCode=XXX'>3 again</a>"

    mock_resp.text = f'''[
        {{"title": {{"rendered": "Listicle"}}, "content": {{"rendered": "{post1_html}"}}, "date": "2024-02-01T00:00:00"}},
        {{"title": {{"rendered": "Single"}}, "content": {{"rendered": "{post2_html}"}}, "date": "2024-01-01T00:00:00"}}
    ]'''

    with patch.object(scraper, "_resolve_trk_redirect", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = lambda href: href

        with patch("asyncio.gather", new_callable=AsyncMock) as mock_gather:
            mock_gather.return_value = [mock_resp]

            await scraper._scrape_rest_api(asyncio.Semaphore(1), set(), set())

            assert len(scraper.data) == 1
            assert isinstance(scraper.data[0], Course)
            assert scraper.data[0].slug == "three"
