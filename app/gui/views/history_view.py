"""Run history and lifetime statistics view with CSV/JSON export."""

from __future__ import annotations

from typing import Any, Callable, Dict, List
import customtkinter
from tkinter import filedialog

from app.gui.theme import (
    COLOR_CAPTION_DARK,
    COLOR_CAPTION_LIGHT,
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
)


class HistoryView(customtkinter.CTkFrame):
    """View displaying historical enrollment runs and data export controls."""

    def __init__(
        self,
        master,
        on_refresh_stats: Callable[[], None],
        on_export: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_refresh_stats = on_refresh_stats
        self.on_export = on_export

        # 1. Header Toolbar
        self.header = customtkinter.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=16, pady=(16, 12))

        self.title_lbl = customtkinter.CTkLabel(
            self.header,
            text="📜 ENROLLMENT RUN HISTORY",
            font=customtkinter.CTkFont(size=15, weight="bold"),
        )
        self.title_lbl.pack(side="left")

        self.export_json_btn = customtkinter.CTkButton(
            self.header,
            text="Export JSON",
            font=customtkinter.CTkFont(size=12),
            width=90,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_PRIMARY,
            text_color=(COLOR_PRIMARY, COLOR_PRIMARY),
            command=self._on_export_json,
        )
        self.export_json_btn.pack(side="right", padx=(6, 0))

        self.export_csv_btn = customtkinter.CTkButton(
            self.header,
            text="Export CSV",
            font=customtkinter.CTkFont(size=12),
            width=90,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_PRIMARY,
            text_color=(COLOR_PRIMARY, COLOR_PRIMARY),
            command=self._on_export_csv,
        )
        self.export_csv_btn.pack(side="right", padx=(6, 0))

        self.refresh_btn = customtkinter.CTkButton(
            self.header,
            text="⟳ Refresh",
            font=customtkinter.CTkFont(size=12),
            width=80,
            height=30,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self.on_refresh_stats,
        )
        self.refresh_btn.pack(side="right")

        # 2. Runs Table Container
        self.scroll_table = customtkinter.CTkScrollableFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.scroll_table.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Table Header
        self.th = customtkinter.CTkFrame(self.scroll_table, corner_radius=6, fg_color=("gray85", "gray30"), height=32)
        self.th.pack(fill="x", padx=4, pady=(4, 6))

        customtkinter.CTkLabel(self.th, text="Run ID", width=60, font=customtkinter.CTkFont(size=11, weight="bold")).pack(side="left", padx=6)
        customtkinter.CTkLabel(self.th, text="Started At", width=140, font=customtkinter.CTkFont(size=11, weight="bold")).pack(side="left", padx=6)
        customtkinter.CTkLabel(self.th, text="Status", width=100, font=customtkinter.CTkFont(size=11, weight="bold")).pack(side="left", padx=6)
        customtkinter.CTkLabel(self.th, text="Enrolled", width=80, font=customtkinter.CTkFont(size=11, weight="bold")).pack(side="left", padx=6)
        customtkinter.CTkLabel(self.th, text="Estimated Savings", width=120, font=customtkinter.CTkFont(size=11, weight="bold")).pack(side="left", padx=6)

        self.rows_frame = customtkinter.CTkFrame(self.scroll_table, fg_color="transparent")
        self.rows_frame.pack(fill="both", expand=True)

        self.empty_lbl = customtkinter.CTkLabel(
            self.rows_frame,
            text="No past runs found in database. Click 'Refresh' to load.",
            font=customtkinter.CTkFont(size=12),
            text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
        )
        self.empty_lbl.pack(pady=30)

    def populate_runs(self, runs: List[Dict[str, Any]]) -> None:
        """Populate the historical runs table rows."""
        for child in self.rows_frame.winfo_children():
            child.destroy()

        if not runs:
            self.empty_lbl = customtkinter.CTkLabel(
                self.rows_frame,
                text="No past runs found in database.",
                font=customtkinter.CTkFont(size=12),
                text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
            )
            self.empty_lbl.pack(pady=30)
            return

        for r in runs:
            row_frame = customtkinter.CTkFrame(self.rows_frame, corner_radius=6, fg_color=("gray95", "gray25"), height=36)
            row_frame.pack(fill="x", padx=4, pady=2)

            rid = str(r.get("id", ""))
            started = r.get("started_at", "N/A")
            status = r.get("status", "completed").upper()
            enrolled = str(r.get("enrolled", 0))
            raw_saved = r.get("saved", 0.0)
            if isinstance(raw_saved, str):
                raw_saved = raw_saved.replace("$", "").replace(",", "").strip()
            try:
                saved = f"${float(raw_saved):,.2f}"
            except (ValueError, TypeError):
                saved = "$0.00"

            st_color = COLOR_SUCCESS if status == "COMPLETED" else COLOR_WARNING if status in ("PENDING", "SCRAPING", "ENROLLING") else COLOR_PRIMARY

            customtkinter.CTkLabel(row_frame, text=rid, width=60, font=customtkinter.CTkFont(size=12)).pack(side="left", padx=6)
            customtkinter.CTkLabel(row_frame, text=started, width=140, font=customtkinter.CTkFont(size=12)).pack(side="left", padx=6)

            st_badge = customtkinter.CTkLabel(
                row_frame,
                text=status,
                width=100,
                font=customtkinter.CTkFont(size=11, weight="bold"),
                fg_color=st_color,
                text_color="#FFFFFF",
                corner_radius=4,
                pady=2,
            )
            st_badge.pack(side="left", padx=6)

            customtkinter.CTkLabel(row_frame, text=enrolled, width=80, font=customtkinter.CTkFont(size=12, weight="bold"), text_color=COLOR_SUCCESS).pack(side="left", padx=6)
            customtkinter.CTkLabel(row_frame, text=saved, width=120, font=customtkinter.CTkFont(size=12, weight="bold"), text_color=COLOR_PRIMARY).pack(side="left", padx=6)

    def _on_export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Export History to CSV",
        )
        if path:
            self.on_export(path)

    def _on_export_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Export History to JSON",
        )
        if path:
            self.on_export(path)
