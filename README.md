# 한미 증시 리서치 보조 (Stock Assistant)

한미 증시를 연동해 하루 3개 시점에 리포트를 자동 생성하고 웹 대시보드로 보여주는 **정보 제공·리서치 보조** 도구입니다.

> ⚠️ **투자 조언 아님** — 투자자문이나 종목 추천이 아닙니다. 면책 문구는 모든 화면 하단에 고정 노출되고 모든 API 응답(`disclaimer`)에도 포함됩니다.

| 리포트 | 발행(KST) | 엔드포인트 |
|---|---|---|
| A. 전일 미국 증시 마감 (3대 지수 + 주요 뉴스 10건) | 07:00 | `GET /report/us-close` |
| B. 한국장 관전 포인트 (섹터 → 관련 종목, 관련도 순) | 07:00 | `GET /report/kr-watchlist` |
| C. 국내 장 마감 + 익일 미국 이벤트 표 | 15:30 장 마감 후 (크론 15:40 권장) | `GET /report/kr-close-and-calendar` |

모든 엔드포인트는 `?date=YYYY-MM-DD`(KST 기준일)로 과거 리포트를 조회할 수 있습니다. `GET /reports` 는 이력 목록입니다.

## 구조

```
backend/            Python 3.11+ (3.12 권장) · FastAPI · SQLAlchemy 2 · PostgreSQL(운영)/SQLite(개발)
  app/fetch/        수집 계층 — Finnhub, FMP, KIS, 네이버 + 공통 캐시·재시도·레이트리밋·일일한도(http.py)
  app/transform/    가공 계층 — 뉴스 선정(us_close), 한국 기업 매핑(kr_mapping), 이벤트 표(calendar)
  app/db/           저장 계층 — 모델·CRUD (PostgreSQL DDL: backend/schema.sql)
  app/llm/claude.py Claude API 래퍼 (structured outputs, 실패 시 규칙기반 fallback)
  app/data/         정적 섹터-종목 매핑 테이블
  app/reports/      리포트 조립 (fetch → transform → store)
  app/jobs/run.py   스케줄 잡 진입점
  tests/            pytest (서머타임 경계, API 장애 fallback, 매핑 회귀 등)
frontend/           Next.js 16 (App Router) 웹 대시보드 — 카드형 UI, 원문 링크는 새 탭으로 열림
infra/scheduler.md  클라우드 크론(UTC) 설정
infra/render.md     백엔드 배포 가이드 (Render + Supabase + GitHub Actions)
infra/optional-integrations.md  선택 기능(네이버 뉴스·AI 요약·FMP·푸시) 설정 순서
render.yaml         Render Blueprint (API 서버, 무료 플랜)
.github/workflows/reports.yml  리포트 예약 생성 (월~금 07:00 / 15:40 KST)
netlify.toml        Netlify 설정 (frontend/ 빌드)
```

## 배포

- 웹 화면: Netlify (`netlify.toml`, 저장소 main 브랜치 자동 배포)
- API 서버: Render 무료 플랜 / DB: Supabase / 리포트 생성: GitHub Actions 예약 실행
- **[infra/render.md](infra/render.md) 의 단계별 가이드** 참고

## 실행

```bash
# 백엔드
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # FCM 푸시까지 쓰면 ".[dev,push]"
cp .env.example .env               # 키 입력 (절대 커밋 금지 — .gitignore 처리됨)
uvicorn app.main:app --reload      # http://localhost:8000/docs
python -m app.jobs.run us-close kr-watchlist --force   # 수동 생성
pytest                                                 # 테스트 (SQLite)
TEST_DATABASE_URL=postgresql://... pytest              # 같은 테스트를 실제 PostgreSQL 로

# 프론트엔드
cd frontend
cp .env.example .env.local
npm install && npm run dev         # http://localhost:3000
```

## 할루시네이션 방지 설계 (최우선 원칙)

- **URL 은 뉴스 API 응답값만 사용**합니다. LLM 출력 스키마에는 URL 필드가 아예 없고, LLM 은 후보 뉴스의 **ID 만 고를 수 있습니다**(JSON Schema `enum`). 제목·출처·시각·URL 은 항상 원본 레코드에서 가져옵니다.
- URL 이 비었거나 형식이 틀리면 `url=null` → 화면에 "원문 링크 없음". 항목은 제외하지 않고 순위를 유지합니다.
- 확인된 뉴스가 10건 미만이면 조회 구간을 최대 48시간 넓히고, 그래도 부족하면 **가짜 항목을 만들지 않고** 경고를 남깁니다.
- LLM 이 제시한 한국 종목은 후보 목록(`KR_UNIVERSE`) 안에서만 채택하고, 티커는 원문에 실제로 등장하는 것만 남깁니다.
- AI 가 만든 요약·추론에는 화면에 `AI 요약` / `AI 추론` 배지를 붙여 규칙·원문 데이터와 구분합니다.
- 실적 발표는 BMO/AMC/DMH 만 표시하고 구체 시각은 만들지 않습니다("확정 시각 없음").
- 경제지표 발표시각 자동 검증: CPI·고용·PCE 등이 08:30 ET 가 아니면 API 타임존 설정 오류 가능성을 경고합니다.
- 모든 리포트에 `sources`(출처·수집시각) · `generated_at_kst` · `status`(ok/partial/failed) · `warnings`/`errors` 가 포함됩니다.

## 뉴스 10건 선정 기준 (`app/transform/us_close.py`)

(a) 시장 전체 방향(금리·매크로) > (b) 시가총액 상위 기업 실적/가이던스 > (c) 특정 섹터 전반 > (d) 개별 이슈.
같은 등급 안에서는 중요도 → 최신순. LLM 이 없거나 실패하면 키워드 규칙으로 분류합니다.

