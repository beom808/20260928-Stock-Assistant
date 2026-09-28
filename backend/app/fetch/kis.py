"""한국투자증권 KIS Developers Open API — 국내 지수 시세.

엔드포인트/필드는 공식 예제 저장소(github.com/koreainvestment/open-trading-api)의
`inquire_index_price`(tr_id FHPUP02100000) 기준. 접근토큰은 발급 빈도 제한이 있으므로 캐시(23h)한다.
"""

from __future__ import annotations

from datetime import timedelta

from app.fetch.http import ApiClient, ApiError
from app.schemas import IndexQuote

KR_INDEX_CODES = {"KOSPI": "0001", "KOSDAQ": "1001"}


def _f(v: object) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


class KisFetcher:
    provider = "kis"

    def __init__(self, client: ApiClient, app_key: str, app_secret: str, base_url: str) -> None:
        self.client = client
        self.app_key = app_key
        self.app_secret = app_secret
        self.base = base_url.rstrip("/")

    async def _token(self) -> str:
        if not (self.app_key and self.app_secret):
            raise ApiError(self.provider, "config", "KIS_APP_KEY / KIS_APP_SECRET 미설정")
        # 시크릿은 json_body 로 전송 → 캐시 키 계산에서 제외됨
        res = await self.client.request_json(
            "POST",
            f"{self.base}/oauth2/tokenP",
            json_body={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            headers={"Content-Type": "application/json"},
            ttl=timedelta(hours=23),
        )
        token = (res.data or {}).get("access_token")
        if not token:
            raise ApiError(self.provider, "http", "접근토큰 발급 실패")
        return token

    async def index_quote(self, name: str) -> IndexQuote:
        token = await self._token()
        res = await self.client.get_json(
            f"{self.base}/uapi/domestic-stock/v1/quotations/inquire-index-price",
            params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": KR_INDEX_CODES[name]},
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": "FHPUP02100000",
                "custtype": "P",
                "Content-Type": "application/json",
            },
            ttl=timedelta(minutes=3),
        )
        body = res.data or {}
        if str(body.get("rt_cd", "0")) != "0":
            raise ApiError(self.provider, "http", f"{body.get('msg_cd')}: {body.get('msg1')}")
        out = body.get("output") or {}
        if isinstance(out, list):
            out = out[0] if out else {}
        close = _f(out.get("bstp_nmix_prpr"))
        if close is None:
            raise ApiError(self.provider, "parse", f"{name} 지수값 없음")
        change = _f(out.get("bstp_nmix_prdy_vrss"))
        pct = _f(out.get("bstp_nmix_prdy_ctrt"))
        # prdy_vrss_sign: 1·2 상승, 3 보합, 4·5 하락 → 값의 부호와 무관하게 sign 기준 정규화
        sign = str(out.get("prdy_vrss_sign"))
        if sign in ("1", "2", "4", "5"):
            k = -1.0 if sign in ("4", "5") else 1.0
            change = k * abs(change) if change is not None else None
            pct = k * abs(pct) if pct is not None else None
        return IndexQuote(
            name=name,
            symbol=KR_INDEX_CODES[name],
            close=close,
            change=change,
            change_pct=pct,
            as_of=res.fetched_at,
            provider="한국투자증권 KIS Open API",
        )
