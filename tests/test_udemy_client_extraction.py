"""Tests for the robust Course ID extraction in UdemyClient."""

import pytest
from bs4 import BeautifulSoup as bs
from unittest.mock import MagicMock, patch
from app.services.udemy_client import UdemyClient
from app.services.course import Course

@pytest.fixture
def udemy_client():
    client = UdemyClient()
    return client

class TestCourseIDExtraction:
    """Test the multiple strategies for extracting course IDs."""

    def test_extract_from_body_attribute(self, udemy_client):
        html = '<body data-clp-course-id="12345"></body>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "12345"

    def test_extract_from_body_data_course_id(self, udemy_client):
        html = '<body data-course-id="67890"></body>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "67890"

    def test_extract_from_meta_udemy_course(self, udemy_client):
        html = '<html><head><meta property="udemy_com:course" content="11111"></head><body></body></html>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "11111"

    def test_extract_from_meta_course_id(self, udemy_client):
        html = '<html><head><meta name="course-id" content="22222"></head><body></body></html>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "22222"

    def test_extract_from_script_course_id(self, udemy_client):
        html = '<html><body><script>window.UD = { visiting_course: { id: 33333 } };</script></body></html>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "33333"

    def test_extract_from_script_json_pattern(self, udemy_client):
        html = '<html><body><script>var params = {"course_id": 44444, "title": "Test"};</script></body></html>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "44444"

    def test_extract_from_script_camel_case(self, udemy_client):
        html = '<html><body><script>const config = {courseId: 55555};</script></body></html>'
        soup = bs(html, "lxml")
        assert udemy_client._extract_course_id(soup) == "55555"

    def test_extract_from_dma_metadata(self, udemy_client):
        """Test extraction via Course.set_metadata which uses data-module-args."""
        course = Course("Test", "https://udemy.com/course/test/")
        dma = {
            "serverSideProps": {
                "course": {
                    "id": 99999,
                    "localeSimpleEnglishTitle": "English",
                    "rating": 4.5,
                    "lastUpdateDate": "2024-01-01"
                },
                "topicMenu": {"breadcrumbs": [{"title": "Development"}]}
            }
        }
        course.set_metadata(dma)
        assert course.course_id == "99999"

@pytest.mark.asyncio
class TestGetCourseIDFlow:
    """Test the integrated get_course_id method."""

    async def test_get_course_id_success_with_metadata(self, udemy_client):
        course = Course("Test", "https://udemy.com/course/test/")
        
        # Mock response content with data-module-args
        mock_html = """
        <body data-module-args='{"serverSideProps": {"course": {"id": 88888}}}'>
        </body>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = mock_html
        mock_resp.url = "https://udemy.com/course/test/"
        
        with patch.object(udemy_client.http, 'get', return_value=mock_resp):
            await udemy_client.get_course_id(course)
            
        assert course.course_id == "88888"
        assert course.is_valid is True

    async def test_get_course_id_fallback_to_extraction(self, udemy_client):
        course = Course("Test", "https://udemy.com/course/test/")
        
        # Mock response content without DMA but with a script tag
        mock_html = """
        <html><body>
        <script>window.course_id = 77777;</script>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = mock_html
        mock_resp.url = "https://udemy.com/course/test/"
        
        with patch.object(udemy_client.http, 'get', return_value=mock_resp):
            await udemy_client.get_course_id(course)
            
        assert course.course_id == "77777"
        assert course.is_valid is True

    async def test_get_course_id_not_found(self, udemy_client):
        course = Course("Test", "https://udemy.com/course/test/")
        
        # Mock response content with nothing
        mock_html = "<html><body>No ID here</body></html>"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = mock_html
        mock_resp.url = "https://udemy.com/course/test/"
        
        with patch.object(udemy_client.http, 'get', return_value=mock_resp):
            await udemy_client.get_course_id(course)
            
        assert course.course_id is None
        assert course.is_valid is False
        assert course.error == "Course ID not found"
