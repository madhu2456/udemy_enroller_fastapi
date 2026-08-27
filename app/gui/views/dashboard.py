"""Main dashboard view featuring profile header, action toolbar, KPI metrics, dual progress, and live results."""

from __future__ import annotations

from typing import Any, Callable, Dict
import customtkinter

from app.gui.components.kpi_card import KPICard
from app.gui.components.log_box import LogBox
from app.gui.components.progress_bar import DualProgressBar
from app.gui.theme import (
    COLOR_DANGER,
    COLOR_DARK_CARD,
    COLOR_INFO,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
)


class DashboardView(customtkinter.CTkFrame):
    """Main dashboard view combining status header, controls, KPIs, and results/logs."""

    def __init__(
        self,
        master,
        on_start_enroll: Callable[[], None],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_stop: Callable[[], None],
        on_scrape_only: Callable[[], None],
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_start_enroll = on_start_enroll
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop
        self.on_scrape_only = on_scrape_only

        self.is_paused = False
        self.is_running = False

        # 1. Profile / Connection Header
        self.header_card = customtkinter.CTkFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.header_card.pack(fill="x", padx=16, pady=(16, 10))

        self.header_left = customtkinter.CTkFrame(self.header_card, fg_color="transparent")
        self.header_left.pack(side="left", padx=16, pady=12)

        self.user_title = customtkinter.CTkLabel(
            self.header_left,
            text="👤 NOT CONNECTED",
            font=customtkinter.CTkFont(size=16, weight="bold"),
            text_color=("gray20", "gray90"),
        )
        self.user_title.pack(anchor="w")

        self.user_subtitle = customtkinter.CTkLabel(
            self.header_left,
            text="Extract cookies from browser or enter token in Login tab",
            font=customtkinter.CTkFont(size=12),
            text_color=("gray50", "gray60"),
        )
        self.user_subtitle.pack(anchor="w")

        self.status_badge = customtkinter.CTkLabel(
            self.header_card,
            text="IDLE",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            fg_color=("gray85", "gray30"),
            text_color=("gray30", "gray80"),
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side="right", padx=16)

        # 2. Action Toolbar
        self.toolbar = customtkinter.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=16, pady=(0, 10))

        self.start_btn = customtkinter.CTkButton(
            self.toolbar,
            text="▶ Start Auto-Enroll",
            font=customtkinter.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            height=36,
            command=self._on_start_click,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = customtkinter.CTkButton(
            self.toolbar,
            text="⏸ Pause",
            font=customtkinter.CTkFont(size=13),
            fg_color=("gray80", "gray30"),
            text_color=("gray10", "gray90"),
            height=36,
            width=80,
            command=self._on_pause_click,
            state="disabled",
        )
        self.pause_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = customtkinter.CTkButton(
            self.toolbar,
            text="⏹ Stop",
            font=customtkinter.CTkFont(size=13),
            fg_color=COLOR_DANGER,
            height=36,
            width=80,
            command=self._on_stop_click,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(0, 8))

        self.scrape_btn = customtkinter.CTkButton(
            self.toolbar,
            text="🕷 Scrape Only",
            font=customtkinter.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_PRIMARY,
            text_color=(COLOR_PRIMARY, COLOR_PRIMARY),
            height=36,
            command=self.on_scrape_only,
        )
        self.scrape_btn.pack(side="left")

        # 3. KPI Metrics Grid (4 columns)
        self.kpi_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.kpi_frame.pack(fill="x", padx=16, pady=(0, 10))
        self.kpi_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")

        self.kpi_enrolled = KPICard(self.kpi_frame, title="Courses Enrolled", initial_value="0", subtitle="Added to library", accent_color=COLOR_SUCCESS)
        self.kpi_enrolled.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.kpi_saved = KPICard(self.kpi_frame, title="Money Saved", initial_value="$0.00", subtitle="Estimated retail value", accent_color=COLOR_PRIMARY)
        self.kpi_saved.grid(row=0, column=1, sticky="ew", padx=6)

        self.kpi_scraped = KPICard(self.kpi_frame, title="Coupons Scraped", initial_value="0", subtitle="From 17 providers", accent_color=COLOR_INFO)
        self.kpi_scraped.grid(row=0, column=2, sticky="ew", padx=6)

        self.kpi_success_rate = KPICard(self.kpi_frame, title="Success Rate", initial_value="100%", subtitle="Free checkout ratio", accent_color=COLOR_WARNING)
        self.kpi_success_rate.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # 4. Dual Progress Bars
        self.progress_widget = DualProgressBar(self)
        self.progress_widget.pack(fill="x", padx=16, pady=(0, 10))

        # 5. Tabview for Live Results & Logs
        self.tabs = customtkinter.CTkTabview(self, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tab_results = self.tabs.add("Live Results")
        self.tab_logs = self.tabs.add("Execution Logs")

        # Results scrollable list
        self.results_list = customtkinter.CTkScrollableFrame(self.tab_results, fg_color="transparent")
        self.results_list.pack(fill="both", expand=True)

        self.empty_results_lbl = customtkinter.CTkLabel(
            self.results_list,
            text="No courses processed yet. Click 'Start Auto-Enroll' to begin.",
            text_color=("gray50", "gray60"),
            font=customtkinter.CTkFont(size=13),
        )
        self.empty_results_lbl.pack(pady=40)

        # Log Console
        self.log_box = LogBox(self.tab_logs)
        self.log_box.pack(fill="both", expand=True)

    def _on_start_click(self) -> None:
        self.is_running = True
        self.is_paused = False
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="⏸ Pause")
        self.stop_btn.configure(state="normal")
        self.scrape_btn.configure(state="disabled")
        self.on_start_enroll()

    def _on_pause_click(self) -> None:
        if not self.is_paused:
            self.is_paused = True
            self.pause_btn.configure(text="▶ Resume")
            self.on_pause()
        else:
            self.is_paused = False
            self.pause_btn.configure(text="⏸ Pause")
            self.on_resume()

    def _on_stop_click(self) -> None:
        self.is_running = False
        self.is_paused = False
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="⏸ Pause")
        self.stop_btn.configure(state="disabled")
        self.scrape_btn.configure(state="normal")
        self.on_stop()

    def reset_controls(self) -> None:
        """Reset buttons back to idle state."""
        self.is_running = False
        self.is_paused = False
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="⏸ Pause")
        self.stop_btn.configure(state="disabled")
        self.scrape_btn.configure(state="normal")

    def update_user_header(self, name: str, currency: str, library_count: int) -> None:
        """Update top profile card with authenticated user information."""
        self.user_title.configure(text=f"👤 {name.upper()}")
        self.user_subtitle.configure(text=f"Currency: {currency} • {library_count} courses in your library")
        self.status_badge.configure(text="CONNECTED", fg_color=COLOR_SUCCESS, text_color="#FFFFFF")

    def update_status_badge(self, status: str) -> None:
        """Update the status pill badge."""
        st_upper = status.upper()
        if st_upper in ("RUNNING", "ENROLLING", "SCRAPING"):
            self.status_badge.configure(text=st_upper, fg_color=COLOR_PRIMARY, text_color="#FFFFFF")
        elif st_upper == "PAUSED":
            self.status_badge.configure(text="PAUSED", fg_color=COLOR_WARNING, text_color="#000000")
        elif st_upper == "STOPPED":
            self.status_badge.configure(text="STOPPED", fg_color=COLOR_DANGER, text_color="#FFFFFF")
        else:
            self.status_badge.configure(text="IDLE", fg_color=("gray85", "gray30"), text_color=("gray30", "gray80"))

    def add_course_result_row(self, course_data: Dict[str, Any]) -> None:
        """Add a course item row into the live results list."""
        if self.empty_results_lbl.winfo_ismapped():
            self.empty_results_lbl.pack_forget()

        # Keep latest 300 rows to ensure UI rendering remains 60fps fast
        children = self.results_list.winfo_children()
        if len(children) > 300:
            try:
                children[0].destroy()
            except Exception:
                pass

        row = customtkinter.CTkFrame(self.results_list, corner_radius=8, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        row.pack(fill="x", pady=3)

        title = course_data.get("title", "Untitled Course")
        source = course_data.get("source", "Web")
        price = course_data.get("price", 0.0)
        status = course_data.get("status", "ENROLLED")
        instructor = course_data.get("instructor", "Unknown")

        status_color = COLOR_SUCCESS if status == "ENROLLED" else COLOR_WARNING if status == "ALREADY ENROLLED" else COLOR_DANGER

        # Left column: Title & details
        left_col = customtkinter.CTkFrame(row, fg_color="transparent")
        left_col.pack(side="left", padx=12, pady=8, fill="x", expand=True)

        title_lbl = customtkinter.CTkLabel(
            left_col,
            text=title,
            font=customtkinter.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        title_lbl.pack(fill="x")

        sub_lbl = customtkinter.CTkLabel(
            left_col,
            text=f"Instructor: {instructor} • Source: {source} • Value: ${price:.2f}",
            font=customtkinter.CTkFont(size=11),
            text_color=("gray50", "gray60"),
            anchor="w",
        )
        sub_lbl.pack(fill="x")

        # Right column: Status badge
        badge = customtkinter.CTkLabel(
            row,
            text=status,
            font=customtkinter.CTkFont(size=11, weight="bold"),
            fg_color=status_color,
            text_color="#FFFFFF",
            corner_radius=6,
            padx=10,
            pady=4,
        )
        badge.pack(side="right", padx=12)
