"""기능 A: 전일 미국 증시 마감 리포트 — 뉴스 10건 선정(가공 계층).

■ 10건 선정 기준 (우선순위 높은 순) ─────────────────────────────────────
  (a) 시장 전체 방향에 영향을 주는 뉴스 — 금리·연준(FOMC)·물가(CPI/PCE)·고용·관세 등 매크로
  (b) 시가총액 상위 기업의 실적 발표 / 가이던스 변경
  (c) 특정 섹터 전반에 영향을 주는 뉴스
  (d) 그 외 개별 기업·개별 이슈
  동일 tier 안에서는 importance(0~100) 내림차순 → 발행 시각 최신순.
─────────────────────────────────────────────────────────────────────────
■ 원문 링크 규칙
  - url 은 뉴스 API 응답의 값만 사용(LLM 이 생성/수정 불가). 유효하지 않으면 None 으로 두고
    화면에 "원문 링크 없음" 표시. 링크가 없어도 항목을 제외하지 않고 순위를 유지한다.
■ 개수 규칙
  - 정확히 10건을 목표로 하되, 실제 확인된 뉴스가 부족하면 조회 구간을 넓혀 재시도하고
    그래도 부족하면 가짜 항목을 만들지 않고 부족 사실을 warnings 에 기록한다.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.data.sector_map import (
    EARNINGS_KEYWORDS,
    MACRO_KEY,
    MACRO_KEYWORDS,
    SECTORS,
    US_TICKER_SECTOR,
)
from app.llm.claude import ClaudeAnalyst, LLMUnavailable
from app.schemas import NewsItem
from app.transform.text import first_sentence, has_keyword, norm_headline

log = logging.getLogger(__name__)

TARGET_COUNT = 10
TIER_ORDER = {"a": 0, "b": 1, "c": 2, "d": 3}
TIER_LABEL = {
    "a": "시장 전체(매크로)",
    "b": "대형주 실적/가이던스",
    "c": "섹터 영향",
    "d": "개별 이슈",
}
SECTOR_KEYS = [*SECTORS.keys(), MACRO_KEY]


def dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out = []
    for n in sorted(items, key=lambda x: x.published_at, reverse=True):
        k = norm_headline(n.headline)[:120]
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def in_window(items: list[NewsItem], start: datetime, end: datetime) -> list[NewsItem]:
    return [n for n in items if start <= n.published_at <= end]


def detect_sectors(n: NewsItem) -> list[str]:
    text = f"{n.headline} {n.summary}"
    found = [k for k, s in SECTORS.items() if has_keyword(text, s.keywords)]
    for t in n.related_tickers:
        sec = US_TICKER_SECTOR.get(t)
        if sec and sec not in found:
            found.append(sec)
    return found


def rule_classify(n: NewsItem, megacaps: set[str]) -> dict:
    """규칙기반 분류 (LLM 불가 시 fallback, LLM 결과 검증 시 보조)."""
    text = f"{n.headline} {n.summary}"
    sectors = detect_sectors(n)
    macro_hits = has_keyword(text, MACRO_KEYWORDS)
    earn_hits = has_keyword(text, EARNINGS_KEYWORDS)
    mega = [t for t in n.related_tickers if t in megacaps] or [
        t for t in megacaps if has_keyword(n.headline, [t.lower()])
    ]
    if len(macro_hits) >= 1 and not mega:
        tier, imp = "a", 60 + 5 * min(len(macro_hits), 6)
        sectors = [MACRO_KEY, *sectors]
    elif earn_hits and mega:
        tier, imp = "b", 55 + 5 * min(len(earn_hits), 5)
    elif sectors:
        tier, imp = "c", 45 + 3 * min(len(sectors), 5)
    else:
        tier, imp = "d", 30
    return {
        "tier": tier,
        "importance": imp,
        "sectors": sectors or [],
        "tickers": sorted(set(n.related_tickers + mega)),
        "title_ko": None,
        "summary_ko": None,
    }


def _valid_tickers(n: NewsItem, tickers: list[str]) -> list[str]:
    """LLM 이 준 티커 중 원문(제목·요약·related)에 실제 등장하는 것만 채택."""
    text = f"{n.headline} {n.summary}".upper()
    ok = []
    for t in tickers:
        t = t.strip().upper()
        if t and (t in n.related_tickers or f" {t} " in f" {text} " or f"({t})" in text):
            ok.append(t)
    return sorted(set(ok))


async def rank_news(
    items: list[NewsItem], analyst: ClaudeAnalyst, megacaps: set[str], max_candidates: int = 60
) -> tuple[list[dict], str, list[str]]:
    """반환: (선정 항목 리스트, 방식 'llm'|'rules', warnings)."""
    warnings: list[str] = []
    cands = items[:max_candidates]
    rules = {n.id: rule_classify(n, megacaps) for n in cands}
    by_id = {n.id: n for n in cands}
    method = "rules"
    merged: dict[str, dict] = dict(rules)

    if cands:
        try:
            payload = [
                {
                    "id": n.id,
                    "headline": n.headline,
                    "summary": n.summary[:500],
                    "related": n.related_tickers,
                    "source": n.source,
                }
                for n in cands
            ]
            llm_items = await analyst.rank_us_news(payload, SECTOR_KEYS)
            for r in llm_items:
                n = by_id.get(r.get("id", ""))
                if n is None or r.get("tier") not in TIER_ORDER:
                    continue
                merged[n.id] = {
                    "tier": r["tier"],
                    "importance": max(0, min(100, int(r.get("importance", 0)))),
                    "sectors": [s for s in r.get("sectors", []) if s in SECTOR_KEYS],
                    "tickers": _valid_tickers(n, r.get("tickers", [])),
                    "title_ko": (r.get("title_ko") or "").strip() or None,
                    "summary_ko": (r.get("summary_ko") or "").strip() or None,
                }
            method = "llm"
        except LLMUnavailable as e:
            warnings.append(f"LLM 분류 불가 → 규칙기반 분류로 대체 ({e})")

    ranked = sorted(
        cands,
        key=lambda n: (
            TIER_ORDER[merged[n.id]["tier"]],
            -merged[n.id]["importance"],
            -n.published_at.timestamp(),
        ),
    )[:TARGET_COUNT]

    out = []
    for rank, n in enumerate(ranked, start=1):
        m = merged[n.id]
        summary = m["summary_ko"] or first_sentence(n.summary) or "(요약 없음 — 원문 확인)"
        out.append(
            {
                "rank": rank,
                "id": n.id,
                "title": n.headline,  # 원문 제목(API 값 그대로)
                "title_ko": m["title_ko"],  # LLM 번역(있을 때만)
                "summary": summary,
                "summary_origin": "llm" if m["summary_ko"] else "api",
                "tier": m["tier"],
                "tier_label": TIER_LABEL[m["tier"]],
                "importance": m["importance"],
                "sectors": [
                    {"key": s, "label": SECTORS[s].label_ko if s in SECTORS else "시장 전반"}
                    for s in m["sectors"]
                ],
                "tickers": m["tickers"],
                "url": n.url,  # None → "원문 링크 없음"
                "source": n.source,
                "provider": n.provider,
                "published_at_utc": n.published_at.isoformat(),
            }
        )
    if len(out) < TARGET_COUNT:
        warnings.append(
            f"확인된 뉴스가 {len(out)}건뿐이어서 {TARGET_COUNT}건을 채우지 못했습니다 "
            "(가짜 항목은 생성하지 않음)."
        )
    return out, method, warnings
