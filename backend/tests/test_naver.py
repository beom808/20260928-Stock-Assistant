"""네이버 뉴스 검색: NAVER API HUB(기본) / 기존 개발자센터(legacy) 주소·인증 헤더."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.fetch.http import ApiError
from app.fetch.providers import build_providers

HUB = "https://naverapihub.apigw.ntruss.com/search/v1/news"
LEGACY = "https://openapi.naver.com/v1/search/news.json"
BODY = {
    "items": [
        {
            "title": "<b>코스피</b> 외국인 순매도 &amp; 반도체 약세",
            "originallink": "https://www.example-news.co.kr/article/1",
            "link": "https://n.news.naver.com/mnews/article/001/1",
            "description": "요약 <b>본문</b>",
            "pubDate": "Tue, 29 Sep 2026 14:05:00 +0900",
        },
        {"title": "날짜 없는 기사", "pubDate": ""},
    ]
}


def settings(**kw) -> Settings:
    return Settings(
        _env_file=None, **({"naver_client_id": "ID", "naver_client_secret": "SEC"} | kw)
    )


async def _search(sessions, st):
    p = build_providers(st, sessions)
    try:
        return await p.naver.search("코스피")
    finally:
        await p.aclose()


@respx.mock
async def test_hub_is_default_and_uses_ncp_headers(sessions):
    route = respx.get(HUB).mock(return_value=httpx.Response(200, json=BODY))
    items = await _search(sessions, settings())
    req = route.calls.last.request
    assert req.headers["X-NCP-APIGW-API-KEY-ID"] == "ID"
    assert req.headers["X-NCP-APIGW-API-KEY"] == "SEC"
    assert "X-Naver-Client-Id" not in req.headers
    assert req.url.params["query"] == "코스피" and req.url.params["sort"] == "date"
    assert len(items) == 1  # pubDate 없는 항목은 버린다
    it = items[0]
    assert it.headline == "코스피 외국인 순매도 & 반도체 약세"
    assert it.summary == "요약 본문"
    assert it.url == "https://www.example-news.co.kr/article/1"  # 응답값 그대로(원문 우선)


@respx.mock
async def test_legacy_developer_center_keys(sessions):
    route = respx.get(LEGACY).mock(return_value=httpx.Response(200, json=BODY))
    items = await _search(sessions, settings(naver_api="legacy"))
    req = route.calls.last.request
    assert req.headers["X-Naver-Client-Id"] == "ID"
    assert req.headers["X-Naver-Client-Secret"] == "SEC"
    assert len(items) == 1


async def test_unknown_mode_and_missing_keys_are_config_errors(sessions):
    with pytest.raises(ApiError) as e:
        await _search(sessions, settings(naver_api="hubb"))
    assert e.value.kind == "config"
    with pytest.raises(ApiError) as e:
        await _search(sessions, Settings(_env_file=None))
    assert e.value.kind == "config"
