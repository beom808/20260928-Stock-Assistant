"""FastAPI 앱 — REST 엔드포인트.

GET  /report/us-close                 기능 A (기본: 최신, ?date=YYYY-MM-DD 로 일자 조회)
GET  /report/kr-watchlist             기능 B
GET  /report/kr-close-and-calendar    기능 C
GET  /reports                         리포트 이력 목록 (?type=&date_from=&date_to=)
POST /jobs/{report_type}/run          스케줄러 트리거 (X-Job-Token 헤더 필요)
POST /push/register                   FCM 웹푸시 토큰 등록(구독). replaces 로 이전 토큰 교체
POST /push/unregister                 구독 취소(토큰 삭제)
GET  /push/count                      구독자 수(등록된 기기 토큰 수)
GET  /health
"""

from __future__ import annotations

import hmac
import logging
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import store
from app.db.session import get_session
from app.disclaimer import DISCLAIMER_KO
from app.jobs.run import run_job
from app.reports.builders import KR_CLOSE, KR_WATCHLIST, REPORT_TYPES, US_CLOSE
from app.timeutil import fmt_kst

logging.basicConfig(level=logging.INFO)
settings = get_settings()
app = FastAPI(title="Stock Assistant API", version="0.1.0", description=DISCLAIMER_KO)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]
DateQ = Annotated[date | None, Query(description="KST 기준일 YYYY-MM-DD (미지정 시 최신)")]


def _report_response(s: Session, report_type: str, d: date | None) -> dict:
    row = store.get_report(s, report_type, d)
    if row is None:
        raise HTTPException(
            404,
            detail={
                "message": "해당 일자의 리포트가 없습니다.",
                "report_type": report_type,
                "date": d.isoformat() if d else None,
                "disclaimer": DISCLAIMER_KO,
            },
        )
    return row.payload | {"revision": row.revision, "stored_at_kst": fmt_kst(row.generated_at_utc)}


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/report/us-close")
def us_close(s: SessionDep, date: DateQ = None) -> dict:
    return _report_response(s, US_CLOSE, date)


@app.get("/report/kr-watchlist")
def kr_watchlist(s: SessionDep, date: DateQ = None) -> dict:
    return _report_response(s, KR_WATCHLIST, date)


@app.get("/report/kr-close-and-calendar")
def kr_close(s: SessionDep, date: DateQ = None) -> dict:
    return _report_response(s, KR_CLOSE, date)


@app.get("/reports")
def reports(
    s: SessionDep,
    type: str | None = Query(
        None, pattern="^(us-close|kr-watchlist|kr-close-and-calendar)$"
    ),  # noqa: A002
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(60, ge=1, le=365),
) -> dict:
    rows = store.list_reports(s, type, date_from, date_to, limit)
    return {
        "disclaimer": DISCLAIMER_KO,
        "items": [
            {
                "report_type": r.report_type,
                "report_date_kst": r.report_date_kst.isoformat(),
                "generated_at_kst": fmt_kst(r.generated_at_utc),
                "status": r.status,
                "revision": r.revision,
            }
            for r in rows
        ],
    }


def _check_token(x_job_token: str | None) -> None:
    expected = settings.job_trigger_token
    if not expected or not x_job_token or not hmac.compare_digest(expected, x_job_token):
        raise HTTPException(401, "invalid job token")


@app.post("/jobs/{report_type}/run")
async def trigger(
    report_type: str,
    force: bool = False,
    x_job_token: Annotated[str | None, Header()] = None,
) -> dict:
    _check_token(x_job_token)
    if report_type not in REPORT_TYPES:
        raise HTTPException(404, "unknown report type")
    return await run_job(report_type, force=force)


class PushRegister(BaseModel):
    token: str
    # 같은 기기에서 토큰이 바뀐 경우 이전 토큰(기기당 1명으로 세기 위해 교체)
    replaces: str | None = None


class PushUnregister(BaseModel):
    token: str


def _valid_token(token: str) -> None:
    if not (20 <= len(token) <= 512):
        raise HTTPException(400, "invalid token")


@app.post("/push/register")
def push_register(body: PushRegister, s: SessionDep) -> dict:
    _valid_token(body.token)
    if body.replaces and body.replaces != body.token and 20 <= len(body.replaces) <= 512:
        store.remove_push_token(s, body.replaces)
    store.add_push_token(s, body.token)
    return {"ok": True, "count": store.count_push_tokens(s)}


@app.post("/push/unregister")
def push_unregister(body: PushUnregister, s: SessionDep) -> dict:
    _valid_token(body.token)
    store.remove_push_token(s, body.token)
    return {"ok": True, "count": store.count_push_tokens(s)}


@app.get("/push/count")
def push_count(s: SessionDep) -> dict:
    """구독자 수 = 등록된 기기(브라우저) 토큰 수. 같은 기기의 다른 브라우저는 따로 센다."""
    return {"count": store.count_push_tokens(s)}
