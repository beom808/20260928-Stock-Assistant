"""Financial Modeling Prep (지수 시세 · 경제캘린더 · 실적캘린더 fallback).

무료 250 req/day 로 조사됨. economic-calendar / earnings-calendar 는 유료 플랜 전용일 수 있다는
2차 자료가 있으므로 연동 전 반드시 요금제 확인. 402/403 응답 시 ApiClient 가 즉시 실패 처리한다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.fetch.http import ApiClient, ApiError
from app.schemas import EarningsEvent, EconEvent, IndexQuote
from app.timeutil import ET


def _num_str(v: object) -> str | None:
    if v is None or v == "":
        return None
    return str(v)


class FmpFetcher:
    provider = "fmp"

    def __init__(self, client: ApiClient, api_key: str, base_url: str, econ_tz: str) -> None:
        self.client = client
        self.api_key = api_key
        self.base = base_url.rstrip("/")
        self.econ_tz = ZoneInfo(econ_tz)

    async def _get(self, path: str, params: dict, ttl: timedelta):
        if not self.api_key:
            raise ApiError(self.provider, "config", "FMP_API_KEY 미설정")
        return await self.client.get_json(
            f"{self.base}{path}", params={**params, "apikey": self.api_key}, ttl=ttl
        )

    async def index_eod(self, name: str, symbol: str, session: date) -> IndexQuote:
        """기준 세션의 공식 종가(일별 EOD). 등락은 직전 거래일 종가로 직접 계산한다.

        2026-09-29 점검: /quote 는 마감 직전(15:59 ET) 값이 남는 경우가 있었다(S&P 500 7,684.50
        vs 종가 7,683.69). /historical-price-eod/light 는 공식 종가와 일치했다.
        (/full 의 change·changePercent 는 '시가 대비'라 전일 대비 등락으로 쓰면 안 된다)
        """
        res = await self._get(
            "/historical-price-eod/light",
            {
                "symbol": symbol,
                "from": (session - timedelta(days=10)).isoformat(),
                "to": session.isoformat(),
            },
            timedelta(hours=1),
        )
        rows = []
        for r in res.data if isinstance(res.data, list) else []:
            try:
                rows.append((date.fromisoformat(str(r["date"])), float(r["price"])))
            except (KeyError, TypeError, ValueError):
                continue
        rows.sort(reverse=True)
        if not rows or rows[0][0] != session:
            raise ApiError(self.provider, "parse", f"{symbol} {session} 종가 없음(아직 미반영)")
        close = rows[0][1]
        change = pct = None
        if len(rows) > 1 and rows[1][1]:
            prev = rows[1][1]
            change = round(close - prev, 2)
            pct = round(change / prev * 100, 2)
        return IndexQuote(
            name=name,
            symbol=symbol,
            close=close,
            change=change,
            change_pct=pct,
            as_of=datetime.combine(session, time(16, 0), tzinfo=ET).astimezone(UTC),
            provider="FMP (일별 종가)",
        )

    async def index_quote(self, name: str, symbol: str) -> IndexQuote:
        res = await self._get("/quote", {"symbol": symbol}, timedelta(minutes=10))
        rows = res.data if isinstance(res.data, list) else []
        if not rows:
            raise ApiError(self.provider, "parse", f"{symbol} 시세 없음")
        q = rows[0]
        pct = q.get("changePercentage", q.get("changesPercentage"))
        ts = q.get("timestamp")
        return IndexQuote(
            name=name,
            symbol=symbol,
            close=q.get("price"),
            change=q.get("change"),
            change_pct=pct,
            as_of=datetime.fromtimestamp(ts, UTC) if isinstance(ts, (int, float)) else None,
            provider="FMP",
        )

    def _parse_econ_dt(self, raw: str) -> tuple[datetime | None, date | None]:
        try:
            naive = datetime.fromisoformat(raw.strip().replace(" ", "T"))
        except (ValueError, AttributeError):
            return None, None
        aware = naive.replace(tzinfo=self.econ_tz)
        return aware.astimezone(UTC), aware.astimezone(ET).date()

    async def economic_calendar(self, d_from: date, d_to: date) -> list[EconEvent]:
        res = await self._get(
            "/economic-calendar",
            {"from": d_from.isoformat(), "to": d_to.isoformat()},
            timedelta(hours=3),
        )
        out = []
        for r in res.data if isinstance(res.data, list) else []:
            country = str(r.get("country") or "").upper()
            if country not in ("US", "USA", "UNITED STATES"):
                continue
            at_utc, d_et = self._parse_econ_dt(str(r.get("date") or ""))
            if d_et is None:
                continue
            out.append(
                EconEvent(
                    name=str(r.get("event") or "").strip(),
                    country="US",
                    at_utc=at_utc,
                    date_et=d_et,
                    estimate=_num_str(r.get("estimate")),
                    previous=_num_str(r.get("previous")),
                    impact=r.get("impact"),
                    provider="FMP",
                )
            )
        return out

    async def earnings_calendar(self, d_from: date, d_to: date) -> list[EarningsEvent]:
        res = await self._get(
            "/earnings-calendar",
            {"from": d_from.isoformat(), "to": d_to.isoformat()},
            timedelta(hours=6),
        )
        out = []
        for r in res.data if isinstance(res.data, list) else []:
            try:
                d = date.fromisoformat(str(r.get("date")))
            except ValueError:
                continue
            t = str(r.get("time") or "").lower()  # stable 응답에 time 이 없으면 미확정 처리
            out.append(
                EarningsEvent(
                    symbol=str(r.get("symbol", "")).upper(),
                    date_et=d,
                    hour=t if t in ("bmo", "amc") else None,
                    eps_estimate=r.get("epsEstimated"),
                    revenue_estimate=r.get("revenueEstimated"),
                    provider="FMP",
                )
            )
        return out
