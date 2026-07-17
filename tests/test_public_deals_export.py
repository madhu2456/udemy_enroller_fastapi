"""Tests for public_deals.json export shared by coupon checker and enrollment."""

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.public_deals_export as public_deals_export_module
from app.models.database import (
    Base,
    EnrolledCourse,
    EnrollmentRun,
    User,
    UserSettings,
    _utcnow_naive,
)
from app.services.public_deals_export import (
    assign_unique_slugs,
    build_sitemap_xml,
    export_public_deals_json,
    extract_udemy_course_slug,
    get_valid_deal_by_slug,
    is_sitemap_quality_deal,
    list_valid_deals_for_sitemap,
    slugify,
    write_sitemap_files,
)


def _seed_isolated_db():
    """Use an in-memory DB so export count is deterministic (no ambient rows)."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(email="deals_export@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserSettings(user_id=user.id))
    run = EnrollmentRun(user_id=user.id, status="completed")
    db.add(run)
    db.commit()
    db.refresh(run)

    valid = EnrolledCourse(
        enrollment_run_id=run.id,
        title="Valid Free Course",
        url="https://www.udemy.com/course/valid/?couponCode=FREE",
        coupon_code="FREE",
        price=19.99,
        is_coupon_valid=True,
        last_checked_at=_utcnow_naive(),
        enrolled_at=_utcnow_naive(),
    )
    invalid = EnrolledCourse(
        enrollment_run_id=run.id,
        title="Expired Course",
        url="https://www.udemy.com/course/exp/?couponCode=OLD",
        coupon_code="OLD",
        price=49.0,
        is_coupon_valid=False,
        last_checked_at=_utcnow_naive(),
        enrolled_at=_utcnow_naive() - timedelta(days=1),
    )
    no_coupon = EnrolledCourse(
        enrollment_run_id=run.id,
        title="No Coupon",
        url="https://www.udemy.com/course/nc/",
        coupon_code=None,
        is_coupon_valid=True,
        enrolled_at=_utcnow_naive(),
    )
    db.add_all([valid, invalid, no_coupon])
    db.commit()
    db.refresh(valid)
    return db, valid


def test_export_only_valid_with_coupon_code():
    db, valid = _seed_isolated_db()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "public_deals.json"
            n = export_public_deals_json(
                db, path=str(out), refresh_sitemap=False
            )
            assert n == 1
            data = json.loads(out.read_text(encoding="utf-8"))
            assert len(data) == 1
            assert data[0]["title"] == "Valid Free Course"
            assert data[0]["coupon_code"] == "FREE"
            assert data[0]["is_coupon_valid"] is True
            assert data[0]["id"] == valid.id
    finally:
        db.close()


def test_export_atomic_replace():
    db, _ = _seed_isolated_db()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "public_deals.json"
            out.write_text("[]", encoding="utf-8")
            export_public_deals_json(db, path=str(out), refresh_sitemap=False)
            assert not (Path(tmp) / "public_deals.json.tmp").exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0].get("slug")
            assert "web-development" in data[0]["slug"] or "valid" in data[0]["slug"]
    finally:
        db.close()


def test_concurrent_exports_use_independent_temp_files(monkeypatch, tmp_path):
    """Overlapping exporters must not move or rewrite each other's temp files."""
    target = tmp_path / "public_deals.json"
    replace_barrier = Barrier(2)
    replace_sources = []
    original_replace = os.replace

    def synchronized_replace(source, destination):
        if Path(destination) == target:
            replace_sources.append(Path(source))
            replace_barrier.wait(timeout=5)
        original_replace(source, destination)

    monkeypatch.setattr(
        public_deals_export_module.os,
        "replace",
        synchronized_replace,
    )

    def make_course(course_id, coupon_code):
        return SimpleNamespace(
            id=course_id,
            title=f"Concurrent Export Course {course_id}",
            url=f"https://www.udemy.com/course/concurrent-export-{course_id}/",
            slug=f"concurrent-export-{course_id}",
            coupon_code=coupon_code,
            price=0.0,
            category="Development",
            language="English",
            rating=4.5,
            is_coupon_valid=True,
            enrolled_at=_utcnow_naive(),
            last_checked_at=_utcnow_naive(),
        )

    courses = [
        make_course(1, "CONCURRENT-A"),
        make_course(2, "CONCURRENT-B"),
    ]

    class FakeDatabase:
        def __init__(self, course):
            self.course = course

        def query(self, model):
            return self

        def filter(self, *criteria):
            return self

        def order_by(self, *ordering):
            return self

        def limit(self, value):
            return self

        def all(self):
            return [self.course]

    def run_export(course):
        return export_public_deals_json(
            FakeDatabase(course),
            path=str(target),
            refresh_sitemap=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run_export, courses))

    assert results == [1, 1]
    assert len(replace_sources) == 2
    assert len(set(replace_sources)) == 2
    published = json.loads(target.read_text(encoding="utf-8"))
    assert len(published) == 1
    assert published[0]["coupon_code"] in {"CONCURRENT-A", "CONCURRENT-B"}
    assert list(tmp_path.iterdir()) == [target]


