"""Unit tests for UdemyClient enrolled courses cache, 500-page sync, and pre-owned detection."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.services.browser_cookies import UdemyBrowserCookies
from app.services.course import Course
from app.services.udemy_client import UdemyClient


class TestCacheLoadAndAtomicSave:
    """Wave 2: Cache persistence round-trip, atomic save, and corrupt file safety."""

    def test_cache_save_and_load_roundtrip(self, tmp_path):
        client = UdemyClient()
        client.udemy_user_id = "user_12345"
        client._cache_dir = tmp_path

        client.enrolled_courses = {"python-101": "2026-01-01T00:00:00Z"}
        client.enrolled_course_ids = {"9999"}
        client.full_sync_complete = True
        client.archived_sync_complete = True
        client.archived_sync_cursor_page = 3

        saved = client._save_enrolled_cache()
        assert saved is True
        cache_file = tmp_path / "enrolled_courses_user_12345.json"
        assert cache_file.exists()

        client2 = UdemyClient()
        client2.udemy_user_id = "user_12345"
        client2._cache_dir = tmp_path
        loaded = client2._load_enrolled_cache()
        assert loaded is True
        assert client2.enrolled_courses == {"python-101": "2026-01-01T00:00:00Z"}
        assert client2.enrolled_course_ids == {"9999"}
        assert client2.full_sync_complete is True
        assert client2.archived_sync_complete is True
        assert client2.archived_sync_cursor_page == 3

    def test_cache_noop_when_user_id_empty(self, tmp_path):
        client = UdemyClient()
        client.udemy_user_id = None
        client._cache_dir = tmp_path

        assert client._save_enrolled_cache() is False
        assert client._load_enrolled_cache() is False
        assert list(tmp_path.iterdir()) == []

    def test_cache_load_corrupted_json(self, tmp_path):
        client = UdemyClient()
        client.udemy_user_id = "user_corrupt"
        client._cache_dir = tmp_path

        corrupt_file = tmp_path / "enrolled_courses_user_corrupt.json"
        corrupt_file.write_text("NOT_VALID_JSON{{{")

        assert client._load_enrolled_cache() is False
        assert client.enrolled_courses is None


class TestGetEnrolledCoursesPagingAndCheckpoint:
    """Wave 2: get_enrolled_courses 500-page limit, checkpointing, and early-stop."""

    @pytest.mark.asyncio
    async def test_get_enrolled_courses_checkpointing_and_pacing(self, tmp_path):
        client = UdemyClient()
        client.udemy_user_id = "checkpoint_user"
        client._cache_dir = tmp_path
        client.archived_sync_complete = True  # isolate Phase 1

        # Simulate 12 pages of results: pages 0-10 have 100 courses, page 11 has 5 courses
        page_results = []
        for p in range(12):
            count = 100 if p < 11 else 5
            results = [
                {
                    "id": p * 100 + i,
                    "url": f"/course/course-p{p}-{i}/",
                    "enrollment_time": "2026-01-01T00:00:00Z",
                }
                for i in range(count)
            ]
            next_url = f"/api-2.0/users/me/subscribed-courses/?page={p+2}" if p < 11 else None
            page_results.append({"results": results, "next": next_url})

        current_page = 0

        async def mock_get(url, **kwargs):
            return MagicMock(status_code=200)

        async def mock_safe_json(resp, context):
            nonlocal current_page
            if current_page < len(page_results):
                data = page_results[current_page]
                current_page += 1
                return data
            return None

        client.http.get = AsyncMock(side_effect=mock_get)
        client.http.safe_json = AsyncMock(side_effect=mock_safe_json)

        save_calls = []
        orig_save = client._save_enrolled_cache

        def record_save():
            save_calls.append(client.full_sync_complete)
            return orig_save()

        client._save_enrolled_cache = MagicMock(side_effect=record_save)

        await client.get_enrolled_courses()

        # Checkpoint occurred at page 10 (with full_sync_complete False), and final save with True
        assert len(save_calls) >= 2
        assert False in save_calls
        assert client.full_sync_complete is True
        assert len(client.enrolled_courses) == 1105
        assert len(client.enrolled_course_ids) == 1105

    @pytest.mark.asyncio
    async def test_get_enrolled_courses_early_stop_when_full_sync_complete(self):
        client = UdemyClient()
        client.full_sync_complete = True
        client.enrolled_courses = {f"course-{i}": "" for i in range(25)}
        client.enrolled_course_ids = {str(i) for i in range(25)}

        # Page 1 contains 12 courses that are already known
        results = [
            {"id": i, "url": f"/course/course-{i}/", "enrollment_time": ""}
            for i in range(12)
        ]
        page_data = {"results": results, "next": "/next-page"}

        client.http.get = AsyncMock(return_value=MagicMock(status_code=200))
        client.http.safe_json = AsyncMock(return_value=page_data)

        await client.get_enrolled_courses()

        # Only 1 page should have been fetched due to early-stop at 10 consecutive known
        assert client.http.get.await_count == 1

    @pytest.mark.asyncio
    async def test_get_enrolled_courses_no_early_stop_when_full_sync_false(self):
        client = UdemyClient()
        client.full_sync_complete = False
        client.enrolled_courses = {f"course-{i}": "" for i in range(25)}
        client.enrolled_course_ids = {str(i) for i in range(25)}

        page1 = {
            "results": [{"id": i, "url": f"/course/course-{i}/", "enrollment_time": ""} for i in range(100)],
            "next": "https://www.udemy.com/api-2.0/users/me/subscribed-courses/?page=2",
        }
        page2 = {
            "results": [{"id": 1000 + i, "url": f"/course/new-course-{i}/", "enrollment_time": ""} for i in range(50)],
            "next": None,
        }

        pages = [page1, page2]
        call_idx = 0

        async def mock_safe_json(resp, context):
            nonlocal call_idx
            res = pages[call_idx]
            call_idx += 1
            return res

        client.http.get = AsyncMock(return_value=MagicMock(status_code=200))
        client.http.safe_json = AsyncMock(side_effect=mock_safe_json)

        await client.get_enrolled_courses()

        # Did NOT early-stop on page 1 even though first 25 were known
        assert client.http.get.await_count == 2
        assert client.full_sync_complete is True


class TestTwoPhaseArchivedLibrarySync:
    """Wave 1 & 3: Two-Phase Complete Library Sync (Active + Archived courses)."""

    @pytest.mark.asyncio
    async def test_two_phase_sync_fetches_active_then_archived(self, tmp_path):
        """Verifies Phase 1 queries is_archived=false, then Phase 2 queries is_archived=true."""
        client = UdemyClient()
        client.udemy_user_id = "two_phase_user"
        client._cache_dir = tmp_path
        client.full_sync_complete = False
        client.archived_sync_complete = False

        requested_urls = []

        async def mock_get(url, **kwargs):
            requested_urls.append(url)
            return MagicMock(status_code=200)

        # Phase 1: 1 page of active courses
        phase1_data = {
            "results": [{"id": 101, "url": "/course/active-1/", "enrollment_time": "2026-01-01T00:00:00Z"}],
            "next": None,
        }
        # Phase 2: 1 page of archived courses
        phase2_data = {
            "results": [{"id": 202, "url": "/course/archived-1/", "enrollment_time": "2025-01-01T00:00:00Z"}],
            "next": None,
        }

        async def mock_safe_json(resp, context):
            if "archived" in context:
                return phase2_data
            return phase1_data

        client.http.get = AsyncMock(side_effect=mock_get)
        client.http.safe_json = AsyncMock(side_effect=mock_safe_json)

        with patch("asyncio.sleep", AsyncMock()):
            await client.get_enrolled_courses(sync_archived=True)

        assert len(requested_urls) == 2
        assert "is_archived=false" in requested_urls[0]
        assert "is_archived=true" in requested_urls[1]
        assert "active-1" in client.enrolled_courses
        assert "archived-1" in client.enrolled_courses
        assert client.full_sync_complete is True
        assert client.archived_sync_complete is True
        assert client.archived_sync_cursor_page == 1

    @pytest.mark.asyncio
    async def test_phase_2_skipped_when_archived_sync_complete(self, tmp_path):
        """When archived_sync_complete is True, Phase 2 makes 0 network calls."""
        client = UdemyClient()
        client.udemy_user_id = "cached_archived_user"
        client._cache_dir = tmp_path
        client.full_sync_complete = True
        client.archived_sync_complete = True

        requested_urls = []

        async def mock_get(url, **kwargs):
            requested_urls.append(url)
            return MagicMock(status_code=200)

        phase1_data = {
            "results": [{"id": 303, "url": "/course/active-303/", "enrollment_time": "2026-01-01T00:00:00Z"}],
            "next": None,
        }

        client.http.get = AsyncMock(side_effect=mock_get)
        client.http.safe_json = AsyncMock(return_value=phase1_data)

        with patch("asyncio.sleep", AsyncMock()):
            await client.get_enrolled_courses(sync_archived=True)

        assert len(requested_urls) == 1
        assert "is_archived=false" in requested_urls[0]
        # No is_archived=true request was made
        assert not any("is_archived=true" in u for u in requested_urls)

    @pytest.mark.asyncio
    async def test_archived_sync_cursor_resumes_from_checkpoint(self, tmp_path):
        """Phase 2 starts requesting from archived_sync_cursor_page and checkpoints."""
        client = UdemyClient()
        client.udemy_user_id = "resuming_user"
        client._cache_dir = tmp_path
        client.full_sync_complete = True
        client.archived_sync_complete = False
        client.archived_sync_cursor_page = 5

        requested_urls = []

        async def mock_get(url, **kwargs):
            requested_urls.append(url)
            return MagicMock(status_code=200)

        phase1_data = {"results": [], "next": None}
        phase2_data = {
            "results": [{"id": 404, "url": "/course/archived-404/", "enrollment_time": "2025-01-01T00:00:00Z"}],
            "next": None,
        }

        async def mock_safe_json(resp, context):
            if "archived" in context:
                return phase2_data
            return phase1_data

        client.http.get = AsyncMock(side_effect=mock_get)
        client.http.safe_json = AsyncMock(side_effect=mock_safe_json)

        with patch("asyncio.sleep", AsyncMock()):
            await client.get_enrolled_courses(sync_archived=True)

        # First request was Phase 1, second request was Phase 2 starting at page 5
        assert len(requested_urls) == 2
        assert "page=5" in requested_urls[1]
        assert "is_archived=true" in requested_urls[1]
        assert client.archived_sync_complete is True
        assert client.archived_sync_cursor_page == 1


class TestFreeCheckoutPreOwnedDetection:
    """Wave 2: free_checkout pre-owned timestamp delta (>15s) vs new (<15s) and pre-check."""

    @pytest.mark.asyncio
    async def test_free_checkout_pre_owned_timestamp_greater_than_15s(self):
        client = UdemyClient()
        course = Course(title="Pre-owned Course", url="https://www.udemy.com/course/pre-owned/")
        course.course_id = "111"
        course.is_free = True

        r1 = MagicMock(status_code=302, headers={})
        r2 = MagicMock(status_code=200, headers={})
        client.http.get = AsyncMock(side_effect=[r1, r2])

        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        client.http.safe_json = AsyncMock(
            return_value={"_class": "course", "id": 111, "enrollment_time": old_ts}
        )

        await client.free_checkout(course)

        assert course.status is False
        assert course.is_already_enrolled is True
        assert course.error == "already_enrolled"
        assert "pre-owned" in client.enrolled_courses
        assert "111" in client.enrolled_course_ids

    @pytest.mark.asyncio
    async def test_free_checkout_newly_enrolled_timestamp(self):
        client = UdemyClient()
        course = Course(title="Newly Enrolled Course", url="https://www.udemy.com/course/new-course/")
        course.course_id = "222"
        course.is_free = True

        r1 = MagicMock(status_code=200, headers={})
        r2 = MagicMock(status_code=200, headers={})
        client.http.get = AsyncMock(side_effect=[r1, r2])

        recent_ts = datetime.now(timezone.utc).isoformat()
        client.http.safe_json = AsyncMock(
            return_value={"_class": "course", "id": 222, "enrollment_time": recent_ts}
        )

        await client.free_checkout(course)

        assert course.status is True
        assert course.is_already_enrolled is False
        assert course.error is None
        assert "222" in client.enrolled_course_ids

    @pytest.mark.asyncio
    async def test_free_checkout_fast_precheck_skips_http(self):
        client = UdemyClient()
        course = Course(title="Known Course", url="https://www.udemy.com/course/known-course/")
        course.course_id = "333"
        course.is_already_enrolled = True

        client.http.get = AsyncMock()

        await client.free_checkout(course)

        assert course.status is False
        assert course.is_already_enrolled is True
        assert course.error == "already_enrolled"
        assert client.http.get.await_count == 0


class TestCliFastPreCheckSkipsCheckCourse:
    """Wave 3: CLI enroll skips check_course for already-owned courses."""

    def test_cli_fast_precheck_bypasses_check_course(self, tmp_path):
        runner = CliRunner()
        json_out = tmp_path / "results.json"

        owned_course = Course(
            title="Owned Course 101",
            url="https://www.udemy.com/course/owned-course/?couponCode=FREE100",
        )
        owned_course.slug = "owned-course"

        async def mock_stream(self):
            scraper_mock = MagicMock()
            scraper_mock.site_name = "Real Discount"
            scraper_mock.courses = [owned_course]
            yield scraper_mock, "completed"

        with patch("app.cli.commands.enroll.get_udemy_cookies") as mock_get_cookies, \
             patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
             patch("app.cli.commands.enroll.ScraperService.stream_results", new=mock_stream):

            mock_get_cookies.return_value = UdemyBrowserCookies(
                is_valid=True,
                access_token="mock_token",
                client_id="mock_cid",
                csrf_token="mock_csrf",
                browser_name="chrome",
            )

            mock_client = MagicMock()
            mock_client.get_session_info = AsyncMock(return_value=True)
            mock_client.get_enrolled_courses = AsyncMock(return_value={})
            mock_client.is_already_enrolled = AsyncMock(return_value=True)
            mock_client.check_course = AsyncMock()
            mock_client.checkout_single = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client.display_name = "Learner"
            mock_client.currency = "USD"
            mock_client.enrolled_courses = {"owned-course": ""}
            mock_client.successfully_enrolled_c = 0
            mock_client.already_enrolled_c = 0
            mock_client.expired_c = 0
            mock_client.excluded_c = 0
            mock_client.unknown_c = 0
            mock_client.amount_saved_c = Decimal(0)
            mock_client.is_course_excluded = MagicMock(return_value=False)

            mock_client_cls.return_value = mock_client

            result = runner.invoke(
                app,
                [
                    "enroll",
                    "--token",
                    "manual_token_123",
                    "--dry-run",
                    "--output",
                    str(json_out),
                ],
            )

            assert result.exit_code == 0
            # check_course must NOT have been called because pre-check skipped it
            assert mock_client.check_course.await_count == 0
            assert mock_client.already_enrolled_c >= 1
            assert "ALREADY OWNED" in result.output
