"""Tests for database-derived platform impact metrics."""

from unittest.mock import MagicMock, patch

from app.core.platform_stats import (
    format_enrolled_impact,
    format_savings_inr_full,
    format_savings_lakh_inr,
    get_platform_impact_display,
)
from app.models.database import SessionLocal, UserSettings


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


class TestPlatformStatsDisplayFlags:
    """Mocked display flags and schema values (no DB dependency)."""

    def _display_for(self, total_enrolled: int, total_amount_saved: float):
        from app.core.platform_stats import _platform_stats_cache

        _platform_stats_cache.clear()
        db = MagicMock()
        with patch(
            "app.core.platform_stats.get_cached_or_compute",
            side_effect=lambda cache, key, compute_fn, ttl_seconds=300: compute_fn(),
        ), patch(
            "app.core.platform_stats.compute_platform_impact_stats",
            return_value={
                "total_enrolled": total_enrolled,
                "total_amount_saved": total_amount_saved,
            },
        ), patch(
            "app.core.platform_stats._public_coupon_count",
            return_value=0,
        ):
            return get_platform_impact_display(db)

    def test_zero_totals_no_impact_no_savings(self):
        display = self._display_for(0, 0.0)
        assert display["has_impact"] is False
        assert display["has_savings"] is False
        assert display["enrolled_schema_value"] == 0

    def test_enrolled_without_savings(self):
        display = self._display_for(42, 0.0)
        assert display["has_impact"] is True
        assert display["has_savings"] is False
        assert display["enrolled_schema_value"] == 42
        assert display["enrolled_schema_value"] != 0

    def test_enrolled_with_savings_schema_floor(self):
        display = self._display_for(1551, 844_321.0)
        assert display["has_impact"] is True
        assert display["has_savings"] is True
        assert display["enrolled_schema_value"] == 1500


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
            assert display["has_impact"] == (display["total_enrolled"] > 0)
            assert display["has_impact"] is (stats["total_enrolled"] > 0)
            assert display["has_savings"] == (display["total_amount_saved"] > 0)
            assert display["has_savings"] is (stats["total_amount_saved"] > 0)
            if stats["total_enrolled"] > 0:
                expected_schema = (
                    stats["total_enrolled"]
                    if stats["total_enrolled"] < 100
                    else (stats["total_enrolled"] // 100) * 100
                )
                assert display["enrolled_schema_value"] == expected_schema
                assert display["enrolled_schema_value"] != 0
            assert "source_count" in display
            assert display["source_count"] == len(UserSettings.default_sites())
            assert display["source_count"] >= 1
            assert display["source_count_display"] == str(display["source_count"])
            assert isinstance(display["public_coupon_count"], int)
            assert display["public_coupon_count"] >= 0
            if display["public_coupon_count"] > 0:
                assert display["public_coupon_display"] == f"{display['public_coupon_count']:,}"
            else:
                assert display["public_coupon_display"] == "—"
        finally:
            db.close()
