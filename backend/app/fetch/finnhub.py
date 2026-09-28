"""Finnhub (뉴스 · 실적캘린더 · 시세).

무료 60 req/min 으로 조사됨 — 연동 전 재확인.

주의: Finnhub 무료 플랜은 개인용(재배포 불가) 조건으로 알려짐 → 서비스 공개 전 약관 확인 필요.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.fetch.http import ApiClient, ApiError, FetchResult
from app.schemas import EarningsEvent, IndexQuote, NewsItem, safe_url, stable_id


class FinnhubFetcher:
    provider = "finnhub"

    def __init__(self, client: ApiClient, api_key: str, base_url: str) -> None:
        self.client = client
        self.api_key = api_key
        self.base = base_url.rstrip("/")

    def _check(self) -> None:
        if not self.api_key:
            raise ApiError(self.provider, "config", "FINNHUB_API_KEY 미설정")

    async def _get(self, path: str, params: dict, ttl: timedelta) -> FetchResult:
        self._check()
        return await self.client.get_json(
            f"{self.base}{path}", params={**params, "token": self.api_key}, ttl=ttl
        )

    @staticmethod
    def _to_news(raw: dict) -> NewsItem | None:
        headline = (raw.get("headline") or "").strip()
        ts = raw.get("datetime")
        if not headline or not isinstance(ts, (int, float)):
            return None
        related = [t.strip().upper() for t in str(raw.get("related") or "").split(",") if t.strip()]
        return NewsItem(
            id=f"fh-{raw['id']}" if raw.get("id") else stable_id("fh", headline, ts),
            headline=headline,
            summary=(raw.get("summary") or "").strip(),
            url=safe_url(raw.get("url")),
            source=raw.get("source") or "",
            published_at=datetime.fromtimestamp(ts, UTC),
            related_tickers=related,
            provider="Finnhub",
        )

    async def market_news(self) -> tuple[list[NewsItem], FetchResult]:
        res = await self._get("/news", {"category": "general"}, timedelta(minutes=10))
        items = [n for n in (self._to_news(r) for r in res.data or []) if n]
        return items, res

    async def company_news(self, symbol: str, d_from: date, d_to: date) -> list[NewsItem]:
        res = await self._get(
            "/company-news",
            {"symbol": symbol, "from": d_from.isoformat(), "to": d_to.isoformat()},
            timedelta(minutes=30),
        )
        out = []
        for r in res.data or []:
            n = self._to_news(r)
            if n:
                if symbol not in n.related_tickers:
                    n.related_tickers.append(symbol)
                out.append(n)
        return out

    async def earnings_calendar(self, d_from: date, d_to: date) -> list[EarningsEvent]:
        res = await self._get(
            "/calendar/earnings",
            {"from": d_from.isoformat(), "to": d_to.isoformat()},
            timedelta(hours=6),
        )
        out = []
        for r in (res.data or {}).get("earningsCalendar", []) or []:
            try:
                d = date.fromisoformat(r["date"])
            except (KeyError, ValueError, TypeError):
                continue
            hour = (r.get("hour") or "").lower() or None
            out.append(
                EarningsEvent(
                    symbol=str(r.get("symbol", "")).upper(),
                    date_et=d,
                    hour=hour if hour in ("bmo", "amc", "dmh") else None,
                    eps_estimate=r.get("epsEstimate"),
                    revenue_estimate=r.get("revenueEstimate"),
                    provider="Finnhub",
                )
            )
        return out

    async def etf_proxy_quote(self, name: str, etf: str) -> IndexQuote:
        """지수 시세를 못 받을 때의 대체: 지수 추종 ETF 가격(프록시임을 명시)."""
        res = await self._get("/quote", {"symbol": etf}, timedelta(minutes=10))
        q = res.data or {}
        if not q.get("c"):
            raise ApiError(self.provider, "parse", f"{etf} 시세 없음")
        return IndexQuote(
            name=name,
            symbol=etf,
            close=q.get("c"),
            change=q.get("d"),
            change_pct=q.get("dp"),
            as_of=datetime.fromtimestamp(q["t"], UTC) if q.get("t") else None,
            provider="Finnhub",
            is_proxy=True,
            note=f"지수 대신 추종 ETF({etf}) 등락률 — 지수와 소폭 차이 가능",
        )
