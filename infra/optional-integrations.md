# 선택 기능 설정 가이드 (순서대로)

| 순서 | 기능 | 비용 | 난이도 | 키를 넣는 곳 |
|---|---|---|---|---|
| 1 | 국내 당일 뉴스 (네이버 검색 API, NAVER API HUB) | 무료 제공량 내 무료(카드 등록 필요할 수 있음) | ★★ | GitHub Secrets |
| 2 | AI 분류·한국어 요약 (Anthropic Claude API) | **유료(사용량)** | ★ | GitHub Secrets |
| 3 | 미국 경제지표·FOMC 일정 (FMP) | 무료~유료(플랜 확인 필요) | ★ | GitHub Secrets |
| 4 | 발행 알림 푸시 (Firebase Cloud Messaging) | 무료 플랜으로 가능한 것으로 알려짐 | ★★★ | GitHub Secrets + Netlify |

- 리포트는 GitHub Actions 가 만들므로 **1~3 의 키는 GitHub Secrets 에만** 넣는다 (Render 에는 불필요).
- GitHub Secrets 위치: 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
  (바로가기: `https://github.com/beom808/20260928-Stock-Assistant/settings/secrets/actions`)
- 각 단계를 마친 뒤 **Actions → reports → Run workflow** 로 수동 실행하면 로그에서 바로 확인할 수 있다.
- 🔐 키·비밀번호는 채팅·코드에 붙여 넣지 말 것.

---

## 1. 국내 당일 뉴스 — 네이버 검색 API (NAVER API HUB)

> 2026-07-31 부터 네이버 개발자센터(developers.naver.com)의 검색 API **신규 발급이 종료**되고
> 네이버 클라우드 플랫폼의 **NAVER API HUB** 로 이관되었다(2027-06-30 개발자센터 종료 예정으로 알려짐).
> 이 앱은 기본으로 NAVER API HUB 주소·인증 방식을 쓴다. 메뉴 이름은 바뀔 수 있으니 화면에서 확인.

1. https://www.ncloud.com 가입/로그인 (네이버 클라우드 플랫폼)
   - 가입 완료에 **결제수단(카드) 등록**이 필요하다는 자료가 있다. HUB 는 무료 제공량 안에서는 과금되지 않는 것으로 알려짐
2. 콘솔 → 서비스 목록에서 **NAVER API HUB** 선택
3. **API Key 발급** → **Client ID**, **Client Secret** 확인 (Secret 은 한 번만 보일 수 있으니 바로 복사)
   - 사용할 API 선택 화면이 있으면 **검색(뉴스)** 포함
   - (권장) 호출량 임계치(threshold) 설정이 있으면 하루 수백 건 수준으로 설정
4. GitHub Secrets 등록
   - `NAVER_CLIENT_ID` = Client ID
   - `NAVER_CLIENT_SECRET` = Client Secret
5. 확인: Run workflow(`afternoon`) → 로그에 `국내 뉴스 검색 실패` 경고가 없으면 성공.
   화면의 "오늘의 국내 주요 이슈"에 기사 목록(원문 링크 포함)이 나온다.

> 무료 제공량: 하루 25,000회로 알려짐(이 앱은 하루 수 회). 유료 전환 시 사전 공지 예정이라고 알려짐.
> 기존 개발자센터에서 이미 받은 키가 있다면: GitHub → Settings → Secrets and variables → Actions →
> **Variables** 탭 → `NAVER_API` = `legacy` (키 이름은 위와 같음).

## 2. AI 분류·한국어 요약 — Anthropic Claude API (유료)

효과: 뉴스 10건을 (a)매크로 > (b)대형주 실적 > (c)섹터 > (d)개별 순으로 AI 가 분류하고 한국어 제목·요약을
붙인다. 한국 기업 관련도에 AI 추론이 더해진다(화면에 `AI 요약`/`AI 추론` 배지로 구분).
AI 는 후보 목록 안에서 고르기만 하고, 원문 링크·제목·수치는 항상 뉴스 API 원본을 쓴다.

