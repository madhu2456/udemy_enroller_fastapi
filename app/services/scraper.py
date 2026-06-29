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
from app.services.http_client import AsyncHTTPClient


class Scraper(ABC):
    """Base class for all coupon site scrapers."""

    def __init__(self, http: AsyncHTTPClient, proxy: Optional[str] = None):
        self.http = http
        self.proxy = proxy
        self.data: List[Course] = []
        self.progress = 0
        self.length = 0
        self.done = False
        self.error = None

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

    async def _resolve_trk_redirect(self, trk_url: str) -> str | None:
        """Follow a short trk.udemy.com redirect to the real course URL.
        Returns the resolved URL or None if resolution fails.
        """
        if "trk.udemy.com" not in trk_url:
            normalized = Course.normalize_link(trk_url)
            return normalized if "udemy.com/course/" in normalized else None

        # Course.normalize_link inherently extracts u=, url=, link=, target=, redirect=, go=
        # and preserves any outer couponCode.
        normalized = Course.normalize_link(trk_url)
        if "udemy.com/course/" in normalized and "trk.udemy.com" not in normalized:
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
                if "udemy.com/course/" in resolved:
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
        if "udemy.com/course/" in clean_url:
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
        if not title or not url or "udemy.com" not in url:
            return

        if self._is_generic_course_title(title) or len(title) < 4:
            # Try to extract from URL slug if possible
            match = re.search(r"udemy\.com/course/([^/?#]+)", url)
            if match:
                title = match.group(1).replace("-", " ").title()
            else:
                return  # Skip if we can't get a good title

        course = Course(title=title, url=url, site=self.site_name)
        if course not in self.data:
            self.data.append(course)

    async def _run_detail_task(self, semaphore, func, *args):
        """Helper to run a detail-fetching function with a concurrency semaphore."""
        async with semaphore:
            try:
                return await func(*args)
            except Exception as e:
                logger.warning(f"Detail task failed in {func.__name__}: {e}")
                return None, None

    async def playwright_get(self, url: str, wait_selector: str = None) -> str:
        """Fetch page content using Playwright with stealth patches.

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
            resp = await self.http.get(url, headers=headers)
            data = await self.http.safe_json(resp)

            if not data or "items" not in data:
                logger.info(
                    "  Real Discount: API blocked, falling back to Playwright for listing..."
                )
                content = await self.playwright_get(
                    "https://www.real.discount/store/udemy?sortBy=sale_start",
                    wait_selector=".card-title",
                )
                if content:
                    soup = self.parse_html(content)
                    items = soup.select(".card-title a")
                    self.length = len(items)
                    for i, a in enumerate(items):
                        title = a.get_text(strip=True)
                        link = a.get("href")
                        if title and link:
                            self.append_to_list(title, link)
                        self.progress = i + 1
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

                resp = await self.http.get(
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
                                or "udemy.com/course/" not in normalized_link
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
    """

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
            seen_urls: set[str] = set()
            total_found = 0
            max_courses = 500
            max_api_pages = 4  # 395 posts total = ~4 pages
            self.length = max_api_pages

            page_tasks = []
            for page in range(1, max_api_pages + 1):
                url = f"{base_api}?per_page=100&page={page}"
                page_tasks.append(self.http.get(url, use_cloudscraper=True, timeout=20))

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
                        links = soup.select("a[href*='udemy.com']")

                        for link in links:
                            href = link.get("href", "")
                            if "udemy.com" not in href:
                                continue

                            resolved = await self._resolve_trk_redirect(href)
                            if not resolved:
                                continue

                            # Deduplicate by normalized URL
                            normalized = Course.normalize_link(resolved)
                            if normalized in seen_urls:
                                continue
                            seen_urls.add(normalized)

                            # Prefer link text, fall back to post title
                            title = link.get_text(strip=True)
                            if len(title) < 10:
                                title = post_title
                            if len(title) < 3:
                                title = "Unknown"

                            self.append_to_list(title[:200], resolved)
                            total_found += 1
                            if total_found >= max_courses:
                                logger.info(
                                    f"  Interview Gig: Reached {max_courses} course limit"
                                )
                                return

                except Exception:
                    continue

            logger.info(f"  Interview Gig: REST API found {total_found} unique courses")
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
            resp = await self.http.get(
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

                    # Extract Udemy URL with regex (most reliable)
                    udemy_match = re.search(
                        r'href="(https?://[^"]*udemy\.com/course/[^"]*)"',
                        text,
                    )
                    if not udemy_match:
                        return None, None
                    udemy_url = udemy_match.group(1)

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
                    resp = await self.http.get(url, use_cloudscraper=True, timeout=15)
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
                        r'["\'](https?://www\.udemy\.com/course/[^"\']+)["\']',
                        text,
                    )
                    # Filter out image URLs (udemycdn.com is already excluded by regex)
                    udemy_url = None
                    for m in matches:
                        if ".jpg" in m or ".png" in m or ".jpeg" in m:
                            continue
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
                    resp = await self.http.get(url, use_cloudscraper=True, timeout=15)
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
                        r'href="(https?://www\.udemy\.com/course/[^"]+)"',
                        text,
                    )
                    udemy_url = None
                    for m in matches:
                        if "couponCode=" in m:
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
                    resp = await self.http.get(
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
                        r'["\'](https?://www\.udemy\.com/course/[^"\']+)["\']',
                        text,
                    )
                    udemy_url = None
                    for m in matches:
                        if ".jpg" in m or ".png" in m:
                            continue
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
    Each listing page has 10 courses; detail pages contain direct
    Udemy links with coupon codes in anchor tags.
    """

    @property
    def site_name(self) -> str:
        return "Korshub"

    @property
    def code_name(self) -> str:
        return "kh"

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
                    resp = await self.http.get(
                        url, use_cloudscraper=True, timeout=15, retry_403=True
                    )
                    if not resp or resp.status_code != 200:
                        if page_num <= 1:
                            break
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")
                    page_urls: set[str] = set()
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if href.startswith("/courses/") and href.endswith("-udemy"):
                            page_urls.add(f"https://www.korshub.com{href}")

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

                    # Extract Udemy URL with coupon
                    matches = re.findall(
                        r'href="(https?://www\.udemy\.com/course/[^"]+)"',
                        text,
                    )
                    udemy_url = None
                    for m in matches:
                        if "udemy.com/user/" in m:
                            continue
                        udemy_url = m
                        break

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
                page_tasks.append(self.http.get(url, use_cloudscraper=True, timeout=15))

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
                        follow_redirects=False,
                        raise_for_status=False,
                        use_cloudscraper=False,
                        timeout=15,
                    )
                    if not resp or resp.status_code not in (301, 302, 307, 308):
                        return None, None

                    location = resp.headers.get("location", "")
                    if not location or "udemy.com" not in location:
                        return None, None

                    return title, location
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _resolve_out, slug, title)
                for slug, title in listing_results
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
                    return await self.http.get(url, use_cloudscraper=True, timeout=15)

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
                        raise_for_status=False,
                        timeout=15,
                    )
                    if not resp or resp.status_code not in (301, 302, 307, 308):
                        return None, None

                    location = resp.headers.get("location", "")
                    if not location:
                        return None, None

                    udemy_url = await self._resolve_trk_redirect(location)
                    if not udemy_url or "udemy.com" not in udemy_url:
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


class CourseJoinerScraper(Scraper):
    """Course Joiner (coursejoiner.com) — category-based listing + detail scraper.
    Free Udemy courses at /category/free-udemy/.
    Listing pages have h3 > a links to /free-udemy/{slug}/.
    Detail pages contain a direct Udemy course link (affiliate tracking URL).
    NOTE: Course Joiner does NOT provide coupon codes on its detail pages.
    The extracted URLs are plain Udemy course links without coupons.
    These courses were free at the time of listing but may require
    payment or may no longer be available for free enrollment.
    """

    MAX_COURSES = 500
    MAX_LISTING_PAGES = 60
    DETAIL_BATCH_SIZE = 10

    @property
    def site_name(self) -> str:
        return "Course Joiner"

    @property
    def code_name(self) -> str:
        return "cj"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = self.MAX_LISTING_PAGES
            seen_detail_urls = set()
            seen_udemy_urls = set()

            async def _fetch_detail(detail_url: str, title: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text
                    soup = self.parse_html(text)
                    udemy_url = None

                    # Use BeautifulSoup anchors first
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "udemy.com/course/" in href:
                            udemy_url = href
                            break

                    # Fall back to regex over full page text
                    if not udemy_url:
                        matches = re.findall(
                            r'(https?://[^"\'\s<>]*udemy\.com/course/[^"\'\s<>]+)', text
                        )
                        for m in matches:
                            if ".jpg" not in m and ".png" not in m:
                                udemy_url = m
                                break

                    if not udemy_url:
                        return None, None

                    return title, udemy_url
                except Exception:
                    return None, None

            for page_num in range(1, self.MAX_LISTING_PAGES + 1):
                if len(self.data) >= self.MAX_COURSES:
                    break
                self.progress = page_num

                if page_num == 1:
                    url = "https://coursejoiner.com/category/free-udemy/"
                else:
                    url = (
                        f"https://coursejoiner.com/category/free-udemy/page/{page_num}/"
                    )

                resp = await self.http.get(url, use_cloudscraper=True, timeout=15)
                if not resp or resp.status_code != 200:
                    break

                soup = self.parse_html(resp.content)

                if page_num == 1:
                    pagination = soup.find_all("a", class_="page-numbers")
                    if pagination:
                        try:
                            pages = [
                                int(p.get_text(strip=True).replace(",", ""))
                                for p in pagination
                                if p.get_text(strip=True).replace(",", "").isdigit()
                            ]
                            if pages:
                                max_found = max(pages)
                                self.length = min(self.MAX_LISTING_PAGES, max_found)
                        except Exception:
                            pass

                pending_items = []
                for h in soup.find_all(["h2", "h3"]):
                    a = h.find("a", href=True)
                    if not a:
                        continue

                    href = a.get("href", "")
                    if "/free-udemy/" not in href or "#" in href:
                        continue

                    title = a.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    title = re.sub(
                        r"\s*[-|]\s*\(?Free\s*Course\)?\s*$",
                        "",
                        title,
                        flags=re.IGNORECASE,
                    ).strip()

                    if href not in seen_detail_urls:
                        seen_detail_urls.add(href)
                        pending_items.append((href, title))

                if not pending_items:
                    break

                chunk_size = self.DETAIL_BATCH_SIZE
                for i in range(0, len(pending_items), chunk_size):
                    if len(self.data) >= self.MAX_COURSES:
                        break

                    chunk = pending_items[i : i + chunk_size]
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
                        if isinstance(results, Exception):
                            continue

                        title, link = results
                        if title and link:
                            if len(self.data) >= self.MAX_COURSES:
                                break

                            normalized_link = Course.normalize_link(link)
                            if (
                                not normalized_link
                                or "udemy.com/course/" not in normalized_link
                            ):
                                continue

                            if normalized_link in seen_udemy_urls:
                                continue

                            prev_len = len(self.data)
                            self.append_to_list(title[:200], normalized_link)

                            if len(self.data) > prev_len:
                                seen_udemy_urls.add(normalized_link)

            if not self.data:
                logger.warning("  Course Joiner: No courses found in listings")

        except Exception:
            self.error = traceback.format_exc()


class FreeCourseSitesScraper(Scraper):
    BASE_URL = "https://freecoursesites.com"
    CATEGORY_SOURCES = [
        {"slug": "udemy-free-courses", "fallback_id": 78256},
        {"slug": "100-off-udemy-coupon", "fallback_id": 137426},
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
            resp = await self.http.get(
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
        for anchor in soup.select(
            "a.mks_button[href*='udemy.com'], a[href*='udemy.com/course/'], a[href*='trk.udemy.com']"
        ):
            candidates.append(anchor)

        courses = []
        import html as html_lib

        for a in candidates:
            href = a.get("href", "").strip()
            if not href:
                continue

            href = html_lib.unescape(href)

            if "trk.udemy.com" in href:
                resolved = await self._resolve_trk_redirect(href)
                if resolved:
                    href = resolved

            normalized = Course.normalize_link(href)
            if "udemy.com/course/" not in normalized:
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

                resp = await self.http.get(
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
                resp = await self.http.get(
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


class FreeWebCartScraper(Scraper):
    BASE_URL = "https://freewebcart.com"
    MAX_COURSES = 500
    COURSES_PER_PAGE = 24
    MAX_LISTING_PAGES = 25
    DETAIL_CHUNK_SIZE = 5

    @property
    def site_name(self) -> str:
        return "FreeWebCart"

    @property
    def code_name(self) -> str:
        return "fwc"

    def _parse_listing_candidates(self, html: str) -> list[dict]:
        soup = self.parse_html(html)
        candidates = []
        for a in soup.select('a.course-card-link[href^="/course/"]'):
            href = a.get("href", "").strip()
            if not href or not href.startswith("/course/"):
                continue

            detail_url = urllib.parse.urljoin(self.BASE_URL, href)

            title = ""
            title_el = a.select_one("h3.title-modern")
            if title_el:
                title = title_el.get_text(" ", strip=True)

            if not title:
                img_el = a.select_one("img[alt]")
                if img_el and img_el.get("alt"):
                    title = img_el.get("alt").strip()

            if not title:
                slug = href.replace("/course/", "").strip("/")
                title = slug.replace("-", " ").title()

            suffix = " - Free Udemy Course"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()

            candidates.append(
                {
                    "detail_url": detail_url,
                    "title": title,
                    "slug": href.replace("/course/", "").strip("/"),
                }
            )

        seen = set()
        unique = []
        for c in candidates:
            if c["detail_url"] not in seen:
                seen.add(c["detail_url"])
                unique.append(c)

        return unique

    async def _collect_listing_candidates(self) -> list[dict]:
        all_candidates = []
        self.length = self.MAX_LISTING_PAGES

        for page in range(1, self.MAX_LISTING_PAGES + 1):
            self.progress = page

            url = (
                f"{self.BASE_URL}/courses"
                if page == 1
                else f"{self.BASE_URL}/courses?page={page}"
            )

            resp = await self.http.get(
                url, use_cloudscraper=True, timeout=20, raise_for_status=False
            )

            fallback_used = False
            if page == 1 and resp and resp.status_code == 200:
                candidates = self._parse_listing_candidates(resp.text)
                if not resp.text.strip() or not candidates:
                    fallback_used = True

                if fallback_used:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept-Encoding": "identity",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    }
                    resp = await self.http.get(
                        url,
                        use_cloudscraper=False,
                        timeout=20,
                        raise_for_status=False,
                        headers=headers,
                    )

            if not resp:
                self.diagnostics["listing_fetch_failures"] += 1
                break

            if resp.status_code != 200:
                self.diagnostics["non_200_statuses"] += 1
                break

            if not resp.text.strip():
                self.diagnostics["empty_bodies"] += 1
                break

            candidates = self._parse_listing_candidates(resp.text)
            if not candidates:
                self.diagnostics["zero_candidate_pages"] += 1
                break

            seen = {c["detail_url"] for c in all_candidates}
            for c in candidates:
                if c["detail_url"] not in seen:
                    all_candidates.append(c)
                    seen.add(c["detail_url"])

        return all_candidates

    async def _extract_course_from_detail(
        self, candidate: dict
    ) -> tuple[str, str] | None:
        try:
            resp = await self.http.get(
                candidate["detail_url"],
                use_cloudscraper=True,
                timeout=15,
                raise_for_status=False,
            )
            if not resp or resp.status_code != 200:
                self.diagnostics["detail_fetch_failures"] += 1
                return None

            html_text = resp.text
            udemy_url = None

            import html as html_lib
            import json
            import re

            for match in re.finditer(
                r'"sourceUrl"\s*:\s*"((?:\\.|[^"\\])*)"', html_text
            ):
                raw = match.group(1)
                try:
                    decoded = json.loads(f'"{raw}"')
                    candidate_url = html_lib.unescape(decoded).strip()
                    if "udemy.com/course/" in candidate_url:
                        udemy_url = candidate_url
                        break
                except Exception:
                    pass

            if not udemy_url:
                soup = self.parse_html(html_text)
                for a in soup.select('a[href*="udemy.com/course/"]'):
                    href = a.get("href", "").strip()
                    if href:
                        udemy_url = href
                        break

            if not udemy_url:
                match = re.search(
                    r'(https://www\.udemy\.com/course/[a-zA-Z0-9_-]+/?(?:[^"\'>\s]+)?)',
                    html_text,
                )
                if match:
                    udemy_url = match.group(1)

            if not udemy_url:
                self.diagnostics["no_udemy_link_details"] += 1
                return None

            normalized = Course.normalize_link(udemy_url)
            if "udemy.com/course/" not in normalized:
                self.diagnostics["invalid_normalized_urls"] += 1
                return None

            title = ""
            if "soup" not in locals():
                soup = self.parse_html(html_text)
            h1 = soup.select_one("h1.detail-title")
            if h1:
                title = h1.get_text(" ", strip=True)

            if not title:
                title = candidate.get("title", "")

            if not title:
                title = candidate.get("slug", "").replace("-", " ").title()

            return (title[:200] if title else "FreeWebCart Course", normalized)

        except Exception as e:
            logger.debug(f"Error extracting detail {candidate['detail_url']}: {e}")
            return None

    async def _process_detail_candidates(
        self, candidates: list[dict], detail_semaphore: asyncio.Semaphore
    ) -> None:
        self.length = len(candidates)
        self.progress = 0

        seen_udemy_urls = set()

        for i in range(0, len(candidates), self.DETAIL_CHUNK_SIZE):
            if len(self.data) >= self.MAX_COURSES:
                break

            chunk = candidates[i : i + self.DETAIL_CHUNK_SIZE]

            detail_tasks = [
                self._run_detail_task(
                    detail_semaphore, self._extract_course_from_detail, c
                )
                for c in chunk
            ]

            results_list = await asyncio.gather(*detail_tasks, return_exceptions=True)
            for res in results_list:
                self.progress += 1
                if isinstance(res, tuple) and len(res) == 2 and res[0] and res[1]:
                    title, url = res
                    if url not in seen_udemy_urls:
                        seen_udemy_urls.add(url)
                        if len(self.data) < self.MAX_COURSES:
                            self.append_to_list(title, url)
                    else:
                        self.diagnostics["duplicates"] += 1

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        import time

        start_time = time.time()
        self.diagnostics = {
            "listing_fetch_failures": 0,
            "non_200_statuses": 0,
            "empty_bodies": 0,
            "zero_candidate_pages": 0,
            "total_candidates": 0,
            "detail_fetch_failures": 0,
            "no_udemy_link_details": 0,
            "invalid_normalized_urls": 0,
            "duplicates": 0,
            "appended_courses": 0,
        }
        try:
            candidates = await self._collect_listing_candidates()
            listing_time = time.time() - start_time
            self.diagnostics["total_candidates"] = len(candidates)
            if candidates:
                await self._process_detail_candidates(candidates, detail_semaphore)

            detail_time = time.time() - start_time - listing_time
            self.diagnostics["appended_courses"] = len(self.data)
            logger.info(
                f"  FreeWebCart timing: {listing_time:.1f}s listing, {detail_time:.1f}s details"
            )
            if len(self.data) == 0:
                logger.warning(
                    f"FreeWebCart scrape ended with 0 courses. Diagnostics: {self.diagnostics}"
                )
        except Exception:
            self.error = traceback.format_exc()


SCRAPER_REGISTRY = {
    "FreeWebCart": FreeWebCartScraper,
    "FreeCourseSites": FreeCourseSitesScraper,
    "Real Discount": RealDiscountScraper,
    "E-next": ENextScraper,
    "Interview Gig": InterviewGigScraper,
    "UdemyXpert": UdemyXpertScraper,
    "Coursesity": CoursesityScraper,
    "Course Folder": CourseFolderScraper,
    "Couponami": CouponamiScraper,
    "Korshub": KorshubScraper,
    "UdemyFreebies": UdemyFreebiesScraper,
    "iDownloadCoupon": IDownloadCouponScraper,
    "Course Joiner": CourseJoinerScraper,
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
