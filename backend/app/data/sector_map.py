"""정적 매핑 테이블: 미국 섹터/종목 → 한국 상장기업 (하이브리드 매핑의 '규칙' 부분).

⚠️ 유지보수 주의
- 종목코드는 작성 시점 기준 값이다. 운영 전 KRX 종목마스터(KIS 제공 마스터파일 등)로 재검증할 것.
- 공급망(고객사/공급사) 관계는 널리 공개·보도된 관계만 넣었고, 근거 문구에 '알려짐/보도'로 표기했다.
  사업 관계는 변할 수 있으므로 분기마다 사람이 검토해야 한다.
- 점수는 0~1 척도. 네 가지 기준을 분리해 저장하고, 가중합은 transform/kr_mapping.py 에서 계산.
  ① same_industry  동일 산업/직접 경쟁
  ② supply_chain   공급망(고객사·공급사)
  ③ sensitivity    실적 민감도(수출 비중·환율 등)
  ④ theme          테마성 연관 (최하위 가중치)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KrCompany:
    code: str
    name: str
    market: str  # KOSPI | KOSDAQ


@dataclass(frozen=True)
class Relation:
    code: str
    same_industry: float = 0.0
    supply_chain: float = 0.0
    sensitivity: float = 0.0
    theme: float = 0.0
    basis: str = ""  # 판단 근거 1줄


@dataclass(frozen=True)
class SectorDef:
    key: str
    label_ko: str
    kr_sector_ko: str
    keywords: tuple[str, ...]  # 규칙기반 섹터 판별용 (영문 소문자, 단어 경계 매칭)
    relations: tuple[Relation, ...] = field(default_factory=tuple)


KR_UNIVERSE: dict[str, KrCompany] = {
    c.code: c
    for c in [
        KrCompany("005930", "삼성전자", "KOSPI"),
        KrCompany("000660", "SK하이닉스", "KOSPI"),
        KrCompany("042700", "한미반도체", "KOSPI"),
        KrCompany("009150", "삼성전기", "KOSPI"),
        KrCompany("373220", "LG에너지솔루션", "KOSPI"),
        KrCompany("006400", "삼성SDI", "KOSPI"),
        KrCompany("247540", "에코프로비엠", "KOSDAQ"),
        KrCompany("003670", "포스코퓨처엠", "KOSPI"),
        KrCompany("005380", "현대차", "KOSPI"),
        KrCompany("000270", "기아", "KOSPI"),
        KrCompany("012330", "현대모비스", "KOSPI"),
        KrCompany("011070", "LG이노텍", "KOSPI"),
        KrCompany("034220", "LG디스플레이", "KOSPI"),
        KrCompany("035420", "NAVER", "KOSPI"),
        KrCompany("035720", "카카오", "KOSPI"),
        KrCompany("207940", "삼성바이오로직스", "KOSPI"),
        KrCompany("068270", "셀트리온", "KOSPI"),
        KrCompany("010950", "S-Oil", "KOSPI"),
        KrCompany("096770", "SK이노베이션", "KOSPI"),
        KrCompany("105560", "KB금융", "KOSPI"),
        KrCompany("055550", "신한지주", "KOSPI"),
        KrCompany("012450", "한화에어로스페이스", "KOSPI"),
        KrCompany("079550", "LIG넥스원", "KOSPI"),
        KrCompany("267260", "HD현대일렉트릭", "KOSPI"),
        KrCompany("010120", "LS ELECTRIC", "KOSPI"),
        KrCompany("009540", "HD한국조선해양", "KOSPI"),
        KrCompany("042660", "한화오션", "KOSPI"),
        KrCompany("005490", "POSCO홀딩스", "KOSPI"),
        KrCompany("259960", "크래프톤", "KOSPI"),
        KrCompany("036570", "엔씨소프트", "KOSPI"),
    ]
}

R = Relation

SECTORS: dict[str, SectorDef] = {
    s.key: s
    for s in [
        SectorDef(
            "semiconductors",
            "반도체",
            "반도체",
            (
                "semiconductor",
                "chip",
                "chips",
                "chipmaker",
                "memory",
                "dram",
                "nand",
                "hbm",
                "foundry",
                "gpu",
                "nvidia",
                "micron",
                "tsmc",
                "broadcom",
                "amd",
                "intel",
                "asml",
                "lam research",
                "applied materials",
            ),
            (
                R(
                    "000660",
                    1.0,
                    0.8,
                    0.8,
                    0.3,
                    "메모리 동종업체이며 엔비디아향 HBM 주요 공급사로 알려짐",
                ),
                R(
                    "005930",
                    1.0,
                    0.5,
                    0.8,
                    0.3,
                    "메모리·파운드리 동종업체(마이크론·TSMC 등과 직접 경쟁)",
                ),
                R(
                    "042700",
                    0.4,
                    0.7,
                    0.6,
                    0.5,
                    "HBM 제조용 TC본더 장비 공급사로 알려짐(메모리 투자 연동)",
                ),
                R(
                    "009150",
                    0.5,
                    0.4,
                    0.6,
                    0.3,
                    "반도체 패키지기판·MLCC 등 전자부품(서버·AI 수요 연동)",
                ),
            ),
        ),
        SectorDef(
            "ai_infra_power",
            "AI 인프라·전력기기",
            "전력기기/AI 인프라",
            (
                "data center",
                "datacenter",
                "power grid",
                "transformer",
                "electricity demand",
                "hyperscaler",
                "capex",
                "ai infrastructure",
                "utility",
                "utilities",
            ),
            (
                R(
                    "267260",
                    0.8,
                    0.5,
                    0.8,
                    0.5,
                    "변압기 등 전력기기 제조사로 미국향 수출 비중이 큰 것으로 알려짐",
                ),
                R(
                    "010120",
                    0.8,
                    0.4,
                    0.6,
                    0.5,
                    "전력기기·배전 설비 제조사(데이터센터 전력 수요 연동)",
                ),
                R("000660", 0.2, 0.5, 0.5, 0.4, "AI 서버 투자 확대 시 HBM 수요와 연동"),
            ),
        ),
        SectorDef(
            "ev_battery",
            "전기차·2차전지",
            "2차전지",
            (
                "ev",
                "electric vehicle",
                "battery",
                "batteries",
                "lithium",
                "tesla",
                "rivian",
                "charging",
            ),
            (
                R(
                    "373220",
                    0.9,
                    0.7,
                    0.8,
                    0.4,
                    "배터리 셀 제조사로 테슬라·GM 등 미국 완성차 공급사로 알려짐",
                ),
                R("006400", 0.9, 0.5, 0.7, 0.4, "배터리 셀 동종업체(미국 완성차 합작 공장 보도)"),
                R("247540", 0.7, 0.5, 0.6, 0.6, "양극재 제조사(배터리 셀 업체 공급망)"),
                R("003670", 0.7, 0.5, 0.6, 0.6, "양·음극재 제조사(배터리 공급망)"),
            ),
        ),
        SectorDef(
            "autos",
            "자동차",
            "자동차",
            (
                "automaker",
                "auto",
                "autos",
                "car sales",
                "vehicle",
                "general motors",
                "ford",
                "auto tariff",
            ),
            (
                R(
                    "005380",
                    1.0,
                    0.2,
                    0.9,
                    0.3,
                    "완성차 동종업체이며 미국 판매 비중·관세·환율 민감도가 큼",
                ),
                R(
                    "000270",
                    1.0,
                    0.2,
                    0.9,
                    0.3,
                    "완성차 동종업체이며 미국 판매 비중·관세·환율 민감도가 큼",
                ),
                R("012330", 0.7, 0.6, 0.7, 0.3, "현대차그룹 부품 계열사(완성차 판매 연동)"),
            ),
        ),
        SectorDef(
            "consumer_electronics",
            "IT 하드웨어(스마트폰)",
            "IT 부품",
            ("iphone", "smartphone", "apple", "handset", "wearable", "display"),
            (
                R("011070", 0.5, 0.9, 0.8, 0.4, "카메라모듈 제조사로 애플이 최대 고객사로 알려짐"),
                R("034220", 0.6, 0.6, 0.6, 0.3, "OLED 패널 제조사로 애플향 공급이 보도됨"),
                R("005930", 0.8, 0.3, 0.5, 0.3, "스마트폰 직접 경쟁사(갤럭시) 및 부품 공급"),
                R("009150", 0.4, 0.5, 0.5, 0.3, "MLCC·카메라모듈 등 스마트폰 부품"),
            ),
        ),
        SectorDef(
            "internet_platform",
            "인터넷·플랫폼",
            "인터넷/플랫폼",
            (
                "google",
                "alphabet",
                "meta",
                "search",
                "advertising",
                "ad revenue",
                "social media",
                "cloud",
            ),
            (
                R("035420", 0.8, 0.1, 0.4, 0.5, "국내 검색·광고·클라우드 동종업체"),
                R("035720", 0.7, 0.1, 0.3, 0.5, "국내 플랫폼·광고 동종업체"),
            ),
        ),
        SectorDef(
            "biotech_pharma",
            "바이오·제약",
            "바이오",
            (
                "biotech",
                "pharma",
                "drug",
                "fda",
                "clinical",
                "obesity",
                "glp-1",
                "eli lilly",
                "biosimilar",
            ),
            (
                R("207940", 0.6, 0.6, 0.6, 0.5, "바이오의약품 CDMO(글로벌 제약사 위탁생산) 기업"),
                R("068270", 0.8, 0.2, 0.6, 0.5, "바이오시밀러 제조사로 미국 시장 판매 비중 존재"),
            ),
        ),
        SectorDef(
            "energy_oil",
            "에너지·유가",
            "정유/에너지",
            (
                "oil",
                "crude",
                "opec",
                "brent",
                "wti",
                "gasoline",
                "refining",
                "natural gas",
                "exxon",
            ),
            (
                R("010950", 0.9, 0.2, 0.8, 0.3, "정유사로 유가·정제마진 민감도가 큼"),
                R("096770", 0.8, 0.2, 0.7, 0.3, "정유·석유화학 사업 보유(유가 민감)"),
            ),
        ),
        SectorDef(
            "financials_rates",
            "금융·금리",
            "은행/금융",
            (
                "bank",
                "banks",
                "treasury yield",
                "yields",
                "interest rate",
                "rate cut",
                "rate hike",
                "jpmorgan",
                "lending",
            ),
            (
                R("105560", 0.7, 0.0, 0.6, 0.4, "은행지주사로 금리·순이자마진 민감"),
                R("055550", 0.7, 0.0, 0.6, 0.4, "은행지주사로 금리·순이자마진 민감"),
            ),
        ),
        SectorDef(
            "defense_aerospace",
            "방산·항공우주",
            "방산",
            (
                "defense",
                "pentagon",
                "military",
                "missile",
                "nato",
                "lockheed",
                "boeing",
                "aerospace",
                "war",
            ),
            (
                R("012450", 0.8, 0.2, 0.5, 0.7, "방산·항공엔진 제조사(해외 수출 비중 확대 보도)"),
                R("079550", 0.8, 0.1, 0.4, 0.7, "유도무기 방산업체"),
            ),
        ),
        SectorDef(
            "shipbuilding",
            "조선·해운",
            "조선",
            ("shipbuilding", "shipyard", "navy", "lng carrier", "vessel", "maritime"),
            (
                R("009540", 0.9, 0.2, 0.6, 0.6, "조선 중간지주사(미국 조선 협력 이슈 연동)"),
                R("042660", 0.9, 0.3, 0.6, 0.6, "조선사로 미 해군 함정 MRO 수주가 보도됨"),
            ),
        ),
        SectorDef(
            "steel_materials",
            "철강·소재",
            "철강",
            ("steel", "aluminum", "metal tariff", "iron ore", "nucor"),
            (R("005490", 0.9, 0.2, 0.7, 0.4, "철강 동종업체로 미국 관세·원자재 가격 민감"),),
        ),
        SectorDef(
            "gaming_entertainment",
            "게임·엔터",
            "게임",
            ("video game", "gaming", "game", "esports", "nintendo", "electronic arts", "take-two"),
            (
                R("259960", 0.8, 0.0, 0.5, 0.5, "게임 개발사로 해외 매출 비중이 큼"),
                R("036570", 0.8, 0.0, 0.3, 0.4, "게임 개발사(동종 업종)"),
            ),
        ),
    ]
}

# 미국 개별 종목 → 섹터 (뉴스 related 티커로 섹터 판별)
US_TICKER_SECTOR: dict[str, str] = {
    "NVDA": "semiconductors",
    "AMD": "semiconductors",
    "MU": "semiconductors",
    "INTC": "semiconductors",
    "AVGO": "semiconductors",
    "TSM": "semiconductors",
    "QCOM": "semiconductors",
    "ASML": "semiconductors",
    "AMAT": "semiconductors",
    "LRCX": "semiconductors",
    "SMCI": "ai_infra_power",
    "VRT": "ai_infra_power",
    "GEV": "ai_infra_power",
    "ORCL": "ai_infra_power",
    "TSLA": "ev_battery",
    "RIVN": "ev_battery",
    "LCID": "ev_battery",
    "GM": "autos",
    "F": "autos",
    "STLA": "autos",
    "TM": "autos",
    "AAPL": "consumer_electronics",
    "GOOGL": "internet_platform",
    "GOOG": "internet_platform",
    "META": "internet_platform",
    "AMZN": "internet_platform",
    "MSFT": "internet_platform",
    "NFLX": "internet_platform",
    "LLY": "biotech_pharma",
    "NVO": "biotech_pharma",
    "PFE": "biotech_pharma",
    "MRK": "biotech_pharma",
    "AMGN": "biotech_pharma",
    "XOM": "energy_oil",
    "CVX": "energy_oil",
    "COP": "energy_oil",
    "JPM": "financials_rates",
    "BAC": "financials_rates",
    "GS": "financials_rates",
    "MS": "financials_rates",
    "WFC": "financials_rates",
    "C": "financials_rates",
    "LMT": "defense_aerospace",
    "RTX": "defense_aerospace",
    "NOC": "defense_aerospace",
    "GD": "defense_aerospace",
    "BA": "defense_aerospace",
    "NUE": "steel_materials",
    "X": "steel_materials",
    "CLF": "steel_materials",
    "EA": "gaming_entertainment",
    "TTWO": "gaming_entertainment",
    "RBLX": "gaming_entertainment",
}

# 미국 개별 종목 → 한국 기업 직접 공급망 엣지 (해당 티커가 뉴스에 등장할 때만 가산)
US_TICKER_EDGES: dict[str, tuple[Relation, ...]] = {
    "NVDA": (
        R("000660", supply_chain=1.0, basis="엔비디아향 HBM 주요 공급사로 알려짐"),
        R(
            "042700",
            supply_chain=0.6,
            basis="HBM 생산용 TC본더 공급(엔비디아 수요의 간접 수혜 구조)",
        ),
    ),
    "AAPL": (
        R("011070", supply_chain=1.0, basis="애플이 최대 고객사로 알려진 카메라모듈 공급사"),
        R("034220", supply_chain=0.6, basis="아이폰용 OLED 패널 공급이 보도됨"),
    ),
    "TSLA": (R("373220", supply_chain=0.8, basis="테슬라향 배터리 셀 공급사로 알려짐"),),
    "GM": (
        R("373220", supply_chain=0.8, basis="GM과 미국 배터리 합작법인(얼티엄셀즈) 운영이 알려짐"),
    ),
    "MU": (
        R("000660", same_industry=1.0, basis="마이크론과 메모리(DRAM·HBM) 직접 경쟁"),
        R("005930", same_industry=1.0, basis="마이크론과 메모리(DRAM·NAND) 직접 경쟁"),
    ),
    "TSM": (R("005930", same_industry=0.8, basis="TSMC와 파운드리 직접 경쟁"),),
}

MACRO_KEY = "macro_broad"
MACRO_LABEL = "시장 전반(매크로)"

# (a) 매크로 판별 키워드 — transform/us_close.py 규칙기반 fallback 에서 사용
MACRO_KEYWORDS: tuple[str, ...] = (
    "fed",
    "fomc",
    "powell",
    "federal reserve",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "pce",
    "ppi",
    "jobs report",
    "payrolls",
    "nonfarm",
    "unemployment",
    "gdp",
    "treasury",
    "yields",
    "recession",
    "tariff",
    "tariffs",
    "dollar",
    "shutdown",
    "debt ceiling",
    "stocks",
    "wall street",
    "s&p 500",
    "nasdaq",
    "dow",
)
EARNINGS_KEYWORDS: tuple[str, ...] = (
    "earnings",
    "results",
    "revenue",
    "guidance",
    "forecast",
    "outlook",
    "quarterly",
    "profit",
    "eps",
    "beats",
    "misses",
)