1. https://platform.claude.com (Claude Console) 가입/로그인
2. **Billing(결제)** 에서 카드 등록·크레딧 충전 (최소 금액·결제 방식은 화면에서 확인)
3. (권장) 월 사용 한도 설정: **Settings → Limits** (https://platform.claude.com/settings/limits, 메뉴 이름은 화면에서 확인)
4. **API Keys → Create Key** → 키는 한 번만 보이므로 바로 복사
5. GitHub Secrets 등록: `ANTHROPIC_API_KEY` = 키
6. (선택) 모델 변경: 기본 `claude-opus-5-5`. 비용을 줄이려면 GitHub → Settings → Secrets and variables →
   Actions → **Variables** 탭 → `ANTHROPIC_MODEL` = `claude-sonnet-5-5`
7. 확인: Run workflow(`all`) → 화면 뉴스 카드에 한국어 제목과 `AI 요약` 배지가 보이면 성공.
   로그에 `LLM 분류 불가` 경고가 있으면 그 사유를 확인.

> **비용 추정(확정 아님)**: 하루 약 입력 2만·출력 1.5~2만 토큰으로 추정(사고 토큰은 출력으로 과금되어 더 늘 수 있음).
> 공식 요금표(2026-09 확인: Opus 5.5 입력 $4/출력 $20, Sonnet 5.5 입력 $2/출력 $10 — 100만 토큰당)로 계산하면
> 평일 22일 기준 **Opus 5.5 약 월 $8~11, Sonnet 5.5 약 월 $4~5**. 실제 금액은 콘솔 Usage 에서 확인.

## 3. 미국 경제지표·FOMC 일정 — FMP

1. https://site.financialmodelingprep.com 가입 → Dashboard 에서 **API Key** 복사
2. GitHub Secrets 등록: `FMP_API_KEY`
3. 확인: Run workflow(`afternoon`) → 로그
   - 오류 없음 → 성공 (캘린더에 CPI·고용·FOMC 등 표시, 발표시각 자동 검증 경고가 없어야 정상)
   - `HTTP 402` / `403` → **무료 플랜에서 경제캘린더를 제공하지 않는 것** → 유료 전환 여부 결정
     (유료로 바꾸지 않아도 나머지 기능은 그대로 동작)
> 2026-09-29 확인: 무료 플랜에서 **지수 시세는 제공, 경제캘린더는 HTTP 402(유료 전용)**.
> 경제지표 일정은 FMP 대신 **BEA·연준 공식 일정(무료)** 을 기본으로 사용한다(CPI·고용 등 BLS 지표는 미포함).
> 유료 플랜이면 GitHub → Variables 에 `FMP_ECON_CALENDAR` = `true` 로 FMP 일정도 함께 쓴다.

4. 부가 효과: FMP 지수 시세가 무료로 제공되면 미국 3대 지수가 ETF 대체값 대신 **실제 지수값**으로 표시된다.

> 무료 한도 하루 250회로 알려짐(이 앱은 하루 5회 수준). 경제캘린더의 무료 제공 여부는 확인하지 못함.

## 4. 발행 알림 푸시 — Firebase Cloud Messaging (웹 푸시)

리포트가 발행되면(07:00, 15:40) 구독한 브라우저로 알림을 보낸다.
- PC(크롬·엣지·맥 사파리): 사이트 상단 **발행 알림 받기** 버튼으로 구독
- iPhone: 사파리에서 사이트 열기 → 공유 → **홈 화면에 추가** → 홈 화면 앱에서 버튼으로 구독
  (iOS 는 홈 화면에 추가한 웹앱에서만 웹 푸시가 되는 것으로 알려짐)

### 4-1. Firebase 프로젝트와 웹앱
1. https://console.firebase.google.com → **프로젝트 추가** (Google 애널리틱스는 꺼도 됨)
2. 프로젝트 개요 → **웹 앱 추가(`</>`)** → 앱 닉네임 입력 → 등록 (Firebase Hosting 체크 불필요)
3. 표시되는 `firebaseConfig` 에서 **apiKey, projectId, messagingSenderId, appId** 4개 값을 기록
   (웹 설정값은 브라우저에 공개되는 값이라 비밀은 아님)

### 4-2. 웹 푸시 인증서(VAPID 키)
4. ⚙ **프로젝트 설정 → 클라우드 메시징** 탭 → 하단 **웹 푸시 인증서 → 키 쌍 생성** → 공개 키 문자열 복사

### 4-3. 서버 발송용 서비스 계정 키 (비밀)
5. ⚙ **프로젝트 설정 → 서비스 계정** 탭 → **새 비공개 키 생성** → JSON 파일 다운로드
6. 같은 탭/클라우드 메시징 탭에서 **Firebase Cloud Messaging API (V1)** 가 **사용 설정됨** 인지 확인

### 4-4. 값 넣기
7. **Netlify** → `stockassistant2` → Environment variables 에 추가 후 **Trigger deploy**
   - `NEXT_PUBLIC_FIREBASE_API_KEY` = apiKey
   - `NEXT_PUBLIC_FIREBASE_PROJECT_ID` = projectId
   - `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` = messagingSenderId
   - `NEXT_PUBLIC_FIREBASE_APP_ID` = appId
   - `NEXT_PUBLIC_FIREBASE_VAPID_KEY` = 4번의 공개 키
   - `NEXT_PUBLIC_API_BASE_URL` = `https://stock-assistant-api-7oz1.onrender.com` (구독 토큰 등록용)
8. **GitHub Secrets**
   - `FCM_PROJECT_ID` = projectId
   - `FCM_SERVICE_ACCOUNT_JSON` = 5번 JSON 파일을 텍스트 편집기로 열어 **내용 전체** 붙여넣기
   - 다운로드한 JSON 파일은 등록 후 안전한 곳에 보관하거나 삭제 (절대 저장소에 올리지 말 것)

### 4-5. 구독과 확인
9. 사이트 새로고침 → 상단 **발행 알림 받기** → 브라우저 알림 **허용** → 버튼이 "알림 켜짐" 으로 바뀌면 구독 완료
10. Run workflow(`morning`) → 로그에 `FCM: 1/1 건 발송` → 알림 수신 확인. 알림을 누르면 해당 리포트 화면이 열린다.

---

## 문제 해결

| 증상 | 확인할 곳 |
|---|---|
| 로그에 `…미설정` | 해당 Secret 이름 철자(대문자·밑줄) |
| 네이버 `HTTP 401` | Client ID/Secret 바뀌지 않았는지, 키 발급처(HUB/개발자센터)와 `NAVER_API` 값이 맞는지 |
| `LLM 분류 불가 (API error 401…)` | Anthropic 키, `…402/credit` 면 크레딧 잔액 |
| FMP `HTTP 402/403` | 플랜 미지원(유료 필요) |
| 알림 버튼이 안 보임 | Netlify 의 `NEXT_PUBLIC_FIREBASE_*` 5개 + 재배포 여부 |
| "알림이 차단됨" | 브라우저 사이트 설정에서 알림 허용으로 변경 |
| 로그에 `FCM: 등록된 구독 토큰 없음` | 9번 구독을 먼저 완료 |
| 로그에 `FCM 인증 실패` | `FCM_SERVICE_ACCOUNT_JSON` 에 JSON 전체가 들어갔는지 |
