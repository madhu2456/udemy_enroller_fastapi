import pytest
import asyncio
from unittest.mock import MagicMock
from app.services.scraper import CourseJoinerScraper
from app.services.http_client import AsyncHTTPClient

@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    return client

@pytest.fixture
def scraper(http_client):
    return CourseJoinerScraper(http_client)

@pytest.mark.asyncio
async def test_pagination_and_cap(scraper):
    scraper.MAX_LISTING_PAGES = 60
    scraper.MAX_COURSES = 500

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "coursejoiner.com/category/free-udemy" in url:
            page = 1
            if "page/" in url:
                page = int(url.split("/")[-2])
            
            # Give 60 items per page
            links = [f'<h3><a href="http://detail/{page}/{i}/free-udemy/">Detail</a></h3>' for i in range(60)]
            html = f"<html>{''.join(links)}</html>"
            resp.content = html.encode('utf-8')
        elif url.startswith("http://detail/"):
            parts = url.split("/")
            page = int(parts[-4])
            i = int(parts[-3])
            
            # Simulate failures/duplicates for the first page
            if page == 1:
                if i % 2 == 0:
                    return None
                else:
                    course_slug = "duplicate-course"
            else:
                course_slug = f"course-{page}-{i}"

            html = f'<html><h3>Title</h3><a href="https://www.udemy.com/course/{course_slug}/?couponCode=123">Link</a></html>'
            resp.content = html.encode('utf-8')
            resp.text = html
        else:
            return None
        
        return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 500
    listing_calls = [c for c in scraper.http.get.call_args_list if "coursejoiner.com" in c[0][0]]
    assert len(listing_calls) > 8

@pytest.mark.asyncio
async def test_empty_listing_stops_gracefully(scraper):
    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"<html></html>"
        return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 0

@pytest.mark.asyncio
async def test_encoded_escaped_urls_and_duplicates(scraper):
    scraper.MAX_COURSES = 5
    
    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "coursejoiner.com/category/free-udemy" in url:
            # 5 items, all same detail link, 5 more different but with same udemy url
            links = ['<h3><a href="http://detail/1/free-udemy/">Detail</a></h3>'] * 5
            links += ['<h3><a href="http://detail/2/free-udemy/">Detail</a></h3>'] * 5
            html = f"<html>{''.join(links)}</html>"
            resp.content = html.encode('utf-8')
        elif url == "http://detail/1/free-udemy/":
            # Direct link with anchor
            html = '<html><h3>Title</h3><a href="https://www.udemy.com/course/same-course/?couponCode=123">Link</a></html>'
            resp.content = html.encode('utf-8')
            resp.text = html
        elif url == "http://detail/2/free-udemy/":
            # Encoded link in text, no anchor
            html = '<html><h3>Title</h3>Some text with href="https://www.udemy.com/course/same-course/?couponCode=123"</html>'
            resp.content = html.encode('utf-8')
            resp.text = html
        else:
            resp = None
            
        return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 1
