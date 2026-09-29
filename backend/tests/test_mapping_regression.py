"""관련기업 매핑 회귀 테스트: 샘플 뉴스 10건 → 기대 출력 비교 + 하이브리드(LLM) 병합 규칙 검증."""

from __future__ import annotations

import json

from app.config import Settings
from app.data.sector_map import KR_UNIVERSE, SECTORS
from app.transform.kr_mapping import WEIGHTS, label_for, map_to_korea, relevance
from app.transform.us_close import rank_news
from tests.helpers import FIXTURES, FakeAnalyst, load_sample_news, no_llm

EXPECTED = json.loads((FIXTURES / "expected_mapping.json").read_text())
MEGACAPS = set(Settings().watchlist)


async def _rules_pipeline():
    ranked, method, _ = await rank_news(load_sample_news(), no_llm(), MEGACAPS)
    mapping = await map_to_korea(ranked, no_llm())
    return ranked, method, mapping


async def test_news_ranking_matches_expected():
    ranked, method, _ = await _rules_pipeline()
    assert method == "rules"
    assert [r["id"] for r in ranked] == EXPECTED["news_order"]
    assert {r["id"]: r["tier"] for r in ranked} == EXPECTED["news_tiers"]
    assert [r["rank"] for r in ranked] == list(range(1, 11))


async def test_invalid_urls_kept_in_rank_with_no_link():
    ranked, _, _ = await _rules_pipeline()
    no_link = sorted(r["id"] for r in ranked if r["url"] is None)
    assert no_link == sorted(EXPECTED["no_link_ids"])
    assert len(ranked) == 10  # 링크가 없어도 제외하지 않음


async def test_sector_company_mapping_matches_expected():
    _, _, mapping = await _rules_pipeline()
    got = {s["key"]: [c["code"] for c in s["companies"]] for s in mapping["sectors"]}
    assert got == EXPECTED["sectors"]
    assert [s["key"] for s in mapping["sectors"]][:2] == EXPECTED["first_sectors"]
    for s in mapping["sectors"]:
        rels = [c["relevance"] for c in s["companies"]]
        assert rels == sorted(rels, reverse=True)
        for c in s["companies"]:
            assert c["rationale"]  # 판단 근거 1줄 필수
            assert set(c["magnitudes"]) == set(WEIGHTS)
            # LLM 이 없으면 수혜/악재 방향을 추측하지 않는다
            assert c["score"] is None and c["scores"] is None and c["label"] == "방향 미판정"


async def test_ticker_edge_rationale_takes_priority():
    _, _, mapping = await _rules_pipeline()
    semis = next(s for s in mapping["sectors"] if s["key"] == "semiconductors")
    hynix = next(c for c in semis["companies"] if c["code"] == "000660")
    assert "HBM" in hynix["rationale"] and hynix["magnitudes"]["supply_chain"] == 1.0


def test_theme_has_lowest_weight_and_no_same_industry():
    assert "same_industry" not in WEIGHTS  # 동일산업은 점수에서 제외 (2026-09-29 요청)
    assert WEIGHTS["theme"] == min(WEIGHTS.values())
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    assert [round(WEIGHTS[c] * 100) for c in ("supply_chain", "sensitivity", "theme")] == [
        46,
        38,
        15,
    ]


def test_score_labels():
    assert [label_for(v) for v in (80, 30, 29, 10, 9, 0, -9, -10, -29, -30, None)] == [
        "수혜",
        "수혜",
        "약한 수혜",
        "약한 수혜",
        "중립",
        "중립",
        "중립",
        "약한 악재",
        "약한 악재",
        "악재",
        "방향 미판정",
    ]


def test_static_table_codes_are_in_universe():
    for s in SECTORS.values():
        for r in s.relations:
            assert r.code in KR_UNIVERSE, (s.key, r.code)


