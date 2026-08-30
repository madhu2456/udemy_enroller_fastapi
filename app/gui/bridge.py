"""Zero-freeze AsyncioBridge for CustomTkinter GUI.

Runs a dedicated daemon worker thread with its own asyncio event loop and uses
thread-safe queues for bidirectional IPC with the Tkinter UI thread.
"""

from __future__ import annotations

import asyncio
import csv
import json
import queue
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.constants import FM036_PRICE_UNKNOWN  # W3-02: FM036 unknown-price sentinel 9999.0
from app.models.database import EnrollmentRun, SessionLocal
from app.services.browser_cookies import get_udemy_cookies
from app.services.course import Course
from app.services.scraper import SCRAPER_REGISTRY, ScraperService
from app.services.session_store import (
    clear_persistent_session,
    load_persistent_session,
    save_persistent_session,
    verify_and_restore_session,
)
from app.services.udemy_client import UdemyClient


class AsyncioBridge:
    """Thread-safe bridge between Tkinter main UI and background Asyncio worker."""

    def __init__(self):
        self.command_queue: queue.Queue = queue.Queue()
        self.event_queue: queue.Queue = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running: bool = False

        self._pause_event: Optional[asyncio.Event] = None
        self._cancel_requested: bool = False
        self._active_udemy_client: Optional[UdemyClient] = None
        self._is_paused: bool = False

    def start(self) -> None:
        """Start the background worker thread and event loop."""
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, name="GUI-AsyncioBridge", daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        """Stop background worker and terminate event loop."""
        self.running = False
        self._cancel_requested = True
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def send_command(self, command: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Send a command from UI thread to background worker."""
        self.command_queue.put({"command": command, "payload": payload or {}})

    def emit_event(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Push an event from worker to UI queue."""
        self.event_queue.put({"event": event, "data": data or {}})

    def poll_events(self, max_count: int = 100) -> List[Dict[str, Any]]:
        """Retrieve pending events from the queue (called by Tkinter root.after)."""
        events = []
        try:
            while len(events) < max_count:
                item = self.event_queue.get_nowait()
                events.append(item)
        except queue.Empty:
            pass
        return events

    def _worker_loop(self) -> None:
        """Entry point for the background worker thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._process_commands_loop())
        except Exception as e:
            logger.debug(f"Worker loop terminated: {e}")
        finally:
            self.loop.close()

    async def _process_commands_loop(self) -> None:
        """Async loop consuming commands from command_queue."""
        self._pause_event = asyncio.Event()
        self._pause_event.set()

        while self.running:
            try:
                try:
                    cmd_item = self.command_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    continue

                cmd = cmd_item.get("command")
                payload = cmd_item.get("payload", {})

                if cmd == "START_ENROLL":
                    self._cancel_requested = False
                    self._pause_event.set()
                    self._is_paused = False
                    await self._handle_start_enroll(payload)
                elif cmd == "SCRAPE_ONLY":
                    self._cancel_requested = False
                    self._pause_event.set()
                    self._is_paused = False
                    await self._handle_scrape_only(payload)
                elif cmd == "PAUSE":
                    self._is_paused = True
                    if self._pause_event:
                        self._pause_event.clear()
                    self.emit_event("STATUS_CHANGE", {"status": "PAUSED"})
                    self.emit_event("LOG", {"level": "WARNING", "message": "Execution paused by user."})
                elif cmd == "RESUME":
                    self._is_paused = False
                    if self._pause_event:
                        self._pause_event.set()
                    self.emit_event("STATUS_CHANGE", {"status": "RUNNING"})
                    self.emit_event("LOG", {"level": "INFO", "message": "Execution resumed."})
                elif cmd == "STOP":
                    self._cancel_requested = True
                    if self._pause_event:
                        self._pause_event.set()
                    self.emit_event("STATUS_CHANGE", {"status": "STOPPED"})
                    self.emit_event("LOG", {"level": "WARNING", "message": "Stop requested. Halting..."})
                elif cmd == "TEST_LOGIN":
                    await self._handle_test_login(payload)
                elif cmd == "AUTO_EXTRACT_COOKIES":
                    await self._handle_auto_extract_cookies(payload)
                elif cmd == "RESTORE_SAVED_SESSION":
                    await self._handle_restore_saved_session(payload)
                elif cmd == "CLEAR_SAVED_SESSION":
                    await self._handle_clear_saved_session()
                elif cmd == "FETCH_STATS":
                    await self._handle_fetch_stats()
                elif cmd == "EXPORT_HISTORY":
                    await self._handle_export_history(payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.emit_event("LOG", {"level": "ERROR", "message": f"Bridge error: {e}"})

    async def _handle_restore_saved_session(self, payload: Dict[str, Any]) -> None:
        """Check for and restore previously saved persistent Udemy session on startup."""
        self.emit_event("LOG", {"level": "INFO", "message": "Checking for saved Udemy session credentials..."})
        is_valid, client, session_data, err = await verify_and_restore_session()

        if is_valid and session_data:
            self.emit_event("AUTH_SUCCESS", session_data)
            self.emit_event(
                "LOG",
                {
                    "level": "SUCCESS",
                    "message": f"✓ Restored saved session for {session_data['display_name']} ({session_data['library_count']} courses in library). Session active!",
                },
            )
            if client:
                await client.close()
            return

        # If a saved session was found but failed authentication, notify user that it expired
        if session_data and session_data.get("access_token"):
            self.emit_event(
                "AUTH_FAILED",
                {
                    "error": "Saved Udemy session has expired.",
                    "notes": "Udemy session cookies expire every 30-90 days. Please update your tokens in the Login tab.",
                    "access_token": session_data.get("access_token", ""),
                    "client_id": session_data.get("client_id", ""),
                    "csrf_token": session_data.get("csrf_token", ""),
                },
            )
            self.emit_event(
                "LOG",
                {
                    "level": "WARNING",
                    "message": "⚠️ Saved Udemy session has expired. Please update your session cookies in the Login tab.",
                },
            )
            return

        # No saved session exists: try browser auto-extraction fallback
        browser = payload.get("browser", "auto")
        extracted = get_udemy_cookies(browser=browser)
        if extracted.is_valid:
            await self._handle_test_login(extracted.to_dict())
        else:
            self.emit_event(
                "LOG",
                {
                    "level": "INFO",
                    "message": "No saved session found. Enter your cookies in the Login tab to save them for long-term use.",
                },
            )

    async def _handle_clear_saved_session(self) -> None:
        """Wipe saved persistent session upon user request."""
        clear_persistent_session()
        self.emit_event("AUTH_FAILED", {"error": "Saved session cleared.", "notes": "Enter new tokens in the Login tab."})
        self.emit_event("LOG", {"level": "INFO", "message": "Saved session credentials have been cleared."})

    async def _handle_test_login(self, payload: Dict[str, Any]) -> None:
        """Test credentials against Udemy API and persist for long-term use."""
        access_token = payload.get("access_token", "")
        client_id = payload.get("client_id", "")
        csrf_token = payload.get("csrf_token", "")
        browser = payload.get("browser", "auto")

        self.emit_event("LOG", {"level": "INFO", "message": "Testing Udemy session credentials..."})

        if not access_token:
            extracted = get_udemy_cookies(browser=browser)
            if extracted.is_valid:
                access_token = extracted.access_token
                client_id = extracted.client_id
                csrf_token = extracted.csrf_token
                self.emit_event("LOG", {"level": "SUCCESS", "message": f"Extracted credentials from {extracted.browser_name.title()}"})
            else:
                self.emit_event("AUTH_FAILED", {"error": extracted.error or "No browser cookies found", "notes": extracted.notes})
                return

        client = UdemyClient()
        try:
            client.cookie_login(access_token=access_token, client_id=client_id, csrf_token=csrf_token)
            await client.get_session_info()
            if client.is_authenticated:
                try:
                    await client.get_enrolled_courses()
                except Exception as e:
                    self.emit_event("LOG", {"level": "WARNING", "message": f"Could not pre-fetch library: {e}"})
                lib_count = len(client.enrolled_courses or {})
                curr = (client.currency or "USD").upper()

                # Automatically persist valid credentials for long term
                save_persistent_session(
                    cookies={"access_token": access_token, "client_id": client_id, "csrf_token": csrf_token},
                    display_name=client.display_name,
                    user_id=client.udemy_user_id,
                    currency=curr,
                )

                self.emit_event(
                    "AUTH_SUCCESS",
                    {
                        "display_name": client.display_name,
                        "user_id": client.udemy_user_id,
                        "currency": curr,
                        "library_count": lib_count,
                        "access_token": access_token,
                        "client_id": client_id,
                        "csrf_token": csrf_token,
                        "is_saved": True,
                    },
                )
                self.emit_event(
                    "LOG",
                    {
                        "level": "SUCCESS",
                        "message": f"Authenticated as {client.display_name} ({lib_count} courses in library). Session saved for long-term use!",
                    },
                )
            else:
                self.emit_event("AUTH_FAILED", {"error": "Invalid or expired credentials"})
                self.emit_event("LOG", {"level": "ERROR", "message": "Authentication failed: Invalid credentials."})
        except Exception as e:
            self.emit_event("AUTH_FAILED", {"error": str(e) or "Authentication error"})
            self.emit_event("LOG", {"level": "ERROR", "message": f"Authentication error: {e}"})
        finally:
            await client.close()

    async def _handle_auto_extract_cookies(self, payload: Dict[str, Any]) -> None:
        """Auto extract browser cookies."""
        browser = payload.get("browser", "auto")
        self.emit_event("LOG", {"level": "INFO", "message": f"Scanning browser cookies ({browser})..."})
        extracted = get_udemy_cookies(browser=browser)
        if extracted.is_valid:
            self.emit_event("COOKIES_EXTRACTED", extracted.to_dict())
            self.emit_event("LOG", {"level": "SUCCESS", "message": f"Successfully extracted Udemy cookies from {extracted.browser_name.title()}"})
        else:
            self.emit_event("COOKIES_EXTRACTED_FAILED", {"error": extracted.error, "notes": extracted.notes})
            self.emit_event("LOG", {"level": "ERROR", "message": f"Cookie extraction failed: {extracted.error}"})

    async def _handle_fetch_stats(self) -> None:
        """Fetch lifetime database stats and past runs."""
        try:
            with SessionLocal() as db:
                runs = db.query(EnrollmentRun).order_by(EnrollmentRun.started_at.desc()).limit(20).all()
                total_enrolled = sum(r.enrolled_count or 0 for r in runs)
                total_saved = sum(float(r.amount_saved or 0.0) for r in runs)

                runs_data = [
                    {
                        "id": r.id,
                        "started_at": r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "",
                        "status": r.status,
                        "enrolled": r.enrolled_count or 0,
                        "saved": float(r.amount_saved or 0.0),
                    }
                    for r in runs
                ]

                self.emit_event(
                    "STATS_LOADED",
                    {
                        "total_runs": len(runs),
                        "total_enrolled": total_enrolled,
                        "total_saved": total_saved,
                        "runs": runs_data,
                    },
                )
        except Exception as e:
            self.emit_event("LOG", {"level": "ERROR", "message": f"Failed to fetch stats: {e}"})

    async def _handle_export_history(self, payload: Dict[str, Any]) -> None:
        """Export history to file."""
        file_path = payload.get("file_path", "")
        if not file_path:
            return

        try:
            with SessionLocal() as db:
                runs = db.query(EnrollmentRun).order_by(EnrollmentRun.started_at.desc()).all()
                out_path = Path(file_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                if out_path.suffix.lower() == ".json":
                    data = [
                        {
                            "id": r.id,
                            "started_at": str(r.started_at),
                            "completed_at": str(r.completed_at),
                            "status": r.status,
                            "courses_found": r.total_courses_found,
                            "enrolled_count": r.successfully_enrolled,
                            "amount_saved": float(r.amount_saved or 0.0),
                        }
                        for r in runs
                    ]
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                else:
                    with open(out_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["ID", "Started At", "Completed At", "Status", "Courses Found", "Enrolled", "Saved ($)"])
                        for r in runs:
                            writer.writerow([r.id, r.started_at, r.completed_at, r.status, r.total_courses_found, r.successfully_enrolled, r.amount_saved])

            self.emit_event("LOG", {"level": "SUCCESS", "message": f"Exported history to {file_path}"})
        except Exception as e:
            self.emit_event("LOG", {"level": "ERROR", "message": f"Failed to export history: {e}"})

    async def _handle_scrape_only(self, payload: Dict[str, Any]) -> None:
        """Scrape courses without performing checkout."""
        sites = payload.get("sites") or list(SCRAPER_REGISTRY.keys())
        self.emit_event("STATUS_CHANGE", {"status": "SCRAPING"})
        self.emit_event("LOG", {"level": "INFO", "message": f"Starting scraping on {len(sites)} coupon sources..."})

        scraper_service = ScraperService(sites_to_scrape=sites)
        all_courses: List[Course] = []
        completed_scrapers = 0

        async for scraper, state in scraper_service.stream_results():
            if self._cancel_requested:
                break
            completed_scrapers += 1
            all_courses.extend(scraper.courses)
            self.emit_event(
                "SCRAPER_PROGRESS",
                {
                    "completed": completed_scrapers,
                    "total": len(scraper_service.scrapers),
                    "site_name": scraper.site_name,
                    "state": state,
                    "courses_found": len(scraper.courses),
                },
            )
            self.emit_event("LOG", {"level": "INFO", "message": f"[{scraper.site_name}] {state.upper()} - Found {len(scraper.courses)} courses"})

        # Deduplicate
        seen = set()
        unique = []
        for c in all_courses:
            k = getattr(c, "slug", None) or getattr(c, "url", None)
            if k and k not in seen:
                seen.add(k)
                unique.append(c)

        for c in unique:
            inst_list = getattr(c, "instructors", None)
            inst_str = ", ".join(inst_list) if inst_list else getattr(c, "instructor", "Unknown")
            self.emit_event(
                "COURSE_DISCOVERED",
                {
                    "title": c.title,
                    "url": c.url,
                    "instructor": inst_str,
                    "rating": c.rating,
                    "category": c.category,
                    "language": c.language,
                    "price": float(c.price) if c.price else 0.0,
                    "source": getattr(c, "source", "") or getattr(c, "site_name", "") or getattr(c, "site", "Web"),
                    "status": "DISCOVERED",
                },
            )

        self.emit_event("STATUS_CHANGE", {"status": "IDLE"})
        self.emit_event("LOG", {"level": "SUCCESS", "message": f"Scrape complete: {len(unique)} unique courses discovered."})

    async def _handle_start_enroll(self, payload: Dict[str, Any]) -> None:
        """Run the end-to-end background enrollment pipeline."""
        access_token = payload.get("access_token", "")
        client_id = payload.get("client_id", "")
        csrf_token = payload.get("csrf_token", "")
        browser = payload.get("browser", "auto")
        sites = payload.get("sites") or list(SCRAPER_REGISTRY.keys())
        filters = payload.get("filters", {})
        limit = filters.get("limit", 0)

        # 1. Resolve Auth
        if not access_token:
            saved = load_persistent_session()
            if saved and saved.get("access_token"):
                access_token = saved["access_token"]
                client_id = saved.get("client_id", "")
                csrf_token = saved.get("csrf_token", "")
                self.emit_event("LOG", {"level": "INFO", "message": f"Using saved session credentials for {saved.get('display_name', 'Udemy User')}..."})
            else:
                extracted = get_udemy_cookies(browser=browser)
                if extracted.is_valid:
                    access_token = extracted.access_token
                    client_id = extracted.client_id
                    csrf_token = extracted.csrf_token
                else:
                    self.emit_event("LOG", {"level": "ERROR", "message": extracted.error or "No valid cookies found."})
                    self.emit_event("STATUS_CHANGE", {"status": "IDLE"})
                    return

        self._active_udemy_client = UdemyClient()
        try:
            self._active_udemy_client.cookie_login(access_token, client_id, csrf_token)
            self.emit_event("STATUS_CHANGE", {"status": "AUTHENTICATING"})
            self.emit_event("LOG", {"level": "INFO", "message": "Authenticating with Udemy API..."})

            await self._active_udemy_client.get_session_info()
            if not self._active_udemy_client.is_authenticated:
                self.emit_event("LOG", {"level": "ERROR", "message": "Failed to authenticate session. The session cookies may have expired."})
                self.emit_event("STATUS_CHANGE", {"status": "IDLE"})
                return

            try:
                await self._active_udemy_client.get_enrolled_courses()
            except Exception as e:
                self.emit_event("LOG", {"level": "WARNING", "message": f"Could not pre-fetch library: {e}"})
            existing_count = len(self._active_udemy_client.enrolled_courses or {})
            curr = (self._active_udemy_client.currency or "USD").upper()

            # Save valid session for long-term reuse
            save_persistent_session(
                cookies={"access_token": access_token, "client_id": client_id, "csrf_token": csrf_token},
                display_name=self._active_udemy_client.display_name,
                user_id=self._active_udemy_client.udemy_user_id,
                currency=curr,
            )

            self.emit_event("LOG", {"level": "SUCCESS", "message": f"Connected as {self._active_udemy_client.display_name} ({existing_count} existing courses)"})

            # 2. Scrape
            self.emit_event("STATUS_CHANGE", {"status": "SCRAPING"})
            self.emit_event("LOG", {"level": "INFO", "message": f"Scraping {len(sites)} coupon providers..."})

            scraper_service = ScraperService(sites_to_scrape=sites)
            all_courses: List[Course] = []
            completed_scrapers = 0

            async for scraper, state in scraper_service.stream_results():
                if self._cancel_requested:
                    self.emit_event("LOG", {"level": "WARNING", "message": "Run aborted during scraping."})
                    self.emit_event("STATUS_CHANGE", {"status": "IDLE"})
                    return

                completed_scrapers += 1
                all_courses.extend(scraper.courses)
                self.emit_event(
                    "SCRAPER_PROGRESS",
                    {
                        "completed": completed_scrapers,
                        "total": len(scraper_service.scrapers),
                        "site_name": scraper.site_name,
                        "state": state,
                        "courses_found": len(scraper.courses),
                    },
                )

            # Deduplicate
            seen = set()
            unique_courses: List[Course] = []
            for c in all_courses:
                k = getattr(c, "slug", None) or getattr(c, "url", None)
                if k and k not in seen:
                    seen.add(k)
                    unique_courses.append(c)

            self.emit_event("LOG", {"level": "SUCCESS", "message": f"Scraped {len(unique_courses)} unique courses. Starting checkout..."})
            self.emit_event("STATUS_CHANGE", {"status": "ENROLLING"})

            # 3. Enroll
            processed_count = 0
            for course in unique_courses:
                if self._cancel_requested:
                    self.emit_event("LOG", {"level": "WARNING", "message": "Enrollment stopped by user."})
                    break

                if self._pause_event:
                    await self._pause_event.wait()

                if limit and self._active_udemy_client.successfully_enrolled_c >= limit:
                    self.emit_event("LOG", {"level": "INFO", "message": f"Reached max enrollment limit ({limit}). Stopping."})
                    break

                try:
                    # Filter check
                    try:
                        if self._active_udemy_client.is_course_excluded(course, filters):
                            self._active_udemy_client.excluded_c += 1
                            self.emit_event("ENROLL_PROGRESS", {"completed": processed_count + 1, "total": len(unique_courses), "current_title": getattr(course, "title", "")})
                            continue
                    except Exception as e:
                        logger.debug(f"Filter evaluation error for {getattr(course, 'title', '')}: {e}")

                    # Check coupon status on Udemy
                    try:
                        await self._active_udemy_client.check_course(course)
                    except Exception as e:
                        logger.debug(f"Check error: {e}")

                    inst_list = getattr(course, "instructors", None)
                    inst_str = ", ".join(inst_list) if inst_list else getattr(course, "instructor", "Unknown")
                    price_val = float(course.price) if getattr(course, "price", None) else FM036_PRICE_UNKNOWN  # W3-02: 9999.0 fail-closed

                    is_already = getattr(course, "status", "") == "Already Enrolled" or getattr(course, "is_already_enrolled", False)
                    is_exp = (course.error and "expired" in str(course.error).lower()) or getattr(course, "is_expired", False)
                    # FM-036 / W3-02: price-gated free eligibility — fail-closed: price None => not free (FM036_PRICE_UNKNOWN=9999.0)
                    try:
                        _price_float = float(course.price) if course.price is not None else FM036_PRICE_UNKNOWN
                    except (ValueError, TypeError):
                        _price_float = FM036_PRICE_UNKNOWN
                    _coupon_free = bool(course.is_coupon_valid) and _price_float == 0
                    _explicit_free = bool(course.is_free) and _price_float == 0
                    is_valid_free = (_coupon_free or _explicit_free) and not is_exp and course.price is not None
                    is_definitely_paid = course.price is not None and _price_float > 0 and not _coupon_free and not _explicit_free  # noqa: F841 -- FM-036 guard at top before any _cs_get/fetch

                    if is_already:
                        self._active_udemy_client.already_enrolled_c += 1
                        status_text = "ALREADY ENROLLED"
                        self.emit_event("LOG", {"level": "INFO", "message": f"[ALREADY OWNED] {getattr(course, 'title', '')[:45]}"})
                    elif is_exp:
                        self._active_udemy_client.expired_c += 1
                        status_text = "EXPIRED"
                    elif is_valid_free:
                        try:
                            success = await self._active_udemy_client.checkout_single(course)
                        except Exception as e:
                            logger.error(f"Checkout exception for {getattr(course, 'title', '')}: {e}")
                            success = False

                        if success:
                            status_text = "ENROLLED"
                            self.emit_event("LOG", {"level": "SUCCESS", "message": f"★ ENROLLED: {getattr(course, 'title', '')[:45]} (Saved ${price_val:.2f})"})
                        else:
                            status_text = "FAILED"
                            self.emit_event("LOG", {"level": "ERROR", "message": f"✗ Checkout failed: {getattr(course, 'title', '')[:45]}"})
                    else:
                        status_text = "PAID"
                        self._active_udemy_client.expired_c += 1
                        self.emit_event("LOG", {"level": "WARNING", "message": f"[NOT 100% FREE] {getattr(course, 'title', '')[:45]} (Price: {getattr(course, 'currency', '$')}{price_val:.2f})"})

                    self.emit_event(
                        "COURSE_PROCESSED",
                        {
                            "title": getattr(course, "title", "Untitled"),
                            "url": getattr(course, "url", ""),
                            "coupon_code": getattr(course, "coupon_code", ""),
                            "instructor": inst_str,
                            "rating": getattr(course, "rating", None),
                            "price": price_val,
                            "status": status_text,
                            "source": getattr(course, "source", "") or getattr(course, "site_name", "") or getattr(course, "site", "Web"),
                        },
                    )

                    self.emit_event("ENROLL_PROGRESS", {"completed": processed_count + 1, "total": len(unique_courses), "current_title": getattr(course, "title", "")})
                    self.emit_event(
                        "KPI_UPDATE",
                        {
                            "enrolled": self._active_udemy_client.successfully_enrolled_c,
                            "already_enrolled": self._active_udemy_client.already_enrolled_c,
                            "expired": self._active_udemy_client.expired_c,
                            "excluded": self._active_udemy_client.excluded_c,
                            "money_saved": float(self._active_udemy_client.amount_saved_c),
                            "total_scraped": len(unique_courses),
                        },
                    )
                except Exception as course_err:
                    logger.debug(f"Course loop exception for {getattr(course, 'title', 'unknown')}: {course_err}")
                finally:
                    processed_count += 1

            self.emit_event("STATUS_CHANGE", {"status": "IDLE"})
            self.emit_event("LOG", {"level": "SUCCESS", "message": f"Enrollment session complete. Enrolled {self._active_udemy_client.successfully_enrolled_c} courses."})
            self.emit_event("RUN_FINISHED", {})

        finally:
            if self._active_udemy_client:
                await self._active_udemy_client.close()
                self._active_udemy_client = None
