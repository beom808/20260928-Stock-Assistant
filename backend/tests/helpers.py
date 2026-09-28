from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.llm.claude import ClaudeAnalyst
from app.schemas import NewsItem, safe_url

FIXTURES = Path(__file__).parent / "fixtures"


def load_sample_news() -> list[NewsItem]:
    raw = json.loads((FIXTURES / "sample_news.json").read_text())["items"]
    return [
        NewsItem(
            id=r["id"],
            headline=r["headline"],
            summary=r["summary"],
            url=safe_url(r["url"]),
            source="example",
            published_at=datetime.fromtimestamp(r["ts"], UTC),
            related_tickers=[t for t in r["related"].split(",") if t],
            provider="fixture",
        )
        for r in raw
    ]


def no_llm() -> ClaudeAnalyst:
    return ClaudeAnalyst(api_key="", model="test")


class FakeAnalyst(ClaudeAnalyst):
    """고정 응답을 돌려주는 가짜 LLM (네트워크 없음)."""

    def __init__(self, us=None, kr=None, issues=None) -> None:
        super().__init__(api_key="", model="fake")
        self.enabled = True
        self._us, self._kr, self._issues = us, kr, issues

    async def rank_us_news(self, candidates, sector_keys):
        return self._us(candidates) if callable(self._us) else (self._us or [])

    async def infer_kr_relations(self, sector_briefs, universe):
        return self._kr or []

    async def pick_kr_issues(self, candidates, k):
        return self._issues or []
