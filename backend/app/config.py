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
    # FMP 경제캘린더는 무료 플랜 미지원(HTTP 402 확인) → 기본은 BEA·연준 공식 일정만 사용.
    # 유료 플랜이면 true 로 켜서 함께 사용
    fmp_econ_calendar: bool = False

    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"

    # 키움증권 REST API (설정되어 있으면 국내 지수에 KIS 보다 우선 사용)
    kiwoom_app_key: str = ""
    kiwoom_app_secret: str = ""
    kiwoom_base_url: str = "https://api.kiwoom.com"
    # 키움 허용 IP 대응: 고정 IP 프록시 주소 (예: Fixie 의 http://fixie:비밀번호@...:80). 비밀 정보.
    kiwoom_proxy_url: str = ""

    naver_client_id: str = ""
    naver_client_secret: str = ""
    # hub = NAVER API HUB(네이버 클라우드, 신규 발급), legacy = 기존 개발자센터 키
    naver_api: str = "hub"
    naver_daily_limit: int = 20000

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    fcm_project_id: str = ""
    fcm_service_account_file: str = ""  # 서비스 계정 키 파일 경로 (또는 아래 JSON 내용)
    fcm_service_account_json: str = ""  # 서비스 계정 키 JSON 전체 (GitHub Secret 용, 비밀 정보)
    # 알림을 눌렀을 때 열 웹 화면 주소 (FCM 링크는 전체 https 주소여야 함)
    site_url: str = "https://stockassistant2.netlify.app"

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
