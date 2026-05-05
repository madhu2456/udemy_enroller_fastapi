"""Enrollment manager - handles the background enrollment pipeline."""

import asyncio
import random
import re
from typing import List, Optional, Dict

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
                # Must create a new dict copy so SQLAlchemy detects the mutation
                pd = dict(run.progress_data or {})
                pd["scraping_progress"] = progress
                run.progress_data = pd
                db.commit()
                await asyncio.sleep(2)

            raw_courses = await scrape_task
            logger.warning(f"Scraper returned {len(raw_courses)} courses total.")

            # Final scraping progress update
            pd = dict(run.progress_data or {})
            pd["scraping_progress"] = self.scraper_service.get_progress()
            run.progress_data = pd
            db.commit()

            # Pre-filter for uniqueness and already enrolled (by slug)
            scraped_courses: List[Course] = []
            seen_slugs = set()

            # Build a set of courses we KNOW are already enrolled from previous runs.
            # This avoids hitting Udemy's API for courses we already discovered.
            # For users with massive libraries (20k+), this is far safer than bulk-fetching.
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
                logger.warning(
                    f"Loaded {len(enrolled_slugs)} already-enrolled courses from DB history."
                )
            except Exception as e:
                logger.warning(f"Could not load enrolled history from DB: {e}")

            # Also load previously attempted course+coupon combos (any status)
            # to avoid re-trying identical URLs with the same coupon.
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
                logger.warning(
                    f"Loaded {len(previously_attempted)} previously attempted course+coupon combos."
                )
            except Exception as e:
                logger.warning(f"Could not load previous attempts: {e}")

            skipped_already_enrolled = 0
            skipped_already_tried = 0

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

                # Skip if we already know this course is already enrolled from a prior run
                if course.slug and course.slug in enrolled_slugs:
                    skipped_already_enrolled += 1
                    continue

                # Skip if we already tried this exact course + coupon in a previous run
                coupon = course.coupon_code or ""
                if course.slug and (course.slug, coupon) in previously_attempted:
                    skipped_already_tried += 1
                    continue

                scraped_courses.append(course)

            self.total_courses = len(scraped_courses)
            logger.warning(
                f"Final course list to process: {self.total_courses} courses "
                f"({skipped_already_enrolled} skipped as already enrolled from DB, "
                f"{skipped_already_tried} skipped as already tried with same coupon)."
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
                logger.info(f"[PROCESS] Delaying {course_delay:.1f}s before enrolling {course.title}")
                await asyncio.sleep(course_delay)

                start_time = asyncio.get_event_loop().time()
                logger.info(f"[PROCESS] Calling checkout_single for {course.title}")
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
                    # Distinguish between expired coupon vs actual failure
                    err = (course.error or "").lower()
                    if "price mismatch" in err or "expired" in err:
                        status = "expired"
                        self.udemy.expired_c += 1
                        logger.warning(
                            f"⏰ Coupon Expired (checkout): {course.title} — {course.error}"
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
                            f"  Status: Already enrolled (DB cache: {course.slug})"
                        )
                    else:
                        logger.info(f"[PIPELINE] Fetching course_id for {course.title}")
                        await self.udemy.get_course_id(course)
                        logger.info(
                            f"[PIPELINE] course_id={course.course_id} | valid={course.is_valid} | "
                            f"error={course.error or 'none'} for {course.title}"
                        )

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
                        elif await self.udemy.check_already_enrolled_live(course):
                            # Live API check with course_id confirms already enrolled
                            self.udemy.already_enrolled_c += 1
                            course_status = "already_enrolled"
                            logger.info(
                                f"  Status: Already enrolled (Live API: {course.slug})"
                            )
                        else:
                            # Apply user filters
                            self.udemy.is_course_excluded(course, self.settings)
                            if course.is_excluded:
                                self.udemy.excluded_c += 1
                                course_status = "excluded"
                                logger.info("  Status: Excluded (Filter match)")
                            else:
                                # Course is valid and free/couponed - Enrolling
                                logger.info(f"[PIPELINE] Checking coupon for {course.title}")
                                await self.udemy.check_course(course)
                                logger.info(
                                    f"[PIPELINE] coupon_valid={course.is_coupon_valid} | "
                                    f"price={course.price} | error={course.error or 'none'} for {course.title}"
                                )
                                if not course.is_coupon_valid:
                                    if "403" in (course.error or ""):
                                        course_status = "failed"
                                        error_msg = course.error
                                    else:
                                        self.udemy.expired_c += 1
                                        course_status = "expired"
                                    
                                    logger.warning(
                                        f"  Status: {course_status.capitalize()} ({course.error}) for {course.title}"
                                    )
                                else:
                                    # Enrolling in single course mode
                                    logger.info(f"[PIPELINE] Attempting enrollment for {course.title}")
                                    await process_single_course(course)
                                    saved_already = True
                except Exception as e:
                    logger.exception(f"[PIPELINE ERROR] Unexpected error processing {course.title}: {e}")
                    course_status = "failed"
                    error_msg = str(e)

                if not saved_already:
                    await self._save_course(db, run, course, course_status, error_msg)

                # Periodically update run progress
                if (index + 1) % 5 == 0 or (index + 1) == self.total_courses:
                    await self._update_run_stats(db, run)

                # Server-specific batch pauses to avoid Udemy rate limits
                if self._is_server:
                    # Detect account block signal and trigger longer cooldown
                    if error_msg and "temporarily blocked" in error_msg.lower():
                        cooldown = random.uniform(120, 180)
                        logger.warning(
                            f"  [SERVER] Account block signal detected. Cooling down for {cooldown:.0f}s..."
                        )
                        await asyncio.sleep(cooldown)

                    # After every 25 courses, take a longer breather
                    if (index + 1) % 25 == 0:
                        breather = random.uniform(20, 40)
                        logger.info(
                            f"  [SERVER] Batch pause after {index + 1} courses. Sleeping {breather:.0f}s..."
                        )
                        await asyncio.sleep(breather)

                    # Standard server safety sleep (longer than local)
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                else:
                    # Local: small safety sleep (fast, residential IP)
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

            # Invalidate dashboard stats cache so the scorecards reflect
            # the latest lifetime totals immediately.
            _stats_cache.pop(self.user_id, None)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save course {course.title}: {e}")
