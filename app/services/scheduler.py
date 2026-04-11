"""Background scheduler for automated enrollment runs."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Dict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from sqlalchemy import update
from loguru import logger

from app.models.database import SessionLocal, User, UserSettings, EnrollmentRun
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
            # Poll for pending runs every 10 seconds
            self.scheduler.add_job(self.poll_pending_runs, "interval", seconds=10)
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
                if EnrollmentManager.get_active_run(db, user.id):
                    continue

                # Check last run time
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
                    asyncio.create_task(self.create_pending_run_for_user(user.id))

        except Exception as e:
            logger.exception("Error in check_and_trigger_runs")
        finally:
            db.close()

    async def create_pending_run_for_user(self, user_id: int):
        """Create a pending run for a specific user to be picked up by the poller."""
        db: Session = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user or not user.udemy_cookies:
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

            run = EnrollmentRun(
                user_id=user.id,
                status="pending",
                currency=user.currency or "usd",
                progress_data={
                    "settings": settings_dict
                }
            )
            db.add(run)
            db.commit()
        except Exception as e:
            logger.exception(f"Failed to create pending run for user {user_id}")
        finally:
            db.close()

    async def poll_pending_runs(self):
        """Poll database for pending runs and execute them."""
        db: Session = SessionLocal()
        try:
            pending_runs = db.query(EnrollmentRun).filter(EnrollmentRun.status == "pending").all()
            for run in pending_runs:
                # Atomic acquire
                stmt = (
                    update(EnrollmentRun)
                    .where(EnrollmentRun.id == run.id, EnrollmentRun.status == "pending")
                    .values(status="scraping")
                )
                result = db.execute(stmt)
                db.commit()
                
                if result.rowcount == 1:
                    logger.info(f"Acquired lock for run {run.id}, starting background task.")
                    asyncio.create_task(self._execute_run(run.id, run.user_id, run.progress_data.get("settings", {})))
        except Exception as e:
            logger.exception("Error polling pending runs")
        finally:
            db.close()

    async def _execute_run(self, run_id: int, user_id: int, settings_dict: dict):
        """Restore session and execute enrollment run."""
        db: Session = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user or not user.udemy_cookies:
                run = db.get(EnrollmentRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = "User or cookies not found"
                    db.commit()
                return

            client = UdemyClient(proxy=settings_dict.get("proxy_url"))
            client.cookie_dict = user.udemy_cookies
            try:
                await client.get_session_info()
            except Exception as e:
                logger.error(f"Failed to restore session for run {run_id}: {e}")
                run = db.get(EnrollmentRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = f"Failed to restore session: {e}"
                    db.commit()
                return

            manager = EnrollmentManager(client, settings_dict, db, user_id, close_client=True)
            manager.run_id = run_id
            manager.status = "scraping"  # Update manager status since it starts right into phase 1
            await manager._run_pipeline()

        except Exception as e:
            logger.exception(f"Failed to execute run {run_id}")
        finally:
            db.close()
