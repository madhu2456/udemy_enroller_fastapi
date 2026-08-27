"""Scrapers management view with checklist and quick toggle buttons for 17 coupon sources."""

from __future__ import annotations

from typing import Dict, List
import customtkinter

from app.gui.theme import (
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
)
from app.services.scraper import SCRAPER_REGISTRY


class ScrapersView(customtkinter.CTkFrame):
    """View displaying all 17 supported scrapers with toggle checkboxes and quick controls."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.switches: Dict[str, customtkinter.CTkCheckBox] = {}

        # 1. Header & Counter Card
        self.header_card = customtkinter.CTkFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.header_card.pack(fill="x", padx=16, pady=(16, 12))

        self.title_lbl = customtkinter.CTkLabel(
            self.header_card,
            text="🕷 COUPON SCRAPER SOURCES",
            font=customtkinter.CTkFont(size=15, weight="bold"),
        )
        self.title_lbl.pack(side="left", padx=16, pady=12)

        self.counter_badge = customtkinter.CTkLabel(
            self.header_card,
            text=f"{len(SCRAPER_REGISTRY)} / {len(SCRAPER_REGISTRY)} Active",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_SUCCESS,
            text_color="#FFFFFF",
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self.counter_badge.pack(side="right", padx=16)

        # 2. Action Controls Toolbar
        self.toolbar = customtkinter.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=16, pady=(0, 12))

        self.select_all_btn = customtkinter.CTkButton(
            self.toolbar,
            text="✓ Select All",
            font=customtkinter.CTkFont(size=12),
            width=100,
            height=32,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self.select_all,
        )
        self.select_all_btn.pack(side="left", padx=(0, 8))

        self.deselect_all_btn = customtkinter.CTkButton(
            self.toolbar,
            text="✗ Deselect All",
            font=customtkinter.CTkFont(size=12),
            width=100,
            height=32,
            fg_color=("gray80", "gray30"),
            text_color=("gray10", "gray90"),
            command=self.deselect_all,
        )
        self.deselect_all_btn.pack(side="left")

        # 3. Scraper Checkboxes in Scrollable Grid
        self.scroll_frame = customtkinter.CTkScrollableFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.scroll_frame.columnconfigure((0, 1), weight=1)

        all_scrapers = list(SCRAPER_REGISTRY.keys())
        for idx, scraper_name in enumerate(all_scrapers):
            row = idx // 2
            col = idx % 2

            item_frame = customtkinter.CTkFrame(self.scroll_frame, corner_radius=8, fg_color="transparent")
            item_frame.grid(row=row, column=col, sticky="ew", padx=12, pady=6)

            cb = customtkinter.CTkCheckBox(
                item_frame,
                text=scraper_name,
                font=customtkinter.CTkFont(size=13, weight="bold"),
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=6,
                fg_color=COLOR_PRIMARY,
                hover_color=COLOR_PRIMARY_HOVER,
                command=self._update_counter,
            )
            cb.select()
            cb.pack(side="left", padx=8, pady=8)
            self.switches[scraper_name] = cb

        self._update_counter()

    def _update_counter(self) -> None:
        selected_count = sum(1 for cb in self.switches.values() if cb.get() == 1)
        total = len(self.switches)
        self.counter_badge.configure(text=f"{selected_count} / {total} Active")

    def select_all(self) -> None:
        """Enable all 17 scrapers."""
        for cb in self.switches.values():
            cb.select()
        self._update_counter()

    def deselect_all(self) -> None:
        """Disable all scrapers."""
        for cb in self.switches.values():
            cb.deselect()
        self._update_counter()

    def get_selected_scrapers(self) -> List[str]:
        """Return list of enabled scraper names."""
        return [name for name, cb in self.switches.items() if cb.get() == 1]
