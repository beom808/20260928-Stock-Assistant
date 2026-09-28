"""스케줄 잡 진입점.

사용법:
  python -m app.jobs.run us-close
  python -m app.jobs.run kr-watchlist
  python -m app.jobs.run kr-close-and-calendar [--force]

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
    if payload["status"] != "failed":
        await notify_report(
            settings,
            sessions,
            payload["title"],
            f"{payload['generated_at_kst']} 발행",
            f"/report/{report_type}",
        )
    return {"status": payload["status"], "report_type": report_type}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("report_type", choices=REPORT_TYPES)
    p.add_argument("--force", action="store_true", help="휴장일에도 실행")
    a = p.parse_args()
    print(asyncio.run(run_job(a.report_type, a.force)))


if __name__ == "__main__":
    main()
