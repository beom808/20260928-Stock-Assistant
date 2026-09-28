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


def check_db_url(url: str) -> tuple[str, list[str]]:
    """DB 주소 형식 점검 → (비밀번호를 가린 주소, 문제 목록). 비밀번호는 절대 출력하지 않는다."""
    url = url.strip()
    problems: list[str] = []
    scheme, sep, rest = url.partition("://")
    if not sep or not scheme.startswith(("postgres", "sqlite")):
        return "(형식 불명)", ["postgresql:// 로 시작하는 주소가 아닙니다."]
    if scheme.startswith("sqlite"):
        return url, problems
    userinfo, at, hostpart = rest.rpartition("@")
    if not at:
        return f"{scheme}://***", ["사용자/비밀번호와 서버 주소 사이의 '@' 가 없습니다."]
    user, _, password = userinfo.partition(":")
    masked = f"{scheme}://{user}:***@{hostpart}"
    if "@" in userinfo:
        problems.append(
            "'@' 가 두 번 이상 있습니다. 비밀번호에 '@' 가 있거나 '@' 를 한 번 더 입력했습니다. "
            "비밀번호를 영문·숫자로 재설정하는 것을 권장합니다."
        )
    if "[" in password or "]" in password or "YOUR-PASSWORD" in password:
        problems.append("[YOUR-PASSWORD] 부분이 실제 비밀번호로 바뀌지 않았습니다.")
    if hostpart.startswith("db.") and ".supabase.co" in hostpart:
        problems.append(
            "Supabase Direct connection 주소입니다(IPv6 전용). Session pooler 주소를 쓰세요."
        )
    if any(c.isspace() for c in url):
        problems.append("주소 안에 공백이나 줄바꿈이 있습니다.")
    return masked, problems


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
