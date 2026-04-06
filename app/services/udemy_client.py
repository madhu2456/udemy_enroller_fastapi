"""Udemy API client for authentication and course enrollment."""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote

import cloudscraper
import requests
from bs4 import BeautifulSoup as bs

from app.services.course import Course

logger = logging.getLogger(__name__)


class LoginException(Exception):
    """Raised when Udemy login fails."""
    pass


class UdemyClient:
    """Handles authentication and enrollment with the Udemy API."""

    def __init__(self):
        self.client = requests.session()
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "Referer": "https://www.udemy.com/",
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
        self.client.headers.update(headers)

        self.display_name: str = ""
        self.currency: str = "usd"
        self.cookie_dict: dict = {}
        self.enrolled_courses: dict = None  # loaded lazily at enrollment time

        # Enrollment counters
        self.successfully_enrolled_c = 0
        self.already_enrolled_c = 0
        self.expired_c = 0
        self.excluded_c = 0
        self.amount_saved_c = Decimal(0)

        self.course: Course = None
        self.is_authenticated = False

    def manual_login(self, email: str, password: str):
        """Login using email and password."""
        logger.info("Attempting manual login")
        s = requests.session()
        try:
            r = s.get(
                "https://www.udemy.com/join/signup-popup/?locale=en_US&response_type=html&next=https%3A%2F%2Fwww.udemy.com%2Flogout%2F",
                headers={"User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)"},
                timeout=30,
            )
        except requests.exceptions.ConnectionError as e:
            raise LoginException(
                "Could not connect to Udemy — check your internet connection and try again."
            ) from e
        except requests.exceptions.Timeout:
            raise LoginException(
                "Connection to Udemy timed out — check your internet connection and try again."
            )
        try:
            csrf_token = r.cookies["csrftoken"]
        except KeyError:
            raise LoginException("Could not retrieve CSRF token from Udemy")

        data = {
            "csrfmiddlewaretoken": csrf_token,
            "locale": "en_US",
            "email": email,
            "password": password,
        }
        s.cookies.update(r.cookies)
        s.headers.update({
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.udemy.com/join/login-popup/?passwordredirect=True&response_type=json",
            "Origin": "https://www.udemy.com",
            "DNT": "1",
            "Host": "www.udemy.com",
        })
        s = cloudscraper.create_scraper(sess=s)
        r = s.post(
            "https://www.udemy.com/join/login-popup/?passwordredirect=True&response_type=json",
            data=data,
            allow_redirects=False,
        )

        if "returnUrl" in r.text:
            self.cookie_dict = {
                "client_id": r.cookies["client_id"],
                "access_token": r.cookies["access_token"],
                "csrf_token": csrf_token,
            }
        else:
            try:
                login_error = r.json()["error"]["data"]["formErrors"][0]
            except (KeyError, IndexError):
                raise LoginException("Unknown login error")
            if login_error[0] == "Y":
                raise LoginException("Too many logins per hour, try later")
            elif login_error[0] == "T":
                raise LoginException("Email or password incorrect")
            else:
                raise LoginException(login_error)

    def cookie_login(self, access_token: str, client_id: str, csrf_token: str):
        """Login using cookies (from browser)."""
        self.cookie_dict = {
            "client_id": client_id,
            "access_token": access_token,
            "csrf_token": csrf_token,
        }

    def get_session_info(self):
        """Fetch session info and set up authenticated client."""
        logger.info("Getting session info")
        s = cloudscraper.CloudScraper()
        headers = {
            "User-Agent": "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "Referer": "https://www.udemy.com/",
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        # ── Step 1: verify login ───────────────────────
        try:
            ctx_resp = s.get(
                "https://www.udemy.com/api-2.0/contexts/me/?header=True",
                cookies=self.cookie_dict,
                headers=headers,
                timeout=30,
            )
        except requests.exceptions.ConnectionError as e:
            raise LoginException(
                "Could not connect to Udemy — check your internet connection and try again."
            ) from e
        except requests.exceptions.Timeout:
            raise LoginException(
                "Connection to Udemy timed out — check your internet connection and try again."
            )
        if not ctx_resp.text or not ctx_resp.text.strip():
            raise LoginException("Udemy returned an empty response during login verification")
        try:
            ctx = ctx_resp.json()
        except Exception:
            raise LoginException(
                f"Could not parse Udemy login response (HTTP {ctx_resp.status_code}). "
                "This may be a temporary rate-limit — please try again in a minute."
            )

        if not ctx.get("header", {}).get("isLoggedIn"):
            raise LoginException("Login failed — credentials were rejected by Udemy")

        self.display_name = ctx["header"]["user"]["display_name"]

        # ── Step 2: get currency ───────────────────────
        cart_resp = s.get(
            "https://www.udemy.com/api-2.0/shopping-carts/me/",
            headers=headers,
            cookies=self.cookie_dict,
            timeout=30,
        )
        self.currency = "usd"  # sensible default
        if cart_resp.text and cart_resp.text.strip():
            try:
                cart = cart_resp.json()
                self.currency = cart["user"]["credit"]["currency_code"]
            except Exception as e:
                logger.warning(f"Could not parse shopping-cart response, defaulting to USD: {e}")

        # ── Step 3: set up authenticated session ───────
        s = cloudscraper.CloudScraper()
        s.cookies.update(self.cookie_dict)
        s.headers.update(headers)
        s.keep_alive = False
        self.client = s
        self.is_authenticated = True

        # enrolled_courses loaded lazily on first enrollment run, not at login
        logger.info(f"Session info retrieved — logged in as {self.display_name} ({self.currency.upper()})")

    def get_enrolled_courses(self):
        """Fetch all enrolled courses."""
        logger.info("Getting enrolled courses")
        next_page = (
            "https://www.udemy.com/api-2.0/users/me/subscribed-courses/"
            "?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"
        )
        courses = {}
        page_num = 0
        max_pages = 50  # safety cap (~5000 courses)

        while next_page and page_num < max_pages:
            page_num += 1
            try:
                response = self.client.get(next_page, timeout=30)
            except Exception as e:
                logger.error(f"Network error fetching enrolled courses page {page_num}: {e}")
                break

            # Log non-200 status for debugging
            if response.status_code != 200:
                logger.error(
                    f"Enrolled courses page {page_num} returned HTTP {response.status_code}. "
                    f"Body: {response.text[:200]}"
                )
                break

            # Guard against empty or non-JSON response
            if not response.text or not response.text.strip():
                logger.error(f"Empty response on enrolled courses page {page_num}")
                break

            try:
                data = response.json()
            except Exception as e:
                logger.error(
                    f"JSON decode error on enrolled courses page {page_num}: {e}. "
                    f"Response text: {response.text[:300]}"
                )
                break

            for course in data.get("results", []):
                try:
                    parts = course["url"].split("/")
                    slug = parts[3] if len(parts) > 3 and parts[2] == "draft" else parts[2]
                    courses[slug] = course.get("enrollment_time", "")
                except (IndexError, KeyError) as e:
                    logger.warning(f"Could not parse enrolled course entry: {course} — {e}")

            next_page = data.get("next")

        self.enrolled_courses = courses
        logger.info(f"Found {len(courses)} enrolled courses across {page_num} page(s)")

    # ── Course validation ─────────────────────────────

    def get_course_id(self, course: Course):
        """Fetch course ID and metadata from Udemy."""
        if course.course_id:
            return
        url = re.sub(r"\W+$", "", unquote(course.url))
        r = None
        for _ in range(3):
            try:
                r = self.client.get(url)
                break
            except Exception as e:
                logger.error(f"Error fetching course ID: {e}")
                r = None

        if r is None:
            course.is_valid = False
            course.error = "Failed to fetch course page"
            return

        course.set_url(r.url)
        soup = bs(r.content, "lxml")
        course_id = soup.find("body").get("data-clp-course-id", "invalid")
        if course_id == "invalid":
            course.is_valid = False
            course.error = "Course ID not found on page"
            return

        course.course_id = course_id
        dma = json.loads(soup.find("body")["data-module-args"])
        course.set_metadata(dma)

    def check_course(self, course: Course):
        """Check coupon validity and price."""
        if course.price is not None:
            return
        url = f"https://www.udemy.com/api-2.0/course-landing-components/{course.course_id}/me/?components=purchase"
        if course.coupon_code:
            url += f",redeem_coupon&couponCode={course.coupon_code}"
        for _ in range(3):
            try:
                r = self.client.get(url).json()
                break
            except Exception:
                r = None
        if r is None:
            return

        amount = r.get("purchase", {}).get("data", {}).get("list_price", {}).get("amount")
        course.price = Decimal(str(amount)) if amount is not None else None

        if course.coupon_code and "redeem_coupon" in r:
            discount = r["purchase"]["data"]["pricing_result"]["discount_percent"]
            status = r["redeem_coupon"]["discount_attempts"][0]["status"]
            course.is_coupon_valid = discount == 100 and status == "applied"

    def is_already_enrolled(self, course: Course) -> bool:
        # Lazy-load enrolled courses on first check during an enrollment run
        if not hasattr(self, "enrolled_courses") or self.enrolled_courses is None:
            self.get_enrolled_courses()
        return course.slug in self.enrolled_courses

    def is_course_excluded(self, course: Course, settings: dict):
        """Check if course should be excluded based on settings."""
        categories = [k for k, v in settings.get("categories", {}).items() if v]
        languages = [k for k, v in settings.get("languages", {}).items() if v]
        min_rating = settings.get("min_rating", 0.0)
        instructor_exclude = settings.get("instructor_exclude", [])
        title_exclude = settings.get("title_exclude", [])
        threshold = settings.get("course_update_threshold_months", 24)

        # Check last update
        if course.last_update:
            try:
                last_update_date = datetime.strptime(course.last_update, "%Y-%m-%d")
                current_date = datetime.now()
                months_diff = (current_date.year - last_update_date.year) * 12 + (current_date.month - last_update_date.month)
                if months_diff >= threshold:
                    course.is_excluded = True
                    course.error = f"Not updated in {months_diff} months (last: {course.last_update}, threshold: {threshold})"
                    return
            except ValueError:
                pass

        # Check instructor
        for instructor in course.instructors:
            if instructor in instructor_exclude:
                course.is_excluded = True
                course.error = f"Instructor excluded: {instructor}"
                return

        # Check title keywords
        title_words = course.title.casefold().split()
        for word in title_words:
            if word.casefold() in [t.casefold() for t in title_exclude]:
                course.is_excluded = True
                course.error = f"Title keyword excluded: {word}"
                return

        # Check category
        if course.category and course.category not in categories:
            course.is_excluded = True
            course.error = f"Category not enabled: {course.category}"
            return

        # Check language
        if course.language and course.language not in languages:
            course.is_excluded = True
            course.error = f"Language not enabled: {course.language}"
            return

        # Check rating
        if course.rating is not None and course.rating < min_rating:
            course.is_excluded = True
            course.error = f"Rating too low: {course.rating} (min: {min_rating})"

    # ── Enrollment ────────────────────────────────────

    def free_checkout(self, course: Course):
        """Enroll in a free course."""
        self.client.get(f"https://www.udemy.com/course/subscribe/?courseId={course.course_id}")
        r = self.client.get(
            f"https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private"
        )
        if r.status_code == 503:
            course.status = True
            return
        try:
            r = r.json()
            course.status = r.get("_class") == "course"
        except Exception:
            course.status = False

    @staticmethod
    def _title_overlap(a: str, b: str) -> float:
        """Jaccard word-overlap score between two titles (0.0–1.0).
        Strips punctuation and year tokens so '...Hello' matches '...Hello 2026'.
        """
        def tokenize(s):
            s = re.sub(r'\b(20\d{2})\b', '', s)          # remove years like 2024, 2025, 2026
            s = re.sub(r'[^\w\s]', '', s.lower())         # remove punctuation
            return set(s.split()) - {'the', 'a', 'an', 'and', 'or', 'in', 'of', 'to', 'for'}
        ta, tb = tokenize(a), tokenize(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    @staticmethod
    def _throttle_wait(result: dict) -> int:
        """Return the number of seconds to wait if Udemy is throttling, else 0."""
        detail = result.get("detail", "")
        if "throttled" in str(detail).lower():
            match = re.search(r"(\d+)\s+second", str(detail), re.IGNORECASE)
            wait = int(match.group(1)) if match else 60
            logger.warning(f"Udemy rate-limit hit — waiting {wait}s before retrying")
            return wait
        return 0

    def _checkout_one(self, course: Course, headers: dict) -> bool:
        """Enroll in a single course with a coupon. Returns True on success."""
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
            try:
                r = self.client.post(
                    "https://www.udemy.com/payment/checkout-submit/",
                    json=payload, headers=headers,
                )
                result = {"status": "succeeded"} if r.status_code == 504 else r.json()
            except Exception as e:
                logger.error(f"Single checkout error for '{course.title}': {e}")
                time.sleep(3)
                continue

            if result.get("status") == "succeeded":
                self.enrolled_courses[course.slug] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                self.amount_saved_c += Decimal(str(course.price)) if course.price else Decimal(0)
                self.successfully_enrolled_c += 1
                logger.info(f"Single checkout succeeded: {course.title}")
                return True

            dev = result.get("developer_message", "")
            if "item_already_subscribed" in dev:
                logger.warning(f"Single checkout: already enrolled — {course.title}")
                self.enrolled_courses[course.slug] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                self.already_enrolled_c += 1
                return True  # treat as success so the caller marks it enrolled

            # Handle rate-throttling: wait the requested time then retry
            wait = self._throttle_wait(result)
            if wait:
                time.sleep(wait)
                continue  # don't count this as a failed attempt

            logger.error(f"Single checkout attempt {attempt+1} failed for '{course.title}': {result}")
            self.client.get("https://www.udemy.com/payment/checkout/", headers=headers)
            time.sleep(5)

        return False

    def checkout_single(self, course: Course) -> bool:
        """Public single-course checkout. Builds headers and delegates to _checkout_one."""
        headers = {
            "User-Agent": "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.udemy.com",
            "Referer": "https://www.udemy.com/payment/checkout/",
            "X-CSRF-Token": self.client.cookies.get("csrftoken", domain="www.udemy.com"),
        }
        result = self._checkout_one(course, headers)
        # Reset the checkout page between courses
        self.client.get("https://www.udemy.com/payment/checkout/", headers=headers)
        return result

    def bulk_checkout(self, valid_courses: list[Course]):
        """Bulk enroll in courses with valid coupons."""
        logger.info(f"Bulk enrolling in {len(valid_courses)} courses")

        remaining = [c for c in valid_courses if not c.is_free]
        if not remaining:
            return False

        headers = {
            "User-Agent": "okhttp/4.10.0 UdemyAndroid 9.7.0(515) (phone)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.udemy.com",
            "Referer": "https://www.udemy.com/payment/checkout/",
            "X-CSRF-Token": self.client.cookies.get("csrftoken", domain="www.udemy.com"),
        }

        # One removal pass per course + 3 genuine retries
        for attempt in range(len(remaining) + 3):
            if not remaining:
                return True

            items = [
                {
                    "buyable": {"id": str(c.course_id), "type": "course"},
                    "discountInfo": {"code": c.coupon_code},
                    "price": {"amount": 0, "currency": self.currency.upper()},
                }
                for c in remaining
            ]
            payload = {
                "checkout_environment": "Marketplace",
                "checkout_event": "Submit",
                "payment_info": {"method_id": "0", "payment_method": "free-method", "payment_vendor": "Free"},
                "shopping_info": {"items": items, "is_cart": True},
            }

            r = self.client.post(
                "https://www.udemy.com/payment/checkout-submit/",
                json=payload, headers=headers,
            )
            try:
                result = {"status": "succeeded"} if r.status_code == 504 else r.json()
            except Exception:
                logger.error(f"Bulk checkout parse error: {r.text}")
                return False

            if result.get("status") == "succeeded":
                for course in remaining:
                    self.enrolled_courses[course.slug] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    self.amount_saved_c += Decimal(str(course.price)) if course.price else Decimal(0)
                    self.successfully_enrolled_c += 1
                logger.info(f"Successfully enrolled in {len(remaining)} courses")
                return True

            dev_msg = result.get("developer_message", "")
            if "item_already_subscribed" in dev_msg:
                msg_text = result.get("message", "")

                # Extract quoted title from Udemy's error message
                quoted = re.search(r'"([^"]+)"', msg_text)
                error_title = quoted.group(1) if quoted else ""

                # Find best word-overlap match in the batch
                offender = None
                if error_title:
                    best_score, best_course = 0.0, None
                    for c in remaining:
                        if c.title:
                            score = self._title_overlap(c.title, error_title)
                            if score > best_score:
                                best_score, best_course = score, c
                    if best_score >= 0.4:
                        offender = best_course

                if offender:
                    logger.warning(
                        f"Removing already-subscribed course (score={best_score:.2f}) "
                        f"from batch and retrying: {offender.title}"
                    )
                    self.enrolled_courses[offender.slug] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    self.already_enrolled_c += 1
                    remaining.remove(offender)
                    self.client.get("https://www.udemy.com/payment/checkout/", headers=headers)
                    continue  # retry immediately

                # Can't identify the offender — fall back to one-by-one
                logger.warning(
                    f"Could not identify already-subscribed course from '{error_title}' "
                    f"— falling back to one-by-one enrollment for {len(remaining)} courses"
                )
                for course in list(remaining):
                    self._checkout_one(course, headers)
                    self.client.get("https://www.udemy.com/payment/checkout/", headers=headers)
                    time.sleep(1)
                return True  # individual results already tracked inside _checkout_one

            # Handle rate-throttling: wait the requested time and retry without
            # burning one of the limited attempts
            wait = self._throttle_wait(result)
            if wait:
                time.sleep(wait)
                continue  # retry immediately after the wait; don't count as failure

            logger.error(f"Bulk checkout attempt {attempt + 1} failed: {result}")
            self.client.get("https://www.udemy.com/payment/checkout/", headers=headers)
            time.sleep(5 + min(attempt, 2))

        return False
