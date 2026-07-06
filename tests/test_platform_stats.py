"""Tests for database-derived platform impact metrics."""

from app.core.platform_stats import (
    format_enrolled_impact,
    format_savings_inr_full,
    format_savings_lakh_inr,
    get_platform_impact_display,
)
from app.models.database import SessionLocal


class TestPlatformStatsFormatting:
    def test_format_enrolled_impact_rounds_down(self):
        assert format_enrolled_impact(1551) == "1,500+"
        assert format_enrolled_impact(1400) == "1,400+"
        assert format_enrolled_impact(0) == "0"

    def test_format_savings_lakh_inr(self):
        assert format_savings_lakh_inr(844_321) == "₹8.4L+"
        assert format_savings_lakh_inr(1_000_471) == "₹10.0L+"
        assert format_savings_lakh_inr(0) == "₹0"

    def test_format_savings_inr_full(self):
        assert format_savings_inr_full(844_321) == "₹8,44,000+"
        assert format_savings_inr_full(1_000_471) == "₹10,00,000+"
        assert format_savings_inr_full(0) == "₹0"


class TestPlatformStatsIntegration:
    def test_get_platform_impact_display_matches_db_totals(self):
        from app.core.platform_stats import _platform_stats_cache, compute_platform_impact_stats

        _platform_stats_cache.clear()
        db = SessionLocal()
        try:
            stats = compute_platform_impact_stats(db)
            display = get_platform_impact_display(db)

            assert display["total_enrolled"] == stats["total_enrolled"]
            assert display["total_amount_saved"] == stats["total_amount_saved"]
            assert display["enrolled_display"] == format_enrolled_impact(stats["total_enrolled"])
            assert display["saved_display_lakh"] == format_savings_lakh_inr(
                stats["total_amount_saved"]
            )
            assert display["saved_display_full"] == format_savings_inr_full(
                stats["total_amount_saved"]
            )
        finally:
            db.close()