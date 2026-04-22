from app.core import constants
"""Course scraper service - asynchronously scrapes coupon sites for free Udemy courses."""

import asyncio
import re
import traceback
import random
from abc import ABC, abstractmethod
from html import unescape
from typing import List, Optional, Set, Union
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

    def parse_html(self, content: Union[bytes, str]) -> bs:
        if isinstance(content, str):
            content = content.encode("utf-8")
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
                    if title and "100%OFF Udemy Coupons" in title:
                        return None, None
                    
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
                "Accept": "application/json",
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
                    r"load_content\"\:\"(.*?)\"", resp.text, re.DOTALL
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
            # They moved from /product to /posts endpoint
            listing_tasks = [
                self.http.get(
                    f"https://idownloadcoupon.com/wp-json/wp/v2/posts?per_page=100&page={page}",
                    headers={"Accept": "application/json"},
                    log_failures=False,
                    raise_for_status=False
                )
                for page in range(1, 4)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"idc page {i+1}")
                if isinstance(data, list):
                    all_items.extend(data)
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    title = unescape(item.get("title", {}).get("rendered", "")).strip()
                    content = item.get("content", {}).get("rendered", "")
                    if not title or not content:
                        return None, None
                    
                    soup = self.parse_html(content)
                    a_tag = soup.find("a", href=lambda h: h and "udemy.com" in h)
                    if a_tag:
                        return title, self.cleanup_link(a_tag["href"])
                    
                    # Fallback to old link_num method if content doesn't have it
                    link_num = item.get("id")
                    if link_num:
                        url = f"https://idownloadcoupon.com/udemy/{link_num}/"
                        r = await self.http.get(
                            url,
                            follow_redirects=False,
                            raise_for_status=False,
                            attempts=1,
                            log_failures=False,
                        )
                        location = r.headers.get("Location", "") if r else ""
                        if location:
                            return title, self.cleanup_link(unquote(location))
                            
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
            logger.exception("idc scraper failed")
            self.error = traceback.format_exc()


class TutorialBarScraper(Scraper):
    @property
    def site_name(self) -> str: return "TutorialBar"

    @property
    def code_name(self) -> str: return "tb"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 3
            # Try WordPress API first as it's more reliable
            headers = {"Accept": "application/json"}
            listing_tasks = [
                self.http.get(f"https://www.tutorialbar.com/wp-json/wp/v2/posts?per_page=100&page={page}", headers=headers, log_failures=False)
                for page in range(1, 4)
            ]
            
            api_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"tb api page {i+1}")
                if isinstance(data, list):
                    api_items.extend(data)
                self.progress = i + 1

            if api_items:
                self.length = len(api_items)
                self.progress = 0
                
                async def _fetch_api_details(item):
                    try:
                        title = unescape(item.get("title", {}).get("rendered", "")).split("|")[0].strip()
                        content = item.get("content", {}).get("rendered", "")
                        soup = self.parse_html(content)
                        a_tag = soup.find("a", href=lambda h: h and "udemy.com" in h)
                        if a_tag:
                            return title, a_tag["href"]
                        return None, None
                    except Exception:
                        return None, None

                detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_api_details, item) for item in api_items]
                for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                    title, link = await task
                    if title and link:
                        cleaned = self.cleanup_link(link)
                        if cleaned:
                            self.append_to_list(title, cleaned)
                    self.progress = i + 1
                return

            # Fallback to home page scraping
            logger.info("tb API failed or empty, trying home page scraping")
            all_items = []
            
            if self.enable_headless:
                async with PlaywrightService(proxy=self.proxy) as pw:
                    content = await pw.get_page_content("https://www.tutorialbar.com/")
                    if content:
                        soup = self.parse_html(content.encode())
                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            if "tutorialbar.com" in href and len(href) > 35:
                                if not any(x in href for x in ["/category/", "/tag/", "/author/", "/page/", "/wp-content/", "/wp-json/", "/wp-login"]):
                                    if href not in all_items:
                                        all_items.append(href)
            else:
                resp = await self.http.get("https://www.tutorialbar.com/")
                if resp:
                    soup = self.parse_html(resp.content)
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "tutorialbar.com" in href and len(href) > 35:
                            if not any(x in href for x in ["/category/", "/tag/", "/author/", "/page/", "/wp-content/", "/wp-json/", "/wp-login"]):
                                if href not in all_items:
                                    all_items.append(href)

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(url):
                try:
                    page = await self.http.get(url, attempts=1, log_failures=False)
                    if not page: return None, None
                    soup = self.parse_html(page.content)
                    title = soup.title.string.split("|")[0].strip() if soup.title else "Untitled"
                    a_tag = soup.find("a", href=lambda h: h and "udemy.com" in h)
                    if a_tag:
                        return title, a_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            if not all_items:
                 logger.warning("tb scraper found no listing links on home page")

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, url) for url in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    cleaned = self.cleanup_link(link)
                    if cleaned:
                        self.append_to_list(title, cleaned)
                self.progress = i + 1
        except Exception:
            logger.exception("tb scraper failed")
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
                "Accept": "application/json",
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
                if isinstance(data, list):
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
                self.http.post(
                    "https://courson.xyz/load-more-coupons", 
                    json={"filters": {}, "offset": (page - 1) * 30},
                    headers={"Accept": "application/json"}
                )
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


