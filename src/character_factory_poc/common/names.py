"""이름 정규화와 유출 검사 (FR-35, D-0017).

순위 목록의 인물 이름이 S1 다음 단계 산출물·이미지 프롬프트에 섞였는지 찾는다. 공백·문장부호를
지우고 casefold한 뒤 부분 문자열로 비교하므로 띄어쓰기·대소문자를 바꾼 표기도 잡는다.
"""

from __future__ import annotations

from collections.abc import Iterable

MIN_NAME_CHARS = 2


def normalize_name(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def find_name_leaks(text: str, names: Iterable[str]) -> list[str]:
    """text 안에 나타난 이름(원래 표기)을 정렬해 돌려준다. 두 글자 미만 이름은 검사하지 않는다."""
    hay = normalize_name(text)
    found = set()
    for name in names:
        key = normalize_name(name)
        if len(key) >= MIN_NAME_CHARS and key in hay:
            found.add(name)
    return sorted(found)
