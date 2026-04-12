"""Comprehensive pytest test suite for core functionality."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock

from main import app
from app.models.database import Base, get_db, User, UserSettings
from app.security import hash_password, verify_password
from app.security import validate_proxy_url


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_udemy_enroller.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


# ──────────────────────────────────────────────────────────────
# Security Tests
# ──────────────────────────────────────────────────────────────

class TestPasswordSecurity:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test password hashing."""
        plain_password = "test_password_123"
        hashed = hash_password(plain_password)
        
        assert hashed != plain_password
        assert len(hashed) > 0
        assert "$2b$" in hashed  # bcrypt prefix

    def test_verify_password_success(self):
        """Test password verification with correct password."""
        plain_password = "test_password_123"
        hashed = hash_password(plain_password)
        
        assert verify_password(plain_password, hashed) is True

    def test_verify_password_failure(self):
        """Test password verification with incorrect password."""
        hashed = hash_password("correct_password")
        
        assert verify_password("wrong_password", hashed) is False

    def test_password_consistency(self):
        """Test that hashing is not deterministic (random salt)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestURLValidation:
    """Test URL validation for proxy and other inputs."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert validate_proxy_url("http://proxy.example.com:8080") is True

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert validate_proxy_url("https://proxy.example.com:8080") is True

    def test_valid_socks5_url(self):
        """Test valid SOCKS5 URL."""
        assert validate_proxy_url("socks5://localhost:1080") is True

    def test_invalid_scheme(self):
        """Test URL with invalid scheme."""
        assert validate_proxy_url("ftp://invalid.com") is False

    def test_invalid_format(self):
        """Test malformed URL."""
        assert validate_proxy_url("not a url") is False

    def test_empty_url(self):
        """Test empty URL."""
        assert validate_proxy_url("") is True


# ──────────────────────────────────────────────────────────────
# Health Check Tests
# ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self):
        """Test health check returns 200."""
        response = client.get("/api/health")
        assert response.status_code == 200
        
    def test_health_check_response_structure(self):
        """Test health check response has required fields."""
        response = client.get("/api/health")
        data = response.json()
        
        assert "status" in data
        assert "version" in data
        assert data["status"] == "healthy"


# ──────────────────────────────────────────────────────────────
# CORS Tests
# ──────────────────────────────────────────────────────────────

class TestCORSConfiguration:
    """Test CORS headers are properly configured."""

    def test_cors_headers_present(self):
        """Test that CORS headers are returned."""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


# ──────────────────────────────────────────────────────────────
# Database Tests
# ──────────────────────────────────────────────────────────────

class TestDatabaseModels:
    """Test database models and relationships."""

    def setup_method(self):
        """Setup test database before each test."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_user_creation_with_password_hash(self):
        """Test creating user with password hash."""
        db = TestingSessionLocal()
        try:
            user = User(
                email="test@example.com",
                password_hash=hash_password("test_password"),
                udemy_display_name="Test User"
            )
            db.add(user)
            db.commit()
            
            retrieved_user = db.query(User).filter(User.email == "test@example.com").first()
            assert retrieved_user is not None
            assert retrieved_user.email == "test@example.com"
            assert retrieved_user.password_hash is not None
            assert verify_password("test_password", retrieved_user.password_hash)
        finally:
            db.close()

    def test_user_settings_creation(self):
        """Test creating user settings."""
        db = TestingSessionLocal()
        try:
            user = User(email="test@example.com", udemy_display_name="Test User")
            db.add(user)
            db.commit()
            
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.commit()
            
            retrieved_settings = db.query(UserSettings).filter(
                UserSettings.user_id == user.id
            ).first()
            assert retrieved_settings is not None
            assert retrieved_settings.discounted_only is False
        finally:
            db.close()

    def test_user_settings_defaults(self):
        """Test user settings have proper defaults."""
        db = TestingSessionLocal()
        try:
            user = User(email="test@example.com", udemy_display_name="Test User")
            db.add(user)
            db.commit()
            
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.commit()
            
            assert settings.sites is not None
            assert settings.languages is not None
            assert settings.categories is not None
            assert isinstance(settings.instructor_exclude, list)
            assert settings.min_rating == 0.0
        finally:
            db.close()


# ──────────────────────────────────────────────────────────────
# Logging Tests
# ──────────────────────────────────────────────────────────────

class TestLogging:
    """Test logging configuration."""

    def test_logging_module_imports(self):
        """Test logging configuration imports successfully."""
        from app.logging_config import setup_logging
        logger = setup_logging()
        
        assert logger is not None


# ──────────────────────────────────────────────────────────────
# Sentry Configuration Tests
# ──────────────────────────────────────────────────────────────

class TestSentryConfiguration:
    """Test Sentry error tracking setup."""

    def test_sentry_initialization(self):
        """Test Sentry initializes with correct config."""
        from app.sentry_config import setup_sentry
        
        # Sentry setup should work even if DSN is empty
        setup_sentry()


# ──────────────────────────────────────────────────────────────
# Rate Limiting Tests
# ──────────────────────────────────────────────────────────────

class TestRateLimiting:
    """Test rate limiting configuration."""

    def test_rate_limit_config_imports(self):
        """Test rate limiting config imports successfully."""
        from app.rate_limit_config import setup_rate_limiting, limiter
        
        assert limiter is not None


# ──────────────────────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────────────────────

class TestAPIIntegration:
    """Test API endpoints integration."""

    def setup_method(self):
        """Setup test database before each test."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_auth_status_unauthenticated(self):
        """Test auth status returns false for unauthenticated users."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False

    def test_settings_get_unauthenticated(self):
        """Test settings endpoint returns 401 for unauthenticated users."""
        response = client.get("/api/settings/")
        assert response.status_code == 401

    def test_enrollment_start_unauthenticated(self):
        """Test enrollment endpoint returns 401 for unauthenticated users."""
        response = client.post("/api/enrollment/start")
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────
# Fixtures for cleanup
# ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_test_db():
    """Cleanup test database after each test."""
    yield
    # Cleanup can happen here if needed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
