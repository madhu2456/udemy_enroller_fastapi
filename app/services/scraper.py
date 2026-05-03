"""Course scraper service - Technatic-style (No Playwright for enrollment, Playwright allowed for scraping fallback)."""

import asyncio
import random
import re
import traceback
import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Optional, Union, Dict

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
        return BeautifulSoup(content, "lxml")

    async def _resolve_trk_redirect(self, trk_url: str) -> str | None:
        """Follow a short trk.udemy.com redirect to the real course URL.
        Returns the resolved URL or None if resolution fails.
        """
        if "trk.udemy.com" not in trk_url:
            return trk_url
        try:
            resp = await self.http.head(trk_url, follow_redirects=True, timeout=15)
            if resp and resp.status_code in (200, 301, 302, 307, 308):
                resolved = str(resp.url)
                if "udemy.com/course/" in resolved:
                    return resolved
            # Fallback: try GET if HEAD didn't work
            resp = await self.http.get(trk_url, follow_redirects=True, timeout=15)
            if resp:
                resolved = str(resp.url)
                if "udemy.com/course/" in resolved:
                    return resolved
        except Exception as e:
            logger.debug(f"Failed to resolve trk redirect {trk_url}: {e}")
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

    def append_to_list(self, title: str, url: str):
        """Add a course to the data list with deduplication logic."""
        if not title or not url or "udemy.com" not in url:
            return

        # Filter out generic titles that some scrapers pick up
        generic_titles = {
            "get coupon",
            "redeem coupon",
            "enroll now",
            "enroll for free",
            "free coupon",
            "click here",
            "get this deal",
            "view course",
            "learn more",
            "download now",
        }
        
        clean_title = title.lower().strip()
        if clean_title in generic_titles or len(title) < 4:
            # Try to extract from URL slug if possible
            match = re.search(r"udemy\.com/course/([^/?#]+)", url)
            if match:
                title = match.group(1).replace("-", " ").title()
            else:
                return # Skip if we can't get a good title

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
        """Fetch page content using Playwright (fallback for Cloudflare)."""
        try:
            from playwright.async_api import async_playwright

            stealth_async = None
            try:
                from playwright_stealth import stealth_async
            except (ImportError, ModuleNotFoundError):
                logger.warning("  playwright_stealth not found, proceeding without it.")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
                        await asyncio.sleep(10)
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
                logger.info("  Real Discount: API blocked, falling back to Playwright for listing...")
                content = await self.playwright_get("https://www.real.discount/store/udemy?sortBy=sale_start", wait_selector=".card-title")
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
    @property
    def site_name(self) -> str:
        return "E-next"

    @property
    def code_name(self) -> str:
        return "en"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 20  # 20 listing pages
            listing_tasks = [
                self.http.get(f"https://jobs.e-next.in/course/udemy/{p}")
                for p in range(1, 21)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                if resp:
                    soup = self.parse_html(resp.content)
                    all_items.extend(
                        soup.find_all(
                            "a", {"class": "btn btn-secondary btn-sm btn-block"}
                        )
                    )
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

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

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in all_items
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class CourseCouponClubScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Course Coupon Club"

    @property
    def code_name(self) -> str:
        return "ccc"

    @staticmethod
    def _extract_udemy_url_from_trk(href: str) -> str | None:
        """Extract the real Udemy URL from trk.udemy.com affiliate links.
        Long links have a `u=` parameter; short ones cannot be resolved without a redirect.
        """
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "u" in qs:
            return urllib.parse.unquote(qs["u"][0])
        # Short trk links (e.g. /4Gb2En) require a redirect; return as-is and let
        # the enrollment pipeline resolve it later.
        return href

    async def _scrape_rest_api(self, detail_semaphore: asyncio.Semaphore) -> bool:
        """Use WordPress REST API for fast bulk extraction.
        Returns True if successful, False to fall back to HTML scraping.
        """
        import json

        base_api = "https://coursecouponclub.com/wp-json/wp/v2/posts"
        seen_urls: set[str] = set()
        total_found = 0
        max_courses = 500

        # Fetch up to 10 pages (1000 posts).  Page 1 is a giant listicle with
        # 700+ links (many old), so we include it but rely on deduplication.
        max_api_pages = 10
        self.length = max_api_pages
        page_tasks = []
        for page in range(1, max_api_pages + 1):
            url = f"{base_api}?per_page=100&page={page}"
            page_tasks.append(self.http.get(url, use_cloudscraper=True, timeout=20))

        logger.info(
            f"  Course Coupon Club: Fetching up to {max_api_pages} REST API pages..."
        )

        # Process pages as they complete (fastest-first)
        for i, task in enumerate(asyncio.as_completed(page_tasks)):
            self.progress = i + 1
            try:
                resp = await task
                if not resp or resp.status_code != 200:
                    continue

                posts = json.loads(resp.text)
                if not isinstance(posts, list) or not posts:
                    continue

                for post in posts:
                    content_html = post.get("content", {}).get("rendered", "")
                    post_title = (
                        post.get("title", {}).get("rendered", "")
                        or "Unknown"
                    )

                    soup = self.parse_html(content_html)
                    links = soup.select("a[href*='udemy.com']")

                    for link in links:
                        href = link.get("href", "")
                        if "udemy.com" not in href:
                            continue

                        # Resolve trk.udemy.com redirect URLs
                        resolved = self._extract_udemy_url_from_trk(href)
                        if not resolved:
                            continue

                        # Short trk links (e.g. /o4Mz6e) need a redirect resolution
                        if "trk.udemy.com" in resolved and "/u=" not in resolved:
                            resolved = await self._resolve_trk_redirect(resolved)
                            if not resolved:
                                continue

                        # Deduplicate by normalized URL (ignore coupon differences)
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
                                f"  Course Coupon Club: Reached {max_courses} course limit"
                            )
                            return True

            except Exception:
                # One page failed — keep going with the rest
                continue

        logger.info(
            f"  Course Coupon Club: REST API found {total_found} unique courses"
        )
        return total_found > 0

    async def _scrape_html_fallback(self, detail_semaphore: asyncio.Semaphore):
        """Legacy HTML fallback: scrape homepage + paginated archive pages."""
        logger.info("  Course Coupon Club: Falling back to HTML scraping...")

        all_items: list[BeautifulSoup] = []
        excluded = {
            "tag",
            "category",
            "blog",
            "9-99-courses",
            "submit-coupon",
            "contact-us",
        }

        # Fetch homepage + pages 2-5 concurrently
        page_urls = ["https://coursecouponclub.com/"] + [
            f"https://coursecouponclub.com/page/{p}/" for p in range(2, 6)
        ]
        self.length = len(page_urls)
        page_tasks = [
            self.http.get(u, use_cloudscraper=True, timeout=15) for u in page_urls
        ]

        for i, task in enumerate(asyncio.as_completed(page_tasks)):
            self.progress = i + 1
            try:
                resp = await task
                if not resp:
                    continue
                soup = self.parse_html(resp.content)
                for a in soup.select(".rh-post-title a, h2 a, h3 a"):
                    href = a.get("href", "").rstrip("/")
                    if "coursecouponclub.com" not in href:
                        continue
                    parts = href.split("/")
                    if len(parts) < 4 or any(p in href for p in excluded):
                        continue
                    all_items.append(a)
            except Exception:
                continue

        # Deduplicate by href
        unique_items: dict[str, BeautifulSoup] = {}
        for a in all_items:
            href = a.get("href", "")
            if href and href not in unique_items:
                unique_items[href] = a

        self.length = len(unique_items)
        self.progress = 0

        async def _fetch_details(item):
            try:
                page = await self.http.get(item["href"], use_cloudscraper=True)
                page_content = page.content if page else None
                if not page_content:
                    return []

                detail_soup = self.parse_html(page_content)
                found_courses = []

                # Direct Udemy links
                for link in detail_soup.select("a[href*='udemy.com']"):
                    href = link.get("href", "")
                    title = link.get_text(strip=True)
                    if len(title) < 10:
                        parent = link.find_parent(["h1", "h2", "h3", "h4", "p", "div"])
                        title = parent.get_text(strip=True) if parent else item.get_text(strip=True)
                    if "udemy.com" in href:
                        found_courses.append((title[:200], href))

                # Button fallbacks
                if not found_courses:
                    for btn in detail_soup.select(".btn_offer_block, .re_-f-btn, .wp-block-button__link"):
                        href = btn.get("href", "")
                        if href and ("udemy.com" in href or "/go/" in href or "trk.udemy.com" in href):
                            title = btn.get_text(strip=True) or item.get_text(strip=True)
                            found_courses.append((title[:200], href))

                # Resolve short trk.udemy.com redirects
                resolved_courses = []
                for title, href in found_courses:
                    if "trk.udemy.com" in href and "/u=" not in href:
                        resolved = await self._resolve_trk_redirect(href)
                        if resolved:
                            resolved_courses.append((title, resolved))
                    else:
                        resolved_courses.append((title, href))
                return resolved_courses
            except Exception:
                return []

        detail_tasks = [
            self._run_detail_task(detail_semaphore, _fetch_details, item)
            for item in list(unique_items.values())[:150]
        ]
        for i, task in enumerate(asyncio.as_completed(detail_tasks)):
            results = await task
            if results:
                for title, link in results:
                    self.append_to_list(title, link)
            self.progress = i + 1

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            # Strategy 1: WordPress REST API (fast, no detail pages needed)
            ok = await self._scrape_rest_api(detail_semaphore)
            if ok:
                return

            # Strategy 2: HTML fallback
            await self._scrape_html_fallback(detail_semaphore)
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

    @staticmethod
    def _extract_udemy_url_from_trk(href: str) -> str | None:
        """Extract the real Udemy URL from trk.udemy.com affiliate links."""
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "u" in qs:
            return urllib.parse.unquote(qs["u"][0])
        return href

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
                page_tasks.append(
                    self.http.get(url, use_cloudscraper=True, timeout=20)
                )

            for i, task in enumerate(asyncio.as_completed(page_tasks)):
                self.progress = i + 1
                try:
                    resp = await task
                    if not resp or resp.status_code != 200:
                        continue

                    posts = json.loads(resp.text)
                    if not isinstance(posts, list) or not posts:
                        continue

                    for post in posts:
                        content_html = post.get("content", {}).get("rendered", "")
                        post_title = (
                            post.get("title", {}).get("rendered", "")
                            or "Unknown"
                        )

                        soup = self.parse_html(content_html)
                        links = soup.select("a[href*='udemy.com']")

                        for link in links:
                            href = link.get("href", "")
                            if "udemy.com" not in href:
                                continue

                            # Resolve trk.udemy.com redirect URLs
                            resolved = self._extract_udemy_url_from_trk(href)
                            if not resolved:
                                continue

                            # Short trk links (e.g. /o4Mz6e) need a redirect resolution
                            if "trk.udemy.com" in resolved and "/u=" not in resolved:
                                resolved = await self._resolve_trk_redirect(resolved)
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

            logger.info(
                f"  Interview Gig: REST API found {total_found} unique courses"
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
                        title_match = re.search(
                            r'<title>([^<]+)</title>', text
                        )
                        if title_match:
                            title = title_match.group(1)

                    if title:
                        # Clean title: remove "- Free Udemy Coupon | UdemyXpert" suffix
                        title = re.sub(
                            r"\s*[-|]\s*Free Udemy Coupon.*", "", title, flags=re.IGNORECASE
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
                    resp = await self.http.get(
                        url, use_cloudscraper=True, timeout=15
                    )
                    if not resp or resp.status_code != 200:
                        break

                    text = resp.text
                    links = re.findall(
                        r'href="(/course-detail/[^"]+)"', text
                    )
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
            logger.info(
                f"  Coursesity: Found {len(detail_urls)} detail URLs to fetch"
            )

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
                        title_match = re.search(
                            r'<title>([^<]+)</title>', text
                        )
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
                self._run_detail_task(
                    detail_semaphore, _fetch_detail, url
                )
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
                "", "live-free-udemy-coupon.php", "udemy-coupon-codes.php",
            }

            detail_urls: list[str] = []

            self.length = max_pages
            for page_num in range(0, max_pages):
                self.progress = page_num + 1
                url = (
                    f"https://coursefolder.net/free-udemy-coupon.php"
                    f"?page={page_num}"
                )
                try:
                    resp = await self.http.get(
                        url, use_cloudscraper=True, timeout=15
                    )
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
                    title_match = re.search(
                        r'<title>([^<]+)</title>', text
                    )
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
                self._run_detail_task(
                    detail_semaphore, _fetch_detail, url
                )
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
                                ("category/", "language/", "vendor/", "go/", "page/", "feed")
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
            logger.info(
                f"  Couponami: Found {len(detail_urls)} /go/ URLs to fetch"
            )

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
                        url, use_cloudscraper=True, timeout=15
                    )
                    if not resp or resp.status_code != 200:
                        break

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
            logger.info(
                f"  Korshub: Found {len(detail_urls)} detail URLs to fetch"
            )

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
                self._run_detail_task(
                    detail_semaphore, _fetch_detail, url
                )
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
                page_tasks.append(
                    self.http.get(url, use_cloudscraper=True, timeout=15)
                )

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
            page_tasks = []
            for page_num in range(1, max_pages + 1):
                url = f"https://idownloadcoupon.com/page/{page_num}/"
                page_tasks.append(
                    self.http.get(url, use_cloudscraper=True, timeout=15)
                )

            for i, task in enumerate(asyncio.as_completed(page_tasks)):
                self.progress = i + 1
                try:
                    resp = await task
                    if not resp or resp.status_code != 200:
                        continue

                    soup = self.parse_html(resp.content)
                    for a in soup.find_all("a", href=True):
                        href = a.get("href", "")
                        # Match title links: /udemy/{numeric_id}/{slug}/
                        match = re.search(
                            r"/udemy/(\d+)/[^/]+/?$", href
                        )
                        if not match:
                            continue

                        cid = match.group(1)
                        if cid in seen_ids:
                            continue
                        seen_ids.add(cid)

                        title = a.get_text(strip=True)
                        # Skip generic / empty titles
                        if not title or title.lower() in {"redeem offer", "udemy", "sale!"}:
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

                    # Parse u= parameter from trk.udemy.com redirect URL
                    parsed = urllib.parse.urlparse(location)
                    qs = urllib.parse.parse_qs(parsed.query)
                    udemy_url = qs.get("u", [""])[0]
                    if udemy_url:
                        udemy_url = urllib.parse.unquote(udemy_url)

                    if not udemy_url or "udemy.com" not in udemy_url:
                        return None, None

                    return title, udemy_url
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _resolve_redeem, cid, title)
                for cid, title in listing_results
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

    @property
    def site_name(self) -> str:
        return "Course Joiner"

    @property
    def code_name(self) -> str:
        return "cj"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            seen_urls: set[str] = set()
            max_courses = 500
            courses_per_page = 20
            max_pages = (max_courses // courses_per_page) + 2

            detail_urls: list[tuple[str, str]] = []

            # Step 1: Fetch listing pages sequentially
            self.length = max_pages
            for page_num in range(1, max_pages + 1):
                self.progress = page_num
                url = f"https://coursejoiner.com/category/free-udemy/page/{page_num}/"
                try:
                    resp = await self.http.get(
                        url, use_cloudscraper=True, timeout=15
                    )
                    if not resp or resp.status_code != 200:
                        break

                    soup = self.parse_html(resp.content)
                    page_found = 0

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

                        # Clean title suffixes
                        title = re.sub(
                            r"\s*[-|]\s*\(?Free\s*Course\)?\s*$",
                            "",
                            title,
                            flags=re.IGNORECASE,
                        ).strip()

                        detail_urls.append((href, title))
                        page_found += 1

                    if page_found == 0:
                        break

                    if len(detail_urls) >= max_courses:
                        break
                except Exception:
                    continue

            if not detail_urls:
                logger.warning("  Course Joiner: No courses found in listings")
                return

            # Deduplicate by URL
            unique_details: dict[str, str] = {}
            for href, title in detail_urls:
                if href not in unique_details:
                    unique_details[href] = title

            unique_list = list(unique_details.items())[:max_courses]
            self.length = len(unique_list)
            self.progress = 0
            logger.info(
                f"  Course Joiner: Found {len(unique_list)} unique detail URLs"
            )

            # Step 2: Fetch detail pages concurrently
            async def _fetch_detail(detail_url: str, title: str):
                try:
                    page = await self.http.get(
                        detail_url, use_cloudscraper=True, timeout=15
                    )
                    if not page or page.status_code != 200:
                        return None, None

                    text = page.text

                    # Extract Udemy course URL
                    matches = re.findall(
                        r'href="(https?://www\.udemy\.com/course/[^"]+)"',
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

                    return title, udemy_url
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(
                    detail_semaphore, _fetch_detail, url, title
                )
                for url, title in unique_list
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

            logger.info(f"  Course Joiner: Found {found} unique Udemy courses")
        except Exception:
            self.error = traceback.format_exc()


SCRAPER_REGISTRY = {
    "Real Discount": RealDiscountScraper,
    "E-next": ENextScraper,
    "Course Coupon Club": CourseCouponClubScraper,
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

    async def scrape_all(self) -> List[Course]:
        logger.warning(f"Starting scrape for: {self.sites}")
        detail_semaphore = asyncio.Semaphore(15)

        async def _run_scraper(scraper: Scraper):
            logger.warning(f"  Scraper started: {scraper.site_name}")
            try:
                await scraper.scrape(detail_semaphore)
                logger.warning(
                    f"  Scraper finished: {scraper.site_name} (Found {len(scraper.data)} courses)"
                )
            except Exception as e:
                logger.error(f"  Scraper failed: {scraper.site_name} - {e}")
                scraper.error = str(e)
            finally:
                scraper.done = True

        # Run the deduplicated list of unique scraper instances
        tasks = [_run_scraper(s) for s in self.scrapers]
        await asyncio.gather(*tasks)

        all_data = []
        for s in self.scrapers:
            all_data.extend(s.data)

        # Deduplicate by URL
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
        for site_name in self.sites:
            if site_name in self.site_to_scraper:
                s = self.site_to_scraper[site_name]
                results.append(
                    {
                        "site": site_name,  # Return the specific requested site name
                        "progress": s.progress,
                        "total": s.length,
                        "done": s.done,
                        "error": s.error,
                    }
                )
        return results
