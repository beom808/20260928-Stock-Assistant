"""익일 미국 이벤트 표: KST 변환(서머타임), BMO/AMC, 확정 시각 없음, 타임존 설정 자동 검증."""

from __future__ import annotations

from datetime import date, datetime, time

from app.schemas import EarningsEvent, EconEvent
from app.timeutil import KST, UTC, et_wall_to_utc
from app.transform.calendar import build_calendar, check_release_times, classify_event

WATCH = {"NVDA", "AAPL", "MSFT"}


def econ(name: str, d: date, t: time | None, est: str | None = None) -> EconEvent:
    return EconEvent(
        name=name,
        country="US",
        at_utc=et_wall_to_utc(d, t) if t else None,
        date_et=d,
        estimate=est,
        impact="High",
        provider="FMP",
    )


def test_classify_event():
    assert classify_event("Fed Interest Rate Decision") == "FOMC"
    assert classify_event("FOMC Press Conference") == "FOMC"
    assert classify_event("CPI YoY") == "매크로지표"
    assert classify_event("Nonfarm Payrolls") == "매크로지표"
    assert classify_event("Core PCE Price Index MoM") == "매크로지표"
    assert classify_event("Baker Hughes Oil Rig Count") == "기타 지표"


def test_cpi_row_kst_edt_and_est():
    now_edt = datetime(2026, 10, 13, 15, 40, tzinfo=KST).astimezone(UTC)
    cal = build_calendar(
        [econ("CPI YoY", date(2026, 10, 13), time(8, 30), "2.9%")], [], now_edt, WATCH
    )
    row = cal["rows"][0]
    assert row["kst"] == "10/13 21:30 KST" and row["et"] == "10/13 08:30 EDT"
    assert row["consensus"] == "2.9%" and row["time_confirmed"]

    now_est = datetime(2026, 11, 10, 15, 40, tzinfo=KST).astimezone(UTC)
    cal = build_calendar([econ("CPI YoY", date(2026, 11, 10), time(8, 30))], [], now_est, WATCH)
    assert cal["rows"][0]["kst"] == "11/10 22:30 KST"
    assert cal["rows"][0]["et"] == "11/10 08:30 EST"
    assert cal["rows"][0]["consensus"] is None


def test_fomc_row_next_day_kst_with_press_note():
    now = datetime(2026, 12, 9, 15, 40, tzinfo=KST).astimezone(UTC)
    cal = build_calendar(
        [econ("Fed Interest Rate Decision", date(2026, 12, 9), time(14, 0))], [], now, WATCH
    )
    row = cal["rows"][0]
    assert row["kind"] == "FOMC" and row["kst"] == "12/10 04:00 KST"
    assert "30분" in row["note"]


def test_earnings_bmo_amc_and_unknown_never_invent_time():
    now = datetime(2026, 10, 27, 15, 40, tzinfo=KST).astimezone(UTC)  # ET 10/27 02:40
    evs = [
        EarningsEvent(
            symbol="MSFT",
            date_et=date(2026, 10, 27),
            hour="amc",
            provider="Finnhub",
            eps_estimate=3.1,
        ),
        EarningsEvent(symbol="AAPL", date_et=date(2026, 10, 28), hour="bmo", provider="Finnhub"),
        EarningsEvent(symbol="NVDA", date_et=date(2026, 10, 28), hour=None, provider="FMP"),
        EarningsEvent(symbol="ZZZZ", date_et=date(2026, 10, 27), hour="bmo", provider="Finnhub"),
    ]
    cal = build_calendar([], evs, now, WATCH)
    rows = {r["event"]: r for r in cal["rows"]}
    assert "ZZZZ 실적 발표" not in rows  # 워치리스트 밖
    msft = rows["MSFT 실적 발표"]
    assert "AMC" in msft["et"] and "확정 시각 없음" in msft["et"]
    assert msft["kst"].startswith("10/28 05:00 KST 이후")  # 16:00 EDT
    assert msft["consensus"] == "EPS 예상 3.1" and msft["time_confirmed"] is False
    aapl = rows["AAPL 실적 발표"]
    assert aapl["kst"].startswith("10/28 22:30 KST 이전")  # 09:30 EDT
    nvda = rows["NVDA 실적 발표"]
    assert nvda["kst"] == "확정 시각 없음" and ":" not in nvda["et"].split(" ", 1)[1]


def test_window_excludes_past_and_far_events():
    now = datetime(2026, 10, 13, 15, 40, tzinfo=KST).astimezone(UTC)
    evs = [
        econ("CPI YoY", date(2026, 10, 12), time(8, 30)),  # 이미 지남
        econ("PPI MoM", date(2026, 10, 14), time(8, 30)),  # 48h 이내
        econ("Retail Sales MoM", date(2026, 10, 20), time(8, 30)),  # 범위 밖
    ]
    cal = build_calendar(evs, [], now, WATCH)
    assert [r["event"] for r in cal["rows"]] == ["PPI MoM"]


def test_release_time_sanity_check_flags_wrong_timezone():
    good = [econ("CPI YoY", date(2026, 10, 13), time(8, 30))]
    assert check_release_times(good) == []
    # API 가 ET 시각을 UTC 로 잘못 해석한 경우 → 04:30 ET 로 보임
    wrong = [
        EconEvent(
            name="CPI YoY",
            country="US",
            at_utc=datetime(2026, 10, 13, 8, 30, tzinfo=UTC),
            date_et=date(2026, 10, 13),
            provider="FMP",
        )
    ]
    w = check_release_times(wrong)
    assert w and "FMP_ECON_CALENDAR_TZ" in w[0]
