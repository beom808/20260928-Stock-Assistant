"""리포트 조립(오케스트레이션): fetch → transform → store.

각 섹션은 독립적으로 실패할 수 있으며, 실패 시 리포트 전체를 버리지 않고 해당 섹션에 오류를
기록한 뒤 status=partial 로 저장한다. 모든 리포트에는 출처·생성시각(KST)·면책문구가 포함된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import store
from app.disclaimer import DISCLAIMER_KO
from app.fetch.http import ApiError
from app.fetch.providers import Providers
from app.llm.claude import ClaudeAnalyst, LLMUnavailable
from app.schemas import EarningsEvent, IndexQuote, NewsItem
from app.timeutil import (
    US_CLOSE_ET,
    et_wall_to_utc,
    fmt_kst,
    is_us_trading_day,
    kst_today,
    last_completed_us_session,
    now_utc,
    to_et,
    to_kst,
    us_close_kst,
)
from app.transform.calendar import build_calendar
from app.transform.kr_mapping import map_to_korea
from app.transform.text import first_sentence, norm_headline
from app.transform.us_close import TARGET_COUNT, dedupe, in_window, rank_news

log = logging.getLogger(__name__)

US_CLOSE = "us-close"
KR_WATCHLIST = "kr-watchlist"
KR_CLOSE = "kr-close-and-calendar"
REPORT_TYPES = (US_CLOSE, KR_WATCHLIST, KR_CLOSE)

US_INDICES = [
    # (표시명, FMP 지수 심볼, 대체 ETF, ETF 비고)
    ("S&P 500", "^GSPC", "SPY", None),
    ("나스닥 종합", "^IXIC", "QQQ", "QQQ는 나스닥100 추종 — 나스닥 종합지수와 구성이 다름"),
    ("다우존스", "^DJI", "DIA", None),
]


@dataclass
class Ctx:
    settings: Settings
    providers: Providers
    analyst: ClaudeAnalyst
    sessions: sessionmaker[Session]
    now: datetime = field(default_factory=now_utc)
    sources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def src(
        self, name: str, used_for: str, fetched_at: datetime | None = None, stale=False
    ) -> None:
        entry = {
            "name": name,
            "used_for": used_for,
            "fetched_at_kst": fmt_kst(fetched_at) if fetched_at else None,
            "stale_cache": stale,
        }
        if entry not in self.sources:
            self.sources.append(entry)


def envelope(ctx: Ctx, report_type: str, title: str, report_date: date, data: dict) -> dict:
    status = "failed" if data.get("_fatal") else ("partial" if ctx.errors else "ok")
    data.pop("_fatal", None)
    return {
        "report_type": report_type,
        "title": title,
        "report_date_kst": report_date.isoformat(),
        "generated_at_kst": fmt_kst(ctx.now),
        "generated_at_utc": ctx.now.isoformat(),
        "disclaimer": DISCLAIMER_KO,
        "status": status,
        "sources": ctx.sources,
        "warnings": ctx.warnings,
        "errors": ctx.errors,
        "data": data,
    }


def _quote_dict(q: IndexQuote) -> dict:
    return q.model_dump(mode="json") | {
        "as_of_kst": fmt_kst(q.as_of) if q.as_of else None,
    }


# ── 기능 A ────────────────────────────────────────────────────────────────
async def _us_indices(ctx: Ctx, session: date) -> list[dict]:
    out = []
    for name, sym, etf, etf_note in US_INDICES:
        q: IndexQuote | None = None
        try:
            q = await ctx.providers.fmp.index_quote(name, sym)
            ctx.src("Financial Modeling Prep", "미국 지수 시세", q.as_of)
        except ApiError as e:
            ctx.warnings.append(f"{name} 지수 시세 실패({e.kind}) → ETF 프록시 시도")
            try:
                q = await ctx.providers.finnhub.etf_proxy_quote(name, etf)
                if etf_note:
                    q.note = f"{q.note} / {etf_note}"
                ctx.src("Finnhub", "미국 지수 대체(ETF) 시세", q.as_of)
            except ApiError as e2:
                ctx.errors.append(f"{name} 시세 수집 실패: {e2}")
        if q is None:
            out.append({"name": name, "symbol": sym, "error": "시세 없음"})
            continue
        if q.as_of and to_et(q.as_of).date() != session:
            ctx.warnings.append(
                f"{name} 시세 기준일({to_et(q.as_of).date()})이 직전 세션({session})과 다름 — "
                "데이터 지연 또는 휴장 여부 확인 필요"
            )
        out.append(_quote_dict(q))
    return out


async def _us_news(ctx: Ctx, session: date) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        general, res = await ctx.providers.finnhub.market_news()
        items += general
        ctx.src("Finnhub /news", "미국 시장 뉴스", res.fetched_at, res.stale)
    except ApiError as e:
        ctx.errors.append(f"시장 뉴스 수집 실패: {e}")
    # (b) 대형주 실적/가이던스 누락 방지를 위해 상위 종목의 기업 뉴스도 후보에 포함
    d_from = session - timedelta(days=1)
    for sym in ctx.settings.watchlist[:12]:
        try:
            items += await ctx.providers.finnhub.company_news(sym, d_from, kst_today(ctx.now))
        except ApiError as e:
            ctx.warnings.append(f"{sym} 기업 뉴스 수집 실패: {e.kind}")
            if e.kind in ("config", "quota"):
                break
    if any(n.provider == "Finnhub" for n in items):
        ctx.src("Finnhub /company-news", "미국 대형주 기업 뉴스")
    return dedupe(items)


def _prev_us_session(d: date) -> date:
    p = d - timedelta(days=1)
    while not is_us_trading_day(p):
        p -= timedelta(days=1)
    return p


async def build_us_close(ctx: Ctx) -> dict:
    session = last_completed_us_session(ctx.now)
    indices = await _us_indices(ctx, session)
    all_news = await _us_news(ctx, session)

    # 조회 구간: 직전 세션 전일 마감(16:00 ET) ~ 리포트 생성 시각.
    start = et_wall_to_utc(_prev_us_session(session), US_CLOSE_ET)
    window = in_window(all_news, start, ctx.now)
    widen = 0
    while len(window) < TARGET_COUNT and widen < 2:
        widen += 1
        start -= timedelta(hours=24)
        window = in_window(all_news, start, ctx.now)
    if widen:
        ctx.warnings.append(f"뉴스가 부족해 조회 구간을 {widen * 24}시간 확장했습니다.")

    megacaps = set(ctx.settings.watchlist)
    ranked, method, w = await rank_news(window, ctx.analyst, megacaps)
    ctx.warnings.extend(w)
    if method == "llm":
        ctx.src(f"Anthropic Claude ({ctx.analyst.model})", "뉴스 분류·한국어 요약(원문 기반)")

    data = {
        "session_date_et": session.isoformat(),
        "session_close_kst": fmt_kst(us_close_kst(session)),
        "session_close_tz": to_et(et_wall_to_utc(session, US_CLOSE_ET)).tzname(),
        "indices": indices,
        "news": ranked,
        "news_window_kst": f"{fmt_kst(start)} ~ {fmt_kst(ctx.now)}",
        "ranking_method": method,
        "selection_criteria": [
            "(a) 시장 전체 방향(금리·매크로)",
            "(b) 시가총액 상위 기업 실적/가이던스",
            "(c) 특정 섹터 전반 영향",
            "(d) 개별 이슈",
        ],
    }
    if not ranked and all("error" in i for i in indices):
        data["_fatal"] = True
    return envelope(ctx, US_CLOSE, "전일 미국 증시 마감 리포트", kst_today(ctx.now), data)


# ── 기능 B ────────────────────────────────────────────────────────────────
async def build_kr_watchlist(ctx: Ctx, us_report: dict) -> dict:
    us_items = us_report.get("data", {}).get("news", [])
    mapping = await map_to_korea(us_items, ctx.analyst)
    ctx.warnings.extend(mapping.pop("warnings"))
    ctx.src("정적 섹터-종목 매핑 테이블(내부)", "관련도 규칙 점수")
    if mapping["method"] == "hybrid":
        ctx.src(f"Anthropic Claude ({ctx.analyst.model})", "관련도 추론(후보 종목 내에서만)")
    ctx.src(f"전일 미국 마감 리포트({us_report.get('generated_at_kst')})", "입력 이슈(기능 A 결과)")
    data = {
        "notice": (
            "정규장(09:00) 개장 전 사전 브리핑입니다. KRX 프리마켓은 미시행이므로 이 시각의 "
            "국내 실거래 데이터는 포함되지 않습니다."
        ),
        "us_session_date_et": us_report.get("data", {}).get("session_date_et"),
        **mapping,
    }
    if not us_items:
        ctx.errors.append("입력으로 쓸 미국 뉴스가 없어 관전 포인트를 만들 수 없습니다.")
    return envelope(ctx, KR_WATCHLIST, "한국장 관전 포인트", kst_today(ctx.now), data)


# ── 기능 C ────────────────────────────────────────────────────────────────
KR_NEWS_QUERIES = ("코스피 마감", "코스닥 마감", "증시 특징주")
KR_ISSUE_COUNT = 5


async def _kr_issues(ctx: Ctx) -> tuple[list[dict], str]:
    items: list[NewsItem] = []
    for q in KR_NEWS_QUERIES:
        try:
            items += await ctx.providers.naver.search(q)
        except ApiError as e:
            ctx.warnings.append(f"국내 뉴스 검색 실패('{q}'): {e.kind}")
            if e.kind in ("config", "quota"):
                break
    today = kst_today(ctx.now)
    items = [n for n in dedupe(items) if to_kst(n.published_at).date() == today]
    if not items:
        return [], "none"
    ctx.src("네이버 검색 API(뉴스)", "국내 당일 이슈")
    by_id = {n.id: n for n in items}
    picked: list[tuple[NewsItem, str, str]] = []
    method = "rules"
    try:
        cands = [{"id": n.id, "title": n.headline, "desc": n.summary[:300]} for n in items[:40]]
        for r in await ctx.analyst.pick_kr_issues(cands, KR_ISSUE_COUNT):
            n = by_id.get(r.get("id", ""))
            if n and all(n.id != p[0].id for p in picked):
                picked.append((n, (r.get("summary_ko") or "").strip(), "llm"))
        method = "llm"
    except LLMUnavailable as e:
        ctx.warnings.append(f"LLM 이슈 선정 불가 → 최신순 선정 ({e})")
    if not picked:
        seen: set[str] = set()
        for n in items:
            k = norm_headline(n.headline)[:30]
            if k in seen:
                continue
            seen.add(k)
            picked.append((n, first_sentence(n.summary), "api"))
            if len(picked) >= KR_ISSUE_COUNT:
                break
    out = [
        {
            "rank": i,
            "title": n.headline,
            "summary": s or first_sentence(n.summary) or "(요약 없음 — 원문 확인)",
            "summary_origin": origin if s else "api",
            "url": n.url,
            "source": n.source,
            "published_at_kst": fmt_kst(n.published_at),
        }
        for i, (n, s, origin) in enumerate(picked, start=1)
    ]
    return out, method


async def _kr_indices(ctx: Ctx) -> list[dict]:
    """국내 지수: 키움 REST(설정 시) → 한국투자증권 KIS(설정 시) 순서로 시도."""
    kiwoom, kis = ctx.providers.kiwoom, ctx.providers.kis
    out = []
    kospi_close: float | None = None
    for name in ("KOSPI", "KOSDAQ"):
        q: IndexQuote | None = None
        errs: list[str] = []
        if kiwoom.configured:
            try:
                q = await kiwoom.index_quote(
                    name, exclude_close=kospi_close if name == "KOSDAQ" else None
                )
                q.as_of = q.as_of or ctx.now
                ctx.src("키움증권 REST API", "국내 지수", q.as_of)
            except ApiError as e:
                errs.append(str(e))
        if q is None:
            try:
                q = await kis.index_quote(name)
                ctx.src("한국투자증권 KIS Open API", "국내 지수", q.as_of)
            except ApiError as e:
                if (
                    e.kind != "config"
                ):  # KIS 미설정은 키움 오류가 있으면 그것을, 없으면 아래 안내를 보여줌
                    errs.append(str(e))
        if q is None:
            msg = (
                "; ".join(errs)
                or "국내 지수 API 키 미설정 (KIWOOM_APP_KEY/SECRET 또는 KIS_APP_KEY/SECRET)"
            )
            ctx.errors.append(f"{name} 지수 수집 실패: {msg}")
            out.append({"name": name, "error": "시세 없음"})
            continue
        if name == "KOSPI":
            kospi_close = q.close
        out.append(_quote_dict(q))
    return out


async def _us_calendar(ctx: Ctx) -> dict:
    et_today = to_et(ctx.now).date()
    d_to = et_today + timedelta(days=3)
    econ = []
    try:
        econ = await ctx.providers.fmp.economic_calendar(et_today, d_to)
        ctx.src("Financial Modeling Prep economic-calendar", "미국 경제지표·FOMC 일정")
    except ApiError as e:
        ctx.errors.append(f"경제캘린더 수집 실패: {e}")
    earnings: list[EarningsEvent] = []
    try:
        earnings = await ctx.providers.finnhub.earnings_calendar(et_today, d_to)
        ctx.src("Finnhub /calendar/earnings", "미국 실적발표 일정(BMO/AMC)")
    except ApiError as e:
        ctx.warnings.append(f"Finnhub 실적캘린더 실패({e.kind}) → FMP 시도")
        try:
            earnings = await ctx.providers.fmp.earnings_calendar(et_today, d_to)
            ctx.src("Financial Modeling Prep earnings-calendar", "미국 실적발표 일정")
        except ApiError as e2:
            ctx.errors.append(f"실적캘린더 수집 실패: {e2}")
    cal = build_calendar(econ, earnings, ctx.now, set(ctx.settings.watchlist))
    ctx.warnings.extend(cal.pop("warnings"))
    return cal


async def build_kr_close(ctx: Ctx) -> dict:
    indices = await _kr_indices(ctx)
    issues, issue_method = await _kr_issues(ctx)
    if issue_method == "llm":
        ctx.src(f"Anthropic Claude ({ctx.analyst.model})", "국내 이슈 선정·요약(원문 기반)")
    calendar = await _us_calendar(ctx)
    data = {
        "indices": indices,
        "issues": issues,
        "issue_method": issue_method,
        "us_calendar": calendar,
        "calendar_columns": ["이벤트명", "종류", "미국시각(ET)", "한국시각(KST)", "컨센서스"],
    }
    return envelope(
        ctx, KR_CLOSE, "국내 장 마감 리포트 + 익일 미국 캘린더", kst_today(ctx.now), data
    )


# ── 실행 진입점 ───────────────────────────────────────────────────────────
async def generate(
    report_type: str,
    settings: Settings,
    providers: Providers,
    analyst: ClaudeAnalyst,
    sessions: sessionmaker[Session],
    now: datetime | None = None,
) -> dict:
    ctx = Ctx(settings, providers, analyst, sessions, now=now or now_utc())
    if report_type == US_CLOSE:
        payload = await build_us_close(ctx)
    elif report_type == KR_WATCHLIST:
        with sessions() as s:
            row = store.get_report(s, US_CLOSE, kst_today(ctx.now))
        if row is None:
            sub = Ctx(settings, providers, analyst, sessions, now=ctx.now)
            us = await build_us_close(sub)
            with sessions() as s:
                store.upsert_report(s, US_CLOSE, kst_today(ctx.now), us, us["status"])
        else:
            us = row.payload
        payload = await build_kr_watchlist(ctx, us)
    elif report_type == KR_CLOSE:
        payload = await build_kr_close(ctx)
    else:
        raise ValueError(f"unknown report type: {report_type}")
    with sessions() as s:
        store.upsert_report(s, report_type, kst_today(ctx.now), payload, payload["status"])
    return payload
