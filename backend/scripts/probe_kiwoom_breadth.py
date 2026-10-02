"""키움 ka20001(업종현재가요청) 전체 응답 필드 점검 — 상승·하락 종목 수 확인용. 키 미출력."""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE = "https://api.kiwoom.com"
CT = "application/json;charset=UTF-8"


def main() -> int:
    key, secret = os.environ.get("KIWOOM_APP_KEY", ""), os.environ.get("KIWOOM_APP_SECRET", "")
    proxy = os.environ.get("KIWOOM_PROXY_URL") or None
    if not (key and secret):
        print("키움 키 미설정")
        return 0
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
        for body in ({"mrkt_tp": "0", "inds_cd": "001"}, {"mrkt_tp": "1", "inds_cd": "101"}):
            r = c.post(
                f"{BASE}/api/dostk/sect",
                json=body,
                headers={
                    "Content-Type": CT,
                    "authorization": f"Bearer {tok}",
                    "api-id": "ka20001",
                    "cont-yn": "N",
                    "next-key": "",
                },
            )
            print(f"\n=== {body} → HTTP {r.status_code}")
            d = r.json()
            for k, v in d.items():
                if isinstance(v, list):
                    print(f"목록 '{k}' {len(v)}행, 첫 행:", json.dumps(v[:1], ensure_ascii=False))
                else:
                    print(f"{k} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
