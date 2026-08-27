"""Navigation sidebar component for view switching and appearance settings."""

from __future__ import annotations

from typing import Callable, Dict
import customtkinter

from app.gui.theme import (
    COLOR_DARK_SURFACE,
    COLOR_LIGHT_SURFACE,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
)


class SidebarView(customtkinter.CTkFrame):
    """Left sidebar with navigation buttons, branding, and theme selector."""

    NAV_ITEMS = [
        ("dashboard", "📊 Dashboard"),
        ("scrapers", "🕷 Scrapers (17)"),
        ("filters", "⚙ Filters"),
        ("login", "🔑 Login & Cookies"),
        ("history", "📜 History & Stats"),
    ]

    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(
            master,
            width=220,
            corner_radius=0,
            fg_color=(COLOR_LIGHT_SURFACE, COLOR_DARK_SURFACE),
            **kwargs,
        )
        self.on_navigate = on_navigate
        self.buttons: Dict[str, customtkinter.CTkButton] = {}
        self.active_view = "dashboard"

        # 1. Branding Header
        self.brand_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.brand_frame.pack(fill="x", padx=16, pady=(20, 16))

        self.logo_lbl = customtkinter.CTkLabel(
            self.brand_frame,
            text="🎓 UDEMY ENROLLER",
            font=customtkinter.CTkFont(size=14, weight="bold"),
            text_color=COLOR_PRIMARY,
        )
        self.logo_lbl.pack(anchor="w")

        self.sub_lbl = customtkinter.CTkLabel(
            self.brand_frame,
            text="Desktop Pro Edition",
            font=customtkinter.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self.sub_lbl.pack(anchor="w")

        # Separator line
        self.sep = customtkinter.CTkFrame(self, height=1, fg_color=("gray85", "gray30"))
        self.sep.pack(fill="x", padx=16, pady=(0, 16))

        # 2. Navigation Buttons
        self.nav_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="both", expand=True, padx=12)

        for view_key, label in self.NAV_ITEMS:
            btn = customtkinter.CTkButton(
                self.nav_frame,
                text=label,
                anchor="w",
                height=38,
                corner_radius=8,
                font=customtkinter.CTkFont(size=13),
                fg_color="transparent",
                text_color=("gray20", "gray90"),
                hover_color=(COLOR_PRIMARY, COLOR_PRIMARY_HOVER),
                command=lambda vk=view_key: self._select_view(vk),
            )
            btn.pack(fill="x", pady=3)
            self.buttons[view_key] = btn

        # Highlight default view
        self._highlight_button("dashboard")

        # 3. Theme Toggle at bottom
        self.bottom_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(fill="x", padx=16, pady=16)

        self.theme_lbl = customtkinter.CTkLabel(
            self.bottom_frame,
            text="Appearance Mode",
            font=customtkinter.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self.theme_lbl.pack(anchor="w", pady=(0, 4))

        self.theme_switch = customtkinter.CTkOptionMenu(
            self.bottom_frame,
            values=["Dark", "Light", "System"],
            font=customtkinter.CTkFont(size=12),
            command=self._change_theme,
        )
        self.theme_switch.set("Dark")
        self.theme_switch.pack(fill="x")

    def _select_view(self, view_key: str) -> None:
        if self.active_view == view_key:
            return
        self.active_view = view_key
        self._highlight_button(view_key)
        self.on_navigate(view_key)

    def _highlight_button(self, active_key: str) -> None:
        for vk, btn in self.buttons.items():
            if vk == active_key:
                btn.configure(
                    fg_color=COLOR_PRIMARY,
                    text_color="#FFFFFF",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=("gray20", "gray90"),
                )

    def _change_theme(self, new_mode: str) -> None:
        customtkinter.set_appearance_mode(new_mode.lower())
