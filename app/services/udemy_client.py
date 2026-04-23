"""Udemy API client for authentication and course enrollment - Asynchronous version."""

import json
import logging
import re
import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote
from typing import Optional, Dict, List

import httpx
from bs4 import BeautifulSoup as bs
from loguru import logger

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.core import constants

# Known false-positive IDs from Udemy (e.g. tracking/user IDs appearing on blocked pages)
BLACKLIST_IDS = {"562413829"}


class LoginException(Exception):
    """Raised when Udemy login fails."""
    pass


class UdemyClient:
    """Handles asynchronous authentication and enrollment with the Udemy API."""

    def __init__(self, proxy: Optional[str] = None, firecrawl_api_key: Optional[str] = None):
        self.http = AsyncHTTPClient(proxy=proxy)
        self.firecrawl_api_key = firecrawl_api_key
        self.http.client.headers.update({
            "User-Agent": constants.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{constants.UDEMY_BASE_URL}/",
        })

        self.display_name: str = ""
        self.currency: str = "usd"
        self.cookie_dict: dict = {}
        self.enrolled_courses: Optional[Dict[str, str]] = None

        # Enrollment counters
        self.successfully_enrolled_c = 0
        self.already_enrolled_c = 0
        self.expired_c = 0
        self.excluded_c = 0
        self.amount_saved_c = Decimal(0)

        self.is_authenticated = False

    async def _firecrawl_scrape(self, url: str, schema: Optional[Dict] = None, use_cookies: bool = True) -> Optional[Dict]:
        """Perform a stealthy scrape using Firecrawl API."""
        if not self.firecrawl_api_key:
            return None
            
        try:
            headers = {"Authorization": f"Bearer {self.firecrawl_api_key}", "Content-Type": "application/json"}
            payload = {"url": url}
            
            if schema:
                payload["params"] = {"extract": {"schema": schema}}
                
            if use_cookies and self.cookie_dict:
                cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookie_dict.items()])
                payload["pageOptions"] = {"headers": {"Cookie": cookie_str}}

            resp = await self.http.post("https://api.firecrawl.dev/v0/scrape", json=payload, headers=headers, req_type="api", log_failures=False)
            data = await self.http.safe_json(resp, "firecrawl request")
            
            if data and data.get("success") and "data" in data:
                return data["data"]
            return None
        except Exception as e:
            logger.debug(f"Firecrawl request failed for {url}: {e}")
            return None

    async def _playwright_request(self, url: str, method: str = "GET", data: Optional[Dict] = None, req_type: str = "xhr") -> Optional[httpx.Response]:
        """Perform a stealthy request using a real headless browser."""
        from app.services.playwright_service import PlaywrightService
        try:
            async with PlaywrightService(proxy=self.http.proxy) as pw:
                cookies = []
                for k, v in self.cookie_dict.items():
                    cookies.append({"name": k, "value": v, "url": "https://www.udemy.com"})
                await pw._context.add_cookies(cookies)
                
                page = await pw._context.new_page()
                
                headers_dict = {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRF-Token": self.cookie_dict.get('csrf_token') or self.cookie_dict.get('csrftoken', ''),
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty"
                }
                if method == "POST":
                    headers_dict.update({
                        "Origin": constants.UDEMY_BASE_URL,
                        "Referer": f"{constants.UDEMY_BASE_URL}/payment/checkout/"
                    })
                
                headers_json = json.dumps(headers_dict)
                body_json = json.dumps(data) if data else "null"
                
                js_template = """
                async () => {
                    try {
                        const options = {
                            method: "METHOD_PLACEHOLDER",
                            headers: HEADERS_PLACEHOLDER,
                            credentials: "include"
                        };
                        const bodyData = BODY_PLACEHOLDER;
                        if (bodyData !== "null" && bodyData !== null) {
                            options.body = JSON.stringify(bodyData);
                        }
                        
                        const response = await fetch("URL_PLACEHOLDER", options);
                        return {
                            status: response.status,
                            content: await response.text(),
                            url: response.url
                        };
                    } catch (e) {
                        return { status: 0, content: e.message, url: "" };
                    }
                }
                """
                js_script = js_template.replace("URL_PLACEHOLDER", url) \
                                      .replace("METHOD_PLACEHOLDER", method) \
                                      .replace("HEADERS_PLACEHOLDER", headers_json) \
                                      .replace("BODY_PLACEHOLDER", body_json)
                try:
                    await page.goto(f"{constants.UDEMY_BASE_URL}/robots.txt", wait_until="commit", timeout=15000)
                    await asyncio.sleep(1) # Stabilization
                except Exception as e:
                    logger.debug(f"Playwright navigation to robots.txt timed out: {e}")
                
                result = await page.evaluate(js_script)
                await page.close()
                
                if result:
                    if result['status'] == 0:
                        logger.error(f"Playwright fetch error for {url}: {result['content']}")
                        return None
                    
                    if result['status'] != 200:
                        logger.debug(f"  Playwright request to {url} returned status {result['status']}")

                    mock_resp = httpx.Response(
                        status_code=result['status'],
                        content=result['content'].encode(),
                        request=httpx.Request(method, result.get('url', url))
                    )
                    return mock_resp
                return None
        except Exception as e:
            logger.error(f"Playwright request failed for {url}: {e}")
            return None

    async def close(self):
        await self.http.close()

    def set_proxy(self, proxy: Optional[str]):
        """Update the proxy configuration."""
        if self.http.proxy != proxy:
            old_headers = self.http.client.headers
            old_cookies = self.http.client.cookies
            asyncio.create_task(self.http.close())
            self.http = AsyncHTTPClient(proxy=proxy)
            self.http.client.headers.update(old_headers)
            self.http.client.cookies.update(old_cookies)

    async def _check_cloudflare_challenge(self, html: str) -> bool:
        """Detect if page is Cloudflare challenge. Returns True if Cloudflare challenge detected."""
        cloudflare_indicators = [
            'Just a moment',
            'challenge-platform',
            'Checking your browser before accessing',
            'Ray ID',
            '__cf_bm',
            'cf_clearance',
            'cfrequests',
            'Cloudflare',
        ]
        return any(indicator in html for indicator in cloudflare_indicators)

    async def _extract_csrf_from_html(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML using various methods. Returns token value or None."""
        if not html:
            return None
        
        # Method 1: Look for csrftoken in meta tag
        meta_match = re.search(r'<meta[^>]*name=["\']csrftoken["\'][^>]*content=["\']([^"\']+)["\']', html)
        if meta_match:
            token = meta_match.group(1)
            logger.debug(f"Found CSRF token in meta tag: {token[:20]}...")
            return token
        
        # Method 2: Look for csrf_token in meta tag
        meta_match = re.search(r'<meta[^>]*name=["\']csrf_token["\'][^>]*content=["\']([^"\']+)["\']', html)
        if meta_match:
            token = meta_match.group(1)
            logger.debug(f"Found csrf_token in meta tag: {token[:20]}...")
            return token
        
        # Method 3: Look for CSRF token in script data (flexible pattern)
        script_match = re.search(r'["\']?csrf["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']', html, re.IGNORECASE)
        if script_match:
            token = script_match.group(1)
            logger.debug(f"Found CSRF token in script: {token[:20]}...")
            return token
        
        # Method 4: Look for X-CSRFToken or similar in script (flexible pattern)
        script_match = re.search(r'["\']?X-CSRF-?Token["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']', html, re.IGNORECASE)
        if script_match:
            token = script_match.group(1)
            logger.debug(f"Found X-CSRFToken in script: {token[:20]}...")
            return token
        
        # Method 5: Look for CSRF in any data attribute or hidden input
        input_match = re.search(r'<input[^>]*name=["\']csrf(?:token)?["\'][^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if input_match:
            token = input_match.group(1)
            logger.debug(f"Found CSRF in hidden input: {token[:20]}...")
            return token
        
        logger.warning("No CSRF token found in HTML")
        return None

    async def _refresh_csrf_stealth(self) -> bool:
        """Refresh CSRF token and all session cookies using Playwright. Returns True if successful."""
        from app.services.playwright_service import PlaywrightService
        logger.info("Stealth: Refreshing CSRF token and cookies via Playwright...")
        csrf_found = False
        try:
            # CRITICAL: Always fetch a fresh CSRF token from the server, never reuse from login
            # The old approach of reusing login tokens was causing persistent 403 errors
            logger.debug("Fetching fresh CSRF token (not reusing login token)...")
            
            async with PlaywrightService(proxy=self.http.proxy) as pw:
                page = await pw._context.new_page()
                
                # Attempt with multiple strategies
                for strategy_attempt in range(2):
                    if strategy_attempt == 1:
                        logger.info("Trying alternate Cloudflare resolution strategy...")
                    
                    # STRATEGY: Navigate to home page with extended wait
                    await page.goto(f"{constants.UDEMY_BASE_URL}/", wait_until="commit", timeout=30000)
                    await asyncio.sleep(2) # Initial wait for page load
                    
                    # Check if we hit Cloudflare challenge
                    html_content = await page.content()
                    is_cf_challenge = await self._check_cloudflare_challenge(html_content)
                    
                    if is_cf_challenge:
                        logger.warning("Cloudflare challenge detected. Waiting for challenge resolution...")
                        challenge_resolved = False
                        
                        # EXTENDED WAIT: Try to resolve challenge with longer delays
                        for wait_attempt in range(15):  # 15 attempts × 2 seconds = 30 seconds max
                            await asyncio.sleep(2)
                            html_content = await page.content()
                            
                            if not await self._check_cloudflare_challenge(html_content):
                                logger.info(f"Cloudflare challenge resolved after {(wait_attempt + 1) * 2} seconds")
                                challenge_resolved = True
                                break
                        
                        if not challenge_resolved:
                            logger.warning("Cloudflare challenge persisted after 30 seconds. Trying page reload...")
                            # Try reloading the page to trigger challenge resolution
                            try:
                                await page.reload(wait_until="commit", timeout=30000)
                                await asyncio.sleep(3)
                                html_content = await page.content()
                                if not await self._check_cloudflare_challenge(html_content):
                                    logger.info("Challenge resolved after page reload")
                                    challenge_resolved = True
                            except Exception as e:
                                logger.debug(f"Page reload failed: {e}")
                        
                        if not challenge_resolved and strategy_attempt < 1:
                            logger.warning("Challenge still unresolved. Trying with fresh context...")
                            await page.close()
                            continue
                    
                    # PART 1: Extract cookies
                    cookies = await pw._context.cookies()
                    logger.debug(f"Received {len(cookies)} cookies from Playwright")
                    
                    cookie_names = [c['name'] for c in cookies]
                    logger.debug(f"Cookie names: {', '.join(cookie_names[:20])}")
                    
                    cf_clearance_found = False
                    for c in cookies:
                        self.http.client.cookies.set(c['name'], c['value'])
                        self.cookie_dict[c['name']] = c['value']
                        if c['name'] in ('csrftoken', 'csrf_token'):
                            logger.info(f"SUCCESS: Found {c['name']} in cookies!")
                            csrf_found = True
                        if c['name'] == 'cf_clearance':
                            logger.debug(f"Found Cloudflare clearance cookie")
                            cf_clearance_found = True
                    
                    # If we have CSRF token from cookies, we're done
                    if csrf_found:
                        break
                    
                    # If we got cf_clearance but no CSRF token, Cloudflare challenge isn't fully resolved
                    if cf_clearance_found and is_cf_challenge:
                        logger.warning("Cloudflare clearance found but CSRF token missing from cookies. Session may not be fully authenticated.")
                        if strategy_attempt < 1:
                            logger.info("Retrying with fresh context...")
                            await page.close()
                            continue
                    
                    # PART 2: Extract from HTTP headers
                    if not csrf_found:
                        logger.debug("CSRF token not in cookies, attempting header extraction...")
                        try:
                            request = await page.evaluate("() => fetch(window.location.href, {method: 'HEAD'}).then(r => Object.fromEntries(r.headers))")
                            if request and isinstance(request, dict):
                                for header_name in ['x-csrftoken', 'X-CSRFToken', 'X-CSRF-Token']:
                                    if header_name in request:
                                        csrf_token = request[header_name]
                                        self.http.client.headers['X-CSRFToken'] = csrf_token
                                        self.cookie_dict['_csrf_from_header'] = csrf_token
                                        logger.info(f"Success: Extracted CSRF from response header ({header_name})")
                                        csrf_found = True
                                        break
                        except Exception as e:
                            logger.debug(f"Header extraction failed: {e}")
                    
                    # PART 3: Extract from HTML
                    if not csrf_found:
                        logger.debug("CSRF token not in cookies/headers, attempting HTML extraction...")
                        csrf_token = await self._extract_csrf_from_html(html_content)
                        
                        if csrf_token:
                            self.http.client.headers['X-CSRFToken'] = csrf_token
                            self.cookie_dict['_csrf_from_html'] = csrf_token
                            logger.info(f"Success: Extracted CSRF from HTML")
                            csrf_found = True
                        else:
                            logger.warning("Could not find CSRF token in HTML")
                    
                    # If we found a token, we're done with strategies
                    if csrf_found:
                        break
                    
                    # If Cloudflare challenge was blocking and we didn't get token, retry strategy
                    if is_cf_challenge and not csrf_found and strategy_attempt < 1:
                        logger.warning(f"Cloudflare likely still blocking. Retrying with fresh page...")
                        await page.close()
                        page = await pw._context.new_page()
                        continue
                    
                    # No more strategies to try
                    break
                
                # FINAL ATTEMPT: If still no token, check session validity
                if not csrf_found:
                    logger.error("No CSRF token found after all strategies and extraction methods.")
                    # Check if we have any auth cookies at all
                    auth_cookies = [c for c in cookies if any(name in c['name'].lower() for name in ['auth', 'access', 'sessionid', 'jwt'])]
                    if not auth_cookies:
                        logger.error("CRITICAL: No authentication cookies found. Session is not authenticated. This user needs to log in again.")
                    else:
                        logger.warning(f"Auth cookies exist ({len(auth_cookies)}) but CSRF token not accessible. May be IP/session block or Cloudflare still blocking.")
                
                await page.close()
                
                if csrf_found:
                    logger.info("CSRF token refresh successful")
                else:
                    logger.error("CSRF token refresh failed - no valid token obtained after all attempts")
                    
                return csrf_found
        except Exception as e:
            logger.error(f"Failed to refresh CSRF via Playwright: {e}")
            return False

    async def manual_login(self, email: str, password: str):
        """Asynchronously login using email and password."""
        logger.info(f"Attempting manual login for {email}")
        try:
            r = await self.http.get(
                constants.UDEMY_SIGNUP_POPUP_URL,
                headers={"User-Agent": constants.DEFAULT_USER_AGENT},
                randomize_headers=False,
                req_type="document"
            )
            if not r:
                raise LoginException("Could not connect to Udemy.")

            csrf_token = r.cookies.get("csrftoken")
            if not csrf_token:
                raise LoginException("Email/password login is currently restricted by Udemy security.")

            data = {
                "csrfmiddlewaretoken": csrf_token,
                "locale": "en_US",
                "email": email,
                "password": password,
            }

            self.http.client.cookies.update(r.cookies)
            self.http.client.headers.update({
                "Referer": constants.UDEMY_LOGIN_POPUP_URL,
                "Origin": constants.UDEMY_BASE_URL,
            })

            resp = await self.http.post(
                constants.UDEMY_LOGIN_POPUP_URL,
                data=data,
                req_type="api"
            )

            if resp and "returnUrl" in resp.text:
                self.cookie_dict = {
                    "client_id": resp.cookies.get("client_id"),
                    "access_token": resp.cookies.get("access_token"),
                    "csrf_token": csrf_token,
                }
            else:
                error_data = await self.http.safe_json(resp, "login error")
                msg = error_data.get("error", {}).get("data", {}).get("formErrors", [["Unknown error"]])[0][0]
                raise LoginException(msg)

        except Exception as e:
            if isinstance(e, LoginException):
                raise
            logger.exception("Manual login failed")
            raise LoginException(f"Login failed: {str(e)}")

    def cookie_login(self, access_token: str, client_id: str, csrf_token: str):
        """Login using cookies (from browser)."""
        self.cookie_dict = {
            "client_id": client_id,
            "access_token": access_token,
            "csrf_token": csrf_token,
        }
        self.http.client.cookies.update(self.cookie_dict)

    async def get_session_info(self):
        """Fetch session info asynchronously."""
        logger.info("Getting session info")
        try:
            headers = {"req_type": "api"}
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            resp = await self.http.get(
                constants.UDEMY_CONTEXT_URL,
                cookies=self.cookie_dict,
                headers=headers,
                randomize_headers=True,
                req_type="api"
            )
            ctx = await self.http.safe_json(resp, "session info")
            if not ctx or not ctx.get("header", {}).get("isLoggedIn"):
                raise LoginException("Login failed - session invalid.")

            self.display_name = ctx["header"]["user"]["display_name"]

            cart_resp = await self.http.get(
                constants.UDEMY_CART_URL,
                cookies=self.cookie_dict,
                headers=headers,
                randomize_headers=True,
                req_type="api"
            )
            cart = await self.http.safe_json(cart_resp, "cart info")
            if cart:
                self.currency = cart.get("user", {}).get("credit", {}).get("currency_code", "usd")

            self.is_authenticated = True
            logger.info(f"Authenticated as {self.display_name} ({self.currency.upper()})")

        except Exception as e:
            logger.exception("Failed to get session info")
            raise LoginException(f"Session verification failed: {str(e)}")

    async def get_enrolled_courses(self, known_slugs: set = None):
        """Fetch all enrolled courses in parallel pages. Stops early if known courses are found."""
        logger.info("Fetching enrolled courses...")
        base_url = f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"
        
        self.enrolled_courses = {}
        known_slugs = known_slugs or set()
        
        common_headers = {}
        if self.cookie_dict.get("access_token"):
            common_headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

        resp = await self.http.get(base_url, cookies=self.cookie_dict, headers=common_headers, req_type="api")
        data = await self.http.safe_json(resp, "enrolled courses page 1")
        if not data:
            return

        def process_results(results):
            stop = False
            for c in results:
                try:
                    parts = c["url"].split("/")
                    slug = parts[3] if len(parts) > 3 and parts[2] == "draft" else parts[2]
                    self.enrolled_courses[slug] = c.get("enrollment_time", "")
                    if slug in known_slugs:
                        stop = True
                except (IndexError, KeyError):
                    continue
            return stop

        if process_results(data.get("results", [])):
            logger.info(f"Fetched 1 page of enrolled courses (Reached known courses).")
            return

        batch_size = 5
        for start_page in range(2, 51, batch_size):
            tasks = []
            for page in range(start_page, start_page + batch_size):
                if page > 50: break
                url = f"{base_url}&page={page}"
                tasks.append(self.http.get(url, cookies=self.cookie_dict, headers=common_headers, req_type="api"))
            
            resps = await asyncio.gather(*tasks)
            any_stop = False
            for i, r in enumerate(resps):
                page_data = await self.http.safe_json(r, f"enrolled courses page {start_page + i}")
                if page_data and page_data.get("results"):
                    if process_results(page_data["results"]):
                        any_stop = True
                else:
                    any_stop = True
            
            if any_stop:
                logger.info(f"Reached known courses or end of list at batch starting page {start_page}.")
                break

        for slug in known_slugs:
            if slug not in self.enrolled_courses:
                self.enrolled_courses[slug] = ""
        logger.info(f"Enrolled courses check complete. Total tracked: {len(self.enrolled_courses)}.")

    def _extract_course_id(self, soup: bs) -> Optional[str]:
        """Extract course ID using multiple strategies."""
        BLACKLIST_IDS = {"562413829"}

        body = soup.find("body")
        if body:
            cid = body.get("data-clp-course-id") or body.get("data-course-id")
            if cid and str(cid) not in BLACKLIST_IDS:
                logger.debug(f"Found course ID {cid} via body data-attribute")
                return str(cid)

        meta_tags = [
            ("meta", {"property": "udemy_com:course"}),
            ("meta", {"name": "course-id"}),
            ("meta", {"property": "og:url"}),
        ]
        for tag, attrs in meta_tags:
            el = soup.find(tag, attrs)
            if el:
                content = el.get("content")
                if content and str(content) not in BLACKLIST_IDS:
                    if attrs.get("property") == "udemy_com:course" or attrs.get("name") == "course-id":
                        logger.debug(f"Found course ID {content} via meta tag {tag}")
                        return str(content)

        scripts = soup.find_all("script")
        for script in scripts:
            if not script.string:
                continue
            
            patterns = [
                (r'["\']?course["\']?\s*:\s*{\s*["\']?id["\']?\s*[:=]\s*(\d+)', "script course object id"),
                (r'["\']?visiting_course["\']?\s*:\s*{\s*["\']?id["\']?\s*[:=]\s*(\d+)', "script visiting_course object id"),
                (r'["\']?course_?id["\']?\s*[:=]\s*(\d+)', "script regex course_id"),
                (r'["\']?courseId["\']?\s*[:=]\s*(\d+)', "script regex courseId")
            ]
            for pattern, name in patterns:
                match = re.search(pattern, script.string, re.IGNORECASE)
                if match:
                    cid = match.group(1)
                    if cid and 4 < len(cid) < 12 and cid not in BLACKLIST_IDS:
                        logger.debug(f"Found course ID {cid} via {name}")
                        return cid

        return None

    async def get_course_id(self, course: Course, use_headless_fallback: bool = True):
        """Fetch course ID and metadata with Firecrawl-first, Playwright fallback chain."""
        if course.course_id:
            return
        url = re.sub(r"\W+$", "", unquote(course.url))
        
        if self.firecrawl_api_key:
            logger.info(f"Stealth: Fetching course ID for {course.title} via Firecrawl...")
            fc_schema = {"type": "object", "properties": {"course_id": {"type": "string"}, "title": {"type": "string"}}}
            fc_data = await self._firecrawl_scrape(url, schema=fc_schema)
            if fc_data and "extract" in fc_data:
                cid = fc_data["extract"].get("course_id")
                if cid and str(cid) not in BLACKLIST_IDS:
                    course.course_id = str(cid)
                    final_url = fc_data.get("metadata", {}).get("pageUrl")
                    if final_url and "udemy.com" in final_url:
                        logger.debug(f"  Firecrawl redirected to: {final_url}")
                        course.set_url(final_url)
                    
                    if course.coupon_code:
                        logger.debug(f"  Success: Found ID {course.course_id} and coupon via Firecrawl")
                        return
                    else:
                        logger.debug(f"  Firecrawl found ID {course.course_id} but no coupon. Continuing to fallback...")

        consecutive_403 = 0
        max_403_retries = 2
        
        if use_headless_fallback:
            logger.info(f"Stealth: Fetching course ID for {course.title} via Playwright...")
            while consecutive_403 < max_403_retries:
                resp = await self._playwright_request(url, req_type="document")
                if resp and resp.status_code == 200:
                    final_url = str(resp.url)
                    logger.debug(f"  Playwright resolved to: {final_url}")
                    course.set_url(final_url)
                    soup = bs(resp.content, "lxml")
                    body = soup.find("body")
                    if body:
                        try:
                            dma = json.loads(body.get("data-module-args", "{}"))
                            course.set_metadata(dma)
                        except Exception: pass
                    if not course.course_id:
                        course.course_id = self._extract_course_id(soup)
                    if course.course_id:
                        if course.coupon_code:
                            logger.debug(f"  Success: Found ID {course.course_id} and coupon via Playwright")
                        else:
                            logger.debug(f"  Success: Found ID {course.course_id} via Playwright (still no coupon)")
                        return
                    break
                elif resp and resp.status_code == 403:
                    consecutive_403 += 1
                    if consecutive_403 < max_403_retries:
                        logger.warning(f"403 Forbidden on course fetch for {course.title}. Refreshing session (attempt {consecutive_403}/{max_403_retries})...")
                        if await self._refresh_csrf_stealth():
                            await asyncio.sleep(1)
                            continue
                    logger.error(f"Too many 403 errors ({consecutive_403}) on Playwright course fetch. Falling back to standard.")
                    break
                else:
                    logger.debug(f"Playwright returned {resp.status_code if resp else 'None'}. Falling back to standard.")
                    break

        logger.info(f"Standard: Fetching course ID for {course.title}...")
        consecutive_403 = 0
        while consecutive_403 < max_403_retries:
            resp = await self.http.get(url, log_failures=False, raise_for_status=False)
            if resp and resp.status_code == 200:
                final_url = str(resp.url)
                logger.debug(f"  Standard Request resolved to: {final_url}")
                course.set_url(final_url)
                soup = bs(resp.content, "lxml")
                body = soup.find("body")
                if body:
                    try:
                        dma = json.loads(body.get("data-module-args", "{}"))
                        course.set_metadata(dma)
                    except Exception: pass
                if not course.course_id:
                    course.course_id = self._extract_course_id(soup)
                if course.course_id:
                    return
                break
            elif resp and resp.status_code == 403:
                consecutive_403 += 1
                if consecutive_403 < max_403_retries:
                    logger.warning(f"403 Forbidden on course fetch for {course.title}. Refreshing session (attempt {consecutive_403}/{max_403_retries})...")
                    if await self._refresh_csrf_stealth():
                        await asyncio.sleep(1)
                        continue
                logger.error(f"Too many 403 errors ({consecutive_403}) on standard course fetch. Giving up.")
                break
            else:
                logger.debug(f"Standard request returned {resp.status_code if resp else 'None'}.")
                break

        if not course.course_id:
            course.is_valid = False
            if resp and resp.status_code == 200:
                course.error = "Course ID not found"
            else:
                course.error = f"Failed to fetch course page ({resp.status_code if resp else 'No response'})"
            logger.warning(f"Failed to identify course: {course.title}")

    async def check_course(self, course: Course):
        """Check coupon validity with Firecrawl-first, Playwright fallback chain."""
        if course.price is not None:
            return
        
        url = f"{constants.UDEMY_COURSE_LANDING_COMPONENTS_URL}{course.course_id}/me/?components=purchase"
        if course.coupon_code:
            url += f",redeem_coupon&couponCode={course.coupon_code}"

        r = None
        if self.firecrawl_api_key:
            logger.info(f"Stealth: Checking coupon for {course.title} via Firecrawl...")
            fc_data = await self._firecrawl_scrape(url)
            if fc_data and "content" in fc_data:
                try:
                    r = json.loads(fc_data["content"])
                except Exception: pass

        if not r:
            logger.info(f"Stealth: Checking coupon for {course.title} via Playwright...")
            resp = await self._playwright_request(url)
            if resp and resp.status_code == 200:
                r = await self.http.safe_json(resp, "playwright check course")

        if not r:
            logger.info(f"Standard: Checking coupon for {course.title}...")
            resp = await self.http.get(url, cookies=self.cookie_dict)
            r = await self.http.safe_json(resp, "standard check course")

        if not r:
            course.is_coupon_valid = False
            course.error = "Failed to fetch course price info"
            return

        purchase_data = r.get("purchase", {}).get("data", {})
        amount = purchase_data.get("list_price", {}).get("amount")
        course.price = Decimal(str(amount)) if amount is not None else None

        if course.coupon_code:
            if "redeem_coupon" in r:
                discount_attempts = r["redeem_coupon"].get("discount_attempts", [])
                if discount_attempts:
                    status = discount_attempts[0].get("status")
                    pricing = purchase_data.get("pricing_result", {})
                    discount = pricing.get("discount_percent")
                    
                    if (status == "applied" or status == "unused") and discount == 100:
                        course.is_coupon_valid = True
                    else:
                        course.is_coupon_valid = False
                        if status not in ("applied", "unused"):
                            course.error = f"Coupon status: {status}"
                        elif discount != 100:
                            course.error = f"Coupon only {discount}% off (not 100%)"
                else:
                    course.is_coupon_valid = False
                    course.error = "No discount attempts returned"
            else:
                course.is_coupon_valid = False
                course.error = "Coupon not found in response"
        else:
            course.is_coupon_valid = False
            course.error = "No coupon code provided"

    async def is_already_enrolled(self, course: Course, known_slugs: set = None) -> bool:
        if self.enrolled_courses is None:
            await self.get_enrolled_courses(known_slugs)
        return course.slug in self.enrolled_courses

    def is_course_excluded(self, course: Course, settings: dict):
        return

    async def free_checkout(self, course: Course):
        """Enroll in a free course with Playwright-first stealth fallback."""
        sub_url = f"{constants.UDEMY_COURSE_SUBSCRIBE_URL}?courseId={course.course_id}"
        status_url = f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private"
        
        csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
        
        logger.info(f"Stealth: Enrolling in free course {course.title} via Playwright...")
        resp = await self._playwright_request(sub_url, method="POST")
        if resp and resp.status_code == 200:
            check_resp = await self._playwright_request(status_url)
            if check_resp and check_resp.status_code == 200:
                data = await self.http.safe_json(check_resp, "playwright free checkout check")
                course.status = data.get("_class") == "course" if data else False
                if course.status: 
                    logger.debug(f"  Success: Enrolled in {course.title} via Playwright")
                    return

        logger.info(f"Standard: Enrolling in free course {course.title}...")
        headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}
        await self.http.post(sub_url, cookies=self.cookie_dict, headers=headers, req_type="api", log_failures=False)
        
        resp = await self.http.get(status_url, cookies=self.cookie_dict, req_type="api", log_failures=False)
        if resp and resp.status_code == 200:
            data = await self.http.safe_json(resp, "standard free checkout check")
            course.status = data.get("_class") == "course" if data else False
            if course.status:
                return

        logger.info(f"Fallback: Using checkout pipeline for free course {course.title}...")
        course.status = await self.checkout_single(course)

    async def checkout_single(self, course: Course) -> bool:
        """Asynchronously enroll in a single course with a coupon."""
        max_retry_attempts = 2
        attempt_count = 0
        
        for retry_attempt in range(max_retry_attempts):
            attempt_count += 1
            csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
            if not csrf_token:
                 refresh_success = await self._refresh_csrf_stealth()
                 if not refresh_success:
                     logger.error(f"Failed to obtain CSRF token for {course.title}")
                     if retry_attempt >= max_retry_attempts - 1:
                         return False
                     await asyncio.sleep(2)
                     continue
                 csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
                 if not csrf_token:
                     logger.error(f"CSRF token still empty after refresh for {course.title}")
                     if retry_attempt >= max_retry_attempts - 1:
                         return False
                     await asyncio.sleep(2)
                     continue

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": constants.UDEMY_CHECKOUT_URL,
                "X-CSRF-Token": csrf_token,
            }
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            result = await self._checkout_one(course, headers)
            if result:
                logger.debug(f"✓ Single-course checkout succeeded for {course.title} (attempt {attempt_count})")
                return True
        
        logger.warning(f"✗ Single-course checkout failed for {course.title} after {attempt_count} attempts")
        return False

    @staticmethod
    def _title_overlap(a: str, b: str) -> float:
        def tokenize(s):
            s = re.sub(r'\b(20\d{2})\b', '', s)
            s = re.sub(r'[^\w\s]', '', s.lower())
            return set(s.split()) - {'the', 'a', 'an', 'and', 'or', 'in', 'of', 'to', 'for'}
        ta, tb = tokenize(a), tokenize(b)
        if not ta or not tb: return 0.0
        return len(ta & tb) / len(ta | tb)

    def _throttle_wait(self, result: dict) -> int:
        detail = result.get("detail", "")
        if "throttled" in str(detail).lower():
            match = re.search(r"(\d+)\s+second", str(detail), re.IGNORECASE)
            return int(match.group(1)) if match else 60
        return 0

    async def _checkout_one(self, course: Course, headers: dict) -> bool:
        """Enroll with coupon via Playwright-first stealth chain (POST required)."""
        payload = {
            "checkout_environment": "Marketplace",
            "checkout_event": "Submit",
            "payment_info": {"method_id": "0", "payment_method": "free-method", "payment_vendor": "Free"},
            "shopping_info": {
                "items": [{
                    "buyable": {"id": str(course.course_id), "type": "course"},
                    "discountInfo": {"code": course.coupon_code},
                    "price": {"amount": 0, "currency": self.currency.upper()},
                }],
                "is_cart": True,
            },
        }
        
        # Increase max attempts significantly due to Cloudflare challenges
        max_attempts = 7  # Increased from 5
        consecutive_403_count = 0
        max_403_consecutive = 4  # Increased from 3 (Cloudflare can cause multiple 403s)
        
        for attempt in range(max_attempts):
            # Try to get CSRF token from multiple sources (prioritize real tokens)
            csrf = (self.http.client.cookies.get("csrftoken") or 
                   self.cookie_dict.get("csrf_token") or 
                   self.cookie_dict.get("_csrf_from_header") or 
                   self.http.client.headers.get("X-CSRFToken") or 
                   self.cookie_dict.get("_csrf_from_html", ""))
            
            # Log token source for debugging (real vs fallback)
            if csrf:
                token_source = "cookie"
                if "_csrf_from_header" in self.cookie_dict and self.cookie_dict.get("_csrf_from_header") == csrf:
                    token_source = "response_header"
                elif "_csrf_from_html" in self.cookie_dict and self.cookie_dict.get("_csrf_from_html") == csrf:
                    token_source = "html"
                elif "_csrf_fallback" in self.cookie_dict and self.cookie_dict.get("_csrf_fallback") == csrf:
                    token_source = "fallback_uuid"
                    logger.warning(f"Using fallback UUID token for {course.title} - session may be invalid")
                logger.debug(f"Using CSRF token from {token_source}: {csrf[:20]}..." if len(csrf) > 20 else f"Using CSRF token from {token_source}")
            else:
                logger.warning("No CSRF token available for checkout")
            
            headers["X-CSRFToken"] = csrf

            logger.info(f"Stealth: Executing checkout for {course.title} via Playwright (attempt {attempt + 1}/{max_attempts})...")
            resp = await self._playwright_request(constants.UDEMY_CHECKOUT_SUBMIT_URL, method="POST", data=payload)
            
            if not resp or resp.status_code != 200:
                logger.info(f"Standard: Falling back to HTTPX checkout for {course.title}...")
                resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=True, req_type="xhr", attempts=1, raise_for_status=False)
            
            if not resp:
                continue
            
            if resp.status_code == 403:
                consecutive_403_count += 1
                if consecutive_403_count > max_403_consecutive:
                    logger.error(f"Too many 403 errors ({consecutive_403_count}) for {course.title}. Giving up.")
                    return False
                
                logger.warning(f"403 Forbidden on checkout for {course.title}. Refreshing session (attempt {consecutive_403_count}/{max_403_consecutive})...")
                
                # Implement improved exponential backoff with jitter
                base_backoff = min(2 ** consecutive_403_count, 16)  # 2, 4, 8, 16 seconds (capped at 16)
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = base_backoff + jitter
                logger.debug(f"Waiting {backoff_delay:.1f}s before session refresh (base: {base_backoff}s, jitter: {jitter:.1f}s)...")
                await asyncio.sleep(backoff_delay)
                
                # On repeated 403 errors, suggest using Firecrawl if available
                if consecutive_403_count >= 2 and self.firecrawl_api_key:
                    logger.info(f"Persistent 403 errors detected. Consider using Firecrawl API for course fetch/checkout operations.")
                
                refresh_success = await self._refresh_csrf_stealth()
                if not refresh_success:
                    logger.error(f"Failed to refresh CSRF token for {course.title}. Session may be invalid.")
                    if consecutive_403_count >= max_403_consecutive:
                        return False
                else:
                    # Extra wait after successful refresh to ensure cookies are synced
                    await asyncio.sleep(3)
                
                continue

            consecutive_403_count = 0
            result = await self.http.safe_json(resp, "checkout one")
            if result and result.get("status") == "succeeded":
                self.amount_saved_c += Decimal(str(course.price or 0))
                self.successfully_enrolled_c += 1
                if self.enrolled_courses is not None:
                    self.enrolled_courses[course.slug] = datetime.now(UTC).isoformat()
                return True
            
            wait = self._throttle_wait(result or {})
            if wait:
                logger.info(f"Throttled. Waiting {wait} seconds before retry...")
                await asyncio.sleep(wait)
                continue
            
            logger.warning(f"Checkout failed with response status {resp.status_code}. Giving up.")
            break
        return False

    async def bulk_checkout(self, courses: List[Course]) -> Dict[Course, str]:
        """Asynchronously enroll in a batch of courses with stealth priority."""
        outcomes: Dict[Course, str] = {c: "failed" for c in courses}
        if not courses:
            return outcomes
        
        # Monitoring metrics
        metrics = {
            "total_attempts": 0,
            "successful_403_recoveries": 0,
            "failed_checkouts": 0,
            "session_blocks": 0,
            "total_delay_time": 0.0,
            "start_time": asyncio.get_event_loop().time(),
        }
        
        remaining = list(courses)
        max_bulk_attempts = len(courses) + 2
        consecutive_403_count = 0
        max_403_consecutive = 3
        
        for attempt in range(max_bulk_attempts):
            if not remaining:
                break
            
            metrics["total_attempts"] += 1
            
            if attempt > 0:
                # Improved exponential backoff with jitter
                # Start at 2s, double each time: 2s, 4s, 8s, 16s (capped)
                base_delay = min(2 ** (attempt), 16)  # Capped at 16 seconds
                # Add extra delay if we've had 403s (adaptive multiplier)
                if consecutive_403_count > 0:
                    adaptive_multiplier = 1.0 + (consecutive_403_count * 0.4)  # 1.4x, 1.8x, 2.2x...
                    base_delay *= adaptive_multiplier
                
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = min(base_delay + jitter, 20)  # Cap final delay at 20 seconds
                metrics["total_delay_time"] += backoff_delay
                
                logger.info(f"Waiting {backoff_delay:.1f}s before bulk checkout retry "
                           f"(attempt {attempt + 1}/{max_bulk_attempts}, "
                           f"403_count={consecutive_403_count}/{max_403_consecutive}, "
                           f"base={base_delay:.1f}s, jitter={jitter:.1f}s)...")
                await asyncio.sleep(backoff_delay)

            csrf_token = (self.http.client.cookies.get("csrftoken") or 
                         self.cookie_dict.get("csrf_token") or 
                         self.http.client.headers.get("X-CSRFToken") or 
                         self.cookie_dict.get("_csrf_from_html", ""))
            if not csrf_token:
                 logger.info(f"No CSRF token for bulk checkout. Refreshing...")
                 refresh_success = await self._refresh_csrf_stealth()
                 if not refresh_success:
                     logger.error(f"Failed to refresh CSRF token for bulk checkout")
                     consecutive_403_count += 1
                     if consecutive_403_count >= max_403_consecutive:
                         logger.error(f"Too many consecutive refresh failures ({consecutive_403_count}). Giving up bulk checkout.")
                         metrics["session_blocks"] += 1
                         break
                     continue
                 csrf_token = (self.http.client.cookies.get("csrftoken") or 
                              self.cookie_dict.get("csrf_token") or 
                              self.http.client.headers.get("X-CSRFToken") or 
                              self.cookie_dict.get("_csrf_from_html", ""))
                 if not csrf_token:
                     logger.error("CSRF token still empty after refresh")
                     consecutive_403_count += 1
                     if consecutive_403_count >= max_403_consecutive:
                         logger.error(f"Too many consecutive CSRF failures. Giving up bulk checkout.")
                         metrics["session_blocks"] += 1
                         break
                     continue

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.udemy.com/payment/checkout/",
                "X-CSRF-Token": csrf_token,
            }
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            items = [{
                "buyable": {"id": str(c.course_id), "type": "course"},
                "discountInfo": {"code": c.coupon_code},
                "price": {"amount": 0, "currency": self.currency.upper()},
            } for c in remaining]
            
            payload = {
                "checkout_environment": "Marketplace",
                "checkout_event": "Submit",
                "payment_info": {"method_id": "0", "payment_method": "free-method", "payment_vendor": "Free"},
                "shopping_info": {"items": items, "is_cart": True},
            }
            
            logger.info(f"Stealth: Executing bulk checkout for {len(remaining)} courses via Playwright (attempt {attempt + 1}/{max_bulk_attempts})...")
            resp = await self._playwright_request(constants.UDEMY_CHECKOUT_SUBMIT_URL, method="POST", data=payload)
            
            if not resp or resp.status_code != 200:
                logger.info("Standard: Falling back to HTTPX for bulk checkout...")
                resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=True, req_type="xhr", attempts=1, raise_for_status=False)
            
            if not resp:
                logger.warning(f"No response from bulk checkout attempt {attempt + 1}")
                continue
                
            if resp.status_code == 403:
                consecutive_403_count += 1
                if consecutive_403_count > max_403_consecutive:
                    logger.error(f"Too many 403 errors ({consecutive_403_count}) on bulk checkout. Session may be blocked. Giving up.")
                    metrics["session_blocks"] += 1
                    break
                
                logger.warning(f"Bulk checkout hit 403 Forbidden (attempt {consecutive_403_count}/{max_403_consecutive}). "
                             f"Refreshing session... [Total attempts: {metrics['total_attempts']}]")
                
                # Implement improved exponential backoff before refresh
                base_backoff = min(2 ** consecutive_403_count, 16)  # 2, 4, 8, 16 seconds
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = base_backoff + jitter
                metrics["total_delay_time"] += backoff_delay
                logger.debug(f"Waiting {backoff_delay:.1f}s before session refresh (base: {base_backoff}s)...")
                await asyncio.sleep(backoff_delay)
                
                refresh_success = await self._refresh_csrf_stealth()
                if refresh_success:
                    metrics["successful_403_recoveries"] += 1
                    logger.info(f"✓ Successfully recovered from 403 (recovery #{metrics['successful_403_recoveries']})")
                    # Extra wait after refresh to ensure session is ready
                    await asyncio.sleep(2)
                else:
                    logger.error("Failed to refresh CSRF after 403 - session may be blocked")
                    metrics["failed_checkouts"] += 1
                continue

            consecutive_403_count = 0
            result = await self.http.safe_json(resp, "bulk checkout")
            
            if result and result.get("status") == "succeeded":
                for c in remaining:
                    self.amount_saved_c += Decimal(str(c.price or 0))
                    self.successfully_enrolled_c += 1
                    if self.enrolled_courses is not None:
                        self.enrolled_courses[c.slug] = datetime.now(UTC).isoformat()
                    outcomes[c] = "enrolled"
                
                elapsed = asyncio.get_event_loop().time() - metrics["start_time"]
                logger.info(f"✓ Bulk checkout succeeded for {len(remaining)} courses "
                           f"[Attempts: {metrics['total_attempts']}, Time: {elapsed:.1f}s, "
                           f"403 Recoveries: {metrics['successful_403_recoveries']}]")
                break
            
            msg = result.get("message", "") if result else ""
            developer_message = (result or {}).get("developer_message", "")
            if "item_already_subscribed" in str(developer_message):
                quoted = re.search(r'"([^"]+)"', msg)
                error_title = quoted.group(1) if quoted else ""
                
                offender = None
                if error_title:
                    best_score, best_course = 0.0, None
                    for c in remaining:
                        score = self._title_overlap(c.title, error_title)
                        if score > best_score:
                            best_score, best_course = score, c
                    if best_score >= 0.4:
                        offender = best_course
                
                if offender:
                    logger.info(f"Course {offender.title} already enrolled. Removing from batch...")
                    remaining.remove(offender)
                    self.already_enrolled_c += 1
                    outcomes[offender] = "already_enrolled"
                    continue
                
                logger.info(f"Conflict detected but couldn't identify specific course. Falling back to single enrollments...")
                for c in remaining:
                    success = await self.checkout_single(c)
                    outcomes[c] = "enrolled" if success else "failed"
                break

            wait = self._throttle_wait(result or {})
            if wait:
                logger.info(f"Throttled. Waiting {wait} seconds before retry...")
                await asyncio.sleep(wait)
                continue
            
            logger.warning(f"Bulk checkout failed (attempt {attempt + 1}). Response: {result}")
            break
        
        # Log final metrics
        elapsed = asyncio.get_event_loop().time() - metrics["start_time"]
        success_rate = (len([o for o in outcomes.values() if o == "enrolled"]) / len(courses) * 100) if courses else 0
        
        logger.info(f"📊 Bulk Checkout Metrics: "
                   f"Attempts={metrics['total_attempts']}, "
                   f"403_Recoveries={metrics['successful_403_recoveries']}, "
                   f"Session_Blocks={metrics['session_blocks']}, "
                   f"Total_Delay={metrics['total_delay_time']:.1f}s, "
                   f"Success_Rate={success_rate:.1f}%, "
                   f"Duration={elapsed:.1f}s")
        
        return outcomes