def test_slug_from_udemy_url_and_title():
    assert (
        extract_udemy_course_slug(
            "https://www.udemy.com/course/python-for-beginners/?couponCode=ABC"
        )
        == "python-for-beginners"
    )
    assert slugify("More Free Courses in IT & Software!") == "more-free-courses-in-it-software"


def test_unique_slugs_on_collision():
    deals = [
        {
            "id": 1,
            "title": "Same Title",
            "url": "https://www.udemy.com/course/same-title/",
            "is_coupon_valid": True,
        },
        {
            "id": 2,
            "title": "Same Title",
            "url": "https://www.udemy.com/course/same-title/",
            "is_coupon_valid": True,
        },
    ]
    assign_unique_slugs(deals)
    assert deals[0]["slug"] == "same-title"
    assert deals[1]["slug"] == "same-title-2"
    assert deals[0]["slug"] != deals[1]["slug"]


def test_get_valid_deal_by_slug_resolves_name():
    deals = assign_unique_slugs(
        [
            {
                "id": 99,
                "title": "Learn FastAPI",
                "url": "https://www.udemy.com/course/learn-fastapi/",
                "coupon_code": "FREE",
                "is_coupon_valid": True,
            }
        ]
    )
    # Write temp and load via path
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "public_deals.json"
        out.write_text(json.dumps(deals), encoding="utf-8")
        found = get_valid_deal_by_slug("learn-fastapi", path=str(out))
        assert found is not None
        assert found["id"] == 99
        # numeric legacy
        found2 = get_valid_deal_by_slug("99", path=str(out))
        assert found2 is not None


def test_build_sitemap_includes_deal_slugs_not_udemy():
    deals = assign_unique_slugs(
        [
            {
                "id": 1,
                "title": "Python Basics",
                "url": "https://www.udemy.com/course/python-basics/?couponCode=X",
                "coupon_code": "X",
                "is_coupon_valid": True,
                "last_checked_at": "2026-07-12T00:00:00Z",
            }
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        deals_path = Path(tmp) / "public_deals.json"
        deals_path.write_text(json.dumps(deals), encoding="utf-8")
        xml, n = build_sitemap_xml(deals_path=str(deals_path))
        assert n == 1
        assert "/udemycoupons/c/python-basics" in xml
        assert "www.udemy.com" not in xml
        assert "/udemycoupons</loc>" in xml or "/udemycoupons\n" in xml


def test_sitemap_quality_filters_thin_and_stale():
    from datetime import date, timedelta

    recent = (date.today() - timedelta(days=2)).isoformat() + "T00:00:00Z"
    old = (date.today() - timedelta(days=45)).isoformat() + "T00:00:00Z"
    good = {
        "id": 1,
        "title": "Python Basics Course",
        "url": "https://www.udemy.com/course/python-basics/",
        "coupon_code": "FREE",
        "is_coupon_valid": True,
        "last_checked_at": recent,
    }
    thin = {
        "id": 2,
        "title": "Hi",
        "url": "https://www.udemy.com/course/hi/",
        "coupon_code": "X",
        "is_coupon_valid": True,
        "last_checked_at": recent,
    }
    stale = {
        "id": 3,
        "title": "Old Valid Course Name",
        "url": "https://www.udemy.com/course/old-course/",
        "coupon_code": "OLD",
        "is_coupon_valid": True,
        "last_checked_at": old,
    }
    no_code = {
        "id": 4,
        "title": "Missing Coupon Title",
        "url": "https://www.udemy.com/course/missing/",
        "coupon_code": None,
        "is_coupon_valid": True,
        "last_checked_at": recent,
    }
    assign_unique_slugs([good, thin, stale, no_code])
    assert is_sitemap_quality_deal(good) is True
    assert is_sitemap_quality_deal(thin) is False
    assert is_sitemap_quality_deal(stale) is False
    assert is_sitemap_quality_deal(no_code) is False

    with tempfile.TemporaryDirectory() as tmp:
        deals_path = Path(tmp) / "public_deals.json"
        deals_path.write_text(
            json.dumps([good, thin, stale, no_code]), encoding="utf-8"
        )
        sitemap_deals = list_valid_deals_for_sitemap(str(deals_path))
        assert len(sitemap_deals) == 1
        assert sitemap_deals[0]["id"] == 1
        xml, n = build_sitemap_xml(deals_path=str(deals_path))
        assert n == 1
        assert "/udemycoupons/c/python-basics" in xml
        assert "/udemycoupons/c/hi" not in xml
        assert "old-course" not in xml


def test_export_refreshes_sitemap_files():
    db, _ = _seed_isolated_db()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            deals_path = Path(tmp) / "public_deals.json"
            sm_path = Path(tmp) / "sitemap.generated.xml"
            meta_path = Path(tmp) / "sitemap.meta.json"
            n = export_public_deals_json(db, path=str(deals_path), refresh_sitemap=False)
            assert n == 1
            # explicit sitemap write from that JSON
            count = write_sitemap_files(
                deals_path=str(deals_path),
                sitemap_path=str(sm_path),
                meta_path=str(meta_path),
            )
            assert count == 1
            assert sm_path.exists()
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta["deal_urls"] == 1
            assert "/udemycoupons/c/" in sm_path.read_text(encoding="utf-8")
    finally:
        db.close()
