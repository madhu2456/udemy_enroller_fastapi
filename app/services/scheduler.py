"""Background scheduler for automated enrollment runs."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import SessionLocal, User, UserSettings
from app.services.udemy_client import UdemyClient
from app.services.enrollment_manager import EnrollmentManager


class EnrollmentScheduler:
    """Manages periodic enrollment runs for users with enabled schedules."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    @staticmethod
    def _utcnow_naive() -> datetime:
        """Return current UTC timestamp without tzinfo for DB DateTime columns."""
        return datetime.now(UTC).replace(tzinfo=None)

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            # Check for scheduled runs every 30 minutes
            self.scheduler.add_job(self.check_and_trigger_runs, "interval", minutes=30)
            logger.info("Enrollment Scheduler started")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Enrollment Scheduler stopped")

    async def check_and_trigger_runs(self):
        """Find users with active schedules and trigger runs if due."""
        logger.info("Checking for scheduled enrollment runs...")
        db: Session = SessionLocal()
        try:
            # Join User and UserSettings to find eligible users
            eligible_users = db.query(User).join(UserSettings).filter(
                UserSettings.schedule_interval > 0,
                User.udemy_cookies != None
            ).all()

            for user in eligible_users:
                # Check if already running
                if EnrollmentManager.get_active_run(user.id):
                    continue

                # Check last run time
                from app.models.database import EnrollmentRun
                last_run = db.query(EnrollmentRun).filter(
                    EnrollmentRun.user_id == user.id
                ).order_by(EnrollmentRun.started_at.desc()).first()

                should_run = False
                if not last_run:
                    should_run = True
                else:
                    interval_delta = timedelta(hours=user.settings.schedule_interval)
                    if self._utcnow_naive() >= last_run.started_at + interval_delta:
                        should_run = True

                if should_run:
                    logger.info(f"Triggering scheduled run for user {user.email}")
                    asyncio.create_task(self.run_for_user(user.id))

        except Exception as e:
            logger.exception("Error in check_and_trigger_runs")
        finally:
            db.close()

    async def run_for_user(self, user_id: int):
        """Restore session and start enrollment run for a specific user."""
        db: Session = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user or not user.udemy_cookies:
                return

            client = UdemyClient(proxy=user.settings.proxy_url)
            client.cookie_dict = user.udemy_cookies
            try:
                await client.get_session_info()
            except Exception as e:
                logger.error(f"Failed to restore session for scheduled run (user {user_id}): {e}")
                return

            settings_dict = {
                "sites": user.settings.sites or {},
                "languages": user.settings.languages or {},
                "categories": user.settings.categories or {},
                "instructor_exclude": user.settings.instructor_exclude or [],
                "title_exclude": user.settings.title_exclude or [],
                "min_rating": user.settings.min_rating or 0.0,
                "course_update_threshold_months": user.settings.course_update_threshold_months or 24,
                "discounted_only": user.settings.discounted_only or False,
                "proxy_url": user.settings.proxy_url,
                "enable_headless": user.settings.enable_headless or False,
            }

            manager = EnrollmentManager(client, settings_dict, db, user_id, close_client=True)
            await manager.start()

        except Exception as e:
            logger.exception(f"Failed scheduled run for user {user_id}")
        finally:
            # Note: DB session is closed by EnrollmentManager when pipeline finishes
            # or here if it fails before starting. 
            # Actually EnrollmentManager uses SessionLocal() inside its pipeline.
            db.close()
