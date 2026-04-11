"""Unified asynchronous HTTP client for the Udemy Enroller."""

import asyncio
import logging
from typing import Optional, Dict, Any, Union

import httpx
from loguru import logger


class AsyncHTTPClient:
    """Wraps httpx.AsyncClient with retries and timeout management."""

    def __init__(self, proxy: Optional[str] = None, max_concurrency: int = 20):
        self.proxy = proxy
        self._request_semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.client = httpx.AsyncClient(
            proxy=self.proxy,
            timeout=httpx.Timeout(15.0, connect=30.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=20.0),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
            }
        )

    async def close(self):
        await self.client.aclose()

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async GET request with retries."""
        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        last_attempt = 0
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            last_attempt = attempt + 1
            try:
                async with self._request_semaphore:
                    response = await self.client.get(url, **kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_error = e
                if log_failures:
                    logger.debug(f"GET attempt {attempt + 1}/{attempts} failed for {url}: {type(e).__name__}")
                should_retry = attempt < attempts - 1
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    # Retry only on rate limiting and 5xx server errors.
                    if status != 429 and status < 500:
                        should_retry = False
                if should_retry:
                    delay = 2 * (attempt + 1)
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        delay = int(retry_after) if retry_after and retry_after.isdigit() else 30
                        if log_failures:
                            logger.warning(f"Rate limited (429). Waiting {delay}s before retrying GET...")
                    await asyncio.sleep(delay)
                else:
                    break
        if log_failures:
            reason = f"{type(last_error).__name__}" if last_error else "UnknownError"
            logger.warning(f"GET failed after {last_attempt} attempt(s) [{reason}]: {url}")
        return None

    async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async POST request with retries."""
        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        last_attempt = 0
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            last_attempt = attempt + 1
            try:
                async with self._request_semaphore:
                    response = await self.client.post(url, **kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_error = e
                if log_failures:
                    logger.debug(f"POST attempt {attempt + 1}/{attempts} failed for {url}: {type(e).__name__}")
                should_retry = attempt < attempts - 1
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    # Retry only on rate limiting and 5xx server errors.
                    if status != 429 and status < 500:
                        should_retry = False
                if should_retry:
                    delay = 2 * (attempt + 1)
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        delay = int(retry_after) if retry_after and retry_after.isdigit() else 30
                        if log_failures:
                            logger.warning(f"Rate limited (429). Waiting {delay}s before retrying POST...")
                    await asyncio.sleep(delay)
                else:
                    break
        if log_failures:
            reason = f"{type(last_error).__name__}" if last_error else "UnknownError"
            logger.warning(f"POST failed after {last_attempt} attempt(s) [{reason}]: {url}")
        return None

    async def safe_json(self, response: Optional[httpx.Response], context: str = "") -> Union[Dict, list, None]:
        """Safely parse JSON from a response."""
        if response is None:
            return None
        try:
            return response.json()
        except Exception as e:
            logger.error(f"JSON error in {context or 'unknown'}: {e}. Body: {response.text[:200]}")
            return None
