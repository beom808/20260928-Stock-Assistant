"""설정으로부터 공급자별 fetcher 묶음을 생성."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.fetch.finnhub import FinnhubFetcher
from app.fetch.fmp import FmpFetcher
from app.fetch.http import ApiClient
from app.fetch.kis import KisFetcher
from app.fetch.naver import NaverNewsFetcher


@dataclass
class Providers:
    finnhub: FinnhubFetcher
    fmp: FmpFetcher
    kis: KisFetcher
    naver: NaverNewsFetcher
    http: httpx.AsyncClient

    async def aclose(self) -> None:
        await self.http.aclose()


def build_providers(
    settings: Settings, sessions: sessionmaker[Session], http: httpx.AsyncClient | None = None
) -> Providers:
    http = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))
    fh = ApiClient("finnhub", sessions, http, per_minute=settings.finnhub_rate_per_min)
    fmp = ApiClient("fmp", sessions, http, per_minute=30, daily_limit=settings.fmp_daily_limit)
    # KIS 는 초당 호출 제한이 있어 분당으로 보수적으로 제한
    kis = ApiClient("kis", sessions, http, per_minute=60)
    nv = ApiClient("naver", sessions, http, per_minute=60, daily_limit=settings.naver_daily_limit)
    return Providers(
        finnhub=FinnhubFetcher(fh, settings.finnhub_api_key, settings.finnhub_base_url),
        fmp=FmpFetcher(
            fmp, settings.fmp_api_key, settings.fmp_base_url, settings.fmp_econ_calendar_tz
        ),
        kis=KisFetcher(kis, settings.kis_app_key, settings.kis_app_secret, settings.kis_base_url),
        naver=NaverNewsFetcher(nv, settings.naver_client_id, settings.naver_client_secret),
        http=http,
    )
