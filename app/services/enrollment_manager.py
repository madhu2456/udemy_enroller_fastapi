"""Enrollment manager - handles the background enrollment pipeline."""

import asyncio
import random
import time
from typing import Any, Optional, Dict

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
from app.services.alerts import send_alert
from app.services.course import Course
from app.services.enrollment_queue import EnrollmentPriorityQueue
from app.services.scraper import ScraperService
from app.services.udemy_client import UdemyClient
from config.settings import resolve_user_proxy

MAX_CATALOG_SEED: int = 25
PRE_CHECKOUT_TTL_SECONDS: float = 240.0
VALIDATION_WORKERS: int = 3
DECOUPLED_ENROLLMENT_ENABLED: bool = True
COUPON_EXPIRY_SIGNATURES: tuple[str, ...] = (
    "expired",
    "price mismatch",
    "not 100%",
    "not free",
    "discount",
    "already_redeemed",
    "maximum_redemptions",
    "no longer valid",
    "claim code",
)


class EnrollmentManager:
    """Manages the background enrollment process for a specific run."""

    # Track active tasks to prevent duplicate runs per user
    active_tasks: Dict[int, asyncio.Task] = {}
    active_managers: Dict[int, "EnrollmentManager"] = {}
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
        self.abort_event = asyncio.Event()

        self._checkout_semaphore = asyncio.Semaphore(1)
        self._db_lock = asyncio.Lock()

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
    async def sweep_stale_runs(cls) -> int:
        """Mark runs stalled on a missing/old heartbeat as failed (F-ENRL-O01).

        ``asyncio.to_thread`` calls (cloudscraper/httpx) cannot be interrupted
        by ``task.cancel()``, so a hung pipeline stops updating
        ``last_heartbeat``. Run periodically by the lifespan sweeper; also
        cancels any registered in-memory task so a recovered run cannot keep
        working against a marked-failed row. Returns the number of runs
        recovered.
        """
        from datetime import timedelta

        from config.settings import get_settings

        settings = get_settings()
        timeout_minutes = int(getattr(settings, "STALE_RUN_TIMEOUT_MINUTES", 15))
        cutoff = _utcnow_naive() - timedelta(minutes=timeout_minutes)

        recovered = 0
        with SessionLocal() as db:
            stale = (
                db.query(EnrollmentRun)
                .filter(
                    EnrollmentRun.status.in_(["pending", "scraping", "enrolling"])
                )
                .filter(
                    (EnrollmentRun.last_heartbeat.is_(None))
                    | (EnrollmentRun.last_heartbeat < cutoff)
                )
                .all()
            )
            for run in stale:
                run.status = "failed"
                run.error_message = (
                    f"Interrupted: no heartbeat for over {timeout_minutes} minutes"
                )
                run.completed_at = _utcnow_naive()
                recovered += 1
            if stale:
                db.commit()
                for run in stale:
                    mgr = cls.active_managers.pop(run.id, None)
                    if mgr is not None:
                        mgr.abort_event.set()
                    task = cls.active_tasks.pop(run.id, None)
                    if task is not None and not task.done():
                        task.cancel()
                    clear_user_caches(run.user_id)
                    logger.warning(
                        f"Sweeper marked stale enrollment run {run.id} failed "
                        f"(no heartbeat for over {timeout_minutes} minutes)"
                    )
                    # F230: alert on stuck-task recovery (webhook OFF unless
                    # ALERT_WEBHOOK_URL is set; never raises).
                    await send_alert(
                        "enrollment_stuck",
                        f"Enrollment run {run.id} (user {run.user_id}) marked "
                        f"failed after no heartbeat for over {timeout_minutes} "
                        "minutes",
                        run_id=run.id,
                        user_id=run.user_id,
                    )
        return recovered

    @classmethod
    def get_progress_from_run(cls, run: EnrollmentRun) -> dict:
        """Extract progress metrics from a run record."""
        pd: Any = run.progress_data or {}

        scraping_progress = pd.get("scraping_progress", [])
        sources_total = len(scraping_progress)
        sources_completed = sum(1 for s in scraping_progress if s.get("state") == "completed")
        sources_failed = sum(1 for s in scraping_progress if s.get("state") in ("failed", "timed_out"))
        courses_discovered = sum(s.get("courses_found", 0) for s in scraping_progress)

        phase: str = str(run.status or "")
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
    async def _cancel_active_run_unlocked(
        cls, user_id: int, active_id: int, timeout: float = 5.0
    ) -> None:
        """Cancel an active run under the user lock without re-acquiring it."""
        manager = cls.active_managers.get(active_id)
        if manager is not None:
            manager.abort_event.set()

        task = cls.active_tasks.get(active_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        with SessionLocal() as db:
            old_run = db.get(EnrollmentRun, active_id)
            if old_run and old_run.status in ("pending", "scraping", "enrolling"):
                old_run.status = "cancelled"
                old_run.error_message = "Superseded by new run"
                old_run.completed_at = _utcnow_naive()
                db.commit()

        clear_user_caches(user_id)

    @classmethod
    async def start_run(
        cls,
        user_id: int,
        udemy_client: UdemyClient,
        settings: dict,
        close_client: bool = False,
    ) -> int:
        """Create a run and start the background task, superseding any prior active run."""
        lock = cls.get_lock(user_id)
        async with lock:
            logger.warning(f"Creating enrollment run for user {user_id}")
            with SessionLocal() as db:
                active = cls.get_active_run(db, user_id)
                active_id = active.id if active else None
                started_at = active.started_at if active else None

            # Rapid double-click debounce window (3.0 seconds)
            if active_id and started_at:
                age = (_utcnow_naive() - started_at).total_seconds()
                if 0 <= age < 3.0:
                    logger.info(
                        f"Rapid duplicate run request for user {user_id} ({age:.2f}s old); reusing run {active_id}"
                    )
                    return active_id

            if active_id:
                logger.warning(
                    f"Active run {active_id} found for user {user_id}; superseding with new run."
                )
                await cls._cancel_active_run_unlocked(user_id, active_id)

            with SessionLocal() as db:
                run = EnrollmentRun(
                    user_id=user_id, status="pending", currency=udemy_client.currency
                )
                db.add(run)
                db.commit()
                db.refresh(run)
                run_id = run.id

            logger.warning(f"Run {run_id} created. Starting background task.")
            manager = cls(user_id, run_id, udemy_client, settings, close_client)
            task = asyncio.create_task(manager.run_pipeline())
            cls.active_tasks[run_id] = task
            cls.active_managers[run_id] = manager

            return run_id

    async def run_pipeline(self):
        """Main enrollment pipeline: Scrape -> Filter -> Enroll."""
        with logger.contextualize(user_id=self.user_id):
            await self._run_pipeline_impl()

    async def process_single_course(self, course: Course) -> tuple[bool, str]:
        """Perform checkout for a single validated course without redundant pre-process sleep."""
        start_time = asyncio.get_event_loop().time()
        logger.info(f"[PROCESS] Calling checkout_single for {course.title}")
        success = await self.udemy.checkout_single(course)
        duration = asyncio.get_event_loop().time() - start_time

        if course.status is None:
            # 504/503 responses never confirm enrollment (F-ENRL-O02):
            # record as "unknown" so stats stay honest (not enrolled).
            status = "unknown"
            self.udemy.unknown_c += 1
            logger.warning(
                f"⏳ Enrollment unknown (unconfirmed response): {course.title} ({duration:.1f}s)"
            )
        elif success:
            status = "enrolled"
            self.udemy.successfully_enrolled_c += 1
            if course.list_price:
                self.udemy.amount_saved_c += course.list_price
            logger.info(f"✅ Enrollment Success: {course.title} ({duration:.1f}s)")
        elif getattr(course, "is_already_enrolled", False):
            status = "already_enrolled"
            self.udemy.already_enrolled_c += 1
            logger.info(f"ℹ️ Already Enrolled: {course.title} ({duration:.1f}s)")
        else:
            err = (course.error or "").lower()
            if any(sig in err for sig in COUPON_EXPIRY_SIGNATURES):
                status = "expired"
                self.udemy.expired_c += 1
                logger.warning(f"⏰ Coupon Expired (checkout): {course.title} — {course.error}")
            else:
                status = "failed"
                logger.warning(f"❌ Enrollment Failed: {course.title} ({duration:.1f}s)")

        return success, status

    async def _checkout_consumer(
        self,
        db: Session,
        run: EnrollmentRun,
        checkout_queue: EnrollmentPriorityQueue,
        source_stats: dict,
        abort_event: asyncio.Event,
    ) -> None:
        """Stage 2: Single-threaded checkout consumer consuming from freshness priority queue (FM-002)."""
        async with self._checkout_semaphore:
            while not abort_event.is_set():
                item = await checkout_queue.get()
                if item.course is None:
                    checkout_queue.task_done()
                    break

                course = item.course
                discovered_at = item.discovered_at

                try:
                    if self.abort_event.is_set():
                        break
                    now = time.time()
                    # Fast price probe pre-checkout TTL re-check (Task 3.3 / FM-002)
                    if now - discovered_at > PRE_CHECKOUT_TTL_SECONDS:
                        logger.info(
                            f"[TTL PROBE] Course '{course.title}' dwelled {now - discovered_at:.1f}s in queue "
                            f"(> {PRE_CHECKOUT_TTL_SECONDS}s). Re-probing coupon validity..."
                        )
                        await self.udemy.check_course(course)
                        if not course.is_coupon_valid:
                            self.udemy.expired_c += 1
                            course_status = "expired"
                            error_msg = course.error or "Coupon expired during queue dwell"
                            site_key = course.site or "Unknown"
                            source_stats[site_key][course_status] += 1
                            self.processed += 1
                            self.current_course_title = course.title
                            self.current_course_url = course.url or ""
                            await self._save_course(db, run, course, course_status, error_msg)
                            await self._update_run_stats(db, run)
                            continue

                    if self.abort_event.is_set():
                        break
                    can_continue = await self._wait_for_circuit_breaker(db, run)
                    if not can_continue:
                        run.status = "failed"
                        run.error_message = "checkout_circuit_exhausted"
                        self.status = "failed"
                        async with self._db_lock:
                            db.commit()
                        abort_event.set()
                        break

                    if self.abort_event.is_set():
                        break
                    self.processed += 1
                    self.current_course_title = course.title
                    self.current_course_url = course.url or ""

                    success, course_status = await self.process_single_course(course)

                    site_key = course.site or "Unknown"
                    source_stats[site_key][course_status] += 1
                    error_msg = course.error if not success else None

                    await self._save_course(db, run, course, course_status, error_msg)
                    await self._update_run_stats(db, run)

                    if self._is_server:
                        if error_msg and "temporarily blocked" in error_msg.lower():
                            cooldown = random.uniform(120, 180)
                            await asyncio.sleep(cooldown)
                        if self.processed % 25 == 0:
                            await asyncio.sleep(random.uniform(20, 40))
                        await asyncio.sleep(random.uniform(1.5, 3.5))
                    else:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.exception(f"[CHECKOUT ERROR] Unexpected error checking out {course.title}: {e}")
                finally:
                    checkout_queue.task_done()

    async def _validation_worker(
        self,
        db: Session,
        run: EnrollmentRun,
        validation_queue: asyncio.Queue,
        checkout_queue: EnrollmentPriorityQueue,
        enrolled_slugs: set[str],
        previously_attempted: set[tuple[str, str]],
        source_stats: dict,
        abort_event: asyncio.Event,
    ) -> None:
        """Stage 1: Async validation worker pool worker (FM-001)."""
        while not abort_event.is_set():
            candidate = await validation_queue.get()
            if candidate is None:
                validation_queue.task_done()
                break

            course, discovered_at = candidate
            course_status = "failed"
            error_msg = None
            push_to_checkout = False

            try:
                coupon_code = course.coupon_code or ""
                if course.slug and course.slug in enrolled_slugs:
                    course.is_already_enrolled = True
                    self.udemy.already_enrolled_c += 1
                    course_status = "already_enrolled"
                elif course.slug and (course.slug, coupon_code) in previously_attempted:
                    validation_queue.task_done()
                    continue
                elif await self.udemy.is_already_enrolled(course, enrolled_slugs):
                    course.is_already_enrolled = True
                    self.udemy.already_enrolled_c += 1
                    course_status = "already_enrolled"
                else:
                    logger.info(f"[VALIDATION] Fetching course_id for {course.title}")
                    if not course.course_id:
                        await self.udemy.get_course_id(course)

                    if not course.is_valid:
                        error_msg = course.error or ""
                        if "403" in error_msg:
                            course_status = "failed"
                        else:
                            self.udemy.excluded_c += 1
                            course_status = "invalid"
                    elif await self.udemy.check_already_enrolled_live(course):
                        course.is_already_enrolled = True
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
                            logger.info(f"[VALIDATION] Checking coupon for {course.title}")
                            await self.udemy.check_course(course)
                            if not course.is_coupon_valid:
                                err_lower = (course.error or "").lower()
                                if any(sig in err_lower for sig in COUPON_EXPIRY_SIGNATURES):
                                    self.udemy.expired_c += 1
                                    course_status = "expired"
                                else:
                                    course_status = "failed"
                                error_msg = course.error
                            elif self.settings.get("discounted_only") and course.is_free:
                                self.udemy.excluded_c += 1
                                course_status = "excluded"
                                error_msg = "Course is free by default"
                                course.is_excluded = True
                                course.error = error_msg
                            else:
                                push_to_checkout = True

                if push_to_checkout:
                    await checkout_queue.put(course, discovered_at=discovered_at)
                else:
                    site_key = course.site or "Unknown"
                    source_stats[site_key][course_status] += 1
                    self.processed += 1
                    self.current_course_title = course.title
                    self.current_course_url = course.url or ""
                    await self._save_course(db, run, course, course_status, error_msg)
                    await self._update_run_stats(db, run)

            except Exception as e:
                logger.exception(f"[VALIDATION ERROR] Error validating {course.title}: {e}")
                course_status = "failed"
                error_msg = str(e)
                site_key = course.site or "Unknown"
                source_stats[site_key][course_status] += 1
                self.processed += 1
                await self._save_course(db, run, course, course_status, error_msg)
                await self._update_run_stats(db, run)
            finally:
                validation_queue.task_done()

    async def _run_pipeline_impl(self):
        logger.warning(f"Starting enrollment pipeline for run {self.run_id}")
        db = SessionLocal()
        stop_event = asyncio.Event()
        heartbeat_task: Optional[asyncio.Task] = None
        producer_task: Optional[asyncio.Task] = None
        validation_tasks: list[asyncio.Task] = []
        checkout_task: Optional[asyncio.Task] = None
        abort_event = self.abort_event
        try:
            run = db.get(EnrollmentRun, self.run_id)
            if not run or self.abort_event.is_set() or run.status != "pending":
                logger.info(f"Pipeline {self.run_id} aborted before startup; skipping execution.")
                return

            run.status = "scraping"
            run.last_heartbeat = _utcnow_naive()
            db.commit()
            self.status = "scraping"

            async def _heartbeat_worker(stop_evt: asyncio.Event):
                while not stop_evt.is_set():
                    try:
                        try:
                            await asyncio.wait_for(stop_evt.wait(), timeout=30.0)
                            break
                        except asyncio.TimeoutError:
                            pass

                        def _update_db_heartbeat():
                            from sqlalchemy import text
                            now = _utcnow_naive()
                            with SessionLocal() as heartbeat_db:
                                heartbeat_db.execute(
                                    text(
                                        "UPDATE enrollment_runs SET last_heartbeat = :now "
                                        "WHERE id = :run_id AND status IN ('pending', 'scraping', 'enrolling')"
                                    ),
                                    {"now": now, "run_id": self.run_id},
                                )
                                heartbeat_db.commit()

                        await asyncio.to_thread(_update_db_heartbeat)
                    except asyncio.CancelledError:
                        break
                    except Exception as hb_err:
                        logger.warning(f"Heartbeat worker error for run {self.run_id}: {hb_err}")

            heartbeat_task = asyncio.create_task(_heartbeat_worker(stop_event))

            enabled_sites = [k for k, v in self.settings.get("sites", {}).items() if v]
            logger.warning(f"Enabled sites: {enabled_sites}")
            self.scraper_service = ScraperService(
                enabled_sites,
                # User proxy honored only when ALLOW_USER_PROXY is enabled
                # (server mode hard-disables it — F-ENRL-C05)
                proxy=resolve_user_proxy(self.settings.get("proxy_url")),
                max_workers=self.settings.get("scraper_workers") or self.settings.get("max_scraper_workers"),
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
            source_stats = defaultdict(lambda: {"enrolled": 0, "already_enrolled": 0, "expired": 0, "failed": 0, "excluded": 0, "invalid": 0, "unknown": 0})

            scrapers_succeeded = 0

            validation_queue: asyncio.Queue[Optional[tuple[Course, float]]] = asyncio.Queue()
            checkout_queue = EnrollmentPriorityQueue()

            checkout_task = asyncio.create_task(
                self._checkout_consumer(db, run, checkout_queue, source_stats, abort_event)
            )

            validation_tasks = [
                asyncio.create_task(
                    self._validation_worker(
                        db,
                        run,
                        validation_queue,
                        checkout_queue,
                        enrolled_slugs,
                        previously_attempted,
                        source_stats,
                        abort_event,
                    )
                )
                for _ in range(VALIDATION_WORKERS)
            ]

            async def _producer():
                nonlocal scrapers_succeeded
                try:
                    # Phase 1: Seed candidate queue with verified public deals
                    try:
                        from app.services.public_deals_export import load_public_deals

                        all_deals = load_public_deals() or []
                    except Exception as e:
                        logger.warning(f"Could not load public deals for seeding: {e}")
                        all_deals = []

                    seed_candidates: list[Course] = []
                    for d in all_deals:
                        if not isinstance(d, dict) or not d.get("is_coupon_valid"):
                            continue
                        c = Course.from_deal(d, site="Verified Deals")
                        if not c or not c.url:
                            continue
                        if c.url in seen_slugs:
                            continue
                        if c.slug and c.slug in enrolled_slugs:
                            continue
                        coupon_str = c.coupon_code or ""
                        if c.slug and (c.slug, coupon_str) in previously_attempted:
                            continue
                        seen_slugs.add(c.url)
                        seed_candidates.append(c)
                        if len(seed_candidates) >= MAX_CATALOG_SEED:
                            break

                    if seed_candidates:
                        logger.info(f"Seeding enrollment pipeline with {len(seed_candidates)} verified public deals.")
                        self.total_courses += len(seed_candidates)
                        run.total_courses_found = self.total_courses
                        async with self._db_lock:
                            db.commit()
                        for c in seed_candidates:
                            if abort_event.is_set():
                                break
                            await validation_queue.put((c, time.time()))

                    async for scraper, state in self.scraper_service.stream_results():
                        if abort_event.is_set() or run.status == "failed":
                            break
                        pd = dict(run.progress_data or {})
                        pd["scraping_progress"] = self.scraper_service.get_progress()
                        run.progress_data = pd
                        run.last_heartbeat = _utcnow_naive()
                        async with self._db_lock:
                            db.commit()

                        if state == "completed":
                            scrapers_succeeded += 1

                        for course in scraper.data:
                            if abort_event.is_set():
                                break
                            if not course.url:
                                continue

                            if course.url in seen_slugs:
                                continue
                            seen_slugs.add(course.url)

                            if not course.slug and course.url:
                                # Parse-based slug fallback (no host literal — F-ENRL-C07);
                                # Course.set_slug extracts /course/{slug} from the path.
                                course.set_slug()

                            if course.slug and course.slug in enrolled_slugs:
                                continue

                            coupon = course.coupon_code or ""
                            if course.slug and (course.slug, coupon) in previously_attempted:
                                continue

                            if self.abort_event.is_set():
                                break
                            if self.status == "scraping":
                                async with self._db_lock:
                                    db.refresh(run)
                                    if run.status in ("pending", "scraping") and not self.abort_event.is_set():
                                        run.status = "enrolling"
                                        run.last_heartbeat = _utcnow_naive()
                                        db.commit()
                                        self.status = "enrolling"
                                    else:
                                        self.abort_event.set()
                                        break

                            self.total_courses += 1
                            run.total_courses_found = self.total_courses
                            await validation_queue.put((course, time.time()))
                finally:
                    for _ in range(VALIDATION_WORKERS):
                        await validation_queue.put(None)

            producer_task = asyncio.create_task(_producer())

            async def _monitor_abort():
                await abort_event.wait()
                if producer_task and not producer_task.done():
                    producer_task.cancel()

            abort_monitor_task = asyncio.create_task(_monitor_abort())

            try:
                await producer_task
            except asyncio.CancelledError:
                if not abort_event.is_set():
                    raise
            finally:
                abort_monitor_task.cancel()

            await asyncio.gather(*validation_tasks, return_exceptions=True)
            await checkout_queue.put(None)
            await checkout_task

            pd = dict(run.progress_data or {})
            pd["scraping_progress"] = self.scraper_service.get_progress()
            run.progress_data = pd

            if self.abort_event.is_set():
                logger.info(f"Pipeline {self.run_id} aborted/superseded; skipping completion finalization.")
                return
            async with self._db_lock:
                db.refresh(run)
                if self.abort_event.is_set() or run.status in ("cancelled", "failed"):
                    logger.info(f"Pipeline {self.run_id} already terminal ({run.status}); skipping completion finalization.")
                    return

            if run.status == "failed":
                pass
            elif scrapers_succeeded == 0 and self.total_courses == 0:
                run.status = "failed"
                run.error_message = "All sources failed or timed out and no courses were found."
            else:
                run.status = "completed"

            run.completed_at = _utcnow_naive()
            run.last_heartbeat = _utcnow_naive()
            async with self._db_lock:
                db.commit()
            self.status = run.status

            logger.info("--- Source Telemetry Summary ---")
            for site, stats in source_stats.items():
                total = sum(stats.values())
                logger.info(f"  {site}: {total} processed | {stats['enrolled']} enrolled | {stats['already_enrolled']} already enrolled | {stats['expired']} expired | {stats['failed']} failed | {stats['excluded']} excluded | {stats['invalid']} invalid | {stats['unknown']} unknown")
            logger.info("--------------------------------")
            _health = self.udemy.get_session_health_report()
            logger.info(f"Enrollment pipeline completed. Enrolled: {self.udemy.successfully_enrolled_c}")

            # Merge free coupons from this run into the public catalog (does not
            # replace the whole file from the multi-tenant user DB). Validity
            # re-checks are owned by scripts/coupon_checker.py.
            try:
                n = self._merge_run_into_public_catalog(db)
                logger.info(
                    f"Merged this run into public_deals.json + sitemap "
                    f"({n} catalog deals total)"
                )
            except Exception as e:
                logger.warning(f"Could not merge public_deals after enrollment: {e}")

            # Dispatch webhook notification if configured (Wave 6)
            try:
                from app.services.notifications import NotificationService

                total_proc = sum(sum(stats.values()) for stats in source_stats.values())
                saved_amount = float(
                    getattr(self.udemy, "amount_saved_c", 0.0)
                    or getattr(run, "amount_saved", 0.0)
                    or 0.0
                )
                run_currency = (
                    str(
                        getattr(run, "currency", None)
                        or getattr(self.udemy, "currency", "usd")
                        or "usd"
                    ).strip().lower()
                ) or "usd"
                enrolled_count = int(getattr(self.udemy, "successfully_enrolled_c", 0))
                await NotificationService.send_run_notification_for_user(
                    db=db,
                    user_id=self.user_id,
                    run_id=self.run_id,
                    status=run.status,
                    enrolled_count=enrolled_count,
                    saved_amount=saved_amount,
                    processed_count=total_proc,
                    currency=run_currency,
                )
            except Exception as notif_err:
                logger.warning(f"Could not dispatch run notification: {notif_err}")

        except asyncio.CancelledError:
            logger.info(f"Enrollment pipeline {self.run_id} cancelled")
            abort_event.set()
            for t in [producer_task, *validation_tasks, checkout_task]:
                if t and not t.done():
                    t.cancel()
            tasks_to_gather = [t for t in [producer_task, *validation_tasks, checkout_task] if t]
            if tasks_to_gather:
                await asyncio.gather(*tasks_to_gather, return_exceptions=True)
            cleanup_db = SessionLocal()
            try:
                run = cleanup_db.get(EnrollmentRun, self.run_id)
                # Only record a user-initiated cancel when the run is still
                # active — a sweeper/stop timeout may already have marked it
                # failed (F-ENRL-O01) and must not be overwritten.
                if run and run.status in ("pending", "scraping", "enrolling"):
                    run.status = "cancelled"
                    run.completed_at = _utcnow_naive()
                    cleanup_db.commit()
                try:
                    self._merge_run_into_public_catalog(cleanup_db)
                except Exception as exp:
                    logger.warning(f"public_deals merge on cancel failed: {exp}")
            finally:
                cleanup_db.close()
            raise
        except Exception as e:
            if not self.abort_event.is_set():
                logger.exception("Enrollment pipeline failed")
                # F230: alert on enrollment task failure (webhook OFF unless
                # ALERT_WEBHOOK_URL is set; never raises).
                await send_alert(
                    "enrollment_failed",
                    f"Enrollment run {self.run_id} (user {self.user_id}) failed: {e}",
                    run_id=self.run_id,
                    user_id=self.user_id,
                )
                try:
                    run = db.get(EnrollmentRun, self.run_id)
                    if run and run.status in ("pending", "scraping", "enrolling"):
                        run.status = "failed"
                        run.error_message = str(e)
                        run.completed_at = _utcnow_naive()
                        db.commit()
                    try:
                        self._merge_run_into_public_catalog(db)
                    except Exception as exp:
                        logger.warning(f"public_deals merge on failure failed: {exp}")
                except Exception:
                    pass
        finally:
            if stop_event:
                stop_event.set()
            if heartbeat_task:
                try:
                    await asyncio.wait_for(asyncio.shield(heartbeat_task), timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    heartbeat_task.cancel()
                    try:
                        await asyncio.shield(heartbeat_task)
                    except (asyncio.CancelledError, Exception):
                        pass
                except Exception as e:
                    logger.warning(f"Error shutting down heartbeat worker: {e}")

            clear_user_caches(self.user_id)
            EnrollmentManager.active_tasks.pop(self.run_id, None)
            EnrollmentManager.active_managers.pop(self.run_id, None)
            db.close()
            if self.scraper_service:
                try:
                    await self.scraper_service.http.close()
                except Exception as e:
                    logger.warning(f"Error closing scraper HTTP client: {e}")
            if self.close_client:
                await self.udemy.close()

    async def _wait_for_circuit_breaker(self, db: Session, run: EnrollmentRun) -> bool:
        """Pause queue consumption if the checkout circuit breaker is open, pulsing heartbeats.

        Returns False if the maximum circuit trips ceiling is exceeded (run should halt).
        Returns True once the circuit cooldown has expired and processing can continue.
        """
        if not callable(getattr(self.udemy, "is_checkout_circuit_open", None)):
            return True
        if not self.udemy.is_checkout_circuit_open():
            return True

        if callable(getattr(self.udemy, "has_exceeded_max_circuit_trips", None)) and self.udemy.has_exceeded_max_circuit_trips():
            logger.error(f"Run {self.run_id}: Checkout circuit trip ceiling exceeded. Halting pipeline.")
            return False

        cooldown = self.udemy.get_checkout_circuit_cooldown_remaining() if hasattr(self.udemy, "get_checkout_circuit_cooldown_remaining") else 45.0
        logger.warning(
            f"Run {self.run_id}: Checkout circuit breaker is OPEN. Pausing queue consumption for ~{cooldown:.1f}s."
        )

        while self.udemy.is_checkout_circuit_open():
            if callable(getattr(self.udemy, "has_exceeded_max_circuit_trips", None)) and self.udemy.has_exceeded_max_circuit_trips():
                return False
            rem = self.udemy.get_checkout_circuit_cooldown_remaining() if hasattr(self.udemy, "get_checkout_circuit_cooldown_remaining") else 5.0
            if rem <= 0.0:
                break
            await asyncio.sleep(min(rem, 5.0))
            run.last_heartbeat = _utcnow_naive()
            try:
                async with self._db_lock:
                    db.commit()
            except Exception as e:
                logger.debug(f"Heartbeat pulse commit in circuit wait failed: {e}")
                async with self._db_lock:
                    db.rollback()

        logger.info(f"Run {self.run_id}: Checkout circuit breaker cooled down. Resuming queue consumption.")
        return True

    def _merge_run_into_public_catalog(self, db: Session) -> int:
        """Upsert free coupons from this run into public_deals.json (no full DB replace)."""
        from app.services.public_deals_export import merge_deals_into_public_catalog

        rows = (
            db.query(EnrolledCourse)
            .filter(
                EnrolledCourse.enrollment_run_id == self.run_id,
                EnrolledCourse.coupon_code.isnot(None),
                EnrolledCourse.is_coupon_valid.is_(True),
            )
            .all()
        )
        if not rows:
            return 0

        payload = []
        for c in rows:
            payload.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "url": c.url,
                    "slug": c.slug,
                    "course_id": c.course_id,
                    "coupon_code": c.coupon_code,
                    "price": c.price,
                    "category": c.category,
                    "language": c.language,
                    "rating": c.rating,
                    "is_coupon_valid": True,
                    "enrolled_at": c.enrolled_at.isoformat() + "Z"
                    if c.enrolled_at
                    else None,
                    "last_checked_at": c.last_checked_at.isoformat() + "Z"
                    if c.last_checked_at
                    else None,
                }
            )
        return merge_deals_into_public_catalog(payload)

    async def _update_run_stats(self, db: Session, run: EnrollmentRun):
        """Flush in-memory counters to the run record."""
        async with self._db_lock:
            try:
                run.total_processed = self.processed
                run.successfully_enrolled = self.udemy.successfully_enrolled_c
                run.already_enrolled = self.udemy.already_enrolled_c
                run.expired = self.udemy.expired_c
                run.excluded = self.udemy.excluded_c
                run.amount_saved = float(self.udemy.amount_saved_c)
                run.last_heartbeat = _utcnow_naive()

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
        error_msg: Optional[str] = None,
    ):
        """Save an individual course result to the database."""
        async with self._db_lock:
            try:
                # We record the original price (savings) in the price column for analytics
                # only if status is enrolled. Otherwise it's just 0.0.
                price_val = float(course.list_price or course.price or 0.0)

                # Persist coupon validity so public_deals.json can be rebuilt after runs
                # (same fields the standalone coupon_checker updates).
                coupon_valid = None
                if course.coupon_code:
                    coupon_valid = bool(getattr(course, "is_coupon_valid", False))
                list_price = float(
                    getattr(course, "list_price", None) or course.price or price_val or 0.0
                )
                # Enrolled rows keep savings amount; valid free deals also keep list price for UI
                stored_price = (
                    price_val
                    if status == "enrolled"
                    else (list_price if coupon_valid else 0.0)
                )

                ec = EnrolledCourse(
                    enrollment_run_id=run.id,
                    title=course.title,
                    url=course.url,
                    slug=course.slug,
                    course_id=course.course_id,
                    coupon_code=course.coupon_code,
                    price=stored_price,
                    category=course.category,
                    language=course.language,
                    rating=course.rating,
                    site_source=course.site,
                    status=status,
                    error_message=error_msg or course.error,
                    is_coupon_valid=coupon_valid,
                    last_checked_at=_utcnow_naive() if course.coupon_code else None,
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
