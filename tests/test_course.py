"""Targeted tests for Course URL parsing and redaction (WP-UDEMY-02 / SEC-UDEMY-02)."""

import logging

from app.services.course import Course


def test_course_set_slug_redacts_on_failure(caplog):
    """Test that Course.set_slug redacts sensitive URLs on parse failure."""
    sensitive_url = "?couponCode=SUPERSECRET123&access_token=TOKEN999"

    with caplog.at_level(logging.ERROR):
        course = Course(title="Test Course", url=sensitive_url)

    # Slug should be None due to invalid URL format
    assert course.slug is None

    # Check captured log messages
    error_logs = [record.message for record in caplog.records if record.levelname == "ERROR"]
    assert len(error_logs) > 0
    assert any("Invalid URL format:" in log for log in error_logs)

    # Sensitive query values must be redacted
    for log in error_logs:
        assert "SUPERSECRET123" not in log
        assert "TOKEN999" not in log
        assert "***REDACTED***" in log


def test_course_valid_url_sets_slug():
    """Test that valid Udemy course URL extracts slug correctly."""
    valid_url = "https://www.udemy.com/course/python-masterclass/?couponCode=FREE123"
    course = Course(title="Python Course", url=valid_url)
    assert course.slug == "python-masterclass"
    assert course.coupon_code == "FREE123"
