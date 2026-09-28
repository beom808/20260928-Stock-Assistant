"""관련기업 매핑 회귀 테스트: 샘플 뉴스 10건 → 기대 출력 비교 + 하이브리드(LLM) 병합 규칙 검증."""

from __future__ import annotations

import json

from app.config import Settings
from app.data.sector_map import KR_UNIVERSE, SECTORS
from app.transform.kr_mapping import WEIGHTS, map_to_korea, relevance
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
            assert set(c["scores"]) == set(WEIGHTS)


async def test_ticker_edge_rationale_takes_priority():
    _, _, mapping = await _rules_pipeline()
    semis = next(s for s in mapping["sectors"] if s["key"] == "semiconductors")
    hynix = next(c for c in semis["companies"] if c["code"] == "000660")
    assert "HBM" in hynix["rationale"] and hynix["scores"]["supply_chain"] == 1.0


def test_theme_has_lowest_weight():
    assert WEIGHTS["theme"] == min(WEIGHTS.values())
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_static_table_codes_are_in_universe():
    for s in SECTORS.values():
        for r in s.relations:
            assert r.code in KR_UNIVERSE, (s.key, r.code)


async def test_hybrid_blends_llm_and_drops_unknown_codes():
    ranked, _, _ = await _rules_pipeline()
    llm = FakeAnalyst(
        kr=[
            # 정적 관계가 있는 쌍 → 0.6*정적 + 0.4*LLM
            {
                "sector_key": "energy_oil",
                "code": "010950",
                "same_industry": 0.5,
                "supply_chain": 0.0,
                "sensitivity": 0.5,
                "theme": 0.0,
                "rationale": "정유",
            },
            # LLM 만 제시한 쌍 → 0.8 할인, 근거는 AI 추론 표기
            {
                "sector_key": "energy_oil",
                "code": "005490",
                "same_industry": 0.0,
                "supply_chain": 0.5,
                "sensitivity": 1.0,
                "theme": 0.5,
                "rationale": "원가 영향",
            },
            # 후보에 없는 종목/섹터 → 폐기
            {
                "sector_key": "energy_oil",
                "code": "999999",
                "same_industry": 1,
                "supply_chain": 1,
                "sensitivity": 1,
                "theme": 1,
                "rationale": "가짜",
            },
            {
                "sector_key": "not_active",
                "code": "005930",
                "same_industry": 1,
                "supply_chain": 1,
                "sensitivity": 1,
                "theme": 1,
                "rationale": "x",
            },
        ]
    )
    mapping = await map_to_korea(ranked, llm)
    assert mapping["method"] == "hybrid"
    energy = next(s for s in mapping["sectors"] if s["key"] == "energy_oil")
    by = {c["code"]: c for c in energy["companies"]}
    assert "999999" not in by
    soil = by["010950"]
    assert soil["scores"]["same_industry"] == round(0.6 * 0.9 + 0.4 * 0.5, 3)
    assert soil["rationale_origin"] == "rule"
    posco = by["005490"]
    assert posco["rationale_origin"] == "llm"
    assert posco["scores"]["sensitivity"] == 0.8
    assert posco["relevance"] == relevance(posco["scores"])


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
