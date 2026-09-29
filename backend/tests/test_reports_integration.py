"""리포트 조립 통합 테스트 (외부 API 는 respx 로 모킹): fallback · partial 상태 · 저장."""

from __future__ import annotations

import re
from datetime import datetime

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import store
from app.disclaimer import DISCLAIMER_KO
from app.fetch.providers import build_providers
from app.reports.builders import KR_CLOSE, KR_WATCHLIST, US_CLOSE, generate
from app.timeutil import KST, UTC
from tests.helpers import no_llm

NOW = datetime(2026, 9, 29, 7, 0, tzinfo=KST).astimezone(UTC)  # 화 07:00 KST → 9/28(월) 세션


def settings(**kw) -> Settings:
    base = dict(
        finnhub_api_key="fh",
        fmp_api_key="fmp",
        kis_app_key="k",
        kis_app_secret="s",
        us_megacap_watchlist="NVDA,AAPL",
        anthropic_api_key="",
    )
    return Settings(_env_file=None, **(base | kw))


def news(i: int, ts: int, headline: str, url: str = "https://example.com/n") -> dict:
    return {
        "id": i,
        "datetime": ts,
        "headline": headline,
        "summary": "s.",
        "url": url,
        "source": "X",
        "related": "",
    }


def mock_finnhub(ok_news: bool = True):
    ts = int(datetime(2026, 9, 28, 20, 0, tzinfo=UTC).timestamp())
    general = [news(i, ts - i * 60, f"Fed headline {i} on inflation") for i in range(12)]
    respx.get("https://finnhub.io/api/v1/news").mock(
        return_value=httpx.Response(200, json=general) if ok_news else httpx.Response(500)
    )
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 500.0, "d": 5.0, "dp": 1.0, "t": ts})
    )


@pytest.fixture
def no_sleep(monkeypatch):
    async def _s(_):
        return None

    monkeypatch.setattr("app.fetch.http.asyncio.sleep", _s)


@respx.mock
async def test_us_close_falls_back_to_etf_proxy_when_index_plan_denied(sessions, no_sleep):
    mock_finnhub()
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(402, text="Special Endpoint")
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(US_CLOSE, st, p, no_llm(), sessions, now=NOW)
    await p.aclose()

    assert payload["disclaimer"] == DISCLAIMER_KO
    assert payload["generated_at_kst"] == "2026-09-29 07:00 KST"
    d = payload["data"]
    assert d["session_date_et"] == "2026-09-28"
    assert d["session_close_kst"] == "2026-09-29 05:00 KST"
    assert all(i["is_proxy"] for i in d["indices"])
    assert len(d["news"]) == 10
    assert payload["status"] == "ok"
    assert any(s["name"] == "Finnhub" for s in payload["sources"])
    with sessions() as s:
        assert store.get_report(s, US_CLOSE) is not None


@respx.mock
async def test_partial_status_when_news_fails_and_stale_absent(sessions, no_sleep):
    mock_finnhub(ok_news=False)
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(
            200, json=[{"price": 1.0, "change": 0.1, "changePercentage": 0.5}]
        )
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(US_CLOSE, st, p, no_llm(), sessions, now=NOW)
    await p.aclose()
    assert payload["status"] == "partial"
    assert any("시장 뉴스 수집 실패" in e for e in payload["errors"])


@respx.mock
async def test_kr_watchlist_builds_us_report_if_missing(sessions, no_sleep):
    mock_finnhub()
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(402)
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(KR_WATCHLIST, st, p, no_llm(), sessions, now=NOW)
    await p.aclose()
    assert "프리마켓" in payload["data"]["notice"]
    assert payload["data"]["macro_points"]
    with sessions() as s:
        assert store.get_report(s, US_CLOSE) is not None


