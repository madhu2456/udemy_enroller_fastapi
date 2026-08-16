"""SERP title/description length caps for coupon detail pages (Fix 16)."""

from pathlib import Path
import re

from app.core.seo_meta import (
    coupon_serp_description,
    coupon_serp_title,
    truncate_at_word,
)


class TestTruncateAtWord:
    def test_short_unchanged(self):
        assert truncate_at_word("Hello world", 20) == "Hello world"

    def test_truncates_at_word_boundary(self):
        result = truncate_at_word("The quick brown fox jumps", 14)
        assert len(result) <= 14
        assert result.endswith("…")
        assert " " not in result.rstrip("…") or result.count(" ") >= 1

    def test_empty_and_zero(self):
        assert truncate_at_word("", 10) == ""
        assert truncate_at_word("abc", 0) == ""
        assert truncate_at_word(None, 10) == ""  # type: ignore[arg-type]


class TestCouponSerpTitle:
    def test_short_title_full_structure(self):
        title = coupon_serp_title("Python Basics")
        assert title == "Python Basics — Free coupon | Udemy Enroller"
        assert len(title) <= 60
        assert title.endswith("| Udemy Enroller")
        assert "— Free coupon" in title

    def test_long_title_truncated_ends_with_brand(self):
        long = (
            "The Complete 2024 Web Development Bootcamp "
            "From Zero to Hero with React Node and MongoDB"
        )
        title = coupon_serp_title(long)
        assert len(title) <= 60
        assert title.endswith("| Udemy Enroller")
        assert "…" in title or len(long) + len(" — Free coupon | Udemy Enroller") <= 60

    def test_empty_title_fallback(self):
        title = coupon_serp_title("")
        assert len(title) <= 60
        assert "Free course" in title
        assert len(re.findall(r"\bUdemy\b", title)) == 1
        assert title.endswith("| Udemy Enroller")

    def test_whitespace_title_fallback(self):
        title = coupon_serp_title("   ")
        assert "Free course" in title
        assert len(re.findall(r"\bUdemy\b", title)) == 1
        assert len(title) <= 60


class TestCouponSerpDescription:
    def test_description_within_limit(self):
        desc = coupon_serp_description(
            "Python Basics",
            "Development",
            coupon_code="FREE2024",
            language="English",
        )
        assert len(desc) <= 155
        assert "Python Basics" in desc
        assert "Development" in desc
        assert "FREE2024" in desc
        assert "Not affiliated with Udemy" in desc

    def test_long_title_description_capped(self):
        long = (
            "The Complete Ultimate Masterclass in Full Stack Web Development "
            "Including React Angular Vue Node Express MongoDB and AWS Deployment"
        )
        desc = coupon_serp_description(
            long,
            "Development",
            coupon_code="LONGCODE99",
            language="English",
        )
        assert len(desc) <= 155
        assert desc  # non-empty

    def test_empty_title_fallback(self):
        desc = coupon_serp_description("", "Other")
        assert len(desc) <= 155
        assert "this course" in desc
        assert "Not affiliated with Udemy" in desc

    def test_no_code_still_valid(self):
        desc = coupon_serp_description("Short Course", "IT & Software")
        assert len(desc) <= 155
        assert "Code " not in desc
        assert "Not affiliated with Udemy" in desc


class TestMetaKeywordsEmpty:
    TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"

    def test_keyword_blocks_are_empty_or_absent(self):
        stuffed = []
        empty_block = re.compile(
            r"\{%\s*block\s+meta_keywords\s*%\}\s*\{%\s*endblock\s*%\}"
        )
        for path in self.TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"\{%\s*block\s+meta_keywords\s*%\}(.*?)\{%\s*endblock\s*%\}",
                text,
                flags=re.S,
            ):
                if match.group(1).strip():
                    stuffed.append(f"{path}:block={match.group(1).strip()!r}")
            for match in re.finditer(
                r'<meta[^>]*name=["\']keywords["\'][^>]*content=["\']([^"\']*)["\']',
                text,
                flags=re.I | re.S,
            ):
                value = match.group(1).strip()
                if value and not empty_block.fullmatch(value):
                    stuffed.append(f"{path}:content={value!r}")
        assert stuffed == []
