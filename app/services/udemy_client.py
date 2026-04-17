"""Udemy API client for authentication and course enrollment - Asynchronous version."""

import json
import logging
import re
import asyncio
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


class LoginException(Exception):
    """Raised when Udemy login fails."""
    pass


class UdemyClient:
    """Handles asynchronous authentication and enrollment with the Udemy API."""

    def __init__(self, proxy: Optional[str] = None):
        self.http = AsyncHTTPClient(proxy=proxy)
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

    async def close(self):
        await self.http.close()

    def set_proxy(self, proxy: Optional[str]):
        """Update the proxy configuration."""
        if self.http.proxy != proxy:
            # Re-initialize the AsyncHTTPClient with new proxy
            old_headers = self.http.client.headers
            old_cookies = self.http.client.cookies
            asyncio.create_task(self.http.close())
            self.http = AsyncHTTPClient(proxy=proxy)
            self.http.client.headers.update(old_headers)
            self.http.client.cookies.update(old_cookies)

    async def manual_login(self, email: str, password: str):
        """Asynchronously login using email and password."""
        logger.info(f"Attempting manual login for {email}")
        try:
            r = await self.http.get(
                constants.UDEMY_SIGNUP_POPUP_URL,
                headers={"User-Agent": constants.DEFAULT_USER_AGENT},
                randomize_headers=False
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

            # POST for login
            self.http.client.cookies.update(r.cookies)
            self.http.client.headers.update({
                "Referer": constants.UDEMY_LOGIN_POPUP_URL,
                "Origin": constants.UDEMY_BASE_URL,
            })

            resp = await self.http.post(
                constants.UDEMY_LOGIN_POPUP_URL,
                data=data
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
            resp = await self.http.get(
                constants.UDEMY_CONTEXT_URL,
                cookies=self.cookie_dict,
                randomize_headers=False
            )
            ctx = await self.http.safe_json(resp, "session info")
            if not ctx or not ctx.get("header", {}).get("isLoggedIn"):
                raise LoginException("Login failed - session invalid.")

            self.display_name = ctx["header"]["user"]["display_name"]

            # Get currency
            cart_resp = await self.http.get(
                constants.UDEMY_CART_URL,
                cookies=self.cookie_dict,
                randomize_headers=False
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
        """Fetch all enrolled courses asynchronously. Stops early if known courses are found."""
        logger.info("Fetching enrolled courses")
        next_page = (
            f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"
        )
        courses = {}
        page_num = 0
        known_slugs = known_slugs or set()
        stop_fetching = False

        while next_page and page_num < 50 and not stop_fetching:
            page_num += 1
            resp = await self.http.get(next_page, cookies=self.cookie_dict)
            data = await self.http.safe_json(resp, f"enrolled courses page {page_num}")
            if not data:
                break

            results = data.get("results", [])
            if not results:
                break

            for course in results:
                try:
                    parts = course["url"].split("/")
                    slug = parts[3] if len(parts) > 3 and parts[2] == "draft" else parts[2]
                    courses[slug] = course.get("enrollment_time", "")
                    if slug in known_slugs:
                        # Reached courses we already know about. Stop fetching.
                        stop_fetching = True
                except (IndexError, KeyError):
                    continue

            next_page = data.get("next")

        self.enrolled_courses = courses
        # Merge with known_slugs so is_already_enrolled works for older courses
        for slug in known_slugs:
            if slug not in self.enrolled_courses:
                self.enrolled_courses[slug] = ""
        logger.info(f"Fetched {page_num} page(s) of enrolled courses.")

    async def get_course_id(self, course: Course, use_headless_fallback: bool = True):
        """Fetch course ID and metadata asynchronously with optional headless fallback."""
        if course.course_id:
            return
        url = re.sub(r"\W+$", "", unquote(course.url))
        resp = await self.http.get(url)
        
        # Check if we need to fall back to Playwright due to Cloudflare
        should_retry_headless = False
        if not resp:
            should_retry_headless = True
        else:
            soup = bs(resp.content, "lxml")
            title = soup.find("title")
            title_text = title.text.strip() if title else ""
            if "Access Denied" in title_text or "Just a moment" in title_text or "Attention Required" in title_text:
                should_retry_headless = True
        
        if should_retry_headless and use_headless_fallback:
            logger.info(f"Cloudflare detected for {course.title}, falling back to headless browser...")
            from app.services.playwright_service import PlaywrightService
            async with PlaywrightService() as pw:
                content = await pw.get_page_content(url)
                if content:
                    soup = bs(content, "lxml")
                    body = soup.find("body")
                    course_id = body.get("data-clp-course-id") if body else None
                    if course_id:
                        course.course_id = course_id
                        try:
                            dma = json.loads(body.get("data-module-args", "{}"))
                            course.set_metadata(dma)
                            return
                        except Exception:
                            pass

        if not resp:
            course.is_valid = False
            course.error = "Failed to fetch course page"
            return

        course.set_url(str(resp.url))
        soup = bs(resp.content, "lxml")
        body = soup.find("body")
        course_id = body.get("data-clp-course-id") if body else None
        
        if not course_id:
            course.is_valid = False
            course.error = "Course ID not found"
            if body:
                title = soup.find("title")
                title_text = title.text.strip() if title else "No title"
                logger.warning(f"Course ID not found for {course.title}. Page title: {title_text}")
            return

        course.course_id = course_id
        try:
            dma = json.loads(body.get("data-module-args", "{}"))
            course.set_metadata(dma)
        except Exception as e:
            logger.warning(f"Metadata parse error for {course.title}: {e}")

    async def check_course(self, course: Course):
        """Check coupon validity asynchronously."""
        if course.price is not None:
            return
        url = f"{constants.UDEMY_COURSE_LANDING_COMPONENTS_URL}{course.course_id}/me/?components=purchase"
        if course.coupon_code:
            url += f",redeem_coupon&couponCode={course.coupon_code}"

        resp = await self.http.get(url, cookies=self.cookie_dict)
        r = await self.http.safe_json(resp, "check course")
        if not r:
            return

        amount = r.get("purchase", {}).get("data", {}).get("list_price", {}).get("amount")
        course.price = Decimal(str(amount)) if amount is not None else None

        if course.coupon_code and "redeem_coupon" in r:
            discount = r["purchase"]["data"]["pricing_result"]["discount_percent"]
            status = r["redeem_coupon"]["discount_attempts"][0]["status"]
            course.is_coupon_valid = (discount == 100 and status == "applied")

    async def is_already_enrolled(self, course: Course) -> bool:
        if self.enrolled_courses is None:
            await self.get_enrolled_courses()
        return course.slug in self.enrolled_courses

    def is_course_excluded(self, course: Course, settings: dict):
        """Check if course should be excluded based on settings."""
        # DISABLED: User requested to never exclude any course.
        return

    async def free_checkout(self, course: Course):
        """Enroll in a free course asynchronously."""
        await self.http.get(f"{constants.UDEMY_COURSE_SUBSCRIBE_URL}?courseId={course.course_id}", cookies=self.cookie_dict)
        resp = await self.http.get(
            f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private",
            cookies=self.cookie_dict
        )
        if resp and resp.status_code == 200:
            data = await self.http.safe_json(resp, "free checkout check")
            course.status = data.get("_class") == "course" if data else False
        else:
            course.status = False

    async def checkout_single(self, course: Course) -> bool:
        """Asynchronously enroll in a single course with a coupon."""
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": constants.UDEMY_CHECKOUT_URL,
            "X-CSRF-Token": self.http.client.cookies.get("csrftoken", ""),
        }
        result = await self._checkout_one(course, headers)
        return result

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
        
        for attempt in range(3):
            resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=False)
            result = await self.http.safe_json(resp, "checkout one")
            
            if result and result.get("status") == "succeeded":
                self.amount_saved_c += Decimal(str(course.price or 0))
                self.successfully_enrolled_c += 1
                if self.enrolled_courses is not None:
                    self.enrolled_courses[course.slug] = datetime.now(UTC).isoformat()
                return True
            
            wait = self._throttle_wait(result or {})
            if wait:
                await asyncio.sleep(wait)
                continue
            break
        return False

    async def bulk_checkout(self, courses: List[Course]) -> Dict[Course, str]:
        """Asynchronously enroll in a batch of courses."""
        outcomes: Dict[Course, str] = {c: "failed" for c in courses}
        if not courses: return outcomes
        
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": constants.UDEMY_CHECKOUT_URL,
            "X-CSRF-Token": self.http.client.cookies.get("csrftoken", ""),
        }
        
        remaining = list(courses)
        for attempt in range(len(courses) + 2):
            if not remaining: break
            
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
            
            resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=False)
            result = await self.http.safe_json(resp, "bulk checkout")
            
            if result and result.get("status") == "succeeded":
                for c in remaining:
                    self.amount_saved_c += Decimal(str(c.price or 0))
                    self.successfully_enrolled_c += 1
                    if self.enrolled_courses is not None:
                        self.enrolled_courses[c.slug] = datetime.now(UTC).isoformat()
                    outcomes[c] = "enrolled"
                break
            
            # Handle "already enrolled" by finding the offender
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
                        if score > best_score: best_score, best_course = score, c
                    if best_score >= 0.4: offender = best_course
                
                if offender:
                    remaining.remove(offender)
                    self.already_enrolled_c += 1
                    outcomes[offender] = "already_enrolled"
                    continue
                
                # If we can't find it, fall back to single
                for c in remaining:
                    success = await self.checkout_single(c)
                    outcomes[c] = "enrolled" if success else "failed"
                break

            wait = self._throttle_wait(result or {})
            if wait:
                await asyncio.sleep(wait)
                continue
            break
        return outcomes
