from app.core import constants
"""Course scraper service - asynchronously scrapes coupon sites for free Udemy courses."""

import asyncio
import re
import traceback
from abc import ABC, abstractmethod
from html import unescape
from typing import List, Optional, Set
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup as bs
from loguru import logger

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.services.playwright_service import PlaywrightService
from config.settings import get_settings


class Scraper(ABC):
    """Base scraper interface."""

    def __init__(self, http_client: AsyncHTTPClient, proxy: Optional[str] = None, enable_headless: bool = False):
        self.http = http_client
        self.proxy = proxy
        self.enable_headless = enable_headless
        self.length = 0
        self.progress = 0
        self.done = False
        self.error = ""
        self.data: List[Course] = []

    @property
    @abstractmethod
    def site_name(self) -> str:
        """Full site name."""
        pass

    @property
    @abstractmethod
    def code_name(self) -> str:
        """Short code name for the scraper (used for legacy compatibility if needed)."""
        pass

    @abstractmethod
    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        """Perform the scraping."""
        pass

    def append_to_list(self, title: str, link: str):
        """Thread-safe append to a site's data list."""
        if title and link:
            course = Course(title, link)
            course.site = self.site_name
            self.data.append(course)

    def parse_html(self, content: bytes) -> bs:
        return bs(content, "lxml")

    def cleanup_link(self, link: str) -> Optional[str]:
        """Resolve redirect/affiliate links to a plain udemy.com URL."""
        if not link:
            return None
        parsed_url = urlparse(link)
        netloc = parsed_url.netloc.lower()
        if netloc in ("www.udemy.com", "udemy.com"):
            return link
        if netloc == "trk.udemy.com":
            query_params = parse_qs(parsed_url.query)
            if "u" in query_params:
                return unquote(query_params["u"][0])
            return None
        if netloc == "click.linksynergy.com":
            query_params = parse_qs(parsed_url.query)
            if "RD_PARM1" in query_params:
                return unquote(query_params["RD_PARM1"][0])
            if "murl" in query_params:
                return unquote(query_params["murl"][0])
            return None
        return None

    async def _run_detail_task(self, detail_semaphore: asyncio.Semaphore, fetcher, item):
        async with detail_semaphore:
            return await fetcher(item)


class DiscUdemyScraper(Scraper):
    @property
    def site_name(self) -> str: return "Discudemy"

    @property
    def code_name(self) -> str: return "du"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            head = {
                "referer": "https://www.discudemy.com",
            }
            self.length = 10

            # Phase 1: collect listing links
            all_items = []
            if self.enable_headless:
                async with PlaywrightService(proxy=self.proxy) as pw:
                    for page in range(1, 4):
                        content = await pw.get_page_content(f"https://www.discudemy.com/all/{page}", wait_for_selector=".card-header")
                        if content:
                            soup = self.parse_html(content.encode())
                            all_items.extend(soup.find_all("a", {"class": "card-header"}))
                        self.progress = page
            else:
                listing_tasks = [
                    self.http.get(f"https://www.discudemy.com/all/{page}", headers=head)
                    for page in range(1, 11)
                ]
                for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                    resp = await task
                    if resp:
                        soup = self.parse_html(resp.content)
                        all_items.extend(soup.find_all("a", {"class": "card-header"}))
                    self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            # Phase 2: resolve each listing
            async def _fetch_details(item):
                try:
                    title = item.string
                    slug = item["href"].split("/")[-1]
                    resp = await self.http.get(
                        f"https://www.discudemy.com/go/{slug}",
                        headers=head,
                        attempts=1,
                        log_failures=False,
                    )
                    if not resp:
                        return None, None
                    soup = self.parse_html(resp.content)
                    container = soup.find("div", {"class": "ui segment"})
                    if not container or not container.a:
                        return None, None
                    return title, container.a["href"]
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    link = self.cleanup_link(link)
                    if link:
                        self.append_to_list(title, link)
                self.progress = i + 1

        except Exception:
            logger.exception("du scraper failed")
            self.error = traceback.format_exc()


