"""외부 API 실패 / 한도 초과 시 fallback 동작."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx

from app.db.models import ApiCache
from app.fetch.http import ApiClient, ApiError, QuotaExceeded, RateLimiter
from app.timeutil import now_utc

URL = "https://api.example.test/data"


def make_client(sessions, fake_sleep, **kw):
    return ApiClient("test", sessions, httpx.AsyncClient(), sleep=fake_sleep, **kw)


@respx.mock
async def test_retry_on_429_then_success_respects_retry_after(sessions, fake_sleep):
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    c = make_client(sessions, fake_sleep)
    res = await c.get_json(URL, params={"q": 1})
    assert res.data == {"ok": 1} and not res.stale
    assert route.call_count == 2
    assert fake_sleep.calls == [7.0]


@respx.mock
async def test_fresh_cache_avoids_network(sessions, fake_sleep):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[1]))
    c = make_client(sessions, fake_sleep)
    await c.get_json(URL, params={"q": 1})
    res = await c.get_json(URL, params={"q": 1})
    assert res.from_cache and route.call_count == 1


@respx.mock
async def test_5xx_exhausts_retries_then_uses_stale_cache(sessions, fake_sleep):
    c = make_client(sessions, fake_sleep, max_retries=2)
    respx.get(URL).mock(return_value=httpx.Response(200, json={"v": "old"}))
    await c.get_json(URL, params={"q": 1}, ttl=timedelta(seconds=-1))  # 즉시 만료된 캐시
    respx.get(URL).mock(return_value=httpx.Response(503))
    res = await c.get_json(URL, params={"q": 1})
    assert res.stale and res.data == {"v": "old"}
    assert fake_sleep.calls == [1.0, 2.0]  # 지수 백오프


@respx.mock
async def test_network_error_without_cache_raises(sessions, fake_sleep):
    respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
    c = make_client(sessions, fake_sleep, max_retries=1)
    with pytest.raises(ApiError) as ei:
        await c.get_json(URL)
    assert ei.value.kind == "network"


@respx.mock
async def test_4xx_is_not_retried(sessions, fake_sleep):
    route = respx.get(URL).mock(return_value=httpx.Response(403, text="plan required"))
    c = make_client(sessions, fake_sleep)
    with pytest.raises(ApiError):
        await c.get_json(URL)
    assert route.call_count == 1 and fake_sleep.calls == []


@respx.mock
async def test_daily_quota_blocks_calls_and_falls_back(sessions, fake_sleep):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"n": 1}))
    c = make_client(sessions, fake_sleep, daily_limit=1)
    await c.get_json(URL, params={"a": 1}, ttl=timedelta(seconds=-1))
    # 한도 도달 → 같은 키는 stale 캐시, 다른 키는 QuotaExceeded
    res = await c.get_json(URL, params={"a": 1})
    assert res.stale
    with pytest.raises(QuotaExceeded):
        await c.get_json(URL, params={"a": 2})
    assert route.call_count == 1


@respx.mock
async def test_stale_cache_too_old_is_not_used(sessions, fake_sleep):
    c = make_client(sessions, fake_sleep, max_retries=0, stale_max_age=timedelta(hours=1))
    respx.get(URL).mock(return_value=httpx.Response(200, json={"v": 1}))
    await c.get_json(URL, ttl=timedelta(seconds=-1))
    with sessions() as s:
        row = s.query(ApiCache).one()
        row.fetched_at_utc = now_utc() - timedelta(hours=5)
        s.commit()
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ApiError):
        await c.get_json(URL)


def test_cache_key_excludes_secrets():
    from app.fetch.http import cache_key

    assert cache_key("p", URL, {"q": 1, "token": "A"}) == cache_key(
        "p", URL, {"q": 1, "token": "B"}
    )


async def test_rate_limiter_queues_excess_requests(fake_sleep):
    t = {"now": 0.0}

    async def sleep(secs: float) -> None:
        fake_sleep.calls.append(secs)
        t["now"] += secs

    lim = RateLimiter(2, clock=lambda: t["now"], sleep=sleep)
    await lim.acquire()
    await lim.acquire()
    await lim.acquire()  # 3번째는 윈도가 비워질 때까지 대기
    assert len(fake_sleep.calls) == 1 and fake_sleep.calls[0] == pytest.approx(60.05)
