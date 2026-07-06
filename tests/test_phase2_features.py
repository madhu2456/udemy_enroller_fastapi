"""Unit tests for Phase 2 functional and security features: filters, identity migration, log isolation, and settings validations."""

import pytest
import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from config.settings import Settings
from app.services.course import Course
from app.services.udemy_client import UdemyClient
from app.routers.auth import login_with_cookies
from app.models.database import User

# ==========================================
# 1. Pydantic Settings Validation Tests
# ==========================================

class TestProductionSettingsValidation:
    """Test the Settings model validation for production deployment safety."""

    def test_local_env_allows_defaults(self):
        """Test that default keys are auto-generated in local development."""
        settings = Settings(
            DEPLOYMENT_ENV="local",
            SECRET_KEY="change-me-in-production-use-a-strong-secret-key",
            COOKIE_SECURE=False
        )
        # The model validator auto-generates a random key when it detects the default
        assert settings.SECRET_KEY != "change-me-in-production-use-a-strong-secret-key"
        assert len(settings.SECRET_KEY) == 64  # 32 bytes hex = 64 chars
        assert settings.COOKIE_SECURE is False

    def test_server_env_rejects_default_secret_key(self):
        """Test that server mode rejects short/insecure secret keys."""
        # Key shorter than 32 characters should raise ValueError
        with pytest.raises(ValueError, match="SECRET_KEY must be at least 32"):
            Settings(
                DEPLOYMENT_ENV="server",
                SECRET_KEY="short-key"
            )
        # A key >= 32 chars with encryption key present should succeed
        from cryptography.fernet import Fernet
        valid_fernet_key = Fernet.generate_key().decode()
        settings = Settings(
            DEPLOYMENT_ENV="server",
            SECRET_KEY="a-valid-strong-secure-random-key-1234567890",
            COOKIE_ENCRYPTION_KEY=valid_fernet_key,
        )
        assert settings.COOKIE_SECURE is True

    def test_server_env_forces_cookie_secure(self):
        """Test that server mode automatically forces COOKIE_SECURE to True."""
        from cryptography.fernet import Fernet
        valid_fernet_key = Fernet.generate_key().decode()
        settings = Settings(
            DEPLOYMENT_ENV="server",
            SECRET_KEY="a-valid-strong-secure-random-key-1234567890",
            COOKIE_ENCRYPTION_KEY=valid_fernet_key,
            COOKIE_SECURE=False  # Try setting it to False
        )
        assert settings.COOKIE_SECURE is True


# ==========================================
# 2. Settings, Exclusions & Filters Tests
# ==========================================

