"""KPI metric card component for displaying dashboard metrics."""

from __future__ import annotations

from typing import Optional
import customtkinter

from app.gui.theme import (
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
)


class KPICard(customtkinter.CTkFrame):
    """Reusable metric card displaying a KPI value, title, and badge."""

    def __init__(
        self,
        master,
        title: str,
        initial_value: str = "0",
        subtitle: Optional[str] = None,
        accent_color: str = COLOR_PRIMARY,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=12,
            fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD),
            **kwargs,
        )
        self.accent_color = accent_color

        # Title Label
        self.title_label = customtkinter.CTkLabel(
            self,
            text=title.upper(),
            font=customtkinter.CTkFont(size=11, weight="bold"),
            text_color=("gray50", "gray70"),
        )
        self.title_label.pack(anchor="w", padx=16, pady=(12, 4))

        # Main Metric Value
        self.value_label = customtkinter.CTkLabel(
            self,
            text=initial_value,
            font=customtkinter.CTkFont(size=26, weight="bold"),
            text_color=self.accent_color,
        )
        self.value_label.pack(anchor="w", padx=16, pady=(0, 4))

        # Subtitle / Info Badge
        self.subtitle_label = customtkinter.CTkLabel(
            self,
            text=subtitle or "",
            font=customtkinter.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        if subtitle:
            self.subtitle_label.pack(anchor="w", padx=16, pady=(0, 12))

    def update_value(self, value: str, subtitle: Optional[str] = None) -> None:
        """Update the displayed metric value and optional subtitle."""
        self.value_label.configure(text=value)
        if subtitle is not None:
            self.subtitle_label.configure(text=subtitle)
            if not self.subtitle_label.winfo_ismapped():
                self.subtitle_label.pack(anchor="w", padx=16, pady=(0, 12))
