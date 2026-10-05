"""Shared isolated database fixtures for API tests."""

from collections.abc import Generator
from sqlite3 import Connection

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Use a fresh in-memory SQLite database for each test."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection: Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    test_session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = test_session_factory()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


@pytest.fixture
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    """Use the isolated database and skip creation on the developer database."""
    monkeypatch.setattr(main_module, "create_tables", lambda _engine: None)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(main_module.app) as test_client:
            yield test_client
    finally:
        main_module.app.dependency_overrides.clear()
