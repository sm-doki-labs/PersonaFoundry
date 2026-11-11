"""말로 나가는 답에 섞인 작성 메모·괄호 설명을 찾는다(D-0149).

Gemini Flash는 드물게 답을 쓰기 전 계획(프롬프트 칸 요약, "답변 구상", 글자 수)을
본문에 그대로 쓴다.
영상통화에서는 그대로 목소리가 되므로, 걸리면 그 답을 버리고 다시 생성한다.
"""

from __future__ import annotations

import re
from collections.abc import Callable

#: 프롬프트 칸 이름표, 화살표, 계획 표지, 글자 수 표기, 칸 머리.
MEMO = re.compile(
    r"(?:^|\n|[.。]\s*)(?:경향|말투|말높임|길이|행동|페르소나|지침|상황|답변)\s*[:：]"
    r"|→|->|답변\s*구상|\d+\s*자\s*안팎|\(약\s*\d+\s*자\)"
    r"|\[(?:PERSONA|OUTPUT|CURRENT|INPUT)"
)
#: 말로 하지 않는 괄호 설명. 소리 내어 읽으면 어색하다.
PAREN = re.compile(r"\([^()]{1,40}\)")


def memo_reason(text: str) -> str | None:
    """걸린 이유. 깨끗하면 None."""
    if m := MEMO.search(text or ""):
        return f"작성 메모: {m.group(0).strip()[:20]}"
    if m := PAREN.search(text or ""):
        return f"괄호 설명: {m.group(0)[:20]}"
    return None


def guarded(generate: Callable[[int], str], max_tries: int = 3) -> tuple[str, list[dict]]:
    """generate(시도 번호)를 메모가 없는 답이 나올 때까지 max_tries번까지 부른다.

    (답, 버린 답 기록)을 돌려준다. 끝까지 걸리면 마지막 답을 그대로 돌려주고 기록에 남긴다.
    """
    rejected: list[dict] = []
    text = ""
    for attempt in range(1, max_tries + 1):
        text = generate(attempt)
        reason = memo_reason(text)
        if reason is None:
            return text, rejected
        rejected.append({"attempt": attempt, "reason": reason, "text": text})
    return text, rejected
