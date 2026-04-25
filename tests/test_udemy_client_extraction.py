"""Tests for the robust Course ID extraction in UdemyClient."""

import pytest
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
        assert udemy_client._extract_course_id(html) == "12345"

    def test_extract_from_body_data_course_id(self, udemy_client):
        html = '<body data-course-id="67890"></body>'
        assert udemy_client._extract_course_id(html) == "67890"

    def test_extract_from_script_course_id(self, udemy_client):
        html = "<html><body><script>window.course_id = 33333;</script></body></html>"
        assert udemy_client._extract_course_id(html) == "33333"

    def test_ignore_blacklisted_id(self, udemy_client):
        # Even if it looks like a course ID, 562413829 should be ignored
        html = (
            "<html><body><script>window.course_id = 562413829;</script></body></html>"
        )
        assert udemy_client._extract_course_id(html) is None


@pytest.mark.asyncio
class TestGetCourseIDFlow:
    """Test the integrated get_course_id method (No Playwright)."""

    async def test_get_course_id_success_via_api(self, udemy_client):
        course = Course("Test", "https://udemy.com/course/test/")
        course.slug = "test"

        mock_data = {"id": 12345}

        with patch.object(
            udemy_client.http, "get", return_value=MagicMock(status_code=200)
        ):
            with patch.object(udemy_client.http, "safe_json", return_value=mock_data):
                await udemy_client.get_course_id(course)

        assert course.course_id == "12345"

    async def test_get_course_id_success_via_html(self, udemy_client):
        course = Course("Test", "https://udemy.com/course/test/")
        course.slug = "test"

        # Mock API failure
        mock_api_resp = MagicMock(status_code=404)

        # Mock HTML success
        mock_html = '<body data-course-id="67890"></body>'
        mock_html_resp = MagicMock(status_code=200, text=mock_html)

        with patch.object(
            udemy_client.http, "get", side_effect=[mock_api_resp, mock_html_resp]
        ):
            with patch.object(udemy_client.http, "safe_json", return_value=None):
                await udemy_client.get_course_id(course)

        assert course.course_id == "67890"
