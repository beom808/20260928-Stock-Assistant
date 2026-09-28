"""DB 스키마 (SQLAlchemy 2). PostgreSQL 운영 / SQLite 개발·테스트 겸용.

- reports       : 리포트 이력 (유형 × KST 기준일 1건, 재실행 시 revision 증가하며 갱신)
- job_runs      : 스케줄 잡 실행 로그 (성공/실패/오류 메시지)
- api_cache     : 외부 API 응답 캐시 (TTL + 장애 시 stale fallback 용)
- api_usage     : 공급자별 일일 호출 수 (무료 한도 초과 방지)
- push_tokens   : FCM 웹푸시 토큰
동일 구조의 PostgreSQL DDL 은 backend/schema.sql 참고.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("report_type", "report_date_kst", name="uq_report_type_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(40), index=True)
    report_date_kst: Mapped[date] = mapped_column(Date, index=True)
    generated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # ok | partial | failed
    revision: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JsonType)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(40), index=True)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # running | ok | partial | failed | skipped
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApiCache(Base):
    __tablename__ = "api_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    fetched_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    body: Mapped[dict | list] = mapped_column(JsonType)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    usage_date_utc: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class PushToken(Base):
    __tablename__ = "push_tokens"

    token: Mapped[str] = mapped_column(String(512), primary_key=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
