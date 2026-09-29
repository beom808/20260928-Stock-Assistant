"""공식 경제일정 출처의 실제 응답 형식을 확인하는 점검 스크립트 (GitHub Actions 수동 실행용).

개발 환경에서는 bls.gov / bea.gov / federalreserve.gov 에 접근할 수 없어 형식을 직접 볼 수 없다.
각 URL 의 HTTP 상태·Content-Type·앞부분과, 안내 페이지에 있는 .ics/.json 링크를 출력한다.
"""

from __future__ import annotations

import re
import sys

import httpx

UA = {
    "browser": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36",
    "bot": "stock-assistant/1.0 (+https://github.com/beom808/20260928-Stock-Assistant)",
}
PAGES = [
    "https://www.bls.gov/help/hlpical.htm",
    "https://www.bls.gov/schedule/news_release/cpi.htm",
    "https://www.bea.gov/news/schedule/icalendar",
    "https://www.bea.gov/news/schedule",
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
]
CANDIDATES = [
    "https://www.bls.gov/schedule/news_release/bls.ics",
    "https://apps.bea.gov/API/signup/release_dates.json",
    "https://www.federalreserve.gov/json/calendar.json",
]
LINK = re.compile(r"""href=["']([^"']+\.(?:ics|json)[^"']*)["']""", re.I)


def show(c: httpx.Client, url: str, n: int = 1500) -> str:
    try:
        r = c.get(url)
    except httpx.HTTPError as e:
        print(f"\n=== {url}\n  오류: {type(e).__name__}: {e}")
        return ""
    ctype = r.headers.get("content-type")
    print(f"\n=== {url}\n  HTTP {r.status_code}  {ctype}  {len(r.content)}B")
    print("  final:", r.url)
    print(r.text[:n])
    return r.text if r.status_code == 200 else ""


def main() -> int:
    found: set[str] = set()
    for label, ua in UA.items():
        print(f"\n########## User-Agent: {label}")
        with httpx.Client(headers={"User-Agent": ua}, timeout=20, follow_redirects=True) as c:
            for p in PAGES:
                html = show(c, p, 300)
                for href in LINK.findall(html):
                    found.add(str(httpx.URL(p).join(href)))
    print("\n########## 안내 페이지에서 찾은 .ics/.json 링크:")
    for u in sorted(found):
        print(" ", u)
    opts = {"headers": {"User-Agent": UA["browser"]}, "timeout": 20, "follow_redirects": True}
    with httpx.Client(**opts) as c:
        for u in list(sorted(found))[:8] + CANDIDATES:
            show(c, u, 2500)
    return 0


if __name__ == "__main__":
    sys.exit(main())
