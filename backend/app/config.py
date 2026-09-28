"""환경변수 기반 설정. API 키 등 시크릿은 코드/레포에 절대 두지 않는다."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./stock_assistant.db"
    job_trigger_token: str = ""
    cors_origins: str = "http://localhost:3000"

    finnhub_api_key: str = ""
    finnhub_base_url: str = "https://finnhub.io/api/v1"
    finnhub_rate_per_min: int = 50  # 무료 60/min 으로 조사됨 → 여유분을 두고 50

    fmp_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    fmp_daily_limit: int = 240  # 무료 250/day 로 조사됨 → 여유분
    fmp_econ_calendar_tz: str = "UTC"

    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"

    # 키움증권 REST API (설정되어 있으면 국내 지수에 KIS 보다 우선 사용)
    kiwoom_app_key: str = ""
    kiwoom_app_secret: str = ""
    kiwoom_base_url: str = "https://api.kiwoom.com"

    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_daily_limit: int = 20000

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    fcm_project_id: str = ""
    fcm_service_account_file: str = ""

    # 미국 대형주 워치리스트 (실적 캘린더 필터 / 기업 뉴스 수집용)
    us_megacap_watchlist: str = (
        "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AVGO,TSM,AMD,MU,INTC,QCOM,ORCL,NFLX,"
        "JPM,LLY,XOM,WMT,COST,ASML,AMAT,LRCX,SMCI,PLTR,CRM,ADBE,BA,GM,F"
    )

    @property
    def watchlist(self) -> list[str]:
        return [s.strip().upper() for s in self.us_megacap_watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
