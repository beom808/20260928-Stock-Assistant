"""키움 ka10051(업종별투자자순매수요청) 응답 형식 점검(수동). 토큰·키는 출력하지 않는다.

공식 가이드(openapi.kiwoom.com)는 개발 환경에서 열리지 않아, 후보 요청값을 보내
실제 응답(return_msg·필드명·단위)을 확인한 뒤 구현한다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

BASE = "https://api.kiwoom.com"
CT = "application/json;charset=UTF-8"


def main() -> int:
    key, secret = os.environ.get("KIWOOM_APP_KEY", ""), os.environ.get("KIWOOM_APP_SECRET", "")
    proxy = os.environ.get("KIWOOM_PROXY_URL") or None
    if not (key and secret):
        print("키움 키 미설정")
        return 0
    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    with httpx.Client(proxy=proxy, timeout=30) as c:
        r = c.post(
            f"{BASE}/oauth2/token",
            json={"grant_type": "client_credentials", "appkey": key, "secretkey": secret},
            headers={"Content-Type": CT},
        )
        tok = (r.json() or {}).get("token")
        print("토큰 발급:", "성공" if tok else f"실패 HTTP {r.status_code}")
        if not tok:
            return 0
        bodies = [
            {"mrkt_tp": "0", "amt_qty_tp": "0", "base_dt": today, "stex_tp": "3"},
            {"mrkt_tp": "1", "amt_qty_tp": "0", "base_dt": today, "stex_tp": "3"},
            {"mrkt_tp": "0", "amt_qty_tp": "0", "base_dt": today, "stex_tp": "1"},
            {"mrkt_tp": "0", "amt_qty_tp": "0", "base_dt": today},
            {"mrkt_tp": "0", "amt_qty_tp": "0"},
        ]
        for b in bodies:
            r = c.post(
                f"{BASE}/api/dostk/sect",
                json=b,
                headers={
                    "Content-Type": CT,
                    "authorization": f"Bearer {tok}",
                    "api-id": "ka10051",
                    "cont-yn": "N",
                    "next-key": "",
                },
            )
            print(f"\n=== 요청 {b} → HTTP {r.status_code}")
            try:
                d = r.json()
            except ValueError:
                print(r.text[:300])
                continue
            print("return_code:", d.get("return_code"), "| return_msg:", d.get("return_msg"))
            for k, v in d.items():
                if isinstance(v, list):
                    print(f"목록 필드 '{k}': {len(v)}행")
                    for row in v[:2]:
                        print("  ", json.dumps(row, ensure_ascii=False))
                    for row in v:
                        if isinstance(row, dict) and str(row.get("inds_cd", "")) in (
                            "001", "101", "001_AL", "101_AL",
                        ):  # fmt: skip
                            print("  [종합]", json.dumps(row, ensure_ascii=False))
                elif k not in ("return_code", "return_msg"):
                    print(f"필드 '{k}': {str(v)[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
