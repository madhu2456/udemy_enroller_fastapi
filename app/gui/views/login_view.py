"""Login and browser cookie extraction view for Udemy authentication."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
import customtkinter

from app.gui.theme import (
    COLOR_CAPTION_DARK,
    COLOR_CAPTION_LIGHT,
    COLOR_DANGER,
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
)
from app.services.browser_cookies import list_available_browsers


class LoginView(customtkinter.CTkFrame):
    """View allowing 1-click browser cookie extraction or manual credential input."""

    def __init__(
        self,
        master,
        on_auto_extract: Callable[[str], None],
        on_test_login: Callable[[Dict[str, str]], None],
        on_clear_session: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_auto_extract = on_auto_extract
        self.on_test_login = on_test_login
        self.on_clear_session = on_clear_session

        self.scroll = customtkinter.CTkScrollableFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.scroll.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. 1-Click Browser Extraction Section
        self._build_browser_extraction_section()

        # 2. Manual Credentials Section
        self._build_manual_credentials_section()

        # 3. Session Status Card
        self._build_status_card()

    def _build_browser_extraction_section(self) -> None:
        card = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        card.pack(fill="x", padx=16, pady=(12, 16))

        lbl = customtkinter.CTkLabel(card, text="🚀 1-CLICK BROWSER AUTO-EXTRACTION", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 4))

        sub = customtkinter.CTkLabel(
            card,
            text="Automatically extract active Udemy session cookies from your installed browser without typing passwords.",
            font=customtkinter.CTkFont(size=11),
            text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
        )
        sub.pack(anchor="w", pady=(0, 10))

        row = customtkinter.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x")

        # Browser dropdown
        installed = list_available_browsers()
        browser_choices = ["Auto-Detect"] + [b.title() for b in installed]
        if not installed:
            browser_choices = ["Auto-Detect", "Firefox", "Chrome", "Edge", "Brave", "Opera", "Chromium"]

        self.browser_select = customtkinter.CTkOptionMenu(
            row,
            values=browser_choices,
            font=customtkinter.CTkFont(size=12),
            width=150,
            height=34,
        )
        self.browser_select.set("Auto-Detect")
        self.browser_select.pack(side="left", padx=(0, 10))

        self.extract_btn = customtkinter.CTkButton(
            row,
            text="Extract & Test Cookies",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            height=34,
            command=self._on_extract_click,
        )
        self.extract_btn.pack(side="left")

    def _build_manual_credentials_section(self) -> None:
        card = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        card.pack(fill="x", padx=16, pady=(0, 16))

        lbl = customtkinter.CTkLabel(card, text="🔑 MANUAL CREDENTIALS / EXTENSION TOKENS", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 4))

        sub = customtkinter.CTkLabel(
            card,
            text="Paste your tokens manually or export them from the Udemy Enroller Chrome Extension.",
            font=customtkinter.CTkFont(size=11),
            text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
        )
        sub.pack(anchor="w", pady=(0, 10))

        # Access Token
        tok_lbl = customtkinter.CTkLabel(card, text="Access Token (Required):", font=customtkinter.CTkFont(size=12, weight="bold"))
        tok_lbl.pack(anchor="w")

        tok_row = customtkinter.CTkFrame(card, fg_color="transparent")
        tok_row.pack(fill="x", pady=(2, 8))

        self.token_entry = customtkinter.CTkEntry(
            tok_row,
            placeholder_text="e.g. eyJhbGciOi...",
            show="*",
            height=32,
        )
        self.token_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.show_tok_btn = customtkinter.CTkButton(
            tok_row,
            text="Show",
            width=60,
            height=32,
            fg_color=("gray80", "gray30"),
            text_color=("gray10", "gray90"),
            command=self._toggle_token_visibility,
        )
        self.show_tok_btn.pack(side="right")

        # Client ID
        cid_lbl = customtkinter.CTkLabel(card, text="Client ID (Optional):", font=customtkinter.CTkFont(size=12))
        cid_lbl.pack(anchor="w")

        self.cid_entry = customtkinter.CTkEntry(card, placeholder_text="e.g. c_...", height=32)
        self.cid_entry.pack(fill="x", pady=(2, 8))

        # CSRF Token
        csrf_lbl = customtkinter.CTkLabel(card, text="CSRF Token (Optional):", font=customtkinter.CTkFont(size=12))
        csrf_lbl.pack(anchor="w")

        self.csrf_entry = customtkinter.CTkEntry(card, placeholder_text="e.g. csrftoken value", height=32)
        self.csrf_entry.pack(fill="x", pady=(2, 12))

        # Action Buttons Row
        btn_row = customtkinter.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x")

        self.test_btn = customtkinter.CTkButton(
            btn_row,
            text="✓ Test & Save Session",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_SUCCESS,
            height=34,
            command=self._on_test_click,
        )
        self.test_btn.pack(side="left", padx=(0, 10))

        self.clear_btn = customtkinter.CTkButton(
            btn_row,
            text="Clear Saved Session",
            font=customtkinter.CTkFont(size=12),
            fg_color=("gray80", "gray30"),
            hover_color=COLOR_DANGER,
            text_color=("gray10", "gray90"),
            height=34,
            command=self._on_clear_click,
        )
        self.clear_btn.pack(side="left")

    def _build_status_card(self) -> None:
        self.status_card = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color=("gray90", "gray25"))
        self.status_card.pack(fill="x", padx=16, pady=(0, 16))

        self.status_title = customtkinter.CTkLabel(
            self.status_card,
            text="Connection Status: Not tested",
            font=customtkinter.CTkFont(size=13, weight="bold"),
            text_color=("gray30", "gray70"),
        )
        self.status_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.status_details = customtkinter.CTkLabel(
            self.status_card,
            text="Click 'Extract & Test Cookies' or enter tokens above.",
            font=customtkinter.CTkFont(size=11),
            text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
            justify="left",
        )
        self.status_details.pack(anchor="w", padx=16, pady=(0, 12))

    def _toggle_token_visibility(self) -> None:
        if self.token_entry.cget("show") == "*":
            self.token_entry.configure(show="")
            self.show_tok_btn.configure(text="Hide")
        else:
            self.token_entry.configure(show="*")
            self.show_tok_btn.configure(text="Show")

    def _on_extract_click(self) -> None:
        chosen = self.browser_select.get().lower()
        if chosen == "auto-detect":
            chosen = "auto"
        self.status_title.configure(text="Extracting cookies...", text_color=COLOR_PRIMARY)
        self.on_auto_extract(chosen)

    def _on_test_click(self) -> None:
        tok = self.token_entry.get().strip()
        cid = self.cid_entry.get().strip()
        csrf = self.csrf_entry.get().strip()
        self.status_title.configure(text="Testing session credentials...", text_color=COLOR_PRIMARY)
        self.on_test_login({"access_token": tok, "client_id": cid, "csrf_token": csrf})

    def _on_clear_click(self) -> None:
        self.token_entry.delete(0, "end")
        self.cid_entry.delete(0, "end")
        self.csrf_entry.delete(0, "end")
        self.status_title.configure(text="Session Cleared", text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK))
        self.status_details.configure(text="Saved session credentials have been deleted. Enter new tokens above.")
        if self.on_clear_session:
            self.on_clear_session()

    def set_auth_success(self, data: Dict[str, Any]) -> None:
        """Update view with successful connection status."""
        data = data or {}
        name = data.get("display_name") or data.get("browser_name") or "Udemy User"
        lib = data.get("library_count", 0)
        curr = data.get("currency", "USD")
        self.status_title.configure(text=f"✓ Connected as {name} (Session Saved)", text_color=COLOR_SUCCESS)
        self.status_details.configure(text=f"Library: {lib} courses • Currency: {curr} • Saved for long-term reuse")

        # T6-2 shape-tolerant: AUTH_SUCCESS {full} vs COOKIES {display + auth FULL}.
        tokens = data.get("auth", data) or data
        if not isinstance(tokens, dict):
            tokens = data
        # Fill entries with FULL auth (never display-truncated).
        if tokens.get("access_token"):
            self.token_entry.delete(0, "end")
            self.token_entry.insert(0, tokens["access_token"])
        if tokens.get("client_id"):
            self.cid_entry.delete(0, "end")
            self.cid_entry.insert(0, tokens["client_id"])
        if tokens.get("csrf_token"):
            self.csrf_entry.delete(0, "end")
            self.csrf_entry.insert(0, tokens["csrf_token"])

    def set_auth_failed(self, error: str, notes: Optional[str] = None) -> None:
        """Update view with failed connection status."""
        self.status_title.configure(text="✗ Connection Failed / Expired", text_color=COLOR_DANGER)
        msg = error or "Authentication failed"
        if notes:
            msg += f"\n\nNote: {notes}"
        self.status_details.configure(text=msg)

    def get_credentials(self) -> Dict[str, str]:
        """Return currently entered tokens."""
        return {
            "access_token": self.token_entry.get().strip(),
            "client_id": self.cid_entry.get().strip(),
            "csrf_token": self.csrf_entry.get().strip(),
        }
