from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import session_factory


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return session_factory(engine)


class FakeSleep:
    """asyncio.sleep 대체 — 실제로 기다리지 않고 호출 기록만 남김."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, secs: float) -> None:
        self.calls.append(secs)


@pytest.fixture
def fake_sleep():
    return FakeSleep()
