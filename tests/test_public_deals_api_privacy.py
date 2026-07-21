"""Privacy-boundary tests for the unauthenticated public coupon API."""

import json

import pytest
from fastapi.testclient import TestClient

from app.models.database import get_db
from app.security import RateLimiter
from app.services import public_deals_export
from main import app
import app.routers.public_deals as public_deals_router


def _forbidden_database():
    raise AssertionError("public coupon endpoint must not resolve the database")
    yield


def _request_public_coupons(monkeypatch, export_path, query=""):
    monkeypatch.setattr(
        public_deals_export,
        "DEFAULT_PUBLIC_DEALS_PATH",
        str(export_path),
    )
    monkeypatch.setattr(
        public_deals_export,
        "get_public_deals_path",
        lambda: str(export_path),
    )
    monkeypatch.setattr(
        public_deals_router,
        "public_coupons_api_limiter",
        RateLimiter(max_requests=50, window_seconds=60),
    )
    app.dependency_overrides[get_db] = _forbidden_database
    client = TestClient(app)
    try:
        return client.get(
            f"/udemycoupons/api/coupons{query}",
            headers={"cf-connecting-ip": "203.0.113.160"},
        )
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("file_contents", [None, "{not valid json"])
def test_public_coupon_api_fails_closed_without_valid_export(
    monkeypatch, tmp_path, file_contents
):
    export_path = tmp_path / "public_deals.json"
    if file_contents is not None:
        export_path.write_text(file_contents, encoding="utf-8")

    response = _request_public_coupons(monkeypatch, export_path)

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "categories": [],
        "total": 0,
        "page": 1,
        "pages": 0,
    }


def test_public_coupon_api_preserves_valid_export_filtering(monkeypatch, tmp_path):
    export_path = tmp_path / "public_deals.json"
    export_path.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "title": "Python Basics",
                    "url": "https://www.udemy.com/course/python-basics/",
                    "slug": "python-basics",
                    "category": "Development",
                    "coupon_code": "FREE-PYTHON",
                    "is_coupon_valid": True,
                },
                {
                    "id": 2,
                    "title": "Advanced Python",
                    "url": "https://www.udemy.com/course/advanced-python/",
                    "slug": "advanced-python",
                    "category": "Development",
                    "coupon_code": "EXPIRED-PYTHON",
                    "is_coupon_valid": False,
                },
                {
                    "id": 3,
                    "title": "Design Fundamentals",
                    "url": "https://www.udemy.com/course/design-fundamentals/",
                    "slug": "design-fundamentals",
                    "category": "Design",
                    "coupon_code": "FREE-DESIGN",
                    "is_coupon_valid": True,
                },
            ]
        ),
        encoding="utf-8",
    )

    response = _request_public_coupons(
        monkeypatch,
        export_path,
        query="?search=PYTHON&category=Development&status=enrolled&page=1&limit=1",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == [
        {
            "id": 1,
            "title": "Python Basics",
            "url": "https://www.udemy.com/course/python-basics/",
            "slug": "python-basics",
            "category": "Development",
            "coupon_code": "FREE-PYTHON",
            "is_coupon_valid": True,
        }
    ]
    assert data["categories"] == ["Design", "Development"]
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["pages"] == 1
