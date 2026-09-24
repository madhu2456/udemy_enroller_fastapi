"""Course scraper service - standard emulated client logic (No Playwright for enrollment, Playwright allowed for scraping fallback)."""

import asyncio
import html
import json
import os
import re
import time
import traceback
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from bs4 import BeautifulSoup
from loguru import logger

from app.services.course import Course, sanitize_course_title
from app.services.http_client import AsyncHTTPClient, _log_safe_url
from app.services.robots_gate import RobotsGate
from app.services.udemy_validation import (
    is_trk_udemy_url,
    is_udemy_course_url,
    is_udemy_url,
)

import ipaddress
import socket

# R4 / W3-02: pytest's network block raises _pytest.outcomes.Failed (BaseException, not
# Exception). To keep the BaseException swallow narrowed while preserving test fail-open,
# we import Failed explicitly and catch it together with Exception (FM-039/DEPLOYMENT_ENV).
try:
    from _pytest.outcomes import Failed as _PytestFailed  # type: ignore[import-untyped]
except ImportError:  # pytest not installed in prod
    _PytestFailed = None  # type: ignore[assignment]

if _PytestFailed is not None:
    _DNS_CATCH_TYPES = (Exception, _PytestFailed)  # type: ignore[assignment]
else:
    _DNS_CATCH_TYPES = (Exception,)

SAFE_PORTS = frozenset({80, 443})


