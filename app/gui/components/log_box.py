"""FIFO 1,000-line ring buffer log console with auto-scroll and color tags."""

from __future__ import annotations

import collections
import datetime
import tkinter
import customtkinter

from app.gui.theme import (
    COLOR_CAPTION_DARK,
    COLOR_CAPTION_LIGHT,
    COLOR_DARK_BG,
    COLOR_DARK_CARD,
    COLOR_LIGHT_BG,
    COLOR_LIGHT_CARD,
)


class LogBox(customtkinter.CTkFrame):
    """Circular ring buffer logging console with auto-scroll and controls."""

    # T5-T2: display-side filter; SUCCESS counts as WARNING-visible.
    LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "SUCCESS": 30, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    LEVEL_OPTIONS = ("DEBUG", "INFO", "WARNING", "ERROR")

    def __init__(self, master, max_lines: int = 1000, **kwargs):
        if not isinstance(master, tkinter.Misc):
            # Headless / mock mode: bypass CTkFrame.__init__ to prevent
            # AppearanceModeTracker / ScalingTracker infinite while loops
            # traversing MagicMock.master hierarchies.
            self.master = master
            self.max_lines = max_lines
            self.log_buffer: collections.deque = collections.deque(maxlen=max_lines)
            self.auto_scroll_enabled = True
            self.min_level = "WARNING"
            self.level_menu = None
            self.textbox = None
            self.toolbar = None
            self.title_lbl = None
            self.clear_btn = None
            self.autoscroll_cb = None
            return

        super().__init__(
            master,
            corner_radius=10,
            fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD),
            **kwargs,
        )
        self.max_lines = max_lines
        self.log_buffer: collections.deque = collections.deque(maxlen=max_lines)
        self.auto_scroll_enabled = True
        self.min_level = "WARNING"

        # Header toolbar
        self.toolbar = customtkinter.CTkFrame(self, fg_color="transparent", height=32)
        self.toolbar.pack(fill="x", padx=8, pady=(6, 4))

        self.title_lbl = customtkinter.CTkLabel(
            self.toolbar,
            text="EXECUTION LOGS",
            font=customtkinter.CTkFont(size=11, weight="bold"),
            text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK),
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

        self.level_menu = None
        if isinstance(master, tkinter.Misc):  # real Tk host only; mock masters skip
            try:
                self.level_menu = customtkinter.CTkOptionMenu(
                    self.toolbar, values=list(self.LEVEL_OPTIONS),
                    command=self.set_min_level, width=110, height=24,
                    font=customtkinter.CTkFont(size=11),
                )
                self.level_menu.set(self.min_level)
                self.level_menu.pack(side="right", padx=4)
            except Exception:
                self.level_menu = None

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
        if self.autoscroll_cb is not None:
            self.auto_scroll_enabled = bool(self.autoscroll_cb.get())

    def set_min_level(self, level: str) -> None:
        """Set display filter; buffer retains all, display filters only."""
        lvl = str(level or "WARNING").upper()
        self.min_level = lvl if lvl in self.LEVEL_OPTIONS else "WARNING"
        if self.level_menu is not None:
            try:
                self.level_menu.set(self.min_level)
            except Exception:
                pass
        self._refresh_display()

    def _level_visible(self, level: str) -> bool:
        return self.LEVEL_ORDER.get(str(level or "").upper(), 0) >= self.LEVEL_ORDER.get(self.min_level, 30)

    def _refresh_display(self) -> None:
        if self.textbox is None:
            return
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        shown = [t for lv, t in self.log_buffer if self._level_visible(lv)][-self.max_lines :]
        for text in shown:
            self.textbox.insert("end", text + "\n")
        self.textbox.configure(state="disabled")

    def append_log(self, text: str, level: str = "INFO") -> None:
        """Append a log line with timestamp and level prefix."""
        norm = str(level or "INFO").upper()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = f"[{now_str}] [{norm:<7}]"
        line = f"{prefix} {text}"

        self.log_buffer.append((norm, line))
        if not self._level_visible(norm):
            return

        if self.textbox is not None:
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
        if self.textbox is not None:
            self.textbox.configure(state="normal")
            self.textbox.delete("1.0", "end")
            self.textbox.configure(state="disabled")

    def pack(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().pack(*args, **kwargs)

    def pack_forget(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().pack_forget(*args, **kwargs)

    def grid(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().grid(*args, **kwargs)

    def grid_forget(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().grid_forget(*args, **kwargs)

    def place(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().place(*args, **kwargs)

    def place_forget(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().place_forget(*args, **kwargs)

    def destroy(self):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().destroy()

    def configure(self, *args, **kwargs):
        if not isinstance(self.master, tkinter.Misc):
            return None
        return super().configure(*args, **kwargs)
