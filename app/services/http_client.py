import asyncio
import random
from typing import Optional, Dict, Union

import httpx
from loguru import logger


class AsyncHTTPClient:
    """Wraps httpx.AsyncClient with retries, timeout management, and anti-ban features."""

    # Original local user-agent pool (5 agents)
    _USER_AGENTS_LOCAL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)",
        "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
    ]

    # Expanded server user-agent pool (17 agents) for datacenter IP evasion
    _USER_AGENTS_SERVER = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/131.0.2903.86",
        "okhttp/4.12.0 UdemyAndroid 9.116.0(2078) (phone)",
        "okhttp/4.12.0 UdemyAndroid 9.115.1(2076) (phone)",
        "okhttp/4.11.0 UdemyAndroid 9.114.0(2070) (phone)",
        "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)",
        "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    ]

    # Server-only Accept-Language rotation
    _ACCEPT_LANGUAGES_SERVER = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9",
        "en-US,en;q=0.8",
        "en;q=0.9",
        "en-US,en-GB;q=0.9,en;q=0.8",
    ]

    def __init__(self, proxy: Optional[str] = None, max_concurrency: int = 20):
        self.proxy = proxy
        self._request_semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._last_request_time = 0.0
        self._scraper = None
        self._mobile_scraper = None
        self._init_client()

        from config.settings import get_settings

        self._is_server = get_settings().DEPLOYMENT_ENV == "server"

    def _init_client(self):
        """Initialize or re-initialize the internal httpx client and cloudscraper."""
        self.client = httpx.AsyncClient(
            proxy=self.proxy,
            timeout=httpx.Timeout(15.0, connect=30.0),
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=40, max_keepalive_connections=20, keepalive_expiry=20.0
            ),
        )
        self._scraper = None
        self._mobile_scraper = None

    def _get_scraper(self, is_mobile: bool = False):
        """Get or create a persistent CloudScraper instance."""
        import cloudscraper

        if is_mobile:
            if not self._mobile_scraper:
                self._mobile_scraper = cloudscraper.create_scraper(
                    browser={
                        "browser": "chrome",
                        "platform": "android",
                        "mobile": True,
                    }
                )
                if self.proxy:
                    self._mobile_scraper.proxies = {"http": self.proxy, "https": self.proxy}
            return self._mobile_scraper
        else:
            if not self._scraper:
                self._scraper = cloudscraper.create_scraper(
                    browser={
                        "browser": "chrome",
                        "platform": "windows",
                        "desktop": True,
                    }
                )
                if self.proxy:
                    self._scraper.proxies = {"http": self.proxy, "https": self.proxy}
            return self._scraper

    def set_proxy(self, proxy: Optional[str]):
        """Update proxy and re-initialize client."""
        if self.proxy == proxy:
            return
        self.proxy = proxy
        self._init_client()

    def _get_headers(
        self,
        url: str,
        custom_headers: Optional[Dict] = None,
        req_type: str = "document",
    ) -> Dict[str, str]:
        """Generate randomized headers for each request, respecting existing ones."""
        from urllib.parse import urlparse

        parsed_url = urlparse(url)

        if self._is_server:
            return self._get_headers_server(parsed_url, custom_headers, req_type)
        else:
            return self._get_headers_local(parsed_url, custom_headers, req_type)

    def _get_headers_local(
        self, parsed_url, custom_headers: Optional[Dict], req_type: str
    ) -> Dict[str, str]:
        """Original local header generation (unchanged from SEO commit)."""
        ua = random.choice(self._USER_AGENTS_LOCAL)
        if custom_headers and "User-Agent" in custom_headers:
            ua = custom_headers["User-Agent"]
        elif self.client.headers.get("User-Agent"):
            ua = self.client.headers.get("User-Agent")

        headers = {
            "Host": parsed_url.netloc,
            "Connection": "keep-alive",
        }

        is_mobile = "UdemyAndroid" in ua or "okhttp" in ua or req_type == "mobile"
        if req_type == "mobile" and not is_mobile:
            ua = "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)"
            is_mobile = True

        headers.update(
            {
                "sec-ch-ua-mobile": "?1" if is_mobile else "?0",
                "sec-ch-ua-platform": '"Android"' if is_mobile else '"Windows"',
            }
        )
        if not is_mobile:
            headers["sec-ch-ua"] = (
                '"Not_A Brand";v="99", "Chromium";v="124", "Google Chrome";v="124"'
            )

        if req_type == "document":
            headers.update(
                {
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Sec-Fetch-Dest": "document",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
        elif req_type in ["api", "xhr", "mobile"]:
            headers.update(
                {
                    "User-Agent": ua,
                    "Accept": "application/json, text/plain, */*",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )

            if is_mobile:
                headers["x-checkout-is-mobile-app"] = "false"
                headers["X-Requested-With"] = "com.udemy.android"
                headers["Accept-Language"] = "en-US"
            else:
                headers["X-Requested-With"] = "XMLHttpRequest"

            referer = None
            if custom_headers:
                referer = custom_headers.get("Referer") or custom_headers.get("referer")

            if referer:
                try:
                    ref_origin = (
                        f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
                    )
                    headers["Origin"] = ref_origin
                except Exception:
                    pass
            elif not is_mobile:
                headers["Origin"] = "https://www.udemy.com"

        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _get_headers_server(
        self, parsed_url, custom_headers: Optional[Dict], req_type: str
    ) -> Dict[str, str]:
        """Expanded server header generation with diverse UAs and dynamic hints."""
        ua = random.choice(self._USER_AGENTS_SERVER)
        if custom_headers and "User-Agent" in custom_headers:
            ua = custom_headers["User-Agent"]

        is_mobile = (
            "UdemyAndroid" in ua
            or "okhttp" in ua
            or "Mobile" in ua
            or req_type == "mobile"
        )
        if req_type == "mobile" and not is_mobile:
            ua = random.choice(
                [
                    u for u in self._USER_AGENTS_SERVER if "UdemyAndroid" in u or "okhttp" in u
                ]
            ) or "okhttp/4.12.0 UdemyAndroid 9.116.0(2078) (phone)"
            is_mobile = True

        accept_lang = random.choice(self._ACCEPT_LANGUAGES_SERVER)

        headers: Dict[str, str] = {
            "Host": parsed_url.netloc,
            "Connection": "keep-alive",
        }

        if not is_mobile:
            chrome_major = self._extract_chrome_major(ua)
            if chrome_major:
                headers["sec-ch-ua"] = (
                    f'"Not_A Brand";v="8", "Chromium";v="{chrome_major}", '
                    f'"Google Chrome";v="{chrome_major}"'
                )
            else:
                headers["sec-ch-ua"] = (
                    '"Not_A Brand";v="8", "Chromium";v="133", "Google Chrome";v="133"'
                )
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = '"Windows"'
            if "Macintosh" in ua:
                headers["sec-ch-ua-platform"] = '"macOS"'
            if "Firefox" in ua:
                headers.pop("sec-ch-ua", None)
                headers.pop("sec-ch-ua-mobile", None)
                headers.pop("sec-ch-ua-platform", None)
        else:
            headers["sec-ch-ua-mobile"] = "?1"
            headers["sec-ch-ua-platform"] = '"Android"'
            if "iPhone" in ua or "iPad" in ua:
                headers["sec-ch-ua-platform"] = '"iOS"'

        if req_type == "document":
            headers.update(
                {
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-User": "?1",
                    "Sec-Fetch-Dest": "document",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": accept_lang,
                    "DNT": "1",
                }
            )
            if not is_mobile and "Firefox" not in ua:
                headers["sec-fetch-priority"] = "high"
        elif req_type in ["api", "xhr", "mobile"]:
            headers.update(
                {
                    "User-Agent": ua,
                    "Accept": "application/json, text/plain, */*",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": accept_lang,
                }
            )

            if is_mobile:
                headers["x-checkout-is-mobile-app"] = "false"
                headers["X-Requested-With"] = "com.udemy.android"
                headers["Accept-Language"] = "en-US"
                headers["x-udemy-client-language"] = "en"
                if "UdemyAndroid" in ua:
                    version = self._extract_udemy_version(ua)
                    if version:
                        headers["x-udemy-android-version"] = version
            else:
                headers["X-Requested-With"] = "XMLHttpRequest"

            referer = None
            if custom_headers:
                referer = custom_headers.get("Referer") or custom_headers.get("referer")

            if referer:
                try:
                    ref_origin = (
                        f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
                    )
                    headers["Origin"] = ref_origin
                except Exception:
                    pass
            elif not is_mobile:
                headers["Origin"] = "https://www.udemy.com"

        if custom_headers:
            headers.update(custom_headers)
        return headers

    @staticmethod
    def _extract_chrome_major(ua: str) -> Optional[str]:
        import re
        m = re.search(r"Chrome/(\d+)", ua)
        return m.group(1) if m else None

    @staticmethod
    def _extract_udemy_version(ua: str) -> Optional[str]:
        import re
        m = re.search(r"UdemyAndroid\s+([\d.]+(?:\(\d+\))?)", ua)
        return m.group(1) if m else None

    async def _apply_human_like_delay(self):
        """Apply a human-like delay between requests to avoid detection patterns.

        On server deployments, uses much longer delays to avoid Udemy rate limits.
        Local runs keep the original fast settings.
        """
        from config.settings import get_settings

        is_server = get_settings().DEPLOYMENT_ENV == "server"
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time

        if is_server:
            target_delay = random.uniform(5.0, 12.0)
        else:
            target_delay = random.uniform(1.0, 4.0)

        if time_since_last < target_delay:
            delay = target_delay - time_since_last
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
        use_cloudscraper = kwargs.pop("use_cloudscraper", False)

        custom_cookies = kwargs.pop("cookies", {})

        await self._apply_human_like_delay()

        for attempt in range(attempts):
            if randomize:
                headers = self._get_headers(
                    url, kwargs.get("headers"), req_type=req_type
                )
            else:
                headers = kwargs.get("headers")

            is_mobile_request = (
                "UdemyAndroid" in str(headers.get("User-Agent", "")) or req_type == "mobile"
            )

            try:
                if use_cloudscraper:
                    if self._is_server:
                        scraper_headers = self._build_scraper_headers_server(headers, kwargs, is_mobile_request, req_type)
                    else:
                        scraper_headers = self._build_scraper_headers_local(headers, kwargs, is_mobile_request)

                    def _do_scrape():
                        scraper = self._get_scraper(is_mobile=is_mobile_request)
                        if custom_cookies:
                            scraper.cookies.update(custom_cookies)

                        resp = scraper.get(
                            url,
                            headers=scraper_headers,
                            timeout=25,
                            allow_redirects=kwargs.get("allow_redirects", True),
                        )
                        if custom_cookies is not None:
                            custom_cookies.update(resp.cookies.get_dict())
                        return resp

                    resp_sync = await asyncio.to_thread(_do_scrape)
                    response = httpx.Response(
                        status_code=resp_sync.status_code,
                        content=resp_sync.content,
                        headers=httpx.Headers(resp_sync.headers),
                        request=httpx.Request("GET", resp_sync.url),
                    )
                else:
                    if custom_cookies:
                        for k, v in custom_cookies.items():
                            self.client.cookies.set(k, v)

                    call_kwargs = kwargs.copy()
                    call_kwargs.pop("headers", None)

                    async with self._request_semaphore:
                        response = await self.client.get(url, headers=headers, **call_kwargs)

                    if custom_cookies is not None:
                        custom_cookies.update(dict(response.cookies))

                if response.status_code == 403:
                    ua_preview = str(headers.get("User-Agent", "unknown"))[:60]
                    logger.warning(
                        f"  [{'CloudScraper' if use_cloudscraper else 'HTTPX'} 403] URL: {url} | UA: {ua_preview}"
                    )

                if raise_for_status:
                    response.raise_for_status()
                return response

            except Exception as e:
                error_name = type(e).__name__
                error_msg = str(e)

                is_dns_error = any(
                    x in error_msg
                    for x in [
                        "NameResolutionError",
                        "getaddrinfo failed",
                        "gaierror",
                        "WSAHOST_NOT_FOUND",
                    ]
                )
                if is_dns_error:
                    error_name = "DNSResolutionError"
                    if log_failures:
                        logger.warning(
                            f"  DNS Resolution failed for {url} (Attempt {attempt+1}/{attempts})"
                        )

                if log_failures:
                    logger.info(
                        f"{'CloudScraper' if use_cloudscraper else 'GET'} attempt {attempt + 1}/{attempts} failed for {url}: {error_name}"
                    )

                should_retry = attempt < attempts - 1
                is_403 = False
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    if status == 403:
                        is_403 = True
                        should_retry = retry_403 and should_retry
                    elif status != 429 and status < 500:
                        should_retry = False

                if should_retry:
                    if self._is_server and is_403 and randomize:
                        logger.info("  Rotating headers for 403 retry...")
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        continue

                    delay = (2 ** attempt) + random.uniform(1, 3)
                    if is_dns_error:
                        delay += 5

                    if (
                        isinstance(e, httpx.HTTPStatusError)
                        and e.response.status_code == 429
                    ):
                        retry_after = e.response.headers.get("Retry-After")
                        delay = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else 30
                        )

                    await asyncio.sleep(delay)
                else:
                    break
        return None

    def _build_scraper_headers_local(self, headers, kwargs, is_mobile_request):
        """Original minimal CloudScraper headers (local)."""
        scraper_headers = {}
        if headers and "Referer" in headers:
            scraper_headers["Referer"] = headers["Referer"]
        if headers and "Authorization" in headers:
            scraper_headers["Authorization"] = headers["Authorization"]

        explicit_ua = (kwargs.get("headers") or {}).get("User-Agent")
        if explicit_ua:
            scraper_headers["User-Agent"] = explicit_ua
        elif is_mobile_request:
            if headers and "User-Agent" in headers:
                scraper_headers["User-Agent"] = headers["User-Agent"]

        scraper_headers["Accept-Encoding"] = "identity"
        return scraper_headers

    def _build_scraper_headers_server(self, headers, kwargs, is_mobile_request, req_type):
        """Full header pass-through for CloudScraper (server)."""
        if is_mobile_request or req_type in ("api", "xhr", "mobile"):
            scraper_headers = dict(headers) if headers else {}
            scraper_headers["Accept-Encoding"] = "identity"
        else:
            scraper_headers = {}
            if headers and "Referer" in headers:
                scraper_headers["Referer"] = headers["Referer"]
            if headers and "Authorization" in headers:
                scraper_headers["Authorization"] = headers["Authorization"]
            explicit_ua = (kwargs.get("headers") or {}).get("User-Agent")
            if explicit_ua:
                scraper_headers["User-Agent"] = explicit_ua
            scraper_headers["Accept-Encoding"] = "identity"
        return scraper_headers

    async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async POST request with retries."""
        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        randomize = kwargs.pop("randomize_headers", True)
        req_type = kwargs.pop("req_type", "api")
        retry_403 = kwargs.pop("retry_403", False)
        use_cloudscraper = kwargs.pop("use_cloudscraper", False)

        custom_cookies = kwargs.pop("cookies", {})
        custom_headers = kwargs.pop("headers", None)
        json_payload = kwargs.pop("json", None)

        await self._apply_human_like_delay()

        for attempt in range(attempts):
            if randomize:
                headers = self._get_headers(
                    url, custom_headers, req_type=req_type
                )
            else:
                headers = custom_headers

            is_mobile_request = (
                "UdemyAndroid" in str(headers.get("User-Agent", "")) or req_type == "mobile"
            )

            try:
                if use_cloudscraper:
                    if self._is_server:
                        scraper_headers = self._build_scraper_headers_server(headers, kwargs, is_mobile_request, req_type)
                    else:
                        scraper_headers = self._build_scraper_headers_local(headers, kwargs, is_mobile_request)

                    def _do_scrape():
                        scraper = self._get_scraper(is_mobile=is_mobile_request)
                        if custom_cookies:
                            scraper.cookies.update(custom_cookies)

                        if json_payload is not None:
                            resp = scraper.post(
                                url,
                                json=json_payload,
                                headers=scraper_headers,
                                timeout=25,
                                allow_redirects=kwargs.get("allow_redirects", True),
                            )
                        else:
                            resp = scraper.post(
                                url,
                                data=kwargs.get("data"),
                                headers=scraper_headers,
                                timeout=25,
                                allow_redirects=kwargs.get("allow_redirects", True),
                            )

                        if custom_cookies is not None:
                            custom_cookies.update(resp.cookies.get_dict())
                        return resp

                    resp_sync = await asyncio.to_thread(_do_scrape)
                    response = httpx.Response(
                        status_code=resp_sync.status_code,
                        content=resp_sync.content,
                        headers=httpx.Headers(resp_sync.headers),
                        request=httpx.Request("POST", resp_sync.url),
                    )
                else:
                    if custom_cookies:
                        for k, v in custom_cookies.items():
                            self.client.cookies.set(k, v)

                    async with self._request_semaphore:
                        if json_payload is not None:
                            response = await self.client.post(url, headers=headers, json=json_payload, **kwargs)
                        else:
                            response = await self.client.post(url, headers=headers, **kwargs)

                    if custom_cookies is not None:
                        custom_cookies.update(dict(response.cookies))

                if response.status_code == 403:
                    ua_preview = str(headers.get("User-Agent", "unknown"))[:60]
                    logger.warning(
                        f"  [{'CloudScraper' if use_cloudscraper else 'HTTPX'} 403] URL: {url} | UA: {ua_preview}"
                    )

                if raise_for_status:
                    response.raise_for_status()
                return response

            except Exception as e:
                error_name = type(e).__name__
                error_msg = str(e)

                is_dns_error = any(
                    x in error_msg
                    for x in [
                        "NameResolutionError",
                        "getaddrinfo failed",
                        "gaierror",
                        "WSAHOST_NOT_FOUND",
                    ]
                )
                if is_dns_error:
                    error_name = "DNSResolutionError"
                    if log_failures:
                        logger.warning(
                            f"  DNS Resolution failed for {url} (Attempt {attempt+1}/{attempts})"
                        )

                if log_failures:
                    logger.info(
                        f"{'CloudScraper' if use_cloudscraper else 'POST'} attempt {attempt + 1}/{attempts} failed for {url}: {error_name}"
                    )

                should_retry = attempt < attempts - 1
                is_403 = False
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    if status == 403:
                        is_403 = True
                        should_retry = retry_403 and should_retry
                    elif status != 429 and status < 500:
                        should_retry = False

                if should_retry:
                    if self._is_server and is_403 and randomize:
                        logger.info("  Rotating headers for 403 retry...")
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        continue

                    delay = (2 ** attempt) + random.uniform(1, 3)
                    if is_dns_error:
                        delay += 5

                    if (
                        isinstance(e, httpx.HTTPStatusError)
                        and e.response.status_code == 429
                    ):
                        retry_after = e.response.headers.get("Retry-After")
                        delay = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else 30
                        )

                    await asyncio.sleep(delay)
                else:
                    break
        return None

    async def safe_json(
        self, response: Optional[httpx.Response], context: str = ""
    ) -> Union[Dict, list, None]:
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

                text = brotli.decompress(content).decode("utf-8", errors="replace")
                decompression_method = "brotli"
            except Exception:
                pass

            # 2. Try Gzip
            if not text:
                try:
                    import gzip

                    text = gzip.decompress(content).decode("utf-8", errors="replace")
                    decompression_method = "gzip"
                except Exception:
                    pass

            # 3. Try Zlib
            if not text:
                try:
                    import zlib

                    try:
                        text = zlib.decompress(content).decode(
                            "utf-8", errors="replace"
                        )
                        decompression_method = "zlib"
                    except Exception:
                        text = zlib.decompress(content, -zlib.MAX_WBITS).decode(
                            "utf-8", errors="replace"
                        )
                        decompression_method = "raw_deflate"
                except Exception:
                    pass

            if text:
                import json

                try:
                    return json.loads(text)
                except Exception as json_e:
                    logger.error(
                        f"JSONDecodeError after manual {decompression_method} decompression in {context or 'unknown'}: {json_e}"
                    )
                    return None

            try:
                body_preview = response.text[:500]
            except Exception:
                body_preview = f"<binary data: {len(content)} bytes>"

            logger.error(
                f"JSON error in {context or 'unknown'}: {initial_e}. Body: {body_preview}"
            )
            return None