async def test_hybrid_blends_llm_and_drops_unknown_codes():
    ranked, _, _ = await _rules_pipeline()

    def rel(code, sc, se, th, why, key="energy_oil"):
        return {"sector_key": key, "code": code, "supply_chain": sc, "sensitivity": se,
                "theme": th, "rationale": why}  # fmt: skip

    llm = FakeAnalyst(
        kr=[
            # 정적 관계가 있는 쌍 → 크기 0.6*정적 + 0.4*|LLM|, 부호는 LLM(악재)
            rel("010950", 0.0, -0.5, 0.0, "유가 급등에 정제마진 악화"),
            # LLM 만 제시한 쌍 → 크기 0.8 할인, 수혜, 근거는 AI 추론 표기
            rel("005490", 0.5, 1.0, 0.5, "원가 영향"),
            # 후보에 없는 종목/섹터 → 폐기
            rel("999999", 1, 1, 1, "가짜"),
            rel("005930", 1, 1, 1, "x", key="not_active"),
        ]
    )
    mapping = await map_to_korea(ranked, llm)
    assert mapping["method"] == "hybrid"
    energy = next(s for s in mapping["sectors"] if s["key"] == "energy_oil")
    by = {c["code"]: c for c in energy["companies"]}
    assert "999999" not in by
    soil = by["010950"]
    static = next(r for r in SECTORS["energy_oil"].relations if r.code == "010950")
    mag = round(0.6 * static.sensitivity + 0.4 * 0.5, 3)
    assert soil["magnitudes"]["sensitivity"] == mag
    assert soil["scores"]["sensitivity"] == -round(100 * mag)  # 악재 → 음수
    assert soil["scores"]["supply_chain"] == 0  # LLM 이 영향 없음(0) → 0점
    assert soil["score"] < 0 and soil["label"] in ("악재", "약한 악재")
    assert soil["rationale_origin"] == "rule"
    posco = by["005490"]
    assert posco["rationale_origin"] == "llm"
    assert posco["magnitudes"]["sensitivity"] == 0.8
    assert posco["scores"] == {"supply_chain": 40, "sensitivity": 80, "theme": 40}
    assert (
        posco["score"] == round(sum(WEIGHTS[c] * posco["scores"][c] for c in WEIGHTS))
        and posco["label"] == "수혜"
    )
    assert posco["relevance"] == relevance(posco["magnitudes"])
    # 영향이 큰 순(|점수|)
    scored = [abs(c["score"]) for c in energy["companies"] if c["score"] is not None]
    assert scored == sorted(scored, reverse=True)


async def test_llm_cannot_inject_unknown_news_or_tickers():
    items = load_sample_news()

    def fake(cands):
        return [
            {
                "id": "s6",
                "tier": "a",
                "importance": 99,
                "title_ko": "유가 급등",
                "summary_ko": "OPEC+ 감산 발표로 유가 급등",
                "sectors": ["energy_oil", "bogus"],
                "tickers": ["XOM", "S6"],
            },
            {
                "id": "fake-id",
                "tier": "a",
                "importance": 100,
                "title_ko": "가짜",
                "summary_ko": "가짜",
                "sectors": [],
                "tickers": [],
            },
        ]

    ranked, method, _ = await rank_news(items, FakeAnalyst(us=fake), MEGACAPS)
    assert method == "llm"
    assert ranked[0]["id"] == "s6" and ranked[0]["summary_origin"] == "llm"
    assert [s["key"] for s in ranked[0]["sectors"]] == ["energy_oil"]
    assert ranked[0]["tickers"] == []  # 원문에 없는 티커 제거
    assert ranked[0]["url"] == "https://example.com/news/6"  # URL 은 원본 그대로
    assert all(r["id"] != "fake-id" for r in ranked)


async def test_fewer_than_ten_news_warns_without_padding():
    items = load_sample_news()[:4]
    ranked, _, warnings = await rank_news(items, no_llm(), MEGACAPS)
    assert len(ranked) == 4
    assert any("4건" in w for w in warnings)
