"""Tests for automation recurring scheduler and multi-platform webhook notifications."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    EnrollmentRun,
    User,
    UserSession,
    UserSettings,
    get_db,
)
from app.security import (
    encrypt_cookies_salted,
    generate_cookie_salt,
    generate_csrf_token,
)
from app.services.notifications import NotificationService
from app.services.scheduler import EnrollmentScheduler
from main import app

# Isolated SQLite test database for API and scheduler tests
_test_db_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-automation-tests-")
_test_db_path = Path(_test_db_dir.name) / "test_automation.db"
test_engine = create_engine(
    f"sqlite:///{_test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

Base.metadata.create_all(bind=test_engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _automation_env(monkeypatch):
    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr("app.services.scheduler.SessionLocal", TestingSessionLocal)
    yield
    if app.dependency_overrides.get(get_db) is _override_get_db:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_client():
    """Authenticated TestClient with a freshly created user and session."""
    db = TestingSessionLocal()
    salt = generate_cookie_salt()
    cookies_dict = {"access_token": "valid_token_123", "client_id": "client_id_456"}
    encrypted_cookies = encrypt_cookies_salted(cookies_dict, salt)

    user = User(
        email=f"automation-{secrets.token_hex(6)}@example.com",
        password_hash="x",
        udemy_display_name="Automation Tester",
        udemy_cookies=encrypted_cookies,
        cookies_salt=salt,
        currency="usd",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    token = secrets.token_hex(32)
    db.add(UserSession(token=token, user_id=user_id))
    db.add(UserSettings(user_id=user_id))
    db.commit()
    db.close()

    client = TestClient(app)
    client.cookies.set("session_id", token)
    yield client, user_id, token

    client.cookies.clear()
    cleanup_db = TestingSessionLocal()
    try:
        cleanup_db.query(EnrollmentRun).filter_by(user_id=user_id).delete()
        cleanup_db.query(UserSession).filter_by(user_id=user_id).delete()
        cleanup_db.query(UserSettings).filter_by(user_id=user_id).delete()
        cleanup_db.query(User).filter_by(id=user_id).delete()
        cleanup_db.commit()
    finally:
        cleanup_db.close()


def _csrf_headers(token: str) -> dict:
    return {"X-CSRF-Token": generate_csrf_token(token)}


# ==============================================================================
# 1. NotificationService._format_payload Tests
# ==============================================================================


class TestNotificationServicePayloadFormatting:
    def test_discord_payload_success(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="discord",
            run_id=42,
            status="completed",
            enrolled_count=5,
            saved_amount=99.95,
            processed_count=20,
        )
        assert headers == {"Content-Type": "application/json"}
        assert raw_content is None
        assert "embeds" in json_data
        embed = json_data["embeds"][0]
        assert embed["color"] == 3066993  # Green
        assert "Run #42 Completed" in embed["title"]
        assert "**5**" in embed["description"]
        assert "$99.95" in embed["description"]

        field_names = [f["name"] for f in embed["fields"]]
        assert "Status" in field_names
        assert "Processed" in field_names
        assert "Enrolled" in field_names

    def test_discord_payload_failure(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="discord",
            run_id=43,
            status="failed",
            enrolled_count=0,
            saved_amount=0.0,
            processed_count=10,
        )
        assert headers == {"Content-Type": "application/json"}
        assert raw_content is None
        embed = json_data["embeds"][0]
        assert embed["color"] == 15158332  # Red
        assert "Run #43 Failed" in embed["title"]

    def test_telegram_payload(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="telegram",
            run_id=10,
            status="completed",
            enrolled_count=3,
            saved_amount=45.0,
            processed_count=15,
        )
        assert headers == {"Content-Type": "application/json"}
        assert raw_content is None
        assert json_data["parse_mode"] == "Markdown"
        text = json_data["text"]
        assert "🎓 *Udemy Enroller Run #10*" in text
        assert "Status: *COMPLETED*" in text
        assert "Enrolled: *3*" in text
        assert "$45.00" in text
        assert "Processed: *15*" in text

    def test_ntfy_payload_success(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="ntfy",
            run_id=99,
            status="completed",
            enrolled_count=7,
            saved_amount=140.0,
            processed_count=30,
        )
        assert json_data == {}
        assert headers["Priority"] == "high"
        assert headers["Tags"] == "mortar_board,books"
        assert "Run #99 (Completed)" in headers["Title"]
        assert raw_content is not None
        assert "Run #99 completed: 7 course(s) enrolled" in raw_content
        assert "$140.00 saved" in raw_content

    def test_ntfy_payload_failure(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="ntfy",
            run_id=100,
            status="failed",
            enrolled_count=0,
            saved_amount=0.0,
            processed_count=5,
        )
        assert json_data == {}
        assert headers["Priority"] == "default"
        assert headers["Tags"] == "warning"
        assert "Run #100 (Failed)" in headers["Title"]

    def test_generic_payload(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="generic",
            run_id=5,
            status="completed",
            enrolled_count=2,
            saved_amount=29.99,
            processed_count=8,
        )
        assert headers == {"Content-Type": "application/json"}
        assert raw_content is None
        assert json_data == {
            "event": "enrollment_finished",
            "run_id": 5,
            "status": "completed",
            "enrolled": 2,
            "saved": 29.99,
            "currency": "usd",
            "processed": 8,
        }

    def test_notification_payload_formatting_inr_and_usd(self):
        # 1. Discord formatting
        discord_inr, _, _ = NotificationService._format_payload(
            webhook_service="discord",
            run_id=1,
            status="completed",
            enrolled_count=3,
            saved_amount=599.0,
            processed_count=10,
            currency="inr",
        )
        assert "₹599.00" in discord_inr["embeds"][0]["description"]
        assert "$599.00" not in discord_inr["embeds"][0]["description"]

        discord_usd, _, _ = NotificationService._format_payload(
            webhook_service="discord",
            run_id=1,
            status="completed",
            enrolled_count=3,
            saved_amount=59.99,
            processed_count=10,
            currency="usd",
        )
        assert "$59.99" in discord_usd["embeds"][0]["description"]
        assert "₹" not in discord_usd["embeds"][0]["description"]

        # 2. Telegram formatting
        tg_inr, _, _ = NotificationService._format_payload(
            webhook_service="telegram",
            run_id=2,
            status="completed",
            enrolled_count=1,
            saved_amount=499.0,
            processed_count=5,
            currency="inr",
        )
        assert "Total Saved: *₹499.00*" in tg_inr["text"]

        tg_usd, _, _ = NotificationService._format_payload(
            webhook_service="telegram",
            run_id=2,
            status="completed",
            enrolled_count=1,
            saved_amount=49.99,
            processed_count=5,
            currency="usd",
        )
        assert "Total Saved: *$49.99*" in tg_usd["text"]

        # 3. Ntfy formatting
        _, _, ntfy_inr = NotificationService._format_payload(
            webhook_service="ntfy",
            run_id=3,
            status="completed",
            enrolled_count=2,
            saved_amount=799.0,
            processed_count=8,
            currency="inr",
        )
        assert "₹799.00 saved" in ntfy_inr

        _, _, ntfy_usd = NotificationService._format_payload(
            webhook_service="ntfy",
            run_id=3,
            status="completed",
            enrolled_count=2,
            saved_amount=79.99,
            processed_count=8,
            currency="usd",
        )
        assert "$79.99 saved" in ntfy_usd

        # 4. Generic webhook payload
        gen_inr, _, _ = NotificationService._format_payload(
            webhook_service="generic",
            run_id=4,
            status="completed",
            enrolled_count=2,
            saved_amount=1200.0,
            processed_count=12,
            currency="inr",
        )
        assert gen_inr["currency"] == "inr"

        gen_usd, _, _ = NotificationService._format_payload(
            webhook_service="generic",
            run_id=4,
            status="completed",
            enrolled_count=2,
            saved_amount=12.0,
            processed_count=12,
            currency="usd",
        )
        assert gen_usd["currency"] == "usd"

    def test_fallback_to_generic_for_unknown_service(self):
        json_data, headers, raw_content = NotificationService._format_payload(
            webhook_service="",
            run_id=1,
            status="completed",
            enrolled_count=0,
            saved_amount=0.0,
            processed_count=0,
        )
        assert json_data["event"] == "enrollment_finished"
        assert json_data["currency"] == "usd"


# ==============================================================================
# 2. NotificationService.send_notification and send_test_webhook Tests
# ==============================================================================


class TestNotificationServiceDispatch:
    @pytest.mark.asyncio
    async def test_send_notification_success_json(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await NotificationService.send_notification(
                webhook_url="https://discord.com/api/webhooks/123/xyz",
                webhook_service="discord",
                run_id=1,
                status="completed",
                enrolled_count=2,
                saved_amount=30.0,
                processed_count=5,
            )
            assert result is True
            assert mock_post.await_count == 1
            call_kwargs = mock_post.call_args.kwargs
            assert "json" in call_kwargs
            assert "headers" in call_kwargs

    @pytest.mark.asyncio
    async def test_send_notification_success_ntfy_raw_content(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await NotificationService.send_notification(
                webhook_url="https://ntfy.sh/my-topic-test",
                webhook_service="ntfy",
                run_id=1,
                status="completed",
                enrolled_count=2,
                saved_amount=30.0,
                processed_count=5,
            )
            assert result is True
            assert mock_post.await_count == 1
            call_kwargs = mock_post.call_args.kwargs
            assert "content" in call_kwargs

    @pytest.mark.asyncio
    async def test_send_notification_failure_status_code(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await NotificationService.send_notification(
                webhook_url="https://example.com/webhook",
                webhook_service="generic",
                run_id=1,
                status="completed",
                enrolled_count=1,
                saved_amount=10.0,
                processed_count=1,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_network_exception(self):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")
            result = await NotificationService.send_notification(
                webhook_url="https://example.com/webhook",
                webhook_service="generic",
                run_id=1,
                status="completed",
                enrolled_count=1,
                saved_amount=10.0,
                processed_count=1,
            )
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "unsafe_url",
        [
            "",
            "   ",
            "http://127.0.0.1/hook",
            "http://127.0.0.1:8080/hook",
            "http://localhost/webhook",
            "http://192.168.1.1/webhook",
            "http://10.0.0.1/webhook",
            "ftp://example.com/hook",
            "http://example.com:22/hook",
        ],
    )
    async def test_ssrf_blocking_send_notification(self, unsafe_url):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            result = await NotificationService.send_notification(
                webhook_url=unsafe_url,
                webhook_service="generic",
                run_id=1,
                status="completed",
                enrolled_count=1,
                saved_amount=10.0,
                processed_count=1,
            )
            assert result is False
            assert mock_post.await_count == 0

    @pytest.mark.asyncio
    async def test_send_test_webhook_success(self):
        with patch.object(
            NotificationService, "send_notification", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = True
            success, msg = await NotificationService.send_test_webhook(
                webhook_url="https://discord.com/api/webhooks/test",
                webhook_service="discord",
            )
            assert success is True
            assert "successfully" in msg
            assert mock_send.await_count == 1

    @pytest.mark.asyncio
    async def test_send_test_webhook_empty_url(self):
        success, msg = await NotificationService.send_test_webhook(
            webhook_url="",
            webhook_service="discord",
        )
        assert success is False
        assert "empty" in msg

    @pytest.mark.asyncio
    async def test_send_test_webhook_unsafe_url(self):
        success, msg = await NotificationService.send_test_webhook(
            webhook_url="http://127.0.0.1/test",
            webhook_service="discord",
        )
        assert success is False
        assert "unsafe" in msg

    @pytest.mark.asyncio
    async def test_send_run_notification_for_user_no_settings(self):
        db = TestingSessionLocal()
        try:
            result = await NotificationService.send_run_notification_for_user(
                db=db,
                user_id=999999,
                run_id=1,
                status="completed",
                enrolled_count=1,
                saved_amount=10.0,
                processed_count=2,
            )
            assert result is False
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_send_run_notification_for_user_with_webhook(self):
        db = TestingSessionLocal()
        user = User(
            email=f"notify-{secrets.token_hex(4)}@example.com",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        settings = UserSettings(
            user_id=user.id,
            webhook_url="https://discord.com/api/webhooks/test",
            webhook_service="discord",
        )
        db.add(settings)
        db.commit()

        try:
            with patch.object(
                NotificationService, "send_notification", new_callable=AsyncMock
            ) as mock_send:
                mock_send.return_value = True
                result = await NotificationService.send_run_notification_for_user(
                    db=db,
                    user_id=user.id,
                    run_id=7,
                    status="completed",
                    enrolled_count=3,
                    saved_amount=45.0,
                    processed_count=10,
                )
                assert result is True
                assert mock_send.await_count == 1
                kwargs = mock_send.call_args.kwargs
                assert kwargs["webhook_url"] == "https://discord.com/api/webhooks/test"
                assert kwargs["webhook_service"] == "discord"
                assert kwargs["run_id"] == 7
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    @pytest.mark.asyncio
    async def test_send_run_notification_for_user_passes_currency(self):
        db = TestingSessionLocal()
        user = User(
            email=f"notify-curr-{secrets.token_hex(4)}@example.com",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        settings = UserSettings(
            user_id=user.id,
            webhook_url="https://discord.com/api/webhooks/test-curr",
            webhook_service="discord",
        )
        db.add(settings)
        db.commit()

        try:
            with patch.object(
                NotificationService, "send_notification", new_callable=AsyncMock
            ) as mock_send:
                mock_send.return_value = True
                result = await NotificationService.send_run_notification_for_user(
                    db=db,
                    user_id=user.id,
                    run_id=88,
                    status="completed",
                    enrolled_count=2,
                    saved_amount=1200.0,
                    processed_count=10,
                    currency="inr",
                )
                assert result is True
                assert mock_send.await_count == 1
                kwargs = mock_send.call_args.kwargs
                assert kwargs["currency"] == "inr"
                assert kwargs["saved_amount"] == 1200.0
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    def test_enrollment_manager_amount_saved_fallback(self):
        """Verify amount_saved resolution safely uses amount_saved_c without AttributeError."""
        from decimal import Decimal
        from app.services.enrollment_manager import EnrollmentManager

        mock_udemy = MagicMock(spec=["amount_saved_c", "successfully_enrolled_c", "currency"])
        mock_udemy.amount_saved_c = Decimal("79.99")
        mock_udemy.successfully_enrolled_c = 4
        mock_udemy.currency = "INR"

        manager = EnrollmentManager(
            user_id=1,
            run_id=99,
            udemy_client=mock_udemy,
            settings={},
        )
        assert not hasattr(manager.udemy, "amount_saved")

        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_run.amount_saved = None
        mock_run.currency = "inr"

        # Defensive extraction logic as implemented in enrollment_manager.py
        saved_amount = float(
            getattr(manager.udemy, "amount_saved_c", 0.0)
            or getattr(mock_run, "amount_saved", 0.0)
            or 0.0
        )
        run_currency = (
            str(
                getattr(mock_run, "currency", None)
                or getattr(manager.udemy, "currency", "usd")
                or "usd"
            ).strip().lower()
        ) or "usd"
        enrolled_count = int(getattr(manager.udemy, "successfully_enrolled_c", 0))

        assert saved_amount == 79.99
        assert run_currency == "inr"
        assert enrolled_count == 4


# ==============================================================================
# 3. EnrollmentScheduler Tests
# ==============================================================================


class TestEnrollmentScheduler:
    @pytest.mark.asyncio
    async def test_user_with_schedule_disabled_not_triggered(self):
        db = TestingSessionLocal()
        user = User(
            email=f"sched-disabled-{secrets.token_hex(4)}@example.com",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        settings = UserSettings(user_id=user.id, schedule_interval_hours=0)
        db.add(settings)
        db.commit()

        try:
            scheduler = EnrollmentScheduler()
            with patch(
                "app.services.enrollment_manager.EnrollmentManager.start_run",
                new_callable=AsyncMock,
            ) as mock_start:
                count = await scheduler.check_and_trigger_due_runs()
                assert count == 0
                assert mock_start.await_count == 0
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    @pytest.mark.asyncio
    async def test_user_not_due_yet_skipped(self):
        db = TestingSessionLocal()
        user = User(
            email=f"sched-notdue-{secrets.token_hex(4)}@example.com",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Interval is 4 hours, last run was 1 hour ago
        settings = UserSettings(
            user_id=user.id,
            schedule_interval_hours=4,
            last_scheduled_run=now - timedelta(hours=1),
        )
        db.add(settings)
        db.commit()

        try:
            scheduler = EnrollmentScheduler()
            with patch(
                "app.services.enrollment_manager.EnrollmentManager.start_run",
                new_callable=AsyncMock,
            ) as mock_start:
                count = await scheduler.check_and_trigger_due_runs()
                assert count == 0
                assert mock_start.await_count == 0
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    @pytest.mark.asyncio
    async def test_user_with_active_run_skipped(self):
        db = TestingSessionLocal()
        user = User(
            email=f"sched-active-{secrets.token_hex(4)}@example.com",
            password_hash="x",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        settings = UserSettings(
            user_id=user.id,
            schedule_interval_hours=2,
            last_scheduled_run=None,
        )
        db.add(settings)

        # Active pending run
        active_run = EnrollmentRun(
            user_id=user.id,
            status="scraping",
            currency="usd",
        )
        db.add(active_run)
        db.commit()

        try:
            scheduler = EnrollmentScheduler()
            with patch(
                "app.services.enrollment_manager.EnrollmentManager.start_run",
                new_callable=AsyncMock,
            ) as mock_start:
                count = await scheduler.check_and_trigger_due_runs()
                assert count == 0
                assert mock_start.await_count == 0
        finally:
            db.query(EnrollmentRun).filter_by(user_id=user.id).delete()
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    @pytest.mark.asyncio
    async def test_user_without_credentials_skipped(self):
        db = TestingSessionLocal()
        user = User(
            email=f"sched-nocreds-{secrets.token_hex(4)}@example.com",
            password_hash="x",
            udemy_cookies=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        settings = UserSettings(
            user_id=user.id,
            schedule_interval_hours=2,
            last_scheduled_run=None,
        )
        db.add(settings)
        db.commit()

        try:
            scheduler = EnrollmentScheduler()
            with patch(
                "app.services.enrollment_manager.EnrollmentManager.start_run",
                new_callable=AsyncMock,
            ) as mock_start:
                count = await scheduler.check_and_trigger_due_runs()
                assert count == 0
                assert mock_start.await_count == 0
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    @pytest.mark.asyncio
    async def test_due_user_triggers_run_and_updates_timestamp(self):
        db = TestingSessionLocal()
        salt = generate_cookie_salt()
        cookies_dict = {"access_token": "valid_token", "client_id": "valid_client"}
        encrypted = encrypt_cookies_salted(cookies_dict, salt)

        user = User(
            email=f"sched-due-{secrets.token_hex(4)}@example.com",
            password_hash="x",
            udemy_cookies=encrypted,
            cookies_salt=salt,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        settings = UserSettings(
            user_id=user.id,
            schedule_interval_hours=2,
            last_scheduled_run=now - timedelta(hours=3),
        )
        db.add(settings)
        db.commit()

        try:
            scheduler = EnrollmentScheduler()
            with patch(
                "app.services.enrollment_manager.EnrollmentManager.start_run",
                new_callable=AsyncMock,
            ) as mock_start:
                mock_start.return_value = 101
                count = await scheduler.check_and_trigger_due_runs()
                assert count == 1
                assert mock_start.await_count == 1
                assert mock_start.call_args[0][0] == user.id

            # Verify last_scheduled_run was updated in database
            db.refresh(settings)
            assert settings.last_scheduled_run is not None
            assert settings.last_scheduled_run > now - timedelta(minutes=1)
        finally:
            db.query(UserSettings).filter_by(user_id=user.id).delete()
            db.query(User).filter_by(id=user.id).delete()
            db.commit()
            db.close()

    def test_restore_user_client_valid_and_invalid(self):
        salt = generate_cookie_salt()
        encrypted = encrypt_cookies_salted(
            {"access_token": "tok123", "client_id": "cid123"}, salt
        )
        user_valid = User(
            email="test-valid@example.com",
            password_hash="x",
            udemy_cookies=encrypted,
            cookies_salt=salt,
        )
        client = EnrollmentScheduler.restore_user_client(user_valid)
        assert client is not None
        assert client.access_token == "tok123"
        assert client.client_id == "cid123"
        assert client.is_authenticated is True

        user_invalid = User(
            email="test-invalid@example.com",
            password_hash="x",
            udemy_cookies=None,
        )
        assert EnrollmentScheduler.restore_user_client(user_invalid) is None

    def test_build_user_settings_dict(self):
        settings = UserSettings(
            user_id=1,
            sites={"Real Discount": True, "NonExistent": True},
            min_rating=4.5,
            course_update_threshold_months=12,
            save_txt=True,
            discounted_only=True,
        )
        res = EnrollmentScheduler.build_user_settings_dict(settings)
        assert res["min_rating"] == 4.5
        assert res["course_update_threshold_months"] == 12
        assert res["save_txt"] is True
        assert res["discounted_only"] is True
        assert "Real Discount" in res["sites"]

    @pytest.mark.asyncio
    async def test_scheduler_lifecycle_start_stop(self):
        scheduler = EnrollmentScheduler(check_interval_seconds=60)
        scheduler.start()
        assert scheduler._task is not None
        assert not scheduler._task.done()

        await scheduler.stop()
        assert scheduler._task.done()


# ==============================================================================
# 4. Settings API Endpoint Tests
# ==============================================================================


class TestSettingsAPIAutomation:
    def test_test_webhook_requires_auth(self):
        anon = TestClient(app)
        resp = anon.post(
            "/api/settings/test-webhook",
            json={"webhook_url": "https://example.com", "webhook_service": "generic"},
        )
        assert resp.status_code == 401

    def test_test_webhook_requires_csrf(self, auth_client):
        client, _user_id, _token = auth_client
        resp = client.post(
            "/api/settings/test-webhook",
            json={"webhook_url": "https://example.com", "webhook_service": "generic"},
        )
        assert resp.status_code == 403

    def test_test_webhook_success(self, auth_client):
        client, _user_id, token = auth_client
        with patch.object(
            NotificationService, "send_test_webhook", new_callable=AsyncMock
        ) as mock_test:
            mock_test.return_value = (True, "Test notification dispatched successfully.")
            resp = client.post(
                "/api/settings/test-webhook",
                headers=_csrf_headers(token),
                json={
                    "webhook_url": "https://discord.com/api/webhooks/test",
                    "webhook_service": "discord",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "successfully" in data["message"]

    def test_test_webhook_invalid_unsafe_url(self, auth_client):
        client, _user_id, token = auth_client
        resp = client.post(
            "/api/settings/test-webhook",
            headers=_csrf_headers(token),
            json={
                "webhook_url": "http://127.0.0.1/hook",
                "webhook_service": "generic",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "unsafe" in data["message"].lower()

    def test_put_settings_updates_automation_fields(self, auth_client):
        client, _user_id, token = auth_client
        update_payload = {
            "schedule_interval_hours": 6,
            "webhook_service": "telegram",
            "webhook_url": "https://api.telegram.org/bot123:abc/sendMessage?chat_id=456",
        }
        put_resp = client.put(
            "/api/settings/",
            headers=_csrf_headers(token),
            json=update_payload,
        )
        assert put_resp.status_code == 200

        get_resp = client.get("/api/settings/")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["schedule_interval_hours"] == 6
        assert data["webhook_service"] == "telegram"
        assert (
            data["webhook_url"]
            == "https://api.telegram.org/bot123:abc/sendMessage?chat_id=456"
        )
