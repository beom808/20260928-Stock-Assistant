"""BEA·연준 공식 발표 일정 파싱과 출처별 독립 수집."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time

import httpx
import pytest
import respx

from app.config import Settings
from app.fetch.official import BEA_URL, FED_URL, parse_bea, parse_fed, parse_fed_time
from app.fetch.providers import build_providers

D0, D1 = date(2026, 9, 28), date(2026, 10, 1)
BEA = {
    "Gross Domestic Product": {
        "release_dates": [
            "2026-08-26T12:30:00+00:00",
            "2026-09-30T12:30:00+00:00",
            "2026-09-30T12:30:00+00:00",  # 원본의 중복
        ]
    },
    "Travel and Tourism Satellite Account": {"release_dates": ["2026-09-30T14:00:00+00:00"]},
    "last_updated": "2026-09-01",  # dict 가 아닌 항목
}
FED = {
    "events": [
        {"title": "FOMC Meeting", "time": "2:00 p.m.", "month": "2026-09", "days": "30"},
        {"title": "FOMC Minutes", "time": "2:00 p.m.", "month": "2026-10", "days": "7"},
        {"title": "G.17 - Industrial Production and Capacity Utilization", "time": "9:15 a.m.",
         "month": "2026-09", "days": "29, 30"},
        {"title": "Beige Book", "time": "", "month": "2026-10", "days": "1"},
        {"title": "Speech - Governor X", "time": "3:00 p.m.", "month": "2026-09", "days": "29"},
    ]
}  # fmt: skip


def test_parse_fed_time():
    assert parse_fed_time("2:00 p.m.") == time(14, 0)
    assert parse_fed_time("9:15 a.m.") == time(9, 15)
    assert parse_fed_time("12:00 p.m.") == time(12, 0)
    assert parse_fed_time("12:30 a.m.") == time(0, 30)
    assert parse_fed_time("") is None and parse_fed_time("TBD") is None


def test_parse_bea_filters_range_duplicates_and_unknown_releases():
    ev = parse_bea(BEA, D0, D1)
    assert len(ev) == 1
    assert ev[0].name.startswith("GDP") and ev[0].at_utc == datetime(
        2026, 9, 30, 12, 30, tzinfo=UTC
    )
    assert ev[0].date_et == date(2026, 9, 30)
    assert parse_bea(["not", "a", "dict"], D0, D1) == []


def test_parse_fed_titles_days_and_missing_time():
    ev = parse_fed(FED, D0, D1)
    names = sorted((e.name, e.date_et) for e in ev)
    assert [n for n, _ in names].count("산업생산 (Fed G.17)") == 2  # "29, 30" → 2건
    assert not any("Speech" in n or "의사록" in n for n, _ in names)  # 범위 밖 · 대상 아님
    fomc = next(e for e in ev if e.name.startswith("FOMC"))
    assert fomc.at_utc == datetime(2026, 9, 30, 18, 0, tzinfo=UTC)  # 14:00 EDT
    beige = next(e for e in ev if e.name.startswith("베이지북"))
    assert beige.at_utc is None and beige.date_et == date(2026, 10, 1)  # 시각 미확정


@pytest.fixture
def no_sleep(monkeypatch):
    async def _s(_):
        return None

    monkeypatch.setattr("app.fetch.http.asyncio.sleep", _s)


@respx.mock
async def test_sources_are_independent_and_fed_bom_is_handled(sessions, no_sleep):
    respx.get(BEA_URL).mock(return_value=httpx.Response(503))
    body = "﻿" + json.dumps(FED)  # 연준 응답은 UTF-8 BOM 으로 시작
    respx.get(FED_URL).mock(
        return_value=httpx.Response(
            200, content=body.encode("utf-8"), headers={"content-type": "application/json"}
        )  # fmt: skip
    )
    p = build_providers(Settings(_env_file=None), sessions)
    events, failed = await p.official.economic_calendar(D0, D1)
    await p.aclose()
    assert any(e.name.startswith("FOMC") for e in events)
    assert len(failed) == 1 and failed[0].startswith("BEA")
    ua = respx.calls.last.request.headers["User-Agent"]
    assert ua.startswith("stock-assistant/")
