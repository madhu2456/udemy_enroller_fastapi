"""Course scraper service - Technatic-style (No Playwright for enrollment, Playwright allowed for scraping fallback)."""

import asyncio
import random
import re
import traceback
import json
from abc import ABC, abstractmethod
from typing import List, Optional, Union, Dict
from urllib.parse import parse_qs, unquote, urlparse

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

        course = Course(title=title, url=url, site=self.site_name)
        if course not in self.data:
            self.data.append(course)

    async def _run_detail_task(self, semaphore, func, *args):
        """Helper to run a detail-fetching function with a concurrency semaphore."""
        async with semaphore:
            return await func(*args)

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

                await browser.close()
                return content
        except Exception as e:
            logger.warning(f"  Playwright fetch failed for {url}: {e}")
            return ""

    async def playwright_get_url(self, url: str) -> str:
        """Follow redirects using Playwright and return the final URL."""
        try:
            from playwright.async_api import async_playwright

            stealth_async = None
            try:
                from playwright_stealth import stealth_async
            except (ImportError, ModuleNotFoundError):
                pass

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                if stealth_async:
                    await stealth_async(page)

                await page.goto(url, wait_until="commit", timeout=60000)
                # Wait a bit for JS redirects
                await asyncio.sleep(2)
                final_url = page.url
                await browser.close()
                return final_url
        except Exception as e:
            logger.warning(f"  Playwright URL fetch failed for {url}: {e}")
            return ""


class UdemyFreebiesScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Udemy Freebies"

    @property
    def code_name(self) -> str:
        return "uf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  Udemy Freebies: Using Playwright for Cloudflare bypass...")
            content = await self.playwright_get(
                "https://www.udemyfreebies.com/free-udemy-courses/1",
                wait_selector="a.theme-img",
            )
            if not content:
                # Fallback to direct HTTP
                all_items = []
                listing_tasks = [
                    self.http.get(
                        f"https://www.udemyfreebies.com/free-udemy-courses/{page}",
                        use_cloudscraper=True,
                    )
                    for page in range(1, 6)
                ]
                for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                    resp = await task
                    if resp:
                        soup = self.parse_html(resp.content)
                        links = soup.find_all(
                            "a", href=re.compile(r"/free-udemy-course/")
                        )
                        all_items.extend(links)
                    self.progress = i + 1
            else:
                soup = self.parse_html(content)
                links = soup.find_all("a", href=re.compile(r"/free-udemy-course/"))
                unique_items = {}
                for link in links:
                    href = link.get("href")
                    if href:
                        if href.startswith("/"):
                            href = "https://www.udemyfreebies.com" + href
                        if href not in unique_items:
                            unique_items[href] = link
                all_items = list(unique_items.values())

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    title = item.get_text(strip=True) or (
                        item.img["alt"] if item.img else "Unknown"
                    )
                    href = item["href"]
                    parts = href.rstrip("/").split("/")
                    if not parts:
                        return None, None
                    out_id = parts[-1]

                    # Try direct HTTP first (faster)
                    resp = await self.http.get(
                        f"https://www.udemyfreebies.com/out/{out_id}",
                        use_cloudscraper=True,
                        allow_redirects=True,
                    )

                    final_url = None
                    if resp and resp.status_code == 200:
                        if "udemy.com" in str(resp.url):
                            final_url = str(resp.url)
                        elif "udemy.com" in resp.text:
                            # Try to extract from content if URL didn't change
                            match = re.search(r'https://www.udemy.com/course/[^"\' >]+', resp.text)
                            if match:
                                final_url = match.group(0)

                    if not final_url:
                        # Fallback to Playwright if blocked or stuck on redirector
                        # We use playwright_get to get content then extract
                        content = await self.playwright_get(
                            f"https://www.udemyfreebies.com/out/{out_id}"
                        )
                        if content:
                            if "udemy.com" in content:
                                match = re.search(r'https://www.udemy.com/course/[^"\' >]+', content)
                                if match:
                                    final_url = match.group(0)

                    return title, final_url
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in all_items[:40]
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link and "udemy.com" in link:
                    cleaned = self.cleanup_link(link)
                    if cleaned:
                        self.append_to_list(title, cleaned)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class RealDiscountScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Real Discount"

    @property
    def code_name(self) -> str:
        return "rd"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            url = "https://cdn.real.discount/api/courses?page=1&limit=500&sortBy=sale_start&store=Udemy&freeOnly=true"
            headers = {
                "referer": "https://www.real.discount/",
                "Host": "cdn.real.discount",
            }
            resp = await self.http.get(url, headers=headers)
            data = await self.http.safe_json(resp)

            if not data or "items" not in data:
                return

            items = data["items"]
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


class CourseVaniaScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Course Vania"

    @property
    def code_name(self) -> str:
        return "cv"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  CourseVania: Fetching nonce for AJAX listing...")
            resp = await self.http.get(
                "https://coursevania.com/courses/", use_cloudscraper=True
            )
            if not resp:
                content = await self.playwright_get("https://coursevania.com/courses/")
            else:
                content = resp.text

            if not content:
                return

            try:
                nonce_match = re.search(r'load_content":"(.*?)"', content, re.DOTALL)
                if not nonce_match:
                    nonce_match = re.search(r'nonce":"(.*?)"', content, re.DOTALL)

                if not nonce_match:
                    soup = self.parse_html(content)
                    page_items = soup.find_all(
                        "a", {"data-preview": "Preview this course"}
                    )
                else:
                    nonce = nonce_match.group(1)
                    ajax_url = f"https://coursevania.com/wp-admin/admin-ajax.php?&template=courses/grid&args=%7B%22posts_per_page%22%3A%22100%22%7D&action=stm_lms_load_content&sort=date_high&nonce={nonce}"
                    ajax_resp = await self.http.get(ajax_url, use_cloudscraper=True)
                    if ajax_resp:
                        ajax_data = await self.http.safe_json(ajax_resp)
                        if ajax_data and "content" in ajax_data:
                            soup = self.parse_html(ajax_data["content"])
                            page_items = soup.find_all(
                                "div", {"class": "stm_lms_courses__single--title"}
                            )
                        else:
                            page_items = []
                    else:
                        page_items = []
            except Exception:
                page_items = []

            if not page_items:
                return
            self.length = len(page_items)

            async def _fetch_details(item):
                try:
                    a_tag = item.find("a") if not item.name == "a" else item
                    if not a_tag:
                        return None, None
                    course_url = a_tag["href"]
                    if not course_url.startswith("http"):
                        course_url = "https://coursevania.com" + course_url

                    title = a_tag.get("title") or a_tag.get_text(strip=True)
                    resp = await self.http.get(course_url, use_cloudscraper=True)
                    page_content = (
                        resp.content if resp and resp.status_code == 200 else None
                    )
                    if not page_content:
                        page_content = await self.playwright_get(course_url)

                    if not page_content:
                        return None, None
                    detail_soup = self.parse_html(page_content)
                    udemy_link = None
                    for a in detail_soup.find_all("a", href=True):
                        if "udemy.com" in a["href"]:
                            udemy_link = a["href"]
                            if "couponCode" in udemy_link:
                                break
                    return title, udemy_link
                except Exception:
                    return None, None

            unique_items = {}
            for item in page_items:
                a_tag = item.find("a") if not item.name == "a" else item
                if a_tag and "href" in a_tag.attrs:
                    unique_items[a_tag["href"]] = item

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in list(unique_items.values())[:40]
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class IDownloadCouponsScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "IDownloadCoupons"

    @property
    def code_name(self) -> str:
        return "idc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            # Category 15 is Verified for Udemy
            listing_tasks = [
                self.http.get(
                    f"https://idownloadcoupon.com/wp-json/wp/v2/product?product_cat=15&per_page=100&page={p}",
                    use_cloudscraper=True,
                )
                for p in range(1, 4)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp)
                if data and isinstance(data, list):
                    all_items.extend(data)
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    title = item.get("title", {}).get("rendered", "Unknown")
                    link_num = item.get("id")
                    if not link_num:
                        return None, None
                    redir_url = f"https://idownloadcoupon.com/udemy/{link_num}/"
                    resp = await self.http.get(
                        redir_url, use_cloudscraper=True, allow_redirects=False
                    )
                    if (
                        resp
                        and resp.status_code in [301, 302]
                        and "Location" in resp.headers
                    ):
                        return title, unquote(resp.headers["Location"])
                    return None, None
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


class CourseJoinerScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Course Joiner"

    @property
    def code_name(self) -> str:
        return "cj"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            listing_tasks = [
                self.http.get(
                    f"https://www.coursejoiner.com/free-udemy-courses/{page}",
                    use_cloudscraper=True,
                )
                for page in range(1, 4)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                if resp:
                    soup = self.parse_html(resp.content)
                    all_items.extend(soup.find_all("div", {"class": "item-details"}))
                self.progress = i + 1

            self.length = len(all_items)

            async def _fetch_details(item):
                try:
                    title_tag = item.find("h3", {"class": "entry-title"})
                    if not title_tag or not title_tag.a:
                        return None, None
                    title = title_tag.get_text(strip=True)
                    page = await self.http.get(
                        title_tag.a["href"], use_cloudscraper=True
                    )
                    if not page:
                        return None, None
                    detail_soup = self.parse_html(page.content)
                    link_tag = detail_soup.find("a", {"class": "wp-block-button__link"})
                    return title, link_tag["href"] if link_tag else None
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


class ENextScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "E-next"

    @property
    def code_name(self) -> str:
        return "en"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            listing_tasks = [
                self.http.get(f"https://jobs.e-next.in/course/udemy/{p}")
                for p in range(1, 6)
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

            async def _fetch_details(item):
                try:
                    resp = await self.http.get(item["href"])
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


class CouponamiScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Couponami"

    @property
    def code_name(self) -> str:
        return "ca"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  Couponami: Using Playwright for Cloudflare bypass...")
            content = await self.playwright_get(
                "https://www.couponami.com/all", wait_selector="section.card"
            )
            if not content:
                listing_tasks = [
                    self.http.get(f"https://www.couponami.com/all/{p}")
                    for p in range(1, 4)
                ]
                all_items = []
                for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                    resp = await task
                    if resp:
                        soup = self.parse_html(resp.content)
                        all_items.extend(soup.find_all("section", {"class": "card"}))
                    self.progress = i + 1
            else:
                soup = self.parse_html(content)
                all_items = soup.find_all("section", {"class": "card"})

            self.length = len(all_items)

            async def _fetch_details(item):
                try:
                    title_tag = item.find("a", {"class": "card-header"})
                    if not title_tag:
                        return None, None
                    title = title_tag.get_text(strip=True)
                    slug = title_tag["href"].rstrip("/").split("/")[-1]
                    go_url = f"https://www.couponami.com/go/{slug}"
                    resp = await self.http.get(go_url, use_cloudscraper=True)
                    content2 = (
                        resp.content if resp and resp.status_code == 200 else None
                    )
                    if not content2:
                        content2 = await self.playwright_get(
                            go_url, wait_selector=".ui.violet.message a"
                        )
                    if not content2:
                        return None, None
                    soup2 = self.parse_html(content2)
                    link_tag = soup2.select_one(
                        ".ui.violet.message a[href*='udemy.com']"
                    ) or soup2.find("a", href=re.compile(r"udemy\.com"))
                    return title, link_tag["href"] if link_tag else None
                except Exception:
                    return None, None

            ca_semaphore = asyncio.Semaphore(3)
            detail_tasks = [
                self._run_detail_task(ca_semaphore, _fetch_details, item)
                for item in all_items[:40]
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

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  Course Coupon Club: Fetching listings...")
            resp = await self.http.get(
                "https://coursecouponclub.com/", use_cloudscraper=True
            )
            if not resp:
                content = await self.playwright_get("https://coursecouponclub.com/")
            else:
                content = resp.text

            if not content:
                return
            soup = self.parse_html(content)
            page_items = soup.select(".rh-post-title a, h2 a, h3 a")
            course_items = []
            excluded = [
                "tag",
                "category",
                "blog",
                "9-99-courses",
                "submit-coupon",
                "contact-us",
            ]
            for a in page_items:
                href = a["href"].rstrip("/")
                if "coursecouponclub.com" not in href:
                    continue
                parts = href.split("/")
                if len(parts) < 4 or any(p in href for p in excluded):
                    continue
                course_items.append(a)

            unique_items = {}
            for item in course_items:
                unique_items[item["href"]] = item

            self.length = len(unique_items)

            async def _fetch_details(a_tag):
                try:
                    title = a_tag.get_text(strip=True)
                    page_url = a_tag["href"]
                    page = await self.http.get(page_url, use_cloudscraper=True)
                    page_content = (
                        page.content if page else await self.playwright_get(page_url)
                    )
                    if not page_content:
                        return None, None
                    detail_soup = self.parse_html(page_content)
                    link_tag = (
                        detail_soup.select_one("a[href*='udemy.com']")
                        or detail_soup.select_one(".btn_offer_block")
                        or detail_soup.select_one(".re_-f-btn")
                    )
                    if link_tag and "href" in link_tag.attrs:
                        return title, link_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in list(unique_items.values())[:40]
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class CouponScorpionScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "Coupon Scorpion"

    @property
    def code_name(self) -> str:
        return "cs"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  Coupon Scorpion: Using Playwright for Cloudflare bypass...")
            url = "https://couponscorpion.com/category/100-off-coupons/"
            content = await self.playwright_get(url, wait_selector=".entry-title a")
            if not content:
                resp = await self.http.get(url, use_cloudscraper=True)
                content = resp.text if resp else ""

            if not content:
                return
            soup = self.parse_html(content)
            page_items = soup.select(".entry-title a, .post-title a, h3 a")

            unique_items = {}
            for a in page_items:
                href = a["href"].rstrip("/")
                if "couponscorpion.com" in href and len(href.split("/")) > 4:
                    unique_items[href] = a

            self.length = len(unique_items)

            async def _fetch_details(a_tag):
                try:
                    title = a_tag.get_text(strip=True)
                    page_url = a_tag["href"]
                    page = await self.http.get(page_url, use_cloudscraper=True)
                    page_content = (
                        page.content if page else await self.playwright_get(page_url)
                    )
                    if not page_content:
                        return None, None
                    detail_soup = self.parse_html(page_content)
                    link_tag = (
                        detail_soup.select_one("a[href*='udemy.com']")
                        or detail_soup.select_one(".btn_offer_block")
                        or detail_soup.select_one("a.button.external")
                    )
                    if link_tag and "href" in link_tag.attrs:
                        return title, link_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in list(unique_items.values())[:40]
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class FreeWebCartScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "FreeWebCart"

    @property
    def code_name(self) -> str:
        return "fwc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  FreeWebCart: Using Playwright for Cloudflare bypass...")
            url = "https://freewebcart.com/udemy-coupons"
            content = await self.playwright_get(url, wait_selector=".course-card-link")
            if not content:
                resp = await self.http.get(url, use_cloudscraper=True)
                content = resp.text if resp else ""

            if not content:
                return
            soup = self.parse_html(content)
            page_items = soup.select("a.course-card-link")

            unique_items = {}
            for a in page_items:
                href = a["href"].rstrip("/")
                if href.startswith("/"):
                    href = "https://freewebcart.com" + href
                unique_items[href] = a

            self.length = len(unique_items)

            async def _fetch_details(a_tag):
                try:
                    title_tag = a_tag.select_one("h3.title-modern")
                    title = title_tag.get_text(strip=True) if title_tag else "Unknown"
                    page_url = a_tag["href"]
                    if page_url.startswith("/"):
                        page_url = "https://freewebcart.com" + page_url

                    page = await self.http.get(page_url, use_cloudscraper=True)
                    page_content = (
                        page.text if page else await self.playwright_get(page_url)
                    )
                    if not page_content:
                        return None, None
                    match = re.search(
                        r'"sourceUrl":"(https://www\.udemy\.com/course/.*?)"',
                        page_content,
                    )
                    if match:
                        udemy_link = match.group(1).replace("\\u0026", "&")
                        return title, udemy_link
                    detail_soup = self.parse_html(page_content)
                    link_tag = detail_soup.select_one("a[href*='udemy.com']")
                    if link_tag:
                        return title, link_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [
                self._run_detail_task(detail_semaphore, _fetch_details, item)
                for item in list(unique_items.values())[:40]
            ]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


class EasyLearnScraper(Scraper):
    @property
    def site_name(self) -> str:
        return "EasyLearn"

    @property
    def code_name(self) -> str:
        return "el"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            logger.info("  EasyLearn: Using Playwright for Cloudflare bypass...")
            url = "https://www.easylearn.ing/"
            content = await self.playwright_get(
                url, wait_selector="a:has-text('Enroll Now')"
            )

            if not content:
                logger.info("  EasyLearn: Playwright failed, falling back to CloudScraper...")
                resp = await self.http.get(url, use_cloudscraper=True)
                content = resp.text if resp else ""

            if not content:
                return
            soup = self.parse_html(content)

            # Links are trk.udemy.com wrapped in affiliate redirector
            links = soup.find_all("a", href=re.compile(r"trk\.udemy\.com"))

            self.length = len(links)
            for i, link in enumerate(links):
                href = link["href"]
                # Try to find title - usually in an <h2> or adjacent <a> before this one
                title = "Unknown"
                # Looking up for the closest course container
                parent = link.find_parent("div")
                if parent:
                    title_tag = parent.find(["h1", "h2", "h3"]) or parent.find(
                        "a", href=re.compile(r"/course/")
                    )
                    if title_tag:
                        title = title_tag.get_text(strip=True)

                cleaned = self.cleanup_link(href)
                if cleaned:
                    self.append_to_list(title, cleaned)
                self.progress = i + 1
        except Exception:
            self.error = traceback.format_exc()


SCRAPER_REGISTRY = {
    "Couponami": CouponamiScraper,
    "Udemy Freebies": UdemyFreebiesScraper,
    "Real Discount": RealDiscountScraper,
    "IDownloadCoupons": IDownloadCouponsScraper,
    "Course Joiner": CourseJoinerScraper,
    "E-next": ENextScraper,
    "Course Coupon Club": CourseCouponClubScraper,
    "Coupon Scorpion": CouponScorpionScraper,
    "FreeWebCart": FreeWebCartScraper,
    "EasyLearn": EasyLearnScraper,
    "Course Vania": CourseVaniaScraper,
    "RealDiscount": RealDiscountScraper,
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