class CourseCouponClubScraper(Scraper):
    @property
    def site_name(self) -> str: return "Course Coupon Club"

    @property
    def code_name(self) -> str: return "ccc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 4
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            listing_tasks = [
                self.http.get(
                    f"https://coursecouponclub.com/wp-json/wp/v2/posts?per_page=100&page={page}",
                    headers=headers
                )
                for page in range(1, 5)
            ]
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"ccc page {i+1}")
                if isinstance(data, list):
                    for item in data:
                        try:
                            post_title = unescape(item.get("title", {}).get("rendered", ""))
                            post_title = post_title.replace("–", "-").replace("—", "-").strip()
                            content = item.get("content", {}).get("rendered", "")
                            
                            soup = self.parse_html(content.encode())
                            a_tags = soup.find_all("a", href=True)
                            for a_tag in a_tags:
                                if "udemy.com" in a_tag["href"]:
                                    course_title = post_title
                                    
                                    # Attempt to find specific title for this course in the block
                                    p = a_tag.find_parent("div", class_="rehub_bordered_block")
                                    if p:
                                        title_div = p.find(class_=lambda c: c and "rehub-main-font" in c)
                                        if title_div and title_div.get_text(strip=True):
                                            course_title = title_div.get_text(strip=True)
                                        else:
                                            img = p.find("img", alt=True)
                                            if img and img["alt"]:
                                                course_title = img["alt"]
                                                
                                    link = self.cleanup_link(a_tag["href"])
                                    if link:
                                        self.append_to_list(course_title, link)
                        except Exception:
                            continue
                self.progress = i + 1
        except Exception:
            logger.exception("ccc scraper failed")
            self.error = traceback.format_exc()


class CouponScorpionScraper(Scraper):
    @property
    def site_name(self) -> str: return "Coupon Scorpion"

    @property
    def code_name(self) -> str: return "cs"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 3
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            listing_tasks = [
                self.http.get(
                    f"https://couponscorpion.com/wp-json/wp/v2/posts?per_page=100&page={page}",
                    headers=headers
                )
                for page in range(1, 4)
            ]
            
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                data = await self.http.safe_json(resp, f"cs page {i+1}")
                if isinstance(data, list):
                    all_items.extend(data)
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                try:
                    title = unescape(item.get("title", {}).get("rendered", ""))
                    title = title.replace("–", "-").replace("—", "-").strip()
                    post_link = item.get("link")
                    if not post_link:
                        return None, None
                    
                    page_resp = await self.http.get(post_link, headers=headers, attempts=1, log_failures=False)
                    if not page_resp:
                        return None, None
                        
                    soup = self.parse_html(page_resp.content)
                    a_tag = soup.find("a", href=lambda h: h and "/scripts/udemy/out.php" in h)
                    if not a_tag:
                        return None, None
                        
                    out_link = a_tag["href"]
                    if out_link.startswith("/"):
                        out_link = f"https://couponscorpion.com{out_link}"
                    # Fetch redirect
                    redir_resp = await self.http.get(
                        out_link,
                        headers=headers,
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=1,
                        log_failures=False
                    )
                    
                    udemy_link = redir_resp.headers.get("Location") if redir_resp else None
                    if udemy_link:
                        return title, udemy_link
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, udemy_link = await task
                if title and udemy_link:
                    cleaned_link = self.cleanup_link(udemy_link)
                    if cleaned_link:
                        self.append_to_list(title, cleaned_link)
                self.progress = i + 1
                
        except Exception:
            logger.exception("cs scraper failed")
            self.error = traceback.format_exc()


