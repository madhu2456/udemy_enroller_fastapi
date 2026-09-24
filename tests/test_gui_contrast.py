"""F018: computed WCAG 2.x contrast for GUI caption / progress / brand pairs.

Static ratio computation (no Tk mainloop, no display). Every token in
app/gui/theme.py that replaced a failing audit color is asserted here against
the exact surface backgrounds it renders on, per the D.1 predicate:

    caption pairs       >= 4.5:1 (both themes)
    progress label pairs>= 4.5:1 (both themes)
    brand on dark       >= 3:1  (both themes)
"""

from __future__ import annotations

from app.gui.theme import (
    COLOR_CAPTION_DARK,
    COLOR_CAPTION_LIGHT,
    COLOR_DARK_BG,
    COLOR_DARK_CARD,
    COLOR_DARK_SURFACE,
    COLOR_LIGHT_BG,
    COLOR_LIGHT_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_LABEL_LIGHT,
    COLOR_PRIMARY_ON_DARK,
    COLOR_SUCCESS_LABEL_DARK,
    COLOR_SUCCESS_LABEL_LIGHT,
)

# Surfaces the audited text renders on (theme.py palette + CTk defaults).
LIGHT_SURFACES = [COLOR_LIGHT_CARD, "#E6E6E6", "#FFFFFF", COLOR_LIGHT_BG]
DARK_SURFACES = [COLOR_DARK_CARD, COLOR_DARK_SURFACE, "#404040", COLOR_DARK_BG]


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of a #RRGGBB color."""
    value = hex_color.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"not a 6-digit hex color: {hex_color!r}")
    channels = []
    for i in (0, 2, 4):
        srgb = int(value[i : i + 2], 16) / 255.0
        linear = srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4
        channels.append(linear)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colors (>= 1.0)."""
    lum_fg = _relative_luminance(fg)
    lum_bg = _relative_luminance(bg)
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


def _assert_all(fg: str, backgrounds: list[str], minimum: float) -> list[float]:
    ratios = [contrast_ratio(fg, bg) for bg in backgrounds]
    worst_bg = backgrounds[ratios.index(min(ratios))]
    assert min(ratios) >= minimum, (
        f"{fg} contrast {min(ratios):.2f}:1 on {worst_bg} below {minimum}:1 "
        f"(all: {dict(zip(backgrounds, [round(r, 2) for r in ratios]))})"
    )
    return ratios


def test_caption_pairs_meet_44_5_both_themes():
    """Captions: gray50 #7F7F7F (3.16-4.00) / gray60 #999999 (3.61) replaced."""
    light = _assert_all(COLOR_CAPTION_LIGHT, LIGHT_SURFACES, 4.5)
    dark = _assert_all(COLOR_CAPTION_DARK, DARK_SURFACES, 4.5)
    assert min(light) >= 4.5 and min(dark) >= 4.5


def test_progress_label_pairs_meet_44_5_both_themes():
    """Progress labels: PRIMARY #A435F0 (4.31/2.13) + SUCCESS #198754 (4.04/2.27) replaced."""
    _assert_all(COLOR_PRIMARY_LABEL_LIGHT, [COLOR_LIGHT_CARD], 4.5)
    _assert_all(COLOR_PRIMARY_ON_DARK, [COLOR_DARK_CARD], 4.5)
    _assert_all(COLOR_SUCCESS_LABEL_LIGHT, [COLOR_LIGHT_CARD], 4.5)
    _assert_all(COLOR_SUCCESS_LABEL_DARK, [COLOR_DARK_CARD], 4.5)


def test_brand_on_dark_meets_3_1_both_themes():
    """Brand mark: #A435F0 on #2D2F31 (2.78) and #1C1D1F (3.49) replaced."""
    assert contrast_ratio(COLOR_PRIMARY_ON_DARK, COLOR_DARK_SURFACE) >= 3.0  # sidebar logo
    assert contrast_ratio(COLOR_PRIMARY_ON_DARK, COLOR_DARK_BG) >= 3.0       # scrape label
    assert contrast_ratio(COLOR_PRIMARY, COLOR_DARK_SURFACE) < 3.0           # old value failed


def test_new_tokens_keep_light_mode_brand_intact():
    """Light-mode brand purple #A435F0 stays text-AA on the surfaces that host it.

    Sidebar logo renders on the light surface #FFFFFF (4.83:1); the scrape
    button label renders on the light workspace #F7F9FA (4.58:1). Card surfaces
    only host brand through >=26pt-bold KPI values (AA large-text, 3:1) and
    filled buttons (white-on-purple 4.83:1), which are covered separately.
    """
    light_brand_surfaces = ["#FFFFFF", COLOR_LIGHT_BG]
    _assert_all(COLOR_PRIMARY, light_brand_surfaces, 4.5)
