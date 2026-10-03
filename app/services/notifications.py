"""Multi-platform user notification service (Discord, Telegram, Ntfy, Generic)."""

from typing import Optional, Tuple
import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.models.database import UserSettings
from app.services.http_client import AsyncHTTPClient


class NotificationService:
    """Dispatches event and run completion notifications to user-configured webhooks."""

    @staticmethod
    def _format_payload(
        webhook_service: str,
        run_id: int,
        status: str,
        enrolled_count: int,
        saved_amount: float,
        processed_count: int,
    ) -> Tuple[dict, dict, Optional[str]]:
        """Format payload and headers based on target service.

        Returns (json_data, headers, raw_content).
        """
        service = (webhook_service or "generic").lower().strip()
        is_success = status.lower() == "completed"

        if service == "discord":
            embed_color = 3066993 if is_success else 15158332  # Green or Red
            payload = {
                "embeds": [
                    {
                        "title": f"Udemy Enroller: Run #{run_id} {status.title()}",
                        "description": (
                            f"Successfully enrolled in **{enrolled_count}** course(s)!\n"
                            f"Total Saved: **${saved_amount:.2f}**"
                        ),
                        "color": embed_color,
                        "fields": [
                            {"name": "Status", "value": status.upper(), "inline": True},
                            {"name": "Processed", "value": str(processed_count), "inline": True},
                            {"name": "Enrolled", "value": str(enrolled_count), "inline": True},
                        ],
                        "footer": {"text": "Udemy Enroller Automation Platform"},
                    }
                ]
            }
            return payload, {"Content-Type": "application/json"}, None

        if service == "telegram":
            text = (
                f"🎓 *Udemy Enroller Run #{run_id}*\n\n"
                f"Status: *{status.upper()}*\n"
                f"Enrolled: *{enrolled_count}*\n"
                f"Total Saved: *${saved_amount:.2f}*\n"
                f"Processed: *{processed_count}*"
            )
            return {"text": text, "parse_mode": "Markdown"}, {"Content-Type": "application/json"}, None

        if service == "ntfy":
            headers = {
                "Title": f"Udemy Enroller: Run #{run_id} ({status.title()})",
                "Priority": "high" if is_success else "default",
                "Tags": "mortar_board,books" if is_success else "warning",
            }
            body = (
                f"Run #{run_id} {status}: {enrolled_count} course(s) enrolled, "
                f"${saved_amount:.2f} saved ({processed_count} processed)."
            )
            return {}, headers, body

        # Generic webhook JSON payload
        generic_payload = {
            "event": "enrollment_finished",
            "run_id": run_id,
            "status": status,
            "enrolled": enrolled_count,
            "saved": round(saved_amount, 2),
            "processed": processed_count,
        }
        return generic_payload, {"Content-Type": "application/json"}, None

    @classmethod
    async def send_notification(
        cls,
        webhook_url: str,
        webhook_service: str,
        run_id: int,
        status: str,
        enrolled_count: int,
        saved_amount: float,
        processed_count: int,
    ) -> bool:
        """Send run completion notification to user webhook."""
        if not webhook_url or not webhook_url.strip():
            return False

        webhook_url = webhook_url.strip()
        if not AsyncHTTPClient._is_safe_url(webhook_url):
            logger.warning(f"Blocked unsafe webhook URL: {webhook_url}")
            return False

        json_data, headers, raw_content = cls._format_payload(
            webhook_service=webhook_service,
            run_id=run_id,
            status=status,
            enrolled_count=enrolled_count,
            saved_amount=saved_amount,
            processed_count=processed_count,
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if raw_content is not None:
                    resp = await client.post(webhook_url, content=raw_content.encode("utf-8"), headers=headers)
                else:
                    resp = await client.post(webhook_url, json=json_data, headers=headers)
                if resp.status_code in (200, 201, 204):
                    logger.info(f"Dispatched webhook notification to {webhook_service} for run #{run_id}")
                    return True
                logger.warning(f"Webhook dispatch failed with HTTP {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.warning(f"Error dispatching webhook notification: {e}")
            return False

    @classmethod
    async def send_test_webhook(cls, webhook_url: str, webhook_service: str) -> Tuple[bool, str]:
        """Send a test notification to verify webhook configuration."""
        if not webhook_url or not webhook_url.strip():
            return False, "Webhook URL cannot be empty."

        webhook_url = webhook_url.strip()
        if not AsyncHTTPClient._is_safe_url(webhook_url):
            return False, "Invalid or unsafe webhook URL format."

        success = await cls.send_notification(
            webhook_url=webhook_url,
            webhook_service=webhook_service,
            run_id=0,
            status="test",
            enrolled_count=5,
            saved_amount=99.99,
            processed_count=25,
        )
        if success:
            return True, "Test notification dispatched successfully."
        return False, "Failed to deliver webhook notification. Check URL and server logs."

    @classmethod
    async def send_run_notification_for_user(
        cls,
        db: Session,
        user_id: int,
        run_id: int,
        status: str,
        enrolled_count: int,
        saved_amount: float,
        processed_count: int,
    ) -> bool:
        """Query user settings and dispatch notification if webhook is configured."""
        try:
            settings = db.query(UserSettings).filter_by(user_id=user_id).first()
            if not settings or not settings.webhook_url:
                return False
            return await cls.send_notification(
                webhook_url=settings.webhook_url,
                webhook_service=settings.webhook_service or "generic",
                run_id=run_id,
                status=status,
                enrolled_count=enrolled_count,
                saved_amount=saved_amount,
                processed_count=processed_count,
            )
        except Exception as e:
            logger.warning(f"Failed to lookup webhook settings for user {user_id}: {e}")
            return False
