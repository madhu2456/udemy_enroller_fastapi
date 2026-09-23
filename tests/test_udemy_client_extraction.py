"""Tests for the robust Course ID extraction in UdemyClient."""

import html as html_lib
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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

    def test_extract_quoted_string_id(self, udemy_client):
        html = '<script>var config = {"courseId": "12345"};</script>'
        assert udemy_client._extract_course_id(html) == "12345"

    def test_extract_escaped_quote_json(self, udemy_client):
        html = r'<div data-json="{\"courseId\":\"12345\"}">'
        assert udemy_client._extract_course_id(html) == "12345"

    def test_extract_html_entity_quotes(self, udemy_client):
        html = '<div data-props="&quot;courseId&quot;:&quot;12345&quot;">'
        assert udemy_client._extract_course_id(html) == "12345"

    def test_mobile_deeplink_precedence_over_legacy_div(self, udemy_client):
        html = (
            '<div data-course-id="111111"></div>'
            '<script>{"urlMobileNativeDeeplink":"udemy://discover?courseId=222222"}</script>'
        )
        assert udemy_client._extract_course_id(html) == "222222"

    def test_prevention_of_carousel_collisions(self, udemy_client):
        html = (
            '<html><body>'
            '<div class="recommendation-carousel" data-course-id="999999"></div>'
            '</body></html>'
        )
        assert udemy_client._extract_course_id(html) is None

    def test_container_data_clp_course_id(self, udemy_client):
        html = '<html><body><main class="clp-lead" data-clp-course-id="777777"></main></body></html>'
        assert udemy_client._extract_course_id(html) == "777777"


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
        # Redirect target must be an exact Udemy netloc (F-ENRL-C07 gate);
        # a MagicMock url would be rejected as a non-Udemy host.
        mock_html_resp.url = "https://www.udemy.com/course/test/"

        with patch.object(
            udemy_client.http, "get", side_effect=[mock_api_resp, mock_html_resp]
        ):
            with patch.object(udemy_client.http, "safe_json", return_value=None):
                await udemy_client.get_course_id(course)

        assert course.course_id == "67890"

    async def test_get_course_id_un_gated_dma(self, udemy_client):
        course = Course("DMA Course", "https://www.udemy.com/course/dma-test/")
        course.slug = "dma-test"

        mock_api_resp = MagicMock(status_code=404)
        dma_json = {
            "serverSideProps": {
                "course": {
                    "id": 888888,
                    "localeSimpleEnglishTitle": "English",
                    "rating": 4.8,
                }
            }
        }
        encoded_dma = html_lib.escape(json.dumps(dma_json))
        html = f'<html><body><div class="device-market-attributes" data-server-side-props="{encoded_dma}"></div></body></html>'
        mock_html_resp = MagicMock(status_code=200, text=html)
        mock_html_resp.url = "https://www.udemy.com/course/dma-test/"

        with patch.object(
            udemy_client.http, "get", side_effect=[mock_api_resp, mock_html_resp]
        ):
            with patch.object(udemy_client.http, "safe_json", return_value=None):
                await udemy_client.get_course_id(course)

        assert course.is_valid is True
        assert course.course_id == "888888"
        assert course.language == "English"
        assert course.rating == 4.8


class TestCourseMetadataBoundsValidation:
    """Test bounds and validity enforcement in Course.set_metadata."""

    def test_course_set_metadata_bounds_validation(self):
        # Non-digits rejected
        c1 = Course("T1", "https://udemy.com/course/t1/")
        c1.set_metadata({"serverSideProps": {"course": {"id": "abc12"}}})
        assert c1.course_id is None

        # Length < 5 rejected
        c2 = Course("T2", "https://udemy.com/course/t2/")
        c2.set_metadata({"serverSideProps": {"course": {"id": 1234}}})
        assert c2.course_id is None

        # Length > 11 rejected
        c3 = Course("T3", "https://udemy.com/course/t3/")
        c3.set_metadata({"serverSideProps": {"course": {"id": 123456789012}}})
        assert c3.course_id is None

        # Blacklisted ID rejected
        c4 = Course("T4", "https://udemy.com/course/t4/")
        c4.set_metadata({"serverSideProps": {"course": {"id": 562413829}}})
        assert c4.course_id is None

        # Valid numeric ID accepted
        c5 = Course("T5", "https://udemy.com/course/t5/")
        c5.set_metadata({"serverSideProps": {"course": {"id": 123456}}})
        assert c5.course_id == "123456"


