"""Enrollment manager - orchestrates scraping and enrollment asynchronously."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional, Dict, List

from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

from app.models.database import SessionLocal, EnrollmentRun, EnrolledCourse, User
from app.services.course import Course
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient


class EnrollmentManager:
    """Manages the full enrollment pipeline asynchronously: scrape -> validate -> enroll."""

    @staticmethod
    def _utcnow_naive() -> datetime:
        """Return current UTC timestamp without tzinfo for DB DateTime columns."""
        return datetime.now(UTC).replace(tzinfo=None)

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
        """Create the run record then return the run_id. Let the scheduler pick it up."""
        active = self.get_active_run(self._request_db, self.user_id)
        if active:
            raise RuntimeError("An enrollment run is already active for this user")

        run = EnrollmentRun(
            user_id=self.user_id,
            status="pending",
            currency=self.udemy.currency,
            progress_data={
                "settings": self.settings
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
            run = db.get(EnrollmentRun, self.run_id)

            # Phase 1: Scrape
            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            if not enabled_sites:
                await self._fail(db, run, "No sites enabled for scraping")
                return

            self.scraper = ScraperService(
                enabled_sites,
                proxy=self.settings.get("proxy_url"),
                enable_headless=self.settings.get("enable_headless", False)
            )
            raw_scraped_courses = await self.scraper.scrape_all()

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

            async def process_batch():
                if not batch: return
                outcomes = await self.udemy.bulk_checkout(batch)
                for c, status in outcomes.items():
                    await self._save_course(db, run, c, status)
                batch.clear()

            for index, course in enumerate(scraped_courses):
                self.processed = index + 1
                self.current_course_title = course.title
                self.current_course_url = course.url or ""

                if index == 0 or (index + 1) % 25 == 0 or (index + 1) == self.total_courses:
                    logger.info(f"Processing {index + 1}/{self.total_courses}: {course.title}")
                else:
                    logger.debug(f"Processing {index + 1}/{self.total_courses}: {course.title}")

                if await self.udemy.is_already_enrolled(course):
                    self.udemy.already_enrolled_c += 1
                    await self._save_course(db, run, course, "already_enrolled")
                else:
                    await self.udemy.get_course_id(course)

                    if not course.is_valid:
                        self.udemy.excluded_c += 1
                        await self._save_course(db, run, course, "invalid", course.error)
                    elif await self.udemy.is_already_enrolled(course):
                        self.udemy.already_enrolled_c += 1
                        await self._save_course(db, run, course, "already_enrolled")
                    else:
                        # Apply user filters
                        self.udemy.is_course_excluded(course, self.settings)
                        if course.is_excluded:
                            self.udemy.excluded_c += 1
                            await self._save_course(db, run, course, "excluded", course.error)
                            continue

                        if course.is_free:
                            if self.settings.get("discounted_only", False):
                                self.udemy.excluded_c += 1
                                await self._save_course(db, run, course, "excluded", "Free course (discounted only)")
                            else:
                                await self.udemy.free_checkout(course)
                                if course.status:
                                    self.udemy.successfully_enrolled_c += 1
                                    await self._save_course(db, run, course, "enrolled")
                                else:
                                    self.udemy.expired_c += 1
                                    await self._save_course(db, run, course, "failed")
                        else:
                            await self.udemy.check_course(course)
                            if not course.is_coupon_valid:
                                self.udemy.expired_c += 1
                                await self._save_course(db, run, course, "expired")
                            else:
                                batch.append(course)
                                if len(batch) >= 10:
                                    await process_batch()

                await self._update_run_stats(db, run)
                # Small sleep to prevent tight loop blocking and respect rate limits
                await asyncio.sleep(1.5)

            # Process remaining batch
            await process_batch()
            await self._update_run_stats(db, run)

            # Mark complete
            run.status = "completed"
            run.completed_at = self._utcnow_naive()
            db.commit()
            self.status = "completed"
            logger.info("Enrollment pipeline completed successfully")

        except Exception as e:
            logger.exception("Enrollment pipeline failed")
            try:
                run = db.get(EnrollmentRun, self.run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(e)
                    run.completed_at = self._utcnow_naive()
                    db.commit()
            except Exception:
                pass
            self.status = "failed"
        finally:
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
            if self.scraper:
                pd["scraping_progress"] = self.scraper.get_progress()
            
            run.progress_data = pd
            flag_modified(run, "progress_data")
            
            db.commit()
        except Exception:
            db.rollback()

    async def _save_course(self, db: Session, run: EnrollmentRun, course: Course,
                           status: str, error: str = None):
        """Save one course record and update user stats."""
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

            db.commit()
        except Exception as e:
            logger.error(f"Failed to save course record: {e}")
            db.rollback()

    async def _fail(self, db: Session, run: EnrollmentRun, message: str):
        run.status = "failed"
        run.error_message = message
        run.completed_at = self._utcnow_naive()
        db.commit()
        self.status = "failed"
