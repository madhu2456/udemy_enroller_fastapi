"""Tests for hosted-demo login restrictions (BACKLOG-008)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestHostedDemoLoginRestrictions:
    def test_homepage_hides_email_tab_in_server_mode(self):
        app.state.deployment_env = "server"
        try:
            response = client.get("/")
            assert response.status_code == 200
            assert 'id="tab-email"' not in response.text
            assert "only <strong" in response.text
            assert "Cookie Login</strong> is available" in response.text
            assert 'id="cookie-form"' in response.text
        finally:
            app.state.deployment_env = "local"

    def test_homepage_shows_email_tab_in_local_mode(self):
        app.state.deployment_env = "local"
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="tab-email"' in response.text

    @patch("app.routers.auth.settings")
    @patch("app.routers.auth.UdemyClient")
    def test_email_login_api_disabled_in_server_mode(
        self, mock_client_class, mock_settings
    ):
        mock_settings.DEPLOYMENT_ENV = "server"
        response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cookie Login" in data["message"]
        mock_client_class.assert_not_called()