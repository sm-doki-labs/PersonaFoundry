"""S4 챕터 기준 프레임 계약 (LLD §5.10, D-0025)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.hero import ImageRef
from character_factory_poc.contracts.plan import Chapter
from character_factory_poc.contracts.qa import QaSummary
from character_factory_poc.contracts.reference import RankingScope

ChapterId = Literal["ch1", "ch2", "ch3"]


@register("frames-inputs-v1")
class FramesInputs(Strict):
    """S4 실행 입력 고정본: 기준 얼굴(G2)과 승인된 기획의 챕터(G3)."""

    schemaVersion: Literal["frames-inputs-v1"] = "frames-inputs-v1"
    appearanceRev: str = Field(pattern=r"^ar\d+$")
    planRev: str = Field(pattern=r"^pr\d+$")
    scope: RankingScope
    job: str
    styleTags: dict[str, list[str]] = Field(default_factory=dict)
    referenceImage: ImageRef
    # 생성에 실제로 넣은 참조(D-0027). 얼굴 크롭이면 reference/<id>-face.png, 실패하면 전체 이미지.
    identityReference: ImageRef | None = None
    referenceCrop: Literal["face", "full"] = "full"
    cropNote: str = ""
    chapters: list[Chapter] = Field(min_length=3, max_length=3)


@register("chapter-frame-v1")
class ChapterFrame(Strict):
    schemaVersion: Literal["chapter-frame-v1"] = "chapter-frame-v1"
    frameId: str = Field(pattern=r"^ch[123]-f\d+$")
    chapterId: ChapterId
    appearanceRev: str
    planRev: str
    prompt: str = Field(min_length=1)
    negativePrompt: str = ""
    model: str
    provider: str
    settings: dict[str, str | int]
    fileSha256: str
    filePath: str
    qa: QaSummary | None = None  # 완성 이미지 자동 검사 요약(D-0036)


class ApprovedFrame(Strict):
    chapterId: ChapterId
    frameId: str
    path: str
    sha256: str
    prompt: str


@register("chapter-frames-approved-v1")
class ApprovedFrames(Strict):
    """G4에서 사람이 챕터마다 한 장씩 승인한 기준 프레임. S6 액션 영상의 입력이다."""

    schemaVersion: Literal["chapter-frames-approved-v1"] = "chapter-frames-approved-v1"
    characterId: str
    frameRev: str = Field(pattern=r"^fr\d+$")
    appearanceRev: str
    planRev: str
    frames: list[ApprovedFrame] = Field(min_length=3, max_length=3)
    notes: str = ""

    @field_validator("frames")
    @classmethod
    def _one_per_chapter(cls, v: list[ApprovedFrame]) -> list[ApprovedFrame]:
        if sorted(f.chapterId for f in v) != ["ch1", "ch2", "ch3"]:
            raise ValueError("frames는 ch1, ch2, ch3 각각 하나씩이어야 한다")
        return v
