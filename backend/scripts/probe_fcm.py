"""FCM 설정 점검(수동, 알림 발송 없음): 서비스 계정 JSON · 프로젝트 ID · FCM API 사용 여부.

- JSON 파싱과 OAuth 토큰 발급이 되는지
- JSON 안의 project_id 가 FCM_PROJECT_ID 와 같은지 (값은 출력하지 않음)
- messages:send 를 validate_only 로 가짜 토큰에 호출 → 400(토큰 무효)이면 인증·API 모두 정상
키·토큰 값은 출력하지 않는다.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import Settings  # noqa: E402
from app.notify.fcm import _access_token, fcm_configured  # noqa: E402


def main() -> int:
    st = Settings()
    if not fcm_configured(st):
        print("❌ FCM_PROJECT_ID 또는 FCM_SERVICE_ACCOUNT_JSON 미설정")
        return 1
    try:
        info = json.loads(st.fcm_service_account_json)
    except ValueError as e:
        print(f"❌ FCM_SERVICE_ACCOUNT_JSON 이 올바른 JSON 이 아님 (앞뒤가 잘렸는지 확인): {e}")
        return 1
    print("JSON 필드:", sorted(info))
    print("type:", info.get("type"))
    same = info.get("project_id") == st.fcm_project_id.strip()
    print("project_id 일치:", "✅" if same else "❌ (FCM_PROJECT_ID 값 확인)")
    try:
        token = _access_token(st)
        print("✅ OAuth 토큰 발급 성공")
    except Exception as e:  # noqa: BLE001
        print(f"❌ OAuth 토큰 발급 실패: {type(e).__name__}")
        return 1
    url = f"https://fcm.googleapis.com/v1/projects/{st.fcm_project_id.strip()}/messages:send"
    body = {
        "validate_only": True,
        "message": {"token": "invalid-test-token", "notification": {"title": "t", "body": "b"}},
    }
    r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    status = r.json().get("error", {}).get("status") if r.status_code != 200 else "OK"
    print("FCM validate_only 응답:", r.status_code, status)
    if r.status_code == 400:
        print("✅ 인증·FCM API 정상 (가짜 토큰이라 400 이 정상)")
    elif r.status_code == 403:
        print("❌ FCM API(V1) 사용 중지 또는 권한 없음:", r.text[:300])
    elif r.status_code == 404:
        print("❌ 프로젝트를 찾을 수 없음 — FCM_PROJECT_ID 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
