"""원격 실행: 리포트 생성을 Render 서버(POST /jobs/{type}/run)에게 맡긴다.

왜 필요한가
- 키움 REST API 는 '등록된 IP' 에서 온 요청만 허용한다(오류 8050).
- GitHub Actions 러너는 실행마다 IP 가 바뀌어 등록할 수 없다.
- Render 서버는 지역별로 정해진 외부 IP 를 쓴다(대시보드 Connect → Outbound).
- 그래서 키움이 필요한 리포트는 GitHub Actions 가 Render 를 '호출'만 하고 실행은 Render 에서 한다.

사용법:
  RENDER_API_URL=https://... RENDER_JOB_TOKEN=... \\
    python -m app.jobs.remote kr-close-and-calendar [--force]
무료 서버는 잠들어 있을 수 있으므로 /health 로 먼저 깨운 뒤 실행 요청을 보낸다.
하나라도 실패(status=failed / HTTP 오류)면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable

import httpx

from app.reports.builders import REPORT_TYPES

log = logging.getLogger(__name__)

WAKE_ATTEMPTS = 12  # 10초 간격 → 최대 약 2분 대기(무료 서버 기동 시간 여유)
WAKE_INTERVAL = 10.0
RUN_TIMEOUT = httpx.Timeout(600.0, connect=30.0)


async def wake(
    http: httpx.AsyncClient,
    base: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    last = ""
    for _ in range(WAKE_ATTEMPTS):
        try:
            r = await http.get(f"{base}/health", timeout=60.0)
            if r.status_code == 200:
                return
            last = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            last = repr(e)
        await sleep(WAKE_INTERVAL)
    raise RuntimeError(f"Render 서버가 응답하지 않습니다: {last}")


async def trigger(
    report_types: list[str],
    force: bool,
    base: str,
    token: str,
    http: httpx.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    own = http is None
    http = http or httpx.AsyncClient()
    failed = False
    try:
        await wake(http, base, sleep)
        for rt in report_types:
            r = await http.post(
                f"{base}/jobs/{rt}/run",
                params={"force": str(force).lower()},
                headers={"X-Job-Token": token},
                timeout=RUN_TIMEOUT,
            )
            if r.status_code != 200:
                log.error("[%s] 원격 실행 실패: HTTP %s %s", rt, r.status_code, r.text[:300])
                failed = True
                continue
            result = r.json()
            for e in result.get("errors", []):
                log.error("[%s] %s", rt, e)
            for w in result.get("warnings", []):
                log.warning("[%s] %s", rt, w)
            print({"status": result.get("status"), "report_type": rt, "remote": True})
            failed |= result.get("status") == "failed"
    finally:
        if own:
            await http.aclose()
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("report_types", nargs="+", choices=REPORT_TYPES)
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    base = os.environ.get("RENDER_API_URL", "").rstrip("/")
    token = os.environ.get("RENDER_JOB_TOKEN", "")
    if not (base and token):
        log.error("RENDER_API_URL / RENDER_JOB_TOKEN 이 필요합니다.")
        return 1
    try:
        return asyncio.run(trigger(a.report_types, a.force, base, token))
    except RuntimeError as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
