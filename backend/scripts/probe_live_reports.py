"""배포된 API 의 최신 리포트 요약(수동 점검). 공개 데이터만 출력."""

from __future__ import annotations

import json
import sys

import httpx

API = "https://stock-assistant-api-7oz1.onrender.com"


def main() -> int:
    with httpx.Client(timeout=90) as c:
        for rt in ("us-close", "kr-watchlist", "kr-close-and-calendar"):
            r = c.get(f"{API}/report/{rt}")
            print(f"\n=== {rt}: HTTP {r.status_code}")
            if r.status_code != 200:
                continue
            p = r.json()
            d = p.get("data", {})
            print(p.get("title"), "|", p.get("generated_at_kst"), "|", p.get("status"))
            for i in d.get("indices", []):
                print(" 지수", i.get("name"), i.get("close"), i.get("change"), i.get("change_pct"),
                      i.get("provider"))  # fmt: skip
            if d.get("fx"):
                print(" 환율", json.dumps(d["fx"], ensure_ascii=False))
            for m in d.get("macro") or []:
                print(" 매크로", m.get("name"), m.get("value"), m.get("change"), m.get("date"))
            if rt == "kr-watchlist":
                print(" method", d.get("method"), "weights", d.get("weights"))
                for s in d.get("sectors", []):
                    print(" 섹터", s.get("kr_sector"))
                    for co in s.get("companies", []):
                        print("   ", co.get("name"), co.get("score"), co.get("label"),
                              co.get("scores"), "|", co.get("llm_rationale"))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
