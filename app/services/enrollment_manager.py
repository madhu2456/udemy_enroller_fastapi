"""Enrollment manager - orchestrates scraping and enrollment in background."""

import logging
import threading
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.database import SessionLocal, EnrollmentRun, EnrolledCourse, User
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
        self.user_id = user_id
        self.run_id: Optional[int] = None

        # The background thread creates its own session — never share the
        # request-scoped session across thread boundaries.
        self._request_db = db

        # Live progress (read by the SSE/polling endpoint)
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

    def start(self) -> int:
        """Create the run record (using the request session) then hand off to background thread."""
        if self.user_id in self._active_runs:
            raise RuntimeError("An enrollment run is already active for this user")

        # Create the run record while we still have the request session.
        run = EnrollmentRun(
            user_id=self.user_id,
            status="scraping",
            currency=self.udemy.currency,
        )
        self._request_db.add(run)
        self._request_db.commit()
        self._request_db.refresh(run)
        self.run_id = run.id

        self._active_runs[self.user_id] = self
        self.status = "scraping"

        self._thread = threading.Thread(target=self._run_pipeline, daemon=True)
        self._thread.start()

        return self.run_id

    # ── Background thread ──────────────────────────────────────────────────

    def _run_pipeline(self):
        """Full enrollment pipeline — runs in a dedicated thread with its own DB session."""
        db = SessionLocal()
        try:
            # Reload the run record in *our* session
            run = db.get(EnrollmentRun, self.run_id)

            # Phase 1: Scrape
            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            if not enabled_sites:
                self._fail(db, run, "No sites enabled for scraping")
                return

            self.scraper = ScraperService(enabled_sites)
            scraped_courses = self.scraper.scrape_all()
            self.total_courses = len(scraped_courses)

            run.total_courses_found = self.total_courses
            run.status = "enrolling"
            db.commit()
            self.status = "enrolling"

            # Phase 2: Process and enroll (one course at a time)
            for index, course in enumerate(scraped_courses):
                self.udemy.course = course
                self.processed = index + 1
                self.current_course_title = course.title
                self.current_course_url = course.url or ""

                logger.info(f"Processing {index + 1}/{self.total_courses}: {course.title}")

                if self.udemy.is_already_enrolled(course):
                    self.udemy.already_enrolled_c += 1
                    self._save_course(db, run, course, "already_enrolled")
                else:
                    self.udemy.get_course_id(course)

                    if not course.is_valid:
                        self.udemy.excluded_c += 1
                        self._save_course(db, run, course, "invalid", course.error)
                    elif self.udemy.is_already_enrolled(course):
                        self.udemy.already_enrolled_c += 1
                        self._save_course(db, run, course, "already_enrolled")
                    else:
                        if course.is_free:
                            if self.settings.get("discounted_only", False):
                                self.udemy.excluded_c += 1
                                self._save_course(db, run, course, "excluded", "Free course (discounted only)")
                            else:
                                self.udemy.free_checkout(course)
                                if course.status:
                                    self.udemy.successfully_enrolled_c += 1
                                    self._save_course(db, run, course, "enrolled")
                                else:
                                    self.udemy.expired_c += 1
                                    self._save_course(db, run, course, "failed")
                        else:
                            self.udemy.check_course(course)
                            if not course.is_coupon_valid:
                                self.udemy.expired_c += 1
                                self._save_course(db, run, course, "expired")
                            else:
                                success = self.udemy.checkout_single(course)
                                if success:
                                    self._save_course(db, run, course, "enrolled")
                                else:
                                    self._save_course(db, run, course, "failed")

                self._update_run_stats(db, run)

            # Mark complete
            run.status = "completed"
            run.completed_at = datetime.utcnow()
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
                    run.completed_at = datetime.utcnow()
                    db.commit()
            except Exception:
                pass
            self.status = "failed"
        finally:
            db.close()
            self._active_runs.pop(self.user_id, None)

    def _update_run_stats(self, db: Session, run: EnrollmentRun):
        """Flush in-memory counters to the run record."""
        try:
            run.total_processed = self.processed
            run.successfully_enrolled = self.udemy.successfully_enrolled_c
            run.already_enrolled = self.udemy.already_enrolled_c
            run.expired = self.udemy.expired_c
            run.excluded = self.udemy.excluded_c
            run.amount_saved = float(self.udemy.amount_saved_c)
            db.commit()
        except Exception:
            db.rollback()

    def _save_course(self, db: Session, run: EnrollmentRun, course: Course,
                     status: str, error: str = None):
        """Save one course record AND atomically increment the user's lifetime stats."""
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

            # Atomically update the user-level lifetime aggregate so metrics
            # are always accurate even if this run never reaches 'completed'.
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
                db.execute(
                    update(User).where(User.id == self.user_id)
                    .values(total_already_enrolled=User.total_already_enrolled + 1)
                )
            elif status == "expired":
                db.execute(
                    update(User).where(User.id == self.user_id)
                    .values(total_expired=User.total_expired + 1)
                )
            elif status in ("excluded", "invalid"):
                db.execute(
                    update(User).where(User.id == self.user_id)
                    .values(total_excluded=User.total_excluded + 1)
                )

            db.commit()
        except Exception as e:
            logger.error(f"Failed to save course record: {e}")
            db.rollback()

    def get_progress(self) -> dict:
        """Return live progress for the SSE/polling endpoint."""
        return {
            "run_id": self.run_id,
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
