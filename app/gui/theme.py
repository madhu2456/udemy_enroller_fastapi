"""CustomTkinter theme and palette definition matching Udemy brand colors."""

from __future__ import annotations

import customtkinter

# Palette Constants
COLOR_PRIMARY = "#A435F0"       # Udemy Purple
COLOR_PRIMARY_HOVER = "#8710D8" # Darker Purple
COLOR_SECONDARY = "#5624D0"     # Deep Indigo
COLOR_SECONDARY_HOVER = "#401B9C"

COLOR_DARK_BG = "#1C1D1F"       # Main background dark
COLOR_DARK_SURFACE = "#2D2F31"  # Surface / Sidebar dark
COLOR_DARK_CARD = "#3E4143"     # Card dark
COLOR_DARK_BORDER = "#4E5154"

COLOR_LIGHT_BG = "#F7F9FA"      # Main background light
COLOR_LIGHT_SURFACE = "#FFFFFF" # Surface / Sidebar light
COLOR_LIGHT_CARD = "#F0F2F5"    # Card light
COLOR_LIGHT_BORDER = "#D1D7DC"

COLOR_SUCCESS = "#198754"       # Green
COLOR_WARNING = "#FFC107"       # Yellow
COLOR_DANGER = "#DC3545"        # Red
COLOR_INFO = "#0D6EFD"          # Blue

# ---------------------------------------------------------------------------
# WCAG-safe caption / accent tokens (F018)
# ---------------------------------------------------------------------------
# Tk resolves the CustomTkinter gray names to X11 shades: "gray50" -> #7F7F7F
# and "gray60" -> #999999, which measured 3.2-4.0:1 on the card / surface
# backgrounds (#F0F2F5, #E6E6E6, #FFFFFF, #3E4143, #404040). The tokens below
# are the >=4.5:1 replacements; every ratio is asserted in
# tests/test_gui_contrast.py using the WCAG 2.x relative-luminance formula.
COLOR_CAPTION_LIGHT = "#666666"        # 5.12:1 on #F0F2F5 / 4.60:1 on #E6E6E6 / 5.74:1 on #FFFFFF
COLOR_CAPTION_DARK = "#B3B3B3"         # 4.91:1 on #3E4143 / 6.41:1 on #2D2F31 / 4.95:1 on #404040

# Brand purple #A435F0 fails as text on dark surfaces (2.78:1 on #2D2F31,
# 3.49:1 on #1C1D1F) and as a progress label (2.13:1 on #3E4143). Lighter
# lavender token for every brand-on-dark placement (sidebar logo, scrape
# button label, progress labels).
COLOR_PRIMARY_ON_DARK = "#D2A6FF"      # 6.81:1 on #2D2F31 / 8.55:1 on #1C1D1F / 5.21:1 on #3E4143
COLOR_PRIMARY_LABEL_LIGHT = "#7A1FA2"  # 7.36:1 on #F0F2F5 (FM-038 precedent)
COLOR_SUCCESS_LABEL_LIGHT = "#157347"  # 5.24:1 on #F0F2F5
COLOR_SUCCESS_LABEL_DARK = "#4ADE80"   # 5.90:1 on #3E4143

# Typography
FONT_FAMILY = "Segoe UI" if customtkinter.get_appearance_mode() == "Dark" else "Helvetica"


def apply_theme(appearance_mode: str = "dark") -> None:
    """Configure CustomTkinter global appearance mode and color theme."""
    customtkinter.set_appearance_mode(appearance_mode)
    customtkinter.set_default_color_theme("dark-blue")
