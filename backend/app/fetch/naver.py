"""네이버 검색 API(뉴스) — 국내 당일 이슈 수집용(선택).

2026-07-31 부터 네이버 개발자센터(openapi.naver.com) 검색 API 신규 발급이 막히고
네이버 클라우드 플랫폼의 NAVER API HUB 로 이관됨.
(2차 자료로 확인 — 공식 문서 원문은 개발 환경에서 접근 불가)
- hub(기본): GET https://naverapihub.apigw.ntruss.com/search/v1/news
  헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
- legacy: GET https://openapi.naver.com/v1/search/news.json
  헤더 X-Naver-Client-Id / X-Naver-Client-Secret (기존 발급 키, 2027-06-30 종료 예정으로 알려짐)
요청 파라미터·응답 형식은 둘이 같다고 알려져 있다(2차 자료).

originallink(언론사 원문)를 우선 사용, 없으면 link(네이버 뉴스).
둘 다 API 응답값 그대로이며 생성·수정하지 않는다.
"""

from __future__ import annotations

import html
import re
from datetime import timedelta
from email.utils import parsedate_to_datetime

from app.fetch.http import ApiClient, ApiError
from app.schemas import NewsItem, safe_url, stable_id

_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html.unescape(_TAG.sub("", s or "")).strip()


class NaverNewsFetcher:
    provider = "naver"
    ENDPOINTS = {
        "hub": (
            "https://naverapihub.apigw.ntruss.com/search/v1/news",
            ("X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
        ),
        "legacy": (
            "https://openapi.naver.com/v1/search/news.json",
            ("X-Naver-Client-Id", "X-Naver-Client-Secret"),
        ),
    }

    def __init__(
        self, client: ApiClient, client_id: str, client_secret: str, api: str = "hub"
    ) -> None:
        self.client = client
        self.cid = client_id
        self.secret = client_secret
        self.api = api.strip().lower() or "hub"

    async def search(self, query: str, display: int = 30) -> list[NewsItem]:
        if not (self.cid and self.secret):
            raise ApiError(self.provider, "config", "NAVER_CLIENT_ID / SECRET 미설정")
        if self.api not in self.ENDPOINTS:
            msg = f"NAVER_API 는 hub 또는 legacy (현재 {self.api!r})"
            raise ApiError(self.provider, "config", msg)
        url, (id_header, secret_header) = self.ENDPOINTS[self.api]
        res = await self.client.get_json(
            url,
            params={"query": query, "display": display, "sort": "date"},
            headers={id_header: self.cid, secret_header: self.secret},
            ttl=timedelta(minutes=15),
        )
        out = []
        for i, r in enumerate((res.data or {}).get("items", []) or []):
            try:
                pub = parsedate_to_datetime(r.get("pubDate", ""))
            except (TypeError, ValueError):
                continue
            title = _clean(r.get("title", ""))
            if not title:
                continue
            url = safe_url(r.get("originallink")) or safe_url(r.get("link"))
            out.append(
                NewsItem(
                    id=stable_id("nv", title, r.get("pubDate"), i),
                    headline=title,
                    summary=_clean(r.get("description", "")),
                    url=url,
                    source=(url or "").split("/")[2] if url else "",
                    published_at=pub,
                    provider="네이버 검색 API",
                )
            )
        return out
