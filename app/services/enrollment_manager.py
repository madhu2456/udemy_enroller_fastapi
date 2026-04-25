"""Enrollment manager - handles the background enrollment pipeline."""

import asyncio
import random
import re
from typing import List, Optional, Dict

from sqlalchemy.orm import Session
from loguru import logger

from app.core.cache import clear_user_caches
from app.models.database import (
    EnrollmentRun,
    EnrolledCourse,
    SessionLocal,
    _utcnow_naive,
)
from app.services.course import Course
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient


class EnrollmentManager:
    """Manages the background enrollment process for a specific run."""

    # Track active tasks to prevent duplicate runs per user
    active_tasks: Dict[int, asyncio.Task] = {}

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

        return {
            "run_id": run.id,
            "status": run.status,
            "total_courses": run.total_courses_found,
            "processed": run.total_processed,
            "successfully_enrolled": run.successfully_enrolled,
            "already_enrolled": run.already_enrolled,
            "expired": run.expired,
            "excluded": run.excluded,
            "amount_saved": float(run.amount_saved or 0.0),
            "current_course_title": pd.get("current_course_title"),
            "current_course_url": pd.get("current_course_url"),
            "scraping_progress": pd.get("scraping_progress", []),
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
        logger.warning(f"Creating enrollment run for user {user_id}")
        db = SessionLocal()
        try:
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
        logger.warning(f"Starting enrollment pipeline for run {self.run_id}")
        db = SessionLocal()
        try:
            run = db.get(EnrollmentRun, self.run_id)
            if not run:
                logger.error(f"Run {self.run_id} not found in database.")
                return

            # Phase 1: Scraping
            run.status = "scraping"
            db.commit()
            self.status = "scraping"

            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            logger.warning(f"Enabled sites: {enabled_sites}")
            self.scraper_service = ScraperService(
                enabled_sites, proxy=self.settings.get("proxy_url")
            )

            # Start scraping in background but wait for it, while periodically updating status
            scrape_task = asyncio.create_task(self.scraper_service.scrape_all())

            while not scrape_task.done():
                # Update scraping progress in DB every 2 seconds
                progress = self.scraper_service.get_progress()
                pd = run.progress_data or {}
                pd["scraping_progress"] = progress
                run.progress_data = pd
                db.commit()
                await asyncio.sleep(2)

            raw_courses = await scrape_task
            logger.warning(f"Scraper returned {len(raw_courses)} courses total.")

            # Final scraping progress update
            pd = run.progress_data or {}
            pd["scraping_progress"] = self.scraper_service.get_progress()
            run.progress_data = pd
            db.commit()

            # Pre-filter for uniqueness and already enrolled (by slug)
            scraped_courses: List[Course] = []
            seen_slugs = set()
            enrolled_slugs = set()

            # Load user's already enrolled courses if client is authenticated
            if self.udemy.enrolled_courses is None:
                try:
                    await self.udemy.get_enrolled_courses()
                except Exception:
                    logger.warning(
                        "Could not fetch enrolled courses list, proceeding with individual checks."
                    )

            if self.udemy.enrolled_courses:
                enrolled_slugs = set(self.udemy.enrolled_courses.keys())
                logger.warning(
                    f"User has {len(enrolled_slugs)} courses already enrolled."
                )

            for course in raw_courses:
                if not course.url:
                    continue

                # Deduplicate by URL/Slug
                if course.url in seen_slugs:
                    continue
                seen_slugs.add(course.url)

                if not course.slug and course.url:
                    match = re.search(r"udemy\.com/course/([^/?#]+)", course.url)
                    if match:
                        course.slug = match.group(1)

                if course.slug and course.slug in enrolled_slugs:
                    continue

                scraped_courses.append(course)

            self.total_courses = len(scraped_courses)
            logger.warning(
                f"Final course list to process: {self.total_courses} courses."
            )

            run.total_courses_found = self.total_courses
            run.status = "enrolling"
            db.commit()
            self.status = "enrolling"

            # Phase 2: Process and enroll (Single Course Mode only)
            logger.info("🔄 Single-course checkout mode active (Technatic-style logic)")

            async def process_single_course(course: Course):
                """Process single course checkout with metrics tracking."""
                # Add jitter delay between enrollments (Technatic style)
                course_delay = random.uniform(2.0, 5.0)
                await asyncio.sleep(course_delay)

                start_time = asyncio.get_event_loop().time()
                success = await self.udemy.checkout_single(course)
                duration = asyncio.get_event_loop().time() - start_time

                if success:
                    status = "enrolled"
                    self.udemy.successfully_enrolled_c += 1
                    # Add to amount saved only on success
                    if course.list_price:
                        self.udemy.amount_saved_c += course.list_price
                    logger.info(
                        f"✅ Enrollment Success: {course.title} ({duration:.1f}s)"
                    )
                else:
                    status = "failed"
                    logger.warning(
                        f"❌ Enrollment Failed: {course.title} ({duration:.1f}s)"
                    )

                await self._save_course(db, run, course, status)
                return success

            for index, course in enumerate(scraped_courses):
                self.processed = index + 1
                self.current_course_title = course.title
                self.current_course_url = course.url or ""

                if (
                    index == 0
                    or (index + 1) % 25 == 0
                    or (index + 1) == self.total_courses
                ):
                    logger.warning(
                        f"Processing {index + 1}/{self.total_courses}: {course.title}"
                    )
                else:
                    logger.debug(
                        f"Processing {index + 1}/{self.total_courses}: {course.title}"
                    )

                course_status = "failed"
                error_msg = None
                saved_already = False

                try:
                    # Check if already enrolled
                    if not course.slug and course.url:
                        match = re.search(r"udemy\.com/course/([^/?#]+)", course.url)
                        if match:
                            course.slug = match.group(1)

                    if await self.udemy.is_already_enrolled(course, enrolled_slugs):
                        self.udemy.already_enrolled_c += 1
                        course_status = "already_enrolled"
                        logger.debug(
                            f"  Status: Already enrolled (Slug: {course.slug})"
                        )
                    else:
                        await self.udemy.get_course_id(course)

                        if not course.is_valid:
                            error_msg = course.error or ""
                            if "403" in error_msg:
                                course_status = "failed"
                                logger.info(
                                    f"  Status: Skipped (403 Forbidden) - {error_msg}"
                                )
                            else:
                                self.udemy.excluded_c += 1
                                course_status = "invalid"
                                logger.info(f"  Status: Invalid - {error_msg}")
                        elif await self.udemy.is_already_enrolled(
                            course, enrolled_slugs
                        ):
                            self.udemy.already_enrolled_c += 1
                            course_status = "already_enrolled"
                        else:
                            # Apply user filters
                            self.udemy.is_course_excluded(course, self.settings)
                            if course.is_excluded:
                                self.udemy.excluded_c += 1
                                course_status = "excluded"
                                logger.info("  Status: Excluded (Filter match)")
                            else:
                                # Course is valid and free/couponed - Enrolling
                                await self.udemy.check_course(course)
                                if not course.is_coupon_valid:
                                    self.udemy.expired_c += 1
                                    course_status = "expired"
                                    logger.warning(
                                        f"  Status: Expired/Invalid ({course.error}) for {course.title}"
                                    )
                                else:
                                    # Enrolling in single course mode
                                    await process_single_course(course)
                                    saved_already = True
                except Exception as e:
                    logger.exception(f"Unexpected error processing {course.title}")
                    course_status = "failed"
                    error_msg = str(e)

                if not saved_already:
                    await self._save_course(db, run, course, course_status, error_msg)

                # Periodically update run progress
                if (index + 1) % 5 == 0 or (index + 1) == self.total_courses:
                    await self._update_run_stats(db, run)

                # Small safety sleep
                await asyncio.sleep(random.uniform(0.5, 1.5))

            # Mark complete and log session health metrics
            run.status = "completed"
            run.completed_at = _utcnow_naive()
            db.commit()
            self.status = "completed"

            # Log session health report for diagnostics
            _health = self.udemy.get_session_health_report()
            logger.info(
                f"Enrollment pipeline completed. Enrolled: {self.udemy.successfully_enrolled_c}"
            )

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

            pd = run.progress_data or {}
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
            ec = EnrolledCourse(
                enrollment_run_id=run.id,
                title=course.title,
                url=course.url,
                slug=course.slug,
                course_id=course.course_id,
                coupon_code=course.coupon_code,
                price=float(course.price) if course.price else 0.0,
                category=course.category,
                language=course.language,
                rating=course.rating,
                site_source=course.site,
                status=status,
                error_message=error_msg or course.error,
            )
            db.add(ec)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save course {course.title}: {e}")
