"""Enrollment manager - orchestrates scraping and enrollment asynchronously."""

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Optional, Dict, List

from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

from app.models.database import SessionLocal, EnrollmentRun, EnrolledCourse, User, _utcnow_naive
from app.services.course import Course
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient
from config.settings import get_settings


from app.core.cache import clear_user_caches

class EnrollmentManager:

    """Manages the full enrollment pipeline asynchronously: scrape -> validate -> enroll."""

    active_tasks: Dict[int, asyncio.Task] = {}

    def __init__(self, udemy_client: UdemyClient, settings: dict, db: Session, user_id: int, close_client: bool = False):
        self.udemy = udemy_client
        self.settings = settings
        self.user_id = user_id
        self.run_id: Optional[int] = None
        self._request_db = db
        self.close_client = close_client

        # Live progress
        self.status = "idle"
        self.scraper: Optional[ScraperService] = None
        self.current_course_title = ""
        self.current_course_url = ""
        self.total_courses = 0
        self.processed = 0
        self._task: Optional[asyncio.Task] = None

    @classmethod
    def get_active_run(cls, db: Session, user_id: int) -> Optional[EnrollmentRun]:
        return db.query(EnrollmentRun).filter(
            EnrollmentRun.user_id == user_id,
            EnrollmentRun.status.in_(["pending", "scraping", "enrolling"])
        ).first()

    @classmethod
    def get_progress_from_run(cls, run: EnrollmentRun) -> dict:
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
            "amount_saved": float(run.amount_saved),
            "current_course_title": pd.get("current_course_title", ""),
            "current_course_url": pd.get("current_course_url", ""),
            "scraping_progress": pd.get("scraping_progress", []),
        }

    async def start(self) -> int:
        """Create the run record and return the run_id. Pipeline is executed via BackgroundTasks."""
        active = self.get_active_run(self._request_db, self.user_id)
        if active:
            raise RuntimeError("An enrollment run is already active for this user")

        enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
        initial_scraping_progress = [
            {"site": site, "progress": 0, "total": 0, "done": False, "error": None}
            for site in enabled_sites
        ]

        run = EnrollmentRun(
            user_id=self.user_id,
            status="pending",
            currency=self.udemy.currency,
            progress_data={
                "settings": self.settings,
                "scraping_progress": initial_scraping_progress
            }
        )
        self._request_db.add(run)
        self._request_db.commit()
        self._request_db.refresh(run)
        self.run_id = run.id

        return self.run_id

    async def _run_pipeline(self):
        """Full enrollment pipeline - asynchronous background task."""
        # Use a new DB session for the background task
        db = SessionLocal()
        try:
            if self.run_id is None:
                logger.error("EnrollmentManager: run_id is None in _run_pipeline")
                return

            run = db.get(EnrollmentRun, self.run_id)

            # Phase 1: Scrape
            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            if not enabled_sites:
                await self._fail(db, run, "No sites enabled for scraping")
                return

            run.status = "scraping"
            db.commit()
            self.status = "scraping"

            self.scraper = ScraperService(
                enabled_sites,
                proxy=self.settings.get("proxy_url"),
                enable_headless=self.settings.get("enable_headless", False),
                firecrawl_api_key=self.settings.get("firecrawl_api_key")
            )

            async def _update_scraping_progress():
                while self.status == "scraping":
                    await self._update_run_stats(db, run)
                    await asyncio.sleep(1)

            progress_task = asyncio.create_task(_update_scraping_progress())
            try:
                raw_scraped_courses = await self.scraper.scrape_all()
            finally:
                progress_task.cancel()

            # Pre-filter to ignore previously processed courses for this user
            previous_courses = db.query(EnrolledCourse.url, EnrolledCourse.slug, EnrolledCourse.status)\
                .join(EnrollmentRun).filter(EnrollmentRun.user_id == self.user_id).all()
            
            processed_urls = {c.url for c in previous_courses if c.url and c.status in ("enrolled", "already_enrolled", "expired", "invalid")}
            enrolled_slugs = {c.slug for c in previous_courses if c.slug and c.status in ("enrolled", "already_enrolled")}

            scraped_courses = []
            import re
            for course in raw_scraped_courses:
                if course.url in processed_urls:
                    continue
                
                if not course.slug and course.url:
                    match = re.search(r"udemy\.com/course/([^/?#]+)", course.url)
                    if match:
                        course.slug = match.group(1)
                
                if course.slug and course.slug in enrolled_slugs:
                    continue
                    
                scraped_courses.append(course)

            self.total_courses = len(scraped_courses)

            run.total_courses_found = self.total_courses
            run.status = "enrolling"
            db.commit()
            self.status = "enrolling"

            # Phase 2: Process and enroll
            batch: List[Course] = []
            use_single_course = get_settings().SINGLE_COURSE_CHECKOUT
            
            if use_single_course:
                logger.info("🔄 Single-course checkout mode enabled (one at a time)")
            else:
                logger.info(f"🔄 Bulk checkout mode enabled ({get_settings().ENROLLMENT_BATCH_SIZE} at a time)")

            async def process_batch():
                if not batch: return
                # Add random delay before processing batch (respect server rate limits)
                batch_delay = random.uniform(2.0, 5.0)
                logger.debug(f"Processing batch of {len(batch)} courses (delay: {batch_delay:.1f}s)")
                await asyncio.sleep(batch_delay)
                
                # Track batch metrics
                batch_start = asyncio.get_event_loop().time()
                outcomes = await self.udemy.bulk_checkout(batch)
                batch_duration = asyncio.get_event_loop().time() - batch_start
                
                # Log batch summary
                enrolled = sum(1 for status in outcomes.values() if status == "enrolled")
                failed = sum(1 for status in outcomes.values() if status == "failed")
                logger.info(f"📦 Batch Complete: {enrolled}/{len(batch)} enrolled, "
                           f"{failed} failed, {batch_duration:.1f}s duration")
                
                for c, status in outcomes.items():
                    await self._save_course(db, run, c, status)
                batch.clear()
            
            async def process_single_course(course: Course):
                """Process single course checkout with metrics tracking."""
                course_delay = random.uniform(1.0, 3.0)
                await asyncio.sleep(course_delay)
                
                start_time = asyncio.get_event_loop().time()
                success = await self.udemy.checkout_single(course)
                duration = asyncio.get_event_loop().time() - start_time
                
                if success:
                    self.udemy.successfully_enrolled_c += 1
                    status = "enrolled"
                    logger.info(f"✅ Single Checkout Success: {course.title} ({duration:.1f}s)")
                else:
                    status = "failed"
                    logger.warning(f"❌ Single Checkout Failed: {course.title} ({duration:.1f}s)")
                
                await self._save_course(db, run, course, status)
                return success

            for index, course in enumerate(scraped_courses):
                self.processed = index + 1
                self.current_course_title = course.title
                self.current_course_url = course.url or ""

                if index == 0 or (index + 1) % 25 == 0 or (index + 1) == self.total_courses:
                    logger.info(f"Processing {index + 1}/{self.total_courses}: {course.title}")
                else:
                    logger.debug(f"Processing {index + 1}/{self.total_courses}: {course.title}")

                course_status = "failed"
                error_msg = None

                if await self.udemy.is_already_enrolled(course, enrolled_slugs):
                    self.udemy.already_enrolled_c += 1
                    course_status = "already_enrolled"
                    logger.debug(f"  Status: Already enrolled (Slug: {course.slug})")
                else:
                    await self.udemy.get_course_id(course)

                    if not course.is_valid:
                        self.udemy.excluded_c += 1
                        course_status = "invalid"
                        error_msg = course.error
                        logger.info(f"  Status: Invalid - {error_msg}")
                    elif await self.udemy.is_already_enrolled(course, enrolled_slugs):
                        self.udemy.already_enrolled_c += 1
                        course_status = "already_enrolled"
                        logger.debug(f"  Status: Already enrolled (ID match)")
                    else:
                        # Apply user filters
                        self.udemy.is_course_excluded(course, self.settings)
                        if course.is_excluded:
                            self.udemy.excluded_c += 1
                            course_status = "excluded"
                            error_msg = course.error
                            logger.info(f"  Status: Excluded - {error_msg}")
                        elif course.is_free:
                            if self.settings.get("discounted_only", False):
                                self.udemy.excluded_c += 1
                                course_status = "excluded"
                                error_msg = "Free course (discounted only)"
                                logger.info(f"  Status: Excluded - {error_msg}")
                            else:
                                await self.udemy.free_checkout(course)
                                if course.status:
                                    self.udemy.successfully_enrolled_c += 1
                                    course_status = "enrolled"
                                    logger.info(f"  Status: Enrolled (Free)")
                                else:
                                    self.udemy.expired_c += 1
                                    course_status = "failed"
                                    logger.info(f"  Status: Failed (Free checkout error)")
                        else:
                            await self.udemy.check_course(course)
                            if not course.is_coupon_valid:
                                self.udemy.expired_c += 1
                                course_status = "expired"
                                logger.info(f"  Status: Expired - {course.error or 'Coupon no longer valid'}")
                            else:
                                if use_single_course:
                                    # Single-course mode: process immediately
                                    logger.info(f"  Status: Processing single checkout (Price: {course.price})")
                                    await process_single_course(course)
                                    course_status = "pending"  # Already saved in process_single_course
                                else:
                                    # Bulk mode: add to batch
                                    logger.info(f"  Status: Added to batch (Price: {course.price})")
                                    batch.append(course)
                                    if len(batch) >= get_settings().ENROLLMENT_BATCH_SIZE:
                                        await process_batch()
                                    course_status = "batched"

                if course_status not in ("batched", "pending"):
                    await self._save_course(db, run, course, course_status, error_msg)

                # Update stats and commit every 5 courses or on the last one
                if (index + 1) % 5 == 0 or (index + 1) == self.total_courses:
                    await self._update_run_stats(db, run)
                
                # Small sleep to prevent tight loop blocking and respect rate limits
                # Vary the sleep to avoid detectable patterns (1-3 seconds)
                await asyncio.sleep(random.uniform(1.0, 3.0))

            # Process remaining batch (only in bulk mode)
            if not use_single_course:
                await process_batch()
            await self._update_run_stats(db, run)

            # Mark complete
            run.status = "completed"
            run.completed_at = _utcnow_naive()
            db.commit()
            self.status = "completed"
            logger.info("Enrollment pipeline completed successfully")

        except asyncio.CancelledError:
            logger.info(f"Enrollment pipeline {self.run_id} cancelled (Shutdown or Logout)")
            # Use a fresh DB session for cleanup to avoid issues with the potentially stalled session
            cleanup_db = SessionLocal()
            max_cleanup_retries = 3
            cleanup_retry_delay = 0.5
            
            cleanup_success = False
            max_cleanup_retries = 5  # Increased from 3
            cleanup_retry_delay = 1  # Start with 1 second
            try:
                for cleanup_attempt in range(max_cleanup_retries):
                    try:
                        run = cleanup_db.get(EnrollmentRun, self.run_id)
                        if run:
                            run.status = "cancelled"
                            run.error_message = "Cancelled by system/user"
                            run.completed_at = _utcnow_naive()
                            cleanup_db.commit()
                            logger.info(f"Enrollment run {self.run_id} marked as cancelled in DB.")
                            cleanup_success = True
                            break
                    except Exception as e:
                        cleanup_db.rollback()
                        if "database is locked" in str(e).lower() and cleanup_attempt < max_cleanup_retries - 1:
                            # Exponential backoff: 1, 2, 4, 8, 16 seconds
                            backoff_time = cleanup_retry_delay * (2 ** cleanup_attempt)
                            logger.debug(f"Database locked during cleanup (attempt {cleanup_attempt + 1}/{max_cleanup_retries}). Retrying in {backoff_time}s...")
                            await asyncio.sleep(backoff_time)
                            continue
                        logger.error(f"Failed to mark run {self.run_id} as cancelled: {e}")
                        break
            finally:
                cleanup_db.close()
            
            if not cleanup_success:
                logger.warning(f"Could not persist cancellation status for run {self.run_id} to database")
            
            self.status = "cancelled"
            raise
        except Exception as e:
            logger.exception("Enrollment pipeline failed")
            max_error_retries = 5  # Increased from 3
            error_retry_delay = 1  # Increased from 0.5
            
            for error_attempt in range(max_error_retries):
                try:
                    run = db.get(EnrollmentRun, self.run_id)
                    if run:
                        run.status = "failed"
                        run.error_message = str(e)
                        run.completed_at = _utcnow_naive()
                        db.commit()
                    break
                except Exception as db_e:
                    db.rollback()
                    if "database is locked" in str(db_e).lower() and error_attempt < max_error_retries - 1:
                        # Exponential backoff: 1, 2, 4, 8, 16 seconds
                        backoff_time = error_retry_delay * (2 ** error_attempt)
                        logger.debug(f"Database locked during error cleanup (attempt {error_attempt + 1}/{max_error_retries}). Retrying in {backoff_time}s...")
                        await asyncio.sleep(backoff_time)
                        continue
                    logger.debug(f"Could not update run status on error: {db_e}")
                    break
            self.status = "failed"
        finally:
            # Clear cache so UI shows final state immediately
            clear_user_caches(self.user_id)
            
            EnrollmentManager.active_tasks.pop(self.run_id, None)
            db.close()

            if self.close_client:
                await self.udemy.close()

    async def _update_run_stats(self, db: Session, run: EnrollmentRun):
        """Flush in-memory counters to the run record with retry logic for database locks."""
        max_retries = 5  # Increased from 3
        retry_delay = 1  # Increased from 0.5
        
        for attempt in range(max_retries):
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
                if self.scraper:
                    pd["scraping_progress"] = self.scraper.get_progress()
                
                run.progress_data = pd
                flag_modified(run, "progress_data")
                
                db.commit()
                return
            except Exception as e:
                db.rollback()
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    # Exponential backoff: 1, 2, 4, 8, 16 seconds
                    backoff_time = retry_delay * (2 ** attempt)
                    logger.debug(f"Database locked during stats update (attempt {attempt + 1}/{max_retries}). Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                    continue
                logger.debug(f"Failed to update run stats (attempt {attempt + 1}/{max_retries}): {e}")
                break

    async def _save_course(self, db: Session, run: EnrollmentRun, course: Course,
                           status: str, error: str = None):
        """Add course record and update user stats in the current transaction. 
        Note: Does not commit; caller must commit (e.g., via _update_run_stats)."""
        try:
            db.add(EnrolledCourse(
                enrollment_run_id=run.id,
                title=course.title,
                url=course.url or "",
                slug=course.slug,
                course_id=course.course_id,
                coupon_code=course.coupon_code,
                price=float(course.price) if course.price else None,
                category=course.category,
                language=course.language,
                rating=course.rating,
                site_source=course.site,
                status=status,
                error_message=error,
            ))

            if status == "enrolled":
                db.execute(
                    update(User)
                    .where(User.id == self.user_id)
                    .values(
                        total_enrolled=User.total_enrolled + 1,
                        total_amount_saved=User.total_amount_saved + (float(course.price) if course.price else 0.0),
                    )
                )
            elif status == "already_enrolled":
                db.execute(update(User).where(User.id == self.user_id).values(total_already_enrolled=User.total_already_enrolled + 1))
            elif status == "expired":
                db.execute(update(User).where(User.id == self.user_id).values(total_expired=User.total_expired + 1))
            elif status in ("excluded", "invalid"):
                db.execute(update(User).where(User.id == self.user_id).values(total_excluded=User.total_excluded + 1))

        except Exception as e:
            logger.error(f"Failed to prepare course record: {e}")
            db.rollback()

    async def _fail(self, db: Session, run: EnrollmentRun, message: str):
        run.status = "failed"
        run.error_message = message
        run.completed_at = _utcnow_naive()
        db.commit()
        self.status = "failed"
