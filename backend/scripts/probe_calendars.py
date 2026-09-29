"""공식 경제일정 출처의 실제 응답 형식을 확인하는 점검 스크립트 (GitHub Actions 수동 실행용).

개발 환경에서는 bea.gov / federalreserve.gov / api.stlouisfed.org 에 접근할 수 없어 형식을 직접
볼 수 없다. 1차 점검 결과: BLS 는 자동 요청 차단(403), BEA JSON·연준 calendar.json 은 정상.
"""

from __future__ import annotations

import collections
import json
import sys

import httpx

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0"


def main() -> int:
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        bea = c.get("https://apps.bea.gov/API/signup/release_dates.json").json()
        print("BEA 발표 종류:")
        for name, v in bea.items():
            if not isinstance(v, dict):
                print(f"  (dict 아님) {name}: {str(v)[:120]}")
                continue
            future = [d for d in v.get("release_dates", []) if d >= "2026-09-01"]
            print(f"  {name}: {future[:3]}")

        r = c.get("https://www.federalreserve.gov/json/calendar.json")
        ev = json.loads(r.content.decode("utf-8-sig"))["events"]
        print("\n연준 calendar.json 이벤트 수:", len(ev))
        print("type 분포:", collections.Counter(e.get("type") for e in ev).most_common())
        print("키 종류:", sorted({k for e in ev for k in e}))
        fomc = [e for e in ev if "FOMC" in (e.get("type", "") + e.get("title", ""))]
        print(f"\nFOMC 관련 {len(fomc)}건 (앞 15건):")
        for e in fomc[:15]:
            print(" ", json.dumps(e, ensure_ascii=False)[:300])
        soon = [e for e in ev if e.get("month") in ("2026-09", "2026-10")]
        print(f"\n2026-09~10 이벤트 {len(soon)}건 중 Speeches 제외:")
        for e in soon:
            if e.get("type") != "Speeches":
                print(" ", json.dumps(e, ensure_ascii=False)[:300])

        r = c.get(
            "https://api.stlouisfed.org/fred/releases/dates",
            params={"file_type": "json", "api_key": "invalid"},
        )
        print("\nFRED 접근 확인(잘못된 키):", r.status_code, r.text[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
