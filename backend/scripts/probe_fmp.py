"""FMP 무료 플랜에서 지수 일별 종가(EOD) 엔드포인트가 되는지 확인(수동 점검, AI 호출 없음).

FMP_API_KEY 환경변수 필요. 키는 파라미터로만 쓰고 출력하지 않는다.
"""

from __future__ import annotations

import os
import sys

import httpx

BASE = "https://financialmodelingprep.com/stable"
PATHS = ["/historical-price-eod/light", "/historical-price-eod/full", "/quote"]


def main() -> int:
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        print("FMP_API_KEY 없음")
        return 1
    with httpx.Client(timeout=30) as c:
        for sym in ("USDKRW", "^TNX", "DX-Y.NYB", "CLUSD", "^VIX", "ES=F", "NQ=F"):
            r = c.get(BASE + "/quote", params={"symbol": sym, "apikey": key})
            print(f"\n=== {sym} /quote: HTTP {r.status_code}")
            print(r.text[:500])
        for sym in ("^GSPC", "^IXIC", "^DJI"):
            for path in PATHS:
                params = {"symbol": sym, "apikey": key}
                if "historical" in path:
                    params |= {"from": "2026-09-23", "to": "2026-09-28"}
                r = c.get(BASE + path, params=params)
                print(f"\n=== {sym} {path}: HTTP {r.status_code}")
                print(r.text[:700])
    return 0


if __name__ == "__main__":
    sys.exit(main())
