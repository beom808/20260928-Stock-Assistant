"""키움 REST 국내 지수: 시장구분 후보 순차 시도 · 값 검증 · 캐시 분리 · KIS fallback."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
import respx

from app.config import Settings
from app.fetch.http import ApiError
from app.fetch.providers import build_providers
from app.reports.builders import Ctx, _kr_indices
from app.timeutil import KST, UTC
from tests.helpers import no_llm

BASE = "https://api.kiwoom.com"
NOW = datetime(2026, 9, 29, 15, 40, tzinfo=KST).astimezone(UTC)


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **({"kiwoom_app_key": "k", "kiwoom_app_secret": "s"} | kw))


def token_ok():
    respx.post(f"{BASE}/oauth2/token").mock(
        return_value=httpx.Response(
            200, json={"token": "TKN", "token_type": "bearer", "return_code": 0}
        )
    )


def sect_router(table: dict[tuple[str, str], dict]):
    """(mrkt_tp, inds_cd) → 응답 본문. 표에 없으면 오류 응답."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["api-id"] == "ka20001"
        assert request.headers["authorization"] == "Bearer TKN"
        body = json.loads(request.content)
        key = (body["mrkt_tp"], body["inds_cd"])
        calls.append(key)
        return httpx.Response(
            200, json=table.get(key, {"return_code": 1, "return_msg": "잘못된 요청"})
        )

    respx.post(f"{BASE}/api/dostk/sect").mock(side_effect=handler)
    return calls


def ok(cur, pre, rt, sig):
    return {"return_code": 0, "cur_prc": cur, "pred_pre": pre, "flu_rt": rt, "pred_pre_sig": sig}


@pytest.fixture
def no_sleep(monkeypatch):
    async def _s(_):
        return None

    monkeypatch.setattr("app.fetch.http.asyncio.sleep", _s)


async def _run(sessions, st):
    p = build_providers(st, sessions)
    ctx = Ctx(st, p, no_llm(), sessions, now=NOW)
    try:
        return await _kr_indices(ctx), ctx
    finally:
        await p.aclose()


@respx.mock
async def test_candidates_tried_in_order_and_cache_not_shared(sessions, no_sleep):
    token_ok()
    calls = sect_router(
        {
            ("0", "001"): ok("+3,412.55", "18.20", "0.54", "2"),
            # 코스닥: "1" 은 오류 → "10" 에서 성공한다고 가정
            ("10", "101"): ok("-812.40", "3.10", "0.38", "5"),
        }
    )
    out, ctx = await _run(sessions, settings())
    kospi, kosdaq = out
    assert (kospi["close"], kospi["change"], kospi["change_pct"]) == (3412.55, 18.2, 0.54)
    assert (kosdaq["close"], kosdaq["change"], kosdaq["change_pct"]) == (812.4, -3.1, -0.38)
    assert calls == [("0", "001"), ("1", "101"), ("10", "101")]
    assert kosdaq["provider"] == "키움증권 REST API"
    assert not ctx.errors


@respx.mock
async def test_kosdaq_same_value_as_kospi_is_rejected(sessions, no_sleep):
    token_ok()
    same = ok("3412.55", "18.20", "0.54", "2")
    sect_router(
        {("0", "001"): same, ("1", "101"): same, ("10", "101"): ok("812.40", "0", "0", "3")}
    )
    out, _ = await _run(sessions, settings())
    assert out[1]["close"] == 812.4 and out[1]["change"] == 0.0


@respx.mock
async def test_implausible_value_not_adopted_then_kis_fallback(sessions, no_sleep):
    token_ok()
    sect_router({})  # 모든 후보 오류
    respx.post("https://openapi.koreainvestment.com:9443/oauth2/tokenP").mock(
        return_value=httpx.Response(200, json={"access_token": "T"})
    )
    respx.get(url__regex=r".*inquire-index-price.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output": {
                    "bstp_nmix_prpr": "3000.00",
                    "bstp_nmix_prdy_vrss": "1",
                    "prdy_vrss_sign": "2",
                    "bstp_nmix_prdy_ctrt": "0.03",
                },
            },
        )
    )
    out, ctx = await _run(sessions, settings(kis_app_key="a", kis_app_secret="b"))
    assert out[0]["provider"] == "한국투자증권 KIS Open API"
    assert not ctx.errors


def test_parse_rejects_out_of_range_and_error_codes():
    from app.fetch.kiwoom import KiwoomFetcher

    assert KiwoomFetcher._parse("KOSPI", ok("341255", "1820", "0.54", "2")) is None  # 단위 오해
    assert KiwoomFetcher._parse("KOSPI", {"return_code": 1, "cur_prc": "3000"}) is None
    assert KiwoomFetcher._parse("KOSPI", ok("", "0", "0", "3")) is None


@respx.mock
async def test_no_keys_gives_clear_error(sessions, no_sleep):
    out, ctx = await _run(sessions, Settings(_env_file=None))
    assert all("error" in o for o in out)
    assert any("KIWOOM_APP_KEY" in e for e in ctx.errors)


@respx.mock
async def test_token_failure_is_reported(sessions, no_sleep):
    respx.post(f"{BASE}/oauth2/token").mock(
        return_value=httpx.Response(200, json={"return_code": 3, "return_msg": "인증 실패"})
    )
    out, ctx = await _run(sessions, settings())
    assert all("error" in o for o in out)
    assert any("인증 실패" in e for e in ctx.errors)
    with pytest.raises(ApiError):
        p = build_providers(settings(), sessions)
        try:
            await p.kiwoom.index_quote("KOSPI")
        finally:
            await p.aclose()


