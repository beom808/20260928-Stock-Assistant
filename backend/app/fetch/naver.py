"""네이버 검색 API(뉴스) — 국내 당일 이슈 수집용(선택).

검색 API 전체 합산 25,000 req/day 로 조사됨(재확인 필요). originallink(언론사 원문)를 우선 사용,
없으면 link(네이버 뉴스). 둘 다 API 응답값 그대로이며 생성·수정하지 않는다.
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
    URL = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self, client: ApiClient, client_id: str, client_secret: str) -> None:
        self.client = client
        self.cid = client_id
        self.secret = client_secret

    async def search(self, query: str, display: int = 30) -> list[NewsItem]:
        if not (self.cid and self.secret):
            raise ApiError(self.provider, "config", "NAVER_CLIENT_ID / SECRET 미설정")
        res = await self.client.get_json(
            self.URL,
            params={"query": query, "display": display, "sort": "date"},
            headers={"X-Naver-Client-Id": self.cid, "X-Naver-Client-Secret": self.secret},
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
