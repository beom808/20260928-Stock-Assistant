"""구독(푸시) 엔드포인트 · 알림 본문 · ECB 환율/FRED 매크로 파싱."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.fetch.http import ApiError
from app.fetch.macro import parse_ecb_series, parse_fred_latest
from app.fetch.providers import build_providers


@pytest.fixture
def client(sessions):
    from app import main
    from app.db.session import get_session

    def _override():
        with sessions() as s:
            yield s

    main.app.dependency_overrides[get_session] = _override
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_subscribe_unsubscribe_and_count_per_device(client):
    a, b, a2 = "tok-a" + "x" * 30, "tok-b" + "x" * 30, "tok-a2" + "x" * 30
    assert client.get("/push/count").json() == {"count": 0}
    assert client.post("/push/register", json={"token": a}).json()["count"] == 1
    assert client.post("/push/register", json={"token": a}).json()["count"] == 1  # 중복 X
    assert client.post("/push/register", json={"token": b}).json()["count"] == 2
    # 같은 기기에서 토큰이 바뀌면 이전 토큰을 교체 → 여전히 기기당 1명
    r = client.post("/push/register", json={"token": a2, "replaces": a})
    assert r.json()["count"] == 2
    assert client.post("/push/unregister", json={"token": a2}).json()["count"] == 1
    assert client.post("/push/unregister", json={"token": a2}).json()["count"] == 1  # 멱등
    assert client.get("/push/count").json() == {"count": 1}
    assert client.post("/push/unregister", json={"token": "short"}).status_code == 400


def test_push_body_has_key_numbers():
    from app.jobs.run import _eok, push_body

    assert _eok(-29629) == "−2조 9,629억" and _eok(1248) == "+1,248억" and _eok(None) == "-"
    kr = {
        "report_type": "kr-close-and-calendar",
        "generated_at_kst": "2026-09-29 15:40 KST",
        "data": {
            "indices": [
                {"name": "KOSPI", "close": 6870.81, "change_pct": -0.27},
                {"name": "KOSDAQ", "close": 849.8, "change_pct": 0.38},
            ],
            "fx": {"rate": 1357.93},
            "investor_flows": [{"market": "KOSPI", "foreign": -29629}],
        },
    }
    assert push_body(kr) == (
        "KOSPI 6,870.81(-0.27%) · KOSDAQ 849.80(+0.38%) · 원/달러 1,357.93 · 외국인 −2조 9,629억"
    )
    us = {"data": {"indices": [{"name": "S&P 500", "close": 7683.69, "change_pct": -0.77},
                               {"name": "다우존스", "error": "시세 없음"}]}}  # fmt: skip
    assert push_body(us) == "S&P 7,683.69(-0.77%)"
    wl = {"report_type": "kr-watchlist", "data": {"sectors": [{"kr_sector": "반도체"}]}}
    assert push_body(wl) == "주목: 반도체"
    assert push_body({"generated_at_kst": "t", "data": {}}) == "t 발행"


def test_parse_ecb_and_fred():
    ecb = {"rates": {"2026-09-25": {"KRW": 1356.0}, "2026-09-28": {"KRW": 1357.93},
                     "bad": {"KRW": 1}, "2026-09-24": {}}}  # fmt: skip
    assert parse_ecb_series(ecb) == [(date(2026, 9, 28), 1357.93), (date(2026, 9, 25), 1356.0)]
    assert parse_ecb_series(None) == []
    fred = {"observations": [{"date": "2026-09-25", "value": "5.17"},
                             {"date": "2026-09-24", "value": "."},
                             {"date": "2026-09-23", "value": "5.18"}]}  # fmt: skip
    assert parse_fred_latest(fred) == [(date(2026, 9, 25), 5.17), (date(2026, 9, 23), 5.18)]


@respx.mock
async def test_fred_macro_labels_lag_and_not_dxy(sessions):
    obs = {"observations": [{"date": "2026-09-25", "value": "5.17"},
                            {"date": "2026-09-24", "value": "5.18"}]}  # fmt: skip
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(200, json=obs)
    )
    p = build_providers(Settings(_env_file=None, fred_api_key="k" * 32), sessions)
    out = await p.macro.fred_macro()
    await p.aclose()
    assert [o["name"] for o in out] == ["미국 10년물 금리", "달러지수(연준 광의)"]
    assert out[0]["value"] == 5.17 and out[0]["change"] == -0.01 and out[0]["unit"] == "%"
    assert "1영업일" in out[0]["note"] and "DXY 와 다른" in out[1]["provider"]


async def test_fred_macro_requires_key(sessions):
    p = build_providers(Settings(_env_file=None), sessions)
    with pytest.raises(ApiError) as e:
        await p.macro.fred_macro()
    await p.aclose()
    assert e.value.kind == "config"
