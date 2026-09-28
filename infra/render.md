# 백엔드 배포 가이드 (Render + Supabase)

구성: **Render**(FastAPI 서버 1개 + 크론잡 2개, 싱가포르 리전) + **Supabase**(PostgreSQL 무료).
설정은 저장소 루트의 `render.yaml`(Blueprint)에 들어 있다.

> 🔐 API 키·DB 비밀번호는 **Render 화면에만** 입력한다. 코드, GitHub, 채팅에 붙여 넣지 말 것.

---

## 1단계. Supabase — DB 만들기

1. https://supabase.com → **Start your project** → GitHub 로 로그인
2. **New project**
   - Name: `stock-assistant` (자유)
   - Database Password: **영문·숫자만**으로 길게 만들고 따로 보관
     (특수문자가 있으면 접속 주소에서 인코딩 문제가 생길 수 있음)
   - Region: **Southeast Asia (Singapore)** — Render 서버와 같은 지역이라 빠름
3. 프로젝트가 만들어지면 상단 **Connect** 버튼 → Connection string 에서 **Session pooler** 선택
   → `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-...pooler.supabase.com:5432/postgres` 형태의 주소 복사
   → `[YOUR-PASSWORD]` 부분을 2번의 비밀번호로 바꾼다. 이것이 `DATABASE_URL` 이다.

> ⚠️ **Direct connection 주소(`db.xxxx.supabase.co`)는 쓰지 말 것.** 기본적으로 IPv6 전용이라
> Render 에서 접속이 실패할 수 있다. Session pooler(포트 5432)는 IPv4 를 지원한다.
> 테이블은 백엔드가 처음 실행될 때 자동 생성된다(수동 생성 원하면 `backend/schema.sql`).

## 2단계. API 키 발급

| 변수명 | 발급처 | 필요도 |
|---|---|---|
| `FINNHUB_API_KEY` | https://finnhub.io (가입 후 Dashboard) | **필수** — 미국 뉴스·실적 일정 |
| `FMP_API_KEY` | https://financialmodelingprep.com | 권장 — 미국 지수·경제캘린더 (일부 유료일 수 있음) |
| `KIS_APP_KEY`, `KIS_APP_SECRET` | https://apiportal.koreainvestment.com | 권장 — 코스피·코스닥 (한국투자증권 계좌 필요) |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com | 선택 — AI 요약 (사용량 과금). 없으면 규칙기반 |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | https://developers.naver.com (검색 API) | 선택 — 국내 당일 이슈 |

없는 키는 비워 두지 말고 **변수 자체를 추가하지 않으면** 된다(해당 섹션은 "수집 실패"로 표시되고 나머지는 정상 동작).

## 3단계. Render — 환경변수 그룹 만들기 (Blueprint 적용 **전에**)

1. https://render.com → **Get Started** → GitHub 로 로그인
   (GitHub 권한 요청 시 `beom808/20260928-Stock-Assistant` 저장소 접근 허용)
2. 왼쪽 메뉴 **Environment Groups** → **New Environment Group**
3. Group name: **`stock-assistant-secrets`** (철자 정확히 — render.yaml 이 이 이름을 참조)
4. 변수 추가:
   - `DATABASE_URL` = 1단계에서 만든 Session pooler 주소
   - 2단계에서 발급한 키들 (`FINNHUB_API_KEY` 등)
5. **Create Environment Group**

## 4단계. Render — Blueprint 로 서비스 생성

1. 상단 **New** → **Blueprint**
2. 저장소 `beom808/20260928-Stock-Assistant` 선택, 브랜치 `main`
3. Render 가 `render.yaml` 을 읽어 3개 서비스를 보여 준다:
   - `stock-assistant-api` (Web Service, Free)
   - `stock-assistant-morning` (Cron, 월~금 07:00 KST)
   - `stock-assistant-afternoon` (Cron, 월~금 15:40 KST)
4. **Apply** (크론잡은 유료라 이 단계에서 카드 등록을 요청받을 수 있음 — 크론잡 1개당 최소 $1/월로 조사됨)
5. 빌드가 끝나면 `stock-assistant-api` 페이지 상단의 주소(`https://stock-assistant-api-xxxx.onrender.com`)를 복사
6. 브라우저에서 `그주소/health` 접속 → `{"ok":true}` 가 나오면 서버 정상

## 5단계. 첫 리포트 수동 생성 (다음 07:00 을 기다리지 않으려면)

1. Render → `stock-assistant-morning` → **Trigger Run** → Logs 에서 결과 확인
   - 마지막 줄 `{'status': 'ok', ...}` 또는 `partial`(일부 키 없음) 이면 정상
   - 한국 휴장일이면 `skipped` (정상 동작)
2. 같은 방법으로 `stock-assistant-afternoon` 도 실행 가능

## 6단계. Netlify — 웹 화면과 연결

1. Netlify → 프로젝트 `stockassistant2` → **Environment variables** → **Add a variable**
   - Key: `API_BASE_URL`
   - Value: 4-5단계의 Render 주소 (끝에 `/` 없이)
2. **Deploys** → **Trigger deploy** → **Deploy site**
3. https://stockassistant2.netlify.app 새로고침 → 리포트 카드 표시 확인

> 무료 서버는 15분간 요청이 없으면 잠든다. 첫 접속 시 "백엔드 서버가 깨어나는 중일 수 있습니다"가
> 보이면 30~60초 후 새로고침. 항상 켜 두려면 Render 에서 해당 서비스를 유료(Starter) 플랜으로 변경.

---

## 문제 해결

| 증상 | 확인할 곳 |
|---|---|
| 빌드 실패 | Render → 서비스 → Events/Logs 의 에러 줄 |
| `/health` 는 되는데 리포트 404 | 아직 리포트가 없음 → 5단계 실행 |
| 크론 로그에 DB 접속 오류 | `DATABASE_URL` 이 Session pooler 주소인지, 비밀번호 치환했는지 |
| 크론 로그에 `FINNHUB_API_KEY 미설정` | 환경변수 그룹에 키 추가 후 다시 Trigger Run |
| 화면에 계속 "연결할 수 없습니다" | Netlify `API_BASE_URL` 값과 재배포 여부 |