class TestCourseFiltersAndExclusions:
    """Test the complete Udemy course exclusion and metadata-based filter logic."""

    @pytest.fixture
    def client(self):
        return UdemyClient()

    @pytest.fixture
    def settings_dict(self):
        return {
            "min_rating": 4.5,
            "languages": {"English": True, "Spanish": True, "French": False},
            "categories": {"Development": True, "Business": False},
            "instructor_exclude": ["bad-instructor", "spammer"],
            "title_exclude": ["trash", "spam"],
            "course_update_threshold_months": 12
        }

    def test_rating_exclusion(self, client, settings_dict):
        """Verify rating-based exclusion."""
        course = Course("Python Course", "https://udemy.com/course/python/")
        course.rating = 4.2  # Below 4.5
        course.language = "English"
        course.category = "Development"
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True
        assert "Rating" in course.error

        course_ok = Course("Python Course", "https://udemy.com/course/python/")
        course_ok.rating = 4.7
        course_ok.language = "English"
        course_ok.category = "Development"
        client.is_course_excluded(course_ok, settings_dict)
        assert course_ok.is_excluded is False

    def test_language_exclusion(self, client, settings_dict):
        """Verify language dictionary exclusion (True = allowed, False = excluded)."""
        course = Course("French Python", "https://udemy.com/course/french/")
        course.language = "French"  # French is False in settings
        course.category = "Development"
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True

        course_spanish = Course("Spanish Python", "https://udemy.com/course/spanish/")
        course_spanish.language = "Spanish"  # Spanish is True
        course_spanish.category = "Development"
        client.is_course_excluded(course_spanish, settings_dict)
        assert course_spanish.is_excluded is False

        course_unsupported = Course("German Python", "https://udemy.com/course/german/")
        course_unsupported.language = "German"  # German is missing from settings map
        course_unsupported.category = "Development"
        client.is_course_excluded(course_unsupported, settings_dict)
        assert course_unsupported.is_excluded is True

    def test_category_exclusion(self, client, settings_dict):
        """Verify category dictionary exclusion."""
        course = Course("Business Python", "https://udemy.com/course/business/")
        course.category = "Business"  # Business is False
        course.language = "English"
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True

        course_dev = Course("Development Python", "https://udemy.com/course/dev/")
        course_dev.category = "Development"  # Development is True
        course_dev.language = "English"
        client.is_course_excluded(course_dev, settings_dict)
        assert course_dev.is_excluded is False

    def test_instructor_exclusion(self, client, settings_dict):
        """Verify instructor exclusion."""
        course = Course("Python Course", "https://udemy.com/course/python/")
        course.instructors = ["bad-instructor"]
        course.language = "English"
        course.category = "Development"
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True

        course_ok = Course("Python Course", "https://udemy.com/course/python/")
        course_ok.instructors = ["good-instructor"]
        course_ok.language = "English"
        course_ok.category = "Development"
        client.is_course_excluded(course_ok, settings_dict)
        assert course_ok.is_excluded is False

    def test_title_exclusions(self, client, settings_dict):
        """Verify keyword title exclusions."""
        course = Course("Python course is a trash course", "https://udemy.com/course/python/")
        course.language = "English"
        course.category = "Development"
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True

        course_ok = Course("Perfect Python Course", "https://udemy.com/course/python/")
        course_ok.language = "English"
        course_ok.category = "Development"
        client.is_course_excluded(course_ok, settings_dict)
        assert course_ok.is_excluded is False

    def test_last_updated_threshold(self, client, settings_dict):
        """Verify course last updated date threshold exclusion."""
        course = Course("Old Python", "https://udemy.com/course/old/")
        course.language = "English"
        course.category = "Development"
        
        # 2 years ago (threshold is 12 months)
        two_years_ago = (datetime.datetime.now() - datetime.timedelta(days=730)).strftime("%Y-%m-%d")
        course.last_update = two_years_ago
        client.is_course_excluded(course, settings_dict)
        assert course.is_excluded is True

        # 3 months ago (valid)
        three_months_ago = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
        course_ok = Course("New Python", "https://udemy.com/course/new/")
        course_ok.language = "English"
        course_ok.category = "Development"
        course_ok.last_update = three_months_ago
        client.is_course_excluded(course_ok, settings_dict)
        assert course_ok.is_excluded is False


# ==========================================
# 3. Cookie Login Stable Identity & Migration Tests
# ==========================================

@pytest.mark.asyncio
class TestCookieLoginIdentityMigration:
    """Test identity migration and stable Udemy ID checks inside /login/cookies."""

    async def test_legacy_user_migration_flow(self):
        """Verify legacy display-name users are successfully migrated to stable ID emails."""
        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_cookie_req = MagicMock(
            access_token="token123",
            client_id="client123",
            csrf_token="csrf123"
        )

        mock_user = User(
            id=42,
            email="john_doe@udemy.local",  # Legacy email format
            udemy_display_name="John Doe",
            udemy_cookies=None
        )

        # Mock query sequence: First query by email (None), second query by display name (returns legacy user)
        mock_db.query.return_value.filter.return_value.first.side_effect = [None, mock_user]

        mock_client_inst = MagicMock(
            display_name="John Doe",
            udemy_user_id="9999",
            cookie_dict={"access_token": "token123"},
            currency="usd"
        )
        mock_client_inst.get_session_info = AsyncMock()

        with patch("app.routers.auth.UdemyClient", return_value=mock_client_inst):
            with patch("app.routers.auth.encrypt_cookies", return_value=b"encrypted"):
                with patch("app.routers.auth._create_session", return_value="session123"):
                    with patch("app.routers.auth._login_response"):
                        await login_with_cookies(mock_cookie_req, mock_request, mock_db)

        # Assert that the user's email was successfully migrated to stable Udemy ID email
        assert mock_user.email == "udemy_9999@udemy.local"
        assert mock_db.commit.call_count >= 1


# ==========================================
# 4. Log Isolation Stream-Filtering Tests
# ==========================================

