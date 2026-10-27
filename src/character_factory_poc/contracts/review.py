"""관문 사전 검토 계약 (LLD §5.19, 명세 §7.2, D-0049).

`gate-review-v1`은 관문 revision 하나에 묶인 검토 결과다. 추천은 상태를 바꾸지 않고,
관문 기록(`gate-record-v1`)이 reviewRef·followedReview로만 가리킨다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ArtifactRef, Strict

ReviewMode = Literal["llm", "vision", "deterministic"]
ReviewVerdict = Literal["RECOMMEND", "OK", "CONCERN"]


class ReviewDefect(Strict):
    field: str
    note: str


class ReviewItem(Strict):
    candidateId: str = Field(description="관문 화면 항목 ID와 같은 값(web/gate_items.py)")
    chapterId: str | None = None
    rank: int | None = Field(default=None, ge=1)
    verdict: ReviewVerdict
    reasons: list[str] = Field(default_factory=list)
    defects: list[ReviewDefect] = Field(default_factory=list)


class ReviewerRef(Strict):
    provider: str
    model: str
    family: str


@register("gate-review-v1")
class GateReview(Strict):
    schemaVersion: Literal["gate-review-v1"] = "gate-review-v1"
    subjectId: str
    gate: str
    rev: str
    reviewer: ReviewerRef
    mode: ReviewMode
    shownArtifacts: list[ArtifactRef] = Field(default_factory=list)
    items: list[ReviewItem] = Field(default_factory=list)
    summary: str = ""
    createdAt: str
