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

# Typography
FONT_FAMILY = "Segoe UI" if customtkinter.get_appearance_mode() == "Dark" else "Helvetica"


def apply_theme(appearance_mode: str = "dark") -> None:
    """Configure CustomTkinter global appearance mode and color theme."""
    customtkinter.set_appearance_mode(appearance_mode)
    customtkinter.set_default_color_theme("dark-blue")
