"""FIFO 1,000-line ring buffer log console with auto-scroll and color tags."""

from __future__ import annotations

import collections
import datetime
import customtkinter

from app.gui.theme import (
    COLOR_DARK_BG,
    COLOR_DARK_CARD,
    COLOR_LIGHT_BG,
    COLOR_LIGHT_CARD,
)


class LogBox(customtkinter.CTkFrame):
    """Circular ring buffer logging console with auto-scroll and controls."""

    def __init__(self, master, max_lines: int = 1000, **kwargs):
        super().__init__(
            master,
            corner_radius=10,
            fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD),
            **kwargs,
        )
        self.max_lines = max_lines
        self.log_buffer: collections.deque = collections.deque(maxlen=max_lines)
        self.auto_scroll_enabled = True

        # Header toolbar
        self.toolbar = customtkinter.CTkFrame(self, fg_color="transparent", height=32)
        self.toolbar.pack(fill="x", padx=8, pady=(6, 4))

        self.title_lbl = customtkinter.CTkLabel(
            self.toolbar,
            text="EXECUTION LOGS",
            font=customtkinter.CTkFont(size=11, weight="bold"),
            text_color=("gray50", "gray70"),
        )
        self.title_lbl.pack(side="left", padx=4)

        # Clear button
        self.clear_btn = customtkinter.CTkButton(
            self.toolbar,
            text="Clear",
            width=50,
            height=24,
            font=customtkinter.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray80"),
            command=self.clear_logs,
        )
        self.clear_btn.pack(side="right", padx=4)

        # Auto-scroll checkbox
        self.autoscroll_cb = customtkinter.CTkCheckBox(
            self.toolbar,
            text="Auto-scroll",
            font=customtkinter.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18,
            command=self._toggle_autoscroll,
        )
        self.autoscroll_cb.select()
        self.autoscroll_cb.pack(side="right", padx=8)

        # Textbox for logs
        self.textbox = customtkinter.CTkTextbox(
            self,
            corner_radius=8,
            fg_color=(COLOR_LIGHT_BG, COLOR_DARK_BG),
            font=customtkinter.CTkFont(family="Courier", size=12),
            wrap="none",
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.textbox.configure(state="disabled")

    def _toggle_autoscroll(self) -> None:
        self.auto_scroll_enabled = bool(self.autoscroll_cb.get())

    def append_log(self, text: str, level: str = "INFO") -> None:
        """Append a log line with timestamp and level prefix."""
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = f"[{now_str}] [{level.upper():<7}]"
        line = f"{prefix} {text}"

        self.log_buffer.append(line)

        self.textbox.configure(state="normal")
        self.textbox.insert("end", line + "\n")

        # Trim text in textbox if lines exceed buffer capacity
        line_count = int(float(self.textbox.index("end-1c").split(".")[0]))
        if line_count > self.max_lines:
            self.textbox.delete("1.0", f"{line_count - self.max_lines}.0")

        if self.auto_scroll_enabled:
            self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear_logs(self) -> None:
        """Clear all logs in buffer and textbox."""
        self.log_buffer.clear()
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