class FreeWebCartScraper(Scraper):
    @property
    def site_name(self) -> str: return "FreeWebCart"

    @property
    def code_name(self) -> str: return "fwc"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            self.length = 3
            listing_tasks = [
                self.http.get(f"https://freewebcart.com/?page={page}")
                for page in range(1, 4)
            ]
            all_items = []
            for i, task in enumerate(asyncio.as_completed(listing_tasks)):
                resp = await task
                if resp:
                    soup = self.parse_html(resp.content)
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/course/" in href:
                            if href.startswith("/course/"):
                                href = "https://freewebcart.com" + href
                            if href not in all_items:
                                all_items.append(href)
                self.progress = i + 1

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(url):
                try:
                    page = await self.http.get(url, attempts=1, log_failures=False)
                    if not page: return None, None
                    soup = self.parse_html(page.content)
                    title = soup.title.string.split("|")[0].strip() if soup.title else "Untitled"
                    a_tag = soup.find("a", href=lambda h: h and "udemy.com" in h)
                    if a_tag:
                        return title, a_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, url) for url in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    cleaned = self.cleanup_link(link)
                    if cleaned:
                        self.append_to_list(title, cleaned)
                self.progress = i + 1
        except Exception:
            logger.exception("fwc scraper failed")
            self.error = traceback.format_exc()


class EasyLearnScraper(Scraper):
    @property
    def site_name(self) -> str: return "Easy Learn"

    @property
    def code_name(self) -> str: return "el"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            resp = await self.http.get("https://www.easylearn.ing/sitemap.xml")
            if not resp: return
            
            import re
            locs = re.findall(r"<loc>(.*?)</loc>", resp.text)
            all_items = [l for l in locs if "/course/" in l]
            # Take newest 100
            all_items = all_items[-100:] if len(all_items) > 100 else all_items
            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(url):
                try:
                    page = await self.http.get(url, attempts=1, log_failures=False)
                    if not page: return None, None
                    soup = self.parse_html(page.content)
                    title = soup.title.string.split("|")[0].strip() if soup.title else "Untitled"
                    a_tag = soup.find("a", href=lambda h: h and "udemy.com" in h)
                    if a_tag:
                        return title, a_tag["href"]
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, url) for url in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, link = await task
                if title and link:
                    cleaned = self.cleanup_link(link)
                    if cleaned:
                        self.append_to_list(title, cleaned)
                self.progress = i + 1
        except Exception:
            logger.exception("el scraper failed")
            self.error = traceback.format_exc()


class RedditUdemyFreebiesScraper(Scraper):
    @property
    def site_name(self) -> str: return "Reddit /r/udemyfreebies"

    @property
    def code_name(self) -> str: return "reddit_uf"

    async def scrape(self, detail_semaphore: asyncio.Semaphore):
        try:
            import time
            # Reddit explicitly blocks common bot UAs. Use a standard browser UA.
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
            
            # Domains we already have dedicated scrapers for - skip them to avoid redundancy
            skipped_domains = {
                "freewebcart.com", "easylearn.ing", "idownloadcoupon.com", 
                "tutorialbar.com", "discudemy.com", "udemyfreebies.com",
                "coursecouponclub.com", "couponscorpion.com", "coursejoiner.com",
                "courson.xyz", "jobs.e-next.in", "e-next.in"
            }

            resp = await self.http.get(
                "https://www.reddit.com/r/udemyfreebies/new.json?limit=100", 
                headers=headers,
                randomize_headers=False
            )
            data = await self.http.safe_json(resp, "reddit API")
            if not data or "data" not in data or "children" not in data["data"]:
                return

            current_time = time.time()
            all_items = []
            
            for child in data["data"]["children"]:
                post = child.get("data", {})
                created = post.get("created_utc", 0)
                if current_time - created <= 86400: # 24 hours
                    title = post.get("title", "")
                    title = title.replace("[FREE]", "").replace("[100% OFF]", "").strip()
                    link = post.get("url", "")
                    selftext = post.get("selftext", "")
                    
                    target_url = None
                    if link and link.startswith("http") and "reddit.com" not in link:
                        target_url = link
                    else:
                        match = re.search(r"https?://[^\s\]\)]+", selftext)
                        if match:
                            target_url = match.group(0)
                    
                    if title and target_url:
                        domain = urlparse(target_url).netloc.lower().replace("www.", "")
                        if domain not in skipped_domains:
                            all_items.append((title, target_url))

            self.length = len(all_items)
            self.progress = 0

            async def _fetch_details(item):
                title, target_url = item
                try:
                    if "udemy.com" in target_url:
                        return title, target_url
                        
                    # Fetch redirect or page
                    page_resp = await self.http.get(
                        target_url,
                        headers=headers,
                        follow_redirects=False,
                        raise_for_status=False,
                        attempts=1,
                        log_failures=False
                    )
                    
                    if not page_resp:
                        return None, None
                        
                    # Check redirect
                    location = page_resp.headers.get("Location")
                    if location and "udemy.com" in location:
                        return title, location
                        
                    # Parse HTML
                    soup = self.parse_html(page_resp.content)
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"]
                        if "udemy.com" in href:
                            return title, href
                            
                    return None, None
                except Exception:
                    return None, None

            detail_tasks = [self._run_detail_task(detail_semaphore, _fetch_details, item) for item in all_items]
            for i, task in enumerate(asyncio.as_completed(detail_tasks)):
                title, udemy_link = await task
                if title and udemy_link:
                    cleaned_link = self.cleanup_link(udemy_link)
                    if cleaned_link:
                        self.append_to_list(title, cleaned_link)
                self.progress = i + 1
                
        except Exception:
            logger.exception("reddit_uf scraper failed")
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
    "Course Coupon Club": CourseCouponClubScraper,
    "Coupon Scorpion": CouponScorpionScraper,
    "Reddit /r/udemyfreebies": RedditUdemyFreebiesScraper,
    "TutorialBar": TutorialBarScraper,
    "FreeWebCart": FreeWebCartScraper,
    "Easy Learn": EasyLearnScraper,
}


