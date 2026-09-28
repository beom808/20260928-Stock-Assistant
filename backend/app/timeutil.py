"""타임존 유틸리티.

원칙
- 서버/DB 는 항상 UTC(aware datetime) 로 다룬다.
- ET↔KST 변환은 IANA tz DB(zoneinfo: America/New_York, Asia/Seoul)만 사용한다.
  수동 오프셋(+13h/+14h 등) 계산 금지 — 서머타임 전환일 버그 방지.
- 미국 서머타임(3월 둘째 일요일 ~ 11월 첫째 일요일)은 tz DB 가 자동 반영하므로 하드코딩하지 않는다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import holidays

UTC = UTC
ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

US_OPEN_ET = time(9, 30)
US_CLOSE_ET = time(16, 0)
KRX_OPEN_KST = time(9, 0)
KRX_CLOSE_KST = time(15, 30)


def now_utc() -> datetime:
    return datetime.now(UTC)


def ensure_aware(dt: datetime, assume: ZoneInfo | timezone = UTC) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=assume)


def to_kst(dt: datetime) -> datetime:
    return ensure_aware(dt).astimezone(KST)


def to_et(dt: datetime) -> datetime:
    return ensure_aware(dt).astimezone(ET)


def et_wall_to_utc(d: date, t: time) -> datetime:
    """미국 동부 '벽시계' 시각(d, t)을 UTC 로. DST 여부는 tz DB 가 결정."""
    return datetime.combine(d, t, tzinfo=ET).astimezone(UTC)


def et_wall_to_kst(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=ET).astimezone(KST)


def is_us_dst(d: date) -> bool:
    """해당 날짜 정오(ET) 기준 서머타임(EDT) 여부."""
    return bool(datetime.combine(d, time(12, 0), tzinfo=ET).dst())


def et_abbrev(d: date, t: time = time(12, 0)) -> str:
    return datetime.combine(d, t, tzinfo=ET).tzname() or "ET"


def fmt_kst(dt: datetime) -> str:
    return to_kst(dt).strftime("%Y-%m-%d %H:%M KST")


# ── 거래일 판정 ──────────────────────────────────────────────────────────
# holidays 라이브러리의 거래소 휴장일(XNYS, XKRX)을 사용.
# 임시휴장(재난 등)·조기폐장(13:00 ET)은 반영되지 않을 수 있으므로 운영 시 거래소 공지로 보완 필요.


def _nyse_holidays(year: int) -> holidays.HolidayBase:
    return holidays.financial_holidays("XNYS", years=[year - 1, year, year + 1])


def _krx_holidays(year: int) -> holidays.HolidayBase:
    return holidays.financial_holidays("XKRX", years=[year - 1, year, year + 1])


def is_us_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _nyse_holidays(d.year)


def is_kr_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _krx_holidays(d.year)


def last_completed_us_session(at: datetime) -> date:
    """`at` 시점 기준으로 정규장 마감(16:00 ET)까지 끝난 가장 최근 미국 거래일."""
    et_now = to_et(at)
    d = et_now.date()
    if not (is_us_trading_day(d) and et_now.time() >= US_CLOSE_ET):
        d -= timedelta(days=1)
        while not is_us_trading_day(d):
            d -= timedelta(days=1)
    return d


def us_close_kst(d: date) -> datetime:
    """미국 정규장 마감 시각의 KST 환산 (EDT: 05:00, EST: 06:00 다음날)."""
    return et_wall_to_kst(d, US_CLOSE_ET)


def kst_today(at: datetime | None = None) -> date:
    return to_kst(at or now_utc()).date()