@respx.mock
async def test_dry_run_does_not_store_reports(sessions, no_sleep):
    """테스트 실행(save=False)은 화면에 보이는 리포트를 덮어쓰지 않는다."""
    mock_finnhub()
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(402)
    )
    st = settings()
    p = build_providers(st, sessions)
    us = await generate(US_CLOSE, st, p, no_llm(), sessions, now=NOW, save=False)
    kr = await generate(KR_WATCHLIST, st, p, no_llm(), sessions, now=NOW, save=False)
    await p.aclose()
    assert len(us["data"]["news"]) == 10 and kr["data"]["macro_points"]
    with sessions() as s:
        assert store.get_report(s, US_CLOSE) is None
        assert store.get_report(s, KR_WATCHLIST) is None


def test_dry_run_summary_lists_issues_and_calendar():
    from app.jobs.run import _dry_run_summary

    out = _dry_run_summary(
        {
            "status": "ok",
            "sources": [{"name": "네이버 검색 API(뉴스)"}],
            "data": {
                "indices": [{"name": "KOSPI", "close": 1.0, "provider": "키움증권 REST API"}],
                "issue_method": "llm",
                "issues": [{"title": "t", "summary": "s", "summary_origin": "llm", "url": "u"}],
                "calendar": {"rows": [{"event": "CPI", "kind": "경제지표", "et": "e", "kst": "k"}]},
            },
        }
    )
    assert "네이버 검색 API(뉴스)" in out and '"CPI"' in out and '"llm"' in out


