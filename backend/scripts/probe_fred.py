"""FRED 발표명 확인(수동 점검): 코드의 FRED_RELEASES 이름이 실제 release_name 과 일치하는지.

FRED_API_KEY 환경변수 필요. 키는 URL 파라미터로만 쓰고 출력하지 않는다.
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.fetch.official import FRED_RELEASES  # noqa: E402

WORDS = ("consumer price", "employment situation", "producer price", "retail",
         "jobless", "unemployment insurance", "job openings")  # fmt: skip


def main() -> int:
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        print("FRED_API_KEY 없음")
        return 1
    names: list[str] = []
    offset = 0
    with httpx.Client(timeout=30) as c:
        while True:
            r = c.get(
                "https://api.stlouisfed.org/fred/releases",
                params={"api_key": key, "file_type": "json", "limit": 1000, "offset": offset},
            )
            r.raise_for_status()
            rel = r.json().get("releases", [])
            names += [x["name"] for x in rel]
            if len(rel) < 1000:
                break
            offset += 1000
        print(f"FRED 발표 {len(names)}개")
        for n in sorted(names):
            if any(w in n.lower() for w in WORDS):
                print("  후보:", n)
        for n in FRED_RELEASES:
            print(("  ✅ 일치: " if n in names else "  ❌ 없음: ") + n)
        r = c.get(
            "https://api.stlouisfed.org/fred/releases/dates",
            params={"api_key": key, "file_type": "json", "realtime_start": "2026-09-28",
                    "realtime_end": "2026-11-30", "include_release_dates_with_no_data": "true",
                    "limit": 1000},
        )  # fmt: skip
        for x in r.json().get("release_dates", []):
            if x.get("release_name") in FRED_RELEASES:
                print("  예정:", x["date"], x["release_name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
