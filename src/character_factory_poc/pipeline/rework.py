"""수정 요청 재작업 (LLD §6.9, 명세 §7.3, D-0049).

A 갈래는 실행기가 부르는 자리만 둔다. C 갈래가 브리프 계약·반복 상한·단계별 부분 재생성을 채운다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from character_factory_poc.pipeline.context import Context

if TYPE_CHECKING:
    from character_factory_poc.pipeline.orchestrator import RunOptions


def prepare_rework(ctx: Context, cid: str, sid: str, opt: RunOptions) -> bool:
    """REJECTED 단계를 다시 돌리기 직전에 부른다. False면 그 단계를 돌리지 않는다(반복 상한)."""
    return True
