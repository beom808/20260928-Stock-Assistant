"""원격 실행(GitHub Actions → Render /jobs) 동작."""

from __future__ import annotations

import httpx
import respx

from app.jobs.remote import trigger

BASE = "https://api.example.test"


async def _nosleep(_):
    return None


@respx.mock
async def test_wakes_server_then_runs_and_reports_status():
    health = respx.get(f"{BASE}/health").mock(
        side_effect=[httpx.ConnectError("sleeping"), httpx.Response(502), httpx.Response(200)]
    )
    run = respx.post(f"{BASE}/jobs/kr-close-and-calendar/run").mock(
        return_value=httpx.Response(
            200, json={"status": "partial", "errors": ["FMP 미설정"], "warnings": []}
        )
    )
    code = await trigger(["kr-close-and-calendar"], True, BASE, "tok", sleep=_nosleep)
    assert code == 0  # partial 은 실패로 보지 않음
    assert health.call_count == 3
    req = run.calls.last.request
    assert req.headers["X-Job-Token"] == "tok" and req.url.params["force"] == "true"


@respx.mock
async def test_failed_status_or_http_error_returns_1():
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200))
    respx.post(f"{BASE}/jobs/kr-close-and-calendar/run").mock(
        return_value=httpx.Response(200, json={"status": "failed", "errors": ["x"]})
    )
    assert await trigger(["kr-close-and-calendar"], False, BASE, "t", sleep=_nosleep) == 1
    respx.post(f"{BASE}/jobs/kr-close-and-calendar/run").mock(
        return_value=httpx.Response(401, text="invalid job token")
    )
    assert await trigger(["kr-close-and-calendar"], False, BASE, "t", sleep=_nosleep) == 1


@respx.mock
async def test_server_never_wakes_raises():
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(503))
    try:
        await trigger(["kr-close-and-calendar"], False, BASE, "t", sleep=_nosleep)
    except RuntimeError as e:
        assert "응답하지 않습니다" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
