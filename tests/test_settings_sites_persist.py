"""C7: PUT upgrade-merges sites (defaults ← stored ← PUT); GET still does not write.

Isolated engine + CSRF client pattern matches tests/test_dsr_settings.py.
"""

import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.models.database import Base, User, UserSession, UserSettings, get_db
from app.routers.settings import _merge_sites_for_put
from app.security import generate_csrf_token

_NEW_TWO = ("Courson", "CouponScorpion")
_DROPPED_TWO = ("Real Discount", "Discudemy")
_REPO = Path(__file__).resolve().parents[1]
_SETTINGS_HTML = _REPO / "app" / "templates" / "pages" / "settings.html"

_test_db_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-sites-persist-")
_test_db_path = Path(_test_db_dir.name) / "test_sites_persist.db"
engine = create_engine(
    f"sqlite:///{_test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ten_sites() -> dict:
    return {
        k: True for k in UserSettings.default_sites() if k not in _NEW_TWO
    }


def _legacy_sixteen_sites() -> dict:
    """Pre-unregistration 16-key JSON still present in leftover DBs."""
    return {
        "FreeWebCart": True,
        "FreeCourseSites": True,
        "Real Discount": True,
        "E-next": True,
        "Interview Gig": True,
        "UdemyXpert": True,
        "Coursesity": True,
        "Course Folder": True,
        "Couponami": True,
        "Korshub": True,
        "UdemyFreebies": True,
        "iDownloadCoupon": True,
        "Course Joiner": True,
        "Discudemy": True,
        "Courson": True,
        "CouponScorpion": True,
    }


def _csrf_headers(token: str) -> dict:
    return {"X-CSRF-Token": generate_csrf_token(token)}


@pytest.fixture(autouse=True)
def _sites_persist_env():
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if app.dependency_overrides.get(get_db) is _override_get_db:
            app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sites_client():
    db = TestingSessionLocal()
    user = User(
        email=f"sites-{secrets.token_hex(6)}@example.com",
        password_hash="x",
        udemy_display_name="Sites User",
        currency="usd",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    token = secrets.token_hex(32)
    db.add(UserSession(token=token, user_id=user.id))
    db.add(UserSettings(user_id=user.id, sites=_ten_sites()))
    db.commit()
    db.close()

    client = TestClient(app)
    client.cookies.set("session_id", token)
    yield client, user_id, token

    client.cookies.clear()
    db = TestingSessionLocal()
    try:
        db.query(UserSettings).delete()
        db.query(UserSession).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()


def _db_sites(user_id: int) -> dict:
    db = TestingSessionLocal()
    try:
        row = db.query(UserSettings).filter(UserSettings.user_id == user_id).one()
        return dict(row.sites) if isinstance(row.sites, dict) else row.sites
    finally:
        db.close()


def _set_stored_sites(user_id: int, sites):
    db = TestingSessionLocal()
    try:
        row = db.query(UserSettings).filter(UserSettings.user_id == user_id).one()
        row.sites = sites
        db.commit()
    finally:
        db.close()


class TestMergeSitesForPutHelper:
    def test_ten_stored_and_put_upgrades_new_two_keeps_put_false(self):
        stored = _ten_sites()
        put = dict(stored)
        put["FreeCourseSites"] = False
        merged = _merge_sites_for_put(stored, put)
        defaults = UserSettings.default_sites()
        assert set(merged) == set(defaults)
        assert len(merged) == 12
        for name in _NEW_TWO:
            assert merged[name] is True
        assert merged["FreeCourseSites"] is False
        assert "FreeWebCart" not in merged
        assert "Course Joiner" not in merged

    def test_stored_false_survives_put_that_omits_key(self):
        stored = UserSettings.default_sites()
        stored["FreeCourseSites"] = False
        put = {k: v for k, v in stored.items() if k != "FreeCourseSites"}
        merged = _merge_sites_for_put(stored, put)
        assert merged["FreeCourseSites"] is False

    def test_put_explicit_false_wins(self):
        stored = UserSettings.default_sites()
        put = UserSettings.default_sites()
        put["Courson"] = False
        merged = _merge_sites_for_put(stored, put)
        assert merged["Courson"] is False

    def test_none_stored_and_non_dict_put_upgrades_via_defaults(self):
        merged = _merge_sites_for_put(None, "not-a-dict")
        assert merged == UserSettings.default_sites()

    def test_put_legacy_sixteen_extras_ignored(self):
        stored = _legacy_sixteen_sites()
        put = dict(stored)
        merged = _merge_sites_for_put(stored, put)
        defaults = UserSettings.default_sites()
        assert set(merged) == set(defaults)
        assert len(merged) == 12
        assert "Real Discount" not in merged
        assert "Discudemy" not in merged
        assert "FreeWebCart" not in merged
        assert "Course Joiner" not in merged


class TestSettingsSitesPersistHttp:
    def test_put_ten_upgrades_db_to_twelve_and_keeps_put_false(
        self, sites_client
    ):
        client, user_id, token = sites_client
        put = _ten_sites()
        put["FreeCourseSites"] = False
        response = client.put(
            "/api/settings/",
            json={"sites": put},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        stored = _db_sites(user_id)
        assert set(stored) == set(UserSettings.default_sites())
        assert len(stored) == 12
        for name in _NEW_TWO:
            assert stored[name] is True
        assert stored["FreeCourseSites"] is False
        assert "FreeWebCart" not in stored
        assert "Course Joiner" not in stored

    def test_put_omitting_courson_keeps_stored_false(self, sites_client):
        client, user_id, token = sites_client
        stored = UserSettings.default_sites()
        stored["Courson"] = False
        _set_stored_sites(user_id, stored)
        put = {k: v for k, v in stored.items() if k != "Courson"}
        response = client.put(
            "/api/settings/",
            json={"sites": put},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        assert _db_sites(user_id)["Courson"] is False

    def test_put_explicit_courson_false_wins(self, sites_client):
        client, user_id, token = sites_client
        _set_stored_sites(user_id, UserSettings.default_sites())
        put = UserSettings.default_sites()
        put["Courson"] = False
        response = client.put(
            "/api/settings/",
            json={"sites": put},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        assert _db_sites(user_id)["Courson"] is False

    def test_get_ten_key_returns_twelve_true_without_writing_db(
        self, sites_client
    ):
        client, user_id, _token = sites_client
        before = _db_sites(user_id)
        assert set(before) == set(_ten_sites())
        response = client.get("/api/settings/")
        assert response.status_code == 200
        body = response.json()["sites"]
        defaults = UserSettings.default_sites()
        assert set(body) == set(defaults)
        assert all(body[k] is True for k in defaults)
        assert "FreeWebCart" not in body
        assert "Course Joiner" not in body
        after = _db_sites(user_id)
        assert set(after) == set(_ten_sites())
        for name in _NEW_TWO:
            assert name not in after

    def test_get_legacy_sixteen_drops_rd_du_without_writing_db(self, sites_client):
        client, user_id, _token = sites_client
        legacy = _legacy_sixteen_sites()
        _set_stored_sites(user_id, legacy)
        before = _db_sites(user_id)
        assert len(before) == 16
        assert "Real Discount" in before and "Discudemy" in before
        assert "Course Joiner" in before
        response = client.get("/api/settings/")
        assert response.status_code == 200
        body = response.json()["sites"]
        defaults = UserSettings.default_sites()
        assert set(body) == set(defaults)
        assert len(body) == 12
        assert "Real Discount" not in body
        assert "Discudemy" not in body
        assert "FreeWebCart" not in body
        assert "Course Joiner" not in body
        assert all(body[k] is True for k in defaults)
        after = _db_sites(user_id)
        assert after == before
        assert len(after) == 16
        assert "Real Discount" in after and "Discudemy" in after
        assert after["FreeWebCart"] is True
        assert after["Course Joiner"] is True

    def test_put_legacy_sixteen_extras_ignored_writes_twelve(self, sites_client):
        client, user_id, token = sites_client
        _set_stored_sites(user_id, _legacy_sixteen_sites())
        put = _legacy_sixteen_sites()
        put["FreeCourseSites"] = False
        response = client.put(
            "/api/settings/",
            json={"sites": put},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        stored = _db_sites(user_id)
        defaults = UserSettings.default_sites()
        assert set(stored) == set(defaults)
        assert len(stored) == 12
        assert "Real Discount" not in stored
        assert "Discudemy" not in stored
        assert "FreeWebCart" not in stored
        assert "Course Joiner" not in stored
        assert stored["FreeCourseSites"] is False
        for name in _DROPPED_TWO:
            assert name not in stored

    def test_post_reset_writes_twelve_key_defaults(self, sites_client):
        client, user_id, token = sites_client
        _set_stored_sites(user_id, _legacy_sixteen_sites())
        response = client.post(
            "/api/settings/reset",
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        stored = _db_sites(user_id)
        assert stored == UserSettings.default_sites()
        assert len(stored) == 12
        assert "Real Discount" not in stored
        assert "Discudemy" not in stored
        assert "FreeWebCart" not in stored
        assert "Course Joiner" not in stored

    def test_stored_none_put_does_not_500_and_upgrades_via_defaults(
        self, sites_client
    ):
        client, user_id, token = sites_client
        _set_stored_sites(user_id, None)
        put = _ten_sites()
        put["FreeCourseSites"] = False
        response = client.put(
            "/api/settings/",
            json={"sites": put},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 200
        stored = _db_sites(user_id)
        assert set(stored) == set(UserSettings.default_sites())
        assert stored["FreeCourseSites"] is False
        assert "FreeWebCart" not in stored
        for name in _NEW_TWO:
            assert stored[name] is True

    def test_non_dict_put_sites_does_not_500(self, sites_client):
        client, _user_id, token = sites_client
        response = client.put(
            "/api/settings/",
            json={"sites": "not-a-dict"},
            headers=_csrf_headers(token),
        )
        assert response.status_code == 422


def test_gather_settings_pins_checkbox_dataset_key():
    html = _SETTINGS_HTML.read_text(encoding="utf-8")
    assert "result[cb.dataset.key] = cb.checked" in html
