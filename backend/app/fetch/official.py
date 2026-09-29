"""미국 공식 기관 발표 일정 — 경제캘린더(무료·키 없음).

GitHub Actions 에서 실제 응답을 확인한 형식 (2026-09-29 점검, backend/scripts/probe_calendars.py):
- BEA  https://apps.bea.gov/API/signup/release_dates.json
  {"<발표명>": {"release_dates": ["2026-09-30T12:30:00+00:00", ...]}, ...}  (UTC, 시각 포함)
  dict 가 아닌 항목이 섞여 있을 수 있어 건너뛴다.
- 연준 https://www.federalreserve.gov/json/calendar.json  (UTF-8 BOM 포함)
  {"events": [{"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-10",
               "days": "28", "type": "FOMC"}, ...]}
  days 는 "1, 8, 15" 처럼 여러 날일 수 있고 time 은 빈 문자열일 수 있다(→ 시각 미확정).
  시각은 연준(워싱턴 D.C.) 기준 미 동부시각으로 해석한다.
- BLS(CPI·고용·PPI)는 자동 요청을 차단(403 Access Denied, 봇 정책)하므로 직접 수집하지 않는다.
  → FRED API(세인트루이스 연준, 무료 키)의 fred/releases/dates 로 **발표일**만 받는다.
    FRED 는 시각을 주지 않으므로 BLS 의 관례 발표 시각(08:30 ET 등)을 붙이고
    '관례 시각·미확정' 으로 표시한다(확정 시각처럼 보이지 않게).

두 출처는 서로 독립적으로 수집하고, 한쪽이 실패해도 다른 쪽 일정은 표시한다.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime, time, timedelta

from app.fetch.http import ApiClient, ApiError
from app.schemas import EconEvent
from app.timeutil import ET

BEA_URL = "https://apps.bea.gov/API/signup/release_dates.json"
FED_URL = "https://www.federalreserve.gov/json/calendar.json"
# 자동 수집임을 밝히는 User-Agent (확인 결과 BEA·연준 모두 200 응답)
HEADERS = {
    "User-Agent": "stock-assistant/1.0 (+https://github.com/beom808/20260928-Stock-Assistant)"
}

# 시장에 영향이 큰 BEA 발표만 (이름은 classify_event 키워드 gdp/pce 에 걸리도록 구성)
BEA_RELEASES = {
    "Gross Domestic Product": "GDP 국내총생산 (BEA Gross Domestic Product)",
    "Personal Income and Outlays": "PCE 물가·개인소득/지출 (BEA Personal Income and Outlays)",
    "U.S. International Trade in Goods and Services": "무역수지 (BEA International Trade)",
}
# 연준 일정 중 표에 넣을 것: 제목 → 표시 이름
FED_TITLES = {
    "FOMC Meeting": "FOMC 금리 결정·성명 (FOMC Meeting)",
    "FOMC Press Conference": "FOMC 기자회견 (FOMC Press Conference)",
    "FOMC Minutes": "FOMC 의사록 (FOMC Minutes)",
    "Beige Book": "베이지북 (Beige Book)",
    "G.17 - Industrial Production and Capacity Utilization": "산업생산 (Fed G.17)",
}
FRED_URL = "https://api.stlouisfed.org/fred/releases/dates"
# FRED 발표명 → (표시 이름, 관례 발표 시각 ET). 발표명은 FRED release_name 과 정확히 일치해야 함
FRED_RELEASES: dict[str, tuple[str, time]] = {
    "Consumer Price Index": ("CPI 소비자물가 (BLS Consumer Price Index)", time(8, 30)),
    "Employment Situation": ("고용보고서·비농업고용 (BLS Employment Situation)", time(8, 30)),
    "Producer Price Index": ("PPI 생산자물가 (BLS Producer Price Index)", time(8, 30)),
    "Advance Monthly Sales for Retail and Food Services": (
        "소매판매 retail sales (Census)",
        time(8, 30),
    ),
    "Unemployment Insurance Weekly Claims Report": (
        "신규 실업수당 청구 initial jobless claims (DOL)",
        time(8, 30),
    ),
    "Job Openings and Labor Turnover Survey": ("JOLTS 구인·이직 (BLS)", time(10, 0)),
}
CONVENTION_NOTE = "관례 시각·미확정"
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\s*$", re.I)


def parse_fed_time(raw: str) -> time | None:
    """'2:00 p.m.' → 14:00, '9:15 a.m.' → 09:15, 빈 값·형식 불명 → None(시각 미확정)."""
    m = _TIME.match(raw or "")
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if not (1 <= h <= 12 and 0 <= mi < 60):
        return None
    h = h % 12 + (12 if ap == "p" else 0)
    return time(h, mi)


def parse_bea(body: object, d_from: date, d_to: date) -> list[EconEvent]:
    out: list[EconEvent] = []
    if not isinstance(body, dict):
        return out
    for key, label in BEA_RELEASES.items():
        entry = body.get(key)
        if not isinstance(entry, dict):
            continue
        seen: set[str] = set()
        for raw in entry.get("release_dates") or []:
            if raw in seen:  # 원본에 같은 시각이 중복된 경우가 있다
                continue
            seen.add(raw)
            try:
                at = datetime.fromisoformat(str(raw))
            except ValueError:
                continue
            if at.tzinfo is None:
                continue
            at_utc = at.astimezone(UTC)
            d_et = at_utc.astimezone(ET).date()
            if d_from <= d_et <= d_to:
                out.append(
                    EconEvent(
                        name=label,
                        country="US",
                        at_utc=at_utc,
                        date_et=d_et,
                        impact="high",
                        provider="BEA 공식 발표일정",
                    )  # fmt: skip
                )
    return out


def parse_fed(body: object, d_from: date, d_to: date) -> list[EconEvent]:
    out: list[EconEvent] = []
    events = body.get("events") if isinstance(body, dict) else None
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        title = html.unescape(str(ev.get("title") or "")).strip()
        label = FED_TITLES.get(title)
        if label is None:
            continue
        try:
            y, m = (int(x) for x in str(ev.get("month") or "").split("-"))
        except ValueError:
            continue
        t = parse_fed_time(str(ev.get("time") or ""))
        for part in str(ev.get("days") or "").split(","):
            try:
                d = date(y, m, int(part.strip()))
            except ValueError:
                continue
            if not d_from <= d <= d_to:
                continue
            at_utc = datetime.combine(d, t, tzinfo=ET).astimezone(UTC) if t else None
            out.append(
                EconEvent(
                    name=label,
                    country="US",
                    at_utc=at_utc,
                    date_et=d,
                    impact="high",
                    provider="연준 공식 일정",
                )  # fmt: skip
            )
    return out


def parse_fred(body: object, d_from: date, d_to: date) -> tuple[list[EconEvent], list[str]]:
    """(일정, 기간 안에 있었지만 대상이 아닌 발표명 — 진단용)."""
    out: list[EconEvent] = []
    others: set[str] = set()
    rows = body.get("release_dates") if isinstance(body, dict) else None
    seen: set[tuple[str, date]] = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("release_name") or "").strip()
        try:
            d = date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        if not d_from <= d <= d_to:
            continue
        spec = FRED_RELEASES.get(name)
        if spec is None:
            others.add(name)
            continue
        if (name, d) in seen:
            continue
        seen.add((name, d))
        label, t = spec
        out.append(
            EconEvent(
                name=label,
                country="US",
                at_utc=datetime.combine(d, t, tzinfo=ET).astimezone(UTC),
                date_et=d,
                impact="high",
                provider="FRED 발표일(BLS 등)",
                time_note=CONVENTION_NOTE,
            )
        )
    return out, sorted(others)


def _is_dict(body: object) -> bool:
    return isinstance(body, dict)


class OfficialCalendarFetcher:
    provider = "official"

    def __init__(self, client: ApiClient, fred_api_key: str = "") -> None:
        self.client = client
        self.fred_api_key = fred_api_key
        self.fred_other_releases: list[str] = []  # 진단용(로그)

    async def _get(self, url: str) -> object:
        res = await self.client.get_json(
            url, headers=HEADERS, ttl=timedelta(hours=6), cache_if=_is_dict
        )
        return res.data

    async def economic_calendar(
        self, d_from: date, d_to: date
    ) -> tuple[list[EconEvent], list[str]]:
        """(일정, 실패한 출처 설명 목록). 출처별로 독립 수집한다."""
        events: list[EconEvent] = []
        failed: list[str] = []
        for name, url, parse in (("BEA", BEA_URL, parse_bea), ("연준", FED_URL, parse_fed)):
            try:
                events += parse(await self._get(url), d_from, d_to)
            except ApiError as e:
                failed.append(f"{name} 일정 수집 실패({e.kind}): {e}")
        if self.fred_api_key:
            try:
                res = await self.client.get_json(
                    FRED_URL,
                    params={
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                        "realtime_start": d_from.isoformat(),
                        "realtime_end": d_to.isoformat(),
                        "include_release_dates_with_no_data": "true",
                        "sort_order": "asc",
                        "limit": 1000,
                    },
                    ttl=timedelta(hours=6),
                    cache_if=_is_dict,
                )
                fred, self.fred_other_releases = parse_fred(res.data, d_from, d_to)
                events += fred
            except ApiError as e:
                failed.append(f"FRED 일정 수집 실패({e.kind}): {e}")
        return events, failed
