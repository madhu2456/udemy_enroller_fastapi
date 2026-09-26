"""Main CustomTkinter application window for Udemy Enroller Desktop Edition."""

from __future__ import annotations

import os
import sys
from typing import Dict

import customtkinter

# Headless guard — fail-closed: desktop UI requires DISPLAY/WAYLAND_DISPLAY on Linux
if sys.platform.startswith("linux") and not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
    # Import-time guard for direct module execution; runtime guard also in __init__
    # Allows test collection without display but blocks GUI launch headlessly.
    pass

from app.gui.bridge import AsyncioBridge
from app.gui.theme import apply_theme
from app.gui.views.dashboard import DashboardView
from app.gui.views.filters_view import FiltersView
from app.gui.views.history_view import HistoryView
from app.gui.views.login_view import LoginView
from app.gui.views.scrapers_view import ScrapersView
from app.gui.views.sidebar import SidebarView


class UdemyEnrollerApp(customtkinter.CTk):
    """Main desktop application coordinating UI views and the Asyncio background bridge."""

    def __init__(self, **kwargs):
        # Headless DISPLAY guard — fail-closed (FM-037 companion to gui.py guard)
        if sys.platform.startswith("linux") and not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
            raise SystemExit(
                "[ERROR] No graphical display detected (DISPLAY or WAYLAND_DISPLAY not set). "
                "Run the CLI instead: python cli.py --help"
            )
        super().__init__(**kwargs)
        apply_theme("dark")

        # Ensure SQLite tables exist on fresh installations
        try:
            from app.models.database import create_tables

            create_tables()
        except Exception:
            pass

        self.title("Udemy Course Enroller — Desktop Pro")
        self.geometry("1100x720")
        self.minsize(900, 600)

        # 1. Initialize Asyncio Bridge
        self.bridge = AsyncioBridge()
        self.bridge.start()

        # 2. Layout Skeleton: Left Sidebar + Right Content Area
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar = SidebarView(self, on_navigate=self._navigate_to_view)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.content_container = customtkinter.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew")
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # 3. Instantiate Views
        self.views: Dict[str, customtkinter.CTkFrame] = {}

        self.dashboard_view = DashboardView(
            self.content_container,
            on_start_enroll=self._handle_start_enroll,
            on_pause=self._handle_pause,
            on_resume=self._handle_resume,
            on_stop=self._handle_stop,
            on_scrape_only=self._handle_scrape_only,
        )
        self.views["dashboard"] = self.dashboard_view

        self.scrapers_view = ScrapersView(self.content_container)
        self.views["scrapers"] = self.scrapers_view

        self.filters_view = FiltersView(self.content_container)
        self.views["filters"] = self.filters_view

        self.login_view = LoginView(
            self.content_container,
            on_auto_extract=self._handle_auto_extract_cookies,
            on_test_login=self._handle_test_login,
            on_clear_session=self._handle_clear_session,
        )
        self.views["login"] = self.login_view

        self.history_view = HistoryView(
            self.content_container,
            on_refresh_stats=self._handle_fetch_stats,
            on_export=self._handle_export_history,
        )
        self.views["history"] = self.history_view

        # Show default view
        self._navigate_to_view("dashboard")

        # 4. Schedule periodic IPC event polling (50ms)
        self.after(50, self._poll_bridge_events)

        # 5. Window close protocol
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-restore saved session or scan cookies on startup
        self.bridge.send_command("RESTORE_SAVED_SESSION", {"browser": "auto"})

    def _navigate_to_view(self, view_key: str) -> None:
        """Switch visible view in content container."""
        for key, view_frame in self.views.items():
            if key == view_key:
                view_frame.grid(row=0, column=0, sticky="nsew")
                if key == "history":
                    self._handle_fetch_stats()
            else:
                view_frame.grid_forget()

    def _poll_bridge_events(self) -> None:
        """Poll events from the background bridge and dispatch to UI widgets."""
        try:
            events = self.bridge.poll_events(max_count=50)
            for ev in events:
                try:
                    ev_type = ev.get("event")
                    data = ev.get("data", {})

                    if ev_type == "LOG":
                        self.dashboard_view.log_box.append_log(data.get("message", ""), level=data.get("level", "INFO"))

                    elif ev_type == "AUTH_SUCCESS":
                        self.dashboard_view.update_user_header(
                            name=data.get("display_name", "Udemy User"),
                            currency=data.get("currency", "USD"),
                            library_count=data.get("library_count", 0),
                        )
                        self.login_view.set_auth_success(data)

                    elif ev_type == "AUTH_FAILED":
                        self.login_view.set_auth_failed(data.get("error", "Authentication failed"), notes=data.get("notes"))

                    elif ev_type == "COOKIES_EXTRACTED":
                        self.login_view.set_auth_success(data)
                        # T6-2: send FULL auth directly (no get_credentials re-read -> no stale-entry skew).
                        auth = (data.get("auth") or data) if isinstance(data, dict) else {}
                        self.bridge.send_command("TEST_LOGIN", dict(auth) if isinstance(auth, dict) else {})

                    elif ev_type == "COOKIES_EXTRACTED_FAILED":
                        self.login_view.set_auth_failed(data.get("error", "Failed to extract cookies"), notes=data.get("notes"))

                    elif ev_type == "SCRAPER_PROGRESS":
                        completed = data.get("completed", 0)
                        total = data.get("total", 17)
                        site = data.get("site_name", "")
                        self.dashboard_view.progress_widget.update_scraper_progress(completed, total, status_text=f"({site})")

                    elif ev_type == "ENROLL_PROGRESS":
                        completed = data.get("completed", 0)
                        total = data.get("total", 0)
                        self.dashboard_view.progress_widget.update_enroll_progress(completed, total)

                    elif ev_type == "KPI_UPDATE":
                        enrolled = data.get("enrolled", 0)
                        already = data.get("already_enrolled", 0)
                        money_saved = data.get("money_saved", 0.0)
                        total_scraped = data.get("total_scraped", 0)

                        self.dashboard_view.kpi_enrolled.update_value(str(enrolled), subtitle=f"{already} already owned")
                        self.dashboard_view.kpi_saved.update_value(f"${money_saved:,.2f}")
                        self.dashboard_view.kpi_scraped.update_value(str(total_scraped))

                        total_attempted = enrolled + data.get("expired", 0)
                        if total_attempted > 0:
                            rate = (enrolled / total_attempted) * 100
                            self.dashboard_view.kpi_success_rate.update_value(f"{rate:.1f}%")

                    elif ev_type == "COURSE_PROCESSED":
                        self.dashboard_view.add_course_result_row(data)

                    elif ev_type == "STATUS_CHANGE":
                        self.dashboard_view.update_status_badge(data.get("status", "IDLE"))

                    elif ev_type == "RUN_FINISHED":
                        self.dashboard_view.reset_controls()

                    elif ev_type == "STATS_LOADED":
                        self.history_view.populate_runs(data.get("runs", []))
                except Exception:
                    pass
        finally:
            # Reschedule next poll, absorbing teardown errors if window is destroyed
            try:
                self.after(50, self._poll_bridge_events)
            except Exception:
                pass

    def _handle_start_enroll(self) -> None:
        creds = self.login_view.get_credentials()
        sites = self.scrapers_view.get_selected_scrapers()
        filters = self.filters_view.get_filter_settings()

        payload = {
            "access_token": creds.get("access_token"),
            "client_id": creds.get("client_id"),
            "csrf_token": creds.get("csrf_token"),
            "sites": sites,
            "filters": filters,
        }
        self.bridge.send_command("START_ENROLL", payload)

    def _handle_scrape_only(self) -> None:
        sites = self.scrapers_view.get_selected_scrapers()
        self.bridge.send_command("SCRAPE_ONLY", {"sites": sites})

    def _handle_pause(self) -> None:
        self.bridge.send_command("PAUSE")

    def _handle_resume(self) -> None:
        self.bridge.send_command("RESUME")

    def _handle_stop(self) -> None:
        self.bridge.send_command("STOP")

    def _handle_auto_extract_cookies(self, browser: str) -> None:
        self.bridge.send_command("AUTO_EXTRACT_COOKIES", {"browser": browser})

    def _handle_test_login(self, creds: Dict[str, str]) -> None:
        self.bridge.send_command("TEST_LOGIN", creds)

    def _handle_clear_session(self) -> None:
        self.bridge.send_command("CLEAR_SAVED_SESSION")

    def _handle_fetch_stats(self) -> None:
        self.bridge.send_command("FETCH_STATS")

    def _handle_export_history(self, file_path: str) -> None:
        self.bridge.send_command("EXPORT_HISTORY", {"file_path": file_path})

    def _on_close(self) -> None:
        """Handle window close."""
        self.bridge.stop()
        self.destroy()
