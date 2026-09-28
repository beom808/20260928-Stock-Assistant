from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base


def normalize_db_url(url: str) -> str:
    """Supabase·Render 등이 주는 postgres(ql):// 주소를 설치된 psycopg(v3) 드라이버로 고정."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    url = normalize_db_url(url or get_settings().database_url)
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)  # 운영에서는 schema.sql / 마이그레이션 도구 사용 권장
    return engine


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with session_factory()() as s:
        yield s
