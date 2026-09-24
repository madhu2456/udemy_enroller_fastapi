"""Course filtering settings view for categories, languages, ratings, and exclusions."""

from __future__ import annotations

from typing import Any, Dict
import customtkinter

from app.gui.theme import (
    COLOR_CAPTION_DARK,
    COLOR_CAPTION_LIGHT,
    COLOR_DARK_CARD,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
)

ALL_CATEGORIES = [
    "Development",
    "Business",
    "IT & Software",
    "Office Productivity",
    "Personal Development",
    "Design",
    "Marketing",
    "Lifestyle",
    "Photography & Video",
    "Health & Fitness",
    "Music",
    "Teaching & Academics",
]

ALL_LANGUAGES = [
    "English",
    "Spanish",
    "Portuguese",
    "French",
    "German",
    "Arabic",
    "Hindi",
    "All Languages",
]


class FiltersView(customtkinter.CTkFrame):
    """View allowing users to configure category, language, rating, and keyword filters."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.category_checkboxes: Dict[str, customtkinter.CTkCheckBox] = {}
        self.language_checkboxes: Dict[str, customtkinter.CTkCheckBox] = {}

        # Main scrollable container
        self.scroll = customtkinter.CTkScrollableFrame(self, corner_radius=12, fg_color=(COLOR_LIGHT_CARD, COLOR_DARK_CARD))
        self.scroll.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Rating & Limit Card
        self._build_rating_and_limits_section()

        # 2. Categories Selection
        self._build_categories_section()

        # 3. Languages Selection
        self._build_languages_section()

        # 4. Keyword Exclusions
        self._build_exclusions_section()

    def _build_rating_and_limits_section(self) -> None:
        frame = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(12, 16))

        # Title
        lbl = customtkinter.CTkLabel(frame, text="⚡ ENROLLMENT LIMITS & QUALITY", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 10))

        grid = customtkinter.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1)

        # Min Rating Slider
        left_box = customtkinter.CTkFrame(grid, fg_color="transparent")
        left_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        self.rating_label = customtkinter.CTkLabel(
            left_box,
            text="Minimum Rating: 0.0 ⭐ (Any Rating)",
            font=customtkinter.CTkFont(size=12, weight="bold"),
        )
        self.rating_label.pack(anchor="w")

        self.rating_slider = customtkinter.CTkSlider(
            left_box,
            from_=0.0,
            to=5.0,
            number_of_steps=50,
            progress_color=COLOR_PRIMARY,
            command=self._on_rating_change,
        )
        self.rating_slider.set(0.0)
        self.rating_slider.pack(fill="x", pady=6)

        # Max Limit Entry
        right_box = customtkinter.CTkFrame(grid, fg_color="transparent")
        right_box.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        limit_lbl = customtkinter.CTkLabel(
            right_box,
            text="Max Enrollment Limit (0 = Unlimited):",
            font=customtkinter.CTkFont(size=12, weight="bold"),
        )
        limit_lbl.pack(anchor="w")

        self.limit_entry = customtkinter.CTkEntry(
            right_box,
            placeholder_text="0 (Unlimited)",
            font=customtkinter.CTkFont(size=13),
            height=32,
        )
        self.limit_entry.insert(0, "0")
        self.limit_entry.pack(fill="x", pady=6)

    def _on_rating_change(self, val: float) -> None:
        if val <= 0.1:
            self.rating_label.configure(text="Minimum Rating: 0.0 ⭐ (Any Rating)")
        else:
            self.rating_label.configure(text=f"Minimum Rating: {val:.1f} ⭐")

    def _build_categories_section(self) -> None:
        frame = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(0, 16))

        lbl = customtkinter.CTkLabel(frame, text="📚 CATEGORY FILTERS (Optional)", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 8))

        sub = customtkinter.CTkLabel(frame, text="Select specific categories or leave empty for all categories.", text_color=(COLOR_CAPTION_LIGHT, COLOR_CAPTION_DARK), font=customtkinter.CTkFont(size=11))
        sub.pack(anchor="w", pady=(0, 8))

        grid = customtkinter.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1, 2), weight=1)

        for idx, cat in enumerate(ALL_CATEGORIES):
            r = idx // 3
            c = idx % 3
            cb = customtkinter.CTkCheckBox(grid, text=cat, font=customtkinter.CTkFont(size=12), fg_color=COLOR_PRIMARY)
            cb.grid(row=r, column=c, sticky="w", padx=4, pady=4)
            self.category_checkboxes[cat] = cb

    def _build_languages_section(self) -> None:
        frame = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(0, 16))

        lbl = customtkinter.CTkLabel(frame, text="🌐 LANGUAGE FILTERS", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 8))

        grid = customtkinter.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1, 2, 3), weight=1)

        for idx, lang in enumerate(ALL_LANGUAGES):
            r = idx // 4
            c = idx % 4
            cb = customtkinter.CTkCheckBox(grid, text=lang, font=customtkinter.CTkFont(size=12), fg_color=COLOR_PRIMARY)
            if lang == "All Languages":
                cb.select()
            cb.grid(row=r, column=c, sticky="w", padx=4, pady=4)
            self.language_checkboxes[lang] = cb

    def _build_exclusions_section(self) -> None:
        frame = customtkinter.CTkFrame(self.scroll, corner_radius=10, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(0, 16))

        lbl = customtkinter.CTkLabel(frame, text="🚫 KEYWORD & INSTRUCTOR EXCLUSIONS", font=customtkinter.CTkFont(size=14, weight="bold"))
        lbl.pack(anchor="w", pady=(0, 8))

        kw_lbl = customtkinter.CTkLabel(frame, text="Exclude Course Titles containing (comma-separated keywords):", font=customtkinter.CTkFont(size=12))
        kw_lbl.pack(anchor="w")

        self.kw_entry = customtkinter.CTkEntry(frame, placeholder_text="e.g. beginner, practice test, kids", height=32)
        self.kw_entry.pack(fill="x", pady=(2, 10))

        inst_lbl = customtkinter.CTkLabel(frame, text="Exclude Instructors (comma-separated names):", font=customtkinter.CTkFont(size=12))
        inst_lbl.pack(anchor="w")

        self.inst_entry = customtkinter.CTkEntry(frame, placeholder_text="e.g. John Doe, Academy X", height=32)
        self.inst_entry.pack(fill="x", pady=(2, 10))

    def get_filter_settings(self) -> Dict[str, Any]:
        """Collect all configured filters as a dictionary."""
        categories = [cat for cat, cb in self.category_checkboxes.items() if cb.get() == 1]
        languages = []
        if self.language_checkboxes.get("All Languages") and self.language_checkboxes["All Languages"].get() == 1:
            languages = []
        else:
            languages = [lang for lang, cb in self.language_checkboxes.items() if cb.get() == 1 and lang != "All Languages"]

        try:
            limit = int(self.limit_entry.get().strip() or "0")
        except ValueError:
            limit = 0

        min_rating = round(self.rating_slider.get(), 2)

        kw_text = self.kw_entry.get().strip()
        excluded_keywords = [k.strip() for k in kw_text.split(",") if k.strip()]

        inst_text = self.inst_entry.get().strip()
        excluded_instructors = [i.strip() for i in inst_text.split(",") if i.strip()]

        return {
            "categories": categories,
            "languages": languages,
            "min_rating": min_rating,
            "limit": limit,
            "max_enrollment_limit": limit,
            "excluded_keywords": excluded_keywords,
            "excluded_instructors": excluded_instructors,
            "discounted_only": False,
        }
