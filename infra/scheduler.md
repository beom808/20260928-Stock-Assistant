# 스케줄 설정 (클라우드 크론, UTC 기준)

> 현재 배포 구성에서는 이 일정이 GitHub Actions(`.github/workflows/reports.yml`)에 들어 있다 → `infra/render.md` 참고.
> GitHub 예약 실행은 수 분 이상 늦게 시작될 수 있다.

서버·크론은 **UTC** 로 동작하고 KST 변환은 애플리케이션(`backend/app/timeutil.py`)에서만 한다.
한국(KST)은 서머타임이 없으므로 KST 고정 시각 → UTC 크론식은 연중 고정이다.
미국 서머타임 전환은 리포트 **내용**(ET↔KST 환산)에서 IANA tz DB 로 자동 처리된다.

| 리포트 | 발행 시각(KST) | 크론(UTC) | 비고 |
|---|---|---|---|
| `us-close` → `kr-watchlist` (한 작업에서 순서대로) | 월~금 07:00 | `0 22 * * 0-4` | `python -m app.jobs.run us-close kr-watchlist` |
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
python -m app.jobs.run us-close kr-watchlist
python -m app.jobs.run kr-close-and-calendar --force
# 하나라도 실패하면 종료 코드 1 (크론 화면에 실패로 표시)
```

## Supabase 스케줄러 (GitHub 예약이 늦거나 빠질 때의 보험)

GitHub Actions 의 `schedule` 은 서버가 바쁘면 늦게 시작하거나 통째로 빠질 수 있다.
2026-10-14 15:40 실행이 누락됐고 10-15 07:00·07:30 실행은 시작되지 않았다.
그래서 DB(Supabase) 안의 `pg_cron` 이 정시에 GitHub 의 `workflow_dispatch` 를 호출하게 했다.
같은 작업이 두 번 시작돼도 `--skip-existing` 이 오늘 리포트가 이미 있으면 건너뛰어 중복 발행·알림이 없다.

설정 파일: `infra/supabase-scheduler.sql` (비밀값 없음)

1. **GitHub 토큰 만들기** — GitHub → Settings → Developer settings → Personal access tokens →
   **Fine-grained tokens** → Generate new token
   - Repository access: **Only select repositories** → 이 저장소 하나
   - Permissions → Repository permissions → **Actions: Read and write** (나머지는 건드리지 않음)
   - Expiration: 90일 등으로 정하고 만료 전에 교체
   - 생성 직후 한 번만 보이는 토큰을 복사한다. **채팅·코드에 붙여 넣지 말 것.**
2. **Supabase** → Database → **Extensions** 에서 `pg_cron`, `pg_net` 켜기
3. Supabase → Database → **Vault** → Add new secret: 이름 `github_dispatch_token`, 값 = 1번 토큰
4. Supabase → **SQL Editor** 에 `infra/supabase-scheduler.sql` 내용을 붙여 넣고 Run
5. 테스트(알림·저장 없음): `select private.trigger_report('afternoon', false, true);`
   → `select id, status_code, content from net._http_response order by created desc limit 5;`
   에서 `status_code = 204` 이면 성공. GitHub Actions 탭에 `workflow_dispatch` 실행이 생긴다.
6. 정시 실행 확인: `select jobname, schedule, active from cron.job;`,
   며칠 뒤 `cron.job_run_details` 와 Actions 실행 기록의 시각을 비교한다.

주의
- pg_cron 시각은 UTC 이다. 07:00 KST = 22:00 UTC(일~목), 15:40 KST = 06:40 UTC(월~금).
- 토큰이 새면 이 저장소의 Actions 를 누군가 실행할 수 있다. 권한은 최소로, 의심되면 즉시 삭제.
- Supabase 무료 프로젝트는 오래 쓰지 않으면 일시정지될 수 있다(이 앱은 매일 DB 를 써서 해당 없음).
- 호출 성공 여부는 `net._http_response` 에서만 보인다(`cron.job_run_details` 는 '요청함'까지만).
