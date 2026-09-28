# 백엔드 배포 가이드 (무료 구성: Render + Supabase + GitHub Actions)

| 역할 | 서비스 | 비용 |
|---|---|---|
| 리포트 저장 DB | Supabase (PostgreSQL, 싱가포르) | 무료 |
| API 서버 (DB → 웹 화면 전달) | Render 무료 웹 서비스 (싱가포르) — `render.yaml` | 무료 |
| 리포트 생성 (월~금 07:00 / 15:40 KST) | GitHub Actions 예약 실행 — `.github/workflows/reports.yml` | 무료 (한도 내) |
| 웹 화면 | Netlify — `netlify.toml` | 무료 |

- GitHub 예약 실행은 부하에 따라 **수 분 이상 늦게** 시작될 수 있다.
- 비공개 저장소는 GitHub Actions 무료 사용 시간 한도가 있다(개인 무료 플랜 월 2,000분으로 알려짐, 확인 필요).
  이 작업은 1회 수 분 × 하루 2회라 한도 안에 들어갈 것으로 추정.
- 공개 저장소는 60일간 커밋 등 활동이 없으면 예약 실행이 자동 중지될 수 있다(Actions 탭에서 다시 켜기).

> 🔐 비밀번호·API 키는 **Render / GitHub Secrets 화면에만** 입력한다. 코드, 채팅에 붙여 넣지 말 것.

---

## 1단계. Supabase — DB 만들기

1. https://supabase.com → GitHub 로 로그인 → **New project**
   - Database Password: **영문·숫자만** (특수문자는 주소 인코딩 문제 유발)
   - Region: **Southeast Asia (Singapore)**
2. 상단 **Connect** → **Direct (Connection string)** → **Session pooler** 주소 복사
   (`...@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`)
3. `[YOUR-PASSWORD]` 를 비밀번호로 바꾼다(대괄호 삭제). 이것이 `DATABASE_URL`.

> ⚠️ `db.xxxx.supabase.co` (Direct connection) 주소는 IPv6 전용이라 Render/GitHub 에서 실패할 수 있다.
> 테이블은 첫 실행 때 자동 생성된다.

## 2단계. Render — API 서버 (무료, 카드 불필요 예상)

1. https://render.com → GitHub 로 로그인
2. **Environment Groups** → **New Environment Group**
   - 이름: **`stock-assistant-secrets`**
   - 변수: `DATABASE_URL` = 1단계 주소 (서버는 DB 만 읽으므로 API 키는 불필요)
3. **Blueprints** → **New Blueprint Instance** → 저장소 `beom808/20260928-Stock-Assistant` → **Apply**
   - 서비스 `stock-assistant-api` (Free) 1개가 만들어진다
4. 서비스 주소(`https://stock-assistant-api-xxxx.onrender.com`) + `/health` → `{"ok":true}` 확인

## 3단계. GitHub — 리포트 생성용 Secrets 등록

1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. 아래를 하나씩 등록 (이름 철자·대소문자 정확히):

| Name | 값 | 필요도 |
|---|---|---|
| `DATABASE_URL` | 1단계 주소 (Render 와 같은 값) | **필수** |
| `FINNHUB_API_KEY` | https://finnhub.io 가입 → Dashboard 의 API Key | **필수 권장** — 미국 뉴스·실적 일정 |
| `FMP_API_KEY` | https://financialmodelingprep.com | 선택 — 미국 지수·경제캘린더 (일부 유료일 수 있음) |
| `KIWOOM_APP_KEY`, `KIWOOM_APP_SECRET` | https://openapi.kiwoom.com (키움 계좌로 API 사용 신청 후 발급) | 권장 — 코스피·코스닥 |
| `KIS_APP_KEY`, `KIS_APP_SECRET` | https://apiportal.koreainvestment.com | 선택 — 코스피·코스닥 대안 (키움 실패 시 사용) |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com | 선택 — AI 요약 (사용량 과금) |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | https://developers.naver.com | 선택 — 국내 당일 이슈 |

없는 키는 등록하지 않으면 된다(해당 섹션만 "수집 실패"로 표시).

## 3-1단계. (키움 사용 시) 고정 IP 프록시로 국내 지수 조회

키움 REST API 는 **등록된 IP(최대 10개, 개별 주소)** 에서만 요청을 받는다
(미등록 시 `8050: IP가 등록되지 않았습니다`). GitHub Actions 는 실행마다 IP 가 바뀌고,
Render 의 외부 IP 는 다른 사용자와 공유하는 넓은 대역(/24)이라 등록에 적합하지 않다.
→ **키움 요청만 고정 IP 프록시(Fixie)** 를 거치게 한다. HTTPS 라 프록시는 키·내용을 볼 수 없다.

1. https://usefixie.com 가입 → **New proxy application** (무료 플랜 한도는 가입 화면에서 확인)
2. 앱 화면의 **Outbound IPs(2개)** 를 키움 REST API 홈페이지 → **API 사용신청** → 허용 IP 로 등록
3. 앱 화면의 **Proxy URL** (`http://fixie:...@...:80`, 비밀번호 포함) 을
   GitHub Secrets 에 **`KIWOOM_PROXY_URL`** 로 등록 (채팅·코드에 붙여 넣지 말 것)
4. Actions → reports → Run workflow(`afternoon`) 로 확인 — 로그에 키움 오류가 없으면 성공

## 4단계. 첫 리포트 수동 생성

1. GitHub 저장소 → **Actions** 탭 → 왼쪽 **reports** → **Run workflow**
   - 생성할 리포트: `all`, 휴장일이면 `force` 체크 → **Run workflow**
2. 실행 기록을 눌러 **Generate reports** 단계 로그 확인
   - `{'status': 'ok' …}` 또는 `partial`(일부 키 없음) 이면 정상, `skipped` 는 휴장일
   - 빨간 ✗ 이면 로그 마지막 부분을 확인

## 5단계. Netlify — 웹 화면과 연결

1. Netlify → `stockassistant2` → **Environment variables** → `API_BASE_URL` = 2단계 Render 주소 (끝 `/` 없이)
2. **Deploys** → **Trigger deploy** → **Deploy site**
3. https://stockassistant2.netlify.app 새로고침

> 무료 서버는 15분간 요청이 없으면 잠든다. "깨어나는 중" 안내가 보이면 30~60초 후 새로고침.

---

## 문제 해결

| 증상 | 확인할 곳 |
|---|---|
| Actions 실행 실패: `DATABASE_URL secret 이 설정되지 않았습니다` | 3단계 Secrets 등록 |
| Actions 로그에 DB 접속 오류 | Session pooler 주소인지, 비밀번호 치환했는지 |
| `/health` 는 되는데 화면에 "리포트가 아직 없습니다" | 4단계 수동 실행 |
| 화면에 계속 "연결할 수 없습니다" | Netlify `API_BASE_URL` 값과 재배포 여부 |
| 예약 시각에 실행 안 됨 | Actions 탭에서 워크플로가 비활성화되지 않았는지 (수 분 지연은 정상) |
