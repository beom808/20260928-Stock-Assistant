"""Claude 래퍼: 요청 형태(structured outputs · fallbacks) 와 실패 시 LLMUnavailable 변환.

anthropic SDK 1.x 는 httpx2 기반이므로 respx 대신 httpx2.MockTransport 로 네트워크를 차단한다.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

from app.llm.claude import FALLBACK_BETA, ClaudeAnalyst, LLMUnavailable

CANDS = [{"id": "n1", "headline": "h", "summary": "s", "related": [], "source": "x"}]


def msg(text: str, stop: str = "end_turn") -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def analyst(handler) -> tuple[ClaudeAnalyst, list]:
    seen: list = []

    def _h(req):
        seen.append(req)
        return handler(req)

    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(_h)),
    )
    return ClaudeAnalyst(api_key="test-key", model="claude-opus-5", client=client), seen


async def test_request_shape_and_parse():
    a, seen = analyst(lambda r: httpx2.Response(200, json=msg(json.dumps({"items": []}))))
    assert await a.rank_us_news(CANDS, ["semiconductors"]) == []
    req = seen[-1]
    body = json.loads(req.content)
    assert body["model"] == "claude-opus-5"
    assert body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    item = body["output_config"]["format"]["schema"]["properties"]["items"]["items"]
    assert item["properties"]["id"]["enum"] == ["n1"]
    assert "url" not in item["properties"]  # LLM 은 URL 을 출력할 수 없음
    assert FALLBACK_BETA in req.headers.get("anthropic-beta", "")


async def test_refusal_becomes_unavailable():
    a, _ = analyst(lambda r: httpx2.Response(200, json=msg("", "refusal")))
    with pytest.raises(LLMUnavailable, match="refusal"):
        await a.rank_us_news(CANDS, [])


async def test_truncated_output_becomes_unavailable():
    a, _ = analyst(lambda r: httpx2.Response(200, json=msg('{"items": [', "max_tokens")))
    with pytest.raises(LLMUnavailable, match="truncated"):
        await a.rank_us_news(CANDS, [])


async def test_api_error_becomes_unavailable():
    err = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    a, _ = analyst(lambda r: httpx2.Response(529, json=err))
    with pytest.raises(LLMUnavailable, match="529"):
        await a.rank_us_news(CANDS, [])


async def test_missing_key_is_unavailable():
    with pytest.raises(LLMUnavailable):
        await ClaudeAnalyst(api_key="", model="m").rank_us_news(CANDS, [])
