"""USD/KRW 무료 출처 점검(수동). 키는 출력하지 않는다."""

from __future__ import annotations

import os
import sys

import httpx


def show(c: httpx.Client, label: str, url: str, params: dict) -> None:
    try:
        r = c.get(url, params=params)
        print(f"\n=== {label}: HTTP {r.status_code}\n{r.text[:600]}")
    except httpx.HTTPError as e:
        print(f"\n=== {label}: 오류 {type(e).__name__}")


def main() -> int:
    fh = os.environ.get("FINNHUB_API_KEY", "")
    fred = os.environ.get("FRED_API_KEY", "")
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        show(c, "Finnhub forex/rates", "https://finnhub.io/api/v1/forex/rates",
             {"base": "USD", "token": fh})  # fmt: skip
        show(c, "Finnhub quote OANDA:USD_KRW", "https://finnhub.io/api/v1/quote",
             {"symbol": "OANDA:USD_KRW", "token": fh})  # fmt: skip
        show(c, "Frankfurter(ECB) latest", "https://api.frankfurter.app/latest",
             {"from": "USD", "to": "KRW"})  # fmt: skip
        for sid in ("DEXKOUS", "DGS10", "DTWEXBGS", "DCOILWTICO"):
            show(c, f"FRED {sid}", "https://api.stlouisfed.org/fred/series/observations",
                 {"series_id": sid, "api_key": fred, "file_type": "json",
                  "sort_order": "desc", "limit": 2})  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
