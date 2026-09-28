"""스케줄 잡 진입점.

사용법:
  python -m app.jobs.run us-close kr-watchlist      # 07:00 KST: 여러 리포트를 순서대로 실행
  python -m app.jobs.run kr-close-and-calendar [--force]

하나라도 status=failed 이거나 예외가 나면 종료 코드 1 → 크론 실행이 '실패'로 표시된다.

클라우드 크론(UTC)은 이 스크립트를 직접 실행하거나 POST /jobs/{type}/run 을 호출한다.
KST 는 서머타임이 없으므로 UTC 크론 식은 고정이다 (infra/scheduler.md 참고).
- 07:00 KST (월~금) = 22:00 UTC (일~목)
- 15:30 KST 장 마감 → 종가 확정 여유를 두고 15:40 KST(06:40 UTC) 실행 권장
한국 휴장일(XKRX)에는 --force 없이는 건너뛴다.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.config import Settings, get_settings
from app.db import store
from app.db.session import session_factory
from app.fetch.providers import build_providers
from app.llm.claude import ClaudeAnalyst
from app.notify.fcm import notify_report
from app.reports.builders import REPORT_TYPES, generate
from app.timeutil import is_kr_trading_day, kst_today, now_utc

log = logging.getLogger(__name__)


async def run_job(report_type: str, force: bool = False, settings: Settings | None = None) -> dict:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"report_type must be one of {REPORT_TYPES}")
    settings = settings or get_settings()
    sessions = session_factory()
    with sessions() as s:
        run = store.start_job(s, report_type)
    today = kst_today(now_utc())
    if not force and not is_kr_trading_day(today):
        with sessions() as s:
            store.finish_job(s, s.merge(run), "skipped", f"{today} 한국 휴장일")
        return {"status": "skipped", "reason": f"{today} is not a KRX trading day"}

    providers = build_providers(settings, sessions)
    analyst = ClaudeAnalyst(settings.anthropic_api_key, settings.anthropic_model)
    try:
        payload = await generate(report_type, settings, providers, analyst, sessions)
    except Exception as e:
        with sessions() as s:
            store.finish_job(s, s.merge(run), "failed", repr(e)[:2000])
        raise
    finally:
        await providers.aclose()
    with sessions() as s:
        store.finish_job(
            s, s.merge(run), payload["status"], "; ".join(payload["errors"])[:2000] or None
        )
    # 실행 로그(GitHub Actions 등)에서 원인을 바로 볼 수 있도록 오류·참고 사항을 출력
    # (API 오류 메시지만 담기며 키·비밀번호는 포함되지 않는다)
    for e in payload["errors"]:
        log.error("[%s] %s", report_type, e)
    for w in payload["warnings"]:
        log.warning("[%s] %s", report_type, w)
    if payload["status"] != "failed":
        await notify_report(
            settings,
            sessions,
            payload["title"],
            f"{payload['generated_at_kst']} 발행",
            f"/report/{report_type}",
        )
    return {"status": payload["status"], "report_type": report_type}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("report_types", nargs="+", choices=REPORT_TYPES)
    p.add_argument("--force", action="store_true", help="휴장일에도 실행")
    a = p.parse_args(argv)
    failed = False
    for rt in a.report_types:
        try:
            result = asyncio.run(run_job(rt, a.force))
        except Exception:  # noqa: BLE001 - 다음 리포트는 계속 시도하고 종료 코드로 알린다
            log.exception("%s 생성 중 예외", rt)
            failed = True
            continue
        print(result)
        failed |= result.get("status") == "failed"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
