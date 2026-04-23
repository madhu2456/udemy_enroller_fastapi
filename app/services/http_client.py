import asyncio
import logging
import random
from typing import Optional, Dict, Any, Union, List

import httpx
from loguru import logger

from app.core.constants import DEFAULT_USER_AGENT

class AsyncHTTPClient:
    """Wraps httpx.AsyncClient with retries, timeout management, and anti-ban features."""

    # User-Agent rotation to avoid pattern detection
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    def __init__(self, proxy: Optional[str] = None, max_concurrency: int = 20):
        self.proxy = proxy
        self._request_semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._last_request_time = 0.0
        self.client = httpx.AsyncClient(
            proxy=self.proxy,
            timeout=httpx.Timeout(15.0, connect=30.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=20.0),
        )

    def _get_headers(self, url: str, custom_headers: Optional[Dict] = None, req_type: str = "document") -> Dict[str, str]:
        """Generate randomized headers for each request, respecting existing ones."""
        # Rotate User-Agent for each request to avoid pattern detection
        ua = random.choice(self._USER_AGENTS)
        if custom_headers and "User-Agent" in custom_headers:
            ua = custom_headers["User-Agent"]
        elif self.client.headers.get("User-Agent"):
            ua = self.client.headers.get("User-Agent")

        from urllib.parse import urlparse
        parsed_url = urlparse(url)

        # Basic common headers in Chrome order, starting with Host
        headers = {
            "Host": parsed_url.netloc,
            "Connection": "keep-alive",
        }

        # Add Client Hints (Crucial for modern bot bypass)
        headers.update({
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })

        if req_type == "document":
            headers.update({
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            })
        elif req_type in ["api", "xhr"]:
            headers.update({
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
            })
            
            if "Referer" in headers:
                try:
                    ref_origin = f"{urlparse(headers['Referer']).scheme}://{urlparse(headers['Referer']).netloc}"
                    headers["Origin"] = ref_origin
                except Exception:
                    pass
        
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def _apply_human_like_delay(self):
        """Apply a human-like delay between requests to avoid detection patterns."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        
        # Target delay: 1-4 seconds between requests (human-like browsing)
        target_delay = random.uniform(1.0, 4.0)
        
        if time_since_last < target_delay:
            delay = target_delay - time_since_last
            # Add micro-jitter to avoid perfect timing patterns
            delay += random.uniform(-0.1, 0.2)
            await asyncio.sleep(max(0.1, delay))
        
        self._last_request_time = asyncio.get_event_loop().time()

    async def close(self):
        await self.client.aclose()

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async GET request with retries and anti-ban delays."""
        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        randomize = kwargs.pop("randomize_headers", True)
        req_type = kwargs.pop("req_type", "document")
        retry_403 = kwargs.pop("retry_403", False)
        
        if randomize:
            headers = self._get_headers(url, kwargs.pop("headers", None), req_type=req_type)
        else:
            headers = kwargs.pop("headers", None)
        
        last_attempt = 0
        last_error: Optional[Exception] = None
        
        # Apply human-like delay between requests
        await self._apply_human_like_delay()
        
        # Add a small random jitter before the request to avoid pattern detection
        if randomize:
            await asyncio.sleep(random.uniform(0.1, 0.5))

        for attempt in range(attempts):
            last_attempt = attempt + 1
            try:
                async with self._request_semaphore:
                    response = await self.client.get(url, headers=headers, **kwargs)
                if raise_for_status:
                    response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_error = e
                if log_failures:
                    logger.debug(f"GET attempt {attempt + 1}/{attempts} failed for {url}: {type(e).__name__}")
                
                should_retry = attempt < attempts - 1
                
                if isinstance(e, httpx.TooManyRedirects):
                    # Redirect loops are fatal for the current session/client state
                    should_retry = False 
                elif isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    if status == 403:
                        should_retry = retry_403 and should_retry
                    elif status != 429 and status < 500:
                        should_retry = False
                
                if should_retry:
                    # Exponential backoff with jitter
                    delay = (2 ** attempt) + random.uniform(1, 3)
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        delay = int(retry_after) if retry_after and retry_after.isdigit() else 30
                        logger.warning(f"Rate limited (429) on {url}. Waiting {delay}s...")
                    
                    # If we got a 403, maybe try to change the User-Agent if we were randomizing
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 403 and randomize:
                        pass # Kept consistent UA to match Client Hints

                    await asyncio.sleep(delay)
                else:
                    break
        
        if log_failures:
            reason = f"{type(last_error).__name__}" if last_error else "UnknownError"
            if isinstance(last_error, httpx.HTTPStatusError):
                reason += f" ({last_error.response.status_code})"
            logger.warning(f"GET failed after {last_attempt} attempt(s) [{reason}]: {url}")
        return None

    async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async POST request with retries."""
        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        randomize = kwargs.pop("randomize_headers", True)
        req_type = kwargs.pop("req_type", "api")
        retry_403 = kwargs.pop("retry_403", False)
        
        if randomize:
            headers = self._get_headers(url, kwargs.pop("headers", None), req_type=req_type)
        else:
            headers = kwargs.pop("headers", None)

        last_attempt = 0
        last_error: Optional[Exception] = None
        
        # Apply human-like delay between requests
        await self._apply_human_like_delay()
        
        if randomize:
            await asyncio.sleep(random.uniform(0.1, 0.5))

        for attempt in range(attempts):
            last_attempt = attempt + 1
            try:
                async with self._request_semaphore:
                    response = await self.client.post(url, headers=headers, **kwargs)
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
                    if status == 403:
                        should_retry = retry_403 and should_retry
                    elif status != 429 and status < 500:
                        should_retry = False
                
                if should_retry:
                    delay = (2 ** attempt) + random.uniform(1, 3)
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        delay = int(retry_after) if retry_after and retry_after.isdigit() else 30
                    
                    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 403 and randomize:
                        pass # Kept consistent UA to match Client Hints

                    await asyncio.sleep(delay)
                else:
                    break
        
        if log_failures:
            reason = f"{type(last_error).__name__}" if last_error else "UnknownError"
            if isinstance(last_error, httpx.HTTPStatusError):
                reason += f" ({last_error.response.status_code})"
            logger.warning(f"POST failed after {last_attempt} attempt(s) [{reason}]: {url}")
        return None

    async def safe_json(self, response: Optional[httpx.Response], context: str = "") -> Union[Dict, list, None]:
        """Safely parse JSON from a response, handling manual decompression if needed."""
        if response is None:
            return None
        
        try:
            return response.json()
        except Exception as initial_e:
            content = response.content
            text = None
            decompression_method = None
            
            # 1. Try Brotli
            try:
                import brotli
                text = brotli.decompress(content).decode('utf-8', errors='replace')
                decompression_method = "brotli"
            except Exception:
                pass
            
            # 2. Try Gzip
            if not text:
                try:
                    import gzip
                    text = gzip.decompress(content).decode('utf-8', errors='replace')
                    decompression_method = "gzip"
                except Exception:
                    pass
            
            # 3. Try Zlib (with and without header)
            if not text:
                try:
                    import zlib
                    try:
                        text = zlib.decompress(content).decode('utf-8', errors='replace')
                        decompression_method = "zlib"
                    except Exception:
                        text = zlib.decompress(content, -zlib.MAX_WBITS).decode('utf-8', errors='replace')
                        decompression_method = "raw_deflate"
                except Exception:
                    pass

            # If we have decompressed text, try to parse it as JSON
            if text:
                import json
                try:
                    return json.loads(text)
                except Exception as json_e:
                    logger.error(f"JSONDecodeError after manual {decompression_method} decompression in {context or 'unknown'}: {json_e}. Text preview: {text[:200]}")
                    return None

            # If we couldn't decompress or it wasn't compressed data, log the original error
            try:
                body_preview = response.text[:200]
            except Exception:
                body_preview = f"<binary data: {len(content)} bytes>"
            
            logger.error(f"JSON error in {context or 'unknown'}: {initial_e}. Body: {body_preview}")
            return None
