"""스케줄 잡 진입점.

사용법:
  python -m app.jobs.run us-close kr-watchlist      # 07:00 KST: 여러 리포트를 순서대로 실행
  python -m app.jobs.run kr-close-and-calendar [--force]
  python -m app.jobs.run kr-close-and-calendar --dry-run   # 테스트: 저장·알림 없이 결과만 출력

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
import json
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


def _dry_run_summary(payload: dict) -> str:
    """테스트 실행 결과 요약(로그 출력용). 키·비밀번호는 payload 에 없다."""
    data = payload.get("data", {})
    out = {
        "status": payload.get("status"),
        "sources": [s.get("name") for s in payload.get("sources", [])],
        "indices": [
            {k: i.get(k) for k in ("name", "close", "change", "change_pct", "provider", "error")}
            for i in data.get("indices", [])
        ],
        "issue_method": data.get("issue_method"),
        "issues": [
            {k: i.get(k) for k in ("title", "summary", "summary_origin", "url")}
            for i in data.get("issues", [])
        ],
        "calendar_rows": [
            {k: r.get(k) for k in ("event", "kind", "et", "kst", "provider")}
            for r in (data.get("us_calendar") or {}).get("rows", [])
        ],
    }
    return json.dumps(out, ensure_ascii=False, indent=1)


async def run_job(
    report_type: str,
    force: bool = False,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> dict:
    """dry_run=True: 리포트·실행 이력을 저장하지 않고 알림도 보내지 않는다(결과는 로그로만)."""
    if report_type not in REPORT_TYPES:
        raise ValueError(f"report_type must be one of {REPORT_TYPES}")
    settings = settings or get_settings()
    sessions = session_factory()
    run = None
    if not dry_run:
        with sessions() as s:
            run = store.start_job(s, report_type)
    today = kst_today(now_utc())
    if not force and not is_kr_trading_day(today):
        if run is not None:
            with sessions() as s:
                store.finish_job(s, s.merge(run), "skipped", f"{today} 한국 휴장일")
        return {"status": "skipped", "reason": f"{today} is not a KRX trading day"}

    providers = build_providers(settings, sessions)
    analyst = ClaudeAnalyst(settings.anthropic_api_key, settings.anthropic_model)
    try:
        payload = await generate(
            report_type, settings, providers, analyst, sessions, save=not dry_run
        )
    except Exception as e:
        if run is not None:
            with sessions() as s:
                store.finish_job(s, s.merge(run), "failed", repr(e)[:2000])
        raise
    finally:
        await providers.aclose()
    # 실행 로그(GitHub Actions 등)에서 원인을 바로 볼 수 있도록 오류·참고 사항을 출력
    # (API 오류 메시지만 담기며 키·비밀번호는 포함되지 않는다)
    for e in payload["errors"]:
        log.error("[%s] %s", report_type, e)
    for w in payload["warnings"]:
        log.warning("[%s] %s", report_type, w)
    result = {
        "status": payload["status"],
        "report_type": report_type,
        "errors": payload["errors"],
        "warnings": payload["warnings"],
    }
    if run is None:  # dry_run
        log.info("[%s] 테스트 실행(저장 안 함) 결과:\n%s", report_type, _dry_run_summary(payload))
        return result | {"dry_run": True}
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
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("report_types", nargs="+", choices=REPORT_TYPES)
    p.add_argument("--force", action="store_true", help="휴장일에도 실행")
    p.add_argument("--dry-run", action="store_true", help="저장·알림 없이 결과만 출력(테스트)")
    a = p.parse_args(argv)
    failed = False
    for rt in a.report_types:
        try:
            result = asyncio.run(run_job(rt, a.force, dry_run=a.dry_run))
        except Exception:  # noqa: BLE001 - 다음 리포트는 계속 시도하고 종료 코드로 알린다
            log.exception("%s 생성 중 예외", rt)
            failed = True
            continue
        print(result)
        failed |= result.get("status") == "failed"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
