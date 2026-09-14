import pytest
from app.services.course import Course, sanitize_course_title
from app.services.scraper import Scraper
from app.services.http_client import AsyncHTTPClient
from unittest.mock import MagicMock


def test_sanitize_none_and_non_scalar():
    assert sanitize_course_title(None) == ""
    assert sanitize_course_title([]) == ""
    assert sanitize_course_title({}) == ""
    assert sanitize_course_title(object()) == ""


def test_sanitize_numeric_scalars():
    assert sanitize_course_title(101) == "101"
    assert sanitize_course_title(3.14) == "3.14"
    assert sanitize_course_title(0) == "0"


def test_sanitize_html_tags():
    assert sanitize_course_title("<b>Python</b>") == "Python"
    assert sanitize_course_title("<p class=\"desc\">Data Science</p>") == "Data Science"
    assert sanitize_course_title("<div><span>Nested</span> <em>Tags</em></div>") == "Nested Tags"
    assert sanitize_course_title("<!-- comment -->Hidden Text<!-- /comment -->") == "Hidden Text"


def test_sanitize_html_entities_multi_pass():
    assert sanitize_course_title("Python &amp; AI") == "Python & AI"
    assert sanitize_course_title("Python &amp;amp; AI") == "Python & AI"
    assert sanitize_course_title("Learn &#039;Python&#039; &amp; &quot;SQL&quot;") == "Learn 'Python' & \"SQL\""
    assert sanitize_course_title("Price: 50&euro; &amp; 40&pound;") == "Price: 50€ & 40£"
    assert sanitize_course_title("&lt;b&gt;Introduction to Java&lt;/b&gt;") == "Introduction to Java"


def test_sanitize_preserve_math_and_code_comparisons():
    assert sanitize_course_title("x < y and y > z") == "x < y and y > z"
    assert sanitize_course_title("Score >= 90 &amp; Score < 100") == "Score >= 90 & Score < 100"


def test_sanitize_whitespace_collapsing():
    assert sanitize_course_title("   Course   Title   \n\t   With   Spaces   ") == "Course Title With Spaces"


def test_course_init_title_sanitized():
    c = Course("<b>Java &amp; Spring</b>", "https://www.udemy.com/course/java/")
    assert c.title == "Java & Spring"


def test_scraper_append_to_list_title_sanitized():
    class DummyScraper(Scraper):
        code_name = "dummy"
        site_name = "Dummy"
        async def scrape(self, detail_semaphore):
            pass

    http_client = MagicMock(spec=AsyncHTTPClient)
    scraper = DummyScraper(http_client)
    scraper.append_to_list("<b>Data &amp; AI</b>", "https://www.udemy.com/course/data-ai/")
    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Data & AI"