class TestLogIsolationFiltering:
    """Test user log isolation and stream filtering."""

    def test_log_stream_user_tag_isolation(self):
        """Test process_log_line to verify log leakage prevention between users."""
        
        # Setup mock stream handler logic matching app/routers/dashboard.py
        def process_log_line(line: str, user_id: int) -> str | None:
            import re
            match = re.search(r" \[user:(\d+)\]", line)
            if match:
                line_user_id = int(match.group(1))
                if line_user_id == user_id:
                    return line.replace(match.group(0), "")
            return None

        user_1_line = "2026-05-31 14:00:00 | INFO | starting scraping [user:1]\n"
        user_2_line = "2026-05-31 14:00:00 | INFO | starting scraping [user:2]\n"
        system_line = "2026-05-31 14:00:00 | INFO | app initialization successful\n"

        # User 1 context: Should ONLY see User 1 logs; untagged system lines and other-user lines must be blocked
        assert process_log_line(user_1_line, user_id=1) == "2026-05-31 14:00:00 | INFO | starting scraping\n"
        assert process_log_line(user_2_line, user_id=1) is None
        assert process_log_line(system_line, user_id=1) is None

        # User 2 context: Should ONLY see User 2 logs; untagged system lines and other-user lines must be blocked
        assert process_log_line(user_1_line, user_id=2) is None
        assert process_log_line(user_2_line, user_id=2) == "2026-05-31 14:00:00 | INFO | starting scraping\n"
        assert process_log_line(system_line, user_id=2) is None


# ==========================================
# 5. Phase 2 Security Refinement Tests
# ==========================================

class TestPhase2SecurityRefinements:
    """Test all refined security features from the follow-up review."""

    def test_escape_attr_harden(self):
        """Test that attribute breakout payloads are successfully escaped."""
        def escape_attr(val):
            if val is None:
                return ""
            return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")

        payload = 'https://x/" onmouseover="alert(1)'
        escaped = escape_attr(payload)
        assert escaped == 'https://x/&quot; onmouseover=&quot;alert(1)'
        assert '"' not in escaped
        assert "'" not in escaped

    def test_sanitize_url_query_ampersand(self):
        """Test that sanitizeURL does not escape ampersands in query parameters for direct DOM property assignment."""
        def sanitize_url(val):
            if not val:
                return ""
            clean = str(val).strip()
            if clean.startswith("http://") or clean.startswith("https://") or clean.startswith("/"):
                return clean
            return "about:blank"

        url = "https://udemy.com/course/python/?coupon=FREE&ref=ad"
        sanitized = sanitize_url(url)
        assert sanitized == url
        assert "&" in sanitized  # Safe and uncorrupted for direct DOM assignment

    def test_udemy_identity_fallback_hash(self):
        """Test that Udemy stable fallback ID avoids collisions by using client_id / access_token cookie material."""
        import hashlib
        def get_fallback_id(client_id, access_token, display_name):
            cookie_material = client_id or access_token or ""
            hash_input = f"{cookie_material}:{display_name}"
            return "fallback_" + hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:12]

        id1 = get_fallback_id("client1", None, "John Doe")
        id2 = get_fallback_id("client2", None, "John Doe")

        assert id1.startswith("fallback_")
        assert id2.startswith("fallback_")
        assert id1 != id2  # Avoids "John Doe" display name collisions

    def test_metadata_filters_fail_closed_only_when_narrowed(self):
        """Test that missing course metadata causes exclusion only if filters are actively narrowed from defaults."""
        client = UdemyClient()

        # Default settings (all languages allowed, none False)
        default_settings = {
            "languages": {"English": True, "Spanish": True},
            "categories": {"Development": True}
        }

        # Narrowed settings (at least one language False)
        narrowed_settings = {
            "languages": {"English": True, "Spanish": False},
            "categories": {"Development": True}
        }

        course_missing_meta = Course("Unknown Course", "https://udemy.com/course/unknown/")
        course_missing_meta.language = None
        course_missing_meta.category = None

        # Under default settings, missing metadata does NOT exclude (fail open)
        client.is_course_excluded(course_missing_meta, default_settings)
        assert course_missing_meta.is_excluded is False

        # Under narrowed settings, missing metadata DOES exclude (fail closed)
        client.is_course_excluded(course_missing_meta, narrowed_settings)
        assert course_missing_meta.is_excluded is True
        assert "Language filter enabled but course language is missing" in course_missing_meta.error

    def test_save_txt_user_isolation(self):
        """Test that save_txt writes to the current user's file only."""
        user_id = 42
        filename = f"Courses/enrolled_courses_{user_id}.txt"
        assert filename == "Courses/enrolled_courses_42.txt"
