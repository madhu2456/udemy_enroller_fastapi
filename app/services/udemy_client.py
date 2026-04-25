"""Udemy API client for authentication and course enrollment - Technatic-style (No Playwright)."""

import re
import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional, Dict, Set

from bs4 import BeautifulSoup as bs
from loguru import logger

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.core import constants

# Known false-positive IDs from Udemy
BLACKLIST_IDS = {"562413829"}


class LoginException(Exception):
    """Raised when Udemy login fails."""

    pass


class UdemyClient:
    """Handles asynchronous authentication and enrollment using Technatic-style emulation."""

    def __init__(self, proxy: Optional[str] = None):
        logger.warning("UdemyClient v2.1 (Technatic logic active)")
        self.http = AsyncHTTPClient(proxy=proxy)

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

        # Session recovery tracking
        self.session_recovery_state = {
            "consecutive_403_errors": 0,
            "last_error_time": None,
            "block_count": 0,
        }

        self._course_fetch_lock = asyncio.Lock()
        self._course_fetch_backoff_s = 0.0
        self._course_fetch_consecutive_403s = 0

        # Circuit breaker
        self._global_403_circuit_threshold = 4
        self._global_403_count = 0
        self._account_block_active = False
        self._account_block_cooldown_until = None
        self._account_block_cooldown_seconds = 300

    async def _course_fetch_throttle(self):
        """Global jitter + adaptive backoff."""
        async with self._course_fetch_lock:
            base = random.uniform(3.0, 8.0)
            extra = self._course_fetch_backoff_s
            delay = base + extra
            if extra >= 10.0:
                logger.info(f"  Throttle: sleeping {delay:.1f}s")
            await asyncio.sleep(delay)

    def _course_fetch_report(self, status: int):
        """Update adaptive backoff."""
        if 200 <= status < 300:
            self._course_fetch_consecutive_403s = 0
            self._course_fetch_backoff_s = 0.0
        elif status == 403:
            self._course_fetch_consecutive_403s += 1
            self._global_403_count += 1
            n = self._course_fetch_consecutive_403s
            self._course_fetch_backoff_s = min(60.0, 2.0 ** max(0, n - 1))
            if (
                self._global_403_count >= self._global_403_circuit_threshold
                and not self._account_block_active
            ):
                self._activate_account_block()

    def _activate_account_block(self):
        """Activate circuit breaker with progressive cooldown."""
        self._account_block_active = True
        block_count = self.session_recovery_state.get("block_count", 0) + 1
        self.session_recovery_state["block_count"] = block_count

        multiplier = 1
        if block_count == 2:
            multiplier = 2
        elif block_count == 3:
            multiplier = 4
        elif block_count >= 4:
            multiplier = 6

        cooldown_seconds = self._account_block_cooldown_seconds * multiplier
        self._account_block_cooldown_until = datetime.now(UTC) + __import__(
            "datetime"
        ).timedelta(seconds=cooldown_seconds)

        logger.error(
            f"⚠ ACCOUNT BLOCK DETECTED (#{block_count}). Pausing for {cooldown_seconds}s."
        )

    def is_account_blocked(self) -> bool:
        """Check if account-level circuit breaker is active."""
        if not self._account_block_active:
            return False
        if self._account_block_cooldown_until is None:
            return False
        if datetime.now(UTC) >= self._account_block_cooldown_until:
            logger.info("✓ Account block cooldown expired.")
            self._account_block_active = False
            self._account_block_cooldown_until = None
            self._global_403_count = 0
            self._course_fetch_consecutive_403s = 0
            return False
        return True

    def get_account_block_wait_seconds(self) -> float:
        if not self.is_account_blocked() or self._account_block_cooldown_until is None:
            return 0.0
        return max(
            0.0,
            (self._account_block_cooldown_until - datetime.now(UTC)).total_seconds(),
        )

    def set_proxy(self, proxy: Optional[str]):
        """Update proxy for the underlying HTTP client."""
        self.http.set_proxy(proxy)

    async def _extract_csrf_from_html(self, html: str) -> Optional[str]:
        if not html:
            return None
        patterns = [
            r'<meta[^>]*name=["\']csrftoken["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta[^>]*name=["\']csrf_token["\'][^>]*content=["\']([^"\']+)["\']',
            r'["\']?csrf["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']',
            r'["\']?X-CSRF-?Token["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']',
            r'<input[^>]*name=["\']csrf(?:token)?["\'][^>]*value=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    async def manual_login(self, email: str, password: str):
        """Technatic-style login using CloudScraper and Mobile Emulation."""
        logger.info(f"Attempting login for {email} (Technatic-Style)")
        try:
            # 1. Fetch login page via CloudScraper
            resp = await self.http.get(
                constants.UDEMY_SIGNUP_POPUP_URL,
                use_cloudscraper=True,
                req_type="document",
                log_failures=False,
            )

            if not resp or resp.status_code != 200:
                # 2. Fallback to Standard HTTPX with Mobile headers
                resp = await self.http.get(
                    constants.UDEMY_SIGNUP_POPUP_URL,
                    req_type="mobile",
                    log_failures=True,
                )

            if not resp:
                raise LoginException("Could not connect to Udemy.")

            # Extract CSRF and update cookies
            csrf_token = resp.cookies.get(
                "csrftoken"
            ) or await self._extract_csrf_from_html(resp.text)
            self.cookie_dict.update(dict(resp.cookies))

            if not csrf_token:
                raise LoginException("CSRF token missing. Login restricted.")

            data = {
                "csrfmiddlewaretoken": csrf_token,
                "locale": "en_US",
                "email": email,
                "password": password,
            }

            # 3. Submit Login via CloudScraper (Technatic pattern)
            logger.info("  Submitting login via CloudScraper...")
            resp = await self.http.post(
                constants.UDEMY_LOGIN_POPUP_URL,
                data=data,
                cookies=self.cookie_dict,
                req_type="mobile",
                use_cloudscraper=True,
                log_failures=False,
            )

            # 4. Fallback POST
            if not resp or resp.status_code == 403:
                logger.warning("  CloudScraper blocked. Trying Mobile Emulation...")
                resp = await self.http.post(
                    constants.UDEMY_LOGIN_POPUP_URL,
                    data=data,
                    cookies=self.cookie_dict,
                    req_type="mobile",
                )

            if resp and (
                "returnUrl" in resp.text or "dj_session_id" in str(resp.cookies)
            ):
                self.cookie_dict.update(dict(resp.cookies))
                self.cookie_dict["csrf_token"] = csrf_token
                self.is_authenticated = True
                logger.info("  Login successful!")
            else:
                error_data = await self.http.safe_json(resp, "login")
                msg = (
                    error_data.get("error", {})
                    .get("data", {})
                    .get("formErrors", [["Unknown error"]])[0][0]
                    if error_data
                    else "Access Denied"
                )
                raise LoginException(msg)

        except Exception as e:
            if isinstance(e, LoginException):
                raise
            logger.exception("Login failed")
            raise LoginException(f"Login failed: {str(e)}")

    def cookie_login(self, access_token: str, client_id: str, csrf_token: str):
        self.cookie_dict.update(
            {
                "client_id": client_id,
                "access_token": access_token,
                "csrf_token": csrf_token,
                "csrftoken": csrf_token,  # Sync both names
            }
        )
        self.http.client.cookies.update(self.cookie_dict)

    async def get_session_info(self):
        """Verify session via CloudScraper and Mobile Emulation."""
        logger.info("Getting session info")
        try:
            headers = {"Referer": f"{constants.UDEMY_BASE_URL}/"}
            # Use Bearer token if available, otherwise rely on cookies
            token = self.cookie_dict.get("access_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # Try CloudScraper + Mobile headers
            resp = await self.http.get(
                constants.UDEMY_CONTEXT_URL,
                cookies=self.cookie_dict,
                headers=headers,
                req_type="mobile",
                use_cloudscraper=True,
                log_failures=False,
            )

            if not resp or resp.status_code == 403:
                resp = await self.http.get(
                    constants.UDEMY_CONTEXT_URL,
                    cookies=self.cookie_dict,
                    headers=headers,
                    req_type="mobile",
                    log_failures=False,
                )

            ctx = await self.http.safe_json(resp, "session")
            if not ctx or not ctx.get("header", {}).get("isLoggedIn"):
                # If we have a response but not logged in, log a snippet for diagnosis
                if resp:
                    logger.debug(
                        f"Session check failed. Status: {resp.status_code}, Body snippet: {resp.text[:200]}"
                    )
                raise LoginException("Session invalid.")

            self.display_name = ctx["header"]["user"]["display_name"]
            self.is_authenticated = True
            logger.info(f"Authenticated as {self.display_name}")

        except Exception as e:
            if not isinstance(e, LoginException):
                logger.exception("Failed to get session info")
            raise LoginException(f"Session failed: {str(e)}")

    async def get_enrolled_courses(self, known_slugs: set = None):
        """Fetch enrolled courses using Mobile API headers."""
        logger.info("Fetching enrolled courses...")
        base_url = f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"
        self.enrolled_courses = {}

        common_headers = {}
        if self.cookie_dict.get("access_token"):
            common_headers["Authorization"] = (
                f"Bearer {self.cookie_dict['access_token']}"
            )

        resp = await self.http.get(
            base_url,
            cookies=self.cookie_dict,
            headers=common_headers,
            req_type="mobile",
        )
        data = await self.http.safe_json(resp, "courses")
        if not data:
            return

        for c in data.get("results", []):
            try:
                # URL format: https://www.udemy.com/course/slug/
                parts = c["url"].strip("/").split("/")
                if "course" in parts:
                    idx = parts.index("course")
                    if len(parts) > idx + 1:
                        slug = parts[idx + 1]
                        self.enrolled_courses[slug] = c.get("enrollment_time", "")
            except Exception:
                continue
        logger.info(
            f"Enrolled courses check complete: {len(self.enrolled_courses)} tracked."
        )

    def _extract_course_id(self, html: str) -> Optional[str]:
        soup = bs(html, "lxml")
        body = soup.find("body")
        if body:
            cid = body.get("data-clp-course-id") or body.get("data-course-id")
            if cid and str(cid) not in BLACKLIST_IDS:
                return str(cid)

        # Meta/Script regex fallbacks
        matches = re.findall(r'["\']?course_?id["\']?\s*[:=]\s*(\d+)', html, re.I)
        for cid in matches:
            if 4 < len(cid) < 12 and cid not in BLACKLIST_IDS:
                return cid
        return None

    async def get_course_id(self, course: Course):
        """Slug resolution using Slug API and CloudScraper."""
        if course.course_id:
            return
        if self.is_account_blocked():
            return

        await self._course_fetch_throttle()

        # 1. Anonymous Slug API (Most efficient)
        if course.slug:
            api_url = f"{constants.UDEMY_API_BASE}/courses/{course.slug}/?fields[course]=id,title,url"
            try:
                resp = await self.http.get(
                    api_url, req_type="mobile", randomize_headers=True
                )
                data = await self.http.safe_json(resp)
                if data and data.get("id"):
                    course.course_id = str(data["id"])
                    self._course_fetch_report(200)
                    return
            except Exception:
                pass

        # 2. CloudScraper HTML Fetch
        logger.info(f"  Fetching {course.title} via CloudScraper...")
        resp = await self.http.get(
            course.url, use_cloudscraper=True, req_type="document"
        )
        if resp and resp.status_code == 200:
            course.course_id = self._extract_course_id(resp.text)
            if course.course_id:
                self._course_fetch_report(200)
                return
            else:
                course.is_valid = False
                course.error = "Course ID extraction failed from HTML"
                logger.warning(f"  {course.error} for {course.title}")
        elif resp:
            course.is_valid = False
            course.error = f"HTML fetch failed (Status: {resp.status_code})"
            logger.warning(f"  {course.error} for {course.title} (URL: {course.url})")
            if resp.status_code == 403:
                self._course_fetch_report(403)
        else:
            course.is_valid = False
            course.error = "No response from Udemy"
            logger.warning(f"  {course.error} for {course.title} (URL: {course.url})")

    async def check_course(self, course: Course):
        """Fetch price/coupon info via Mobile API."""
        url = f"{constants.UDEMY_COURSE_LANDING_COMPONENTS_URL}{course.course_id}/me/?components=purchase,redeem_coupon,cacheable_purchase,cacheable_redeem_coupon&couponCode={course.coupon_code or ''}"
        headers = {
            "Referer": course.url or f"{constants.UDEMY_BASE_URL}/course/{course.slug}/"
        }
        if self.cookie_dict.get("access_token"):
            headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

        resp = await self.http.get(
            url,
            cookies=self.cookie_dict,
            headers=headers,
            req_type="mobile",
            use_cloudscraper=True,
        )
        r = await self.http.safe_json(resp, context="check_course")
        if not r:
            status = resp.status_code if resp else "No Response"
            course.is_coupon_valid = False
            course.error = f"Check course failed (Status: {status})"
            logger.warning(f"  {course.error} for {course.title}")
            return

        purchase_data = r.get("purchase", {}).get("data", {})
        pricing_result = purchase_data.get("pricing_result", {})

        # Track list price for "amount saved" stats
        lp = purchase_data.get("list_price", {}).get("amount") or 0
        final_price = pricing_result.get("price", {}).get("amount") or 0
        course.price = Decimal(str(final_price))

        # If it becomes free, we save the list price
        # But we only add to total if enrollment actually succeeds (handled in enrollment_manager)
        course.list_price = Decimal(str(lp))

        # A course is free if final_price is 0 or it's explicitly marked as free
        is_free_result = pricing_result.get("is_free", False) or final_price == 0

        if course.coupon_code and "redeem_coupon" in r:
            attempts = r["redeem_coupon"].get("discount_attempts", [])
            if attempts and attempts[0].get("status") == "applied":
                if is_free_result:
                    course.is_coupon_valid = True
                    logger.info(f"  Coupon applied successfully (Free): {course.title}")
                else:
                    course.is_coupon_valid = False
                    course.error = f"Coupon applied but price is {final_price}"
                    logger.warning(
                        f"  Coupon applied but price mismatch: {course.title} (Price: {final_price})"
                    )
            else:
                course.is_coupon_valid = False
                msg = attempts[0].get("details") if attempts else "Invalid coupon"
                course.error = msg
                logger.warning(f"  Coupon invalid for {course.title}: {msg}")
        elif is_free_result:
            # Course is free without coupon
            course.is_coupon_valid = True
            logger.info(f"  Course is free (no coupon needed): {course.title}")
        else:
            course.is_coupon_valid = False
            course.error = f"Course is not free (Price: {final_price})"
            logger.warning(f"  {course.error} for {course.title}")

    async def is_already_enrolled(
        self, course: Course, known_slugs: Optional[Set[str]] = None
    ) -> bool:
        if known_slugs and course.slug in known_slugs:
            return True
        return (
            self.enrolled_courses is not None and course.slug in self.enrolled_courses
        )

    def is_course_excluded(self, course: Course, settings: dict):
        min_rating = settings.get("min_rating", 0)
        if course.rating and min_rating > 0 and course.rating < min_rating:
            course.is_excluded = True
            return

        allowed_langs = [lang.lower() for lang in settings.get("languages", []) if lang]
        if (
            allowed_langs
            and course.language
            and course.language.lower() not in allowed_langs
        ):
            course.is_excluded = True
            return

    async def free_checkout(self, course: Course):
        """Enroll via Technatic-style two-step verification."""
        # Step 1: Hit the subscribe URL
        sub_url = f"https://www.udemy.com/course/subscribe/?courseId={course.course_id}"
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Referer": course.url
            or f"{constants.UDEMY_BASE_URL}/course/{course.slug}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        # Technatic logic uses GET for subscribe
        await self.http.get(
            sub_url,
            cookies=self.cookie_dict,
            headers=headers,
            req_type="mobile",
            use_cloudscraper=True,
        )

        # Step 2: Verify enrollment via API
        verify_url = f"https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private"
        resp2 = await self.http.get(
            verify_url,
            cookies=self.cookie_dict,
            headers=headers,
            req_type="mobile",
            use_cloudscraper=True,
        )

        if resp2:
            if resp2.status_code == 503:
                # Technatic handles 503 as success for free checkout
                course.status = True
                return

            data = await self.http.safe_json(resp2, context="free_checkout_verify")
            if data and data.get("_class") == "course":
                course.status = True
                return

        status = resp2.status_code if resp2 else "No Response"
        logger.warning(
            f"  Free checkout verification failed for {course.title}. Status: {status}"
        )

    async def checkout_single(self, course: Course) -> bool:
        """Enroll in a single course (Technatic-style)."""
        await self.free_checkout(course)
        return course.status

    def get_session_health_report(self) -> dict:
        return {
            "consecutive_403_errors": self._course_fetch_consecutive_403s,
            "total_403_errors": self._global_403_count,
            "account_blocked": self._account_block_active,
            "csrf_refresh_failures": 0,  # Not applicable in pure emulation
            "cloudflare_challenges": 0,  # Not applicable in pure emulation
        }

    async def close(self):
        await self.http.close()
