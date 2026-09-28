"""타임존 변환: 미국 서머타임 전환(3월 둘째 일요일, 11월 첫째 일요일) 전후 케이스."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.timeutil import (
    ET,
    KST,
    UTC,
    et_wall_to_kst,
    is_us_dst,
    last_completed_us_session,
    us_close_kst,
)


# ── 정규장 마감 16:00 ET → KST ───────────────────────────────────────────
@pytest.mark.parametrize(
    "session, expected_kst",
    [
        # 2026: DST 시작 3/8(일), 종료 11/1(일)
        (date(2026, 3, 6), datetime(2026, 3, 7, 6, 0, tzinfo=KST)),  # 금, EST
        (date(2026, 3, 9), datetime(2026, 3, 10, 5, 0, tzinfo=KST)),  # 월, EDT
        (date(2026, 10, 30), datetime(2026, 10, 31, 5, 0, tzinfo=KST)),  # 금, EDT
        (date(2026, 11, 2), datetime(2026, 11, 3, 6, 0, tzinfo=KST)),  # 월, EST
        # 2027: DST 시작 3/14, 종료 11/7 — 연도별 날짜가 하드코딩이 아님을 확인
        (date(2027, 3, 12), datetime(2027, 3, 13, 6, 0, tzinfo=KST)),
        (date(2027, 3, 15), datetime(2027, 3, 16, 5, 0, tzinfo=KST)),
        (date(2027, 11, 5), datetime(2027, 11, 6, 5, 0, tzinfo=KST)),
        (date(2027, 11, 8), datetime(2027, 11, 9, 6, 0, tzinfo=KST)),
    ],
)
def test_us_close_in_kst_across_dst(session, expected_kst):
    assert us_close_kst(session) == expected_kst


def test_07_kst_report_always_after_us_close():
    for d in (date(2026, 1, 15), date(2026, 3, 9), date(2026, 7, 1), date(2026, 11, 2)):
        close = us_close_kst(d)
        assert close.hour in (5, 6)
        assert close.time() < time(7, 0)


@pytest.mark.parametrize(
    "d, dst",
    [
        (date(2026, 3, 7), False),
        (date(2026, 3, 8), True),  # 전환 당일(02:00 ET 이후 EDT) — 정오 기준 True
        (date(2026, 10, 31), True),
        (date(2026, 11, 1), False),
    ],
)
def test_is_us_dst_boundaries(d, dst):
    assert is_us_dst(d) is dst


# ── 매크로 지표(08:30 ET) · FOMC(14:00 ET) ────────────────────────────────
@pytest.mark.parametrize(
    "d, t, expected",
    [
        (date(2026, 3, 6), time(8, 30), datetime(2026, 3, 6, 22, 30, tzinfo=KST)),  # EST
        (date(2026, 3, 10), time(8, 30), datetime(2026, 3, 10, 21, 30, tzinfo=KST)),  # EDT
        (date(2026, 10, 30), time(8, 30), datetime(2026, 10, 30, 21, 30, tzinfo=KST)),
        (date(2026, 11, 6), time(8, 30), datetime(2026, 11, 6, 22, 30, tzinfo=KST)),
        # FOMC 성명 14:00 ET → 익일 03:00(EDT)/04:00(EST) KST, 기자회견 30분 후
        (date(2026, 9, 16), time(14, 0), datetime(2026, 9, 17, 3, 0, tzinfo=KST)),
        (date(2026, 9, 16), time(14, 30), datetime(2026, 9, 17, 3, 30, tzinfo=KST)),
        (date(2026, 12, 9), time(14, 0), datetime(2026, 12, 10, 4, 0, tzinfo=KST)),
    ],
)
def test_et_wall_to_kst(d, t, expected):
    assert et_wall_to_kst(d, t) == expected


def test_dst_transition_night_uses_tzdb_not_fixed_offset():
    # 3/8 01:59 EST 와 03:00 EDT 는 실제로 1분 차이
    a = datetime(2026, 3, 8, 1, 59, tzinfo=ET).astimezone(UTC)
    b = datetime(2026, 3, 8, 3, 0, tzinfo=ET).astimezone(UTC)
    assert (b - a).total_seconds() == 60


# ── 직전 완료 세션 판정 ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "kst_now, expected",
    [
        (datetime(2026, 9, 29, 7, 0, tzinfo=KST), date(2026, 9, 28)),  # 화 07:00 → 월 세션
        (datetime(2026, 9, 28, 7, 0, tzinfo=KST), date(2026, 9, 25)),  # 월 07:00 → 금 세션
        (datetime(2026, 9, 8, 7, 0, tzinfo=KST), date(2026, 9, 4)),  # 노동절(9/7) 다음날 → 금
        (datetime(2026, 3, 10, 4, 59, tzinfo=KST), date(2026, 3, 6)),  # EDT 마감 05:00 전
        (datetime(2026, 3, 10, 5, 0, tzinfo=KST), date(2026, 3, 9)),  # EDT 마감 직후
        (datetime(2026, 3, 7, 5, 30, tzinfo=KST), date(2026, 3, 5)),  # EST 마감 06:00 전
    ],
)
def test_last_completed_us_session(kst_now, expected):
    assert last_completed_us_session(kst_now.astimezone(UTC)) == expected