@respx.mock
async def test_kr_close_and_calendar(sessions, no_sleep):
    now = datetime(2026, 9, 29, 15, 40, tzinfo=KST).astimezone(UTC)
    respx.post("https://openapi.koreainvestment.com:9443/oauth2/tokenP").mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 86400})
    )
    respx.get(
        re.compile(r"https://openapi\.koreainvestment\.com:9443/uapi/.*inquire-index-price.*")
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output": {
                    "bstp_nmix_prpr": "3,050.12",
                    "bstp_nmix_prdy_vrss": "12.3",
                    "prdy_vrss_sign": "5",
                    "bstp_nmix_prdy_ctrt": "0.40",
                },
            },
        )
    )
    respx.get("https://financialmodelingprep.com/stable/economic-calendar").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "date": "2026-09-29 14:00:00",
                    "country": "US",
                    "event": "JOLTS Job Openings",
                    "estimate": 7.1,
                    "previous": 7.2,
                    "impact": "High",
                },
                {
                    "date": "2026-09-29 14:00:00",
                    "country": "DE",
                    "event": "German thing",
                    "impact": "High",
                },
            ],
        )
    )
    respx.get("https://finnhub.io/api/v1/calendar/earnings").mock(return_value=httpx.Response(429))
    respx.get("https://financialmodelingprep.com/stable/earnings-calendar").mock(
        return_value=httpx.Response(
            200, json=[{"symbol": "NVDA", "date": "2026-09-30", "epsEstimated": 1.2}]
        )
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(KR_CLOSE, st, p, no_llm(), sessions, now=now)
    await p.aclose()

    d = payload["data"]
    kospi = d["indices"][0]
    assert kospi["close"] == 3050.12 and kospi["change"] == -12.3 and kospi["change_pct"] == -0.4
    rows = d["us_calendar"]["rows"]
    assert [r["event"] for r in rows] == ["JOLTS Job Openings", "NVDA 실적 발표"]
    assert rows[0]["kst"] == "09/29 23:00 KST" and rows[0]["et"] == "09/29 10:00 EDT"
    assert rows[1]["kst"] == "확정 시각 없음"
    assert d["issues"] == []  # 네이버 키 미설정 → 가짜 이슈 없음
    assert any("국내 뉴스 검색 실패" in w for w in payload["warnings"])
    assert any("FMP 시도" in w for w in payload["warnings"])


def test_api_endpoints(sessions, monkeypatch):
    from app import main
    from app.db.session import get_session

    def _override():
        with sessions() as s:
            yield s

    main.app.dependency_overrides[get_session] = _override
    monkeypatch.setattr(main.settings, "job_trigger_token", "secret")
    with sessions() as s:
        store.upsert_report(
            s,
            US_CLOSE,
            datetime(2026, 9, 29).date(),
            {"title": "t", "disclaimer": DISCLAIMER_KO},
            "ok",
        )
    c = TestClient(main.app)
    r = c.get("/report/us-close")
    assert r.status_code == 200 and r.json()["disclaimer"] == DISCLAIMER_KO
    assert c.get("/report/us-close", params={"date": "2026-09-29"}).status_code == 200
    miss = c.get("/report/us-close", params={"date": "2026-01-01"})
    assert miss.status_code == 404 and miss.json()["detail"]["disclaimer"] == DISCLAIMER_KO
    assert c.get("/report/kr-watchlist").status_code == 404
    items = c.get("/reports").json()["items"]
    assert items[0]["report_type"] == US_CLOSE
    assert c.post("/jobs/us-close/run").status_code == 401
    assert c.post("/jobs/us-close/run", headers={"X-Job-Token": "bad"}).status_code == 401
    main.app.dependency_overrides.clear()


def test_job_cli_exit_code(monkeypatch):
    from app.jobs import run as jobrun

    results = {"us-close": {"status": "failed"}, "kr-watchlist": {"status": "partial"}}
    calls: list[str] = []

    async def fake_run_job(rt, force=False, settings=None, dry_run=False):
        calls.append(rt)
        return results[rt] | {"report_type": rt}

    monkeypatch.setattr(jobrun, "run_job", fake_run_job)
    assert jobrun.main(["us-close", "kr-watchlist"]) == 1  # 실패가 있으면 1
    assert calls == ["us-close", "kr-watchlist"]  # 앞 작업이 실패해도 뒤 작업은 실행
    results["us-close"] = {"status": "ok"}
    assert jobrun.main(["us-close", "kr-watchlist"]) == 0


def test_normalize_db_url():
    from app.db.session import normalize_db_url

    assert normalize_db_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url(" sqlite:///./x.db ") == "sqlite:///./x.db"
    assert normalize_db_url("postgresql+psycopg://h/db") == "postgresql+psycopg://h/db"


def test_check_db_url_masks_password_and_flags_problems():
    from app.db.session import check_db_url

    good = (
        "postgresql://postgres.abc:Secret123@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    )
    masked, problems = check_db_url(good)
    assert problems == [] and "Secret123" not in masked and "***" in masked

    masked, problems = check_db_url(good.replace("Secret123@", "Secret123@@"))
    assert any("'@'" in p for p in problems) and "Secret123" not in masked

    _, problems = check_db_url(good.replace("Secret123", "[YOUR-PASSWORD]"))
    assert any("YOUR-PASSWORD" in p for p in problems)

    _, problems = check_db_url("postgresql://postgres:pw@db.abc.supabase.co:5432/postgres")
    assert any("Session pooler" in p for p in problems)

    assert check_db_url("sqlite:///./x.db")[1] == []
    assert check_db_url("mysql://x")[1]


@respx.mock
async def test_intraday_etf_quote_is_flagged_on_card(sessions, no_sleep):
    """미국 장중(다음 세션)에 수동 실행하면 전일 마감 값이 아님을 카드에 표시한다."""
    mock_finnhub()
    intraday = int(datetime(2026, 9, 29, 15, 27, tzinfo=UTC).timestamp())  # 9/29 11:27 EDT
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 500.0, "d": -1.0, "dp": -0.2, "t": intraday})
    )
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(402)
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(US_CLOSE, st, p, no_llm(), sessions, now=NOW)
    await p.aclose()
    d = payload["data"]
    assert d["session_date_et"] == "2026-09-28"
    assert all("⚠ 시세 기준일 2026-09-29" in i["note"] for i in d["indices"])


@respx.mock
async def test_close_quote_same_session_has_no_flag(sessions, no_sleep):
    mock_finnhub()  # 시세 시각 9/28 16:00 EDT = 기준 세션
    respx.get("https://financialmodelingprep.com/stable/quote").mock(
        return_value=httpx.Response(402)
    )
    st = settings()
    p = build_providers(st, sessions)
    payload = await generate(US_CLOSE, st, p, no_llm(), sessions, now=NOW)
    await p.aclose()
    assert all("⚠" not in (i.get("note") or "") for i in payload["data"]["indices"])
