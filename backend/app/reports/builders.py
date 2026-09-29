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
from app.transform.calendar import build_calendar, calendar_end
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
            try:  # 공식 종가(일별 EOD) 우선 → 없으면 실시간 시세
                q = await ctx.providers.fmp.index_eod(name, sym, session)
                ctx.src("Financial Modeling Prep (일별 종가)", "미국 지수 종가", q.as_of)
            except ApiError as e0:
                if e0.kind in ("config", "quota"):
                    raise
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
            quote_day = to_et(q.as_of).date()
            ctx.warnings.append(
                f"{name} 시세 기준일({quote_day})이 직전 세션({session})과 다름 — "
                "데이터 지연 또는 휴장 여부 확인 필요"
            )
            # 카드에도 표시: 전일 마감 값이 아닐 수 있음을 숨기지 않는다
            mismatch = (
                f"⚠ 시세 기준일 {quote_day}(ET) ≠ 기준 세션 {session} — 마감 값이 아닐 수 있음"
            )
            q.note = f"{q.note} / {mismatch}" if q.note else mismatch
        out.append(_quote_dict(q))
    return out


async def _fx(ctx: Ctx) -> dict | None:
    """USD/KRW — ECB 기준환율(무료). 서울 외환시장 종가가 아니므로 고시일과 함께 표시."""
    try:
        fx = await ctx.providers.macro.usdkrw_ecb(kst_today(ctx.now))
    except ApiError as e:
        ctx.warnings.append(f"USD/KRW 환율 수집 실패({e.kind})")
        return None
    ctx.src("ECB 기준환율 (Frankfurter)", "USD/KRW 환율")
    return fx


async def _macro(ctx: Ctx, session: date) -> list[dict]:
    """매크로 카드: VIX(FMP 일별 종가) + 미 10년물·달러지수(FRED, 1영업일 이상 지연)."""
    out: list[dict] = []
    try:
        try:
            q = await ctx.providers.fmp.index_eod("VIX", "^VIX", session)
        except ApiError as e0:
            if e0.kind in ("config", "quota"):
                raise
            q = await ctx.providers.fmp.index_quote("VIX", "^VIX")
        out.append(
            {
                "name": "VIX 변동성지수",
                "value": q.close,
                "unit": "",
                "change": q.change,
                "date": to_et(q.as_of).date().isoformat() if q.as_of else None,
                "provider": q.provider,
                "note": None,
            }
        )
        ctx.src(q.provider, "VIX", q.as_of)
    except ApiError as e:
        ctx.warnings.append(f"VIX 수집 실패({e.kind})")
    try:
        out += await ctx.providers.macro.fred_macro()
        ctx.src("FRED (DGS10·DTWEXBGS)", "미국 10년물 금리·달러지수")
    except ApiError as e:
        if e.kind != "config":
            ctx.warnings.append(f"FRED 매크로 지표 수집 실패({e.kind})")
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
    fx = await _fx(ctx)
    macro = await _macro(ctx, session)
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
        "fx": fx,
        "macro": macro,
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
        "us_session_date_et": us_report.get("data", {}).get("session_date_et"),
        **mapping,
    }
    if not us_items:
        ctx.errors.append("입력으로 쓸 미국 뉴스가 없어 관전 포인트를 만들 수 없습니다.")
    return envelope(ctx, KR_WATCHLIST, "국장 관전 포인트", kst_today(ctx.now), data)


# ── 기능 C ────────────────────────────────────────────────────────────────
KR_NEWS_QUERIES = ("코스피 마감", "코스닥 마감", "증시 특징주", "코스피 외국인 기관")
KR_ISSUE_COUNT = 10  # 화면: 홈 5건, 전체 보기 10건


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
        cands = [{"id": n.id, "title": n.headline, "desc": n.summary[:300]} for n in items[:60]]
        for r in await ctx.analyst.pick_kr_issues(cands, KR_ISSUE_COUNT):
            n = by_id.get(r.get("id", ""))
            if n and all(n.id != p[0].id for p in picked):
                picked.append((n, (r.get("summary_ko") or "").strip(), "llm"))
            if len(picked) >= KR_ISSUE_COUNT:  # 여유 있게 받은 뒤 상위 KR_ISSUE_COUNT 건만
                break
        method = "llm"
    except LLMUnavailable as e:
        ctx.warnings.append(f"LLM 이슈 선정 불가 → 최신순 선정 ({e})")
    # LLM 이 덜 골랐거나(비슷한 주제를 합치는 경우 등) 쓸 수 없으면 최신순으로 채운다
    seen = {norm_headline(p[0].headline)[:30] for p in picked}
    for n in items:
        if len(picked) >= KR_ISSUE_COUNT:
            break
        k = norm_headline(n.headline)[:30]
        if k in seen:
            continue
        seen.add(k)
        picked.append((n, first_sentence(n.summary), "api"))
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


async def _kr_flows(ctx: Ctx) -> list[dict]:
    """코스피·코스닥 투자자별 순매수(키움 ka10051, KRX, 억원). 장 마감 직후 값은 잠정치."""
    kiwoom = ctx.providers.kiwoom
    if not kiwoom.configured:
        return []
    out = []
    for name in ("KOSPI", "KOSDAQ"):
        try:
            flows = await kiwoom.investor_flows(name, kst_today(ctx.now))
        except ApiError as e:
            ctx.warnings.append(f"{name} 투자자별 순매수 수집 실패: {e}")
            continue
        out.append({"market": name, "unit": "억원", **flows})
    if out:
        ctx.src("키움증권 REST API (ka10051)", "투자자별 순매수(KRX, 잠정)", ctx.now)
    return out