@respx.mock
async def test_failed_token_is_not_cached_but_success_is(sessions, no_sleep):
    route = respx.post(f"{BASE}/oauth2/token").mock(
        side_effect=[
            httpx.Response(200, json={"return_code": 3, "return_msg": "일시 오류"}),
            httpx.Response(200, json={"token": "TKN", "return_code": 0}),
        ]
    )
    p = build_providers(settings(), sessions)
    try:
        with pytest.raises(ApiError):
            await p.kiwoom._token()
        assert await p.kiwoom._token() == "TKN"  # 실패가 캐시됐다면 여기서 다시 실패
        assert await p.kiwoom._token() == "TKN"  # 성공은 캐시 → 네트워크 추가 호출 없음
    finally:
        await p.aclose()
    assert route.call_count == 2


async def test_proxy_used_only_for_kiwoom(sessions):
    st = settings(kiwoom_proxy_url="http://user:pw@proxy.example.test:80")
    p = build_providers(st, sessions)
    try:
        assert p.kiwoom_http is not None
        assert p.kiwoom.client.http is p.kiwoom_http  # 키움만 프록시 클라이언트
        assert p.finnhub.client.http is p.http  # 나머지는 직접 접속
        assert p.kis.client.http is p.http
    finally:
        await p.aclose()
    p2 = build_providers(settings(), sessions)
    try:
        assert p2.kiwoom_http is None and p2.kiwoom.client.http is p2.http
    finally:
        await p2.aclose()


@respx.mock
async def test_investor_flows_reads_market_total_row_in_eok(sessions, no_sleep):
    """ka10051: 2026-09-29 실서버 응답 형식(종합 행 inds_cd 001/101, 억원, 부호 문자열)."""
    from app.reports.builders import _kr_flows

    token_ok()
    rows = {
        "0": [{"inds_cd": "001", "inds_nm": "종합(KOSPI)", "frgnr_netprps": "-29629",
               "orgn_netprps": "+1248", "ind_netprps": "+11942"},
              {"inds_cd": "002", "inds_nm": "대형주", "frgnr_netprps": "-27938"}],
        "1": [{"inds_cd": "101", "inds_nm": "종합(KOSDAQ)", "frgnr_netprps": "-1452",
               "orgn_netprps": "-18", "ind_netprps": "+1712"}],
    }  # fmt: skip
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["api-id"] == "ka10051"
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"return_code": 0, "inds_netprps": rows[body["mrkt_tp"]]})

    respx.post(f"{BASE}/api/dostk/sect").mock(side_effect=handler)
    st = settings()
    p = build_providers(st, sessions)
    ctx = Ctx(st, p, no_llm(), sessions, now=NOW)
    flows = await _kr_flows(ctx)
    await p.aclose()
    assert flows == [
        {"market": "KOSPI", "unit": "억원", "foreign": -29629.0, "institution": 1248.0,
         "retail": 11942.0},
        {"market": "KOSDAQ", "unit": "억원", "foreign": -1452.0, "institution": -18.0,
         "retail": 1712.0},
    ]  # fmt: skip
    assert seen[0] == {"mrkt_tp": "0", "amt_qty_tp": "0", "base_dt": "20260929", "stex_tp": "1"}


@respx.mock
async def test_investor_flows_error_is_warning_not_fake_value(sessions, no_sleep):
    from app.reports.builders import _kr_flows

    token_ok()
    respx.post(f"{BASE}/api/dostk/sect").mock(
        return_value=httpx.Response(200, json={"return_code": 2, "return_msg": "입력 값 오류"})
    )
    st = settings()
    p = build_providers(st, sessions)
    ctx = Ctx(st, p, no_llm(), sessions, now=NOW)
    assert await _kr_flows(ctx) == []
    await p.aclose()
    assert any("투자자별 순매수 수집 실패" in w for w in ctx.warnings)


def test_breadth_counts_parsed_and_checked():
    """ka20001 등락 종목 수(2026-10-02 실서버 코스닥 값). 합계가 안 맞으면 표시하지 않는다."""
    from app.fetch.kiwoom import _breadth

    body = {"rising": "1109", "stdns": "70", "fall": "562", "upl": "4", "lst": "0",
            "trde_frmatn_stk_num": "1741"}  # fmt: skip
    assert _breadth(body) == {"total": 1741, "rising": 1109, "flat": 70, "falling": 562,
                              "upper_limit": 4, "lower_limit": 0}  # fmt: skip
    assert _breadth(body | {"fall": "560"}) is None  # 합계 불일치
    assert _breadth({k: v for k, v in body.items() if k != "rising"}) is None  # 값 누락


def test_parse_includes_breadth():
    from app.fetch.kiwoom import KiwoomFetcher

    body = ok("+3,050.12", "-12.3", "-0.40", "5") | {
        "rising": "500", "stdns": "50", "fall": "400", "upl": "1", "lst": "2",
        "trde_frmatn_stk_num": "950",
    }  # fmt: skip
    q = KiwoomFetcher._parse("KOSPI", body)
    want = {"total": 950, "rising": 500, "flat": 50, "falling": 400,
            "upper_limit": 1, "lower_limit": 2}  # fmt: skip
    assert q is not None and q.breadth == want
    assert KiwoomFetcher._parse("KOSPI", ok("+3,050.12", "-12.3", "-0.40", "5")).breadth is None
