"""FCM 발행 알림: 미설정 시 무동작, 절대 링크, 만료 토큰 정리."""

from __future__ import annotations

import json

import httpx
import respx

from app.config import Settings
from app.db import store
from app.notify import fcm

URL = "https://fcm.googleapis.com/v1/projects/proj-1/messages:send"


def st(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


async def test_not_configured_sends_nothing(sessions):
    assert await fcm.notify_report(st(), sessions, "t", "b", "/report/us-close") == 0


def test_absolute_link():
    assert fcm.absolute_link(st(), "/report/us-close") == (
        "https://stockassistant2.netlify.app/report/us-close"
    )
    assert (
        fcm.absolute_link(st(site_url="https://x.test/"), "report/a") == "https://x.test/report/a"
    )


@respx.mock
async def test_sends_and_removes_unregistered_tokens(sessions, monkeypatch):
    monkeypatch.setattr(fcm, "_access_token", lambda settings: "ACCESS")
    with sessions() as s:
        store.add_push_token(s, "tok-good-" + "x" * 20)
        store.add_push_token(s, "tok-dead-" + "x" * 20)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)["message"]
        assert request.headers["Authorization"] == "Bearer ACCESS"
        assert body["webpush"]["fcm_options"]["link"].startswith("https://")
        if body["token"].startswith("tok-dead"):
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}, text="UNREGISTERED")
        return httpx.Response(200, json={"name": "projects/proj-1/messages/1"})

    respx.post(URL).mock(side_effect=handler)
    settings = st(fcm_project_id="proj-1", fcm_service_account_json='{"type": "service_account"}')
    sent = await fcm.notify_report(settings, sessions, "리포트", "발행", "/report/us-close")
    assert sent == 1
    with sessions() as s:
        assert store.list_push_tokens(s) == ["tok-good-" + "x" * 20]


async def test_auth_failure_is_swallowed(sessions, monkeypatch):
    def boom(settings):
        raise ValueError("bad key")

    monkeypatch.setattr(fcm, "_access_token", boom)
    with sessions() as s:
        store.add_push_token(s, "tok-" + "y" * 30)
    settings = st(fcm_project_id="p", fcm_service_account_json="{}")
    assert await fcm.notify_report(settings, sessions, "t", "b", "/x") == 0


@respx.mock
async def test_failures_are_logged_with_fingerprint_not_token(sessions, monkeypatch, caplog):
    """실패한 구독은 토큰 원문 대신 해시 앞 8자와 사유로 남기고, 일시 오류로는 삭제하지 않는다."""
    import logging

    monkeypatch.setattr(fcm, "_access_token", lambda settings: "ACCESS")
    flaky, dead = "tok-flaky-" + "x" * 20, "tok-dead-" + "x" * 20
    with sessions() as s:
        store.add_push_token(s, flaky)
        store.add_push_token(s, dead)

    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["message"]["token"] == dead:
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}, text="UNREGISTERED")
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})

    respx.post(URL).mock(side_effect=handler)
    settings = st(fcm_project_id="proj-1", fcm_service_account_json='{"type": "service_account"}')
    with caplog.at_level(logging.INFO, logger="app.notify.fcm"):
        assert await fcm.notify_report(settings, sessions, "t", "b", "/x") == 0
    text = caplog.text
    assert fcm.fingerprint(flaky) in text and "UNAVAILABLE" in text
    assert fcm.fingerprint(dead) in text and "구독 삭제" in text
    assert flaky not in text and dead not in text  # 토큰 원문은 로그에 없다
    with sessions() as s:
        assert store.list_push_tokens(s) == [flaky]  # 일시 오류(503)는 구독을 지우지 않는다
