"""계층 간 주고받는 도메인 모델."""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field


def safe_url(raw: str | None) -> str | None:
    """API가 준 URL을 '그대로' 쓰되, 형식이 유효할 때만 채택. 수정·추측·생성하지 않는다."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    try:
        p = urlparse(raw)
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.netloc or " " in raw:
        return None
    return raw


class NewsItem(BaseModel):
    id: str
    headline: str
    summary: str = ""
    url: str | None = None  # None → 화면에 "원문 링크 없음"
    source: str = ""
    published_at: datetime
    related_tickers: list[str] = Field(default_factory=list)
    provider: str


class IndexQuote(BaseModel):
    name: str
    symbol: str
    close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    as_of: datetime | None = None
    provider: str
    is_proxy: bool = False  # 지수 대신 ETF 가격을 쓴 경우 True
    note: str | None = None


class EconEvent(BaseModel):
    name: str
    country: str
    at_utc: datetime | None
    date_et: date
    estimate: str | None = None
    previous: str | None = None
    impact: str | None = None
    provider: str


class EarningsEvent(BaseModel):
    symbol: str
    date_et: date
    hour: str | None = None  # bmo | amc | dmh | None(미확정)
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    provider: str


def stable_id(prefix: str, *parts: object) -> str:
    """프로세스 간에도 동일한 ID (내장 hash() 는 실행마다 달라지므로 사용하지 않음)."""
    import hashlib

    raw = "|".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"
