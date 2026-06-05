"""Unit tests to verify XSS protections and HTML escaping in templates."""

import os
import re
from bs4 import BeautifulSoup
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from unittest.mock import MagicMock

def test_xss_helpers_defined_in_base():
    """Assert that escapeHTML and sanitizeURL are declared in base.html."""
    template_path = os.path.join("app", "templates", "components", "base.html")
    assert os.path.exists(template_path), f"base.html not found at {template_path}"
    
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "function escapeHTML" in content, "escapeHTML helper function is missing from base.html"
    assert "function sanitizeURL" in content, "sanitizeURL helper function is missing from base.html"

def test_escape_in_dashboard_templates():
    """Assert that dangerous innerHTML assignments in dashboard.html use escapeHTML/sanitizeURL."""
    dashboard_path = os.path.join("app", "templates", "pages", "dashboard.html")
    assert os.path.exists(dashboard_path), f"dashboard.html not found"

    with open(dashboard_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the course rendering map function block
    map_block_match = re.search(r"paginatedCourses\.map\(course\s*=>\s*\{([\s\S]*?)\}\)\.join\(''\)", content)
    assert map_block_match is not None, "Could not find course pagination map block in dashboard.html"
    map_block = map_block_match.group(1)

    # Check that variables are escaped or sanitized
    assert "escapeHTML(course.title" in map_block or "escapedTitle" in map_block
    assert "sanitizeURL(course.url)" in map_block or "sanitizedUrl" in map_block
    assert "escapeHTML(course.site_source" in map_block or "escapedSite" in map_block
    assert "escapeHTML(course.status)" in map_block

    # Check for current_course_url link sanitization
    assert "document.getElementById('current-url').href = sanitizeURL(" in content

def test_escape_in_history_templates():
    """Assert that innerHTML assignments in history.html use escapeHTML/sanitizeURL."""
    history_path = os.path.join("app", "templates", "pages", "history.html")
    assert os.path.exists(history_path), f"history.html not found"

    with open(history_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Main runs list status escaping
    assert "escapeHTML(run.status)" in content

    # Check dynamic details HTML structure inside details fetch
    # Check that the mapped values inside details are escaped/sanitized
    assert "escapeHTML(data.run.status)" in content
    assert "sanitizeURL(c.url)" in content
    assert "escapeHTML(c.title" in content
    assert "escapeHTML(c.category" in content
    assert "escapeHTML(c.language" in content
    assert "escapeHTML(c.site_source" in content

def test_escape_in_settings_templates():
    """Assert that input settings tags in settings.html use escapeHTML."""
    settings_path = os.path.join("app", "templates", "pages", "settings.html")
    assert os.path.exists(settings_path), f"settings.html not found"

    with open(settings_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Dynamic tags should be escaped
    assert "escapeHTML(text)" in content
    # Checkbox grid items should be escaped
    assert "escapeHTML(key)" in content
