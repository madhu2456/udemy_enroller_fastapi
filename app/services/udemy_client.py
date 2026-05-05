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
        # Persistent CloudScraper session for enrollment (matches DUCE)
        self._init_cloudscraper()

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

        # Deployment-aware rate limiting
        from config.settings import get_settings

        self._is_server = get_settings().DEPLOYMENT_ENV == "server"

        # Circuit breaker — much more aggressive on server to avoid bans
        if self._is_server:
            # Server: detect blocks after just 2 consecutive 403s
            self._global_403_circuit_threshold = 2
            self._account_block_cooldown_seconds = 600  # 10 min base
        else:
            # Local: more lenient
            self._global_403_circuit_threshold = 4
            self._account_block_cooldown_seconds = 300  # 5 min base

        self._global_403_count = 0
        self._account_block_active = False
        self._account_block_cooldown_until = None

    def _init_cloudscraper(self):
        """Create a persistent CloudScraper session for enrollment (DUCE-style)."""
        try:
            import cloudscraper
            self.cs = cloudscraper.create_scraper()
            logger.debug("CloudScraper session initialized")
        except ImportError:
            self.cs = None
            logger.warning("cloudscraper not installed; enrollment may fail on Cloudflare")

    def _sync_cs_cookies(self):
        """Sync cookie_dict into the CloudScraper session."""
        if self.cs is None:
            return
        self.cs.cookies.clear()
        for k, v in self.cookie_dict.items():
            self.cs.cookies.set(k, v, domain="www.udemy.com")

    async def _cs_get(self, url: str, **kwargs) -> Optional[object]:
        """Async wrapper for CloudScraper GET."""
        if self.cs is None:
            return None
        self._sync_cs_cookies()
        try:
            return await asyncio.to_thread(self.cs.get, url, **kwargs)
        except Exception as e:
            logger.warning(f"  CloudScraper GET failed: {type(e).__name__}: {e}")
            return None

    async def _cs_post(self, url: str, **kwargs) -> Optional[object]:
        """Async wrapper for CloudScraper POST."""
        if self.cs is None:
            return None
        self._sync_cs_cookies()
        try:
            return await asyncio.to_thread(self.cs.post, url, **kwargs)
        except Exception as e:
            logger.warning(f"  CloudScraper POST failed: {type(e).__name__}: {e}")
            return None

    async def _course_fetch_throttle(self):
        """Global jitter + adaptive backoff.

        Server deployments use much longer base delays to avoid Udemy rate limits.
        """
        async with self._course_fetch_lock:
            if self._is_server:
                # Server: 6-15s base + adaptive backoff (datacenter IP needs care)
                base = random.uniform(6.0, 15.0)
            else:
                # Local: 3-8s base + adaptive backoff (residential IP, faster is fine)
                base = random.uniform(3.0, 8.0)
            extra = self._course_fetch_backoff_s
            delay = base + extra
            if extra >= 10.0 or (self._is_server and delay >= 15.0):
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
        """Activate circuit breaker with progressive cooldown.

        Server deployments use longer, more aggressive cooldowns to protect the account.
        """
        self._account_block_active = True
        block_count = self.session_recovery_state.get("block_count", 0) + 1
        self.session_recovery_state["block_count"] = block_count

        if self._is_server:
            # Server: aggressive multipliers (10min -> 20min -> 40min -> 60min)
            if block_count == 1:
                multiplier = 1
            elif block_count == 2:
                multiplier = 2
            elif block_count == 3:
                multiplier = 4
            else:
                multiplier = 6
        else:
            # Local: standard multipliers (5min -> 10min -> 20min -> 30min)
            if block_count == 2:
                multiplier = 2
            elif block_count == 3:
                multiplier = 4
            elif block_count >= 4:
                multiplier = 6
            else:
                multiplier = 1

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

            # Try CloudScraper + Mobile headers with 403 retry + header rotation
            resp = await self.http.get(
                constants.UDEMY_CONTEXT_URL,
                cookies=self.cookie_dict,
                headers=headers,
                req_type="mobile",
                use_cloudscraper=True,
                log_failures=False,
                retry_403=True,
                attempts=3,
            )

            if not resp or resp.status_code == 403:
                resp = await self.http.get(
                    constants.UDEMY_CONTEXT_URL,
                    cookies=self.cookie_dict,
                    headers=headers,
                    req_type="mobile",
                    log_failures=False,
                    retry_403=True,
                    attempts=3,
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
            course.is_valid = False
            course.error = "Account temporarily blocked"
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
            # Update URL if redirected (important for tracking links like trk.udemy.com)
            final_url = str(resp.url)
            if final_url != course.url:
                logger.info(f"    Redirected: {course.url} -> {final_url}")
                course.url = final_url
                course.extract_coupon_code()

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

        purchase = r.get("purchase") or r.get("cacheable_purchase")
        purchase_data = purchase.get("data", {}) if purchase else {}
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
        # Prefer ISO currency code over symbol; Udemy checkout requires valid ISO codes.
        currency = pricing_result.get("price", {}).get("currency") or pricing_result.get("price", {}).get("currency_symbol") or ""
        course.currency = currency

        logger.info(
            f"[CHECK_COURSE PRICE] {course.title} | list_price={lp} | final_price={final_price} | "
            f"is_free={is_free_result} | currency={currency} | coupon={course.coupon_code or 'NONE'}"
        )

        redeem_data = r.get("redeem_coupon") or r.get("cacheable_redeem_coupon")
        if course.coupon_code and redeem_data:
            attempts = redeem_data.get("discount_attempts", [])
            logger.info(
                f"[CHECK_COURSE COUPON] {course.title} | attempts={attempts}"
            )
            if attempts:
                attempt_status = attempts[0].get("status", "failed")
                # Prefer discount_percent == 100 (matches old working code)
                discount = pricing_result.get("discount_percent") or 0
                is_100_percent = discount == 100
                if attempt_status in ("applied", "unused") and (is_100_percent or is_free_result):
                    course.is_coupon_valid = True
                    logger.info(f"  Coupon applied successfully (Free): {course.title} | discount={discount}%")
                else:
                    course.is_coupon_valid = False
                    details = attempts[0].get("details")
                    if attempt_status not in ("applied", "unused"):
                        msg = f"{attempt_status}: {details}" if details else attempt_status
                    elif not is_100_percent:
                        msg = f"Coupon only {discount}% off (not 100%)"
                    else:
                        msg = "Coupon not fully free"
                    course.error = msg
                    logger.warning(f"  Coupon invalid for {course.title}: {msg}")
            else:
                course.is_coupon_valid = False
                course.error = "No discount attempts returned"
                logger.warning(f"  Coupon invalid for {course.title}: {course.error}")
        elif is_free_result:
            # Course is free without coupon
            course.is_coupon_valid = True
            course.is_free = True
            logger.info(f"  Course is free (no coupon needed): {course.title}")
        else:
            course.is_coupon_valid = False
            course.error = f"Course is not free (Price: {currency}{final_price})"
            logger.warning(f"  {course.error} for {course.title}")

    async def is_already_enrolled(
        self, course: Course, known_slugs: Optional[Set[str]] = None
    ) -> bool:
        if known_slugs and course.slug in known_slugs:
            return True
        return (
            self.enrolled_courses is not None and course.slug in self.enrolled_courses
        )

    async def check_already_enrolled_live(self, course: Course) -> bool:
        """Live API check: is the user already enrolled in this specific course?
        Returns True if already enrolled, False if not or unable to determine.
        """
        if not course.course_id:
            return False

        url = (
            f"{constants.UDEMY_API_BASE}/users/me/subscribed-courses/"
            f"{course.course_id}/?fields%5Bcourse%5D=%40default%2C"
            f"buyable_object_type%2Cprimary_subcategory%2Cis_private"
        )
        headers = {}
        if self.cookie_dict.get("access_token"):
            headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

        try:
            resp = await self.http.get(
                url,
                cookies=self.cookie_dict,
                headers=headers,
                req_type="mobile",
                use_cloudscraper=True,
                raise_for_status=False,
            )
            if resp:
                self._course_fetch_report(resp.status_code)

            if resp and resp.status_code == 200:
                logger.debug(
                    f"  Live check: Already enrolled in {course.title}"
                )
                return True
            elif resp and resp.status_code == 404:
                logger.debug(
                    f"  Live check: Not enrolled in {course.title}"
                )
                return False
            else:
                status = resp.status_code if resp else "No Response"
                logger.debug(
                    f"  Live check: Unclear result for {course.title} (status {status})"
                )
                return False
        except Exception as e:
            logger.debug(
                f"  Live check: Error checking enrollment for {course.title}: {e}"
            )
            return False

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

    async def _du_checkout(self, course: Course):
        """DUCE-style single course checkout using persistent CloudScraper session."""
        if self.cs is None:
            logger.error(f"[DU_CHECKOUT] No CloudScraper session for {course.title}")
            course.status = False
            return

        # Log course state at checkout time
        logger.info(
            f"[DU_CHECKOUT STATE] {course.title} | ID={course.course_id} | "
            f"coupon={course.coupon_code or 'NONE'} | price={course.price} | "
            f"list_price={course.list_price} | is_free={course.is_free} | "
            f"is_coupon_valid={course.is_coupon_valid}"
        )

        # Step 1: Preflight GET to checkout page to warm up the session
        checkout_page_url = "https://www.udemy.com/payment/checkout/"
        await self._cs_get(checkout_page_url, timeout=25)

        # Step 2: GET the course landing page to set checkout context cookies
        course_page_url = f"https://www.udemy.com/course/{course.slug}/"
        await self._cs_get(course_page_url, timeout=25)

        # Step 3: Build payload.
        # For coupon courses: use list_price so Udemy can verify the discount.
        # For free courses (no coupon): use amount=0 — list_price without a coupon
        # causes an immediate price_mismatch_error.
        checkout_currency = (course.currency or self.currency or "USD").upper()
        has_coupon = bool(course.coupon_code)
        base_amount = float(course.list_price) if has_coupon and course.list_price is not None else 0.0

        def _build_payload(amount: float):
            return {
                "checkout_environment": "Marketplace",
                "checkout_event": "Submit",
                "payment_info": {
                    "method_id": "0",
                    "payment_method": "free-method",
                    "payment_vendor": "Free",
                },
                "shopping_info": {
                    "items": [
                        {
                            "buyable": {"id": str(course.course_id), "type": "course"},
                            "discountInfo": {"code": course.coupon_code or ""},
                            "price": {
                                "amount": amount,
                                "currency": checkout_currency,
                            },
                        }
                    ],
                    "is_cart": True,
                },
            }

        # Simplified headers matching the old working Playwright/HTTPX fallback style.
        # Avoid mobile-app emulation headers that can confuse Udemy with CloudScraper.
        csrf_token = self.cookie_dict.get("csrftoken", "") or self.cookie_dict.get("csrf_token", "")
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.udemy.com/payment/checkout/",
            "X-CSRF-Token": csrf_token,
        }
        if self.cookie_dict.get("access_token"):
            headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

        max_attempts = 5
        use_zero_next = False
        for attempt in range(max_attempts):
            logger.info(f"[DU_CHECKOUT] Attempt {attempt + 1}/{max_attempts} for {course.title}")

            # On retry, refresh checkout page and apply backoff
            if attempt > 0:
                await self._cs_get(checkout_page_url, timeout=25)
                await asyncio.sleep(min(2 + attempt, 8))

            # Determine amount: free courses start at 0; coupon courses start at list_price
            # and fall back to 0 if Udemy reports price_mismatch.
            if use_zero_next or (not has_coupon and attempt == 0):
                amount = 0.0
            else:
                amount = base_amount

            payload = _build_payload(amount)
            logger.info(f"[DU_CHECKOUT PAYLOAD] {payload}")

            r = await self._cs_post(
                "https://www.udemy.com/payment/checkout-submit/",
                json=payload,
                headers=headers,
                timeout=25,
            )

            if r is None:
                logger.warning(f"[DU_CHECKOUT] No response (attempt {attempt + 1}) for {course.title}")
                continue

            logger.info(f"[DU_CHECKOUT] status={r.status_code} (attempt {attempt + 1}) for {course.title}")

            if r.headers.get("retry-after"):
                logger.error(f"[DU_CHECKOUT] retry-after header detected for {course.title}")
                course.status = False
                return

            if r.status_code == 504:
                logger.info(f"[DU_CHECKOUT] 504 treated as success for {course.title}")
                course.status = True
                return

            try:
                result = r.json()
            except Exception as e:
                logger.warning(f"[DU_CHECKOUT] JSON parse error: {e} | text={r.text[:200]}")
                continue

            if result.get("status") == "succeeded":
                logger.info(f"[DU_CHECKOUT] SUCCESS for {course.title}")
                course.status = True
                return

            # Handle already subscribed
            msg = str(result.get("message", ""))
            dev_msg = str(result.get("developer_message", ""))
            if "already subscribed" in msg.lower() or "already_enrolled" in dev_msg.lower():
                logger.info(f"[DU_CHECKOUT] Already enrolled: {course.title}")
                course.status = True
                return

            # Detect price mismatch so we can fall back to amount=0 on next iteration
            if "price_mismatch" in dev_msg.lower() and amount != 0.0:
                logger.warning(f"[DU_CHECKOUT] Price mismatch on attempt {attempt + 1}, will fallback to 0 for {course.title}")
                use_zero_next = True
                continue

            logger.warning(f"[DU_CHECKOUT] Failed: {result} for {course.title}")

        course.status = False

    async def free_checkout(self, course: Course):
        """Free course checkout: GET subscribe URL then verify enrollment via API."""
        logger.info(f"[FREE_CHECKOUT] {course.title} | ID={course.course_id}")

        # Step 1: GET the subscribe URL (old working Technatic logic)
        sub_url = f"{constants.UDEMY_COURSE_SUBSCRIBE_URL}?courseId={course.course_id}"
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Referer": course.url or f"{constants.UDEMY_BASE_URL}/course/{course.slug}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        r1 = await self.http.get(
            sub_url,
            cookies=self.cookie_dict,
            headers=headers,
            req_type="mobile",
            use_cloudscraper=True,
            log_failures=False,
        )
        if r1 is None:
            logger.warning(f"[FREE_CHECKOUT] Subscribe request returned no response for {course.title}")
        else:
            logger.info(f"[FREE_CHECKOUT] Subscribe status={r1.status_code} for {course.title}")
            if r1.status_code not in (200, 302):
                logger.warning(f"[FREE_CHECKOUT] Subscribe body snippet: {r1.text[:300]}")

        # Step 2: Verify enrollment via API
        verify_url = (
            f"{constants.UDEMY_API_BASE}/users/me/subscribed-courses/"
            f"{course.course_id}/?fields%5Bcourse%5D=%40default%2C"
            f"buyable_object_type%2Cprimary_subcategory%2Cis_private"
        )
        r2 = await self.http.get(
            verify_url,
            cookies=self.cookie_dict,
            headers=headers,
            req_type="mobile",
            use_cloudscraper=True,
            log_failures=False,
        )

        if r2 is None:
            logger.warning(f"[FREE_CHECKOUT] Verify request returned no response for {course.title}")
            course.status = False
            return

        logger.info(f"[FREE_CHECKOUT] Verify status={r2.status_code} for {course.title}")

        if r2.headers.get("retry-after"):
            logger.error(f"[FREE_CHECKOUT] retry-after header for {course.title}")
            course.status = False
            return

        if r2.status_code == 503:
            logger.info(f"[FREE_CHECKOUT] 503 treated as success for {course.title}")
            course.status = True
            return

        data = await self.http.safe_json(r2, context="free_checkout_verify")
        if data is None:
            logger.warning(f"[FREE_CHECKOUT] Could not parse verify JSON for {course.title}")
            course.status = False
            return

        # Log the full verify response so we can diagnose why _class is missing
        logger.info(f"[FREE_CHECKOUT] Verify JSON for {course.title}: {data}")

        course.status = data.get("_class") == "course"
        if course.status:
            logger.info(f"[FREE_CHECKOUT] SUCCESS for {course.title}")
        else:
            logger.warning(
                f"[FREE_CHECKOUT] FAILED for {course.title} | _class={data.get('_class')} | "
                f"status={r2.status_code}"
            )

    async def checkout_single(self, course: Course) -> bool:
        """DUCE-style single course enrollment."""
        logger.info(f"[CHECKOUT_SINGLE] {course.title} | free={course.is_free} | coupon={course.coupon_code or 'NONE'}")

        if course.is_free and not course.coupon_code:
            # Try subscribe endpoint first (fast path for truly free courses)
            await self.free_checkout(course)
            # Fallback: use regular checkout pipeline with amount=0
            # (matches old working code behavior)
            if not course.status:
                logger.warning(f"[CHECKOUT_SINGLE] Free-checkout failed, falling back to du-checkout for {course.title}")
                await self._du_checkout(course)
        else:
            await self._du_checkout(course)

        if course.status:
            logger.info(f"[CHECKOUT_SINGLE] SUCCESS for {course.title}")
        else:
            logger.warning(f"[CHECKOUT_SINGLE] FAILED for {course.title}")
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