## 한국 기업 관련도 (`app/transform/kr_mapping.py`)

네 기준을 **따로 계산**한 뒤 가중합: ① 동일산업/직접경쟁 0.35 · ② 공급망 0.30 · ③ 실적민감도 0.25 · ④ 테마 0.10(최하위).
정적 규칙과 LLM 추론이 둘 다 있으면 `0.6×정적 + 0.4×LLM`, LLM 만 있으면 `×0.8` 할인. 뉴스에 특정 미국 티커가 나오면(예: NVDA) 직접 공급망 엣지(예: SK하이닉스 HBM)를 반영합니다. 종목마다 판단 근거 1줄이 붙습니다.

## 타임존

- 서버·DB·크론은 UTC. ET↔KST 변환은 `zoneinfo`(IANA: `America/New_York`, `Asia/Seoul`)만 사용하고 수동 오프셋은 쓰지 않습니다.
- 미국 서머타임(3월 둘째 일요일~11월 첫째 일요일)은 tz DB 가 자동 반영하며, 2026·2027년 전환 전후를 테스트로 검증합니다.
- 07:00 리포트는 **정규장 개장 전 사전 브리핑**이며, KRX 프리마켓이 미시행이므로 이 시각의 국내 실거래 데이터를 가정하지 않습니다. (NXT 프리마켓 08:00~08:50 데이터 연동은 향후 선택 기능.)

## 외부 API — 연동 전 반드시 재확인할 사항

아래 내용은 2026-09-28 에 확인을 시도한 결과입니다. **Finnhub·FMP 공식 문서 사이트는 개발 환경에서 접근이 차단되어 원문을 직접 확인하지 못했고**, 검색 결과(2차 자료)로만 확인했습니다.

| API | 용도 | 확인 상태 / 주의 |
|---|---|---|
| Finnhub `/news`, `/company-news`, `/calendar/earnings`, `/quote` | 미국 뉴스·실적 일정(BMO/AMC)·ETF 시세 | 무료 60 req/min(2차 자료). 무료 플랜은 **개인용·재배포 불가** 조건으로 알려져 있으므로 서비스 공개 전 약관 확인 필요 |
| FMP `/stable/quote`, `/stable/economic-calendar`, `/stable/earnings-calendar` | 지수 시세(무료 확인)·경제 캘린더(**무료 플랜 402 확인** → 기본 사용 안 함, `FMP_ECON_CALENDAR=true` 로 켬) | 무료 250 req/day. **earnings-calendar 는 유료 전용이라는 2차 자료가 있고, economic-calendar·지수 시세의 무료 제공 여부는 확인하지 못함.** 402/403 이면 지수는 ETF(SPY/QQQ/DIA) 프록시로 대체하고 캘린더는 오류로 표시. `date` 필드의 타임존도 미확인 → `FMP_ECON_CALENDAR_TZ` 로 설정(자동 검증 경고 참고) |
| 키움 REST API `ka20001` 업종현재가 | 코스피(001)·코스닥(101) — 기본 | 공개 예제·명세로 대조(공식 포털 원문은 개발 환경에서 접근 불가). 시장구분 코드가 자료마다 달라 후보를 순서대로 시도하고 정상 응답만 채택 |
| KIS Open API `inquire-index-price` (tr_id `FHPUP02100000`) | 코스피(0001)·코스닥(1001) — 키움 실패 시 대안 | 공식 GitHub 예제(koreainvestment/open-trading-api)로 엔드포인트·필드 확인. 접근토큰은 23시간 캐시(발급 빈도 제한 대응). **토큰이 DB `api_cache` 에 저장되므로 DB 접근 권한 관리 필요** |
| BEA `release_dates.json` · 연준 `calendar.json` | 미국 경제지표(GDP·PCE·무역수지)·FOMC·베이지북 일정 — 기본 | 무료·키 없음, 공식 1차 자료. GitHub Actions 에서 형식 확인(2026-09-29). **BLS(CPI·고용·PPI)는 자동 요청 차단(403)으로 미포함** |
| 네이버 검색 API(뉴스) — NAVER API HUB `/search/v1/news` | 국내 당일 이슈 | 2026-07-31 개발자센터 신규 발급 종료 → 네이버 클라우드 NAVER API HUB 로 이관(2차 자료). 기존 개발자센터 키는 `NAVER_API=legacy`. 무료 25,000 req/day(2차 자료). 미설정 시 이슈 섹션은 비어 있음(가짜 이슈 생성 안 함) |
| Anthropic Claude API | 분류·요약·관련도 추론 | 기본 모델 `claude-opus-5-5`(`ANTHROPIC_MODEL` 로 변경 가능), 거절 시 서버측 fallback(`fallbacks: "default"`). 키가 없으면 규칙기반으로 동작 |

## 알려진 한계

- 정적 매핑 테이블의 종목코드·공급망 관계는 작성 시점 기준입니다. 운영 전 KRX 종목마스터로 코드를 재검증하고, 관계는 분기마다 사람이 검토해야 합니다.
- 휴장일은 `holidays` 라이브러리(XNYS/XKRX) 기준이며 임시 휴장·조기 폐장(13:00 ET)은 반영되지 않을 수 있습니다.
- 나스닥 지수를 ETF 로 대체할 때 쓰는 QQQ 는 나스닥100 추종이라 나스닥 종합지수와 구성이 다릅니다(화면에 표시됨).
- 실제 API 키로 하는 라이브 연동 테스트는 아직 하지 않았습니다. 외부 API 는 모두 모킹해서 테스트했습니다.