class UdemyFreebiesScraper(Scraper):
    @property
    def site_name(self) -> str: return "Udemy Freebies"

    @property
    def code_name(self) -> str: return "uf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 5
            listing_tasks = [
                self.http.get(f"https://www.udemyfreebies.com/free-udemy-courses/{page}")
                for page in range(1, 6)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                if resp:
                    soup = self.parse_html(resp.content)
                    all_items.extend(soup.find_all("a", {"class": "theme-img"}))
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    img = item.find("img")
                    title = img["alt"] if img else None
                    parts = item.get("href", "").split("/")
                    if len(parts) < 5:
                        return None, None
                    # Resolve the out-link without following to Udemy, which often returns 403.
                    resp = await self.http.get(
                        f"https://www.udemyfreebies.com/out/{parts[4]}",
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=1,
                        log_failures=False,
                    )
                    if not resp:
                        return None, None
                    return title, resp.headers.get("Location") or str(resp.url)
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link and "udemy.com" in link:
                    link = self.cleanup_link(link)
                    if title and link:
                        self.append_to_list(title, link)
                self.progress = i + 1

        except Exception:
            logger.exception("uf scraper failed")
            self.error = traceback.format_exc()


class RealDiscountScraper(Scraper):
    @property
    def site_name(self) -> str: return "Real Discount"

    @property
    def code_name(self) -> str: return "rd"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            headers = {
                "Host": "cdn.real.discount",
                "referer": "https://www.real.discount/",
            }
            resp = await self.http.get(
                "https://cdn.real.discount/api/courses?page=1&limit=500&sortBy=sale_start&store=Udemy&freeOnly=true",
                headers=headers,
            )
            data = await self.http.safe_json(resp, "rd API")
            if not data:
                return

            all_items = data.get("items", [])
            self.length = len(all_items)

            for index, item in enumerate(all_items):
                self.progress = index + 1
                if item.get("store") == "Sponsored":
                    continue
                title = item.get("name", "").strip()
                raw_link = item.get("url", "")
                if not title or not raw_link:
                    continue
                link = self.cleanup_link(raw_link)
                if link:
                    self.append_to_list(title, link)
        except Exception:
            logger.exception("rd scraper failed")
            self.error = traceback.format_exc()


class CourseVaniaScraper(Scraper):
    @property
    def site_name(self) -> str: return "Course Vania"

    @property
    def code_name(self) -> str: return "cv"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            resp = await self.http.get("https://coursevania.com/courses/")
            if not resp:
                return

            try:
                nonce = re.search(
                    r"load_content\"\:\"(.*?)\"", resp.content.decode("utf-8"), re.DOTALL
                ).group(1)
            except (AttributeError, IndexError):
                return

            ajax_resp = await self.http.get(
                "https://coursevania.com/wp-admin/admin-ajax.php"
                "?&template=courses/grid&args={%22posts_per_page%22:%22500%22}"
                "&action=stm_lms_load_content&sort=date_high&nonce=" + nonce,
            )
            ajax_data = await self.http.safe_json(ajax_resp, "cv AJAX")
            if not ajax_data:
                return

            soup = self.parse_html(ajax_data.get("content", "").encode())
            page_items = soup.find_all("div", {"class": "stm_lms_courses__single--title"})
            self.length = len(page_items)

            async def _fetch_details(item):
                try:
                    h5 = item.find("h5")
                    a_tag = item.find("a")
                    if not h5 or not a_tag:
                        return None, None
                    title = h5.get_text(strip=True)
                    page = await self.http.get(a_tag["href"], attempts=1, log_failures=False)
                    if not page:
                        return None, None
                    detail_soup = self.parse_html(page.content)
                    affiliate = detail_soup.find("a", {"class": "masterstudy-button-affiliate__link"})
                    return title, affiliate.get("href") if affiliate else None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in page_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link and "udemy.com" in link:
                    link = self.cleanup_link(link)
                    if title and link:
                        self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            logger.exception("cv scraper failed")
            self.error = traceback.format_exc()


class IDownloadCouponsScraper(Scraper):
    @property
    def site_name(self) -> str: return "IDownloadCoupons"

    @property
    def code_name(self) -> str: return "idc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 3
            listing_tasks = [
                self.http.get(f"https://idownloadcoupon.com/wp-json/wp/v2/product?product_cat=15&per_page=100&page={page}")
                for page in range(1, 4)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"idc page {i+1}")
                if data:
                    all_items.extend(data)
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    title = item.get("title", {}).get("rendered", "").strip()
                    link_num = item.get("id")
                    if not title or not link_num:
                        return None, None
                    url = f"https://idownloadcoupon.com/udemy/{link_num}/"
                    # Manual redirect check for this specific site
                    r = await self.http.get(
                        url,
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=1,
                        log_failures=False,
                    )
                    location = r.headers.get("Location", "") if r else ""
                    if not location:
                        return None, None
                    link = unquote(location)
                    return title, self.cleanup_link(link)
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            logger.exception("idc scraper failed")
            self.error = traceback.format_exc()


class ENextScraper(Scraper):
    @property
    def site_name(self) -> str: return "E-next"

    @property
    def code_name(self) -> str: return "en"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 5
            listing_tasks = [
                self.http.get(f"https://jobs.e-next.in/course/udemy/{page}")
                for page in range(1, 6)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                if resp:
                    soup = self.parse_html(resp.content)
                    all_items.extend(soup.find_all("a", {"class": "btn btn-secondary btn-sm btn-block"}))
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    href = item.get("href")
                    if not href:
                        return None, None
                    resp = await self.http.get(href, attempts=1, log_failures=False)
                    if not resp:
                        return None, None
                    soup = self.parse_html(resp.content)
                    h3 = soup.find("h3")
                    btn = soup.find("a", {"class": "btn btn-primary"})
                    if h3 and btn:
                        return h3.get_text(strip=True), btn.get("href")
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    self.append_to_list(title, link)
                self.progress = i + 1
        except Exception:
            logger.exception("en scraper failed")
            self.error = traceback.format_exc()


class CourseJoinerScraper(Scraper):
    @property
    def site_name(self) -> str: return "Course Joiner"

    @property
    def code_name(self) -> str: return "cj"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 4
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            listing_tasks = [
                self.http.get(
                    f"https://www.coursejoiner.com/wp-json/wp/v2/posts?categories=74&per_page=100&page={page}",
                    headers=headers
                )
                for page in range(1, 5)
            ]
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"cj page {i+1}")
                if data:
                    for item in data:
                        try:
                            title = unescape(item["title"]["rendered"])
                            title = title.replace("–", "-").strip().removesuffix("- (Free Course)").strip()
                            soup = self.parse_html(item.get("content", {}).get("rendered", "").encode())
                            a_tag = soup.find("a", string="APPLY HERE")
                            if a_tag and "udemy.com" in a_tag.get("href", ""):
                                self.append_to_list(title, a_tag["href"])
                        except Exception:
                            continue
                self.progress = i + 1
        except Exception:
            logger.exception("cj scraper failed")
            self.error = traceback.format_exc()


class CoursonScraper(Scraper):
    @property
    def site_name(self) -> str: return "Courson"

    @property
    def code_name(self) -> str: return "cxyz"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 10
            listing_tasks = [
                self.http.post("https://courson.xyz/load-more-coupons", json={"filters": {}, "offset": (page - 1) * 30})
                for page in range(1, 11)
            ]
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"cxyz page {i+1}")
                if data:
                    coupons = data.get("coupons", [])
                    for item in coupons:
                        title = item.get("headline", "").strip(' "')
                        id_name = item.get("id_name", "")
                        coupon = item.get("coupon_code", "")
                        if title and id_name and coupon:
                            self.append_to_list(title, f"{constants.UDEMY_BASE_URL}/course/{id_name}/?couponCode={coupon}")
                self.progress = i + 1
        except Exception:
            logger.exception("cxyz scraper failed")
            self.error = traceback.format_exc()


