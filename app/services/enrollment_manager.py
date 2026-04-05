"""Enrollment manager - orchestrates scraping and enrollment in background."""

import asyncio
import logging
import threading
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import EnrollmentRun, EnrolledCourse, UserSettings
from app.services.course import Course
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient

logger = logging.getLogger(__name__)


class EnrollmentManager:
    """Manages the full enrollment pipeline: scrape -> validate -> enroll."""

    # Active runs tracked by user_id
    _active_runs: dict[int, "EnrollmentManager"] = {}

    def __init__(self, udemy_client: UdemyClient, settings: dict, db: Session, user_id: int):
        self.udemy = udemy_client
        self.settings = settings
        self.db = db
        self.user_id = user_id
        self.run: Optional[EnrollmentRun] = None

        # Live progress
        self.status = "idle"
        self.scraper: Optional[ScraperService] = None
        self.current_course_title = ""
        self.current_course_url = ""
        self.total_courses = 0
        self.processed = 0
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def get_active_run(cls, user_id: int) -> Optional["EnrollmentManager"]:
        return cls._active_runs.get(user_id)

    def start(self):
        """Start the enrollment process in a background thread."""
        if self.user_id in self._active_runs:
            raise RuntimeError("An enrollment run is already active for this user")

        # Create DB record
        self.run = EnrollmentRun(
            user_id=self.user_id,
            status="scraping",
            currency=self.udemy.currency,
        )
        self.db.add(self.run)
        self.db.commit()
        self.db.refresh(self.run)

        self._active_runs[self.user_id] = self
        self.status = "scraping"

        self._thread = threading.Thread(target=self._run_pipeline, daemon=True)
        self._thread.start()

        return self.run.id

    def _run_pipeline(self):
        """Full enrollment pipeline."""
        try:
            # Phase 1: Scrape
            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            if not enabled_sites:
                self._fail("No sites enabled for scraping")
                return

            self.scraper = ScraperService(enabled_sites)
            scraped_courses = self.scraper.scrape_all()
            self.total_courses = len(scraped_courses)

            self.run.total_courses_found = self.total_courses
            self.run.status = "enrolling"
            self._save_run()
            self.status = "enrolling"

            # Phase 2: Process and enroll
            valid_courses: list[Course] = []
            batch_size = 5

            for index, course in enumerate(scraped_courses):
                self.udemy.course = course
                self.processed = index + 1
                self.current_course_title = course.title
                self.current_course_url = course.url or ""

                logger.info(f"Processing {index + 1}/{self.total_courses}: {course.title}")

                if self.udemy.is_already_enrolled(course):
                    self.udemy.already_enrolled_c += 1
                    self._save_enrolled_course(course, "already_enrolled")
                else:
                    self.udemy.get_course_id(course)

                    if not course.is_valid:
                        self.udemy.excluded_c += 1
                        self._save_enrolled_course(course, "invalid", course.error)
                    elif self.udemy.is_already_enrolled(course):
                        self.udemy.already_enrolled_c += 1
                        self._save_enrolled_course(course, "already_enrolled")
                    else:
                        self.udemy.is_course_excluded(course, self.settings)
                        if course.is_excluded:
                            self.udemy.excluded_c += 1
                            self._save_enrolled_course(course, "excluded")
                        elif course.is_free:
                            if self.settings.get("discounted_only", False):
                                self.udemy.excluded_c += 1
                                self._save_enrolled_course(course, "excluded", "Free course (discounted only)")
                            else:
                                self.udemy.free_checkout(course)
                                if course.status:
                                    self.udemy.successfully_enrolled_c += 1
                                    self._save_enrolled_course(course, "enrolled")
                                else:
                                    self.udemy.expired_c += 1
                                    self._save_enrolled_course(course, "failed")
                        else:
                            self.udemy.check_course(course)
                            if not course.is_coupon_valid:
                                self.udemy.expired_c += 1
                                self._save_enrolled_course(course, "expired")
                            else:
                                valid_courses.append(course)

                    if len(valid_courses) >= batch_size:
                        success = self.udemy.bulk_checkout(valid_courses)
                        for c in valid_courses:
                            self._save_enrolled_course(c, "enrolled" if success else "failed")
                        valid_courses.clear()

                self._update_run_stats()

            # Final batch
            if valid_courses:
                success = self.udemy.bulk_checkout(valid_courses)
                for c in valid_courses:
                    self._save_enrolled_course(c, "enrolled" if success else "failed")
                self._update_run_stats()

            # Done
            self.status = "completed"
            self.run.status = "completed"
            self.run.completed_at = datetime.utcnow()
            self._save_run()
            logger.info("Enrollment pipeline completed successfully")

        except Exception as e:
            logger.exception("Enrollment pipeline failed")
            self._fail(str(e))
        finally:
            self._active_runs.pop(self.user_id, None)

    def _fail(self, message: str):
        self.status = "failed"
        if self.run:
            self.run.status = "failed"
            self.run.error_message = message
            self.run.completed_at = datetime.utcnow()
            self._save_run()

    def _save_run(self):
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _update_run_stats(self):
        if self.run:
            self.run.total_processed = self.processed
            self.run.successfully_enrolled = self.udemy.successfully_enrolled_c
            self.run.already_enrolled = self.udemy.already_enrolled_c
            self.run.expired = self.udemy.expired_c
            self.run.excluded = self.udemy.excluded_c
            self.run.amount_saved = float(self.udemy.amount_saved_c)
            self._save_run()

    def _save_enrolled_course(self, course: Course, status: str, error: str = None):
        try:
            ec = EnrolledCourse(
                enrollment_run_id=self.run.id,
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
            )
            self.db.add(ec)
            self.db.commit()
        except Exception:
            self.db.rollback()

    def get_progress(self) -> dict:
        """Get current progress for SSE/polling."""
        return {
            "run_id": self.run.id if self.run else None,
            "status": self.status,
            "total_courses": self.total_courses,
            "processed": self.processed,
            "successfully_enrolled": self.udemy.successfully_enrolled_c,
            "already_enrolled": self.udemy.already_enrolled_c,
            "expired": self.udemy.expired_c,
            "excluded": self.udemy.excluded_c,
            "amount_saved": float(self.udemy.amount_saved_c),
            "current_course_title": self.current_course_title,
            "current_course_url": self.current_course_url,
            "scraping_progress": self.scraper.get_progress() if self.scraper else [],
        }
