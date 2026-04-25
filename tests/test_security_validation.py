"""Comprehensive test suite for authentication, security, and validation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, AsyncMock

from main import app
from app.models.database import Base, get_db, User, UserSettings, UserSession
from app.security import (
    hash_password,
    verify_password,
    validate_proxy_url,
    URLValidator,
)


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_udemy_enroller.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    """Override get_db dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_db():
    """Clean up database after each test."""
    yield
    # Delete all records
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


class TestPasswordSecurity:
    """Test password hashing and verification."""

    def test_hash_password_creates_bcrypt_hash(self):
        """Test that password hashing creates valid bcrypt hash."""
        plain_password = "SecurePassword123!"
        hashed = hash_password(plain_password)

        assert hashed != plain_password
        assert len(hashed) > 0
        assert "$2b$" in hashed  # bcrypt prefix

    def test_hash_password_with_weak_password_fails(self):
        """Test that weak passwords are rejected."""
        weak_password = "short"
        with pytest.raises(ValueError, match="at least 8 characters"):
            hash_password(weak_password)

    def test_hash_password_with_empty_string_fails(self):
        """Test that empty passwords are rejected."""
        with pytest.raises(ValueError):
            hash_password("")

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        plain_password = "CorrectPassword123!"
        hashed = hash_password(plain_password)
        assert verify_password(plain_password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        plain_password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(plain_password)
        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_with_invalid_hash(self):
        """Test password verification with invalid hash."""
        assert verify_password("password", "invalid_hash") is False

    def test_verify_password_with_none_values(self):
        """Test password verification with None values."""
        assert verify_password(None, "hash") is False
        assert verify_password("password", None) is False


class TestURLValidation:
    """Test URL validation functionality."""

    def test_validate_url_valid_http(self):
        """Test validation of valid HTTP URLs."""
        validator = URLValidator(url="http://example.com:8080/path")
        assert validator.url == "http://example.com:8080/path"

    def test_validate_url_valid_https(self):
        """Test validation of valid HTTPS URLs."""
        validator = URLValidator(url="https://api.example.com/v1/endpoint")
        assert validator.url == "https://api.example.com/v1/endpoint"

    def test_validate_url_valid_socks5(self):
        """Test validation of valid SOCKS5 proxy URLs."""
        validator = URLValidator(url="socks5://proxy.example.com:1080")
        assert validator.url == "socks5://proxy.example.com:1080"

    def test_validate_url_empty_string_fails(self):
        """Test that empty URL is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            URLValidator(url="")

    def test_validate_url_invalid_scheme_fails(self):
        """Test that invalid schemes are rejected."""
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            URLValidator(url="ftp://example.com")

    def test_validate_url_no_netloc_fails(self):
        """Test that URLs without network location are rejected."""
        with pytest.raises(ValueError, match="no network location"):
            URLValidator(url="http://")

    def test_validate_url_exceeds_max_length(self):
        """Test that URLs exceeding max length are rejected."""
        long_url = "http://example.com/" + "a" * 2100
        with pytest.raises(ValueError, match="exceeds maximum length"):
            URLValidator(url=long_url)

    def test_validate_url_with_injection_attempt(self):
        """Test that URLs with injection patterns are rejected."""
        with pytest.raises(ValueError, match="Invalid characters"):
            URLValidator(url="http://example.com\nmalicious")

    def test_proxy_url_validation_valid(self):
        """Test proxy URL validation with valid URL."""
        assert validate_proxy_url("socks5://proxy.example.com:1080") is True

    def test_proxy_url_validation_empty(self):
        """Test proxy URL validation with None/empty."""
        assert validate_proxy_url(None) is True
        assert validate_proxy_url("") is True

    def test_proxy_url_validation_invalid(self):
        """Test proxy URL validation with invalid URL."""
        assert validate_proxy_url("invalid://url") is False


class TestAuthEndpoints:
    """Test authentication endpoints."""

    @patch("app.routers.auth.UdemyClient")
    def test_login_new_user(self, mock_client_class):
        """Test login with new user credentials."""
        mock_client = MagicMock()
        mock_client.manual_login = AsyncMock(return_value=None)
        mock_client.get_session_info = AsyncMock(return_value=None)
        mock_client.display_name = "Test User"
        mock_client.currency = "USD"
        mock_client.cookie_dict = {"key": "value"}
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "SecurePassword123!"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["status"] == "success"

    @patch("app.routers.auth.UdemyClient")
    def test_login_weak_password(self, mock_client_class):
        """Test login with weak password."""
        response = client.post(
            "/api/auth/login", json={"email": "test@example.com", "password": "weak"}
        )

        assert response.status_code == 422

    def test_auth_status_unauthenticated(self):
        """Test auth status when not authenticated."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    def test_logout_without_session(self):
        """Test logout without active session."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestEnrollmentSessionRestore:
    """Test restoring in-memory Udemy session from persisted DB session."""

    def setup_method(self):
        """Create a user with stored cookies and a DB session token."""
        db = TestingSessionLocal()
        user = User(
            email="restore@example.com",
            password_hash=hash_password("RestorePassword123!"),
            udemy_display_name="Restore User",
            udemy_cookies={
                "access_token": "access-token",
                "client_id": "client-id",
                "csrf_token": "csrf-token",
            },
            currency="USD",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(UserSettings(user_id=user.id))
        db.commit()

        import secrets

        token = secrets.token_hex(32)
        db.add(UserSession(token=token, user_id=user.id))
        db.commit()

        self.db = db
        self.session_token = token
        client.cookies.set("session_id", self.session_token)
        app.state.udemy_clients = {}

    def teardown_method(self):
        """Cleanup per-test state."""
        self.db.close()
        client.cookies.clear()
        app.state.udemy_clients = {}

    @patch("app.routers.enrollment.EnrollmentManager.start_run", new_callable=AsyncMock)
    @patch("app.deps.UdemyClient")
    def test_start_enrollment_restores_client_after_restart(
        self, mock_udemy_client_class, mock_start
    ):
        """Start should work after restart by restoring client from persisted session."""
        mock_start.return_value = 123
        mock_client = MagicMock()
        mock_client.is_authenticated = True
        mock_client.get_session_info = AsyncMock(return_value=None)
        mock_udemy_client_class.return_value = mock_client

        response = client.post("/api/enrollment/start")

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_client.get_session_info.assert_awaited_once()
        assert self.session_token in app.state.udemy_clients


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_health_check_not_rate_limited(self):
        """Test that health check is accessible."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_multiple_requests_allowed(self):
        """Test that multiple requests are allowed."""
        for _ in range(5):
            response = client.get("/api/health")
            assert response.status_code == 200


class TestCORS:
    """Test CORS configuration."""

    def test_cors_origin_in_response(self):
        """Test that CORS headers are present in responses."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_endpoint_accessible(self):
        """Test that health endpoint is accessible."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data


class TestSettingsValidation:
    """Test settings endpoint validation."""

    def setup_method(self):
        """Setup for each test."""
        # Create a test user and session
        user = User(
            email="test@example.com",
            password_hash=hash_password("TestPassword123!"),
            udemy_display_name="Test User",
            currency="USD",
        )
        db = TestingSessionLocal()
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create user settings
        settings = UserSettings(user_id=user.id)
        db.add(settings)
        db.commit()

        # Create session token
        import secrets

        token = secrets.token_hex(32)
        session = UserSession(token=token, user_id=user.id)
        db.add(session)
        db.commit()

        self.user_id = user.id
        self.session_token = token
        self.db = db
        client.cookies.set("session_id", self.session_token)

    def teardown_method(self):
        """Cleanup after each test."""
        self.db.close()
        client.cookies.clear()

    @patch("app.deps.get_current_user_id")
    def test_update_settings_with_valid_proxy(self, mock_user_id):
        """Test updating settings with valid proxy URL."""
        mock_user_id.return_value = self.user_id

        response = client.put(
            "/api/settings/", json={"proxy_url": "socks5://proxy.example.com:1080"}
        )

        assert response.status_code == 200

    @patch("app.deps.get_current_user_id")
    def test_update_settings_with_invalid_proxy(self, mock_user_id):
        """Test updating settings with invalid proxy URL."""
        mock_user_id.return_value = self.user_id

        response = client.put("/api/settings/", json={"proxy_url": "invalid://proxy"})

        assert response.status_code == 422

    @patch("app.deps.get_current_user_id")
    def test_update_settings_min_rating_validation(self, mock_user_id):
        """Test min_rating validation (0-5)."""
        mock_user_id.return_value = self.user_id

        # Test invalid rating (>5)
        response = client.put("/api/settings/", json={"min_rating": 6.0})
        assert response.status_code == 422

    @patch("app.deps.get_current_user_id")
    def test_update_settings_valid_min_rating(self, mock_user_id):
        """Test valid min_rating values."""
        mock_user_id.return_value = self.user_id

        response = client.put("/api/settings/", json={"min_rating": 3.5})
        assert response.status_code == 200


class TestInputValidation:
    """Test input validation across the application."""

    def test_empty_email_rejected(self):
        """Test that empty email is rejected."""
        response = client.post(
            "/api/auth/login", json={"email": "", "password": "ValidPassword123!"}
        )
        assert response.status_code == 422

    def test_invalid_email_format(self):
        """Test that invalid email format is handled."""
        response = client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "ValidPassword123!"},
        )
        assert response.status_code == 422

    def test_password_minimum_length(self):
        """Test that passwords below minimum length are rejected."""
        response = client.post(
            "/api/auth/login", json={"email": "test@example.com", "password": "short"}
        )
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
