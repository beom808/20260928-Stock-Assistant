"""저장(store) 계층: 리포트/잡 로그 CRUD."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobRun, PushToken, Report
from app.timeutil import now_utc


def upsert_report(
    s: Session, report_type: str, report_date_kst: date, payload: dict, status: str
) -> Report:
    row = s.scalar(
        select(Report).where(
            Report.report_type == report_type, Report.report_date_kst == report_date_kst
        )
    )
    now = now_utc()
    if row is None:
        row = Report(
            report_type=report_type,
            report_date_kst=report_date_kst,
            generated_at_utc=now,
            status=status,
            revision=1,
            payload=payload,
        )
        s.add(row)
    else:
        row.generated_at_utc = now
        row.status = status
        row.revision += 1
        row.payload = payload
    s.commit()
    return row


def get_report(s: Session, report_type: str, report_date_kst: date | None = None) -> Report | None:
    q = select(Report).where(Report.report_type == report_type)
    if report_date_kst is not None:
        q = q.where(Report.report_date_kst == report_date_kst)
    return s.scalar(q.order_by(Report.report_date_kst.desc()).limit(1))


def list_reports(
    s: Session, report_type: str | None, date_from: date | None, date_to: date | None, limit: int
) -> list[Report]:
    q = select(Report)
    if report_type:
        q = q.where(Report.report_type == report_type)
    if date_from:
        q = q.where(Report.report_date_kst >= date_from)
    if date_to:
        q = q.where(Report.report_date_kst <= date_to)
    return list(s.scalars(q.order_by(Report.report_date_kst.desc()).limit(limit)))


def start_job(s: Session, report_type: str) -> JobRun:
    run = JobRun(report_type=report_type, started_at_utc=now_utc(), status="running")
    s.add(run)
    s.commit()
    return run


def finish_job(s: Session, run: JobRun, status: str, message: str | None = None) -> None:
    run.status = status
    run.message = message
    run.finished_at_utc = now_utc()
    s.commit()


def add_push_token(s: Session, token: str, at: datetime | None = None) -> None:
    if s.get(PushToken, token) is None:
        s.add(PushToken(token=token, created_at_utc=at or now_utc()))
        s.commit()


def count_push_tokens(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(PushToken)) or 0)


def list_push_tokens(s: Session) -> list[str]:
    return list(s.scalars(select(PushToken.token)))


def remove_push_token(s: Session, token: str) -> None:
    row = s.get(PushToken, token)
    if row is not None:
        s.delete(row)
        s.commit()
