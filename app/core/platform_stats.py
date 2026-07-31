"""Aggregate platform impact metrics derived from the database."""

import math
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.cache import get_cached_or_compute
from app.models.database import User, UserSettings

_platform_stats_cache: Dict[str, Any] = {}


def _format_indian_number(value: int) -> str:
    digits = str(abs(int(value)))
    if len(digits) <= 3:
        return digits
    last_three = digits[-3:]
    remaining = digits[:-3]
    groups = []
    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.insert(0, remaining)
    return ",".join(groups + [last_three])


def compute_platform_impact_stats(db: Session) -> Dict[str, float | int]:
    """Sum lifetime enrollment totals across all users."""
    row = (
        db.query(
            func.coalesce(func.sum(User.total_enrolled), 0).label("total_enrolled"),
            func.coalesce(func.sum(User.total_amount_saved), 0.0).label(
                "total_amount_saved"
            ),
        )
        .one()
    )
    return {
        "total_enrolled": int(row.total_enrolled or 0),
        "total_amount_saved": float(row.total_amount_saved or 0.0),
    }


def format_enrolled_impact(total_enrolled: int) -> str:
    """Conservative public display: round down to the nearest 100."""
    if total_enrolled <= 0:
        return "0"
    rounded = (total_enrolled // 100) * 100
    if rounded == 0:
        return f"{total_enrolled:,}+"
    return f"{rounded:,}+"


def format_savings_lakh_inr(total_amount_saved: float) -> str:
    """Compact INR display used on the homepage (e.g. ₹10.0L+)."""
    if total_amount_saved <= 0:
        return "₹0"
    lakhs = total_amount_saved / 100_000
    floored = math.floor(lakhs * 10) / 10
    return f"₹{floored:.1f}L+"


def format_savings_inr_full(total_amount_saved: float) -> str:
    """Full INR display for llms.txt and schema (e.g. ₹10,00,000+)."""
    if total_amount_saved <= 0:
        return "₹0"
    rounded = int(total_amount_saved // 1000) * 1000
    return f"₹{_format_indian_number(rounded)}+"


def _public_coupon_count() -> int:
    """Count entries in the public deals list; 0 if load fails."""
    try:
        from app.services.public_deals_export import load_public_deals

        return len(load_public_deals())
    except Exception:
        return 0


def get_platform_impact_display(db: Session) -> Dict[str, str | int | float | bool]:
    """Return raw totals and formatted strings for templates and SEO endpoints."""
    stats = get_cached_or_compute(
        _platform_stats_cache,
        "platform",
        lambda: compute_platform_impact_stats(db),
        ttl_seconds=300,
    )
    total_enrolled = stats["total_enrolled"]
    total_amount_saved = stats["total_amount_saved"]
    has_impact = total_enrolled > 0
    has_savings = total_amount_saved > 0
    # Conservative floor for schema: exact under 100, else nearest 100 down.
    # Never publish "0" when enrollments exist (e.g. 42 → "42", 1551 → "1500").
    enrolled_schema_value = (
        total_enrolled if total_enrolled < 100 else (total_enrolled // 100) * 100
    )
    source_count = len(UserSettings.default_sites())
    public_coupon_count = _public_coupon_count()
    return {
        "total_enrolled": total_enrolled,
        "total_amount_saved": total_amount_saved,
        "enrolled_display": format_enrolled_impact(total_enrolled),
        "saved_display_lakh": format_savings_lakh_inr(total_amount_saved),
        "saved_display_full": format_savings_inr_full(total_amount_saved),
        "enrolled_schema_value": enrolled_schema_value,
        "has_impact": has_impact,
        "has_savings": has_savings,
        "source_count": source_count,
        "source_count_display": str(source_count),
        "public_coupon_count": public_coupon_count,
        "public_coupon_display": (
            f"{public_coupon_count:,}" if public_coupon_count > 0 else "—"
        ),
    }
