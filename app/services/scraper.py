"""Course scraper service - scrapes coupon sites for free Udemy courses."""

import concurrent.futures
import inspect
import logging
import re
import threading
import time
import traceback
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup as bs

from app.services.course import Course

logger = logging.getLogger(__name__)

SCRAPER_DICT: dict = {
    "Real Discount": "rd",
    "Courson": "cxyz",
    "IDownloadCoupons": "idc",
    "E-next": "en",
    "Discudemy": "du",
    "Udemy Freebies": "uf",
    "Course Joiner": "cj",
    "Course Vania": "cv",
}


class ScraperService:
    """Scrapes multiple coupon websites for free Udemy course links."""

    def __init__(self, sites_to_scrape: list = None):
        self.sites = sites_to_scrape or list(SCRAPER_DICT.keys())
        for site in self.sites:
            code_name = SCRAPER_DICT.get(site, "")
            if code_name:
                setattr(self, f"{code_name}_length", 0)
                setattr(self, f"{code_name}_data", [])
                setattr(self, f"{code_name}_done", False)
                setattr(self, f"{code_name}_progress", 0)
                setattr(self, f"{code_name}_error", "")

    def get_progress(self) -> list[dict]:
        progress = []
        for site in self.sites:
            code_name = SCRAPER_DICT.get(site, "")
            if code_name:
                progress.append({
                    "site": site,
                    "progress": getattr(self, f"{code_name}_progress", 0),
                    "total": getattr(self, f"{code_name}_length", 0),
                    "done": getattr(self, f"{code_name}_done", False),
                    "error": getattr(self, f"{code_name}_error", ""),
                })
        return progress

    def scrape_all(self) -> list[Course]:
        """Scrape all configured sites and return unique courses."""
        logger.info(f"Starting scrape for sites: {self.sites}")
        threads = []
        for site in self.sites:
            code_name = SCRAPER_DICT.get(site)
            if not code_name or not hasattr(self, code_name):
                continue
            t = threading.Thread(target=self._scrape_site, args=(site,), daemon=True)
            t.start()
            threads.append(t)
            time.sleep(0.2)

        for t in threads:
            t.join()

        scraped_data = set()
        for site in self.sites:
            code_name = SCRAPER_DICT.get(site, "")
            if code_name:
                courses = getattr(self, f"{code_name}_data", [])
                for course in courses:
                    course.site = site
                    scraped_data.add(course)

        logger.info(f"Scraping finished. Found {len(scraped_data)} unique courses.")
        return list(scraped_data)

    def _scrape_site(self, site: str):
        code_name = SCRAPER_DICT[site]
        try:
            getattr(self, code_name)()
        except Exception:
            setattr(self, f"{code_name}_error", traceback.format_exc())
            setattr(self, f"{code_name}_length", -1)
            setattr(self, f"{code_name}_done", True)

    # ── Utility helpers ───────────────────────────────

    def _safe_future_result(self, future):
        """Unwrap a future, returning None on any exception instead of raising."""
        try:
            return future.result()
        except Exception as e:
            logger.warning(f"Worker thread failed: {e}")
            return None

    def append_to_list(self, code_name: str, title: str, link: str):
        """Thread-safe append to a site's data list."""
        if title and link:
            getattr(self, f"{code_name}_data").append(Course(title, link))

    def fetch_page(self, url: str, headers: dict = None) -> requests.Response | None:
        """Fetch a URL with retries and a hard timeout. Returns None on failure."""
        for attempt in range(3):
            try:
                return requests.get(url, headers=headers, timeout=(15, 30))
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError) as e:
                logger.warning(f"fetch_page attempt {attempt+1}/3 failed — {url}: {e}")
                time.sleep(2)
        logger.error(f"fetch_page gave up after 3 attempts: {url}")
        return None

    def safe_json(self, response: requests.Response, context: str = "") -> dict | list | None:
        """Parse JSON from a response, returning None and logging on failure."""
        if response is None:
            logger.error(f"safe_json: no response{' — ' + context if context else ''}")
            return None
        if not response.text or not response.text.strip():
            logger.error(f"safe_json: empty body (HTTP {response.status_code}){' — ' + context if context else ''}")
            return None
        try:
            return response.json()
        except Exception as e:
            logger.error(
                f"safe_json: JSONDecodeError{' — ' + context if context else ''}: {e}. "
                f"First 200 chars: {response.text[:200]}"
            )
            return None

    def parse_html(self, content) -> bs:
        return bs(content, "lxml")

    def cleanup_link(self, link: str) -> str | None:
        """Resolve redirect/affiliate links to a plain udemy.com URL. Returns None on unknown format."""
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
            logger.warning(f"cleanup_link: unknown trk.udemy.com format: {link}")
            return None
        if netloc == "click.linksynergy.com":
            query_params = parse_qs(parsed_url.query)
            if "RD_PARM1" in query_params:
                return unquote(query_params["RD_PARM1"][0])
            if "murl" in query_params:
                return unquote(query_params["murl"][0])
            logger.warning(f"cleanup_link: unknown linksynergy format: {link}")
            return None
        logger.warning(f"cleanup_link: unknown domain '{netloc}' in link: {link}")
        return None

    # ── Site scrapers ─────────────────────────────────

    def du(self):
        """Scrape Discudemy."""
        code = "du"
        try:
            all_items = []
            head = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "referer": "https://www.discudemy.com",
            }

            # Phase 1: collect listing links
            setattr(self, f"{code}_length", 10)
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(self.fetch_page, f"https://www.discudemy.com/all/{page}", headers=head): page
                    for page in range(1, 11)
                }
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        soup = self.parse_html(result.content)
                        all_items.extend(soup.find_all("a", {"class": "card-header"}))
                    setattr(self, f"{code}_progress", i + 1)

            setattr(self, f"{code}_length", len(all_items))

            # Phase 2: resolve each listing to a Udemy link
            def _fetch_details(item):
                try:
                    title = item.string
                    slug = item["href"].split("/")[-1]
                    resp = self.fetch_page(f"https://www.discudemy.com/go/{slug}", headers=head)
                    if not resp:
                        return None, None
                    soup = self.parse_html(resp.content)
                    container = soup.find("div", {"class": "ui segment"})
                    if not container or not container.a:
                        return None, None
                    return title, container.a["href"]
                except Exception as e:
                    logger.warning(f"du._fetch_details error: {e}")
                    return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_fetch_details, item) for item in all_items]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        title, link = result
                        link = self.cleanup_link(link)
                        if title and link:
                            self.append_to_list(code, title, link)
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("du scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def uf(self):
        """Scrape Udemy Freebies."""
        code = "uf"
        try:
            all_items = []
            setattr(self, f"{code}_length", 5)

            # Phase 1: collect listing pages
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(self.fetch_page, f"https://www.udemyfreebies.com/free-udemy-courses/{page}")
                    for page in range(1, 6)
                ]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        soup = self.parse_html(result.content)
                        all_items.extend(soup.find_all("a", {"class": "theme-img"}))
                    setattr(self, f"{code}_progress", i + 1)

            setattr(self, f"{code}_length", len(all_items))

            # Phase 2: resolve redirect links
            def _fetch_details(item):
                try:
                    img = item.find("img")
                    title = img["alt"] if img else None
                    parts = item.get("href", "").split("/")
                    if len(parts) < 5:
                        return None, None
                    resp = requests.get(
                        f"https://www.udemyfreebies.com/out/{parts[4]}",
                        timeout=(10, 20),
                        allow_redirects=True,
                    )
                    link = resp.url
                    return title, link
                except Exception as e:
                    logger.warning(f"uf._fetch_details error: {e}")
                    return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_fetch_details, item) for item in all_items]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        title, link = result
                        if link and "udemy.com" in link:
                            link = self.cleanup_link(link)
                            if title and link:
                                self.append_to_list(code, title, link)
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("uf scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def rd(self):
        """Scrape Real Discount."""
        code = "rd"
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Host": "cdn.real.discount",
                "Connection": "Keep-Alive",
                "dnt": "1",
                "referer": "https://www.real.discount/",
            }
            resp = self.fetch_page(
                "https://cdn.real.discount/api/courses?page=1&limit=500&sortBy=sale_start&store=Udemy&freeOnly=true",
                headers=headers,
            )
            data = self.safe_json(resp, "rd API")
            if not data:
                setattr(self, f"{code}_error", "Failed to fetch or parse Real Discount API")
                setattr(self, f"{code}_length", -1)
                return

            all_items = data.get("items", [])
            setattr(self, f"{code}_length", len(all_items))

            for index, item in enumerate(all_items):
                setattr(self, f"{code}_progress", index + 1)
                if item.get("store") == "Sponsored":
                    continue
                title = item.get("name", "").strip()
                raw_link = item.get("url", "")
                if not title or not raw_link:
                    continue
                link = self.cleanup_link(raw_link)
                if link:
                    self.append_to_list(code, title, link)

        except Exception:
            logger.exception("rd scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def cv(self):
        """Scrape Course Vania."""
        code = "cv"
        try:
            resp = self.fetch_page("https://coursevania.com/courses/")
            if not resp:
                setattr(self, f"{code}_error", "Failed to fetch Course Vania homepage")
                setattr(self, f"{code}_length", -1)
                return

            try:
                nonce = re.search(
                    r"load_content\"\:\"(.*?)\"", resp.content.decode("utf-8"), re.DOTALL
                ).group(1)
            except (AttributeError, IndexError):
                setattr(self, f"{code}_error", "Nonce not found on Course Vania")
                setattr(self, f"{code}_length", -1)
                return

            try:
                ajax_resp = requests.get(
                    "https://coursevania.com/wp-admin/admin-ajax.php"
                    "?&template=courses/grid&args={%22posts_per_page%22:%22500%22}"
                    "&action=stm_lms_load_content&sort=date_high&nonce=" + nonce,
                    timeout=(15, 30),
                )
            except Exception as e:
                setattr(self, f"{code}_error", f"AJAX request failed: {e}")
                setattr(self, f"{code}_length", -1)
                return

            ajax_data = self.safe_json(ajax_resp, "cv AJAX")
            if not ajax_data:
                setattr(self, f"{code}_length", -1)
                return

            soup = self.parse_html(ajax_data.get("content", ""))
            page_items = soup.find_all("div", {"class": "stm_lms_courses__single--title"})
            setattr(self, f"{code}_length", len(page_items))

            def _fetch_details(item):
                try:
                    h5 = item.find("h5")
                    a_tag = item.find("a")
                    if not h5 or not a_tag:
                        return None, None
                    title = h5.get_text(strip=True)
                    page = self.fetch_page(a_tag["href"])
                    if not page:
                        return None, None
                    detail_soup = self.parse_html(page.content)
                    affiliate = detail_soup.find("a", {"class": "masterstudy-button-affiliate__link"})
                    if not affiliate:
                        return None, None
                    return title, affiliate.get("href")
                except Exception as e:
                    logger.warning(f"cv._fetch_details error: {e}")
                    return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(_fetch_details, item) for item in page_items]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        title, link = result
                        if link and "udemy.com" in link:
                            link = self.cleanup_link(link)
                            if title and link:
                                self.append_to_list(code, title, link)
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("cv scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def idc(self):
        """Scrape IDownloadCoupons."""
        code = "idc"
        try:
            all_items = []
            setattr(self, f"{code}_length", 3)

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(
                        self.fetch_page,
                        f"https://idownloadcoupon.com/wp-json/wp/v2/product?product_cat=15&per_page=100&page={page}",
                    )
                    for page in range(1, 4)
                ]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        data = self.safe_json(result, f"idc page {i+1}")
                        if data:
                            all_items.extend(data)
                    setattr(self, f"{code}_progress", i + 1)

            setattr(self, f"{code}_length", len(all_items))

            def _fetch_details(item):
                try:
                    title = item.get("title", {}).get("rendered", "").strip()
                    link_num = item.get("id")
                    if not title or not link_num or link_num in (81, 85):
                        return None, None
                    url = f"https://idownloadcoupon.com/udemy/{link_num}/"
                    r = requests.get(url, allow_redirects=False, timeout=(10, 20))
                    location = r.headers.get("Location", "")
                    if not location:
                        return None, None
                    link = unquote(location)
                    if "comidoc.com" in link or "comidoc.net" in link:
                        return None, None
                    return title, self.cleanup_link(link)
                except Exception as e:
                    logger.warning(f"idc._fetch_details error: {e}")
                    return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
                futures = [executor.submit(_fetch_details, item) for item in all_items]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        title, link = result
                        if title and link:
                            self.append_to_list(code, title, link)
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("idc scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def en(self):
        """Scrape E-next."""
        code = "en"
        try:
            all_items = []
            setattr(self, f"{code}_length", 5)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(self.fetch_page, f"https://jobs.e-next.in/course/udemy/{page}")
                    for page in range(1, 6)
                ]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        soup = self.parse_html(result.content)
                        all_items.extend(soup.find_all("a", {"class": "btn btn-secondary btn-sm btn-block"}))
                    setattr(self, f"{code}_progress", i + 1)

            setattr(self, f"{code}_length", len(all_items))

            def _fetch_details(item):
                try:
                    href = item.get("href")
                    if not href:
                        return None, None
                    resp = self.fetch_page(href)
                    if not resp:
                        return None, None
                    soup = self.parse_html(resp.content)
                    h3 = soup.find("h3")
                    if not h3:
                        return None, None
                    title = h3.get_text(strip=True)
                    btn = soup.find("a", {"class": "btn btn-primary"})
                    if not btn:
                        return None, None
                    return title, btn.get("href")
                except Exception as e:
                    logger.warning(f"en._fetch_details error: {e}")
                    return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
                futures = [executor.submit(_fetch_details, item) for item in all_items]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if result:
                        title, link = result
                        if title and link:
                            self.append_to_list(code, title, link)
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("en scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def cj(self):
        """Scrape Course Joiner."""
        code = "cj"
        try:
            setattr(self, f"{code}_length", 4)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
                "Accept": "application/json, text/html,*/*;q=0.8",
                "DNT": "1",
            }

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(
                        self.fetch_page,
                        f"https://www.coursejoiner.com/wp-json/wp/v2/posts?categories=74&per_page=100&page={page}",
                        headers=headers,
                    )
                    for page in range(1, 5)
                ]
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    if not result:
                        setattr(self, f"{code}_progress", i + 1)
                        continue

                    data = self.safe_json(result, f"cj page {i+1}")
                    if not data:
                        setattr(self, f"{code}_progress", i + 1)
                        continue

                    for item in data:
                        try:
                            title = unescape(item["title"]["rendered"])
                            title = title.replace("–", "-").strip().removesuffix("- (Free Course)").strip()
                            rendered = item.get("content", {}).get("rendered", "")
                            soup = self.parse_html(rendered)
                            a_tag = soup.find("a", string="APPLY HERE")
                            if a_tag and a_tag.has_attr("href") and "udemy.com" in a_tag["href"]:
                                self.append_to_list(code, title, a_tag["href"])
                        except Exception as e:
                            logger.warning(f"cj item parse error: {e}")

                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("cj scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)

    def cxyz(self):
        """Scrape Courson."""
        code = "cxyz"
        try:
            setattr(self, f"{code}_length", 10)

            def _fetch_page(offset):
                try:
                    return requests.post(
                        "https://courson.xyz/load-more-coupons",
                        json={"filters": {}, "offset": offset},
                        timeout=(15, 30),
                    )
                except Exception as e:
                    logger.warning(f"cxyz page offset={offset} failed: {e}")
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(_fetch_page, (page - 1) * 30): page
                    for page in range(1, 11)
                }
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = self._safe_future_result(future)
                    data = self.safe_json(result, f"cxyz page {i+1}") if result else None
                    if data:
                        coupons = data.get("coupons", [])
                        for item in coupons:
                            try:
                                title = item.get("headline", "").strip(' "')
                                id_name = item.get("id_name", "")
                                coupon = item.get("coupon_code", "")
                                if title and id_name and coupon:
                                    link = f"https://www.udemy.com/course/{id_name}/?couponCode={coupon}"
                                    self.append_to_list(code, title, link)
                            except Exception as e:
                                logger.warning(f"cxyz item parse error: {e}")
                    setattr(self, f"{code}_progress", i + 1)

        except Exception:
            logger.exception("cxyz scraper failed")
            setattr(self, f"{code}_error", traceback.format_exc())
        finally:
            setattr(self, f"{code}_done", True)
