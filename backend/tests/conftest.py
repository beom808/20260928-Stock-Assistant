from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import normalize_db_url, session_factory

# 기본은 인메모리 SQLite. TEST_DATABASE_URL 을 주면 실제 PostgreSQL 로 같은 테스트를 돌린다.
# 예) TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def sessions():
    if TEST_DATABASE_URL:
        engine = create_engine(normalize_db_url(TEST_DATABASE_URL))
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        yield session_factory(engine)
        engine.dispose()
        return
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield session_factory(engine)


class FakeSleep:
    """asyncio.sleep 대체 — 실제로 기다리지 않고 호출 기록만 남김."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, secs: float) -> None:
        self.calls.append(secs)


@pytest.fixture
def fake_sleep():
    return FakeSleep()
