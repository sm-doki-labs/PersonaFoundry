"""관문 사전 검토 (LLD §6.8, 명세 §7.2, D-0049).

A 갈래는 실행기가 부르는 자리만 둔다. B 갈래가 검토 등록부·계약·화면을 채운다.
"""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.pipeline.context import Context

# 사람 판정 자체가 내용인 G7a, 블라인드 비교인 G8에는 추천을 붙이지 않는다(FR-45).
NO_REVIEW_GATES = frozenset({"G7a", "G8"})


def review_on_open(ctx: Context, cid: str, gate: str) -> Path | None:
    """관문이 AWAITING_HUMAN이 된 뒤 실행기가 부른다. 예외를 밖으로 내지 않는다."""
    return None
