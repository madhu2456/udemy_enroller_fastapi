"""Tests for hosted-demo login restrictions (BACKLOG-008)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from main import app

client = TestClient(app)


class TestHostedDemoLoginRestrictions:
    @pytest.mark.parametrize("path", ["/", "/login"])
    def test_login_tabs_rendered_with_server_mode_restrictions(self, path):
        app.state.deployment_env = "server"
        try:
            response = client.get(path)
            assert response.status_code == 200
            assert 'id="tab-email"' in response.text
            assert 'id="tab-cookie"' in response.text
            assert 'id="cookie-form"' in response.text
            assert 'id="email-form"' in response.text
            assert 'id="smart-paste-box"' in response.text
            assert "<details" in response.text
            assert "Disabled on hosted demo" in response.text
            assert "Hosted Demo" in response.text
        finally:
            app.state.deployment_env = "local"

    @pytest.mark.parametrize("path", ["/", "/login"])
    def test_login_tabs_rendered_in_local_mode(self, path):
        app.state.deployment_env = "local"
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="tab-email"' in response.text
        assert 'id="tab-cookie"' in response.text
        assert 'id="email-form"' in response.text
        assert 'id="cookie-form"' in response.text
        assert "Disabled on hosted demo" not in response.text

    @patch("app.routers.auth.settings")
    @patch("app.routers.auth.UdemyClient")
    def test_email_login_api_disabled_in_server_mode(
        self, mock_client_class, mock_settings
    ):
        mock_settings.DEPLOYMENT_ENV = "server"
        # Login POSTs are double-submit CSRF protected (F-ENRL-C03): load the
        # login page first to receive the anonymous csrf_token cookie, then
        # echo it in the X-CSRF-Token header like the page's own JS does.
        client.cookies.clear()
        page = client.get("/")
        csrf_token = page.cookies.get("csrf_token")
        assert csrf_token, "login page must set an anonymous csrf_token cookie"
        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePassword123!",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cookie Login" in data["message"]
        mock_client_class.assert_not_called()

    @patch("app.routers.auth.settings")
    @patch("app.routers.auth.login_rate_limiter.is_allowed_redis", new_callable=AsyncMock)
    def test_email_login_rate_limiter_precedes_server_mode_check(
        self, mock_is_allowed, mock_settings
    ):
        mock_settings.DEPLOYMENT_ENV = "server"
        mock_is_allowed.return_value = False

        client.cookies.clear()
        page = client.get("/")
        csrf_token = page.cookies.get("csrf_token")
        assert csrf_token, "login page must set an anonymous csrf_token cookie"

        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePassword123!",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 429
        assert "Too many requests" in response.text
        mock_is_allowed.assert_called_once()