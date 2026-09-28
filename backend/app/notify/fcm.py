"""Firebase Cloud Messaging HTTP v1 — 리포트 발행 알림(선택 기능).

동작 조건
- FCM_PROJECT_ID
- 서비스 계정 키: FCM_SERVICE_ACCOUNT_JSON(내용) 또는 FCM_SERVICE_ACCOUNT_FILE(경로)
- google-auth 설치: `pip install "./backend[push]"`
- 구독 토큰은 웹 화면의 '발행 알림 받기' 버튼 → POST /push/register 로 DB(push_tokens)에 저장된다.
- 알림 링크는 전체 https 주소여야 하므로 SITE_URL 을 앞에 붙인다.
- 실패해도 리포트 발행에는 영향을 주지 않는다. 만료된 토큰(UNREGISTERED)은 DB 에서 지운다.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import store

log = logging.getLogger(__name__)
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def fcm_configured(settings: Settings) -> bool:
    return bool(
        settings.fcm_project_id
        and (settings.fcm_service_account_json or settings.fcm_service_account_file)
    )


def _access_token(settings: Settings) -> str:
    from google.auth.transport.requests import Request  # type: ignore[import-not-found]
    from google.oauth2 import service_account  # type: ignore[import-not-found]

    if settings.fcm_service_account_json:
        info = json.loads(settings.fcm_service_account_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    else:
        creds = service_account.Credentials.from_service_account_file(
            settings.fcm_service_account_file, scopes=[SCOPE]
        )
    creds.refresh(Request())
    return creds.token


def absolute_link(settings: Settings, path: str) -> str:
    return f"{settings.site_url.rstrip('/')}/{path.lstrip('/')}"


async def notify_report(
    settings: Settings,
    sessions: sessionmaker[Session],
    title: str,
    body: str,
    path: str,
    http: httpx.AsyncClient | None = None,
) -> int:
    """발송 성공 건수를 돌려준다. 미설정이면 0."""
    if not fcm_configured(settings):
        return 0
    with sessions() as s:
        targets = store.list_push_tokens(s)
    if not targets:
        log.info("FCM: 등록된 구독 토큰 없음")
        return 0
    try:
        token = await asyncio.to_thread(_access_token, settings)
    except Exception as e:  # noqa: BLE001 - 알림 실패는 리포트에 영향 없음
        log.warning("FCM 인증 실패: %s", type(e).__name__)
        return 0
    url = f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send"
    link = absolute_link(settings, path)
    own = http is None
    http = http or httpx.AsyncClient(timeout=10)
    sent = 0
    try:
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
                log.warning("FCM 전송 실패: %s", type(e).__name__)
                continue
            if r.status_code == 200:
                sent += 1
            elif r.status_code in (400, 404) and "UNREGISTERED" in r.text:
                with sessions() as s:
                    store.remove_push_token(s, t)
            else:
                log.warning("FCM 전송 실패: HTTP %s %s", r.status_code, r.text[:200])
    finally:
        if own:
            await http.aclose()
    log.info("FCM: %d/%d 건 발송", sent, len(targets))
    return sent
