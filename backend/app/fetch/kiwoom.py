"""키움증권 REST API — 국내 지수(코스피·코스닥) 시세.

규격 근거 (공식 포털 openapi.kiwoom.com 원문은 개발 환경에서 접근 불가 → 공개 예제로 대조):
- 서버: https://api.kiwoom.com (모의: https://mockapi.kiwoom.com)
- 토큰: POST /oauth2/token
  body {grant_type: client_credentials, appkey, secretkey} → {token, expires_dt, return_code}
- 업종현재가요청: POST /api/dostk/sect, 헤더 api-id=ka20001, authorization=Bearer <token>
  body {mrkt_tp, inds_cd} → {cur_prc, pred_pre, pred_pre_sig, flu_rt, return_code, return_msg}
- 업종코드: 001 = 종합(KOSPI), 101 = 종합(KOSDAQ)
- ⚠️ 시장구분(mrkt_tp) 값은 자료마다 달라(코스피 "0"/"000", 코스닥 "1"/"10") 확정하지 못했다.
  → 후보를 순서대로 시도하고 정상 응답(return_code 0, 지수값 숫자)만 채택. 추측값은 만들지 않는다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from app.fetch.http import ApiClient, ApiError
from app.schemas import IndexQuote

log = logging.getLogger(__name__)

# (mrkt_tp, inds_cd) 후보 — 앞쪽부터 시도
KIWOOM_INDEX_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "KOSPI": [("0", "001"), ("000", "001")],
    "KOSDAQ": [("1", "101"), ("10", "101"), ("0", "101"), ("000", "101")],
}
SECT_PATH = "/api/dostk/sect"
JSON_CT = "application/json;charset=UTF-8"
# 지수값 타당성 범위(단위 오해·잘못된 코드 응답을 걸러내기 위한 느슨한 범위)
PLAUSIBLE_INDEX_RANGE = (50.0, 100_000.0)


def _num(v: object) -> float | None:
    """'+2,450.12' / '-12.3' / '2450.12' → float. 부호는 호출 측에서 pred_pre_sig 로 정규화."""
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ok_code(body: Any) -> bool:
    return isinstance(body, dict) and str(body.get("return_code", 0)) == "0"


def _ok_token(body: Any) -> bool:
    return _ok_code(body) and bool(body.get("token"))


class KiwoomFetcher:
    provider = "kiwoom"

    def __init__(self, client: ApiClient, app_key: str, app_secret: str, base_url: str) -> None:
        self.client = client
        self.app_key = app_key
        self.app_secret = app_secret
        self.base = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    async def _token(self) -> str:
        if not self.configured:
            raise ApiError(self.provider, "config", "KIWOOM_APP_KEY / KIWOOM_APP_SECRET 미설정")
        res = await self.client.request_json(
            "POST",
            f"{self.base}/oauth2/token",
            json_body={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.app_secret,
            },
            headers={"Content-Type": JSON_CT},
            ttl=timedelta(hours=12),  # 발급 토큰 유효기간(expires_dt)보다 짧게 캐시
            cache_if=_ok_token,
        )
        body = res.data or {}
        token = body.get("token")
        if not token or str(body.get("return_code", 0)) != "0":
            raise ApiError(
                self.provider,
                "http",
                f"토큰 발급 실패: {body.get('return_msg') or '응답에 token 없음'}",
            )
        return token

    async def _sect(self, token: str, mrkt_tp: str, inds_cd: str) -> dict:
        res = await self.client.request_json(
            "POST",
            f"{self.base}{SECT_PATH}",
            json_body={"mrkt_tp": mrkt_tp, "inds_cd": inds_cd},
            headers={
                "Content-Type": JSON_CT,
                "authorization": f"Bearer {token}",
                "api-id": "ka20001",
                "cont-yn": "N",
                "next-key": "",
            },
            ttl=timedelta(minutes=3),
            cache_extra={"api_id": "ka20001", "mrkt_tp": mrkt_tp, "inds_cd": inds_cd},
            cache_if=_ok_code,
        )
        return res.data or {}

    @staticmethod
    def _parse(name: str, body: dict) -> IndexQuote | None:
        if str(body.get("return_code", 0)) != "0":
            return None
        close = _num(body.get("cur_prc"))
        if close is None:
            return None
        close = abs(close)
        lo, hi = PLAUSIBLE_INDEX_RANGE
        if not lo <= close <= hi:
            log.warning("키움 %s 지수값 범위 밖(%s) — 채택하지 않음", name, close)
            return None
        change = _num(body.get("pred_pre"))
        pct = _num(body.get("flu_rt"))
        # pred_pre_sig: 1·2 상승, 3 보합, 4·5 하락 (값 자체 부호와 무관하게 정규화)
        sign = str(body.get("pred_pre_sig", "")).strip()
        if sign in ("1", "2", "4", "5"):
            k = -1.0 if sign in ("4", "5") else 1.0
            change = k * abs(change) if change is not None else None
            pct = k * abs(pct) if pct is not None else None
        elif sign == "3":
            change, pct = 0.0, 0.0
        return IndexQuote(
            name=name, symbol=name, close=close, change=change, change_pct=pct,
            provider="키움증권 REST API",
        )  # fmt: skip

    async def index_quote(self, name: str, exclude_close: float | None = None) -> IndexQuote:
        """지수 1개 조회. exclude_close 와 같은 값이면 잘못된 코드로 보고 다음 후보를 시도."""
        token = await self._token()
        last_msg = ""
        for mrkt_tp, inds_cd in KIWOOM_INDEX_CANDIDATES[name]:
            try:
                body = await self._sect(token, mrkt_tp, inds_cd)
            except ApiError as e:
                if e.kind in ("config", "quota"):
                    raise
                last_msg = str(e)
                continue
            q = self._parse(name, body)
            if q is None:
                last_msg = str(body.get("return_msg") or "지수값 없음")
                continue
            if exclude_close is not None and q.close == exclude_close:
                last_msg = "다른 지수와 같은 값 반환(시장구분 코드 불일치로 판단)"
                continue
            log.info("키움 %s 채택: mrkt_tp=%s inds_cd=%s", name, mrkt_tp, inds_cd)
            return q
        raise ApiError(self.provider, "parse", f"{name} 지수 조회 실패: {last_msg}")
