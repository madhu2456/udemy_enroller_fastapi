"""Course scraper service - standard emulated client logic (No Playwright for enrollment, Playwright allowed for scraping fallback)."""

import asyncio
import random
import re
import traceback
import urllib.parse
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union

from bs4 import BeautifulSoup
from loguru import logger

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient, _log_safe_url
from app.services.robots_gate import RobotsGate
from app.services.udemy_validation import (
    is_trk_udemy_url,
    is_udemy_course_url,
    is_udemy_url,
)


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

        try:
            resp = await self.http.get(
                trk_url,
                use_cloudscraper=True,
                follow_redirects=True,
                raise_for_status=False,
                log_failures=False,
                randomize_headers=True,
                timeout=15,
                attempts=2,
            )
            if resp:
                resolved = str(resp.url)
                if is_udemy_course_url(resolved):
                    resolved_norm = Course.normalize_link(resolved)
                    if outer_coupon and "couponCode=" not in resolved_norm:
                        separator = "&" if "?" in resolved_norm else "?"
                        resolved_norm += f"{separator}couponCode={outer_coupon}"
                    return resolved_norm
        except Exception as e:
            logger.debug(f"GET fallback redirect resolution failed for {trk_url}: {e}")
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
        """
        try:
            from playwright.async_api import async_playwright

            stealth_async = None
            try:
                from playwright_stealth import stealth_async
            except (ImportError, ModuleNotFoundError):
                logger.warning("  playwright_stealth not found, proceeding without it.")

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

                browser = await p.chromium.launch(**launch_kwargs)
                try:
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        locale="en-US",
                    )
                    page = await context.new_page()

                    if stealth_async:
                        await stealth_async(page)

                    await asyncio.sleep(random.uniform(1, 3))

                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                    if wait_selector:
                        try:
                            await page.wait_for_selector(wait_selector, timeout=10000)
                        except Exception:
                            pass

                    await asyncio.sleep(3)

                    content = await page.content()

                    # Check for Cloudflare block
                    if (
                        "Just a moment..." in content
                        or "cf-browser-verification" in content
                        or "Attention Required!" in content
                    ):
                        logger.warning(
                            f"  Playwright hit Cloudflare block on {url}, waiting 10 more seconds..."
                        )
                        await asyncio.sleep(20)
                        content = await page.content()
                        if (
                            "Just a moment..." in content
                            or "cf-browser-verification" in content
                        ):
                            raise Exception(
                                "Cloudflare challenge unresolved by Playwright."
                            )

                    return content
                finally:
                    await browser.close()
        except Exception as e:
            logger.warning(f"  Playwright fetch failed for {url}: {e}")
            return ""


class RealDiscountScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Real Discount"

    @property
    def code_name(self) -> str:
        return "rd"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 1  # Single API call
            url = "https://cdn.real.discount/api/courses?page=1&limit=500&sortBy=sale_start&store=Udemy&freeOnly=true"
            headers = {
                "referer": "https://www.real.discount/",
                "Host": "cdn.real.discount",
            }
            resp = await self._http_get(url, headers=headers)
            data = await self.http.safe_json(resp)

            if resp is None or not data or "items" not in data:
                self.error = "API unreachable; Playwright skipped"
                logger.info("  Real Discount: API unreachable; Playwright skipped")
                return

            items = data.get("items", [])
            self.length = len(items)

            for i, item in enumerate(items):
                if item.get("store") == "Sponsored":
                    self.progress = i + 1
                    continue
                title = item.get("name")
                url = item.get("url")
                if title and url:
                    self.append_to_list(title, url)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class ENextScraper(Scraper):
    MAX_COURSES = 500
    MAX_LISTING_PAGES = 50
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
                    resp = await self.http.get(
                        item["href"], use_cloudscraper=True, timeout=10
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

            for page in range(1, self.MAX_LISTING_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break
                self.progress = page

                resp = await self._http_get(
                    f"https://jobs.e-next.in/course/udemy/{page}"
                )
                if not resp or resp.status_code != 200:
                    break

                soup = self.parse_html(resp.content)
                buttons = soup.find_all(
                    "a", {"class": "btn btn-secondary btn-sm btn-block"}
                )
                if not buttons:
                    break

                pending_items = []
                for btn in buttons:
                    href = btn.get("href")
                    if href and href not in seen_detail_urls:
                        seen_detail_urls.add(href)
                        pending_items.append(btn)

                chunk_size = self.DETAIL_BATCH_SIZE
                for i in range(0, len(pending_items), chunk_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break

                    chunk = pending_items[i : i + chunk_size]
                    detail_tasks = [
                        self._run_detail_task(detail_semaphore, _fetch_details, item)
                        for item in chunk
                    ]

                    results_list = await asyncio.gather(
                        *detail_tasks, return_exceptions=True
                    )
                    for results in results_list:
                        if isinstance(results, Exception):
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
    Short trk hops go through _resolve_one + a local Semaphore(8), chunked,
    with at most 80 scheduled trk HTTP calls.
    """

    MAX_COURSES = 500
    MAX_API_PAGES = 4
    MAX_TRK_HTTP = 80
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

            page_tasks = []
            for page in range(1, self.MAX_API_PAGES + 1):
                url = f"{base_api}?per_page=100&page={page}"
                page_tasks.append(self._http_get(url, use_cloudscraper=True, timeout=20))

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

            local_trk_sem = asyncio.Semaphore(8)
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
            resp = await self._http_get(
                "https://udemyxpert.com/sitemap.xml", use_cloudscraper=True, timeout=20
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
            max_courses = 500

            async def _fetch_detail(page_url: str):
                try:
                    page = await self.http.get(
                        page_url, use_cloudscraper=True, timeout=15
                    )
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

            # Cap at 500 to keep it fast
            urls_to_fetch = course_urls[:max_courses]
            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, url)
                for url in urls_to_fetch
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  UdemyXpert: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CoursesityScraper(Scraper):
    """Coursesity (coursesity.com) — paginated listing + detail page scraper.
    Free Udemy courses listing at /provider/free/udemy-courses.
    Each listing page has 15 courses; detail pages contain the direct
    Udemy course URL embedded in JavaScript strings.

    NOTE: Coursesity does NOT provide coupon codes on its detail pages.
    The extracted URLs are plain Udemy course links without coupons.
    A ~498-class URL yield without couponCode= is expected.
    These courses were free at the time of listing but may require
    payment or may no longer be available for free enrollment.
    """

    @property
    def site_name(self) -> str:
        return "Coursesity"

    @property
    def code_name(self) -> str:
        return "cs"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_courses = 500
            courses_per_page = 15
            max_pages = (max_courses // courses_per_page) + 2

            detail_urls: list[str] = []

            # Step 1: Fetch listing pages sequentially to collect detail URLs
            self.length = max_pages
            for page_num in range(1, max_pages + 1):
                self.progress = page_num
                url = (
                    f"https://coursesity.com/provider/free/udemy-courses"
                    f"?page={page_num}"
                )
                try:
                    resp = await self._http_get(url, use_cloudscraper=True, timeout=15)
                    if not resp or resp.status_code != 200:
                        break

                    text = resp.text
                    links = re.findall(r'href="(/course-detail/[^"]+)"', text)
                    unique = list(dict.fromkeys(links))
                    if not unique:
                        break

                    for link in unique:
                        detail_urls.append(f"https://coursesity.com{link}")

                    if len(detail_urls) >= max_courses:
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

            self.length = len(detail_urls)
            self.progress = 0
            logger.info(f"  Coursesity: Found {len(detail_urls)} detail URLs to fetch")

            # Step 2: Fetch detail pages concurrently
            async def _fetch_detail(detail_url: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    # Extract Udemy course URL from JS strings
                    matches = re.findall(
                        r'["\'](https?://[^"\']+)["\']',
                        text,
                    )
                    # Filter out image URLs (udemycdn.com is already excluded by regex)
                    udemy_url = None
                    for m in matches:
                        if ".jpg" in m or ".png" in m or ".jpeg" in m:
                            continue
                        if is_udemy_course_url(m):
                            udemy_url = m
                            break

                    if not udemy_url:
                        return None, None

                    # Extract title from page
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
                        title = re.sub(
                            r"\s*[-|]\s*Free Online Course.*",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        ).strip()

                    return title or "Unknown", udemy_url
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, url)
                for url in detail_urls[:max_courses]
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  Coursesity: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CourseFolderScraper(Scraper):
    """Course Folder (coursefolder.net) — paginated listing + detail page scraper.
    Free Udemy coupons at /free-udemy-coupon.php.
    Each listing page has ~50 courses; detail pages contain direct
    Udemy links with coupon codes in anchor tags.
    """

    @property
    def site_name(self) -> str:
        return "Course Folder"

    @property
    def code_name(self) -> str:
        return "cf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_courses = 500
            courses_per_page = 50
            max_pages = (max_courses // courses_per_page) + 2
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
                    if len(detail_urls) >= max_courses:
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

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

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, url)
                for url in detail_urls[:max_courses]
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  Course Folder: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CouponamiScraper(Scraper):
    """Couponami (couponami.com) — sitemap-based scraper.
    Uses WordPress post sitemaps to get all course URLs, then fetches
    /go/{slug} redirect pages which embed direct Udemy links with coupons.
    """

    @property
    def site_name(self) -> str:
        return "Couponami"

    @property
    def code_name(self) -> str:
        return "ca"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_courses = 500

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

                    if len(detail_urls) >= max_courses:
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

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

            go_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_go, url)
                for url in detail_urls[:max_courses]
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(go_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  Couponami: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class KorshubScraper(Scraper):
    """Korshub (korshub.com) — paginated listing + detail page scraper.
    Free/discounted Udemy courses at /courses.
    Listing cards are /courses/{one-segment}. Detail pages yield only
    on-page is_udemy_course_url hrefs or a same-origin /go/{uuid} hop
    (at most one extra www↔apex /go/{uuid} 301).
    """

    GO_NETLOCS = frozenset({"korshub.com", "www.korshub.com"})
    GO_PATH_RE = re.compile(r"^/go/[A-Za-z0-9_-]+$")

    @property
    def site_name(self) -> str:
        return "Korshub"

    @property
    def code_name(self) -> str:
        return "kh"

    def _listing_detail_url(self, href: str) -> Optional[str]:
        candidate = urllib.parse.urljoin("https://www.korshub.com/", href)
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower().split(":")[0]
        if host not in self.GO_NETLOCS:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2 or parts[0] != "courses" or not parts[1]:
            return None
        return f"https://www.korshub.com/courses/{parts[1]}"

    def _allowed_go_hop(self, href: str, base: str) -> Optional[str]:
        candidate = urllib.parse.urljoin(base, href)
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower().split(":")[0]
        if host not in self.GO_NETLOCS:
            return None
        if not self.GO_PATH_RE.fullmatch(parsed.path or ""):
            return None
        return f"https://www.korshub.com{parsed.path}"

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

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen: set[str] = set()
            max_courses = 500
            courses_per_page = 10
            max_pages = (max_courses // courses_per_page) + 2

            detail_urls: list[str] = []

            # Step 1: Fetch listing pages sequentially
            self.length = max_pages
            for page_num in range(0, max_pages):
                self.progress = page_num + 1
                url = f"https://www.korshub.com/courses?page={page_num}"
                try:
                    resp = await self._http_get(
                        url, use_cloudscraper=True, timeout=15, retry_403=True
                    )
                    if not resp or resp.status_code != 200:
                        if page_num <= 1:
                            break
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")
                    page_urls: set[str] = set()
                    for a in soup.find_all("a", href=True):
                        detail = self._listing_detail_url(a["href"])
                        if detail:
                            page_urls.add(detail)

                    if not page_urls:
                        break

                    detail_urls.extend(sorted(page_urls))
                    if len(detail_urls) >= max_courses:
                        break
                except Exception:
                    continue

            if not detail_urls:
                return

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
                    soup = self.parse_html(text)

                    udemy_url = None
                    for a in soup.find_all("a", href=True):
                        href = a.get("href", "")
                        if is_udemy_course_url(href):
                            udemy_url = href
                            break
                    if not udemy_url:
                        for m in re.findall(r'href=["\'](https?://[^"\']+)["\']', text):
                            if is_udemy_course_url(m):
                                udemy_url = m
                                break

                    if not udemy_url:
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

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_detail, url)
                for url in detail_urls[:max_courses]
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen:
                        seen.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

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

    @property
    def site_name(self) -> str:
        return "UdemyFreebies"

    @property
    def code_name(self) -> str:
        return "uf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_slugs: set[str] = set()
            max_courses = 500
            courses_per_page = 12
            max_pages = (max_courses // courses_per_page) + 2

            # Step 1: Fetch listing pages concurrently to collect slugs and titles
            logger.info("  UdemyFreebies: Fetching listing pages...")
            listing_results: list[tuple[str, str]] = []

            self.length = max_pages
            page_tasks = []
            for page_num in range(1, max_pages + 1):
                url = f"https://www.udemyfreebies.com/free-udemy-courses/{page_num}"
                page_tasks.append(self._http_get(url, use_cloudscraper=True, timeout=15))

            for i, task in enumerate(asyncio.as_completed(page_tasks)):
                self.progress = i + 1
                try:
                    resp = await task
                    if not resp or resp.status_code != 200:
                        continue

                    soup = self.parse_html(resp.content)
                    coupon_names = soup.find_all("div", class_="coupon-name")

                    for name_div in coupon_names:
                        a = name_div.find("a", href=True)
                        if not a:
                            continue

                        href = a.get("href", "")
                        if "/free-udemy-course/" not in href:
                            continue

                        # Extract slug
                        parts = href.split("/free-udemy-course/")
                        if len(parts) < 2:
                            continue
                        slug = parts[-1].split("?")[0].split("#")[0].rstrip("/")
                        if not slug or slug in seen_slugs:
                            continue
                        seen_slugs.add(slug)

                        title = a.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue

                        listing_results.append((slug, title))

                    if len(listing_results) >= max_courses:
                        break
                except Exception:
                    continue

            if not listing_results:
                logger.warning("  UdemyFreebies: No courses found in listings")
                return

            # Trim to max courses
            listing_results = listing_results[:max_courses]
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
                        attempts=1,
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
                        if len(parts) == 1 and re.fullmatch(
                            r"[A-Za-z0-9_-]+", parts[0]
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

            local_detail_semaphore = asyncio.Semaphore(8)

            async def _limited_resolve(slug: str, title: str):
                async with local_detail_semaphore:
                    return await self._run_detail_task(
                        detail_semaphore, _resolve_out, slug, title
                    )

            detail_tasks = [
                _limited_resolve(slug, title) for slug, title in listing_results
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_urls:
                        seen_urls.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  UdemyFreebies: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class IDownloadCouponScraper(Scraper):
    """iDownloadCoupon (idownloadcoupon.com) — WooCommerce-based course listing.
    Listing pages at /page/{n}/ contain course product cards.
    Each course links to /udemy/{id}/{slug}/ with a "REDEEM OFFER"
    button at /udemy/{id}/ that returns a 302 redirect.
    The redirect location contains a trk.udemy.com URL with a `u=`
    parameter holding the actual Udemy course URL + coupon code.
    """

    @property
    def site_name(self) -> str:
        return "iDownloadCoupon"

    @property
    def code_name(self) -> str:
        return "idc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_ids: set[str] = set()
            max_courses = 500
            courses_per_page = 15
            max_pages = (max_courses // courses_per_page) + 2

            # Step 1: Fetch listing pages concurrently to collect IDs and titles
            logger.info("  iDownloadCoupon: Fetching listing pages...")
            listing_results: list[tuple[str, str]] = []

            self.length = max_pages
            local_listing_semaphore = asyncio.Semaphore(8)

            async def fetch_page(url):
                async with local_listing_semaphore:
                    return await self._http_get(url, use_cloudscraper=True, timeout=15)

            page_tasks = []
            for page_num in range(1, max_pages + 1):
                url = f"https://idownloadcoupon.com/page/{page_num}/"
                page_tasks.append(fetch_page(url))

            results = await asyncio.gather(*page_tasks, return_exceptions=True)
            for i, resp in enumerate(results):
                self.progress = i + 1
                try:
                    if isinstance(resp, Exception):
                        continue
                    if not resp or resp.status_code != 200:
                        continue

                    soup = self.parse_html(resp.content)
                    for a in soup.find_all("a", href=True):
                        href = a.get("href", "")
                        # Match title links: /udemy/{numeric_id}/{slug}/
                        match = re.search(r"/udemy/(\d+)/[^/]+/?$", href)
                        if not match:
                            continue

                        cid = match.group(1)
                        if cid in seen_ids:
                            continue
                        seen_ids.add(cid)

                        title = a.get_text(strip=True)
                        # Skip generic / empty titles
                        if not title or title.lower() in {
                            "redeem offer",
                            "udemy",
                            "sale!",
                        }:
                            continue
                        if len(title) < 3:
                            continue

                        listing_results.append((cid, title))

                    if len(listing_results) >= max_courses:
                        break
                except Exception:
                    continue

            if not listing_results:
                logger.warning("  iDownloadCoupon: No courses found in listings")
                return

            listing_results = listing_results[:max_courses]
            self.length = len(listing_results)
            self.progress = 0
            logger.info(
                f"  iDownloadCoupon: Found {len(listing_results)} unique IDs, resolving redirects..."
            )

            # Step 2: Resolve /udemy/{id}/ redirects concurrently
            seen_urls: set[str] = set()

            async def _resolve_redeem(cid: str, title: str):
                try:
                    redeem_url = f"https://idownloadcoupon.com/udemy/{cid}/"
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

                    location = resp.headers.get("location") or resp.headers.get(
                        "Location"
                    ) or ""
                    if not location:
                        return None, None

                    location = urllib.parse.urljoin(redeem_url, location)
                    if is_udemy_course_url(location):
                        return title, location
                    if not is_trk_udemy_url(location):
                        return None, None

                    udemy_url = await self._resolve_trk_redirect(location)
                    if not udemy_url or not is_udemy_course_url(udemy_url):
                        return None, None

                    return title, udemy_url
                except Exception:
                    return None, None

            local_detail_semaphore = asyncio.Semaphore(8)

            async def _limited_resolve(cid: str, title: str):
                async with local_detail_semaphore:
                    return await self._run_detail_task(
                        detail_semaphore, _resolve_redeem, cid, title
                    )

            detail_tasks = [
                _limited_resolve(cid, title) for cid, title in listing_results
            ]

            found = 0
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_urls:
                        seen_urls.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1

            logger.info(f"  iDownloadCoupon: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class FreeCourseSitesScraper(Scraper):
    BASE_URL = "https://freecoursesites.com"
    CATEGORY_SOURCES = [
        {"slug": "100-off-udemy-coupon", "fallback_id": 137426},
        {"slug": "free-udemy-courses", "fallback_id": 67983},
    ]
    PER_PAGE = 100
    MAX_COURSES = 500
    MAX_REST_PAGES = 5
    MAX_FALLBACK_ARCHIVE_PAGES = 50

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

    async def _scrape_html_fallback(
        self,
        detail_semaphore: asyncio.Semaphore,
        seen_urls: set[str],
    ) -> None:
        logger.info(f"  {self.site_name}: Using HTML fallback")
        no_new_links_count = 0

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
            if len(self.data) >= self.MAX_COURSES:
                break

            slug = source["slug"]
            logger.info(f"  {self.site_name}: HTML fallback scraping category {slug}")
            no_new_links_count = 0

            for page in range(1, self.MAX_FALLBACK_ARCHIVE_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break

                if page == 1:
                    url = f"{self.BASE_URL}/category/{slug}/"
                else:
                    url = f"{self.BASE_URL}/category/{slug}/page/{page}/"

                resp = await self._http_get(
                    url, use_cloudscraper=True, timeout=20, raise_for_status=False
                )
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

    async def _scrape_rest_api(self, seen_urls: set[str]) -> None:
        for source in self.CATEGORY_SOURCES:
            if len(self.data) >= self.MAX_COURSES:
                break

            slug = source["slug"]
            fallback_id = source["fallback_id"]
            cat_id = await self._get_category_id(slug, fallback_id)

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

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_urls: set[str] = set()
            await self._scrape_rest_api(seen_urls)
            if len(self.data) < self.MAX_COURSES:
                await self._scrape_html_fallback(detail_semaphore, seen_urls)
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
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_udemy:
                        seen_udemy.add(normalized)
                        self.append_to_list(title[:200], link)
                        found += 1
                self.progress = i + 1
            logger.info(f"  Discudemy: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


class CoursonScraper(Scraper):
    """Courson (courson.xyz) — HTTP-only /coupon/{slug} scraper.

    Parses window.courseData on coupon pages. Never fetches /claim/ (robots
    Disallow) and never uses Playwright.
    """

    BASE_URL = "https://courson.xyz"
    HOSTS = frozenset({"courson.xyz", "www.courson.xyz"})
    MAX_COUPON_PAGES = 80

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
            coupon_urls: list[str] = []
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

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_coupon, url)
                for url in coupon_urls
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_udemy:
                        seen_udemy.add(normalized)
                        self.append_to_list(title[:200], link)
                self.progress = i + 1
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
        "?categories=21032&per_page=100&page={n}&orderby=date&order=desc"
        "&_fields=id,link,title"
    )
    HTML_LISTING = "https://couponscorpion.com/category/100-off-coupons/"
    MAX_COURSES = 500
    SKIP_PATH_PREFIXES = ("/category/", "/page/", "/scripts/")
    SKIP_PATH_SUBSTRINGS = (
        "/bootstrap-4-tutarial-for-beginners-with-projects/",
        "/scripts/udemy/out.php",
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
        max_pages = (self.MAX_COURSES // 100) + 2
        self.length = max_pages
        for page_num in range(1, max_pages + 1):
            self.progress = page_num
            url = self.REST_URL.format(n=page_num)
            resp = await self._http_get(
                url, use_cloudscraper=True, timeout=15
            )
            if not resp or resp.status_code != 200:
                break
            text = (resp.text or "").strip()
            if not text:
                break
            try:
                data = json.loads(text)
            except Exception:
                break
            if not isinstance(data, list) or not data:
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
                if len(posts) >= self.MAX_COURSES:
                    return posts
        return posts

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
                if len(posts) >= self.MAX_COURSES:
                    return posts
            if page_found == 0:
                break
        return posts

    def _out_url_from_href(self, href: str) -> Optional[str]:
        parsed = urllib.parse.urlparse(href)
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
                timeout=15,
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

            listing = listing[: self.MAX_COURSES]
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
                    soup = self.parse_html(page.text or "")
                    out_url = None
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

            detail_tasks = [
                self._run_detail_task(
                    detail_semaphore, _fetch_post, link, title
                )
                for link, title in listing
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    normalized = Course.normalize_link(link)
                    if normalized not in seen_udemy:
                        seen_udemy.add(normalized)
                        self.append_to_list(title[:200], link)
                self.progress = i + 1
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
}


class ScraperService:
    def __init__(self, sites_to_scrape: List[str] = None, proxy: Optional[str] = None):
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

        worker_sem = asyncio.Semaphore(settings.MAX_SCRAPER_WORKERS)
        detail_sem = asyncio.Semaphore(10)

        if not hasattr(self, "source_states"):
            self.source_states = {id(s): "queued" for s in self.scrapers}

        async def _run_scraper(scraper: Scraper):
            self.source_states[id(scraper)] = "scraping"
            logger.warning(f"  Scraper started: {scraper.site_name}")

            try:
                async with worker_sem:
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
        pending = set(tasks)

        try:
            loop = asyncio.get_event_loop()
            end_time = loop.time() + settings.SCRAPER_RUN_TIMEOUT_SECONDS

            while pending:
                timeout_left = max(0, end_time - loop.time())
                if timeout_left <= 0:
                    break

                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED, timeout=timeout_left
                )

                for task in done:
                    try:
                        scraper, state = task.result()
                        yield scraper, state
                    except asyncio.CancelledError:
                        pass

            # Overall timeout
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                for s in self.scrapers:
                    if self.source_states.get(id(s)) in ("queued", "scraping"):
                        s.error = "Run timed out overall"
                        s.done = True
                        self.source_states[id(s)] = "timed_out"
                        yield s, "timed_out"

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
