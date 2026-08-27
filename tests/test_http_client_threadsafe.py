import threading
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.http_client import AsyncHTTPClient


@pytest.mark.asyncio
async def test_thread_local_scrapers_distinct_per_thread():
    client = AsyncHTTPClient()
    scrapers = []

    def worker():
        s = client._get_scraper(is_mobile=False)
        scrapers.append(s)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Distinct scraper per thread
    assert len(scrapers) == 3
    assert len(set(scrapers)) == 3
    assert len(client._all_scrapers) == 3

    # Closing client closes all scrapers and clears set
    await client.close()
    assert len(client._all_scrapers) == 0


@pytest.mark.asyncio
async def test_init_client_clears_old_scrapers():
    client = AsyncHTTPClient()
    s1 = client._get_scraper(is_mobile=False)
    s2 = client._get_scraper(is_mobile=True)
    assert len(client._all_scrapers) == 2

    # Re-initialization
    client._init_client()
    assert len(client._all_scrapers) == 0

    # New scraper after re-init
    s3 = client._get_scraper(is_mobile=False)
    assert s3 is not s1
    assert s3 is not s2
    assert len(client._all_scrapers) == 1
    await client.close()


@pytest.mark.asyncio
async def test_redirect_kwargs_normalization_httpx():
    client = AsyncHTTPClient()

    with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(
            200,
            content=b"ok",
            request=httpx.Request("GET", "https://example.com/test1"),
        )

        # Case 1: allow_redirects=False passed
        await client.get("https://example.com/test1", allow_redirects=False)
        assert mock_get.call_count == 1
        _, kwargs = mock_get.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs.get("follow_redirects") is False

        # Case 2: follow_redirects=False passed
        mock_get.reset_mock()
        mock_get.return_value = httpx.Response(
            200,
            content=b"ok",
            request=httpx.Request("GET", "https://example.com/test2"),
        )
        await client.get("https://example.com/test2", follow_redirects=False)
        assert mock_get.call_count == 1
        _, kwargs = mock_get.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs.get("follow_redirects") is False

        # Case 3: Default is True
        mock_get.reset_mock()
        mock_get.return_value = httpx.Response(
            200,
            content=b"ok",
            request=httpx.Request("GET", "https://example.com/test3"),
        )
        await client.get("https://example.com/test3")
        assert mock_get.call_count == 1
        _, kwargs = mock_get.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs.get("follow_redirects") is True

    await client.close()


@pytest.mark.asyncio
async def test_redirect_kwargs_normalization_post_and_head():
    client = AsyncHTTPClient()

    with patch.object(client.client, "head", new_callable=AsyncMock) as mock_head:
        mock_head.return_value = httpx.Response(
            200,
            request=httpx.Request("HEAD", "https://example.com/head1"),
        )
        await client.head("https://example.com/head1", allow_redirects=False)
        assert mock_head.call_count == 1
        _, kwargs = mock_head.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs.get("follow_redirects") is False

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            content=b"ok",
            request=httpx.Request("POST", "https://example.com/post1"),
        )
        await client.post("https://example.com/post1", allow_redirects=False, json={"a": 1})
        assert mock_post.call_count == 1
        _, kwargs = mock_post.call_args
        assert "allow_redirects" not in kwargs
        assert kwargs.get("follow_redirects") is False

    await client.close()
