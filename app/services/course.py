"""Course model for the enrollment system."""

from urllib.parse import parse_qs, urlparse, urlsplit, urlunparse
import logging

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
        parsed_url = urlparse(url)
        # Upgrade http → https and bare "udemy.com" → "www.udemy.com"
        scheme = "https"
        netloc = parsed_url.netloc.lower()
        if netloc == "udemy.com":
            netloc = "www.udemy.com"
        path = parsed_url.path if parsed_url.path.endswith("/") else parsed_url.path + "/"
        return urlunparse((
            scheme, netloc, path,
            parsed_url.params, parsed_url.query, parsed_url.fragment,
        ))

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
        self.coupon_code = params.get("couponCode", [None])[0]

    def set_metadata(self, dma):
        try:
            if dma.get("view_restriction"):
                self.is_valid = False
                self.error = dma["serverSideProps"]["limitedAccess"]["errorMessage"]["title"]
                return
            course_data = dma["serverSideProps"]["course"]
            self.instructors = [
                i["absolute_url"].split("/")[-2]
                for i in course_data["instructors"]["instructors_info"]
                if i["absolute_url"]
            ]
            self.language = course_data["localeSimpleEnglishTitle"]
            self.category = dma["serverSideProps"]["topicMenu"]["breadcrumbs"][0]["title"]
            self.rating = course_data["rating"]
            self.last_update = course_data["lastUpdateDate"]
            self.is_free = not course_data.get("isPaid", True)
        except Exception as e:
            self.is_valid = False
            self.error = f"Error parsing course metadata: {str(e)}"

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
