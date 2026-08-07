"""SERP-safe title and meta description helpers."""

import re

# Standalone brand word inside scraped titles/categories: stripped so the final
# SERP/RSS title carries "Udemy" exactly once (in the "| Udemy Enroller" suffix).
_UDEMY_WORD_RE = re.compile(r"\bUdemy\b", re.IGNORECASE)


def truncate_at_word(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    cut = text[: max_len - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(".,;:!?-–— ")
    if not cut:
        cut = text[: max_len - 1].rstrip()
    return f"{cut}…"


def _strip_udemy_word(text: str) -> str:
    """Remove standalone 'Udemy' occurrences and collapse whitespace."""
    return " ".join(_UDEMY_WORD_RE.sub("", text or "").split())


def coupon_serp_title(course_title: str, max_len: int = 60) -> str:
    """e.g. '{Course} — Free coupon | Udemy Enroller' ≤ max_len, 'Udemy' ≤1×."""
    brand = " | Udemy Enroller"
    mid = " — Free coupon"
    title = _strip_udemy_word(course_title) or "Free course"
    full = f"{title}{mid}{brand}"
    if len(full) <= max_len:
        return full
    # Shrink course title first
    budget = max_len - len(mid) - len(brand)
    if budget >= 12:
        return f"{truncate_at_word(title, budget)}{mid}{brand}"
    # Fallback: title | brand only
    budget = max_len - len(brand)
    return f"{truncate_at_word(title, max(budget, 8))}{brand}"


def sanitize_category_name(name: str, max_len: int = 40) -> str:
    """Display-safe category name for category hubs: no standalone 'Udemy'
    (the title/H1 brand is rendered elsewhere) and ≤ max_len at a word boundary."""
    clean = _strip_udemy_word(name)
    if len(clean) <= max_len:
        return clean
    return truncate_at_word(clean, max_len)


def coupon_serp_description(
    course_title: str,
    category_name: str,
    coupon_code: str | None = None,
    language: str | None = None,
    max_len: int = 155,
) -> str:
    """Compelling ≤155 char meta description; prefers keeping disclaimer tail."""
    title = (course_title or "this course").strip() or "this course"
    cat = (category_name or "Udemy").strip() or "Udemy"
    code = (coupon_code or "").strip()
    lang = (language or "").strip()

    code_bit = f" Code {code}." if code else ""
    tail = (
        f"{code_bit} Validity can change — confirm on Udemy. "
        "Not affiliated with Udemy."
    )
    lang_bit = f", {lang}" if lang else ""
    wrapper_len = len(f"Free Udemy coupon for  ({cat}{lang_bit}).") + len(tail)
    t_budget = max_len - wrapper_len
    if t_budget < 10:
        return truncate_at_word(f"Free Udemy coupon for {title}.{tail}", max_len)
    t = truncate_at_word(title, t_budget)
    text = f"Free Udemy coupon for {t} ({cat}{lang_bit}).{tail}"
    if len(text) <= max_len:
        return text
    return truncate_at_word(text, max_len)