async def _us_calendar(ctx: Ctx) -> dict:
    et_today = to_et(ctx.now).date()
    # 금요일(또는 연휴 전) 오후 리포트는 다음 미국 거래일 일정까지 포함
    d_to = to_et(calendar_end(ctx.now)).date()
    # 경제지표·FOMC: BEA·연준 공식 일정(무료) + FRED(키 설정 시, BLS 지표 발표일·관례 시각)
    official = ctx.providers.official
    econ, failed = await official.economic_calendar(et_today, d_to)
    if sum(f.startswith(("BEA", "연준")) for f in failed) < 2:
        ctx.src("BEA·연준 공식 발표 일정", "미국 경제지표·FOMC 일정")
    if official.fred_api_key and not any(f.startswith("FRED") for f in failed):
        ctx.src("FRED 발표일 (BLS 등, 시각은 관례)", "CPI·고용·PPI 등 발표일")
        fred = sorted(f"{e.name} {e.date_et}" for e in econ if e.provider.startswith("FRED"))
        log.info("FRED 발표일(%s~%s ET) 채택: %s", et_today, d_to, fred)
        log.info("FRED 기간 내 기타 발표(표 제외): %s", official.fred_other_releases)
    elif not official.fred_api_key:
        ctx.src("CPI·고용·PPI(BLS) 일정 미포함 — FRED_API_KEY 미설정", "안내")
    if ctx.settings.fmp_econ_calendar:
        try:
            econ += await ctx.providers.fmp.economic_calendar(et_today, d_to)
            ctx.src("Financial Modeling Prep economic-calendar", "미국 경제지표 일정")
        except ApiError as e:
            failed.append(f"FMP 경제캘린더 수집 실패: {e}")
    # 추세 판단용: 지표마다 최근 4회 발표 수치(FRED)를 '이전' 칸에 붙인다
    hist_cache: dict[str, dict | None] = {}
    for ev in econ:
        if ev.previous:
            continue
        if ev.name not in hist_cache:
            try:
                hist_cache[ev.name] = await official.history(ev.name)
            except ApiError as e:
                hist_cache[ev.name] = None
                ctx.warnings.append(f"{ev.name} 과거 수치 조회 실패({e.kind})")
        h = hist_cache[ev.name]
        if h:
            ev.previous, ev.history = h["text"], h
    attempted = 2 + bool(official.fred_api_key) + bool(ctx.settings.fmp_econ_calendar)
    if len(failed) >= attempted:  # 모든 출처가 실패했을 때만 오류(일정이 없는 날은 정상)
        ctx.errors.append("경제캘린더 수집 실패: " + " / ".join(failed))
    else:
        ctx.warnings.extend(failed)
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
    watch = set(ctx.settings.watchlist)
    # 진단용: 받은 실적 일정 수와 관심 종목 매칭 결과(표가 비었을 때 원인 확인)
    log.info(
        "실적캘린더 %d건 수신(%s~%s ET), 관심 종목: %s",
        len(earnings),
        et_today,
        d_to,
        sorted(f"{e.symbol} {e.date_et} {e.hour or '-'}" for e in earnings if e.symbol in watch),
    )
    cal = build_calendar(econ, earnings, ctx.now, watch)
    ctx.warnings.extend(cal.pop("warnings"))
    return cal


async def build_kr_close(ctx: Ctx) -> dict:
    indices = await _kr_indices(ctx)
    fx = await _fx(ctx)
    flows = await _kr_flows(ctx)
    issues, issue_method = await _kr_issues(ctx)
    if issue_method == "llm":
        ctx.src(f"Anthropic Claude ({ctx.analyst.model})", "국내 이슈 선정·요약(원문 기반)")
    calendar = await _us_calendar(ctx)
    data = {
        "indices": indices,
        "fx": fx,
        "investor_flows": flows,
        "issues": issues,
        "issue_method": issue_method,
        "us_calendar": calendar,
        "calendar_columns": ["이벤트명", "종류", "미국시각(ET)", "한국시각(KST)", "최근 4회"],
    }
    return envelope(ctx, KR_CLOSE, "국장 마감 리포트 + 익일 미국 캘린더", kst_today(ctx.now), data)


# ── 실행 진입점 ───────────────────────────────────────────────────────────
async def generate(
    report_type: str,
    settings: Settings,
    providers: Providers,
    analyst: ClaudeAnalyst,
    sessions: sessionmaker[Session],
    now: datetime | None = None,
    save: bool = True,
) -> dict:
    """save=False 면 리포트를 DB 에 저장하지 않는다(테스트 실행 — 화면에 보이는 리포트는 그대로)."""
    ctx = Ctx(settings, providers, analyst, sessions, now=now or now_utc())
    if report_type == US_CLOSE:
        payload = await build_us_close(ctx)
    elif report_type == KR_WATCHLIST:
        with sessions() as s:
            row = store.get_report(s, US_CLOSE, kst_today(ctx.now))
        if row is None:
            sub = Ctx(settings, providers, analyst, sessions, now=ctx.now)
            us = await build_us_close(sub)
            if save:
                with sessions() as s:
                    store.upsert_report(s, US_CLOSE, kst_today(ctx.now), us, us["status"])
        else:
            us = row.payload
        payload = await build_kr_watchlist(ctx, us)
    elif report_type == KR_CLOSE:
        payload = await build_kr_close(ctx)
    else:
        raise ValueError(f"unknown report type: {report_type}")
    if save:
        with sessions() as s:
            store.upsert_report(s, report_type, kst_today(ctx.now), payload, payload["status"])
    return payload
