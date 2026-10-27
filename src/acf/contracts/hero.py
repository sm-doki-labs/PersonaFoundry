"""S2 대표 이미지 계약 (LLD §5.7·§5.8, D-0022, D-0023)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from acf.common.schema import register
from acf.contracts.common import Strict
from acf.contracts.reference import RankingScope


class ImageRef(Strict):
    """rev 폴더 기준 상대 경로와 파일 해시."""

    id: str
    path: str
    sha256: str


@register("hero-candidate-v1")
class HeroCandidate(Strict):
    schemaVersion: Literal["hero-candidate-v1"] = "hero-candidate-v1"
    candidateId: str = Field(pattern=r"^h\d+$")
    clusterId: str
    sourceReferenceRev: str = Field(pattern=r"^rf\d+$")
    referencePreviews: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1)
    negativePrompt: str = ""
    model: str
    provider: str
    settings: dict[str, str | int]
    fileSha256: str
    filePath: str


@register("hero-inputs-v1")
class HeroInputs(Strict):
    """S2 실행 입력 고정본. 이름 없이 외모군 특징과 참조 사진만 담는다(FR-35)."""

    schemaVersion: Literal["hero-inputs-v1"] = "hero-inputs-v1"
    sourceReferenceRev: str = Field(pattern=r"^rf\d+$")
    clusterId: str
    commonTags: dict[str, str | list[str]] = Field(min_length=1)
    scope: RankingScope
    referencePreviews: list[ImageRef] = Field(default_factory=list)


@register("appearance-spec-v1")
class AppearanceSpec(Strict):
    """G2에서 고정한 외모 명세. 이후 단계(S4 프레임, S5·S6 영상)의 얼굴 기준이다."""

    schemaVersion: Literal["appearance-spec-v1"] = "appearance-spec-v1"
    characterId: str
    appearanceRev: str = Field(pattern=r"^ar\d+$")
    sourceReferenceRev: str = Field(pattern=r"^rf\d+$")
    clusterId: str
    scope: RankingScope
    tags: dict[str, str | list[str]] = Field(min_length=1)
    descriptionKo: str = Field(min_length=1)
    descriptionEn: str = Field(min_length=1)
    referenceImage: ImageRef
    referencePreviews: list[ImageRef] = Field(default_factory=list)
    heroPrompt: str = Field(min_length=1)
    forbidden: list[str] = Field(default_factory=list)
    notes: str = ""
