"""Firebase Cloud Messaging HTTP v1 — 리포트 발행 알림(선택 기능).

FCM_PROJECT_ID, FCM_SERVICE_ACCOUNT_FILE 이 설정되고 google-auth 가 설치된 경우에만 동작.
실패해도 리포트 발행에는 영향을 주지 않는다.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import store

log = logging.getLogger(__name__)
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _access_token(sa_file: str) -> str:
    from google.auth.transport.requests import Request  # type: ignore[import-not-found]
    from google.oauth2 import service_account  # type: ignore[import-not-found]

    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token


async def notify_report(
    settings: Settings, sessions: sessionmaker[Session], title: str, body: str, link: str
) -> int:
    if not (settings.fcm_project_id and settings.fcm_service_account_file):
        return 0
    try:
        token = await asyncio.to_thread(_access_token, settings.fcm_service_account_file)
    except Exception as e:  # noqa: BLE001 - 알림 실패는 리포트에 영향 없음
        log.warning("FCM 인증 실패: %s", e)
        return 0
    with sessions() as s:
        targets = store.list_push_tokens(s)
    url = f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send"
    sent = 0
    async with httpx.AsyncClient(timeout=10) as http:
        for t in targets:
            msg = {
                "message": {
                    "token": t,
                    "notification": {"title": title, "body": body},
                    "webpush": {"fcm_options": {"link": link}},
                }
            }
            try:
                r = await http.post(url, json=msg, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as e:
                log.warning("FCM 전송 실패: %s", e)
                continue
            if r.status_code == 200:
                sent += 1
            elif r.status_code in (400, 404) and "UNREGISTERED" in r.text:
                with sessions() as s:
                    store.remove_push_token(s, t)
    return sent
