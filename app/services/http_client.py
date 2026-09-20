import asyncio
import random
import threading
import time
from typing import Dict, Optional, Union
from urllib.parse import urlparse, urlunparse

import httpx
from loguru import logger

from app.logging_config import sanitize_log_message


def _log_safe_url(url: str) -> str:
    """Redact a URL for logging (F-ENRL-C10).

    Strips the query string (coupon codes / session tokens live in queries),
    then passes the remainder through the shared sanitizer for defense in depth.
    """
    try:
        parsed = urlparse(url)
        url = urlunparse(parsed._replace(query="", fragment=""))
    except (ValueError, TypeError):
        pass
    return sanitize_log_message(str(url))


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

    # Expanded server user-agent pool (17 agents) for diverse browser representation
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
        self._thread_local = threading.local()
        self._scrapers_lock = threading.Lock()
        self._all_scrapers: set = set()
        self._ua_pins: Dict[str, str] = {}
        self._init_client()

        from config.settings import get_settings

        self._is_server = get_settings().DEPLOYMENT_ENV == "server"

    def _close_all_scrapers(self):
        with self._scrapers_lock:
            scrapers = list(self._all_scrapers)
            self._all_scrapers.clear()
        for s in scrapers:
            try:
                s.close()
            except Exception:
                pass

    def _init_client(self):
        """Initialize or re-initialize the internal httpx client and cloudscraper."""
        self._close_all_scrapers()
        self._thread_local = threading.local()
        self.client = httpx.AsyncClient(
            proxy=self.proxy,
            timeout=httpx.Timeout(15.0, connect=30.0),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=40, max_keepalive_connections=20, keepalive_expiry=20.0
            ),
        )

    def _get_scraper(self, is_mobile: bool = False):
        """Get or create a persistent CloudScraper instance.

        CloudScraper is used to access coupon aggregator sites that may use
        Cloudflare protection. This is necessary because these sites are the
        primary source of course coupon data.

        Note: Users are responsible for ensuring their use complies with
        the terms of service of coupon aggregator sites.
        """
        attr_name = "mobile_scraper" if is_mobile else "desktop_scraper"
        scraper = getattr(self._thread_local, attr_name, None)
        if scraper is None:
            import cloudscraper
            from requests.adapters import HTTPAdapter

            if is_mobile:
                scraper = cloudscraper.create_scraper(
                    browser={
                        "browser": "chrome",
                        "platform": "android",
                        "mobile": True,
                    }
                )
            else:
                scraper = cloudscraper.create_scraper(
                    browser={
                        "browser": "chrome",
                        "platform": "windows",
                        "desktop": True,
                    }
                )
            adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
            scraper.mount("https://", adapter)
            scraper.mount("http://", adapter)
            if self.proxy:
                scraper.proxies = {"http": self.proxy, "https": self.proxy}
            setattr(self._thread_local, attr_name, scraper)
            with self._scrapers_lock:
                self._all_scrapers.add(scraper)
        return scraper

    async def set_proxy(self, proxy: Optional[str]):
        """Update proxy and re-initialize client, safely closing the old client.

        User-supplied proxies are ignored unless ALLOW_USER_PROXY is enabled
        (F-ENRL-C05). ``__init__`` is deliberately NOT gated so admin-configured
        PROXIES (coupon checker) still apply on construction.
        """
        from config.settings import resolve_user_proxy

        proxy = resolve_user_proxy(proxy)
        if self.proxy == proxy:
            return
        self.proxy = proxy
        old_client = self.client
        self._init_client()
        if old_client:
            try:
                await old_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing old HTTP client: {e}")

    def _get_headers(
        self,
        url: str,
        custom_headers: Optional[Dict] = None,
        req_type: str = "document",
    ) -> Dict[str, str]:
        """Generate randomized headers for each request, respecting existing ones."""
        parsed_url = urlparse(url)

        if self._is_server:
            return self._get_headers_server(parsed_url, custom_headers, req_type)
        else:
            return self._get_headers_local(parsed_url, custom_headers, req_type)

    def _get_headers_local(
        self, parsed_url, custom_headers: Optional[Dict], req_type: str
    ) -> Dict[str, str]:
        """Original local header generation (unchanged from SEO commit)."""
        pin_key = f"{parsed_url.netloc}::{req_type}"
        custom_ua = (custom_headers or {}).get("User-Agent") or (custom_headers or {}).get("user-agent")
        if custom_ua:
            ua = custom_ua
        elif pin_key in self._ua_pins:
            ua = self._ua_pins[pin_key]
        else:
            ua = random.choice(self._USER_AGENTS_LOCAL)
            client_ua = self.client.headers.get("User-Agent", "")
            if client_ua and "python-httpx" not in client_ua:
                ua = client_ua
            self._ua_pins[pin_key] = ua

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
            major = self._extract_chrome_major(ua) or "133"
            headers["sec-ch-ua"] = (
                f'"Not_A Brand";v="8", "Chromium";v="{major}", "Google Chrome";v="{major}"'
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
        pin_key = f"{parsed_url.netloc}::{req_type}"
        custom_ua = (custom_headers or {}).get("User-Agent") or (custom_headers or {}).get("user-agent")
        if custom_ua:
            ua = custom_ua
        elif pin_key in self._ua_pins:
            ua = self._ua_pins[pin_key]
        else:
            ua = random.choice(self._USER_AGENTS_SERVER)
            self._ua_pins[pin_key] = ua

        is_mobile = (
            "UdemyAndroid" in ua
            or "okhttp" in ua
            or "Mobile" in ua
            or req_type == "mobile"
        )
        if req_type == "mobile" and not is_mobile:
            ua = (
                random.choice(
                    [
                        u
                        for u in self._USER_AGENTS_SERVER
                        if "UdemyAndroid" in u or "okhttp" in u
                    ]
                )
                or "okhttp/4.12.0 UdemyAndroid 9.116.0(2078) (phone)"
            )
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
        """Apply a polite delay between requests to respect rate limits.

        On server deployments, uses much longer delays to avoid Udemy rate limits.
        Local runs keep the original fast settings.
        """
        from config.settings import get_settings

        is_server = get_settings().DEPLOYMENT_ENV == "server"
        current_time = time.monotonic()
        time_since_last = current_time - self._last_request_time

        if is_server:
            target_delay = random.uniform(5.0, 12.0)
        else:
            target_delay = random.uniform(1.0, 4.0)

        if time_since_last < target_delay:
            delay = target_delay - time_since_last
            delay += random.uniform(-0.1, 0.2)
            await asyncio.sleep(max(0.1, delay))

        self._last_request_time = time.monotonic()

    async def close(self):
        await self.client.aclose()
        self._close_all_scrapers()

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """SSRF guard: allow only http/https on SAFE_PORTS (80/443), deny private/reserved IP ranges."""
        import ipaddress
        import socket

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            port = parsed.port
            if port is not None and port not in {80, 443}:
                return False
            host = parsed.hostname
            if not host:
                return False
            cleaned_host = host.strip("[]").lower()
            if cleaned_host in ("localhost", "127.0.0.1", "::1") or cleaned_host.endswith(".localhost"):
                return False
            try:
                ip = ipaddress.ip_address(cleaned_host)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                    or ip.is_multicast
                    or ip.is_unspecified
                ):
                    return False
                return True
            except ValueError:
                pass
            try:
                from _pytest.outcomes import Failed as _PytestFailed
                _catch_types = (socket.gaierror, socket.herror, OSError, _PytestFailed)
            except ImportError:
                _catch_types = (socket.gaierror, socket.herror, OSError)

            try:
                infos = socket.getaddrinfo(cleaned_host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                if not infos:
                    return False
                for _family, _type, _proto, _canon, sockaddr in infos:
                    ip_str = sockaddr[0]
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        if (
                            ip.is_private
                            or ip.is_loopback
                            or ip.is_link_local
                            or ip.is_reserved
                            or ip.is_multicast
                            or ip.is_unspecified
                        ):
                            return False
                    except ValueError:
                        continue
                return True
            except _catch_types:
                return False
            return True
        except Exception:
            return False

    async def request(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """Boundary-level SSRF guarded request dispatcher."""
        if not self._is_safe_url(url):
            logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None
        method = method.upper()
        if method == "GET":
            return await self.get(url, **kwargs)
        elif method == "POST":
            return await self.post(url, **kwargs)
        elif method == "HEAD":
            return await self.head(url, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async GET request with retries and anti-ban delays."""
        if not self._is_safe_url(url):
            logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None

        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        randomize = kwargs.pop("randomize_headers", True)
        req_type = kwargs.pop("req_type", "document")
        retry_403 = kwargs.pop("retry_403", False)
        use_cloudscraper = kwargs.pop("use_cloudscraper", False)

        follow_kw = kwargs.pop("follow_redirects", None)
        allow_kw = kwargs.pop("allow_redirects", None)
        if follow_kw is not None:
            redirect_policy = bool(follow_kw)
        elif allow_kw is not None:
            redirect_policy = bool(allow_kw)
        else:
            redirect_policy = False

        custom_cookies = kwargs.pop("cookies", {})

        await self._apply_human_like_delay()

        for attempt in range(attempts):
            if not self._is_safe_url(url):
                logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
                return None

            if randomize:
                headers = self._get_headers(
                    url, kwargs.get("headers"), req_type=req_type
                )
            else:
                headers = kwargs.get("headers")

            is_mobile_request = (
                "UdemyAndroid" in str((headers or {}).get("User-Agent", ""))
                or req_type == "mobile"
            )

            try:
                if use_cloudscraper:
                    if self._is_server:
                        scraper_headers = self._build_scraper_headers_server(
                            headers, kwargs, is_mobile_request, req_type
                        )
                    else:
                        scraper_headers = self._build_scraper_headers_local(
                            headers, kwargs, is_mobile_request
                        )

                    def _do_scrape():
                        scraper = self._get_scraper(is_mobile=is_mobile_request)
                        if custom_cookies:
                            scraper.cookies.update(custom_cookies)

                        resp = scraper.get(
                            url,
                            headers=scraper_headers,
                            timeout=25,
                            allow_redirects=redirect_policy,
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
                    call_kwargs["follow_redirects"] = redirect_policy

                    async with self._request_semaphore:
                        response = await self.client.get(
                            url, headers=headers, **call_kwargs
                        )

                    if custom_cookies is not None:
                        custom_cookies.update(dict(response.cookies))

                if response.status_code == 403 and log_failures:
                    ua_preview = str(((scraper_headers if use_cloudscraper else headers) or {}).get("User-Agent", "unknown"))[:60]
                    logger.warning(
                        f"  [{'CloudScraper' if use_cloudscraper else 'HTTPX'} 403] URL: {_log_safe_url(url)} | UA: {ua_preview}"
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
                            f"  DNS Resolution failed for {_log_safe_url(url)} (Attempt {attempt + 1}/{attempts})"
                        )

                if log_failures:
                    logger.info(
                        f"{'CloudScraper' if use_cloudscraper else 'GET'} attempt {attempt + 1}/{attempts} failed for {_log_safe_url(url)}: {error_name}"
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

                    delay = (2**attempt) + random.uniform(1, 3)
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

    async def head(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async HEAD request with retries."""
        if not self._is_safe_url(url):
            logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None

        attempts = kwargs.pop("attempts", 3)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)

        follow_kw = kwargs.pop("follow_redirects", None)
        allow_kw = kwargs.pop("allow_redirects", None)
        if follow_kw is not None:
            redirect_policy = bool(follow_kw)
        elif allow_kw is not None:
            redirect_policy = bool(allow_kw)
        else:
            redirect_policy = False

        await self._apply_human_like_delay()

        headers = self._get_headers(url, kwargs.get("headers"), req_type="document")

        for attempt in range(attempts):
            if not self._is_safe_url(url):
                logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
                return None

            try:
                call_kwargs = kwargs.copy()
                call_kwargs.pop("headers", None)
                call_kwargs["follow_redirects"] = redirect_policy

                async with self._request_semaphore:
                    response = await self.client.head(
                        url, headers=headers, **call_kwargs
                    )

                if raise_for_status:
                    response.raise_for_status()
                return response

            except Exception as e:
                error_name = type(e).__name__
                if log_failures:
                    logger.info(
                        f"HEAD attempt {attempt + 1}/{attempts} failed for {_log_safe_url(url)}: {error_name}"
                    )

                should_retry = attempt < attempts - 1
                if isinstance(e, httpx.HTTPStatusError):
                    status = e.response.status_code
                    if status != 429 and status < 500:
                        should_retry = False

                if should_retry:
                    delay = (2**attempt) + random.uniform(1, 3)
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
        if headers and headers.get("User-Agent"):
            scraper_headers["User-Agent"] = headers["User-Agent"]
        for hint in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
            if headers and hint in headers:
                scraper_headers[hint] = headers[hint]
        scraper_headers["Accept-Encoding"] = "identity"
        return scraper_headers

    def _build_scraper_headers_server(
        self, headers, kwargs, is_mobile_request, req_type
    ):
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
            if headers and headers.get("User-Agent"):
                scraper_headers["User-Agent"] = headers["User-Agent"]
            for hint in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
                if headers and hint in headers:
                    scraper_headers[hint] = headers[hint]
            scraper_headers["Accept-Encoding"] = "identity"
        return scraper_headers

    async def post(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """Perform an async POST request with retries."""
        if not self._is_safe_url(url):
            logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None

        attempts = kwargs.pop("attempts", 4)
        raise_for_status = kwargs.pop("raise_for_status", True)
        log_failures = kwargs.pop("log_failures", True)
        randomize = kwargs.pop("randomize_headers", True)
        req_type = kwargs.pop("req_type", "api")
        retry_403 = kwargs.pop("retry_403", False)
        use_cloudscraper = kwargs.pop("use_cloudscraper", False)

        follow_kw = kwargs.pop("follow_redirects", None)
        allow_kw = kwargs.pop("allow_redirects", None)
        if follow_kw is not None:
            redirect_policy = bool(follow_kw)
        elif allow_kw is not None:
            redirect_policy = bool(allow_kw)
        else:
            redirect_policy = False

        custom_cookies = kwargs.pop("cookies", {})
        custom_headers = kwargs.pop("headers", None)
        json_payload = kwargs.pop("json", None)

        await self._apply_human_like_delay()

        for attempt in range(attempts):
            if not self._is_safe_url(url):
                logger.warning(f"Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
                return None

            if randomize:
                headers = self._get_headers(url, custom_headers, req_type=req_type)
            else:
                headers = custom_headers

            is_mobile_request = (
                "UdemyAndroid" in str(headers.get("User-Agent", ""))
                or req_type == "mobile"
            )

            try:
                if use_cloudscraper:
                    if self._is_server:
                        scraper_headers = self._build_scraper_headers_server(
                            headers, kwargs, is_mobile_request, req_type
                        )
                    else:
                        scraper_headers = self._build_scraper_headers_local(
                            headers, kwargs, is_mobile_request
                        )

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
                                allow_redirects=redirect_policy,
                            )
                        else:
                            resp = scraper.post(
                                url,
                                data=kwargs.get("data"),
                                headers=scraper_headers,
                                timeout=25,
                                allow_redirects=redirect_policy,
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

                    call_kwargs = kwargs.copy()
                    call_kwargs.pop("headers", None)
                    call_kwargs["follow_redirects"] = redirect_policy

                    async with self._request_semaphore:
                        if json_payload is not None:
                            response = await self.client.post(
                                url, headers=headers, json=json_payload, **call_kwargs
                            )
                        else:
                            response = await self.client.post(
                                url, headers=headers, **call_kwargs
                            )

                    if custom_cookies is not None:
                        custom_cookies.update(dict(response.cookies))

                if response.status_code == 403 and log_failures:
                    ua_preview = str(((scraper_headers if use_cloudscraper else headers) or {}).get("User-Agent", "unknown"))[:60]
                    logger.warning(
                        f"  [{'CloudScraper' if use_cloudscraper else 'HTTPX'} 403] URL: {_log_safe_url(url)} | UA: {ua_preview}"
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
                            f"  DNS Resolution failed for {_log_safe_url(url)} (Attempt {attempt + 1}/{attempts})"
                        )

                if log_failures:
                    logger.info(
                        f"{'CloudScraper' if use_cloudscraper else 'POST'} attempt {attempt + 1}/{attempts} failed for {_log_safe_url(url)}: {error_name}"
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

                    delay = (2**attempt) + random.uniform(1, 3)
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
            # T2: Cloudflare-aware pre-check (before wasted brotli/gzip on CF HTML).
            try:
                status = response.status_code
            except Exception:
                status = "?"
            try:
                ctype = str(response.headers.get("content-type", ""))
            except Exception:
                ctype = ""
            ctype_low = ctype.lower()
            try:
                raw_url = str(getattr(response, "url", "") or "")
            except Exception:
                raw_url = ""
            safe_url = _log_safe_url(raw_url) if raw_url else (context or "unknown")
            try:
                preview_full = response.text
            except Exception:
                try:
                    preview_full = bytes(response.content or b"").decode(
                        "utf-8", errors="replace"
                    )
                except Exception:
                    preview_full = ""
            preview_low = (preview_full or "")[:4096].lower()
            is_cf = (
                any(
                    m in preview_low
                    for m in (
                        "just a moment",
                        "cf-browser-verification",
                        "attention required",
                        "cf-challenge",
                        "cf_chl",
                    )
                )
                or "text/html" in ctype_low
                or "<html" in preview_low
            )
            collapsed = " ".join((preview_full or "").split())
            snippet = sanitize_log_message(collapsed[:120])[:120]
            if is_cf:
                logger.warning(
                    f"CF challenge in {context or 'unknown'} | URL: {safe_url} | status={status} ctype={ctype} | snippet: {snippet}"
                )
                return None
            try:
                nbytes = len(response.content or b"")
            except Exception:
                nbytes = -1
            content = response.content
            text = None

            # 1. Try Brotli
            try:
                import brotli

                text = brotli.decompress(content).decode("utf-8", errors="replace")
            except Exception:
                pass

            # 2. Try Gzip
            if not text:
                try:
                    import gzip

                    text = gzip.decompress(content).decode("utf-8", errors="replace")
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
                    except Exception:
                        text = zlib.decompress(content, -zlib.MAX_WBITS).decode(
                            "utf-8", errors="replace"
                        )
                except Exception:
                    pass

            if text:
                import json

                try:
                    return json.loads(text)
                except Exception:
                    pass

            logger.error(
                f"JSON error in {context or 'unknown'} | URL: {safe_url} | status={status} ctype={ctype} len={nbytes} | snippet: {snippet} | err={type(initial_e).__name__}"
            )
            return None