def _subscribed_result(slug: str) -> dict:
    return {
        "url": f"https://www.udemy.com/course/{slug}/",
        "enrollment_time": "2026-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
class TestGetEnrolledCoursesPagination:
    """Paginate subscribed-courses using Udemy next URLs only."""

    async def test_paginates_100_plus_7(self, udemy_client):
        page1 = {
            "results": [_subscribed_result(f"slug-{i}") for i in range(100)],
            "next": (
                "https://www.udemy.com/api-2.0/users/me/subscribed-courses/"
                "?page=2&page_size=100"
            ),
        }
        page2 = {
            "results": [_subscribed_result(f"slug-extra-{i}") for i in range(7)],
            "next": None,
        }
        udemy_client.cookie_dict = {"access_token": "dummy_access_token"}
        mock_get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_json = AsyncMock(side_effect=[page1, page2])

        with patch.object(udemy_client.http, "get", mock_get), patch.object(
            udemy_client.http, "safe_json", mock_json
        ):
            await udemy_client.get_enrolled_courses()

        assert len(udemy_client.enrolled_courses) == 107
        assert mock_get.await_count == 2
        for call in mock_get.await_args_list:
            assert call.kwargs["req_type"] == "mobile"
            assert call.kwargs["cookies"] is udemy_client.cookie_dict
            assert call.kwargs["headers"]["Authorization"] == "Bearer dummy_access_token"
        first_url = mock_get.await_args_list[0].args[0]
        assert "page_size=100" in first_url
        assert mock_get.await_args_list[1].args[0] == page1["next"]

    async def test_non_udemy_next_is_not_followed(self, udemy_client):
        page1 = {
            "results": [_subscribed_result(f"kept-{i}") for i in range(100)],
            "next": "https://evil.example/phish?page=2",
        }
        mock_get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_json = AsyncMock(return_value=page1)

        with patch.object(udemy_client.http, "get", mock_get), patch.object(
            udemy_client.http, "safe_json", mock_json
        ):
            await udemy_client.get_enrolled_courses()

        assert len(udemy_client.enrolled_courses) == 100
        assert mock_get.await_count == 1

    async def test_short_page_stops_even_with_next(self, udemy_client):
        page = {
            "results": [_subscribed_result("alpha"), _subscribed_result("beta")],
            "next": (
                "https://www.udemy.com/api-2.0/users/me/subscribed-courses/"
                "?page=2&page_size=100"
            ),
        }
        mock_get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_json = AsyncMock(return_value=page)

        with patch.object(udemy_client.http, "get", mock_get), patch.object(
            udemy_client.http, "safe_json", mock_json
        ):
            await udemy_client.get_enrolled_courses()

        assert len(udemy_client.enrolled_courses) == 2
        assert mock_get.await_count == 1

    async def test_empty_results_stop(self, udemy_client):
        page = {"results": [], "next": "https://www.udemy.com/api-2.0/users/me/subscribed-courses/?page=2"}
        mock_get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_json = AsyncMock(return_value=page)

        with patch.object(udemy_client.http, "get", mock_get), patch.object(
            udemy_client.http, "safe_json", mock_json
        ):
            await udemy_client.get_enrolled_courses()

        assert udemy_client.enrolled_courses == {}
        assert mock_get.await_count == 1
