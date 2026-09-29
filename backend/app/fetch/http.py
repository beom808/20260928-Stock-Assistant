"""외부 API 공통 클라이언트: 캐싱 · 재시도 · 요청 큐잉(레이트리밋) · 일일 한도 · stale fallback.

동작 순서
1) 신선한 캐시(TTL 이내)가 있으면 네트워크 호출 없이 반환
2) 일일 한도 초과 시 → 오래된(stale) 캐시로 대체, 없으면 QuotaExceeded
3) 분당 요청 수를 넘지 않도록 슬라이딩 윈도 큐에서 대기 (asyncio.Lock 로 직렬화)
4) 429 / 5xx / 네트워크 오류는 지수 백오프로 재시도 (Retry-After 헤더 우선)
5) 최종 실패 시 stale 캐시(최대 stale_max_age)로 대체, 없으면 ApiError
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ApiCache, ApiUsage
from app.timeutil import ensure_aware, now_utc

log = logging.getLogger(__name__)

SECRET_PARAM_KEYS = {"token", "apikey", "api_key", "appkey", "appsecret"}


class ApiError(Exception):
    def __init__(self, provider: str, kind: str, message: str) -> None:
        super().__init__(f"[{provider}] {kind}: {message}")
        self.provider = provider
        self.kind = kind  # config | quota | rate_limit | http | network | parse


class QuotaExceeded(ApiError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(provider, "quota", message)


@dataclass
class FetchResult:
    data: Any
    provider: str
    fetched_at: datetime
    from_cache: bool = False
    stale: bool = False


class RateLimiter:
    """슬라이딩 윈도 방식 분당 요청 제한. 초과분은 대기열에서 순서대로 대기."""

    def __init__(
        self,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= 60.0:
                    self._stamps.popleft()
                if len(self._stamps) < self.per_minute:
                    self._stamps.append(now)
                    return
                await self._sleep(60.0 - (now - self._stamps[0]) + 0.05)


def cache_key(provider: str, url: str, params: dict[str, Any] | None) -> str:
    safe = {k: v for k, v in (params or {}).items() if k.lower() not in SECRET_PARAM_KEYS}
    raw = json.dumps([provider, url, sorted(safe.items())], default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiClient:
    def __init__(
        self,
        provider: str,
        sessions: sessionmaker[Session],
        http: httpx.AsyncClient,
        per_minute: int | None = None,
        daily_limit: int | None = None,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        stale_max_age: timedelta = timedelta(days=3),
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.provider = provider
        self.sessions = sessions
        self.http = http
        self.limiter = RateLimiter(per_minute, sleep=sleep or asyncio.sleep) if per_minute else None
        self.daily_limit = daily_limit
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.stale_max_age = stale_max_age
        self._sleep = sleep

    # ── cache / usage ────────────────────────────────────────────────────
    def _read_cache(self, key: str) -> ApiCache | None:
        with self.sessions() as s:
            return s.get(ApiCache, key)

    def _write_cache(self, key: str, body: Any, ttl: timedelta) -> datetime:
        now = now_utc()
        with self.sessions() as s:
            row = s.get(ApiCache, key)
            if row is None:
                row = ApiCache(cache_key=key, provider=self.provider)
                s.add(row)
            row.body = body
            row.fetched_at_utc = now
            row.expires_at_utc = now + ttl
            s.commit()
        return now

    def usage_today(self) -> int:
        with self.sessions() as s:
            row = s.get(ApiUsage, (self.provider, now_utc().date()))
            return row.count if row else 0

    def _bump_usage(self) -> None:
        with self.sessions() as s:
            key = (self.provider, now_utc().date())
            row = s.get(ApiUsage, key)
            if row is None:
                row = ApiUsage(provider=self.provider, usage_date_utc=key[1], count=0)
                s.add(row)
            row.count += 1
            s.commit()

    def _stale_or_raise(self, cached: ApiCache | None, err: ApiError) -> FetchResult:
        if cached is not None:
            fetched = ensure_aware(cached.fetched_at_utc)
            if now_utc() - fetched <= self.stale_max_age:
                log.warning("%s → stale cache 사용 (%s)", err, fetched.isoformat())
                return FetchResult(cached.body, self.provider, fetched, from_cache=True, stale=True)
        raise err

    # ── request ──────────────────────────────────────────────────────────
    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        ttl: timedelta = timedelta(minutes=10),
        use_cache: bool = True,
        cache_extra: dict[str, Any] | None = None,
        cache_if: Callable[[Any], bool] | None = None,
        follow_redirects: bool = False,
    ) -> FetchResult:
        # json_body 는 시크릿이 섞일 수 있어 캐시 키에서 제외한다.
        # 같은 URL 에 본문만 다른 요청(예: 지수 코드)은 cache_extra 로 비밀이 아닌 구분값을 넘긴다.
        key_params = params if json_body is None else None
        if cache_extra:
            key_params = {**(key_params or {}), **cache_extra}
        key = cache_key(self.provider, f"{method} {url}", key_params)
        cached = self._read_cache(key) if use_cache else None
        if cached is not None and ensure_aware(cached.expires_at_utc) > now_utc():
            return FetchResult(
                cached.body, self.provider, ensure_aware(cached.fetched_at_utc), from_cache=True
            )

        if self.daily_limit is not None and self.usage_today() >= self.daily_limit:
            return self._stale_or_raise(
                cached, QuotaExceeded(self.provider, f"일일 한도 {self.daily_limit}회 도달")
            )

        last_err: ApiError | None = None
        for attempt in range(self.max_retries + 1):
            if self.limiter:
                await self.limiter.acquire()
            self._bump_usage()
            try:
                resp = await self.http.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    follow_redirects=follow_redirects,
                )
            except httpx.HTTPError as e:
                last_err = ApiError(self.provider, "network", repr(e))
                await self._backoff(attempt, None)
                continue

            if resp.status_code == 429:
                last_err = ApiError(self.provider, "rate_limit", "HTTP 429")
                await self._backoff(attempt, resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 500:
                last_err = ApiError(self.provider, "http", f"HTTP {resp.status_code}")
                await self._backoff(attempt, None)
                continue
            if resp.status_code >= 400:
                # 인증 오류·플랜 미지원(402/403) 등은 재시도해도 동일 → 즉시 중단
                last_err = ApiError(
                    self.provider, "http", f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                break
            try:
                body = resp.json()
            except ValueError:
                last_err = ApiError(self.provider, "parse", "JSON 파싱 실패")
                break
            # HTTP 200 이어도 본문이 실패(return_code 등)면 캐시하지 않는다 → 다음 호출에서 재시도
            cacheable = use_cache and (cache_if is None or cache_if(body))
            fetched = self._write_cache(key, body, ttl) if cacheable else now_utc()
            return FetchResult(body, self.provider, fetched)

        assert last_err is not None
        return self._stale_or_raise(cached, last_err)

    async def get_json(self, url: str, **kw: Any) -> FetchResult:
        return await self.request_json("GET", url, **kw)

    async def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self.max_retries:
            return
        delay = self.backoff_base * (2**attempt)
        if retry_after:
            try:
                delay = max(delay, min(float(retry_after), 60.0))
            except ValueError:
                pass
        await (self._sleep or asyncio.sleep)(delay)
