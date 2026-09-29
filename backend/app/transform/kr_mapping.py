"""기능 B: 국장 관전 포인트 — 미국 섹터/이슈 → 한국 상장기업 관련도·수혜/악재 점수 (하이브리드).

세부 점수(부호 포함, −100~+100점: +는 수혜, −는 악재) — 세 기준을 '분리 계산' 후 가중합
  ① supply_chain  (공급망: 고객사/공급사)     가중치 0.30/0.65 ≈ 46%
  ② sensitivity   (실적 민감도: 수출·환율)    가중치 0.25/0.65 ≈ 38%
  ③ theme         (테마성 연관, 최하위)       가중치 0.10/0.65 ≈ 15%
  (동일 산업 기준은 2026-09-29 요청으로 점수에서 제외 — 정적 테이블 값은 보존)
각 기준 계산
  - 크기(관련 강도): 정적 규칙과 LLM 이 모두 있으면 0.6*정적 + 0.4*|LLM|, 정적만 있으면 정적 값,
    LLM 만 있으면 |LLM| × 0.8 (검증되지 않은 추론 할인)
  - 방향(수혜/악재): 이번 뉴스에 대한 LLM 판단의 부호. 정적 규칙에는 방향이 없으므로 LLM 을 쓸 수
    없으면 점수를 만들지 않고 '방향 미판정'으로 표시한다(추측으로 부호를 붙이지 않는다).
  - 뉴스에 특정 미국 티커가 등장하면 해당 티커의 직접 공급망 엣지(US_TICKER_EDGES)를 max 로 반영
판단 근거 1줄: 기여도가 가장 큰 근거(티커 엣지 > 정적 규칙 > LLM 추론[표기]) 를 사용.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from app.data.sector_map import (
    KR_UNIVERSE,
    MACRO_KEY,
    SECTORS,
    US_TICKER_EDGES,
    US_TICKER_SECTOR,
    Relation,
)
from app.llm.claude import ClaudeAnalyst, LLMUnavailable

log = logging.getLogger(__name__)

# 정적 테이블(Relation)의 기준 — same_industry 는 보존만 하고 점수에는 쓰지 않는다
STATIC_CRITERIA = ("same_industry", "supply_chain", "sensitivity", "theme")
CRITERIA = ("supply_chain", "sensitivity", "theme")
_RAW_W = {"supply_chain": 0.30, "sensitivity": 0.25, "theme": 0.10}
WEIGHTS = {c: w / sum(_RAW_W.values()) for c, w in _RAW_W.items()}
TIER_WEIGHT = {"a": 1.0, "b": 0.9, "c": 0.8, "d": 0.6}
STATIC_W, LLM_W, LLM_ONLY_DISCOUNT = 0.6, 0.4, 0.8
MIN_RELEVANCE = 0.2
# 종합 점수(−100~+100) → 등급
LABELS = ((30, "수혜"), (10, "약한 수혜"), (-9, "중립"), (-29, "약한 악재"))
MAX_COMPANIES_PER_SECTOR = 6


@dataclass
class _Pair:
    static: dict[str, float] = field(default_factory=lambda: dict.fromkeys(STATIC_CRITERIA, 0.0))
    has_static: bool = False
    static_basis: str = ""
    edge_basis: str = ""
    edge_strength: float = 0.0
    llm: dict[str, float] | None = None
    llm_rationale: str = ""


def _merge_static(p: _Pair, r: Relation, is_edge: bool) -> None:
    for c in STATIC_CRITERIA:
        p.static[c] = max(p.static[c], getattr(r, c))
    p.has_static = True
    if is_edge:
        strength = max(getattr(r, c) for c in STATIC_CRITERIA)
        if strength > p.edge_strength:
            p.edge_strength, p.edge_basis = strength, r.basis
    elif not p.static_basis:
        p.static_basis = r.basis


def _magnitudes(p: _Pair) -> dict[str, float]:
    """기준별 관련 강도(0~1, 방향 없음)."""
    out = {}
    for c in CRITERIA:
        if p.has_static and p.llm is not None:
            v = STATIC_W * p.static[c] + LLM_W * abs(p.llm[c])
        elif p.has_static:
            v = p.static[c]
        elif p.llm is not None:
            v = LLM_ONLY_DISCOUNT * abs(p.llm[c])
        else:
            v = 0.0
        out[c] = round(max(0.0, min(1.0, v)), 3)
    return out


def _signed_scores(p: _Pair, mags: dict[str, float]) -> dict[str, int] | None:
    """기준별 부호 점수(−100~+100). 방향(LLM)이 없으면 None."""
    if p.llm is None:
        return None
    out = {}
    for c in CRITERIA:
        d = p.llm[c]
        sign = 1 if d > 0 else -1 if d < 0 else 0
        out[c] = round(100 * sign * mags[c])
    return out


def relevance(mags: dict[str, float]) -> float:
    return round(sum(WEIGHTS[c] * mags[c] for c in CRITERIA), 3)


def total_score(scores: dict[str, int]) -> int:
    return round(sum(WEIGHTS[c] * scores[c] for c in CRITERIA))


def label_for(score: int | None) -> str:
    if score is None:
        return "방향 미판정"
    for floor, name in LABELS:
        if score >= floor:
            return name
    return "악재"


def sector_heat(us_items: list[dict]) -> dict[str, dict]:
    """미국 뉴스 → 섹터별 열기(heat)와 근거 헤드라인."""
    heat: dict[str, dict] = {}
    for it in us_items:
        w = it.get("importance", 50) / 100 * TIER_WEIGHT.get(it.get("tier", "d"), 0.6)
        keys = [s["key"] if isinstance(s, dict) else s for s in it.get("sectors", [])]
        for t in it.get("tickers", []):
            sec = US_TICKER_SECTOR.get(t)
            if sec and sec not in keys:
                keys.append(sec)
        for k in keys:
            h = heat.setdefault(k, {"heat": 0.0, "news": [], "tickers": set()})
            h["heat"] += w
            h["news"].append({"rank": it.get("rank"), "title": it.get("title_ko") or it["title"]})
            h["tickers"].update(t for t in it.get("tickers", []) if US_TICKER_SECTOR.get(t) == k)
    return heat


async def map_to_korea(us_items: list[dict], analyst: ClaudeAnalyst) -> dict:
    warnings: list[str] = []
    heat = sector_heat(us_items)
    active = [k for k in heat if k in SECTORS]

    pairs: dict[tuple[str, str], _Pair] = defaultdict(_Pair)
    for k in active:
        for r in SECTORS[k].relations:
            _merge_static(pairs[(k, r.code)], r, is_edge=False)
        for t in heat[k]["tickers"]:
            for r in US_TICKER_EDGES.get(t, ()):
                _merge_static(pairs[(k, r.code)], r, is_edge=True)

    method = "rules"
    if active:
        briefs = [
            {
                "sector_key": k,
                "sector": SECTORS[k].label_ko,
                "headlines": [n["title"] for n in heat[k]["news"][:5]],
            }
            for k in active
        ]
        universe = [{"code": c.code, "name": c.name} for c in KR_UNIVERSE.values()]
        try:
            rels = await analyst.infer_kr_relations(briefs, universe)
            for r in rels:
                key = (r.get("sector_key"), r.get("code"))
                if key[0] not in active or key[1] not in KR_UNIVERSE:
                    continue  # enum 밖의 값은 폐기 (존재하지 않는 종목 차단)
                p = pairs[key]
                p.llm = {c: max(-1.0, min(1.0, float(r.get(c, 0) or 0))) for c in CRITERIA}
                p.llm_rationale = (r.get("rationale") or "").strip()[:120]
            method = "hybrid"
        except LLMUnavailable as e:
            warnings.append(f"LLM 추론 불가 → 정적 매핑 규칙만 사용 ({e})")

    sectors_out = []
    for k in sorted(active, key=lambda x: -heat[x]["heat"]):
        comps = []
        for (sk, code), p in pairs.items():
            if sk != k:
                continue
            mags = _magnitudes(p)
            rel = relevance(mags)
            if rel < MIN_RELEVANCE:
                continue
            scores = _signed_scores(p, mags)
            score = total_score(scores) if scores is not None else None
            if p.edge_basis:
                why, origin = p.edge_basis, "rule"
            elif p.static_basis:
                why, origin = p.static_basis, "rule"
            else:
                why, origin = p.llm_rationale or "관련 근거 불충분", "llm"
            c = KR_UNIVERSE[code]
            comps.append(
                {
                    "code": code,
                    "name": c.name,
                    "market": c.market,
                    "relevance": rel,
                    "score": score,  # −100~+100 (+ 수혜 / − 악재), 방향 미판정이면 None
                    "label": label_for(score),
                    "scores": scores,  # 기준별 부호 점수, 방향 미판정이면 None
                    "magnitudes": mags,  # 기준별 관련 강도 0~1
                    "rationale": why,
                    "rationale_origin": origin,  # rule=정적 규칙 / llm=AI 추론
                    "llm_rationale": p.llm_rationale or None,
                }
            )
        # 영향이 큰 순(|점수|). 방향 미판정 종목은 뒤에 관련 강도 순
        comps.sort(
            key=lambda x: (
                x["score"] is None,
                -abs(x["score"] or 0),
                -x["relevance"],
                x["code"],
            )
        )
        sec = SECTORS[k]
        n_news = len(heat[k]["news"])
        sectors_out.append(
            {
                "key": k,
                "us_label": sec.label_ko,
                "kr_sector": sec.kr_sector_ko,
                "heat": round(heat[k]["heat"], 3),
                "us_tickers": sorted(heat[k]["tickers"]),
                "news_refs": heat[k]["news"][:5],
                "watch_point": (
                    f"미국 {sec.label_ko} 관련 이슈 {n_news}건 → 국내 {sec.kr_sector_ko} 섹터 주목"
                ),
                "companies": comps[:MAX_COMPANIES_PER_SECTOR],
            }
        )

    macro = heat.get(MACRO_KEY)
    return {
        "method": method,
        "weights": WEIGHTS,
        "macro_points": macro["news"][:5] if macro else [],
        "sectors": sectors_out,
        "warnings": warnings,
    }
