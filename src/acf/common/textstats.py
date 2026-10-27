"""텍스트 통계: 섹션 파싱, 형용사 나열 검사 보조 (LLD §8.6·§8.7)."""

from __future__ import annotations

import re
import unicodedata

_SECTION_RE = re.compile(r"^\[([A-Z0-9_ /:]+)\]\s*$", re.MULTILINE)


def section_names(prompt: str) -> list[str]:
    """프롬프트의 [SECTION] 헤더 이름 목록 (순서 유지)."""
    return [m.group(1).strip() for m in _SECTION_RE.finditer(prompt)]


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# 한국어 서술 종결 어미(…다/…요/…지/…네 + 문장 끝)나 조건·연결 표지. 하나도 없으면 낱말 나열로 본다.
_PREDICATE_RE = re.compile(
    r"(?:[가-힣]+(?:다|요|지|네)(?=[.!?\s,)]|$))"
    r"|(?:[가-힣]+(?:하면|라면|면서|지만|않고|고서|으면|면)(?=[\s,.)]|$))"
    r"|(?:\b(?:때|경우|먼저)(?=[\s,.)]|$))"
)


def looks_like_bare_adjectives(text: str) -> bool:
    """서술·조건 없이 낱말만 나열된 칸인지 (LLD §8.6)."""
    t = normalize_text(text)
    if not t:
        return True
    if _PREDICATE_RE.search(t + " "):
        return False
    tokens = [w for w in re.split(r"[,\s·/]+", t) if w]
    return len(tokens) <= 8
