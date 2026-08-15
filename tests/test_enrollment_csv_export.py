"""F-ENRL-C12: CSV export neutralizes spreadsheet formula injection.

Cells beginning with =, +, -, @, tab or CR are prefixed with a single quote
so spreadsheet apps render them as text instead of executing them.
"""

import csv
import io
import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.models.database import (
    Base,
    EnrolledCourse,
    EnrollmentRun,
    User,
    UserSession,
    get_db,
)

_test_db_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-csv-tests-")
_test_db_path = Path(_test_db_dir.name) / "test_csv.db"
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


@pytest.fixture
def csv_client():
    """TestClient with a user + completed run containing risky cells."""
    app.dependency_overrides[get_db] = _override_get_db
    db = TestingSessionLocal()
    user = User(
        email=f"csv-{secrets.token_hex(6)}@example.com", password_hash="x"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = secrets.token_hex(32)
    db.add(UserSession(token=token, user_id=user.id))
    run = EnrollmentRun(user_id=user.id, status="completed", currency="usd")
    db.add(run)
    db.commit()
    db.refresh(run)

    db.add_all(
        [
            EnrolledCourse(
                enrollment_run_id=run.id,
                title='=HYPERLINK("https://evil.example","Free")',
                url="https://www.udemy.com/course/test/",
                status="enrolled",
            ),
            EnrolledCourse(
                enrollment_run_id=run.id,
                title="+cmd|'/C calc'!A0",
                url="https://www.udemy.com/course/plus/",
                status="failed",
            ),
            EnrolledCourse(
                enrollment_run_id=run.id,
                title="Safe course",
                url="-@SUM(1+1)",
                status="enrolled",
            ),
            EnrolledCourse(
                enrollment_run_id=run.id,
                title="Safe course 2",
                url="https://www.udemy.com/course/safe/",
                coupon_code="\tPASTE",
                error_message="\rMalicious error",
                status="expired",
            ),
        ]
    )
    db.commit()
    run_id = run.id

    client = TestClient(app)
    client.cookies.set("session_id", token)
    yield client, run_id

    client.cookies.clear()
    db.close()
    # Remove only our own override: a previous override captured at import
    # time can be stale (e.g. test_core_functionality installs one at import
    # and removes it at module teardown), so restoring it would resurrect a
    # dependency bound to a deleted database.
    if app.dependency_overrides.get(get_db) is _override_get_db:
        app.dependency_overrides.pop(get_db, None)


def _export_cells(client, run_id):
    response = client.get(f"/api/enrollment/run/{run_id}/export")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = list(csv.reader(io.StringIO(response.text)))
    return rows, [cell for row in rows[1:] for cell in row]


class TestCSVExportFormulaInjection:
    def test_risky_cells_prefixed_with_quote(self, csv_client):
        client, run_id = csv_client
        rows, cells = _export_cells(client, run_id)
        # Header intact
        assert rows[0][0] == "Title"

        def find(cell_value):
            return any(c == cell_value for c in cells)

        assert find("'=HYPERLINK(\"https://evil.example\",\"Free\")")
        assert find("'+cmd|'/C calc'!A0")
        assert find("'-@SUM(1+1)")
        assert find("'\tPASTE")
        assert find("'\rMalicious error")

        # Safe values are preserved unchanged
        assert find("Safe course")
        assert find("https://www.udemy.com/course/safe/")

    def test_no_bare_formula_cells_remain(self, csv_client):
        client, run_id = csv_client
        _, cells = _export_cells(client, run_id)
        for cell in cells:
            assert not cell.startswith(("=", "+", "-", "@", "\t", "\r")) or cell.startswith(
                "'"
            )

    def test_export_requires_ownership(self, csv_client):
        """Another user's run must 404 (server-side ownership gate)."""
        client, run_id = csv_client
        db = TestingSessionLocal()
        other = User(email="other@example.com", password_hash="x")
        db.add(other)
        db.commit()
        db.refresh(other)
        token = secrets.token_hex(32)
        db.add(UserSession(token=token, user_id=other.id))
        db.commit()
        db.close()

        other_client = TestClient(app)
        other_client.cookies.set("session_id", token)
        response = other_client.get(f"/api/enrollment/run/{run_id}/export")
        assert response.status_code == 404
