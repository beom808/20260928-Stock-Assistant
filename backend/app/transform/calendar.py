"""기능 C-2: 익일(향후 1~2일) 미국 시장 이벤트 표 (경제캘린더·실적캘린더 API 기반, 매일 갱신).

- 시각 변환은 timeutil(IANA tz DB)만 사용 → 서머타임 자동 반영.
- 실적발표는 BMO(장전)/AMC(장후)/DMH(장중)만 표시하고 구체 시각은 만들지 않는다("확정 시각 없음").
- 경제지표 발표시각 자동 검증: CPI·고용·PCE 등은 08:30 ET, FOMC 금리결정은 14:00 ET 여야 정상.
  어긋나면 API 타임존 설정(FMP_ECON_CALENDAR_TZ) 오류 가능성을 warnings 로 알린다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.schemas import EarningsEvent, EconEvent
from app.timeutil import ET, KST, US_CLOSE_ET, US_OPEN_ET, UTC, et_wall_to_kst, to_et, to_kst
from app.transform.text import has_keyword

FOMC_KW = (
    "fomc",
    "fed interest rate decision",
    "federal funds rate",
    "fed rate decision",
    "interest rate decision",
    "fomc press conference",
    "fed press conference",
)
CORE_MACRO_KW = (
    "cpi",
    "consumer price index",
    "core cpi",
    "nonfarm payrolls",
    "non farm payrolls",
    "non-farm payrolls",
    "unemployment rate",
    "pce",
    "core pce",
    "ppi",
    "producer price index",
    "gdp",
    "retail sales",
    "initial jobless claims",
    "ism manufacturing",
    "ism services",
    "jolts",
    "michigan consumer sentiment",
    "average hourly earnings",
)
# 발표 시각이 관례적으로 고정된 지표 (ET 벽시계 기준) — 타임존 설정 자동 검증용
EXPECTED_ET = {
    "cpi": time(8, 30),
    "consumer price index": time(8, 30),
    "nonfarm payrolls": time(8, 30),
    "non farm payrolls": time(8, 30),
    "pce": time(8, 30),
    "ppi": time(8, 30),
    "initial jobless claims": time(8, 30),
    "fed interest rate decision": time(14, 0),
}


def classify_event(name: str) -> str:
    if has_keyword(name, FOMC_KW):
        return "FOMC"
    if has_keyword(name, CORE_MACRO_KW):
        return "매크로지표"
    return "기타 지표"


def _fmt_et(dt: datetime) -> str:
    e = to_et(dt)
    return f"{e:%m/%d %H:%M} {e.tzname()}"


def _fmt_kst(dt: datetime) -> str:
    return f"{to_kst(dt):%m/%d %H:%M} KST"


def check_release_times(events: list[EconEvent]) -> list[str]:
    bad = []
    for ev in events:
        if ev.at_utc is None:
            continue
        name = ev.name.lower()
        for kw, expected in EXPECTED_ET.items():
            if has_keyword(name, (kw,)):
                actual = to_et(ev.at_utc).time()
                if actual != expected:
                    bad.append(f"{ev.name}: {actual:%H:%M} ET (예상 {expected:%H:%M} ET)")
                break
    if bad:
        return [
            "경제캘린더 발표시각이 관례와 다릅니다 — API 타임존 설정(FMP_ECON_CALENDAR_TZ) 또는 "
            "일정 변경 여부를 확인하세요: " + "; ".join(bad[:3])
        ]
    return []


def econ_rows(events: list[EconEvent], start: datetime, end: datetime) -> list[dict]:
    rows = []
    for ev in events:
        kind = classify_event(ev.name)
        impact = (ev.impact or "").lower()
        if kind == "기타 지표" and impact not in ("high", "medium", ""):
            continue
        if ev.at_utc is None:
            d_ok = start.astimezone(ET).date() <= ev.date_et <= end.astimezone(ET).date()
            if not d_ok:
                continue
            et_s, kst_s, sort_key, confirmed = (
                f"{ev.date_et:%m/%d} 시각 미확정",
                "시각 미확정",
                datetime.combine(ev.date_et, time(0), tzinfo=ET),
                False,
            )
        else:
            if not (start <= ev.at_utc <= end):
                continue
            et_s, kst_s, sort_key, confirmed = (
                _fmt_et(ev.at_utc),
                _fmt_kst(ev.at_utc),
                ev.at_utc,
                True,
            )
        note = None
        if kind == "FOMC" and "press" not in ev.name.lower():
            note = "기자회견은 통상 성명 발표 30분 후"
        rows.append(
            {
                "event": ev.name,
                "kind": kind,
                "et": et_s,
                "kst": kst_s,
                "consensus": ev.estimate,
                "previous": ev.previous,
                "time_confirmed": confirmed,
                "note": note,
                "provider": ev.provider,
                "_sort": sort_key.astimezone(UTC).isoformat(),
            }
        )
    return rows


_HOUR_TEXT = {
    "bmo": ("장 시작 전(BMO)", "before"),
    "amc": ("장 마감 후(AMC)", "after"),
    "dmh": ("장중(DMH)", "during"),
}


def earnings_rows(
    events: list[EarningsEvent], et_dates: list[date], watchlist: set[str]
) -> list[dict]:
    rows = []
    seen: set[tuple[str, date]] = set()
    for ev in events:
        if ev.date_et not in et_dates or ev.symbol not in watchlist:
            continue
        if (ev.symbol, ev.date_et) in seen:
            continue
        seen.add((ev.symbol, ev.date_et))
        if ev.hour in _HOUR_TEXT:
            label, rel = _HOUR_TEXT[ev.hour]
            et_s = f"{ev.date_et:%m/%d} {label} · 확정 시각 없음"
            if rel == "before":
                ref = et_wall_to_kst(ev.date_et, US_OPEN_ET)
                kst_s = f"{ref:%m/%d %H:%M} KST 이전(개장 전) · 확정 시각 없음"
            elif rel == "after":
                ref = et_wall_to_kst(ev.date_et, US_CLOSE_ET)
                kst_s = f"{ref:%m/%d %H:%M} KST 이후(마감 후) · 확정 시각 없음"
            else:
                o, c = et_wall_to_kst(ev.date_et, US_OPEN_ET), et_wall_to_kst(
                    ev.date_et, US_CLOSE_ET
                )
                kst_s = f"{o:%m/%d %H:%M}~{c:%H:%M} KST 사이 · 확정 시각 없음"
            sort_t = time(9, 0) if rel == "before" else time(16, 1) if rel == "after" else time(12)
        else:
            et_s = f"{ev.date_et:%m/%d} 발표 시점 미확정(BMO/AMC 정보 없음)"
            kst_s = "확정 시각 없음"
            sort_t = time(23, 59)
        eps = f"EPS 예상 {ev.eps_estimate:g}" if isinstance(ev.eps_estimate, (int, float)) else None
        rows.append(
            {
                "event": f"{ev.symbol} 실적 발표",
                "kind": "실적발표",
                "et": et_s,
                "kst": kst_s,
                "consensus": eps,
                "previous": None,
                "time_confirmed": False,
                "note": None,
                "provider": ev.provider,
                "_sort": datetime.combine(ev.date_et, sort_t, tzinfo=ET)
                .astimezone(UTC)
                .isoformat(),
            }
        )
    return rows


def build_calendar(
    econ: list[EconEvent],
    earnings: list[EarningsEvent],
    now: datetime,
    watchlist: set[str],
    horizon: timedelta = timedelta(hours=48),
) -> dict:
    end = now + horizon
    et_today = to_et(now).date()
    et_dates = [et_today + timedelta(days=i) for i in range(0, 3)]
    rows = econ_rows(econ, now, end) + earnings_rows(earnings, et_dates, watchlist)
    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        r.pop("_sort")
    return {
        "window_kst": f"{to_kst(now):%m/%d %H:%M} ~ {end.astimezone(KST):%m/%d %H:%M} KST",
        "rows": rows,
        "warnings": check_release_times(econ),
    }
