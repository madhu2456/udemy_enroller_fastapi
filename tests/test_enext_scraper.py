import pytest
import asyncio
from unittest.mock import MagicMock
from app.services.scraper import ENextScraper
from app.services.http_client import AsyncHTTPClient

@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    return client

@pytest.fixture
def scraper(http_client):
    return ENextScraper(http_client)

@pytest.mark.asyncio
async def test_pagination_continues_on_duplicates_and_failures_to_hit_cap(scraper):
    scraper.MAX_LISTING_PAGES = 50
    scraper.MAX_COURSES = 500

    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "jobs.e-next.in/course/udemy/" in url:
            page = int(url.split("/")[-1])
            # Give 60 items per page
            links = [f'<a class="btn btn-secondary btn-sm btn-block" href="http://detail/{page}/{i}">Detail</a>' for i in range(60)]
            html = f"<html>{''.join(links)}</html>"
            resp.content = html.encode('utf-8')
        elif url.startswith("http://detail/"):
            parts = url.split("/")
            page = int(parts[-2])
            i = int(parts[-1])
            
            # Simulate failures/duplicates for the first page
            if page == 1:
                if i % 2 == 0:
                    # Failure
                    return None
                else:
                    # Duplicate: all odd items yield the same Udemy link
                    course_slug = "duplicate-course"
            else:
                # Later pages yield unique courses
                course_slug = f"course-{page}-{i}"

            html = f'<html><h3>Title {url}</h3><a class="btn btn-primary" href="https://www.udemy.com/course/{course_slug}/?couponCode=123">Link</a></html>'
            resp.content = html.encode('utf-8')
        else:
            return None
        
        return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 500
    listing_calls = [c for c in scraper.http.get.call_args_list if "jobs.e-next.in" in c[0][0]]
    # Page 1 gives 1 unique course. We need 499 more.
    # 499 / 60 = 8.3 => 9 more pages. Total 1 + 9 = 10 pages.
    assert len(listing_calls) == 10

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
    # Should only try the first page and then stop
    listing_calls = [c for c in scraper.http.get.call_args_list if "jobs.e-next.in" in c[0][0]]
    assert len(listing_calls) == 1

@pytest.mark.asyncio
async def test_duplicate_listing_urls_and_duplicate_udemy_urls(scraper):
    scraper.MAX_COURSES = 5
    
    async def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "jobs.e-next.in/course/udemy/" in url:
            # 5 items, all same detail link, 5 more different but with same udemy url
            links = ['<a class="btn btn-secondary btn-sm btn-block" href="http://detail/1">Detail</a>'] * 5
            links += ['<a class="btn btn-secondary btn-sm btn-block" href="http://detail/2">Detail</a>'] * 5
            html = f"<html>{''.join(links)}</html>"
            resp.content = html.encode('utf-8')
        elif url == "http://detail/1" or url == "http://detail/2":
            html = '<html><h3>Title</h3><a class="btn btn-primary" href="https://www.udemy.com/course/same-course/?couponCode=123">Link</a></html>'
            resp.content = html.encode('utf-8')
        else:
            resp = None
            
        return resp

    scraper.http.get.side_effect = mock_get
    
    await scraper.scrape(asyncio.Semaphore(1))
    
    assert len(scraper.data) == 1 # Only one unique course overall
    
    # We should have deduplicated the detail urls
    detail_calls = [c for c in scraper.http.get.call_args_list if "detail" in c[0][0]]
    # Detail 1 and Detail 2 were called once each.
    assert len(detail_calls) == 2
