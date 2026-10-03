"""Automated recurring background enrollment scheduler worker."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from loguru import logger

from app.models.database import EnrollmentRun, SessionLocal, User, UserSettings
from app.services.enrollment_manager import EnrollmentManager
from app.services.udemy_client import UdemyClient
from config.settings import resolve_user_proxy


class EnrollmentScheduler:
    """Background worker that periodically checks for users due for scheduled enrollment."""

    def __init__(self, check_interval_seconds: int = 60):
        self.check_interval_seconds = check_interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Start the background scheduler task."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())
            logger.info("EnrollmentScheduler background worker started.")

    async def stop(self) -> None:
        """Gracefully stop and join the background scheduler task."""
        if self._task and not self._task.done():
            self._stop_event.set()
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            logger.info("EnrollmentScheduler background worker stopped.")

    @staticmethod
    def restore_user_client(user: User) -> Optional[UdemyClient]:
        """Restore an authenticated UdemyClient from user encrypted cookies."""
        if not user or not user.udemy_cookies:
            return None

        from app.security import decrypt_cookies

        cookies = decrypt_cookies(user.udemy_cookies, user.cookies_salt)
        if not isinstance(cookies, dict):
            return None

        access_token = cookies.get("access_token")
        client_id = cookies.get("client_id")
        dj_session_id = cookies.get("dj_session_id")
        if not (access_token and client_id) and not dj_session_id:
            return None

        proxy = resolve_user_proxy(user.settings.proxy_url if user.settings else None)
        client = UdemyClient(proxy=proxy)
        client.cookie_dict = cookies.copy()
        client.access_token = access_token
        client.client_id = client_id
        client.is_authenticated = True
        return client

    @staticmethod
    def build_user_settings_dict(user_settings: UserSettings) -> dict:
        """Build filtered settings dictionary for enrollment pipeline."""
        from app.services.scraper import SCRAPER_REGISTRY

        merged_sites = dict(UserSettings.default_sites())
        user_sites = user_settings.sites or {}
        if isinstance(user_sites, dict):
            for k, v in user_sites.items():
                if k in merged_sites:
                    merged_sites[k] = bool(v)

        enabled_sites = [k for k, v in merged_sites.items() if v and k in SCRAPER_REGISTRY]
        return {
            "sites": {site: True for site in enabled_sites},
            "languages": user_settings.languages or UserSettings.default_languages(),
            "categories": user_settings.categories or UserSettings.default_categories(),
            "instructor_exclude": user_settings.instructor_exclude or [],
            "title_exclude": user_settings.title_exclude or [],
            "min_rating": float(user_settings.min_rating or 0.0),
            "course_update_threshold_months": int(user_settings.course_update_threshold_months or 24),
            "save_txt": bool(user_settings.save_txt),
            "discounted_only": bool(user_settings.discounted_only),
            "proxy_url": user_settings.proxy_url,
        }

    async def check_and_trigger_due_runs(self) -> int:
        """Inspect all users with active schedule intervals and launch due runs.

        Returns the number of runs launched.
        """
        launched_count = 0
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        with SessionLocal() as db:
            try:
                candidates = (
                    db.query(UserSettings)
                    .filter(UserSettings.schedule_interval_hours > 0)
                    .all()
                )
            except Exception as e:
                logger.warning(f"Scheduler query failed: {e}")
                return 0

            for settings in candidates:
                interval_hours = settings.schedule_interval_hours
                if interval_hours <= 0:
                    continue

                last_run = settings.last_scheduled_run
                if last_run is not None:
                    elapsed = now_utc - last_run
                    if elapsed < timedelta(hours=interval_hours):
                        continue

                user = db.query(User).filter_by(id=settings.user_id).first()
                if not user:
                    continue

                active = (
                    db.query(EnrollmentRun)
                    .filter(
                        EnrollmentRun.user_id == user.id,
                        EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]),
                    )
                    .first()
                )
                if active:
                    logger.debug(f"User {user.id} has active run #{active.id}; skipping scheduled trigger.")
                    continue

                client = self.restore_user_client(user)
                if not client:
                    logger.debug(f"User {user.id} has no valid Udemy credentials; skipping scheduled trigger.")
                    continue

                settings_dict = self.build_user_settings_dict(settings)
                try:
                    run_id = await EnrollmentManager.start_run(user.id, client, settings_dict)
                    settings.last_scheduled_run = now_utc
                    db.commit()
                    launched_count += 1
                    logger.info(f"Triggered scheduled enrollment run #{run_id} for user {user.id} (interval: {interval_hours}h)")
                except Exception as e:
                    logger.warning(f"Failed to start scheduled run for user {user.id}: {e}")

        return launched_count

    async def _run_loop(self) -> None:
        """Main periodic polling loop."""
        while not self._stop_event.is_set():
            try:
                await self.check_and_trigger_due_runs()
            except Exception as e:
                logger.warning(f"Error during scheduler check: {e}")

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
