"""Enrollment manager - handles the background enrollment pipeline."""

import asyncio
import random
import re
from typing import Optional, Dict

from sqlalchemy.orm import Session
from loguru import logger

from app.core.cache import clear_user_caches, _stats_cache
from app.models.database import (
    EnrollmentRun,
    EnrolledCourse,
    SessionLocal,
    _utcnow_naive,
    User,
)
from app.services.course import Course
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient


class EnrollmentManager:
    """Manages the background enrollment process for a specific run."""

    # Track active tasks to prevent duplicate runs per user
    active_tasks: Dict[int, asyncio.Task] = {}
    locks: Dict[int, asyncio.Lock] = {}

    @classmethod
    def get_lock(cls, user_id: int) -> asyncio.Lock:
        if user_id not in cls.locks:
            cls.locks[user_id] = asyncio.Lock()
        return cls.locks[user_id]

    def __init__(
        self,
        user_id: int,
        run_id: int,
        udemy_client: UdemyClient,
        settings: dict,
        close_client: bool = False,
    ):
        self.user_id = user_id
        self.run_id = run_id
        self.udemy = udemy_client
        self.settings = settings
        self.close_client = close_client

        self.total_courses = 0
        self.processed = 0
        self.status = "pending"
        self.current_course_title = ""
        self.current_course_url = ""
        self.scraper_service: Optional[ScraperService] = None

        # Deployment-aware rate limiting
        from config.settings import get_settings

        self._is_server = get_settings().DEPLOYMENT_ENV == "server"

    @classmethod
    def get_active_run(cls, db: Session, user_id: int) -> Optional[EnrollmentRun]:
        """Find the active run for a user."""
        return (
            db.query(EnrollmentRun)
            .filter(
                EnrollmentRun.user_id == user_id,
                EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]),
            )
            .first()
        )

    @classmethod
    def get_progress_from_run(cls, run: EnrollmentRun) -> dict:
        """Extract progress metrics from a run record."""
        pd = run.progress_data or {}

        scraping_progress = pd.get("scraping_progress", [])
        sources_total = len(scraping_progress)
        sources_completed = sum(1 for s in scraping_progress if s.get("state") == "completed")
        sources_failed = sum(1 for s in scraping_progress if s.get("state") in ("failed", "timed_out"))
        courses_discovered = sum(s.get("courses_found", 0) for s in scraping_progress)
        
        phase = run.status
        if run.status == "enrolling" and (sources_completed + sources_failed) < sources_total:
            phase = "scraping_and_enrolling"

        return {
            "run_id": run.id,
            "status": run.status,
            "phase": phase,
            "sources_total": sources_total,
            "sources_completed": sources_completed,
            "sources_failed": sources_failed,
            "courses_discovered": courses_discovered,
            "last_update_at": None,
            "total_courses": run.total_courses_found,
            "processed": run.total_processed,
            "successfully_enrolled": run.successfully_enrolled,
            "already_enrolled": run.already_enrolled,
            "expired": run.expired,
            "excluded": run.excluded,
            "amount_saved": float(run.amount_saved or 0.0),
            "currency": run.currency or "usd",
            "current_course_title": pd.get("current_course_title"),
            "current_course_url": pd.get("current_course_url"),
            "scraping_progress": scraping_progress,
        }

    @classmethod
    async def start_run(
        cls,
        user_id: int,
        udemy_client: UdemyClient,
        settings: dict,
        close_client: bool = False,
    ) -> int:
        """Create a run and start the background task."""
        lock = cls.get_lock(user_id)
        async with lock:
            logger.warning(f"Creating enrollment run for user {user_id}")
            db = SessionLocal()
            try:
                active = cls.get_active_run(db, user_id)
                if active:
                    raise ValueError("An enrollment run is already active")

                # Create the run record
                run = EnrollmentRun(
                    user_id=user_id, status="pending", currency=udemy_client.currency
                )
                db.add(run)
                db.commit()
                db.refresh(run)

                logger.warning(f"Run {run.id} created. Starting background task.")
                manager = cls(user_id, run.id, udemy_client, settings, close_client)
                task = asyncio.create_task(manager.run_pipeline())
                cls.active_tasks[run.id] = task

                return run.id
            finally:
                db.close()

    async def run_pipeline(self):
        """Main enrollment pipeline: Scrape -> Filter -> Enroll."""
        with logger.contextualize(user_id=self.user_id):
            await self._run_pipeline_impl()

    async def _run_pipeline_impl(self):
        logger.warning(f"Starting enrollment pipeline for run {self.run_id}")
        db = SessionLocal()
        try:
            run = db.get(EnrollmentRun, self.run_id)
            if not run:
                logger.error(f"Run {self.run_id} not found in database.")
                return

            run.status = "scraping"
            db.commit()
            self.status = "scraping"

            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            logger.warning(f"Enabled sites: {enabled_sites}")
            self.scraper_service = ScraperService(
                enabled_sites, proxy=self.settings.get("proxy_url")
            )

            enrolled_slugs: set[str] = set()
            try:
                from sqlalchemy import select
                stmt = (
                    select(EnrolledCourse.slug)
                    .join(EnrollmentRun)
                    .where(
                        EnrollmentRun.user_id == self.user_id,
                        EnrollmentRun.id != self.run_id,
                        EnrolledCourse.status == "already_enrolled",
                        EnrolledCourse.slug.isnot(None),
                    )
                    .distinct()
                )
                for row in db.execute(stmt):
                    enrolled_slugs.add(row[0])
                logger.warning(f"Loaded {len(enrolled_slugs)} already-enrolled courses from DB history.")
            except Exception as e:
                logger.warning(f"Could not load enrolled history from DB: {e}")

            previously_attempted: set[tuple[str, str]] = set()
            try:
                from sqlalchemy import select
                stmt = (
                    select(EnrolledCourse.slug, EnrolledCourse.coupon_code)
                    .join(EnrollmentRun)
                    .where(
                        EnrollmentRun.user_id == self.user_id,
                        EnrollmentRun.id != self.run_id,
                        EnrolledCourse.slug.isnot(None),
                    )
                )
                for row in db.execute(stmt):
                    previously_attempted.add((row[0], row[1] or ""))
                logger.warning(f"Loaded {len(previously_attempted)} previously attempted course+coupon combos.")
            except Exception as e:
                logger.warning(f"Could not load previous attempts: {e}")

            seen_slugs = set()
            from collections import defaultdict
            source_stats = defaultdict(lambda: {"enrolled": 0, "already_enrolled": 0, "expired": 0, "failed": 0, "excluded": 0, "invalid": 0})

            skipped_already_enrolled = 0
            skipped_already_tried = 0
            scrapers_succeeded = 0
            index = 0

            async def process_single_course(course: Course):
                course_delay = random.uniform(2.0, 5.0)
                logger.info(f"[PROCESS] Delaying {course_delay:.1f}s before enrolling {course.title}")
                await asyncio.sleep(course_delay)

                start_time = asyncio.get_event_loop().time()
                logger.info(f"[PROCESS] Calling checkout_single for {course.title}")
                success = await self.udemy.checkout_single(course)
                duration = asyncio.get_event_loop().time() - start_time

                if success:
                    status = "enrolled"
                    self.udemy.successfully_enrolled_c += 1
                    if course.list_price:
                        self.udemy.amount_saved_c += course.list_price
                    logger.info(f"✅ Enrollment Success: {course.title} ({duration:.1f}s)")
                else:
                    err = (course.error or "").lower()
                    if "price mismatch" in err or "expired" in err:
                        status = "expired"
                        self.udemy.expired_c += 1
                        logger.warning(f"⏰ Coupon Expired (checkout): {course.title} — {course.error}")
                    else:
                        status = "failed"
                        logger.warning(f"❌ Enrollment Failed: {course.title} ({duration:.1f}s)")

                return success, status

            async for scraper, state in self.scraper_service.stream_results():
                pd = dict(run.progress_data or {})
                pd["scraping_progress"] = self.scraper_service.get_progress()
                run.progress_data = pd
                db.commit()

                if state == "completed":
                    scrapers_succeeded += 1

                for course in scraper.data:
                    if not course.url:
                        continue

                    if course.url in seen_slugs:
                        continue
                    seen_slugs.add(course.url)

                    if not course.slug and course.url:
                        match = re.search(r"udemy\.com/course/([^/?#]+)", course.url)
                        if match:
                            course.slug = match.group(1)

                    if course.slug and course.slug in enrolled_slugs:
                        skipped_already_enrolled += 1
                        continue

                    coupon = course.coupon_code or ""
                    if course.slug and (course.slug, coupon) in previously_attempted:
                        skipped_already_tried += 1
                        continue

                    if self.status == "scraping":
                        run.status = "enrolling"
                        db.commit()
                        self.status = "enrolling"

                    self.total_courses += 1
                    run.total_courses_found = self.total_courses
                    self.processed = index + 1
                    self.current_course_title = course.title
                    self.current_course_url = course.url or ""

                    logger.info(f"Processing {index + 1}: {course.title}")

                    course_status = "failed"
                    error_msg = None
                    saved_already = False

                    try:
                        if await self.udemy.is_already_enrolled(course, enrolled_slugs):
                            self.udemy.already_enrolled_c += 1
                            course_status = "already_enrolled"
                            logger.debug(f"  Status: Already enrolled (DB cache: {course.slug})")
                        else:
                            logger.info(f"[PIPELINE] Fetching course_id for {course.title}")
                            await self.udemy.get_course_id(course)
                            if not course.is_valid:
                                error_msg = course.error or ""
                                if "403" in error_msg:
                                    course_status = "failed"
                                else:
                                    self.udemy.excluded_c += 1
                                    course_status = "invalid"
                            elif await self.udemy.check_already_enrolled_live(course):
                                self.udemy.already_enrolled_c += 1
                                course_status = "already_enrolled"
                            else:
                                await self.udemy.populate_course_metadata(course)
                                self.udemy.is_course_excluded(course, self.settings)
                                if course.is_excluded:
                                    self.udemy.excluded_c += 1
                                    course_status = "excluded"
                                    error_msg = course.error or "Filter match"
                                else:
                                    logger.info(f"[PIPELINE] Checking coupon for {course.title}")
                                    await self.udemy.check_course(course)
                                    if not course.is_coupon_valid:
                                        if "403" in (course.error or ""):
                                            course_status = "failed"
                                            error_msg = course.error
                                        else:
                                            self.udemy.expired_c += 1
                                            course_status = "expired"
                                            error_msg = course.error
                                    else:
                                        if self.settings.get("discounted_only") and course.is_free:
                                            self.udemy.excluded_c += 1
                                            course_status = "excluded"
                                            error_msg = "Course is free by default"
                                            course.is_excluded = True
                                            course.error = error_msg
                                        else:
                                            logger.info(f"[PIPELINE] Attempting enrollment for {course.title}")
                                            success, course_status = await process_single_course(course)
                                            saved_already = True
                    except Exception as e:
                        logger.exception(f"[PIPELINE ERROR] Unexpected error processing {course.title}: {e}")
                        course_status = "failed"
                        error_msg = str(e)

                    site_key = course.site or "Unknown"
                    source_stats[site_key][course_status] += 1

                    if not saved_already:
                        await self._save_course(db, run, course, course_status, error_msg)

                    await self._update_run_stats(db, run)
                    index += 1

                    if self._is_server:
                        if error_msg and "temporarily blocked" in error_msg.lower():
                            cooldown = random.uniform(120, 180)
                            await asyncio.sleep(cooldown)
                        if index % 25 == 0:
                            await asyncio.sleep(random.uniform(20, 40))
                        await asyncio.sleep(random.uniform(1.5, 3.5))
                    else:
                        await asyncio.sleep(random.uniform(0.5, 1.5))

            pd = dict(run.progress_data or {})
            pd["scraping_progress"] = self.scraper_service.get_progress()
            run.progress_data = pd

            if scrapers_succeeded == 0 and index == 0:
                run.status = "failed"
                run.error_message = "All sources failed or timed out and no courses were found."
            else:
                run.status = "completed"

            run.completed_at = _utcnow_naive()
            db.commit()
            self.status = run.status

            logger.info("--- Source Telemetry Summary ---")
            for site, stats in source_stats.items():
                total = sum(stats.values())
                logger.info(f"  {site}: {total} processed | {stats['enrolled']} enrolled | {stats['already_enrolled']} already enrolled | {stats['expired']} expired | {stats['failed']} failed | {stats['excluded']} excluded | {stats['invalid']} invalid")
            logger.info("--------------------------------")
            _health = self.udemy.get_session_health_report()
            logger.info(f"Enrollment pipeline completed. Enrolled: {self.udemy.successfully_enrolled_c}")

        except asyncio.CancelledError:
            logger.info(f"Enrollment pipeline {self.run_id} cancelled")
            cleanup_db = SessionLocal()
            try:
                run = cleanup_db.get(EnrollmentRun, self.run_id)
                if run:
                    run.status = "cancelled"
                    run.completed_at = _utcnow_naive()
                    cleanup_db.commit()
            finally:
                cleanup_db.close()
            raise
        except Exception as e:
            logger.exception("Enrollment pipeline failed")
            try:
                run = db.get(EnrollmentRun, self.run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(e)
                    run.completed_at = _utcnow_naive()
                    db.commit()
            except Exception:
                pass
        finally:
            clear_user_caches(self.user_id)
            EnrollmentManager.active_tasks.pop(self.run_id, None)
            db.close()
            if self.scraper_service:
                try:
                    await self.scraper_service.http.close()
                except Exception as e:
                    logger.warning(f"Error closing scraper HTTP client: {e}")
            if self.close_client:
                await self.udemy.close()

    async def _update_run_stats(self, db: Session, run: EnrollmentRun):
        """Flush in-memory counters to the run record."""
        try:
            run.total_processed = self.processed
            run.successfully_enrolled = self.udemy.successfully_enrolled_c
            run.already_enrolled = self.udemy.already_enrolled_c
            run.expired = self.udemy.expired_c
            run.excluded = self.udemy.excluded_c
            run.amount_saved = float(self.udemy.amount_saved_c)

            pd = dict(run.progress_data or {})
            pd["current_course_title"] = self.current_course_title
            pd["current_course_url"] = self.current_course_url
            # Keep scraping_progress if it was already there (from scraping phase)
            run.progress_data = pd
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug(f"Could not update stats: {e}")

    async def _save_course(
        self,
        db: Session,
        run: EnrollmentRun,
        course: Course,
        status: str,
        error_msg: str = None,
    ):
        """Save an individual course result to the database."""
        try:
            # We record the original price (savings) in the price column for analytics 
            # only if status is enrolled. Otherwise it's just 0.0.
            price_val = float(course.list_price or course.price or 0.0)

            ec = EnrolledCourse(
                enrollment_run_id=run.id,
                title=course.title,
                url=course.url,
                slug=course.slug,
                course_id=course.course_id,
                coupon_code=course.coupon_code,
                price=price_val if status == "enrolled" else 0.0,
                category=course.category,
                language=course.language,
                rating=course.rating,
                site_source=course.site,
                status=status,
                error_message=error_msg or course.error,
            )
            db.add(ec)

            # Update User lifetime aggregate stats
            user = db.get(User, self.user_id)
            if user:
                if status == "enrolled":
                    user.total_enrolled += 1
                    user.total_amount_saved += price_val
                elif status == "already_enrolled":
                    user.total_already_enrolled += 1
                elif status == "expired":
                    user.total_expired += 1
                elif status in ["excluded", "invalid"]:
                    user.total_excluded += 1

            db.commit()

            # If the course was successfully enrolled and save_txt is True, append it to a text file
            if status == "enrolled" and self.settings.get("save_txt"):
                try:
                    import os
                    os.makedirs("Courses", exist_ok=True)
                    filename = f"Courses/enrolled_courses_{self.user_id}.txt"
                    with open(filename, "a", encoding="utf-8") as f:
                        f.write(f"{course.title} - {course.url}\n")
                    logger.info(f"Saved {course.title} to {filename}")
                except Exception as e:
                    logger.error(f"Failed to write course to enrolled_courses.txt: {e}")

            # Invalidate dashboard stats cache so the scorecards reflect
            # the latest lifetime totals immediately.
            _stats_cache.pop(self.user_id, None)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save course {course.title}: {e}")