def _is_safe_url(url: str) -> bool:
    """SSRF guard: allow only http/https on SAFE_PORTS, deny private IP ranges after DNS."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        port = parsed.port
        if port is not None and port not in SAFE_PORTS:
            return False
        host = parsed.hostname
        if not host:
            return False
        # Direct IP literal check
        try:
            ip = ipaddress.ip_address(host)
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
        # DNS resolution for hostnames
        try:
            infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except _DNS_CATCH_TYPES:
            # R4 / W3-02: Narrowed from BaseException → Exception (+ _PytestFailed
            # explicitly, which is BaseException not Exception). Fail-open in local/test
            # for DNS/network block so offline flows and pytest allow_network keep working;
            # http.get will fail naturally if host truly unresolvable. In prod
            # (DEPLOYMENT_ENV == "server") fail-closed to avoid SSRF bypass via DNS
            # failure. Documented per R4 — no BaseException swallow (e.g. KeyboardInterrupt
            # propagates).
            try:
                from config.settings import get_settings  # local import to avoid cycle

                if get_settings().DEPLOYMENT_ENV == "server":
                    return False
            except Exception:
                pass
            return True
        for _family, _type, _proto, _canon, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
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
    except Exception:
        return False


class Scraper(ABC):
    """Base class for all coupon site scrapers."""

    def __init__(self, http: AsyncHTTPClient, proxy: Optional[str] = None):
        from config.settings import get_settings

        app_settings = get_settings()

        self.http = http
        self.proxy = proxy
        # F252: per-host robots.txt gate with 24 h cache; fail-open on fetch
        # errors (policy in app/services/robots_gate.py + docs/ops).
        self.robots_gate = RobotsGate(http)
        self.data: List[Course] = []
        self.progress = 0
        self.length = 0
        self.done = False
        self.error = None
        # F252: Circuit breaker and timeout configuration
        self.consecutive_failures = 0
        self.circuit_open = False
        self.max_consecutive_failures = getattr(
            app_settings, "SCRAPER_CIRCUIT_BREAKER_FAILURES", 5
        )
        self.request_timeout = getattr(
            app_settings, "SCRAPER_REQUEST_TIMEOUT_SECONDS", 5.0
        )

    @property
    def courses(self) -> List[Course]:
        """List of scraped courses."""
        return self.data

    @property
    @abstractmethod
    def site_name(self) -> str:
        """Human-readable site name."""
        pass

    @property
    @abstractmethod
    def code_name(self) -> str:
        """Internal short code."""
        pass

    @abstractmethod
    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        """Scrape courses from the site."""
        pass

    @staticmethod
    def _is_cf_challenge(resp) -> bool:
        if resp is None or getattr(resp, "status_code", None) not in (403, 429, 503):
            return False
        text = (getattr(resp, "text", "") or "")[:4096].lower()
        cf_signatures = (
            "just a moment",
            "cf-browser-verification",
            "attention required",
            "cf-challenge",
            "cf_chl",
            "cf-turnstile",
            "challenges.cloudflare.com",
        )
        return any(sig in text for sig in cf_signatures)

    async def _http_get_resilient(
        self, url: str, timeout: float = 10.0, use_robots_circuit: bool = False, **kwargs
    ) -> Optional[object]:
        """Optimistic fast-path via async HTTPX with automated CloudScraper fallback."""
        kwargs.pop("use_cloudscraper", None)
        getter = self._http_get if use_robots_circuit else self.http.get
        resp = await getter(
            url, use_cloudscraper=False, timeout=timeout, raise_for_status=False, **kwargs
        )
        if (
            resp is None
            or getattr(resp, "status_code", None) in (403, 503)
            or self._is_cf_challenge(resp)
        ):
            resp = await getter(url, use_cloudscraper=True, timeout=timeout, **kwargs)
        return resp

    def parse_html(self, content: Union[str, bytes]) -> BeautifulSoup:
        """Helper to parse HTML with BeautifulSoup."""
        import warnings

        from bs4 import MarkupResemblesLocatorWarning

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
            return BeautifulSoup(content, "lxml")

    async def _robots_allowed(self, url: str) -> bool:
        """Honor the target host's robots.txt (F252).

        Fail-open by design: robots.txt fetch errors/5xx allow the fetch so a
        robots outage never takes coupon sources offline (documented policy).
        """
        return await self.robots_gate.is_allowed(url)

    async def _http_get(self, url: str, **kwargs) -> Optional[object]:
        """self.http.get gated by the robots.txt policy, per-request timeout,
        consecutive-failure circuit breaker, and structured logging (F252).

        Each scraper's primary listing fetch goes through this helper: if the
        circuit breaker is open, or if the host disallows the user-agent/path,
        the fetch is skipped (None) and no data is collected from that host.
        """
        if self.circuit_open:
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
                consecutive_failures=self.consecutive_failures,
            ).warning(
                f"  [{self.site_name}] Request skipped — circuit breaker is OPEN "
                f"({self.consecutive_failures} consecutive failures)"
            )
            return None

        if not _is_safe_url(url):
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
            ).warning(f"  [{self.site_name}] Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None

        if not await self._robots_allowed(url):
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
            ).info(
                f"  {self.site_name}: skipped {url} — robots.txt Disallow (F252)"
            )
            return None

        if "timeout" not in kwargs:
            kwargs["timeout"] = self.request_timeout

        try:
            resp = await self.http.get(url, **kwargs)
            if resp is not None and getattr(resp, "status_code", None) == 200:
                self.consecutive_failures = 0
                logger.bind(
                    scraper=self.code_name,
                    site=self.site_name,
                    url=_log_safe_url(url),
                    status_code=200,
                ).debug(f"  [{self.site_name}] Fetch success: 200 OK")
                return resp
            else:
                status = getattr(resp, "status_code", "None")
                self.consecutive_failures += 1
                logger.bind(
                    scraper=self.code_name,
                    site=self.site_name,
                    url=_log_safe_url(url),
                    status_code=status,
                    consecutive_failures=self.consecutive_failures,
                    threshold=self.max_consecutive_failures,
                ).warning(
                    f"  [{self.site_name}] Fetch failed (status={status}, "
                    f"failures={self.consecutive_failures}/{self.max_consecutive_failures})"
                )
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.circuit_open = True
                    self.error = (
                        f"Circuit breaker tripped after {self.consecutive_failures} consecutive failures"
                    )
                    logger.bind(
                        scraper=self.code_name,
                        site=self.site_name,
                        consecutive_failures=self.consecutive_failures,
                    ).error(
                        f"  [{self.site_name}] Circuit breaker TRIPPED after "
                        f"{self.consecutive_failures} consecutive failures"
                    )
                return resp
        except Exception as exc:
            self.consecutive_failures += 1
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
                error=type(exc).__name__,
                consecutive_failures=self.consecutive_failures,
                threshold=self.max_consecutive_failures,
            ).warning(
                f"  [{self.site_name}] Fetch exception ({type(exc).__name__}, "
                f"failures={self.consecutive_failures}/{self.max_consecutive_failures}): {exc}"
            )
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.circuit_open = True
                self.error = (
                    f"Circuit breaker tripped after {self.consecutive_failures} consecutive failures"
                )
                logger.bind(
                    scraper=self.code_name,
                    site=self.site_name,
                    consecutive_failures=self.consecutive_failures,
                ).error(
                    f"  [{self.site_name}] Circuit breaker TRIPPED after "
                    f"{self.consecutive_failures} consecutive failures"
                )
            return None

    async def _resolve_trk_redirect(self, trk_url: str) -> str | None:
        """Follow a short trk.udemy.com redirect to the real course URL.
        Returns the resolved URL or None if resolution fails.
        """
        if not is_trk_udemy_url(trk_url):
            normalized = Course.normalize_link(trk_url)
            return normalized if is_udemy_course_url(normalized) else None

        # Course.normalize_link inherently extracts u=, url=, link=, target=, redirect=, go=
        # and preserves any outer couponCode.
        normalized = Course.normalize_link(trk_url)
        if is_udemy_course_url(normalized) and not is_trk_udemy_url(normalized):
            return normalized

        import urllib.parse

        outer_qs = urllib.parse.parse_qs(urllib.parse.urlparse(trk_url).query)
        outer_coupon = outer_qs.get("couponCode", [None])[0]

        # SSRF hardening: manual redirect loop (max 10 hops) with SAFE_PORTS and private IP denylist
        max_hops = 10
        current_url = trk_url
        for _ in range(max_hops):
            if not _is_safe_url(current_url):
                logger.warning(f"Blocked unsafe trk URL (SSRF guard): {_log_safe_url(current_url)}")
                return None
            try:
                resp = await self.http.get(
                    current_url,
                    use_cloudscraper=True,
                    follow_redirects=False,
                    allow_redirects=False,
                    raise_for_status=False,
                    log_failures=False,
                    randomize_headers=True,
                    timeout=15,
                    attempts=2,
                )
                if not resp:
                    return None
                # Redirect case: validate Location before next hop
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location") or resp.headers.get("Location") or ""
                    if not location:
                        return None
                    location = urllib.parse.urljoin(current_url, location)
                    if not _is_safe_url(location):
                        logger.warning(f"Blocked unsafe redirect Location (SSRF guard): {_log_safe_url(location)}")
                        return None
                    if is_udemy_course_url(location):
                        resolved_norm = Course.normalize_link(location)
                        if outer_coupon and "couponCode=" not in resolved_norm:
                            separator = "&" if "?" in resolved_norm else "?"
                            resolved_norm += f"{separator}couponCode={outer_coupon}"
                        return resolved_norm
                    if is_trk_udemy_url(location):
                        # Preserve outer coupon when hopping between trk URLs
                        try:
                            loc_qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
                            if outer_coupon and "couponCode" not in loc_qs:
                                sep = "&" if "?" in location else "?"
                                location += f"{sep}couponCode={outer_coupon}"
                        except Exception:
                            pass
                    current_url = location
                    continue
                # Non-redirect: check final URL
                resolved = str(resp.url)
                if not _is_safe_url(resolved):
                    return None
                if is_udemy_course_url(resolved):
                    resolved_norm = Course.normalize_link(resolved)
                    if outer_coupon and "couponCode=" not in resolved_norm:
                        separator = "&" if "?" in resolved_norm else "?"
                        resolved_norm += f"{separator}couponCode={outer_coupon}"
                    return resolved_norm
                return None
            except Exception as e:
                logger.debug(f"GET fallback redirect resolution failed for {current_url}: {e}")
                return None
        logger.warning(f"trk redirect exceeded max hops ({max_hops}) for {_log_safe_url(trk_url)}")
        return None

    def cleanup_link(self, link: str) -> Optional[str]:
        """Extract clean Udemy link with coupon from various redirectors."""
        if not link:
            return None

        # Delegate to Course.normalize_link which now handles tracking unwrapping
        clean_url = Course.normalize_link(link)

        # Ensure it's a valid udemy course link
        if is_udemy_course_url(clean_url):
            return clean_url

        return None

    def _html_text(self, raw: str, default: str = "") -> str:
        """Safely extract text without MarkupResemblesLocatorWarning."""
        if not raw:
            return default
        if "<" not in raw and "&" not in raw:
            return raw.strip()
        import html

        try:
            soup = self.parse_html(raw)
            return html.unescape(soup.get_text(" ", strip=True))
        except Exception:
            return html.unescape(raw).strip()

    def _is_generic_course_title(self, title: str) -> bool:
        """Filter out generic CTA titles."""
        if not title:
            return False
        import html
        import re
        import unicodedata

        clean = html.unescape(title).strip()
        clean = (
            unicodedata.normalize("NFKD", clean)
            .encode("ascii", "ignore")
            .decode("utf-8")
            .lower()
        )
        clean = re.sub(r"[^\w\s]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        words = clean.split()
        if len(words) > 5:
            return False

        pattern = r"^(get|view|access|open|download|enroll|redeem|claim|start|grab)\s+(?:(?:this|the|a|my|your)\s+)?(course|coupon|deal|offer|now|free|link|udemy|discount)"
        if re.match(pattern, clean):
            return True

        exact_matches = {
            "get coupon",
            "get course",
            "get course now",
            "get course noe",
            "enroll now",
            "redeem coupon",
            "download now",
            "view course",
            "get this deal",
            "claim coupon",
            "access course",
            "enroll for free",
            "free coupon",
            "click here",
            "learn more",
            "start course",
            "grab discount",
            "go to course",
            "enroll here",
            "obtener el curso",
            "kursu incele",
        }
        return clean in exact_matches

    def append_to_list(self, title: str, url: str):
        """Add a course to the data list with deduplication logic."""
        title = sanitize_course_title(title)
        if not title or not url or not is_udemy_url(url):
            return

        if self._is_generic_course_title(title) or len(title) < 4:
            # Try to extract from URL slug if possible
            slug = None
            try:
                path_parts = urllib.parse.urlparse(url).path.split("/")
                if len(path_parts) > 2 and path_parts[1] == "course":
                    slug = path_parts[2]
            except Exception:
                slug = None
            if slug:
                title = slug.replace("-", " ").title()
            else:
                return  # Skip if we can't get a good title

        course = Course(title=title, url=url, site=self.site_name)
        if course not in self.data:
            self.data.append(course)

    async def _run_detail_task(self, semaphore, func, *args):
        """Helper to run a detail-fetching function with a concurrency semaphore."""
        if self.circuit_open:
            return None, None
        async with semaphore:
            if self.circuit_open:
                return None, None
            try:
                return await func(*args)
            except Exception as e:
                logger.bind(
                    scraper=self.code_name,
                    site=self.site_name,
                    func=func.__name__,
                ).warning(f"Detail task failed in {func.__name__}: {e}")
                return None, None

    async def playwright_get(self, url: str, wait_selector: str = None) -> str:
        """Fetch page content using Playwright with stealth patches.

        Owner decision: playwright-stealth is used as a fallback for coupon aggregator
        sites that use Cloudflare protection. This targets coupon sites, not Udemy.
        The primary scraping method uses CloudScraper without stealth.

        Used as a fallback when CloudScraper cannot bypass Cloudflare protection
        on coupon aggregator sites. playwright-stealth applies browser fingerprint
        patches to reduce detection by anti-bot systems. The stealth library is
        optional — if not installed, Playwright runs without patches.

        Wall-clock bound (T4-T1 hardening): internal timeouts sum to at most
        35s (goto 15000ms + optional wait_for_selector 5000ms + single CF-retry
        reload 15000ms) plus one page.wait_for_timeout(2000) settle; typical
        single-load path completes in ~17-22s. At most 2 page loads
        (1 goto + 1 CF-retry reload). wait_until=commit is used for speed.
        Returns "" on ANY failure, never raises, and never mutates the circuit
        breaker. Missing binary/libs (or missing playwright import) returns ""
        immediately with a BLOCKED_BY_ENV log (reason=binary|libs).

        Caller contract (SSRF/robots gating lives in the caller, NOT here):
        the caller (T4-T2 wiring) MUST pre-check _is_safe_url(url),
        _robots_allowed(url) and same-host scope before calling this helper.
        """
        try:
            try:
                from playwright.async_api import async_playwright
            except ImportError as e:
                logger.bind(reason="binary", error=type(e).__name__).warning(
                    f"  Playwright BLOCKED_BY_ENV (reason=binary): import failed for {url}: {e}"
                )
                return ""

            async with async_playwright() as p:
                launch_kwargs = {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                }
                if self.proxy:
                    launch_kwargs["proxy"] = {"server": self.proxy}

                try:
                    browser = await p.chromium.launch(**launch_kwargs)
                except Exception as e:
                    _msg = str(e).lower()
                    if "executable" in _msg or "has not been downloaded" in _msg:
                        _reason = "binary"
                    elif (
                        "missing depend" in _msg
                        or "host system is missing" in _msg
                        or "shared librar" in _msg
                    ):
                        _reason = "libs"
                    else:
                        raise
                    logger.bind(reason=_reason, error=type(e).__name__).warning(
                        f"  Playwright BLOCKED_BY_ENV (reason={_reason}) for {url}: {e}"
                    )
                    return ""
                try:
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        locale="en-US",
                    )
                    page = await context.new_page()

                    try:
                        from playwright_stealth import Stealth

                        await Stealth().apply_stealth_async(page)
                    except ImportError:
                        logger.warning(
                            "  playwright_stealth not installed, proceeding without stealth patches."
                        )
                    except Exception as e:
                        logger.warning(
                            f"  Playwright stealth patch failed, proceeding without it: {e}"
                        )

                    await page.goto(url, wait_until="commit", timeout=15000)

                    await page.wait_for_timeout(2000)

                    if wait_selector:
                        try:
                            await page.wait_for_selector(wait_selector, timeout=5000)
                        except Exception:
                            pass

                    content = await page.content()

                    # Check for Cloudflare block (single reload retry: max 2 loads)
                    if (
                        "Just a moment..." in content
                        or "cf-browser-verification" in content
                        or "Attention Required!" in content
                    ):
                        logger.warning(
                            f"  Playwright hit Cloudflare block on {url}, single reload retry..."
                        )
                        try:
                            await page.reload(wait_until="commit", timeout=15000)
                        except Exception:
                            return ""
                        content = await page.content()
                        if (
                            "Just a moment..." in content
                            or "cf-browser-verification" in content
                            or "Attention Required!" in content
                        ):
                            logger.warning(
                                f"  Playwright Cloudflare challenge unresolved for {url}."
                            )
                            return ""

                    return content
                finally:
                    try:
                        await browser.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"  Playwright fetch failed for {url}: {e}")
            return ""


class RealDiscountScraper(Scraper):
    API_URL = "https://cdn.real.discount/api/courses"
    MAX_COURSES = 500
    MAX_PAGES = 5
    PAGE_LIMIT = 100

    @property
    def site_name(self) -> str:
        return "Real Discount"

    @property
    def code_name(self) -> str:
        return "rd"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = self.MAX_PAGES
            self.progress = 0
            headers = {
                "referer": "https://www.real.discount/",
                "Host": "cdn.real.discount",
            }
            seen: set[str] = set()

            for page_num in range(1, self.MAX_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break
                url = (
                    f"{self.API_URL}?page={page_num}&limit={self.PAGE_LIMIT}"
                    f"&sortBy=sale_start&store=Udemy&freeOnly=true"
                )
                resp = await self._http_get(url, headers=headers, timeout=15)
                if not resp or getattr(resp, "status_code", None) != 200:
                    if page_num == 1:
                        self.error = "API unreachable; Playwright skipped"
                        logger.info("  Real Discount: API unreachable; Playwright skipped")
                    break

                data = await self.http.safe_json(resp)
                if not data or not isinstance(data, dict) or "items" not in data:
                    if page_num == 1:
                        self.error = "API unreachable; Playwright skipped"
                        logger.info("  Real Discount: API unreachable; Playwright skipped")
                    break

                items = data.get("items", [])
                if not items or not isinstance(items, list):
                    break

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("store", "").lower() != "udemy" or item.get("type") == "ad":
                        continue
                    sale_price = item.get("sale_price")
                    if sale_price is not None:
                        try:
                            if float(sale_price) != 0.0:
                                continue
                        except (ValueError, TypeError):
                            continue

                    raw_url = item.get("url")
                    title = item.get("name")
                    if not raw_url or not title:
                        continue

                    normalized = Course.normalize_link(raw_url)
                    if is_udemy_course_url(normalized) and normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], normalized)
                        if len(self.data) >= self.MAX_COURSES:
                            break

                self.progress = page_num
                if len(items) < self.PAGE_LIMIT:
                    break
        except Exception:
            self.error = traceback.format_exc()


class ENextScraper(Scraper):
    MAX_COURSES = 500
    MAX_LISTING_PAGES = 80
    BATCH_SIZE = 6
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "E-next"

    @property
    def code_name(self) -> str:
        return "en"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = self.MAX_LISTING_PAGES
            seen_detail_urls = set()
            seen_udemy_urls = set()

            async def _fetch_details(item):
                try:
                    resp = await self._http_get_resilient(
                        item["href"], timeout=10
                    )
                    if not resp:
                        return None, None
                    soup = self.parse_html(resp.content)
                    title = (
                        soup.find("h3").get_text(strip=True)
                        if soup.find("h3")
                        else "Unknown"
                    )
                    link = soup.find("a", {"class": "btn btn-primary"})
                    return title, link["href"] if link else None
                except Exception:
                    return None, None

            batch_size = getattr(self, "BATCH_SIZE", 6)
            for start_page in range(1, self.MAX_LISTING_PAGES + 1, batch_size):
                if len(self.data) >= self.MAX_COURSES:
                    break

                page_tasks = [
                    self._http_get(f"https://jobs.e-next.in/course/udemy/{p}")
                    for p in range(
                        start_page,
                        min(start_page + batch_size, self.MAX_LISTING_PAGES + 1),
                    )
                ]
                responses = await asyncio.gather(*page_tasks, return_exceptions=True)

                batch_had_items = False
                pending_items = []

                for resp in responses:
                    if isinstance(resp, Exception) or not resp or resp.status_code != 200:
                        continue
                    soup = self.parse_html(resp.content)
                    buttons = soup.find_all(
                        "a", {"class": "btn btn-secondary btn-sm btn-block"}
                    )
                    if buttons:
                        batch_had_items = True
                        for btn in buttons:
                            href = btn.get("href")
                            if href and href not in seen_detail_urls:
                                seen_detail_urls.add(href)
                                pending_items.append(btn)

                if not batch_had_items:
                    break

                detail_chunk_size = getattr(self, "DETAIL_BATCH_SIZE", 10)
                for i in range(0, len(pending_items), detail_chunk_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break

                    chunk = pending_items[i : i + detail_chunk_size]
                    detail_tasks = [
                        self._run_detail_task(detail_semaphore, _fetch_details, item)
                        for item in chunk
                    ]

                    results_list = await asyncio.gather(
                        *detail_tasks, return_exceptions=True
                    )
                    for results in results_list:
                        if isinstance(results, Exception) or not results:
                            continue

                        title, link = results
                        if title and link:
                            if len(self.data) >= self.MAX_COURSES:
                                break

                            normalized_link = Course.normalize_link(link)
                            if (
                                not normalized_link
                                or not is_udemy_course_url(normalized_link)
                            ):
                                continue

                            if normalized_link in seen_udemy_urls:
                                continue

                            prev_len = len(self.data)
                            self.append_to_list(title, normalized_link)

                            if len(self.data) > prev_len:
                                seen_udemy_urls.add(normalized_link)

        except Exception:
            self.error = traceback.format_exc()


class InterviewGigScraper(Scraper):
    """Interview Gig (elearn.interviewgig.com) — WordPress REST API scraper.
    Parses direct Udemy links from post content.rendered HTML.
    Some posts are bundle posts with 40+ courses each.
    Short trk hops go through _resolve_one + a local Semaphore(2), chunked,
    with at most 80 scheduled trk HTTP calls.
    """

    MAX_COURSES = 500
    MAX_API_PAGES = 6
    MAX_TRK_HTTP = 150
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "Interview Gig"

    @property
    def code_name(self) -> str:
        return "ig"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  Interview Gig: Fetching via WordPress REST API...")
            import json

            base_api = "https://elearn.interviewgig.com/wp-json/wp/v2/posts"
            seen_hrefs: set[str] = set()
            direct_items: list[tuple[str, str]] = []
            trk_items: list[tuple[str, str]] = []
            self.length = self.MAX_API_PAGES

            listing_sem = asyncio.Semaphore(2)

            async def _fetch_api_page(page_num: int):
                async with listing_sem:
                    url = f"{base_api}?per_page=50&page={page_num}"
                    return await self._http_get(url, use_cloudscraper=True, timeout=20)

            page_tasks = [_fetch_api_page(page) for page in range(1, self.MAX_API_PAGES + 1)]
            results = await asyncio.gather(*page_tasks, return_exceptions=True)
            for i, resp in enumerate(results):
                self.progress = i + 1
                try:
                    if isinstance(resp, Exception):
                        continue
                    if not resp or resp.status_code != 200:
                        continue

                    posts = json.loads(resp.text)
                    if not isinstance(posts, list) or not posts:
                        continue

                    for post in posts:
                        content_html = post.get("content", {}).get("rendered", "")
                        post_title = (
                            post.get("title", {}).get("rendered", "") or "Unknown"
                        )

                        soup = self.parse_html(content_html)
                        links = soup.select("a[href]")

                        for link in links:
                            href = link.get("href", "")
                            if not href or href in seen_hrefs:
                                continue

                            title = link.get_text(strip=True)
                            if len(title) < 10:
                                title = post_title
                            if len(title) < 3:
                                title = "Unknown"
                            title = title[:200]

                            normalized = Course.normalize_link(href)
                            if is_udemy_course_url(href) or is_udemy_course_url(
                                normalized
                            ):
                                seen_hrefs.add(href)
                                course_href = (
                                    href if is_udemy_course_url(href) else normalized
                                )
                                direct_items.append((title, course_href))
                            elif is_trk_udemy_url(href):
                                seen_hrefs.add(href)
                                trk_items.append((title, href))
                except Exception:
                    continue

            seen_urls: set[str] = set()

            def _append_resolved(title: str, resolved: str) -> None:
                if not title or not resolved:
                    return
                normalized = Course.normalize_link(resolved)
                if not normalized or normalized in seen_urls:
                    return
                if not is_udemy_course_url(normalized):
                    return
                prev = len(self.data)
                self.append_to_list(title[:200], resolved)
                if len(self.data) > prev:
                    seen_urls.add(normalized)

            for title, href in direct_items:
                if len(self.data) >= self.MAX_COURSES:
                    break
                _append_resolved(title, href)

            async def _resolve_one(href: str, title: str):
                resolved = await self._resolve_trk_redirect(href)
                return title, resolved

            local_trk_sem = asyncio.Semaphore(2)
            scheduled_trk = trk_items[: self.MAX_TRK_HTTP]
            chunk_size = self.DETAIL_BATCH_SIZE
            for i in range(0, len(scheduled_trk), chunk_size):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = scheduled_trk[i : i + chunk_size]
                detail_tasks = [
                    self._run_detail_task(local_trk_sem, _resolve_one, href, title)
                    for title, href in chunk
                ]
                results_list = await asyncio.gather(
                    *detail_tasks, return_exceptions=True
                )
                for results in results_list:
                    if len(self.data) >= self.MAX_COURSES:
                        break
                    if isinstance(results, Exception):
                        continue
                    if not results:
                        continue
                    title, resolved = results
                    _append_resolved(title, resolved)

            logger.info(
                f"  Interview Gig: REST API found {len(self.data)} unique courses"
            )
        except Exception:
            self.error = traceback.format_exc()


class UdemyXpertScraper(Scraper):
    """UdemyXpert (udemyxpert.com) — sitemap-based scraper.
    Parses sitemap.xml for course URLs, then fetches detail pages
    to extract direct Udemy links with coupon codes.
    """

    MAX_COURSES: int = 500
    CANDIDATE_BUFFER: int = 300
    DETAIL_BATCH_SIZE: int = 10

    @property
    def site_name(self) -> str:
        return "UdemyXpert"

    @property
    def code_name(self) -> str:
        return "ux"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  UdemyXpert: Fetching sitemap...")
            self.length = 1  # Sitemap fetch
            resp = await self._http_get_resilient(
                "https://udemyxpert.com/sitemap.xml", timeout=20, use_robots_circuit=True
            )
            self.progress = 1
            if not resp or resp.status_code != 200:
                return

            course_urls = re.findall(
                r"<loc>(https://udemyxpert\.com/courses/[^<]+)</loc>", resp.text
            )
            if not course_urls:
                return

            self.length = len(course_urls)
            self.progress = 0
            logger.info(f"  UdemyXpert: Found {len(course_urls)} courses in sitemap")

            seen: set[str] = set()

            async def _fetch_detail(page_url: str):
                try:
                    page = await self._http_get_resilient(page_url, timeout=15)
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    hrefs = re.findall(
                        r'href=["\'](https?://[^"\']+)["\']',
                        text,
                    )
                    quoted = re.findall(
                        r'["\'](https?://[^"\']+)["\']',
                        text,
                    )
                    matches = list(dict.fromkeys(hrefs + quoted))
                    course_urls = []
                    for m in matches:
                        lower = m.lower()
                        if any(
                            ext in lower
                            for ext in (".jpg", ".png", ".jpeg", ".webp", ".gif", ".svg")
                        ):
                            continue
                        if is_udemy_course_url(m):
                            course_urls.append(m)
                    if not course_urls:
                        return None, None
                    udemy_url = next(
                        (u for u in course_urls if "couponCode=" in u),
                        course_urls[0],
                    )

                    # Extract title from meta tags
                    title = None
                    og_match = re.search(
                        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                        text,
                    )
                    if og_match:
                        title = og_match.group(1)
                    else:
                        title_match = re.search(r"<title>([^<]+)</title>", text)
                        if title_match:
                            title = title_match.group(1)

                    if title:
                        # Clean title: remove "- Free Udemy Coupon | UdemyXpert" suffix
                        title = re.sub(
                            r"\s*[-|]\s*Free Udemy Coupon.*",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        ).strip()

                    return title or "Unknown", udemy_url
                except Exception:
                    return None, None

            urls_to_fetch = course_urls[: getattr(self, "CANDIDATE_BUFFER", 300)]
            self.length = len(urls_to_fetch)
            found = 0

            for i in range(0, len(urls_to_fetch), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = urls_to_fetch[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _fetch_detail, url)
                    for url in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen:
                            seen.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(urls_to_fetch))

            logger.info(f"  UdemyXpert: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CoursesityScraper(Scraper):
    """Coursesity (coursesity.com) — Transfer State SSR JSON + tiered DOM fallback scraper.
    Extracts direct Udemy course URLs and metadata from Angular Universal TransferState
    script tags (app-root-state / serverApp-state / coursesity-state).
    Falls back to DOM-based /course-detail/ crawling when SSR state is absent.
    """

    MAX_COURSES: int = 500
    COURSES_PER_PAGE: int = 15
    MAX_LISTING_PAGES: int = 205
    LISTING_CONCURRENCY: int = 2
    LISTING_ENDPOINT: str = "https://coursesity.com/provider/free/udemy-courses"
    DETAIL_BATCH_SIZE: int = 10

    @property
    def site_name(self) -> str:
        return "Coursesity"

    @property
    def code_name(self) -> str:
        return "cs"

    @staticmethod
    def _sanitize_angular_entities(raw_text: str) -> str:
        """Decodes Angular SSR entity tokens into valid JSON characters."""
        if not raw_text:
            return ""
        entity_map = {
            "&q;": '"',
            "&quot;": '"',
            "&a;": "&",
            "&amp;": "&",
            "&s;": "'",
            "&#39;": "'",
            "&l;": "<",
            "&lt;": "<",
            "&g;": ">",
            "&gt;": ">",
            "&b;": "\\",
        }
        text = raw_text
        for entity, char in entity_map.items():
            text = text.replace(entity, char)
        return html.unescape(text)

    @staticmethod
    def _find_courses_and_count_in_state(
        data: Any,
    ) -> tuple[list[dict[str, Any]], Optional[int]]:
        """DFS traversal to locate course list and totalCount in Angular TransferState."""
        if not isinstance(data, (dict, list)):
            return [], None

        total_count: Optional[int] = None
        courses: list[dict[str, Any]] = []

        if isinstance(data, list):
            if data and isinstance(data[0], dict) and any(k in data[0] for k in ("url", "course_url", "link", "udemy_url", "title", "heading", "name")):
                return data, None

        if isinstance(data, dict):
            if "COURSE_LIST" in data and isinstance(data["COURSE_LIST"], dict):
                cl = data["COURSE_LIST"]
                raw_count = cl.get("totalCount")
                if raw_count is not None:
                    try:
                        total_count = int(raw_count)
                    except (ValueError, TypeError):
                        pass
                cd = cl.get("courseData")
                if isinstance(cd, list):
                    courses = cd

            if courses:
                return courses, total_count

        def _dfs(node: Any):
            nonlocal total_count, courses
            if isinstance(node, dict):
                if total_count is None:
                    for count_key in ("totalCount", "totalCourses", "total_count", "count", "total"):
                        if count_key in node:
                            try:
                                total_count = int(node[count_key])
                                break
                            except (ValueError, TypeError):
                                pass
                for k, v in node.items():
                    if k in ("courseData", "courses", "items", "results") and isinstance(v, list):
                        if v and isinstance(v[0], dict) and any(key in v[0] for key in ("url", "course_url", "link", "udemy_url", "title", "heading", "name", "slug")):
                            courses = v
                    _dfs(v)
            elif isinstance(node, list):
                for item in node:
                    _dfs(item)

        _dfs(data)
        return courses, total_count

    def _parse_transfer_state(
        self, html_text: str
    ) -> tuple[list[dict[str, Any]], Optional[int]]:
        """Parses and sanitizes script#app-root-state Angular TransferState payload."""
        if not html_text:
            return [], None

        script_match = re.search(
            r'<script\s+[^>]*id=["\'](?:app-root-state|serverApp-state|coursesity-state)["\'][^>]*>(.*?)</script>',
            html_text,
            re.DOTALL | re.IGNORECASE,
        )
        if not script_match:
            return [], None

        raw_state = script_match.group(1).strip()
        if not raw_state:
            return [], None

        sanitized_state = self._sanitize_angular_entities(raw_state)
        try:
            state_json = json.loads(sanitized_state, strict=False)
            return self._find_courses_and_count_in_state(state_json)
        except Exception:
            return [], None

    @staticmethod
    def _unwrap_udemy_url(raw_url: str) -> Optional[str]:
        """Extracts destination Udemy course URL from tracking / redirect URLs statically."""
        if not raw_url:
            return None

        unquoted_raw = urllib.parse.unquote(raw_url)
        if is_udemy_course_url(unquoted_raw):
            return Course.normalize_link(unquoted_raw)

        try:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            for param in ("u", "url", "target", "redirect", "dest", "murl"):
                if param in qs and qs[param]:
                    val = qs[param][0]
                    candidate = urllib.parse.unquote(urllib.parse.unquote(val))
                    if is_udemy_course_url(candidate):
                        return Course.normalize_link(candidate)
        except Exception:
            pass

        generic_url_match = re.search(
            r'(https?%3A%2F%2F[^&"\'\s<>]+)', raw_url, re.IGNORECASE
        )
        if generic_url_match:
            candidate = urllib.parse.unquote(urllib.parse.unquote(generic_url_match.group(1)))
            if is_udemy_course_url(candidate):
                return Course.normalize_link(candidate)

        return None

    @staticmethod
    def _clean_title(title: str, fallback_slug: str = "") -> str:
        """Cleans title and strips branding suffixes."""
        if not title and fallback_slug:
            slug_clean = fallback_slug.split("/")[-1].replace("-", " ").title()
            return slug_clean
        cleaned = re.sub(
            r"\s*[-|]\s*Free Online Course.*",
            "",
            title or "",
            flags=re.IGNORECASE,
        ).strip()
        cleaned = html.unescape(cleaned)
        if not cleaned or cleaned.lower() in ("enroll now", "get course"):
            if fallback_slug:
                slug_clean = fallback_slug.split("/")[-1].replace("-", " ").title()
                return slug_clean
        return cleaned or "Unknown"

    async def _process_dom_fallback(
        self,
        html_text: str,
        detail_semaphore: asyncio.Semaphore,
        seen: set[str],
    ) -> int:
        """Tiered fallback: Crawls /course-detail/ links when SSR TransferState is absent."""
        links = re.findall(r'href="(/course-detail/[^"]+)"', html_text)
        unique_links = list(dict.fromkeys(links))
        if not unique_links:
            return 0

        async def _fetch_detail(rel_path: str):
            detail_url = urllib.parse.urljoin(self.LISTING_ENDPOINT, rel_path)
            try:
                page = await self.http.get(detail_url, use_cloudscraper=True, timeout=15)
                if not page or page.status_code != 200:
                    return None, None
                text = page.text or ""
                matches = re.findall(r'["\'](https?://[^"\']+)["\']', text)
                udemy_url = None
                for m in matches:
                    if any(ext in m.lower() for ext in (".jpg", ".png", ".jpeg", ".webp", ".svg")):
                        continue
                    if is_udemy_course_url(m):
                        udemy_url = m
                        break
                    unwrapped = self._unwrap_udemy_url(m)
                    if unwrapped and is_udemy_course_url(unwrapped):
                        udemy_url = unwrapped
                        break

                if not udemy_url:
                    return None, None

                title = None
                og_match = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', text)
                if og_match:
                    title = og_match.group(1)
                else:
                    title_match = re.search(r"<title>([^<]+)</title>", text)
                    if title_match:
                        title = title_match.group(1)

                return self._clean_title(title or "", rel_path), udemy_url
            except Exception:
                return None, None

        added = 0
        for i in range(0, len(unique_links), getattr(self, "DETAIL_BATCH_SIZE", 10)):
            if len(self.data) >= self.MAX_COURSES:
                break
            chunk = unique_links[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
            chunk_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, path)
                for path in chunk
            ]
            results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or not res:
                    continue
                title, link = res
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        added += 1
                        if len(self.data) >= self.MAX_COURSES:
                            break
        return added

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        """Scrapes Coursesity via single-phase Angular TransferState extraction."""
        try:
            logger.info("  Coursesity: Initializing Angular SSR TransferState scraper...")
            seen: set[str] = set()

            p1_resp = await self._http_get(
                f"{self.LISTING_ENDPOINT}?page=1", use_cloudscraper=True, timeout=15
            )
            if not p1_resp or p1_resp.status_code != 200:
                logger.warning("  Coursesity: Failed to load page 1")
                return

            p1_courses, total_count = self._parse_transfer_state(p1_resp.text)
            if total_count and total_count > 0:
                calculated_pages = (total_count + self.COURSES_PER_PAGE - 1) // self.COURSES_PER_PAGE
                max_pages = min(calculated_pages, self.MAX_LISTING_PAGES)
            else:
                max_pages = self.MAX_LISTING_PAGES

            self.length = max_pages
            self.progress = 1

            def _extract_course(c: dict):
                raw_url = c.get("course_url") or c.get("url") or c.get("link") or c.get("udemy_url") or ""
                raw_title = c.get("title") or c.get("heading") or c.get("name") or ""
                slug = c.get("urlSlug") or c.get("slug") or ""
                title = self._clean_title(raw_title, slug)
                return raw_url, title

            if p1_courses:
                for c in p1_courses:
                    if len(self.data) >= self.MAX_COURSES:
                        break
                    raw_url, title = _extract_course(c)
                    udemy_link = self._unwrap_udemy_url(raw_url)
                    if not udemy_link and is_trk_udemy_url(raw_url):
                        udemy_link = await self._resolve_trk_redirect(raw_url)
                    if udemy_link and is_udemy_course_url(udemy_link):
                        normalized = Course.normalize_link(udemy_link)
                        if normalized not in seen:
                            seen.add(normalized)
                            self.append_to_list(title[:200], udemy_link)
            else:
                await self._process_dom_fallback(p1_resp.text, detail_semaphore, seen)

            if len(self.data) >= self.MAX_COURSES or max_pages <= 1:
                logger.info(f"  Coursesity: Harvest complete with {len(self.data)} courses")
                return

            listing_sem = asyncio.Semaphore(min(self.LISTING_CONCURRENCY, 2))

            async def _fetch_page(page_num: int):
                async with listing_sem:
                    url = f"{self.LISTING_ENDPOINT}?page={page_num}"
                    try:
                        resp = await self._http_get(url, use_cloudscraper=True, timeout=15)
                        if not resp or resp.status_code != 200:
                            return None
                        return resp.text
                    except Exception:
                        return None

            page_tasks = [_fetch_page(p) for p in range(2, max_pages + 1)]
            results = await asyncio.gather(*page_tasks, return_exceptions=True)
            for i, page_html in enumerate(results):
                if len(self.data) >= self.MAX_COURSES:
                    break
                self.progress = i + 2
                if not page_html or isinstance(page_html, Exception):
                    continue

                courses, _ = self._parse_transfer_state(page_html)
                if courses:
                    for c in courses:
                        if len(self.data) >= self.MAX_COURSES:
                            break
                        raw_url, title = _extract_course(c)
                        udemy_link = self._unwrap_udemy_url(raw_url)
                        if not udemy_link and is_trk_udemy_url(raw_url):
                            udemy_link = await self._resolve_trk_redirect(raw_url)
                        if udemy_link and is_udemy_course_url(udemy_link):
                            normalized = Course.normalize_link(udemy_link)
                            if normalized not in seen:
                                seen.add(normalized)
                                self.append_to_list(title[:200], udemy_link)
                else:
                    await self._process_dom_fallback(page_html, detail_semaphore, seen)

            logger.info(f"  Coursesity: Found {len(self.data)} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CourseFolderScraper(Scraper):
    """Course Folder (coursefolder.net) — paginated listing + detail page scraper.
    Free Udemy coupons at /free-udemy-coupon.php.
    Each listing page has ~50 courses; detail pages contain direct
    Udemy links with coupon codes in anchor tags.
    """

    MAX_COURSES: int = 500
    MAX_PAGES: int = 18
    CANDIDATE_BUFFER: int = 750
    DETAIL_BATCH_SIZE: int = 10

    @property
    def site_name(self) -> str:
        return "Course Folder"

    @property
    def code_name(self) -> str:
        return "cf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_pages = getattr(self, "MAX_PAGES", 18)
            excluded_paths = {
                "",
                "live-free-udemy-coupon.php",
                "udemy-coupon-codes.php",
            }

            detail_urls: list[str] = []

            self.length = max_pages
            for page_num in range(0, max_pages):
                self.progress = page_num + 1
                url = f"https://coursefolder.net/free-udemy-coupon.php?page={page_num}"
                try:
                    resp = await self._http_get(url, use_cloudscraper=True, timeout=15)
                    if not resp or resp.status_code != 200:
                        break

                    text = resp.text
                    soup = BeautifulSoup(text, "lxml")

                    page_urls: set[str] = set()
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if not href.startswith("https://coursefolder.net/"):
                            continue
                        path = href.replace("https://coursefolder.net/", "")
                        if path in excluded_paths:
                            continue
                        if any(p in path for p in ["category", "page", ".php"]):
                            continue
                        parent = a.find_parent()
                        if parent and "udemycdn" in str(parent):
                            page_urls.add(href)

                    if not page_urls:
                        break

                    detail_urls.extend(sorted(page_urls))
                    if len(detail_urls) >= getattr(self, "CANDIDATE_BUFFER", 750):
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

            detail_urls = detail_urls[: getattr(self, "CANDIDATE_BUFFER", 750)]
            self.length = len(detail_urls)
            self.progress = 0
            logger.info(
                f"  Course Folder: Found {len(detail_urls)} detail URLs to fetch"
            )

            async def _fetch_detail(detail_url: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    # Extract Udemy URL with coupon from anchor tags
                    matches = re.findall(
                        r'href="(https?://[^"]+)"',
                        text,
                    )
                    udemy_url = None
                    for m in matches:
                        if "couponCode=" in m and is_udemy_course_url(m):
                            udemy_url = m
                            break

                    if not udemy_url:
                        return None, None

                    # Extract title from page
                    title = None
                    title_match = re.search(r"<title>([^<]+)</title>", text)
                    if title_match:
                        title = title_match.group(1)
                        # Clean: "[100% Off] Title - Course Folder"
                        title = re.sub(
                            r"^\s*\[100%\s*Off\]\s*",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        )
                        title = re.sub(
                            r"\s*[-|]\s*Course\s*Folder\s*$",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        )
                        title = title.strip()

                    return title or "Unknown", udemy_url
                except Exception:
                    return None, None

            found = 0
            for i in range(0, len(detail_urls), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = detail_urls[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _fetch_detail, url)
                    for url in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen:
                            seen.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(detail_urls))

            logger.info(f"  Course Folder: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CouponamiScraper(Scraper):
    """Couponami (couponami.com) — sitemap-based scraper.
    Uses WordPress post sitemaps to get all course URLs, then fetches
    /go/{slug} redirect pages which embed direct Udemy links with coupons.
    """

    MAX_COURSES: int = 500
    CANDIDATE_BUFFER: int = 300
    DETAIL_BATCH_SIZE: int = 10

    @property
    def site_name(self) -> str:
        return "Couponami"

    @property
    def code_name(self) -> str:
        return "ca"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()

            # Step 1: Fetch sitemaps to collect course slugs
            sitemap_urls = [
                "https://www.couponami.com/post-sitemap1.xml",
                "https://www.couponami.com/post-sitemap2.xml",
                "https://www.couponami.com/post-sitemap3.xml",
                "https://www.couponami.com/post-sitemap4.xml",
            ]

            detail_urls: list[str] = []
            self.length = len(sitemap_urls)
            for i, sitemap_url in enumerate(sitemap_urls):
                self.progress = i + 1
                try:
                    resp = await self._http_get(
                        sitemap_url, use_cloudscraper=True, timeout=20
                    )
                    if not resp or resp.status_code != 200:
                        continue

                    locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
                    for loc in locs:
                        path = loc.replace("https://www.couponami.com/", "").replace(
                            "http://www.couponami.com/", ""
                        )
                        # Must be a course URL: category/slug with single slash
                        if (
                            path
                            and path.count("/") == 1
                            and not path.startswith(
                                (
                                    "category/",
                                    "language/",
                                    "vendor/",
                                    "go/",
                                    "page/",
                                    "feed",
                                )
                            )
                        ):
                            slug = path.split("/")[1]
                            go_url = f"https://www.couponami.com/go/{slug}"
                            detail_urls.append(go_url)

                    if len(detail_urls) >= getattr(self, "CANDIDATE_BUFFER", 750):
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

            detail_urls = detail_urls[: getattr(self, "CANDIDATE_BUFFER", 750)]
            self.length = len(detail_urls)
            self.progress = 0
            logger.info(f"  Couponami: Found {len(detail_urls)} /go/ URLs to fetch")

            # Step 2: Fetch /go/ pages concurrently
            async def _fetch_go(go_url: str):
                try:
                    page = await self.http.get(
                        go_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    # Extract Udemy URL
                    matches = re.findall(
                        r'["\'](https?://[^"\']+)["\']',
                        text,
                    )
                    udemy_url = None
                    for m in matches:
                        if ".jpg" in m or ".png" in m:
                            continue
                        if is_udemy_course_url(m):
                            udemy_url = m
                            break

                    if not udemy_url:
                        return None, None

                    # Extract title from og:title
                    title = None
                    og_match = re.search(
                        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                        text,
                    )
                    if og_match:
                        title = og_match.group(1)
                    else:
                        title_match = re.search(r"<title>([^<]+)</title>", text)
                        if title_match:
                            title = title_match.group(1)
                            # Clean "Enroll Course - Title - Free Udemy Courses - CouponAmI"
                            title = re.sub(
                                r"^Enroll\s*Course\s*[-|]\s*",
                                "",
                                title,
                                flags=re.IGNORECASE,
                            )
                            title = re.sub(
                                r"\s*[-|]\s*Free\s*Udemy\s*Courses.*",
                                "",
                                title,
                                flags=re.IGNORECASE,
                            )
                            title = title.strip()

                    return title or "Unknown", udemy_url
                except Exception:
                    return None, None

            go_semaphore = asyncio.Semaphore(2)
            found = 0
            for i in range(0, len(detail_urls), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = detail_urls[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(go_semaphore, _fetch_go, url)
                    for url in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen:
                            seen.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(detail_urls))

            logger.info(f"  Couponami: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class KorshubScraper(Scraper):
    """Korshub (korshub.com) — paginated listing + detail page scraper.
    Free/discounted Udemy courses at /free-courses?platform=UDEMY (and /courses).
    Listing cards are /courses/{slug}. Detail pages yield Next.js SSR Flight
    payloads with is_udemy_course_url hrefs or same-origin /go/{uuid} hops.
    """

    MAX_COURSES: int = 500
    MAX_PAGES: int = 80
    CANDIDATE_BUFFER: int = 700
    DETAIL_BATCH_SIZE: int = 10
    LISTING_ENDPOINT: str = "https://korshub.com/free-courses"

    GO_NETLOCS = frozenset({"korshub.com", "www.korshub.com"})
    GO_PATH_RE = re.compile(r"^/go/[A-Za-z0-9_-]+$")

    @property
    def site_name(self) -> str:
        return "Korshub"

    @property
    def code_name(self) -> str:
        return "kh"

    def _listing_detail_url(self, href: str) -> Optional[str]:
        candidate = urllib.parse.urljoin("https://korshub.com/", href)
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower().split(":")[0]
        if host not in self.GO_NETLOCS:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2 or parts[0] != "courses" or not parts[1]:
            return None
        scheme = parsed.scheme or "https"
        return f"{scheme}://{host}/courses/{parts[1]}"

    def _allowed_go_hop(self, href: str, base: str) -> Optional[str]:
        candidate = urllib.parse.urljoin(base or "https://korshub.com/", href)
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower().split(":")[0]
        if host not in self.GO_NETLOCS:
            return None
        if not self.GO_PATH_RE.fullmatch(parsed.path or ""):
            return None
        scheme = parsed.scheme or "https"
        return f"{scheme}://{host}{parsed.path}"

    def _allowed_extra_go_hop(self, location: str) -> Optional[str]:
        """Same-origin www↔apex /go/{uuid} Location for one extra hop. Host is not rewritten."""
        if not location:
            return None
        try:
            parsed = urllib.parse.urlparse(location)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https"):
            return None
        netloc = parsed.netloc or ""
        if parsed.username is not None or parsed.password is not None or "@" in netloc:
            return None
        host = (parsed.hostname or "").lower()
        if host not in self.GO_NETLOCS:
            return None
        if not self.GO_PATH_RE.fullmatch(parsed.path or ""):
            return None
        return f"{parsed.scheme}://{host}{parsed.path}"

    def _extract_udemy_url_from_text(self, text: str) -> Optional[str]:
        """Extract direct Udemy course URL from JSON-LD schema, Next.js Flight SSR payload, or page text."""
        if not text:
            return None
        json_match = re.search(
            r'"url":\s*"(https://[^"]+/course/[^"]+)"', text
        )
        if json_match:
            url = json_match.group(1).replace(r"\/", "/")
            if is_udemy_course_url(url):
                return url

        cleaned = (
            text.replace(r"\u0026", "&")
            .replace(r"\\u0026", "&")
            .replace(r"\u002f", "/")
            .replace(r"\u002F", "/")
            .replace(r"\u003d", "=")
            .replace(r"\u003D", "=")
            .replace(r"\u003f", "?")
            .replace(r"\u003F", "?")
            .replace(r"\/", "/")
            .replace(r'\"', '"')
        )
        cleaned = html.unescape(cleaned)
        matches = re.findall(
            r'https?://[A-Za-z0-9_.-]+/course/[A-Za-z0-9_.-]+/[^"\'\s\\<>]*',
            cleaned,
        )
        for m in matches:
            m = m.rstrip(r"\//.,;")
            if is_udemy_course_url(m):
                return m
        return None

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_pages = getattr(self, "MAX_PAGES", 80)
            batch_size = getattr(self, "BATCH_SIZE", 6)
            buffer_limit = min(
                getattr(self, "CANDIDATE_BUFFER", 700), max(self.MAX_COURSES * 8, 40)
            )

            detail_urls: list[str] = []

            # Step 1: Fetch listing pages concurrently in batches
            self.length = max_pages
            stop_pagination = False
            for start_page in range(1, max_pages + 1, batch_size):
                end_page = min(start_page + batch_size, max_pages + 1)
                page_tasks = [
                    self._http_get(
                        f"{self.LISTING_ENDPOINT}?page={p}&platform=UDEMY",
                        use_cloudscraper=True,
                        timeout=15,
                        retry_403=True,
                    )
                    for p in range(start_page, end_page)
                ]
                responses = await asyncio.gather(*page_tasks, return_exceptions=True)

                for p, resp in zip(range(start_page, end_page), responses):
                    self.progress = p
                    if isinstance(resp, Exception):
                        resp = None
                    # Fallback to general /courses if /free-courses is unavailable
                    if (not resp or getattr(resp, "status_code", None) != 200) and p == 1:
                        fallback_url = f"https://korshub.com/courses?page={p - 1}"
                        resp = await self._http_get(
                            fallback_url,
                            use_cloudscraper=True,
                            timeout=15,
                            retry_403=True,
                        )

                    if not resp or getattr(resp, "status_code", None) != 200:
                        if p <= 1:
                            stop_pagination = True
                            break
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")
                    page_urls: set[str] = set()
                    for a in soup.find_all("a", href=True):
                        detail = self._listing_detail_url(a["href"])
                        if detail:
                            page_urls.add(detail)

                    if not page_urls:
                        stop_pagination = True
                        break

                    detail_urls.extend(sorted(page_urls))
                    if len(detail_urls) >= buffer_limit:
                        stop_pagination = True
                        break

                if stop_pagination:
                    break

            if not detail_urls:
                return

            detail_urls = detail_urls[:buffer_limit]
            self.length = len(detail_urls)
            self.progress = 0
            logger.info(f"  Korshub: Found {len(detail_urls)} detail URLs to fetch")

            # Step 2: Fetch detail pages concurrently
            async def _fetch_detail(detail_url: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    # 1. Fast path: Next.js Flight SSR payload unescaping
                    udemy_url = self._extract_udemy_url_from_text(text)

                    # 2. DOM extraction fallback
                    if not udemy_url:
                        soup = self.parse_html(text)
                        for a in soup.find_all("a", href=True):
                            href = a.get("href", "")
                            if is_udemy_course_url(href):
                                udemy_url = href
                                break

                    # 3. /go/ redirect hop fallback
                    if not udemy_url:
                        soup = self.parse_html(text) if "soup" not in locals() else soup
                        go_url = None
                        for a in soup.find_all("a", href=True):
                            go_url = self._allowed_go_hop(a.get("href", ""), detail_url)
                            if go_url:
                                break
                        if go_url:
                            hop_kwargs = {
                                "use_cloudscraper": True,
                                "allow_redirects": False,
                                "follow_redirects": False,
                                "raise_for_status": False,
                                "attempts": 1,
                                "timeout": 15,
                            }
                            hop = await self.http.get(go_url, **hop_kwargs)
                            if hop and hop.status_code in (301, 302, 307, 308):
                                location = (
                                    hop.headers.get("location")
                                    or hop.headers.get("Location")
                                    or ""
                                )
                                location = urllib.parse.urljoin(go_url, location)
                                if is_udemy_course_url(location):
                                    udemy_url = location
                                elif is_trk_udemy_url(location):
                                    udemy_url = await self._resolve_trk_redirect(
                                        location
                                    )
                                else:
                                    extra_url = self._allowed_extra_go_hop(location)
                                    if extra_url:
                                        hop = await self.http.get(
                                            extra_url, **hop_kwargs
                                        )
                                        if hop and hop.status_code in (
                                            301,
                                            302,
                                            307,
                                            308,
                                        ):
                                            location = (
                                                hop.headers.get("location")
                                                or hop.headers.get("Location")
                                                or ""
                                            )
                                            location = urllib.parse.urljoin(
                                                extra_url, location
                                            )
                                            if is_udemy_course_url(location):
                                                udemy_url = location
                                            elif is_trk_udemy_url(location):
                                                udemy_url = (
                                                    await self._resolve_trk_redirect(
                                                        location
                                                    )
                                                )

                    if not udemy_url:
                        return None, None

                    # Extract title from page
                    title = None
                    title_match = re.search(r"<title>([^<]+)</title>", text)
                    if title_match:
                        title = title_match.group(1)
                        # Clean: "100% off coupon for Title | Korshub"
                        title = re.sub(
                            r"^\s*(?:100%\s*off\s*coupon\s*for|FREE\s*coupon\s*for)\s*",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        )
                        title = re.sub(
                            r"\s*[-|]\s*Korshub\s*$",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        )
                        title = re.sub(
                            r"\s*January\s*\d{4}\s*\|\s*Korshub\s*$",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        )
                        title = title.strip()

                    return title or "Unknown", udemy_url
                except Exception:
                    return None, None

            found = 0
            for i in range(0, len(detail_urls), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = detail_urls[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _fetch_detail, url)
                    for url in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen:
                            seen.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(detail_urls))

            logger.info(f"  Korshub: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class UdemyFreebiesScraper(Scraper):
    """UdemyFreebies (udemyfreebies.com) — paginated listing + /out/ redirect scraper.
    Listing pages at /free-udemy-courses/{page} contain course cards.
    Each card links to /free-udemy-course/{slug}.
    The /out/{slug} endpoint returns a 302 redirect to the actual Udemy URL
    with an embedded coupon code.
    """

    MAX_COURSES: int = 500
    COURSES_PER_PAGE: int = 12
    MAX_LISTING_PAGES: int = 85
    LISTING_CONCURRENCY: int = 2
    LISTING_ENDPOINT: str = "https://www.udemyfreebies.com/free-udemy-courses"
    DETAIL_BATCH_SIZE: int = 10

    UDEMY_RESERVED_SLUGS = frozenset({
        "course", "courses", "cart", "join", "user", "topic", "topics",
        "certificate", "support", "terms", "privacy", "affiliate",
        "instructor", "teaching", "mobile", "gift", "featured", "api",
        "organization", "home", "search", "explore", "collection", "category",
    })

    @property
    def site_name(self) -> str:
        return "UdemyFreebies"

    @property
    def code_name(self) -> str:
        return "uf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_slugs: set[str] = set()
            max_pages = getattr(self, "MAX_LISTING_PAGES", 50)

            # Step 1: Fetch listing pages concurrently to collect slugs and titles
            logger.info("  UdemyFreebies: Fetching listing pages...")
            listing_results: list[tuple[str, str]] = []

            self.length = max_pages
            listing_sem = asyncio.Semaphore(min(getattr(self, "LISTING_CONCURRENCY", 2), 2))

            async def _fetch_page(page_num: int):
                async with listing_sem:
                    url = f"{self.LISTING_ENDPOINT}/{page_num}"
                    try:
                        resp = await self._http_get(url, use_cloudscraper=True, timeout=15)
                        if not resp or resp.status_code != 200:
                            return []
                        soup = self.parse_html(resp.content)
                        coupon_names = soup.find_all("div", class_="coupon-name")
                        page_items = []
                        for name_div in coupon_names:
                            a = name_div.find("a", href=True)
                            if not a:
                                continue
                            href = a.get("href", "")
                            if "/free-udemy-course/" not in href:
                                continue
                            parts = href.split("/free-udemy-course/")
                            if len(parts) < 2:
                                continue
                            slug = parts[-1].split("?")[0].split("#")[0].rstrip("/")
                            if not slug:
                                continue
                            title = a.get_text(strip=True)
                            if not title or len(title) < 3:
                                continue
                            page_items.append((slug, title))
                        return page_items
                    except Exception:
                        return []

            page_tasks = [_fetch_page(p) for p in range(1, max_pages + 1)]
            results = await asyncio.gather(*page_tasks, return_exceptions=True)
            for i, items in enumerate(results):
                self.progress = i + 1
                if not items or isinstance(items, Exception):
                    continue
                for slug, title in items:
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        listing_results.append((slug, title))
                if len(listing_results) >= self.MAX_COURSES:
                    break

            if not listing_results:
                logger.warning("  UdemyFreebies: No courses found in listings")
                return

            listing_results = listing_results[: self.MAX_COURSES]
            self.length = len(listing_results)
            self.progress = 0
            logger.info(
                f"  UdemyFreebies: Found {len(listing_results)} unique slugs, resolving /out/ redirects..."
            )

            # Step 2: Resolve /out/{slug} redirects concurrently
            seen_urls: set[str] = set()

            async def _resolve_out(slug: str, title: str):
                try:
                    out_url = f"https://www.udemyfreebies.com/out/{slug}"
                    resp = await self.http.get(
                        out_url,
                        use_cloudscraper=True,
                        allow_redirects=False,
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=2,
                        timeout=15,
                    )
                    if not resp or resp.status_code not in (301, 302, 307, 308):
                        return None, None

                    location = resp.headers.get("location") or resp.headers.get(
                        "Location"
                    ) or ""
                    if not location:
                        return None, None
                    location = urllib.parse.urljoin(out_url, location)
                    parsed = urllib.parse.urlparse(location)
                    if parsed.netloc.lower() in {"udemy.com", "www.udemy.com"}:
                        parts = [p for p in (parsed.path or "").split("/") if p]
                        if (
                            len(parts) == 1
                            and parts[0].lower() not in self.UDEMY_RESERVED_SLUGS
                            and re.fullmatch(r"[A-Za-z0-9_-]+", parts[0])
                        ):
                            coupon = (
                                urllib.parse.parse_qs(parsed.query).get(
                                    "couponCode"
                                )
                                or [""]
                            )[0]
                            if coupon:
                                location = (
                                    "https://www.udemy.com/course/"
                                    f"{parts[0]}/?couponCode="
                                    f"{urllib.parse.quote(coupon)}"
                                )
                    if is_udemy_course_url(location):
                        return title, location
                    if is_trk_udemy_url(location):
                        resolved = await self._resolve_trk_redirect(location)
                        if resolved:
                            return title, resolved
                    return None, None
                except Exception:
                    return None, None

            found = 0
            for i in range(0, len(listing_results), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = listing_results[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _resolve_out, slug, title)
                    for slug, title in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen_urls:
                            seen_urls.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(listing_results))

            logger.info(f"  UdemyFreebies: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class IDownloadCouponScraper(Scraper):
    """iDownloadCoupon (idownloadcoupon.com) — WooCommerce Store REST API + HTML scraper.
    Primary extraction uses WooCommerce Store REST API:
    GET https://idownloadcoupon.com/wp-json/wc/store/v1/products?per_page=50&page={page}
    which yields structured product data (id, name, permalink, add_to_cart).
    Falls back gracefully to HTML product listing at /page/{n}/ if Store API is unavailable.
    Detail hop resolves /udemy/{id}/ redirects to Udemy course links.
    """

    MAX_COURSES: int = 500
    PER_PAGE: int = 50
    MAX_PAGES: int = 15
    LISTING_CONCURRENCY: int = 2
    BASE_URL: str = "https://idownloadcoupon.com"
    STORE_API_ENDPOINT: str = "https://idownloadcoupon.com/wp-json/wc/store/v1/products"
    DETAIL_BATCH_SIZE: int = 10

    @property
    def site_name(self) -> str:
        return "iDownloadCoupon"

    @property
    def code_name(self) -> str:
        return "idc"

    def _unwrap_direct_target(self, raw_url: str) -> Optional[str]:
        """Statically unwraps target Udemy URLs from query parameters without making network requests."""
        if not raw_url:
            return None
        unquoted = urllib.parse.unquote(raw_url)
        if is_udemy_course_url(unquoted):
            return Course.normalize_link(unquoted)
        try:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            for key in ("u", "url", "target", "redirect", "dest"):
                if key in qs and qs[key]:
                    candidate = urllib.parse.unquote(qs[key][0])
                    if is_udemy_course_url(candidate):
                        return Course.normalize_link(candidate)
        except Exception:
            pass
        return None

    async def _collect_store_api_products(self) -> tuple[list[tuple[str, str, Optional[str]]], bool]:
        """Collects courses via WooCommerce Store REST API."""
        logger.info("  iDownloadCoupon: Querying WooCommerce Store REST API...")
        products: list[tuple[str, str, Optional[str]]] = []
        seen_ids: set[str] = set()

        # Step 1: Probe page 1 safely
        p1_url = f"{self.STORE_API_ENDPOINT}?per_page={self.PER_PAGE}&page=1"
        try:
            p1_resp = await self.http.get(
                p1_url,
                use_cloudscraper=True,
                raise_for_status=False,
                attempts=1,
                timeout=15,
            )
        except Exception:
            p1_resp = None

        if not p1_resp or p1_resp.status_code != 200:
            logger.warning("  iDownloadCoupon: Store REST API probe failed, falling back to HTML")
            return [], False

        try:
            p1_data = None
            if hasattr(self.http, "safe_json"):
                p1_data = await self.http.safe_json(p1_resp, "idownloadcoupon_store_api")
            if p1_data is None:
                p1_data = json.loads(p1_resp.text)
            if not isinstance(p1_data, list) or not p1_data:
                return [], False
        except Exception:
            return [], False

        total_pages = self.MAX_PAGES
        headers = getattr(p1_resp, "headers", {}) or {}
        wp_pages_hdr = headers.get("X-WP-TotalPages") or headers.get("x-wp-totalpages")
        if wp_pages_hdr:
            try:
                total_pages = min(int(wp_pages_hdr), self.MAX_PAGES)
            except (ValueError, TypeError):
                total_pages = self.MAX_PAGES

        target_pages = min(total_pages, (self.MAX_COURSES + self.PER_PAGE - 1) // self.PER_PAGE + 1)
        self.length = target_pages
        self.progress = 1

        for item in p1_data:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id", "")).strip()
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            name = html.unescape(item.get("name", "").strip())
            cart_url = (item.get("add_to_cart") or {}).get("url", "")
            direct_url = self._unwrap_direct_target(cart_url)
            products.append((cid, name, direct_url))

        if len(products) >= self.MAX_COURSES or target_pages <= 1:
            return products, True

        api_sem = asyncio.Semaphore(min(self.LISTING_CONCURRENCY, 2))

        async def _fetch_store_page(page: int):
            async with api_sem:
                url = f"{self.STORE_API_ENDPOINT}?per_page={self.PER_PAGE}&page={page}"
                try:
                    resp = await self.http.get(
                        url,
                        use_cloudscraper=True,
                        raise_for_status=False,
                        attempts=2,
                        timeout=15,
                    )
                    if not resp:
                        return []
                    if resp.status_code == 400:
                        return []
                    if resp.status_code != 200:
                        return []
                    data = None
                    if hasattr(self.http, "safe_json"):
                        data = await self.http.safe_json(resp, "idownloadcoupon_store_api")
                    if data is None:
                        data = json.loads(resp.text)
                    if not isinstance(data, list):
                        return []
                    return data
                except Exception:
                    return []

        page_tasks = [_fetch_store_page(p) for p in range(2, target_pages + 1)]
        store_results = await asyncio.gather(*page_tasks, return_exceptions=True)
        for i, data in enumerate(store_results):
            self.progress = i + 2
            if not data or isinstance(data, Exception):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                cid = str(item.get("id", "")).strip()
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                name = html.unescape(item.get("name", "").strip())
                cart_url = (item.get("add_to_cart") or {}).get("url", "")
                direct_url = self._unwrap_direct_target(cart_url)
                products.append((cid, name, direct_url))
                if len(products) >= self.MAX_COURSES:
                    break
            if len(products) >= self.MAX_COURSES:
                break

        return products, True

    async def _collect_html_products(self) -> list[tuple[str, str, Optional[str]]]:
        """Fallback HTML scraper across /page/{n}/."""
        logger.info("  iDownloadCoupon: Ingesting courses via HTML fallback...")
        listing_results: list[tuple[str, str, Optional[str]]] = []
        seen_ids: set[str] = set()

        max_pages = self.MAX_PAGES
        self.length = max_pages
        local_listing_semaphore = asyncio.Semaphore(min(self.LISTING_CONCURRENCY, 2))

        async def fetch_page(page_num: int):
            async with local_listing_semaphore:
                url = f"{self.BASE_URL}/page/{page_num}/"
                return await self._http_get(url, use_cloudscraper=True, timeout=15)

        page_tasks = [fetch_page(p) for p in range(1, max_pages + 1)]
        html_results = await asyncio.gather(*page_tasks, return_exceptions=True)
        for i, resp in enumerate(html_results):
            self.progress = i + 1
            try:
                if not resp or isinstance(resp, Exception) or resp.status_code != 200:
                    continue

                soup = self.parse_html(resp.content)
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    match = re.search(r"/udemy/(\d+)/[^/]+/?$", href)
                    if not match:
                        continue

                    cid = match.group(1)
                    if cid in seen_ids:
                        continue
                    seen_ids.add(cid)

                    title = a.get_text(strip=True)
                    if not title or title.lower() in {"redeem offer", "udemy", "sale!"}:
                        continue
                    if len(title) < 3:
                        continue

                    listing_results.append((cid, title, None))

                if len(listing_results) >= self.MAX_COURSES:
                    break
            except Exception:
                continue

        return listing_results

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            products, success = await self._collect_store_api_products()
            if not success or not products:
                products = await self._collect_html_products()

            if not products:
                logger.warning("  iDownloadCoupon: No courses found in listings")
                return

            products = products[: self.MAX_COURSES]
            self.length = len(products)
            self.progress = 0
            logger.info(
                f"  iDownloadCoupon: Found {len(products)} courses, resolving detail hops..."
            )

            seen_urls: set[str] = set()

            # First pass: append items with statically resolved direct targets
            unresolved_items: list[tuple[str, str]] = []
            for cid, title, direct_url in products:
                if direct_url and is_udemy_course_url(direct_url):
                    norm = Course.normalize_link(direct_url)
                    if norm not in seen_urls:
                        seen_urls.add(norm)
                        self.append_to_list(title[:200], direct_url)
                        if len(self.data) >= self.MAX_COURSES:
                            break
                else:
                    unresolved_items.append((cid, title))

            if len(self.data) >= self.MAX_COURSES or not unresolved_items:
                logger.info(f"  iDownloadCoupon: Harvested {len(self.data)} courses")
                return

            async def _resolve_redeem(cid: str, title: str):
                try:
                    redeem_url = f"{self.BASE_URL}/udemy/{cid}/"
                    resp = await self.http.get(
                        redeem_url,
                        use_cloudscraper=True,
                        allow_redirects=False,
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=1,
                        timeout=15,
                    )
                    if not resp or resp.status_code not in (301, 302, 307, 308):
                        return None, None

                    location = resp.headers.get("location") or resp.headers.get("Location") or ""
                    if not location:
                        return None, None

                    location = urllib.parse.urljoin(redeem_url, location)
                    if is_udemy_course_url(location):
                        return title, location
                    if is_trk_udemy_url(location):
                        unwrapped = self._unwrap_direct_target(location)
                        if unwrapped:
                            return title, unwrapped
                        udemy_url = await self._resolve_trk_redirect(location)
                        if udemy_url and is_udemy_course_url(udemy_url):
                            return title, udemy_url

                    return None, None
                except Exception:
                    return None, None

            found = 0
            for i in range(0, len(unresolved_items), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = unresolved_items[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _resolve_redeem, cid, title)
                    for cid, title in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen_urls:
                            seen_urls.add(normalized)
                            self.append_to_list(title[:200], link)
                            found += 1
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(unresolved_items))

            logger.info(f"  iDownloadCoupon: Found {len(self.data)} total unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class FreeCourseSitesScraper(Scraper):
    BASE_URL = "https://freecoursesites.com"
    CATEGORY_SOURCES = [
        {"slug": "100-off-udemy-coupon", "fallback_id": 137426},
        {"slug": "free-udemy-courses", "fallback_id": 67983},
        {"slug": "udemy-coupon-giveaways", "fallback_id": 0},
        {"slug": "it-software", "fallback_id": 0},
        {"slug": "development", "fallback_id": 0},
    ]
    PER_PAGE = 50
    MAX_COURSES = 500
    MAX_REST_PAGES = 5
    MAX_FALLBACK_ARCHIVE_PAGES = 50
    _last_playwright_ts: float = 0.0
    _PLAYWRIGHT_COOLDOWN_S = 1800.0

    @property
    def site_name(self) -> str:
        return "FreeCourseSites"

    @property
    def code_name(self) -> str:
        return "fcs"

    async def _get_category_id(self, slug: str, fallback_id: int) -> int:
        try:
            url = f"{self.BASE_URL}/wp-json/wp/v2/categories?slug={slug}"
            resp = await self._http_get(
                url, use_cloudscraper=True, timeout=15, raise_for_status=False
            )
            if self._is_cf_challenge(resp) or (resp is not None and resp.status_code == 403):
                logger.warning(f"  [{self.site_name}] Cloudflare Turnstile/WAF challenge on category ID.")
                self._cf_403_observed = True
                self.error = "Blocked by Cloudflare Turnstile WAF"
                return fallback_id
            data = await self.http.safe_json(resp, "freecoursesites_category")
            if isinstance(data, list) and data and data[0].get("id"):
                return int(data[0]["id"])
        except Exception as e:
            logger.debug(
                f"FreeCourseSites: Error fetching category ID for {slug}, using fallback {fallback_id}. {e}"
            )
        return fallback_id

    def _extract_post_title(self, post: dict) -> str:
        raw = post.get("title", {}).get("rendered", "") or ""
        title = self._html_text(raw)
        return title[:200] if title else "FreeCourseSites Course"

    async def _extract_courses_from_html(
        self,
        html: str,
        fallback_title: str,
        seen_urls: set[str],
        resolve_trk: bool = True,
    ) -> list[tuple[str, str]]:
        soup = self.parse_html(html)

        candidates = []
        for anchor in soup.select("a[href]"):
            candidates.append(anchor)

        courses = []
        import html as html_lib

        for a in candidates:
            href = a.get("href", "").strip()
            if not href:
                continue

            href = html_lib.unescape(href)

            classes = a.get("class") or []
            is_button = "mks_button" in classes
            if not (is_button or is_udemy_course_url(href) or is_trk_udemy_url(href)):
                continue

            if is_trk_udemy_url(href):
                if not resolve_trk:
                    continue
                resolved = await self._resolve_trk_redirect(href)
                if resolved:
                    href = resolved

            normalized = Course.normalize_link(href)
            if not is_udemy_course_url(normalized):
                continue

            if normalized in seen_urls:
                continue

            seen_urls.add(normalized)

            raw_text = a.get_text(" ", strip=True)
            if (
                not raw_text
                or len(raw_text) < 4
                or self._is_generic_course_title(raw_text)
            ):
                final_title = fallback_title
            else:
                final_title = raw_text

            courses.append((final_title[:200], normalized))

        return courses

    async def _http_get_fallback(self, url: str, **kwargs) -> Optional[object]:
        """Breaker-aware listing fetch for the HTML fallback (T3).

        The primary ``_http_get`` gate blocks ALL fetches while
        ``circuit_open`` is True, which would starve the HTML fallback even
        though it targets the same per-host listing path. This helper
        intentionally bypasses the OPEN gate for *listing* pages only, under a
        fresh isolated ``fallback_budget=5`` per ``scrape()`` invocation
        (decremented per attempt, hard-stop at 0 — enforced by the caller).
        No retry loop lives outside that budget and no cross-host fan-out is
        introduced (all URLs stay on ``BASE_URL`` / freecoursesites.com), so a
        primary trip on 403/500/host-down cannot double-hammer: at most 5
        fallback listing hits total, and detail tasks stay gated via
        ``_run_detail_task`` (0 HTTP for detail while OPEN).

        Reset-on-200 only (no unconditional reset in ``scrape`` entry):
        - 200 clears ``consecutive_failures`` to 0 AND clears ``circuit_open``
          so a recovered listing re-enables gated detail tasks.
        - Non-200/exception increments ``consecutive_failures`` (no reset)
          and re-trips ``circuit_open`` at threshold, so fallback failures
          count toward instant re-trip.
        """
        if not url or not isinstance(url, str):
            return None
        if not _is_safe_url(url):
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
            ).warning(f"  [{self.site_name}] Blocked unsafe URL (SSRF guard): {_log_safe_url(url)}")
            return None
        if not await self._robots_allowed(url):
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
            ).info(f"  {self.site_name}: skipped {url} — robots.txt Disallow (F252)")
            return None
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.request_timeout
        try:
            resp = await self.http.get(url, **kwargs)
            if resp is not None and getattr(resp, "status_code", None) == 200:
                self.consecutive_failures = 0
                if self.circuit_open:
                    self.circuit_open = False
                    logger.bind(
                        scraper=self.code_name, site=self.site_name
                    ).info(f"  [{self.site_name}] Circuit breaker CLEARED via fallback 200")
                return resp
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.circuit_open = True
                self.error = (
                    f"Circuit breaker tripped after {self.consecutive_failures} consecutive failures"
                )
            return resp
        except Exception as exc:
            self.consecutive_failures += 1
            logger.bind(
                scraper=self.code_name,
                site=self.site_name,
                url=_log_safe_url(url),
                error=type(exc).__name__,
                consecutive_failures=self.consecutive_failures,
            ).warning(f"  [{self.site_name}] Fallback fetch exception ({type(exc).__name__}): {exc}")
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.circuit_open = True
                self.error = (
                    f"Circuit breaker tripped after {self.consecutive_failures} consecutive failures"
                )
            return None

    async def _scrape_html_fallback(
        self,
        detail_semaphore: asyncio.Semaphore,
        seen_urls: set[str],
        fallback_budget: int = 5,
    ) -> int:
        """HTML fallback bounded by an isolated per-scrape listing budget."""
        fallback_remaining = fallback_budget
        if getattr(self, "_cf_403_observed", False):
            logger.info(f"  {self.site_name}: Skipping HTML fallback — Cloudflare 403 previously observed")
            return fallback_remaining

        logger.info(f"  {self.site_name}: Using HTML fallback")
        no_new_links_count = 0
        # T3: fresh isolated counter per scrape() — NOT shared with primary
        # consecutive_failures; each listing attempt spends 1, hard-stop at 0.
        blocked_by_waf = False

        async def _fetch_detail(url: str, post_title: str):
            try:
                resp = await self.http.get(
                    url, use_cloudscraper=True, timeout=15, raise_for_status=False
                )
                if not resp or resp.status_code != 200:
                    return []
                return await self._extract_courses_from_html(
                    resp.text, post_title, seen_urls
                )
            except Exception as e:
                logger.debug(f"Error fetching detail {url}: {e}")
                return []

        for source in self.CATEGORY_SOURCES:
            if blocked_by_waf:
                break
            if len(self.data) >= self.MAX_COURSES:
                break
            if fallback_remaining <= 0:
                break

            slug = source["slug"]
            logger.info(f"  {self.site_name}: HTML fallback scraping category {slug}")
            no_new_links_count = 0

            for page in range(1, self.MAX_FALLBACK_ARCHIVE_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break
                if fallback_remaining <= 0:
                    break

                if page == 1:
                    url = f"{self.BASE_URL}/category/{slug}/"
                else:
                    url = f"{self.BASE_URL}/category/{slug}/page/{page}/"

                # T3: spend 1 unit of the isolated fallback budget per listing
                # attempt (same-host only); bypasses OPEN gate via helper but
                # hard-stops at 0 so a tripped primary cannot double-hammer.
                # Detail fetches below stay gated by _run_detail_task (0 HTTP
                # for detail while OPEN unless a fallback 200 clears it).
                fallback_remaining -= 1
                resp = await self._http_get_fallback(
                    url, use_cloudscraper=True, timeout=20, raise_for_status=False
                )
                is_cf = False
                if resp is not None:
                    resp_text = (getattr(resp, "text", "") or "")[:4096].lower()
                    is_cf = any(m in resp_text for m in ("just a moment", "cf-browser-verification", "attention required", "cf-challenge", "cf_chl"))
                if resp is not None and (resp.status_code == 403 or is_cf):
                    logger.warning(f"  [{self.site_name}] 403/Cloudflare block on category '{slug}' (status={resp.status_code}, is_cf={is_cf}). Halting HTML fallback.")
                    self._cf_403_observed = True
                    blocked_by_waf = True
                    break
                if resp is None and (self.circuit_open or self.consecutive_failures >= self.max_consecutive_failures):
                    logger.warning(f"  [{self.site_name}] Circuit open / failure limit reached in fallback. Halting outer category loop.")
                    blocked_by_waf = True
                    break
                if not resp or resp.status_code != 200:
                    break

                soup = self.parse_html(resp.text)
                detail_links = []
                for a in soup.select("article h2 a, .entry-title a, h2 a"):
                    href = a.get("href", "").strip()
                    if "freecoursesites.com" in href and href not in [
                        d[0] for d in detail_links
                    ]:
                        title = a.get_text(strip=True)
                        detail_links.append((href, title))

                if not detail_links:
                    break

                self.length = len(detail_links)
                self.progress = 0
                new_courses_on_page = 0

                # Process in small chunks to prevent massive over-fetching near the cap
                chunk_size = 5
                for i in range(0, len(detail_links), chunk_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break

                    chunk = detail_links[i : i + chunk_size]
                    detail_tasks = [
                        self._run_detail_task(
                            detail_semaphore, _fetch_detail, href, title
                        )
                        for href, title in chunk
                    ]

                    results_list = await asyncio.gather(
                        *detail_tasks, return_exceptions=True
                    )
                    for results in results_list:
                        self.progress += 1
                        if isinstance(results, Exception):
                            logger.debug(f"Error in detail task: {results}")
                            continue
                        if isinstance(results, list):
                            for title, url in results:
                                if len(self.data) >= self.MAX_COURSES:
                                    break
                                prev_len = len(self.data)
                                self.append_to_list(title, url)
                                if len(self.data) > prev_len:
                                    new_courses_on_page += 1

                    if len(self.data) >= self.MAX_COURSES:
                        break

                if new_courses_on_page == 0:
                    no_new_links_count += 1
                else:
                    no_new_links_count = 0

                if no_new_links_count >= 3:
                    break
            if blocked_by_waf:
                break
        return fallback_remaining  # T4-T2: resort gate needs exhaustion signal

    async def _scrape_rest_api(self, seen_urls: set[str]) -> None:
        for source in self.CATEGORY_SOURCES:
            if getattr(self, "_cf_403_observed", False) or self.circuit_open:
                break
            if len(self.data) >= self.MAX_COURSES:
                break

            slug = source["slug"]
            fallback_id = source["fallback_id"]
            cat_id = await self._get_category_id(slug, fallback_id)
            if getattr(self, "_cf_403_observed", False) or self.circuit_open:
                break

            logger.info(
                f"  {self.site_name}: REST scraping category {slug} (ID: {cat_id})"
            )

            self.length = self.MAX_REST_PAGES
            actual_max_pages = self.MAX_REST_PAGES
            initial_count = len(self.data)

            for page in range(1, self.MAX_REST_PAGES + 1):
                if page > actual_max_pages:
                    break

                self.progress = page
                url = f"{self.BASE_URL}/wp-json/wp/v2/posts?categories={cat_id}&per_page={self.PER_PAGE}&page={page}&orderby=date&order=desc&_fields=id,link,title,content,date"
                resp = await self._http_get(
                    url, use_cloudscraper=True, timeout=20, raise_for_status=False
                )
                if self._is_cf_challenge(resp) or (resp is not None and resp.status_code == 403):
                    logger.warning(f"  [{self.site_name}] Cloudflare Turnstile/WAF challenge on REST category '{slug}' page {page}.")
                    self._cf_403_observed = True
                    self.error = "Blocked by Cloudflare Turnstile WAF"
                    break
                if not resp or resp.status_code != 200:
                    break

                if page == 1:
                    total_pages_header = resp.headers.get(
                        "X-WP-TotalPages"
                    ) or resp.headers.get("x-wp-totalpages")
                    if total_pages_header and total_pages_header.isdigit():
                        actual_max_pages = min(
                            self.MAX_REST_PAGES, int(total_pages_header)
                        )
                        self.length = actual_max_pages

                posts = await self.http.safe_json(resp, "freecoursesites_posts")
                if posts is None:
                    self._cf_403_observed = True  # T4-T2 safe_json CF-None signature
                if not isinstance(posts, list) or not posts:
                    break

                for post in posts:
                    if len(self.data) >= self.MAX_COURSES:
                        break

                    post_title = self._extract_post_title(post)
                    html = post.get("content", {}).get("rendered", "")

                    courses = await self._extract_courses_from_html(
                        html, post_title, seen_urls
                    )
                    for title, url in courses:
                        if len(self.data) >= self.MAX_COURSES:
                            break
                        self.append_to_list(title, url)

                if len(self.data) >= self.MAX_COURSES:
                    break

            added = len(self.data) - initial_count
            logger.info(
                f"  {self.site_name}: Extracted {added} unique courses from {slug}. Total so far: {len(self.data)}"
            )

    async def _scrape_playwright_resort(self, seen_urls: set[str], fallback_remaining: int = 0) -> None:
        """Playwright last-resort (T4-T2, OFF unless FCS_PLAYWRIGHT_FALLBACK=1).
        Triple-guard: empty data + exhausted budget + (OPEN or fails>=thr w/ CF-403
        sig). Single same-host listing from CATEGORY_SOURCES[0]; wait_for 40s, no
        wait_selector. ""/timeout/CF -> 0 courses, zero breaker mutation; only
        semantic success clears OPEN. Cooldown 1800s in-mem (single-replica)."""
        if os.getenv("FCS_PLAYWRIGHT_FALLBACK", "0") != "1":
            return
        if len(self.data) != 0 or (isinstance(fallback_remaining, int) and fallback_remaining > 0):
            return
        cf_sig = bool(getattr(self, "_cf_403_observed", False))
        if not (self.circuit_open or (self.consecutive_failures >= self.max_consecutive_failures and cf_sig)):
            return
        now = time.monotonic()
        if type(self)._last_playwright_ts > 0 and now - type(self)._last_playwright_ts < self._PLAYWRIGHT_COOLDOWN_S:
            logger.bind(scraper=self.code_name, site=self.site_name).info(f"  [{self.site_name}] Playwright resort skipped — cooldown active")
            return
        url = f"{self.BASE_URL}/category/{self.CATEGORY_SOURCES[0]['slug']}/"
        if urllib.parse.urlparse(url).netloc != urllib.parse.urlparse(self.BASE_URL).netloc or not _is_safe_url(url) or not await self._robots_allowed(url):
            logger.bind(scraper=self.code_name, site=self.site_name).warning(f"  [{self.site_name}] Playwright resort blocked (SSRF/scope/robots): {_log_safe_url(url)}")
            return
        type(self)._last_playwright_ts = now
        try:
            html_text = await asyncio.wait_for(self.playwright_get(url), timeout=40)
        except Exception as exc:
            logger.bind(scraper=self.code_name, site=self.site_name).warning(f"  [{self.site_name}] Playwright resort failed ({type(exc).__name__}): {exc}")
            return
        if not html_text:
            logger.bind(scraper=self.code_name, site=self.site_name).warning(f"  [{self.site_name}] Playwright resort BLOCKED_BY_ENV: 0 courses, breaker untouched")
            return
        if "Just a moment..." in html_text or "cf-browser-verification" in html_text or "Attention Required!" in html_text:
            logger.bind(scraper=self.code_name, site=self.site_name).warning(f"  [{self.site_name}] Playwright resort CF unresolved — breaker stays OPEN")
            return
        before = len(self.data)
        for t, link in await self._extract_courses_from_html(html_text, self.CATEGORY_SOURCES[0]["slug"].replace("-", " ").title(), seen_urls, resolve_trk=False):
            self.append_to_list(t, link)
        if len(self.data) - before >= 2:
            self.consecutive_failures = 0
            if self.circuit_open:
                self.circuit_open = False
                logger.bind(scraper=self.code_name, site=self.site_name).info(f"  [{self.site_name}] Circuit breaker CLEARED via playwright resort")
        elif len(self.data) > before:
            logger.bind(scraper=self.code_name, site=self.site_name).warning(f"  [{self.site_name}] Playwright resort-partial — breaker stays OPEN")

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_urls: set[str] = set()
            await self._scrape_rest_api(seen_urls)
            if len(self.data) < self.MAX_COURSES:
                # T3: fresh isolated fallback budget (5) per scrape() invocation.
                # No unconditional breaker reset here — recovery is 200-only
                # via _http_get/_http_get_fallback semantics.
                fallback_remaining = await self._scrape_html_fallback(detail_semaphore, seen_urls, fallback_budget=5)
                await self._scrape_playwright_resort(seen_urls, fallback_remaining)
        except Exception:
            self.error = traceback.format_exc()


class DiscudemyScraper(Scraper):
    """Discudemy (discudemy.com) — native leftover pages after the Couponami rebrand.

    Listing is /all and /all/{n}. Couponami.com listing hrefs are skipped
    (CouponamiScraper already covers those cards). Native discudemy.com/{slug}
    details yield only from on-page couponCode= or direct udemy.com/course URLs.
    Chrome/nav paths are not treated as details; couponami.com/go/ is never fetched.
    """

    BASE_URL = "https://www.discudemy.com"
    DISCUDEMY_HOSTS = frozenset({"www.discudemy.com", "discudemy.com"})
    COUPONAMI_HOSTS = frozenset({"www.couponami.com", "couponami.com"})
    EXCLUDED_SEGMENTS = frozenset(
        {
            "all",
            "policies",
            "category",
            "language",
            "vendor",
            "go",
            "page",
            "feed",
            "search",
            "contact",
            "login",
            "register",
            "manifest",
            "sitemap",
            "robots",
            "apple-touch-icon",
            "favicon",
        }
    )
    CHROME_EXTENSIONS = frozenset(
        {
            ".png",
            ".json",
            ".ico",
            ".xml",
            ".txt",
            ".css",
            ".js",
            ".jpg",
            ".jpeg",
            ".webp",
            ".svg",
            ".gif",
            ".html",
        }
    )
    MAX_COURSES = 500
    COURSES_PER_PAGE = 15

    @property
    def site_name(self) -> str:
        return "Discudemy"

    @property
    def code_name(self) -> str:
        return "du"

    @staticmethod
    def _host(url: str) -> str:
        try:
            return urllib.parse.urlparse(url).netloc.lower().split(":")[0]
        except Exception:
            return ""

    def _is_couponami_url(self, url: str) -> bool:
        return self._host(url) in self.COUPONAMI_HOSTS

    def _is_native_detail(self, url: str) -> bool:
        if self._host(url) not in self.DISCUDEMY_HOSTS:
            return False
        try:
            parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
        except Exception:
            return False
        if len(parts) != 1:
            return False
        segment = parts[0].lower()
        if segment in self.EXCLUDED_SEGMENTS:
            return False
        if any(segment.endswith(ext) for ext in self.CHROME_EXTENSIONS):
            return False
        return True

    def _title_from_html(self, text: str) -> str:
        og_match = re.search(
            r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
            text,
        )
        if og_match:
            return og_match.group(1).strip()
        title_match = re.search(r"<title>([^<]+)</title>", text)
        if title_match:
            title = title_match.group(1)
            title = re.sub(
                r"^Enroll\s*Course\s*[-|]\s*",
                "",
                title,
                flags=re.IGNORECASE,
            )
            title = re.sub(
                r"\s*[-|]\s*Free\s*Udemy\s*Courses.*",
                "",
                title,
                flags=re.IGNORECASE,
            )
            title = re.sub(
                r"\s*[-|]\s*DiscUdemy.*",
                "",
                title,
                flags=re.IGNORECASE,
            )
            return title.strip()
        return ""

    def _udemy_from_quoted_urls(self, text: str) -> Optional[str]:
        matches = re.findall(r'["\'](https?://[^"\']+)["\']', text)
        for m in matches:
            if ".jpg" in m or ".png" in m:
                continue
            if is_udemy_course_url(m):
                return m
        return None

    def _udemy_coupon_url(self, text: str) -> Optional[str]:
        for m in re.findall(r'https?://[^\s"\'<>]+', text):
            if "couponCode=" in m and is_udemy_course_url(m):
                return m
        return self._udemy_from_quoted_urls(text) if "couponCode=" in text else None

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            max_pages = (self.MAX_COURSES // self.COURSES_PER_PAGE) + 2
            candidates: list[tuple[str, str]] = []
            seen_details: set[str] = set()
            self.length = max_pages

            for page_num in range(1, max_pages + 1):
                self.progress = page_num
                url = (
                    f"{self.BASE_URL}/all"
                    if page_num == 1
                    else f"{self.BASE_URL}/all/{page_num}"
                )
                resp = await self._http_get(
                    url, use_cloudscraper=True, timeout=15
                )
                if not resp or resp.status_code != 200:
                    break
                text = resp.text or ""
                if not text.strip():
                    break

                soup = self.parse_html(text)
                for a in soup.find_all("a", href=True):
                    href = urllib.parse.urljoin(self.BASE_URL + "/", a["href"])
                    if self._is_couponami_url(href):
                        continue
                    if not self._is_native_detail(href):
                        continue
                    normalized = href.split("#")[0].rstrip("/")
                    if normalized in seen_details:
                        continue
                    seen_details.add(normalized)
                    title = a.get_text(" ", strip=True) or ""
                    candidates.append((normalized, title))
                    if len(candidates) >= self.MAX_COURSES:
                        break
                if len(candidates) >= self.MAX_COURSES:
                    break

            logger.info(
                f"  Discudemy: Found {len(candidates)} native candidates"
            )
            if not candidates:
                logger.info("  Discudemy: Found 0 unique Udemy courses")
                return

            self.length = len(candidates)
            self.progress = 0
            seen_udemy: set[str] = set()

            async def _fetch_detail(detail_url: str, card_title: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None
                    text = page.text or ""
                    udemy_url = self._udemy_coupon_url(text)
                    if not udemy_url:
                        return None, None
                    title = card_title or self._title_from_html(text) or "Unknown"
                    return title, udemy_url
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, url, title)
                for url, title in candidates[: self.MAX_COURSES]
            ]

            found = 0
            detail_results = await asyncio.gather(*detail_tasks, return_exceptions=True)
            for i, res in enumerate(detail_results):
                self.progress = i + 1
                if not res or isinstance(res, Exception):
                    continue
                title, link = res
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_udemy:
                        seen_udemy.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
            logger.info(f"  Discudemy: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CoursonScraper(Scraper):
    """Courson (courson.xyz) — HTTP-only /coupon/{slug} scraper.

    Parses window.courseData on coupon pages. Never fetches /claim/ (robots
    Disallow) and never uses Playwright.
    """

    BASE_URL = "https://courson.xyz"
    API_URL = "https://courson.xyz/load-more-coupons"
    HOSTS = frozenset({"courson.xyz", "www.courson.xyz"})
    MAX_COURSES = 500
    MAX_COUPON_PAGES = 750
    DETAIL_BATCH_SIZE = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._api_coupon_items: dict[str, dict] = {}

    @property
    def site_name(self) -> str:
        return "Courson"

    @property
    def code_name(self) -> str:
        return "cr"

    def _is_claim_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urllib.parse.urlparse(
                urllib.parse.urljoin(self.BASE_URL + "/", url)
            )
        except Exception:
            return False
        return parsed.path.startswith("/claim/")

    def _is_coupon_page(self, url: str) -> bool:
        if not url or self._is_claim_url(url):
            return False
        try:
            parsed = urllib.parse.urlparse(
                urllib.parse.urljoin(self.BASE_URL + "/", url)
            )
        except Exception:
            return False
        host = parsed.netloc.lower().split(":")[0]
        if host and host not in self.HOSTS:
            return False
        parts = [p for p in parsed.path.split("/") if p]
        return len(parts) == 2 and parts[0] == "coupon" and parts[1]

    def _absolute_coupon_url(self, url: str) -> Optional[str]:
        if not self._is_coupon_page(url):
            return None
        parsed = urllib.parse.urlparse(
            urllib.parse.urljoin(self.BASE_URL + "/", url)
        )
        slug = [p for p in parsed.path.split("/") if p][1]
        return f"{self.BASE_URL}/coupon/{slug}"

    async def _gated_http_get(self, url: str, **kwargs):
        if self._is_claim_url(url):
            return None
        return await self._http_get(url, **kwargs)

    async def _collect_api_posts(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        offset = 0
        limit = 30
        max_batches = getattr(self, "MAX_COUPON_PAGES", 750) // limit + 2
        for _ in range(max_batches):
            try:
                resp = await self.http.post(
                    getattr(self, "API_URL", f"{self.BASE_URL}/load-more-coupons"),
                    json={"filters": {}, "offset": offset},
                    use_cloudscraper=True,
                    timeout=15,
                )
                if not resp or resp.status_code != 200 or not resp.text:
                    break
                data = json.loads(resp.text)
                coupons = data.get("coupons") or []
                if not coupons or not isinstance(coupons, list):
                    break
                new_items = 0
                for item in coupons:
                    if not isinstance(item, dict):
                        continue
                    id_name = item.get("id_name") or item.get("slug") or item.get("id")
                    if not id_name:
                        continue
                    url = f"{self.BASE_URL}/coupon/{id_name}"
                    self._api_coupon_items[url] = {
                        "title": (item.get("title") or item.get("course_title") or "").strip(),
                        "coupon_code": (item.get("coupon_code") or item.get("coupon") or "").strip(),
                        "id_name": id_name,
                    }
                    if url not in seen:
                        seen.add(url)
                        urls.append(url)
                        new_items += 1
                        if len(urls) >= self.MAX_COUPON_PAGES:
                            return urls
                if new_items == 0:
                    break
                offset += len(coupons)
                total_count = data.get("total_count", 0)
                if total_count and offset >= total_count:
                    break
            except Exception:
                break
        return urls

    def _parse_course_data(self, text: str) -> dict:
        match = re.search(r"window\.courseData\s*=\s*\{", text)
        if not match:
            return {}
        start = match.end() - 1
        depth = 0
        end = None
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        blob = text[start:end] if end else text[start : start + 2000]

        def _field(name: str) -> Optional[str]:
            m = re.search(
                rf'{name}\s*:\s*["\']([^"\']+)["\']',
                blob,
            )
            return m.group(1).strip() if m else None

        return {
            "coupon_code": _field("coupon_code"),
            "course_id": _field("course_id"),
            "course_slug": _field("course_slug"),
            "course_title": _field("course_title"),
        }

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self._api_coupon_items = {}
            coupon_urls: list[str] = await self._collect_api_posts()
            if not coupon_urls:
                homepage_urls: list[str] = []
                sitemap_urls: list[str] = []

                home = await self._gated_http_get(
                    f"{self.BASE_URL}/", use_cloudscraper=True, timeout=15
                )
                if home and home.status_code == 200 and home.text:
                    soup = self.parse_html(home.text)
                    for a in soup.find_all("a", href=True):
                        abs_url = self._absolute_coupon_url(a["href"])
                        if abs_url:
                            homepage_urls.append(abs_url)

                sitemap = await self._gated_http_get(
                    f"{self.BASE_URL}/sitemap.xml",
                    use_cloudscraper=True,
                    timeout=20,
                )
                if sitemap and sitemap.status_code == 200 and sitemap.text:
                    for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap.text):
                        abs_url = self._absolute_coupon_url(loc.strip())
                        if abs_url:
                            sitemap_urls.append(abs_url)

                seen: set[str] = set()
                for url in sitemap_urls + homepage_urls:
                    if url not in seen:
                        seen.add(url)
                        coupon_urls.append(url)
                    if len(coupon_urls) >= self.MAX_COUPON_PAGES:
                        break

            coupon_urls = coupon_urls[: self.MAX_COUPON_PAGES]
            if not coupon_urls:
                return

            self.length = len(coupon_urls)
            self.progress = 0
            seen_udemy: set[str] = set()

            async def _fetch_coupon(page_url: str):
                if self._is_claim_url(page_url) or not self._is_coupon_page(page_url):
                    return None, None
                cached = getattr(self, "_api_coupon_items", {}).get(page_url)
                if cached:
                    c_id = cached.get("id_name")
                    c_code = cached.get("coupon_code")
                    if c_id and c_code:
                        udemy_url = f"https://www.udemy.com/course/{c_id}/?couponCode={c_code}"
                        if is_udemy_course_url(udemy_url):
                            c_title = cached.get("title") or c_id.replace("-", " ").title()
                            return c_title, udemy_url
                try:
                    resp = await self._gated_http_get(
                        page_url, use_cloudscraper=True, timeout=15
                    )
                    if not resp or resp.status_code != 200:
                        return None, None
                    text = resp.text or ""
                    data = self._parse_course_data(text)
                    code = data.get("coupon_code")
                    if not code:
                        return None, None
                    slug = data.get("course_slug") or data.get("course_id")
                    if not slug:
                        return None, None
                    udemy_url = (
                        f"https://www.udemy.com/course/{slug}/?couponCode={code}"
                    )
                    if not is_udemy_course_url(udemy_url):
                        return None, None
                    title = data.get("course_title") or ""
                    if not title:
                        og = re.search(
                            r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                            text,
                        )
                        if og:
                            title = og.group(1).strip()
                    if not title:
                        tm = re.search(r"<title>([^<]+)</title>", text)
                        if tm:
                            title = re.sub(
                                r"^\s*Coupon\s*[-:]\s*",
                                "",
                                tm.group(1),
                                flags=re.IGNORECASE,
                            ).strip()
                    return title or slug.replace("-", " ").title(), udemy_url
                except Exception:
                    return None, None

            for i in range(0, len(coupon_urls), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = coupon_urls[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(detail_semaphore, _fetch_coupon, url)
                    for url in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen_udemy:
                            seen_udemy.add(normalized)
                            self.append_to_list(title[:200], link)
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(coupon_urls))
        except Exception:
            self.error = traceback.format_exc()


class CouponScorpionScraper(Scraper):
    """CouponScorpion (couponscorpion.com) — WP REST listing + out.php hop.

    Titles come from REST/post titles. out.php is fetched via self.http.get
    (CloudScraper, allow_redirects=False, attempts=1); only a resolved
    Udemy Location is appended. Location is never followed.
    """

    BASE_URL = "https://couponscorpion.com"
    REST_URL = (
        "https://couponscorpion.com/wp-json/wp/v2/posts"
        "?categories=21032&per_page=50&page={n}&orderby=date&order=desc"
        "&_fields=id,link,title"
    )
    HTML_LISTING = "https://couponscorpion.com/category/100-off-coupons/"
    MAX_COURSES = 500
    MAX_REST_PAGES = 8
    CANDIDATE_BUFFER = 700
    DETAIL_BATCH_SIZE = 10
    SKIP_PATH_PREFIXES = ("/category/", "/page/", "/scripts/")
    SKIP_PATH_SUBSTRINGS = (
        "/bootstrap-4-tutarial-for-beginners-with-projects/",
        "/scripts/udemy/out.php",
    )
    _OUT_PHP_RE = re.compile(
        r'href=["\']([^"\']*/scripts/udemy/out\.php[^"\']*)["\']',
        re.IGNORECASE,
    )

    @property
    def site_name(self) -> str:
        return "CouponScorpion"

    @property
    def code_name(self) -> str:
        return "csc"

    def _skip_listing_href(self, href: str) -> bool:
        try:
            path = urllib.parse.urlparse(href).path or ""
        except Exception:
            return True
        if not path.endswith("/"):
            path = path + "/"
        if any(path.startswith(p) for p in self.SKIP_PATH_PREFIXES):
            return True
        return any(s in href for s in self.SKIP_PATH_SUBSTRINGS)

    def _post_title(self, post: dict) -> str:
        raw = ""
        title_obj = post.get("title")
        if isinstance(title_obj, dict):
            raw = title_obj.get("rendered") or ""
        elif isinstance(title_obj, str):
            raw = title_obj
        return self._html_text(raw)

    async def _collect_rest_posts(self) -> list[tuple[str, str]]:
        import json

        posts: list[tuple[str, str]] = []
        seen_links: set[str] = set()
        buffer_limit = min(
            getattr(self, "CANDIDATE_BUFFER", 700),
            max(self.MAX_COURSES * 3, 50),
        )
        max_pages = getattr(self, "MAX_REST_PAGES", 8)
        batch_size = getattr(self, "REST_BATCH_SIZE", 4)
        self.length = max_pages

        stop_pagination = False
        for start_page in range(1, max_pages + 1, batch_size):
            end_page = min(start_page + batch_size, max_pages + 1)
            page_tasks = [
                self._http_get(
                    self.REST_URL.format(n=p),
                    use_cloudscraper=True,
                    timeout=15,
                )
                for p in range(start_page, end_page)
            ]
            responses = await asyncio.gather(*page_tasks, return_exceptions=True)

            for page_num, resp in zip(range(start_page, end_page), responses):
                self.progress = page_num
                if isinstance(resp, Exception) or not resp or getattr(resp, "status_code", None) != 200:
                    stop_pagination = True
                    break
                text = (getattr(resp, "text", "") or "").strip()
                if not text:
                    stop_pagination = True
                    break
                try:
                    data = json.loads(text)
                except Exception:
                    stop_pagination = True
                    break
                if not isinstance(data, list) or not data:
                    stop_pagination = True
                    break
                for post in data:
                    if not isinstance(post, dict):
                        continue
                    link = (post.get("link") or "").strip()
                    if not link or self._skip_listing_href(link):
                        continue
                    if link in seen_links:
                        continue
                    seen_links.add(link)
                    title = self._post_title(post)
                    if not title:
                        continue
                    posts.append((link, title))
                    if len(posts) >= buffer_limit:
                        return posts[:buffer_limit]

            if stop_pagination or len(posts) >= buffer_limit:
                break

        return posts[:buffer_limit]

    async def _collect_html_posts(self) -> list[tuple[str, str]]:
        posts: list[tuple[str, str]] = []
        seen_links: set[str] = set()
        max_pages = (self.MAX_COURSES // 12) + 2
        self.length = max_pages
        for page_num in range(1, max_pages + 1):
            self.progress = page_num
            url = (
                self.HTML_LISTING
                if page_num == 1
                else f"{self.HTML_LISTING}page/{page_num}/"
            )
            resp = await self._http_get(
                url, use_cloudscraper=True, timeout=15
            )
            if not resp or resp.status_code != 200:
                break
            text = resp.text or ""
            if not text.strip():
                break
            soup = self.parse_html(text)
            page_found = 0
            for a in soup.select("article h2 a, .entry-title a, h2 a"):
                href = urllib.parse.urljoin(self.BASE_URL + "/", a.get("href", ""))
                if self._skip_listing_href(href):
                    continue
                host = urllib.parse.urlparse(href).netloc.lower().split(":")[0]
                if host not in {"couponscorpion.com", "www.couponscorpion.com"}:
                    continue
                if href in seen_links:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or self._is_generic_course_title(title):
                    continue
                seen_links.add(href)
                posts.append((href, title))
                page_found += 1
                if len(posts) >= getattr(self, "CANDIDATE_BUFFER", 800):
                    return posts
            if page_found == 0:
                break
        return posts

    def _out_url_from_href(self, href: str) -> Optional[str]:
        if not href:
            return None
        unescaped_href = html.unescape(href)
        parsed = urllib.parse.urlparse(unescaped_href)
        qs = urllib.parse.parse_qs(parsed.query)
        go = (qs.get("go") or [None])[0]
        if not go:
            return None
        s = (qs.get("s") or [None])[0]
        go_q = urllib.parse.quote(go, safe="")
        if s:
            s_q = urllib.parse.quote(s, safe="")
            return f"{self.BASE_URL}/scripts/udemy/out.php?go={go_q}&s={s_q}"
        return f"{self.BASE_URL}/scripts/udemy/out.php?go={go_q}"

    async def _resolve_out(self, out_url: str) -> Optional[str]:
        try:
            resp = await self.http.get(
                out_url,
                use_cloudscraper=True,
                allow_redirects=False,
                follow_redirects=False,
                raise_for_status=False,
                attempts=1,
                timeout=8,
            )
            if not resp or resp.status_code not in (301, 302, 307, 308):
                status = getattr(resp, "status_code", None)
                logger.warning(
                    f"  CouponScorpion: out.php hop skipped (status={status})"
                )
                return None
            location = resp.headers.get("location") or resp.headers.get("Location") or ""
            if not location:
                return None
            location = urllib.parse.urljoin(out_url, location)
            if is_trk_udemy_url(location):
                return await self._resolve_trk_redirect(location)
            if is_udemy_course_url(location):
                return location
            # Handle relative/same-origin redirect hops
            if "couponscorpion.com" in location and "/scripts/udemy/" in location:
                resp2 = await self.http.get(
                    location,
                    use_cloudscraper=True,
                    allow_redirects=False,
                    follow_redirects=False,
                    raise_for_status=False,
                    attempts=1,
                    timeout=8,
                )
                if resp2 and resp2.status_code in (301, 302, 307, 308):
                    loc2 = resp2.headers.get("location") or resp2.headers.get("Location") or ""
                    loc2 = urllib.parse.urljoin(location, loc2)
                    if is_trk_udemy_url(loc2):
                        return await self._resolve_trk_redirect(loc2)
                    if is_udemy_course_url(loc2):
                        return loc2
            return None
        except Exception:
            return None

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            listing = await self._collect_rest_posts()
            if not listing:
                listing = await self._collect_html_posts()
            if not listing:
                return

            listing = listing[: getattr(self, "CANDIDATE_BUFFER", 800)]
            self.length = len(listing)
            self.progress = 0
            seen_udemy: set[str] = set()

            async def _fetch_post(post_url: str, post_title: str):
                try:
                    page = await self.http.get(
                        post_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None
                    text = page.text or ""
                    out_url = None
                    m = self._OUT_PHP_RE.search(text)
                    if m:
                        out_url = self._out_url_from_href(m.group(1))
                    if not out_url:
                        soup = self.parse_html(text)
                        for a in soup.select('a[href*="/scripts/udemy/out.php"]'):
                            href = urllib.parse.urljoin(post_url, a.get("href", ""))
                            out_url = self._out_url_from_href(href)
                            if out_url:
                                break
                    if not out_url:
                        return None, None
                    udemy_url = await self._resolve_out(out_url)
                    if not udemy_url or not is_udemy_course_url(udemy_url):
                        return None, None
                    title = post_title or "Unknown"
                    return title, udemy_url
                except Exception:
                    return None, None

            for i in range(0, len(listing), getattr(self, "DETAIL_BATCH_SIZE", 10)):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = listing[i : i + getattr(self, "DETAIL_BATCH_SIZE", 10)]
                chunk_tasks = [
                    self._run_detail_task(
                        detail_semaphore, _fetch_post, link, title
                    )
                    for link, title in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link:
                        normalized = Course.normalize_link(link)
                        if normalized not in seen_udemy:
                            seen_udemy.add(normalized)
                            self.append_to_list(title[:200], link)
                            if len(self.data) >= self.MAX_COURSES:
                                break
                self.progress = min(i + len(chunk), len(listing))
        except Exception:
            self.error = traceback.format_exc()


class OnlineCoursesScraper(Scraper):
    """OnlineCourses.ooo — RSS /feed/ then HTML pagination.

    Origin-wide Cloudflare Turnstile abort-closes with error
    'Blocked by Cloudflare Turnstile WAF'. unique=0 is WAF/site-down,
    not a selector miss. RSS items are /coupon/ slugs. Do not add
    Playwright. Do not unregister while indexed.
    """

    BASE_URL = "https://www.onlinecourses.ooo"
    FEED_URL = "https://www.onlinecourses.ooo/feed/"
    MAX_COURSES = 500
    MAX_LISTING_PAGES = 50
    CANDIDATE_BUFFER = 750
    DETAIL_BATCH_SIZE = 10
    SKIP_PATH_PREFIXES = (
        "/category/",
        "/feed/",
        "/tag/",
        "/page/",
        "/author/",
        "/wp-json/",
        "/contact",
        "/privacy-policy",
        "/about",
    )

    @property
    def site_name(self) -> str:
        return "OnlineCourses.ooo"

    @property
    def code_name(self) -> str:
        return "oc"

    def _is_detail_link(self, href: str) -> bool:
        if not href:
            return False
        try:
            parsed = urllib.parse.urlparse(urllib.parse.urljoin(self.BASE_URL, href))
            host = parsed.netloc.lower().split(":")[0]
            if host not in ("onlinecourses.ooo", "www.onlinecourses.ooo"):
                return False
            path = parsed.path or ""
            if not path or path == "/":
                return False
            return not any(path.startswith(p) for p in self.SKIP_PATH_PREFIXES)
        except Exception:
            return False

    async def _fetch_feed_items(self) -> list[tuple[str, str]]:
        candidates = []
        try:
            resp = await self._http_get(
                self.FEED_URL, use_cloudscraper=True, timeout=20, raise_for_status=False
            )
            if self._is_cf_challenge(resp) or (resp is not None and resp.status_code == 403):
                logger.warning(f"  [{self.site_name}] Cloudflare Turnstile/WAF challenge on feed.")
                self._cf_403_observed = True
                self.error = "Blocked by Cloudflare Turnstile WAF"
                return []
            if resp and resp.status_code == 200 and resp.text:
                items = re.findall(
                    r"<item>(.*?)</item>", resp.text, re.DOTALL | re.IGNORECASE
                )
                for item_str in items:
                    link_m = re.search(
                        r"<link>(.*?)</link>", item_str, re.DOTALL | re.IGNORECASE
                    )
                    title_m = re.search(
                        r"<title>(.*?)</title>", item_str, re.DOTALL | re.IGNORECASE
                    )
                    link = link_m.group(1).strip() if link_m else ""
                    title = title_m.group(1).strip() if title_m else ""
                    if link and self._is_detail_link(link):
                        candidates.append((link, title))
        except Exception as e:
            logger.debug(f"OnlineCourses.ooo feed fetch failed: {e}")
        return candidates

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_pages: set[str] = set()
            candidates: list[tuple[str, str]] = []

            feed_items = await self._fetch_feed_items()
            if getattr(self, "_cf_403_observed", False) or self.error == "Blocked by Cloudflare Turnstile WAF":
                return
            for link, title in feed_items:
                if link not in seen_pages:
                    seen_pages.add(link)
                    candidates.append((link, title))

            for page_num in range(1, self.MAX_LISTING_PAGES + 1):
                if len(candidates) >= self.CANDIDATE_BUFFER:
                    break
                url = (
                    f"{self.BASE_URL}/"
                    if page_num == 1
                    else f"{self.BASE_URL}/page/{page_num}/"
                )
                resp = await self._http_get(
                    url, use_cloudscraper=True, timeout=15, raise_for_status=False
                )
                if self._is_cf_challenge(resp) or (resp is not None and resp.status_code == 403):
                    logger.warning(f"  [{self.site_name}] Cloudflare Turnstile/WAF challenge on page {page_num}.")
                    self._cf_403_observed = True
                    self.error = "Blocked by Cloudflare Turnstile WAF"
                    break
                if not resp or resp.status_code != 200 or not resp.text:
                    if page_num == 1 and not candidates:
                        self.error = "Failed to fetch listing page 1"
                    break

                soup = self.parse_html(resp.text)
                new_links = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if self._is_detail_link(href):
                        abs_link = urllib.parse.urljoin(self.BASE_URL, href)
                        if abs_link not in seen_pages:
                            seen_pages.add(abs_link)
                            title = a.get_text(strip=True) or ""
                            candidates.append((abs_link, title))
                            new_links += 1
                if new_links == 0:
                    break

            if not candidates:
                return

            self.length = len(candidates)
            self.progress = 0
            seen_udemy: set[str] = set()

            async def _fetch_detail(detail_url: str, fallback_title: str):
                try:
                    resp = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=10, raise_for_status=False
                    )
                    if not resp or resp.status_code != 200 or not resp.text:
                        return None, None
                    # Fast regex search for course URL
                    m = re.search(r'href="(https?://[^"]+/course/[^"]+)"', resp.text)
                    if m:
                        normalized = Course.normalize_link(m.group(1))
                        if is_udemy_course_url(normalized):
                            h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', resp.text, re.DOTALL)
                            title = (
                                html.unescape(
                                    re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()
                                )
                                if h1_m
                                else fallback_title
                            )
                            if not title or self._is_generic_course_title(title):
                                title = fallback_title
                            return title, normalized

                    soup = self.parse_html(resp.text)
                    btn = soup.select_one(
                        "a.btn_offer_block, a.re_track_btn, a[href*='udemy.com']"
                    )
                    if not btn or not btn.get("href"):
                        return None, None
                    raw_href = btn["href"]
                    normalized = Course.normalize_link(raw_href)
                    if not is_udemy_course_url(normalized):
                        return None, None

                    h1 = soup.find("h1")
                    title = h1.get_text(strip=True) if h1 else fallback_title
                    if not title or self._is_generic_course_title(title):
                        title = fallback_title
                    return title, normalized
                except Exception:
                    return None, None

            batch_size = getattr(self, "DETAIL_BATCH_SIZE", 10)
            for i in range(0, len(candidates), batch_size):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = candidates[i : i + batch_size]
                chunk_tasks = [
                    self._run_detail_task(
                        detail_semaphore, _fetch_detail, item[0], item[1]
                    )
                    for item in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link and link not in seen_udemy:
                        seen_udemy.add(link)
                        self.append_to_list(title[:200], link)
                        if len(self.data) >= self.MAX_COURSES:
                            break
                self.progress = min(i + len(chunk), len(candidates))
        except Exception:
            self.error = traceback.format_exc()


class FreebiesGlobalScraper(Scraper):
    BASE_URL = "https://freebiesglobal.com"
    LISTING_ENDPOINT = "https://freebiesglobal.com/tag/udemy-100-off"
    MAX_COURSES = 500
    MAX_PAGES = 50
    CANDIDATE_BUFFER = 700
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "FreebiesGlobal"

    @property
    def code_name(self) -> str:
        return "fg"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = self.MAX_PAGES
            self.progress = 0
            seen_udemy: set[str] = set()
            candidates: list[str] = []
            candidate_limit = min(
                getattr(self, "CANDIDATE_BUFFER", 700),
                max(self.MAX_COURSES * 3, 20),
            )
            batch_size = getattr(self, "BATCH_SIZE", 6)
            stop_pagination = False

            for start_page in range(1, self.MAX_PAGES + 1, batch_size):
                if (
                    len(self.data) >= self.MAX_COURSES
                    or len(candidates) >= candidate_limit
                    or len(self.data) + len(candidates) >= candidate_limit
                ):
                    break
                end_page = min(start_page + batch_size, self.MAX_PAGES + 1)
                page_tasks = [
                    self._http_get(
                        f"{self.LISTING_ENDPOINT}/"
                        if p == 1
                        else f"{self.LISTING_ENDPOINT}/page/{p}/",
                        use_cloudscraper=True,
                        timeout=15,
                    )
                    for p in range(start_page, end_page)
                ]
                responses = await asyncio.gather(*page_tasks, return_exceptions=True)

                for page_num, resp in zip(range(start_page, end_page), responses):
                    self.progress = page_num
                    if (
                        isinstance(resp, Exception)
                        or not resp
                        or getattr(resp, "status_code", None) != 200
                        or not getattr(resp, "text", None)
                    ):
                        if page_num == 1 and not self.data and not candidates:
                            self.error = "Failed to fetch listing page 1"
                        stop_pagination = True
                        break

                    soup = self.parse_html(resp.text)
                    articles = soup.find_all("article")
                    if not articles:
                        stop_pagination = True
                        break

                    page_found = 0
                    for art in articles:
                        # Check 0-hop card direct link
                        btn = art.select_one(
                            "a.re_track_btn[href*='udemy.com'], a[href*='udemy.com']"
                        )
                        if btn and btn.get("href"):
                            raw_href = btn["href"]
                            normalized = Course.normalize_link(raw_href)
                            if (
                                is_udemy_course_url(normalized)
                                and normalized not in seen_udemy
                            ):
                                heading = art.find(["h2", "h3", "h4"])
                                title = (
                                    heading.get_text(strip=True)
                                    if heading
                                    else (btn.get("title") or "Course")
                                )
                                seen_udemy.add(normalized)
                                self.append_to_list(title[:200], normalized)
                                page_found += 1
                                if len(self.data) >= self.MAX_COURSES:
                                    stop_pagination = True
                                    break
                                continue

                        # Collect 1-hop detail post URL
                        a_tag = art.find("a")
                        if a_tag and a_tag.get("href"):
                            post_url = a_tag["href"]
                            if (
                                "freebiesglobal.com" in post_url
                                and post_url not in candidates
                            ):
                                candidates.append(post_url)
                                page_found += 1
                                if (
                                    len(candidates) >= candidate_limit
                                    or len(self.data) + len(candidates) >= candidate_limit
                                ):
                                    stop_pagination = True
                                    break

                    if stop_pagination:
                        break
                    if page_num > 1 and page_found == 0:
                        stop_pagination = True
                        break

                if stop_pagination:
                    break

            # Process collected detail candidate pages
            if candidates and len(self.data) < self.MAX_COURSES:
                self.length = len(candidates)

                async def _fetch_post(post_url: str):
                    try:
                        r = await self.http.get(
                            post_url,
                            attempts=1,
                            timeout=8,
                            raise_for_status=False,
                            use_cloudscraper=True,
                        )
                        if not r or r.status_code != 200 or not r.text:
                            return None, None
                        # Fast regex for course URL
                        match = re.search(
                            r'href="(https?://[^"]+/course/[^"]+)"',
                            r.text,
                        )
                        if match:
                            norm = Course.normalize_link(match.group(1))
                            if is_udemy_course_url(norm):
                                h1_match = re.search(
                                    r'<h1[^>]*>(.*?)</h1>', r.text, re.DOTALL
                                )
                                title = (
                                    html.unescape(
                                        re.sub(
                                            r"<[^>]+>", "", h1_match.group(1)
                                        ).strip()
                                    )
                                    if h1_match
                                    else "Course"
                                )
                                return title, norm

                        p_soup = self.parse_html(r.text)
                        btn = p_soup.select_one(
                            "a.btn_offer_block, a.re_track_btn, a[href*='udemy.com'], a.btn_deal"
                        )
                        if btn and btn.get("href"):
                            norm = Course.normalize_link(btn["href"])
                            if is_udemy_course_url(norm):
                                h1 = p_soup.find("h1")
                                title = (
                                    h1.get_text(strip=True) if h1 else "Course"
                                )
                                return title, norm
                        return None, None
                    except Exception:
                        return None, None

                batch_size = getattr(self, "DETAIL_BATCH_SIZE", 10)
                for i in range(0, len(candidates), batch_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break
                    chunk = candidates[i : i + batch_size]
                    chunk_tasks = [
                        self._run_detail_task(
                            detail_semaphore, _fetch_post, url
                        )
                        for url in chunk
                    ]
                    results = await asyncio.gather(
                        *chunk_tasks, return_exceptions=True
                    )
                    for res in results:
                        if isinstance(res, Exception) or not res:
                            continue
                        title, link = res
                        if title and link and link not in seen_udemy:
                            seen_udemy.add(link)
                            self.append_to_list(title[:200], link)
                            if len(self.data) >= self.MAX_COURSES:
                                break
                    self.progress = min(i + len(chunk), len(candidates))
        except Exception:
            self.error = traceback.format_exc()


class GeeksGodScraper(Scraper):
    BASE_URL = "https://geeksgod.com"
    LISTING_ENDPOINT = "https://geeksgod.com/courses"
    MAX_COURSES = 500
    MAX_PAGES = 50
    CANDIDATE_BUFFER = 700
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "GeeksGod"

    @property
    def code_name(self) -> str:
        return "gg"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_pages: set[str] = set()
            candidates: list[tuple[str, str]] = []
            batch_size = getattr(self, "BATCH_SIZE", 6)
            buffer_limit = getattr(self, "CANDIDATE_BUFFER", 700)
            self.length = self.MAX_PAGES

            stop_pagination = False
            for start_page in range(1, self.MAX_PAGES + 1, batch_size):
                if len(candidates) >= buffer_limit:
                    break
                end_page = min(start_page + batch_size, self.MAX_PAGES + 1)
                page_tasks = [
                    self._http_get(
                        f"{self.LISTING_ENDPOINT}?page={p}",
                        use_cloudscraper=True,
                        timeout=15,
                    )
                    for p in range(start_page, end_page)
                ]
                responses = await asyncio.gather(*page_tasks, return_exceptions=True)

                for page_num, resp in zip(range(start_page, end_page), responses):
                    self.progress = page_num
                    if (
                        isinstance(resp, Exception)
                        or not resp
                        or getattr(resp, "status_code", None) != 200
                        or not getattr(resp, "text", None)
                    ):
                        if page_num == 1 and not candidates and not self.data:
                            self.error = "Failed to fetch listing page 1"
                        elif page_num > 1 and (candidates or self.data):
                            self.circuit_open = False
                            self.error = None
                            self.consecutive_failures = 0
                        stop_pagination = True
                        break

                    soup = self.parse_html(resp.text)
                    links = soup.select("a[href^='/course/'], a[href*='/course/']")
                    if not links:
                        stop_pagination = True
                        break

                    new_count = 0
                    for a in links:
                        href = a.get("href")
                        if not href:
                            continue
                        abs_url = urllib.parse.urljoin(self.BASE_URL, href)
                        if abs_url not in seen_pages:
                            seen_pages.add(abs_url)
                            title = a.get_text(strip=True)
                            candidates.append((abs_url, title))
                            new_count += 1
                            if len(candidates) >= buffer_limit:
                                stop_pagination = True
                                break
                    if stop_pagination or new_count == 0:
                        stop_pagination = True
                        break

                if stop_pagination:
                    break

            if not candidates:
                return

            candidates = candidates[:buffer_limit]
            self.length = len(candidates)
            self.progress = 0
            seen_udemy: set[str] = set()

            async def _fetch_detail(detail_url: str, fallback_title: str):
                try:
                    resp = await self._http_get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not resp or resp.status_code != 200 or not resp.text:
                        return None, None
                    soup = self.parse_html(resp.text)
                    btn = soup.select_one(
                        "a.btn--primary[href*='udemy.com'], a.btn--primary[href], a[href*='udemy.com']"
                    )
                    if not btn or not btn.get("href"):
                        return None, None
                    raw_href = btn["href"]
                    normalized = Course.normalize_link(raw_href)
                    if not is_udemy_course_url(normalized):
                        return None, None

                    h1 = soup.find("h1")
                    title = h1.get_text(strip=True) if h1 else fallback_title
                    if not title or self._is_generic_course_title(title):
                        title = fallback_title
                    return title, normalized
                except Exception:
                    return None, None

            batch_size = getattr(self, "DETAIL_BATCH_SIZE", 10)
            for i in range(0, len(candidates), batch_size):
                if len(self.data) >= self.MAX_COURSES:
                    break
                chunk = candidates[i : i + batch_size]
                chunk_tasks = [
                    self._run_detail_task(
                        detail_semaphore, _fetch_detail, item[0], item[1]
                    )
                    for item in chunk
                ]
                results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception) or not res:
                        continue
                    title, link = res
                    if title and link and link not in seen_udemy:
                        seen_udemy.add(link)
                        self.append_to_list(title[:200], link)
                        if len(self.data) >= self.MAX_COURSES:
                            break
                self.progress = min(i + len(chunk), len(candidates))
        except Exception:
            self.error = traceback.format_exc()


class TutorialBarScraper(Scraper):
    BASE_URL = "https://www.tutorialbar.com"
    LISTING_ENDPOINT = "https://www.tutorialbar.com/live-coupons"
    MAX_COURSES = 500
    MAX_PAGES = 50
    CANDIDATE_BUFFER = 750
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "TutorialBar"

    @property
    def code_name(self) -> str:
        return "tb"

    def _unescape_rsc_string(self, raw: str) -> str:
        if not raw:
            return ""
        text = (
            raw.replace(r"\u0026", "&")
            .replace(r"\u002F", "/")
            .replace(r"\/", "/")
            .replace(r'\"', '"')
            .replace(r"\\", "\\")
        )
        return html.unescape(text).strip()

    def _extract_from_rsc(self, raw_text: str) -> list[tuple[str, str]]:
        results = []
        if not raw_text:
            return results

        # 1. Match Next.js RSC course objects with negative lookahead preventing cross-course bleeding
        p1 = re.findall(
            r'\\?"course\\?":\s*\{(?:(?!\\?"course\\?":).)*?\\?"title\\?":\s*\\?"((?:\\.|[^"\\])+?)\\?"(?:(?!\\?"course\\?":).)*?\\?"couponUrl\\?":\s*\\?"(https:[^"\\]+?)\\?"',
            raw_text,
            re.DOTALL,
        )
        p2 = re.findall(
            r'\\?"course\\?":\s*\{(?:(?!\\?"course\\?":).)*?\\?"couponUrl\\?":\s*\\?"(https:[^"\\]+?)\\?"(?:(?!\\?"course\\?":).)*?\\?"title\\?":\s*\\?"((?:\\.|[^"\\])+?)\\?"',
            raw_text,
            re.DOTALL,
        )
        for title_match, url_match in p1:
            clean_title = self._unescape_rsc_string(title_match)
            clean_url = self._unescape_rsc_string(url_match)
            if clean_title and clean_url:
                results.append((clean_title, clean_url))
        for url_match, title_match in p2:
            clean_title = self._unescape_rsc_string(title_match)
            clean_url = self._unescape_rsc_string(url_match)
            if clean_title and clean_url and (clean_title, clean_url) not in results:
                results.append((clean_title, clean_url))

        # 2. Fallback for un-nested flight formats (e.g. synthetic test fixtures)
        if not results:
            f1 = re.findall(
                r'\{(?:(?!\{).)*?\\?"title\\?":\s*\\?"((?:\\.|[^"\\])+?)\\?"(?:(?!\{).)*?\\?"couponUrl\\?":\s*\\?"(https:[^"\\]+?)\\?"',
                raw_text,
                re.DOTALL,
            )
            f2 = re.findall(
                r'\{(?:(?!\{).)*?\\?"couponUrl\\?":\s*\\?"(https:[^"\\]+?)\\?"(?:(?!\{).)*?\\?"title\\?":\s*\\?"((?:\\.|[^"\\])+?)\\?"',
                raw_text,
                re.DOTALL,
            )
            for title_match, url_match in f1:
                clean_title = self._unescape_rsc_string(title_match)
                clean_url = self._unescape_rsc_string(url_match)
                if clean_title and clean_url:
                    results.append((clean_title, clean_url))
            for url_match, title_match in f2:
                clean_title = self._unescape_rsc_string(title_match)
                clean_url = self._unescape_rsc_string(url_match)
                if clean_title and clean_url and (clean_title, clean_url) not in results:
                    results.append((clean_title, clean_url))

        return results

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_pages: set[str] = set()
            seen_udemy: set[str] = set()
            candidates: list[tuple[str, str]] = []

            for page_num in range(1, self.MAX_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break
                url = (
                    f"{self.LISTING_ENDPOINT}"
                    if page_num == 1
                    else f"{self.LISTING_ENDPOINT}?page={page_num}"
                )
                resp = await self._http_get(
                    url, use_cloudscraper=True, timeout=15
                )
                if not resp or resp.status_code != 200 or not resp.text:
                    if page_num == 1 and not self.data:
                        self.error = "Failed to fetch listing page 1"
                    break

                page_text = resp.text
                page_extracted = 0

                # 1. Primary 0-hop RSC Flight payload extraction
                rsc_items = self._extract_from_rsc(page_text)
                for raw_title, raw_url in rsc_items:
                    normalized = Course.normalize_link(raw_url)
                    if is_udemy_course_url(normalized) and normalized not in seen_udemy:
                        seen_udemy.add(normalized)
                        self.append_to_list(raw_title[:200], normalized)
                        page_extracted += 1
                        if len(self.data) >= self.MAX_COURSES:
                            break

                if len(self.data) >= self.MAX_COURSES:
                    break

                # 2. Secondary 0-hop DOM card extraction if RSC yielded 0
                soup = self.parse_html(page_text)
                if page_extracted == 0:
                    cards = soup.select("div.coupon-card, div.card, article")
                    for card in cards:
                        btn = card.select_one(
                            "a.btn-primary[href*='udemy.com'], a[href*='udemy.com']"
                        )
                        if btn and btn.get("href"):
                            raw_url = btn["href"]
                            normalized = Course.normalize_link(raw_url)
                            if (
                                is_udemy_course_url(normalized)
                                and normalized not in seen_udemy
                            ):
                                heading = card.find(["h2", "h3", "h4"])
                                title = (
                                    heading.get_text(strip=True)
                                    if heading
                                    else (btn.get("title") or "Unknown")
                                )
                                seen_udemy.add(normalized)
                                self.append_to_list(title[:200], normalized)
                                page_extracted += 1
                                if len(self.data) >= self.MAX_COURSES:
                                    break

                # 3. Fallback detail page collection if 0 items on page
                if page_extracted == 0:
                    course_links = soup.select(
                        ".coupon-card a[href^='/course/'], main a[href^='/course/'], a[href*='/course/']"
                    )
                    for a in course_links:
                        href = a.get("href")
                        if href:
                            abs_url = urllib.parse.urljoin(self.BASE_URL, href)
                            if abs_url not in seen_pages:
                                seen_pages.add(abs_url)
                                title = a.get_text(strip=True)
                                candidates.append((abs_url, title))

                self.progress = page_num
                if page_extracted == 0 and not candidates:
                    break

            # If candidates were collected for 1-hop detail fallback
            if candidates and len(self.data) < self.MAX_COURSES:
                self.length = len(candidates)

                async def _fetch_detail(detail_url: str, fallback_title: str):
                    try:
                        resp = await self._http_get(
                            detail_url, use_cloudscraper=True, timeout=15
                        )
                        if not resp or resp.status_code != 200 or not resp.text:
                            return None, None
                        # Check RSC or JSON-LD in detail page
                        rsc_detail = self._extract_from_rsc(resp.text)
                        for dt, du in rsc_detail:
                            norm = Course.normalize_link(du)
                            if is_udemy_course_url(norm):
                                return dt or fallback_title, norm

                        soup = self.parse_html(resp.text)
                        btn = soup.select_one(
                            "a.btn-primary[href*='udemy.com'], a[href*='udemy.com']"
                        )
                        if btn and btn.get("href"):
                            norm = Course.normalize_link(btn["href"])
                            if is_udemy_course_url(norm):
                                h1 = soup.find("h1")
                                title = (
                                    h1.get_text(strip=True)
                                    if h1
                                    else fallback_title
                                )
                                return title, norm
                        return None, None
                    except Exception:
                        return None, None

                batch_size = getattr(self, "DETAIL_BATCH_SIZE", 10)
                for i in range(0, len(candidates), batch_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break
                    chunk = candidates[i : i + batch_size]
                    chunk_tasks = [
                        self._run_detail_task(
                            detail_semaphore, _fetch_detail, item[0], item[1]
                        )
                        for item in chunk
                    ]
                    results = await asyncio.gather(
                        *chunk_tasks, return_exceptions=True
                    )
                    for res in results:
                        if isinstance(res, Exception) or not res:
                            continue
                        title, link = res
                        if title and link and link not in seen_udemy:
                            seen_udemy.add(link)
                            self.append_to_list(title[:200], link)
                            if len(self.data) >= self.MAX_COURSES:
                                break
                    self.progress = min(i + len(chunk), len(candidates))
        except Exception:
            self.error = traceback.format_exc()


SCRAPER_REGISTRY = {
    "FreeCourseSites": FreeCourseSitesScraper,
    "E-next": ENextScraper,
    "Interview Gig": InterviewGigScraper,
    "UdemyXpert": UdemyXpertScraper,
    "Coursesity": CoursesityScraper,
    "Course Folder": CourseFolderScraper,
    "Couponami": CouponamiScraper,
    "Korshub": KorshubScraper,
    "UdemyFreebies": UdemyFreebiesScraper,
    "iDownloadCoupon": IDownloadCouponScraper,
    "Courson": CoursonScraper,
    "CouponScorpion": CouponScorpionScraper,
    "Real Discount": RealDiscountScraper,
    "OnlineCourses.ooo": OnlineCoursesScraper,
    "FreebiesGlobal": FreebiesGlobalScraper,
    "GeeksGod": GeeksGodScraper,
    "TutorialBar": TutorialBarScraper,
}


class ScraperService:
    def __init__(
        self,
        sites_to_scrape: Optional[List[str]] = None,
        proxy: Optional[str] = None,
        max_workers: Optional[int] = None,
    ):
        self.max_workers = max_workers
        self.http = AsyncHTTPClient(proxy=proxy)
        self.sites = sites_to_scrape or list(SCRAPER_REGISTRY.keys())
        self.scrapers: List[Scraper] = []
        self.site_to_scraper: Dict[str, Scraper] = {}

        # Deduplicate scrapers by class to avoid running the same logic multiple times
        # while keeping a mapping of which requested site maps to which instance.
        class_to_instance = {}
        for site in self.sites:
            if site in SCRAPER_REGISTRY:
                scraper_cls = SCRAPER_REGISTRY[site]
                if scraper_cls not in class_to_instance:
                    instance = scraper_cls(self.http, proxy=proxy)
                    class_to_instance[scraper_cls] = instance
                    self.scrapers.append(instance)
                self.site_to_scraper[site] = class_to_instance[scraper_cls]

    async def stream_results(self):
        """Yield each scraper as it finishes: (scraper_instance, state)."""
        from config.settings import get_settings

        settings = get_settings()

        raw_workers = self.max_workers if self.max_workers is not None else getattr(settings, "MAX_SCRAPER_WORKERS", 6)
        worker_concurrency = raw_workers if isinstance(raw_workers, int) else 6
        worker_sem = asyncio.Semaphore(max(1, min(worker_concurrency, 32)))

        raw_detail = getattr(settings, "SCRAPER_DETAIL_CONCURRENCY", 6)
        detail_concurrency = raw_detail if isinstance(raw_detail, int) else 6

        if not hasattr(self, "source_states"):
            self.source_states = {id(s): "queued" for s in self.scrapers}

        async def _run_scraper(scraper: Scraper):
            async with worker_sem:
                self.source_states[id(scraper)] = "scraping"
                logger.warning(f"  Scraper started: {scraper.site_name}")
                detail_sem = asyncio.Semaphore(max(1, min(detail_concurrency, 32)))

                try:
                    await asyncio.wait_for(
                        scraper.scrape(detail_sem),
                        timeout=settings.SCRAPER_SITE_TIMEOUT_SECONDS,
                    )
                    state = "failed" if scraper.error else "completed"
                    self.source_states[id(scraper)] = state
                    return scraper, state
                except asyncio.TimeoutError:
                    logger.error(f"  Scraper timed out: {scraper.site_name}")
                    scraper.error = (
                        f"Timed out after {settings.SCRAPER_SITE_TIMEOUT_SECONDS}s"
                    )
                    scraper.done = True
                    self.source_states[id(scraper)] = "timed_out"
                    return scraper, "timed_out"
                except asyncio.CancelledError:
                    scraper.done = True
                    if self.source_states.get(id(scraper)) == "scraping":
                        self.source_states[id(scraper)] = "timed_out"
                        return scraper, "timed_out"
                    raise
                except Exception as e:
                    logger.error(f"  Scraper failed: {scraper.site_name} - {e}")
                    scraper.error = str(e)
                    scraper.done = True
                    self.source_states[id(scraper)] = "failed"
                    return scraper, "failed"
                finally:
                    scraper.done = True

        tasks = [asyncio.create_task(_run_scraper(s)) for s in self.scrapers]
        task_to_scraper = {task: scraper for task, scraper in zip(tasks, self.scrapers)}
        pending = set(tasks)
        fleet_timeout_fired = False

        try:
            loop = asyncio.get_event_loop()
            end_time = loop.time() + settings.SCRAPER_RUN_TIMEOUT_SECONDS

            def _cancel_inflight():
                for task in list(pending):
                    scraper = task_to_scraper[task]
                    if self.source_states.get(id(scraper)) == "scraping":
                        task.cancel()

            while pending:
                wait_timeout = None
                if not fleet_timeout_fired:
                    timeout_left = end_time - loop.time()
                    if timeout_left <= 0:
                        _cancel_inflight()
                        fleet_timeout_fired = True
                    else:
                        wait_timeout = timeout_left

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED, timeout=wait_timeout
                )

                if not done and not fleet_timeout_fired:
                    _cancel_inflight()
                    fleet_timeout_fired = True
                    continue

                for task in done:
                    scraper = task_to_scraper[task]
                    try:
                        result_scraper, state = task.result()
                        yield result_scraper, state
                    except asyncio.CancelledError:
                        scraper.done = True
                        if self.source_states.get(id(scraper)) == "scraping":
                            self.source_states[id(scraper)] = "timed_out"
                            yield scraper, "timed_out"

        except asyncio.CancelledError:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise

    async def scrape_all(self) -> List[Course]:
        logger.warning(f"Starting scrape for: {self.sites}")

        # Consume the stream but just collect
        async for scraper, state in self.stream_results():
            if scraper.error:
                logger.warning(
                    f"  Scraper finished: {scraper.site_name} (Found {len(scraper.data)} courses, State: {state}, Error: {scraper.error})"
                )
            else:
                logger.warning(
                    f"  Scraper finished: {scraper.site_name} (Found {len(scraper.data)} courses, State: {state})"
                )

        all_data = []
        for s in self.scrapers:
            all_data.extend(s.data)

        unique_data = {c.url: c for c in all_data}.values()
        logger.warning(
            f"Scraping complete. Found {len(unique_data)} unique courses across {len(self.scrapers)} unique scraper engines."
        )
        return list(unique_data)

    async def close(self):
        """Close the shared HTTP client."""
        await self.http.close()

    def get_progress(self) -> List[dict]:
        """Return progress for all REQUESTED sites, even if they share an instance."""
        results = []
        states = getattr(self, "source_states", {})
        for site_name in self.sites:
            if site_name in self.site_to_scraper:
                s = self.site_to_scraper[site_name]
                state = states.get(id(s), "queued")
                if s.done and state in ("queued", "scraping"):
                    state = "failed" if s.error else "completed"

                results.append(
                    {
                        "site": site_name,
                        "progress": s.progress,
                        "total": s.length,
                        "done": s.done,
                        "error": s.error,
                        "state": state,
                        "courses_found": len(s.data),
                    }
                )
        return results
