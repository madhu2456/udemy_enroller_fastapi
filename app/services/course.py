"""Course model for the enrollment system."""

from urllib.parse import parse_qs, urlparse, urlsplit, urlunparse, unquote
import logging
import html

logger = logging.getLogger(__name__)


class Course:
    """Represents a Udemy course with metadata and enrollment state."""

    def __init__(self, title: str, url: str, site: str = None):
        self.title = title
        self.site = site
        self.url = None
        self.slug = None
        self.course_id = None
        self.coupon_code = None
        self.is_coupon_valid = False

        self.is_free = False
        self.is_valid = True
        self.is_excluded = False

        self.price = None
        self.list_price = None
        self.instructors = []
        self.language = None
        self.category = None
        self.rating = None
        self.last_update = None

        self.retry = False
        self.retry_after = None
        self.ready_time = None
        self.error: str = None
        self.status = None

        self.set_url(url)
        self.extract_coupon_code()

    def set_url(self, url: str):
        self.url = self.normalize_link(url)
        self.set_slug()

    @staticmethod
    def normalize_link(url: str) -> str:
        if not url:
            return ""

        # 0. Handle HTML entities and strip whitespace
        url = html.unescape(url).strip()
        # 1. Unquote multiple times in case of nested encoding (common in tracking links)
        url = unquote(unquote(url))

        # 1a. Capture coupon code from the original URL before redirect unwrapping
        original_parsed = urlparse(url)
        original_qs = parse_qs(original_parsed.query)
        original_coupon = original_qs.get("couponCode", [None])[0]

        # 2. Extract udemy link from query parameters (common in redirectors like trk.udemy.com)
        if "udemy.com" in url.lower() and any(
            k in url for k in ["link=", "url=", "u=", "target=", "redirect=", "go="]
        ):
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            for key in ["link", "url", "u", "target", "redirect", "go"]:
                if key in qs and "udemy.com" in qs[key][0]:
                    url = qs[key][0]
                    break

        parsed_url = urlparse(url)
        # Upgrade http → https and bare "udemy.com" → "www.udemy.com"
        scheme = "https"
        netloc = parsed_url.netloc.lower()
        if netloc == "udemy.com":
            netloc = "www.udemy.com"
        
        # Ensure it's a udemy link before we start stripping things
        if "udemy.com" in netloc:
            path = parsed_url.path
            if not path.endswith("/"):
                path += "/"
            
            # Extract coupon code to keep it, but strip other affiliate params
            qs = parse_qs(parsed_url.query)
            coupon = qs.get("couponCode", [None])[0] or original_coupon
            
            new_query = ""
            if coupon:
                new_query = f"couponCode={coupon}"
            
            return urlunparse(
                (
                    scheme,
                    netloc,
                    path,
                    "", # params
                    new_query,
                    "", # fragment
                )
            )

        # For non-udemy links (shouldn't really happen here but for safety)
        path = (
            parsed_url.path if parsed_url.path.endswith("/") else parsed_url.path + "/"
        )
        return urlunparse(
            (
                scheme,
                netloc,
                path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )

    def set_slug(self):
        parsed_url = urlparse(self.url)
        path_parts = parsed_url.path.split("/")
        if len(path_parts) > 2 and path_parts[1] == "course":
            self.slug = path_parts[2]
        elif len(path_parts) > 1:
            self.slug = path_parts[1]
        else:
            logger.error(f"Invalid URL format: {self.url}")
            self.slug = None

    def extract_coupon_code(self):
        params = parse_qs(urlsplit(self.url).query)
        coupon = params.get("couponCode", [None])[0]
        if coupon:
            self.coupon_code = coupon

    def set_metadata(self, dma):
        from app.services.udemy_client import BLACKLIST_IDS

        try:
            if dma.get("view_restriction"):
                self.is_valid = False
                self.error = (
                    dma.get("serverSideProps", {})
                    .get("limitedAccess", {})
                    .get("errorMessage", {})
                    .get("title", "Access Restricted")
                )
                return

            # Check for course ID in DMA if we don't have it
            if not self.course_id:
                cid = dma.get("serverSideProps", {}).get("course", {}).get("id")
                if cid and str(cid) not in BLACKLIST_IDS:
                    self.course_id = str(cid)

            course_data = dma.get("serverSideProps", {}).get("course", {})
            if not course_data:
                return

            self.instructors = [
                i["absolute_url"].split("/")[-2]
                for i in course_data.get("instructors", {}).get("instructors_info", [])
                if i.get("absolute_url")
            ]
            self.language = course_data.get("localeSimpleEnglishTitle")

            breadcrumbs = (
                dma.get("serverSideProps", {})
                .get("topicMenu", {})
                .get("breadcrumbs", [])
            )
            if breadcrumbs:
                self.category = breadcrumbs[0].get("title")

            self.rating = course_data.get("rating")
            self.last_update = course_data.get("lastUpdateDate")
            self.is_free = not course_data.get("isPaid", True)
        except Exception as e:
            logger.debug(f"Metadata parse partially failed for {self.title}: {str(e)}")

    def to_dict(self):
        return {
            "title": self.title,
            "url": self.url,
            "slug": self.slug,
            "course_id": self.course_id,
            "coupon_code": self.coupon_code,
            "price": float(self.price) if self.price else None,
            "category": self.category,
            "language": self.language,
            "rating": self.rating,
            "site": self.site,
            "is_free": self.is_free,
            "is_valid": self.is_valid,
            "is_excluded": self.is_excluded,
            "error": self.error,
        }

    def __str__(self):
        return f"{self.title} - {self.url}"

    def __eq__(self, other):
        if not isinstance(other, Course):
            return False
        return self.url == other.url

    def __hash__(self):
        return hash(self.url)
