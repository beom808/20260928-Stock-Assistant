from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _kw_pattern(kw: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")


def has_keyword(text: str, keywords: tuple[str, ...] | list[str]) -> list[str]:
    """단어 경계 기준 키워드 매칭 (예: 'ev' 가 'every' 에 매칭되지 않도록)."""
    low = text.lower()
    return [k for k in keywords if _kw_pattern(k).search(low)]


def norm_headline(s: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", " ", s.lower()).strip()


def first_sentence(s: str, limit: int = 160) -> str:
    s = (s or "").strip().replace("\n", " ")
    m = re.search(r"(.+?[.!?])(\s|$)", s)
    out = m.group(1) if m else s
    return out if len(out) <= limit else out[: limit - 1] + "…"
