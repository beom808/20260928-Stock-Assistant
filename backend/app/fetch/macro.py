"""환율(USD/KRW)·거시지표 — 무료 출처만 사용.

2026-09-29 점검(backend/scripts/probe_fx.py, probe_fmp.py):
- FMP USDKRW·^TNX·DX-Y.NYB·유가·지수선물: 무료 플랜 402 / Finnhub forex: 403 → 사용 불가
- ECB 기준환율(Frankfurter, 키 없음): 200 {"base":"USD","date":"2026-09-28","rates":{"KRW":1357.93}}
  ECB 가 영업일마다 한 번 고시하는 값이다(한국 시각으로는 그날 밤). 서울 외환시장 종가가 아니므로
  화면에 반드시 '고시일'과 함께 'ECB 기준'으로 표시한다.
- FRED(무료 키): DGS10(미 10년물, %), DTWEXBGS(연준 광의 달러지수 — ICE DXY 와 다른 지수) 는
  1영업일 이상 늦게 반영된다. DCOILWTICO(WTI)는 주 단위로 늦어 쓰지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.fetch.http import ApiClient, ApiError

ECB_URL = "https://api.frankfurter.app"
FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
# (표시 이름, FRED 시리즈, 단위, 설명)
FRED_MACRO = [
    ("미국 10년물 금리", "DGS10", "%", "FRED DGS10"),
    ("달러지수(연준 광의)", "DTWEXBGS", "", "FRED DTWEXBGS · ICE DXY 와 다른 지수"),
]


def _is_dict(body: object) -> bool:
    return isinstance(body, dict)


def parse_ecb_series(body: object) -> list[tuple[date, float]]:
    """Frankfurter 기간 조회 {"rates": {"YYYY-MM-DD": {"KRW": x}}} → 최신순 [(날짜, 값)]."""
    rates = body.get("rates") if isinstance(body, dict) else None
    out: list[tuple[date, float]] = []
    for k, v in (rates or {}).items():
        try:
            out.append((date.fromisoformat(k), float(v["KRW"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, reverse=True)


def parse_fred_latest(body: object) -> list[tuple[date, float]]:
    """FRED observations(최신순) → 결측(".") 제외한 [(날짜, 값)]."""
    obs = body.get("observations") if isinstance(body, dict) else None
    out: list[tuple[date, float]] = []
    for o in obs or []:
        try:
            out.append((date.fromisoformat(str(o.get("date"))), float(o.get("value"))))
        except (TypeError, ValueError):
            continue
    return sorted(out, reverse=True)


def _change(rows: list[tuple[date, float]]) -> tuple[float | None, float | None]:
    if len(rows) < 2 or not rows[1][1]:
        return None, None
    ch = rows[0][1] - rows[1][1]
    return ch, ch / rows[1][1] * 100


class MacroFetcher:
    provider = "macro"

    def __init__(self, client: ApiClient, fred_api_key: str = "") -> None:
        self.client = client
        self.fred_api_key = fred_api_key

    async def usdkrw_ecb(self, today: date) -> dict:
        """ECB 기준 USD/KRW (최신 고시일 값 + 직전 고시일 대비)."""
        res = await self.client.get_json(
            f"{ECB_URL}/{(today - timedelta(days=10)).isoformat()}..",
            params={"from": "USD", "to": "KRW"},
            ttl=timedelta(hours=1),
            cache_if=_is_dict,
            follow_redirects=True,
        )
        rows = [r for r in parse_ecb_series(res.data) if r[0] <= today]
        if not rows:
            raise ApiError(self.provider, "parse", "ECB USD/KRW 값 없음")
        ch, pct = _change(rows)
        d, v = rows[0]
        return {
            "pair": "USD/KRW",
            "rate": round(v, 2),
            "change": round(ch, 2) if ch is not None else None,
            "change_pct": round(pct, 2) if pct is not None else None,
            "date": d.isoformat(),
            "provider": "ECB 기준환율 (Frankfurter)",
            "note": f"ECB {d:%m/%d} 고시 · 서울 외환시장 종가 아님",
        }

    async def fred_macro(self) -> list[dict]:
        if not self.fred_api_key:
            raise ApiError(self.provider, "config", "FRED_API_KEY 미설정")
        out = []
        for name, series, unit, desc in FRED_MACRO:
            res = await self.client.get_json(
                FRED_OBS_URL,
                params={
                    "api_key": self.fred_api_key,
                    "file_type": "json",
                    "series_id": series,
                    "sort_order": "desc",
                    "limit": 6,  # 결측(".") 대비 여유
                },
                ttl=timedelta(hours=3),
                cache_if=_is_dict,
            )
            rows = parse_fred_latest(res.data)
            if not rows:
                out.append({"name": name, "error": "값 없음", "provider": desc})
                continue
            ch, _ = _change(rows)
            out.append(
                {
                    "name": name,
                    "value": round(rows[0][1], 2),
                    "unit": unit,
                    "change": round(ch, 2) if ch is not None else None,
                    "date": rows[0][0].isoformat(),
                    "provider": desc,
                    "note": f"{rows[0][0]:%m/%d} 기준 · FRED 는 1영업일 이상 늦게 반영",
                }
            )
        return out
