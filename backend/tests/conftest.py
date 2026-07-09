"""Pytest fixtures, including test database setup."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.db.base import Base
from app.main import app

# Deliberately not read from app.core.config.Settings: test configuration
# is a separate concern from application configuration, and Settings has
# extra="forbid", so we don't want test-only env vars coupled to it.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://capitalforge:capitalforge@localhost:5433/capitalforge_test",
)

engine = create_engine(TEST_DATABASE_URL)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    """Create all tables once per test session, drop them once at the end.
    Runs automatically for every test file, no need to request it explicitly.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Session:
    """A database session wrapped in a transaction that's rolled back after
    each test, so tests never leak data into one another regardless of
    execution order.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """A FastAPI TestClient with get_db overridden to use the same
    transaction-wrapped session as db_session, so API calls in a test
    and direct DB assertions in that same test see consistent state.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()