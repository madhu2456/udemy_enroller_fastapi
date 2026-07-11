"""Shared pytest fixtures.

Ensures the SQLAlchemy schema exists for tests that use the app engine /
SessionLocal (e.g. homepage platform stats) without requiring a pre-migrated
ambient database file.
"""

import pytest

from app.models.database import Base, engine


@pytest.fixture(scope="session", autouse=True)
def ensure_app_schema():
    """Create missing tables on the app bind once per test session."""
    Base.metadata.create_all(bind=engine)
    yield