SCRAPER_REGISTRY = {
    "Real Discount": RealDiscountScraper,
    "Courson": CoursonScraper,
    "IDownloadCoupons": IDownloadCouponsScraper,
    "E-next": ENextScraper,
    "Discudemy": DiscUdemyScraper,
    "Udemy Freebies": UdemyFreebiesScraper,
    "Course Joiner": CourseJoinerScraper,
    "Course Vania": CourseVaniaScraper,
}


class ScraperService:
    """Asynchronously scrapes multiple coupon websites for free Udemy course links."""

    def __init__(self, sites_to_scrape: List[str] = None, proxy: Optional[str] = None, enable_headless: bool = False):
        self.sites = sites_to_scrape or list(SCRAPER_REGISTRY.keys())
        self.http = AsyncHTTPClient(proxy=proxy)
        self.proxy = proxy
        self.enable_headless = enable_headless

        app_settings = get_settings()
        site_count = max(1, len(self.sites))
        site_concurrency = min(max(1, app_settings.MAX_SCRAPER_WORKERS), site_count)
        self._site_semaphore = asyncio.Semaphore(site_concurrency)
        self._detail_semaphore = asyncio.Semaphore(max(site_concurrency * 4, 8))

        self.scrapers: List[Scraper] = []
        for site in self.sites:
            scraper_cls = SCRAPER_REGISTRY.get(site)
            if scraper_cls:
                self.scrapers.append(scraper_cls(self.http, proxy=self.proxy, enable_headless=self.enable_headless))

    def get_progress(self) -> List[dict]:
        progress = []
        for scraper in self.scrapers:
            progress.append({
                "site": scraper.site_name,
                "progress": scraper.progress,
                "total": scraper.length,
                "done": scraper.done,
                "error": scraper.error,
            })
        return progress

    async def scrape_all(self) -> List[Course]:
        """Scrape all configured sites asynchronously and return unique courses."""
        logger.info(f"Starting async scrape for sites: {[s.site_name for s in self.scrapers]}")

        tasks = []
        for scraper in self.scrapers:
            tasks.append(self._scrape_site_guarded(scraper))

        try:
            await asyncio.gather(*tasks)

            scraped_data: Set[Course] = set()
            for scraper in self.scrapers:
                for course in scraper.data:
                    scraped_data.add(course)

            logger.info(f"Scraping finished. Found {len(scraped_data)} unique courses.")
            return list(scraped_data)
        finally:
            await self.http.close()

    async def _scrape_site_guarded(self, scraper: Scraper):
        async with self._site_semaphore:
            await self._scrape_site(scraper)

    async def _scrape_site(self, scraper: Scraper):
        try:
            await scraper.scrape(self._detail_semaphore)
        except Exception:
            logger.exception(f"Scraper {scraper.site_name} failed")
            scraper.error = traceback.format_exc()
            scraper.length = -1
        finally:
            scraper.done = True
