"""수정 요청 재작업 계약 (LLD §5.20, 명세 §7.3, D-0049, FR-46).

사람이 남긴 수정 메모를 재작업 브리프 하나로 묶는다. `targets`는 관문 기록의 `requestedChanges`
원문이고, `keep`은 건드리지 않는 단위다. `instructions`는 단계 에이전트에게 그대로 주는 지시문으로,
`[rework] normalize = true`면 텍스트 모델이 메모를 한 번 다듬은 문장이고 아니면 메모 원문을 줄마다
이은 문장이다. 정규화에 실패하면 원문으로 돌아가고 `normalizedBy`를 비운다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict


class ReworkTarget(Strict):
    """다시 만들 단위와 사람 메모 원문. field는 챕터·동작·항목 ID다."""

    field: str = Field(min_length=1)
    note: str = Field(min_length=1, description="관문 기록 requestedChanges[].note 원문 그대로")


class NormalizerRef(Strict):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


@register("rework-brief-v1")
class ReworkBrief(Strict):
    schemaVersion: Literal["rework-brief-v1"] = "rework-brief-v1"
    subjectId: str = Field(description="characterId")
    gate: str
    stage: str
    fromRev: str = Field(description="수정 요청을 받은 관문 revision")
    round: int = Field(ge=1, description="그 관문의 REQUEST_CHANGES 기록 수(이번 것 포함)")
    recordRef: str = Field(min_length=1, description="관문 기록 경로(캐릭터 폴더 기준)")
    targets: list[ReworkTarget] = Field(default_factory=list)
    keep: list[str] = Field(default_factory=list, description="다시 만들지 않고 이월하는 단위 ID")
    instructions: str = ""
    normalizedBy: NormalizerRef | None = None
    createdAt: str
