# 스케줄 설정 (클라우드 크론, UTC 기준)

서버·크론은 **UTC** 로 동작하고 KST 변환은 애플리케이션(`backend/app/timeutil.py`)에서만 한다.
한국(KST)은 서머타임이 없으므로 KST 고정 시각 → UTC 크론식은 연중 고정이다.
미국 서머타임 전환은 리포트 **내용**(ET↔KST 환산)에서 IANA tz DB 로 자동 처리된다.

| 리포트 | 발행 시각(KST) | 크론(UTC) | 비고 |
|---|---|---|---|
| `us-close` 전일 미국 마감 | 월~금 07:00 | `0 22 * * 0-4` | 미국 마감 05:00(EDT)/06:00(EST) KST 이후 |
| `kr-watchlist` 관전 포인트 | 월~금 07:05 | `5 22 * * 0-4` | us-close 가 없으면 자동으로 먼저 생성 |
| `kr-close-and-calendar` | 월~금 15:40 | `40 6 * * 1-5` | 아래 설명 참고 |

- **15:40 권장 이유**: 정규장은 15:30 에 끝나지만(15:20~15:30 종가 단일가), 종가·지수 확정 데이터가
  API 에 반영되기까지 시차가 있을 수 있다. 15:30 정각 실행을 원하면 `30 6 * * 1-5` 로 바꾸면 된다.
- 한국 휴장일(`holidays` 라이브러리 XKRX)에는 잡이 `skipped` 로 기록되고 종료한다(`?force=true` / `--force` 로 강제 실행).
  임시 휴장·조기 폐장은 라이브러리에 없을 수 있으므로 거래소 공지로 보완 필요.

## GCP Cloud Scheduler 예시

```bash
API=https://<your-backend-host>
TOKEN=<JOB_TRIGGER_TOKEN 값>   # Secret Manager 사용 권장

gcloud scheduler jobs create http us-close --schedule="0 22 * * 0-4" --time-zone="Etc/UTC" \
  --uri="$API/jobs/us-close/run" --http-method=POST --headers="X-Job-Token=$TOKEN" \
  --attempt-deadline=600s
gcloud scheduler jobs create http kr-watchlist --schedule="5 22 * * 0-4" --time-zone="Etc/UTC" \
  --uri="$API/jobs/kr-watchlist/run" --http-method=POST --headers="X-Job-Token=$TOKEN" \
  --attempt-deadline=600s
gcloud scheduler jobs create http kr-close --schedule="40 6 * * 1-5" --time-zone="Etc/UTC" \
  --uri="$API/jobs/kr-close-and-calendar/run" --http-method=POST --headers="X-Job-Token=$TOKEN" \
  --attempt-deadline=600s
```

## AWS EventBridge Scheduler 예시

`cron(0 22 ? * SUN-THU *)`, `cron(5 22 ? * SUN-THU *)`, `cron(40 6 ? * MON-FRI *)` (UTC) 로
API Destination(POST + `X-Job-Token` 헤더) 또는 컨테이너 태스크(`python -m app.jobs.run <type>`)를 호출.

## 직접 실행 (컨테이너 잡 / 로컬)

```bash
cd backend
python -m app.jobs.run us-close
python -m app.jobs.run kr-watchlist
python -m app.jobs.run kr-close-and-calendar --force
```
