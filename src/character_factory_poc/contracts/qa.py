"""이미지 자동 검사 계약 (LLD §5.10b, D-0036·D-0037).

비전 판정 모델이 기준표 항목마다 PASS·FAIL·UNSURE와 이유를 내고, FAIL이면 고칠 점을 붙여
이미지를 다시 만든다. 검사는 사람 관문을 대신하지 않는다. 끝까지 통과하지 못한 이미지도
경고와 함께 사람에게 보여 준다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

Verdict = Literal["PASS", "FAIL", "UNSURE"]


class VerdictItem(Strict):
    id: str = Field(min_length=1)
    verdict: Verdict
    reason: str = ""


@register("vision-verdict-v1")
class VisionVerdict(Strict):
    """비전 판정 모델 출력. 기준표의 항목을 빠짐없이 한 번씩 판정한다."""

    schemaVersion: Literal["vision-verdict-v1"] = "vision-verdict-v1"
    items: list[VerdictItem] = Field(min_length=1)
    fixHint: str = Field(default="", description="FAIL이 있을 때 다음 생성에 붙일 영어 수정 지시")


class QaRound(Strict):
    attempt: int = Field(ge=1)
    filePath: str
    sha256: str
    mode: Literal["generate", "edit", "regenerate"]
    fixApplied: str = ""
    items: list[VerdictItem]
    failed: list[str] = Field(default_factory=list)
    unsure: list[str] = Field(default_factory=list)
    fixHint: str = ""


@register("image-qa-v1")
class ImageQaReport(Strict):
    schemaVersion: Literal["image-qa-v1"] = "image-qa-v1"
    imageId: str
    stage: str
    rubric: str
    generatorProvider: str
    generatorModel: str
    judgeProvider: str
    judgeModel: str
    sameFamilyWarning: str = ""
    rounds: list[QaRound] = Field(min_length=1)
    finalAttempt: int = Field(ge=1)
    status: Literal["PASS", "FAIL"]


class QaSummary(Strict):
    """후보·프레임 기록에 붙는 요약. 자세한 내용은 report(qa/<id>.json)에 있다."""

    status: Literal["PASS", "FAIL"]
    attempts: int = Field(ge=1)
    failed: list[str] = Field(default_factory=list)
    unsure: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    report: str
