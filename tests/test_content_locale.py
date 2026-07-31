"""Content-facing locale consistency (Fix 47): en_IN / en-IN."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_base_html_og_locale_is_en_in():
    source = (PROJECT_ROOT / "app/templates/components/base.html").read_text(encoding="utf-8")
    assert 'lang="en-IN"' in source
    assert 'property="og:locale" content="en_IN"' in source
    assert 'property="og:locale" content="en_US"' not in source
    assert '"inLanguage": "en-IN"' in source


def test_llms_txt_language_is_en_in():
    source = (PROJECT_ROOT / "app/routers/seo.py").read_text(encoding="utf-8")
    assert "**Language:** en-IN" in source
    assert "**Language:** en-US" not in source


def test_humans_txt_language_is_en_in():
    source = (PROJECT_ROOT / "app/routers/seo.py").read_text(encoding="utf-8")
    assert "Language: English (en-IN)" in source
    assert "Language: English\n" not in source
