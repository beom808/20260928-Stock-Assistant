"""Anthropic Claude API 래퍼 — 뉴스 요약·이슈 랭킹·섹터-종목 매핑 추론.

할루시네이션 방지 설계
- LLM 에는 '후보 ID 목록'만 고르게 하고(JSON Schema enum 으로 강제), 제목·URL·출처·시각은
  항상 원본 API 레코드에서 가져온다. LLM 출력에는 URL 필드 자체가 없다.
- 섹터 키 / 한국 종목코드도 enum 으로 제한 → 존재하지 않는 종목을 만들 수 없다.
- 출력은 structured outputs(JSON Schema)로 받고, 호출 측에서 한 번 더 검증한다.
- 거절(refusal)·오류·키 미설정 시 LLMUnavailable → 호출 측이 규칙기반 결과로 대체.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(Exception):
    pass


SYSTEM_PROMPT = (
    "당신은 한국 개인투자자를 위한 증시 리서치 보조 분석가입니다. 투자 권유를 하지 않습니다. "
    "반드시 입력으로 주어진 뉴스·목록 안의 정보만 사용하고, 입력에 없는 사실·수치·기업·URL을 "
    "만들어내지 마십시오. 확신이 없으면 낮은 점수를 주고, 판단 근거는 입력 텍스트에 기반해 "
    "짧게 한국어로 쓰십시오."
)


class ClaudeAnalyst:
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        self.enabled = bool(api_key) or client is not None
        self._client = client or (anthropic.AsyncAnthropic(api_key=api_key) if api_key else None)

    async def _structured(self, user: str, schema: dict, max_tokens: int = 16000) -> dict:
        if not self.enabled or self._client is None:
            raise LLMUnavailable("ANTHROPIC_API_KEY 미설정")
        try:
            resp = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
                # 안전 분류기 거절 시 서버측 기본 fallback 모델로 재시도
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise LLMUnavailable(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMUnavailable(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMUnavailable(f"connection error: {e}") from e

        if resp.stop_reason == "refusal":
            raise LLMUnavailable("model refusal")
        if resp.stop_reason == "max_tokens":
            raise LLMUnavailable("output truncated (max_tokens)")
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
        if not text:
            raise LLMUnavailable("empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMUnavailable(f"invalid JSON: {e}") from e

    # ── 기능 A: 미국 뉴스 분류/요약 ─────────────────────────────────────────
    async def rank_us_news(self, candidates: list[dict], sector_keys: list[str]) -> list[dict]:
        ids = [c["id"] for c in candidates]
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "enum": ids},
                            "tier": {"type": "string", "enum": ["a", "b", "c", "d"]},
                            "importance": {"type": "integer"},
                            "title_ko": {"type": "string"},
                            "summary_ko": {"type": "string"},
                            "sectors": {
                                "type": "array",
                                "items": {"type": "string", "enum": sector_keys},
                            },
                            "tickers": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": [
                            "id",
                            "tier",
                            "importance",
                            "title_ko",
                            "summary_ko",
                            "sectors",
                            "tickers",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        }
        prompt = (
            "아래는 미국 증시 관련 뉴스 후보(JSON)입니다. 각 항목을 분류하세요.\n"
            "tier 기준(우선순위 순): a=시장 전체 방향에 영향(금리·물가·고용·연준·관세 등 매크로), "
            "b=시가총액 상위 기업의 실적/가이던스, c=특정 섹터 전반에 영향, d=개별 이슈.\n"
            "importance: 0~100, 한국 투자자 관점의 시장 영향도.\n"
            "title_ko: 원 제목의 충실한 한국어 번역(새 정보 추가 금지). "
            "summary_ko: 입력 headline/summary 에 있는 내용만으로 한 줄 요약(80자 이내).\n"
            "sectors: 영향받는 섹터 키(주어진 enum 중). 시장 전체면 macro_broad.\n"
            "tickers: 입력 텍스트나 related 필드에 실제로 등장하는 미국 티커만.\n\n"
            + json.dumps(candidates, ensure_ascii=False)
        )
        data = await self._structured(prompt, schema)
        return data.get("items", [])

    # ── 기능 B: 한국 기업 관련도 추론 ───────────────────────────────────────
    async def infer_kr_relations(
        self, sector_briefs: list[dict], universe: list[dict]
    ) -> list[dict]:
        codes = [u["code"] for u in universe]
        keys = [b["sector_key"] for b in sector_briefs]
        score = {"type": "number"}
        schema = {
            "type": "object",
            "properties": {
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sector_key": {"type": "string", "enum": keys},
                            "code": {"type": "string", "enum": codes},
                            "supply_chain": score,
                            "sensitivity": score,
                            "theme": score,
                            "rationale": {"type": "string"},
                        },
                        "required": [
                            "sector_key",
                            "code",
                            "supply_chain",
                            "sensitivity",
                            "theme",
                            "rationale",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["relations"],
            "additionalProperties": False,
        }
        prompt = (
            "미국 섹터별 이슈 요약과 한국 상장기업 후보 목록이 주어집니다. "
            "각 섹터 이슈와 관련 있는 한국 기업만 골라, "
            "이번 이슈가 그 기업에 수혜인지 악재인지를 세 가지 경로별로 "
            "-1~+1 로 평가하세요(+ 수혜, - 악재, 0 영향 없음·판단 불가, 절댓값은 영향의 크기).\n"
            "① supply_chain: 고객사·공급사 관계를 통한 영향 "
            "② sensitivity: 수출 비중·환율·업황 등 실적 민감도를 통한 영향 "
            "③ theme: 테마성 연관(단순 키워드 일치는 절댓값 0.3 이하).\n"
            "확실히 알려진 관계가 아니면 supply_chain 절댓값을 크게 주지 마세요. 뉴스 내용만으로 "
            "방향을 판단할 수 없으면 0 에 가깝게 주세요. rationale 은 왜 수혜/악재로 봤는지 "
            "한국어 1줄(60자 이내).\n\n"
            f"섹터 이슈: {json.dumps(sector_briefs, ensure_ascii=False)}\n"
            f"한국 기업 후보: {json.dumps(universe, ensure_ascii=False)}"
        )
        data = await self._structured(prompt, schema)
        return data.get("relations", [])

    # ── 기능 C: 국내 당일 이슈 선정/요약 ────────────────────────────────────
    async def pick_kr_issues(self, candidates: list[dict], k: int) -> list[dict]:
        ids = [c["id"] for c in candidates]
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "enum": ids},
                            "summary_ko": {"type": "string"},
                        },
                        "required": ["id", "summary_ko"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        }
        prompt = (
            "다음은 오늘 국내 증시 관련 뉴스 후보입니다. "
            f"오늘 코스피·코스닥 지수 움직임에 영향이 가장 컸던 순서로 {k + 3}건을 고르세요"
            "(지수 전체를 움직인 수급·매크로·대형주 이슈를 개별 종목 이슈보다 우선). "
            "같은 사건을 다룬 기사는 하나만 고르고 나머지는 서로 다른 주제로 채우되, "
            "해외 개별 종목 기사처럼 한국 증시와 무관한 것은 제외하세요(후보가 부족할 때만 적게). "
            "각 기사에 입력 내용만으로 한 줄 요약(80자 이내)을 쓰세요.\n\n"
            + json.dumps(candidates, ensure_ascii=False)
        )
        data = await self._structured(prompt, schema)
        return data.get("items", [])[: k + 3]
