"""Styled dual progress meter widget for Scraper and Enrollment stages."""

from __future__ import annotations

import customtkinter

from app.gui.theme import (
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_LABEL_LIGHT,
    COLOR_PRIMARY_ON_DARK,
    COLOR_SUCCESS,
    COLOR_SUCCESS_LABEL_DARK,
    COLOR_SUCCESS_LABEL_LIGHT,
)


class DualProgressBar(customtkinter.CTkFrame):
    """Dual progress meter displaying both scraper and enrollment progress."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=10,
            fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD),
            **kwargs,
        )

        # 1. Scraper Progress Bar
        self.scraper_header = customtkinter.CTkFrame(self, fg_color="transparent")
        self.scraper_header.pack(fill="x", padx=12, pady=(10, 2))

        self.scraper_title = customtkinter.CTkLabel(
            self.scraper_header,
            text="COUPON SCRAPERS",
            font=customtkinter.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray70"),
        )
        self.scraper_title.pack(side="left")

        self.scraper_pct = customtkinter.CTkLabel(
            self.scraper_header,
            text="0 / 17 (0%)",
            font=customtkinter.CTkFont(size=11),
            # F018: #A435F0 measured 4.31:1 light / 2.13:1 dark on this card.
            text_color=(COLOR_PRIMARY_LABEL_LIGHT, COLOR_PRIMARY_ON_DARK),
        )
        self.scraper_pct.pack(side="right")

        self.scraper_bar = customtkinter.CTkProgressBar(
            self,
            height=8,
            progress_color=COLOR_PRIMARY,
        )
        self.scraper_bar.set(0.0)
        self.scraper_bar.pack(fill="x", padx=12, pady=(2, 8))

        # 2. Enrollment Progress Bar
        self.enroll_header = customtkinter.CTkFrame(self, fg_color="transparent")
        self.enroll_header.pack(fill="x", padx=12, pady=(4, 2))

        self.enroll_title = customtkinter.CTkLabel(
            self.enroll_header,
            text="COURSE ENROLLMENT",
            font=customtkinter.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray70"),
        )
        self.enroll_title.pack(side="left")

        self.enroll_pct = customtkinter.CTkLabel(
            self.enroll_header,
            text="0 / 0 (0%)",
            font=customtkinter.CTkFont(size=11),
            # F018: #198754 measured 4.04:1 light / 2.27:1 dark on this card.
            text_color=(COLOR_SUCCESS_LABEL_LIGHT, COLOR_SUCCESS_LABEL_DARK),
        )
        self.enroll_pct.pack(side="right")

        self.enroll_bar = customtkinter.CTkProgressBar(
            self,
            height=8,
            progress_color=COLOR_SUCCESS,
        )
        self.enroll_bar.set(0.0)
        self.enroll_bar.pack(fill="x", padx=12, pady=(2, 10))

    def update_scraper_progress(self, completed: int, total: int, status_text: str = "") -> None:
        """Update scraper progress bar and counter label."""
        total = max(1, total)
        ratio = min(1.0, max(0.0, completed / total))
        self.scraper_bar.set(ratio)
        pct = int(ratio * 100)
        self.scraper_pct.configure(text=f"{completed} / {total} ({pct}%) {status_text}".strip())

    def update_enroll_progress(self, completed: int, total: int, status_text: str = "") -> None:
        """Update enrollment progress bar and counter label."""
        total = max(1, total)
        ratio = min(1.0, max(0.0, completed / total))
        self.enroll_bar.set(ratio)
        pct = int(ratio * 100)
        self.enroll_pct.configure(text=f"{completed} / {total} ({pct}%) {status_text}".strip())

    def reset(self) -> None:
        """Reset both progress meters to zero."""
        self.scraper_bar.set(0.0)
        self.scraper_pct.configure(text="0 / 17 (0%)")
        self.enroll_bar.set(0.0)
        self.enroll_pct.configure(text="0 / 0 (0%)")