class ScraperService:
    """Asynchronously scrapes multiple coupon websites for free Udemy course links."""

    def __init__(self, sites_to_scrape: List[str] = None, proxy: Optional[str] = None, enable_headless: bool = False, firecrawl_api_key: Optional[str] = None):
        self.sites = sites_to_scrape or list(SCRAPER_REGISTRY.keys())
        self.enable_headless = enable_headless
        self.firecrawl_api_key = firecrawl_api_key

        app_settings = get_settings()
        
        self.proxies = []
        if proxy:
            self.proxies.append(proxy)
        elif app_settings.PROXIES:
            self.proxies = [p.strip() for p in app_settings.PROXIES.split(",") if p.strip()]

        self.http_clients: List[AsyncHTTPClient] = []
        # Shared client for service-level operations (backwards compatibility with tests)
        self.http = AsyncHTTPClient(proxy=proxy)
        self.http_clients.append(self.http)

        site_count = max(1, len(self.sites))
        site_concurrency = min(max(1, app_settings.MAX_SCRAPER_WORKERS), site_count)
        self._site_semaphore = asyncio.Semaphore(site_concurrency)
        self._detail_semaphore = asyncio.Semaphore(max(site_concurrency * 4, 8))

        self.scrapers: List[Scraper] = []
        for i, site in enumerate(self.sites):
            scraper_cls = SCRAPER_REGISTRY.get(site)
            if scraper_cls:
                assigned_proxy = self.proxies[i % len(self.proxies)] if self.proxies else None
                client = AsyncHTTPClient(proxy=assigned_proxy)
                self.http_clients.append(client)
                self.scrapers.append(scraper_cls(client, proxy=assigned_proxy, enable_headless=self.enable_headless))

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
        # Shuffle scrapers to avoid hitting sites in the same order every time
        shuffled_scrapers = list(self.scrapers)
        random.shuffle(shuffled_scrapers)
        
        logger.info(f"Starting async scrape for sites: {[s.site_name for s in shuffled_scrapers]}")

        running_tasks = []
        try:
            # Stagger the start of each scraper slightly
            for i, scraper in enumerate(shuffled_scrapers):
                if i > 0:
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                
                # Create the task and track it
                task = asyncio.create_task(self._scrape_site_guarded(scraper))
                running_tasks.append(task)
            
            # Wait for all started tasks to finish
            await asyncio.gather(*running_tasks)

            scraped_data: Set[Course] = set()
            for scraper in self.scrapers:
                for course in scraper.data:
                    scraped_data.add(course)

            logger.info(f"Scraping finished. Found {len(scraped_data)} unique courses.")
            return list(scraped_data)
        except asyncio.CancelledError:
            logger.info("Scraping cancelled, cleaning up tasks...")
            for task in running_tasks:
                task.cancel()
            if running_tasks:
                await asyncio.gather(*running_tasks, return_exceptions=True)
            raise
        finally:
            for client in self.http_clients:
                try:
                    await client.close()
                except Exception:
                    pass

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
