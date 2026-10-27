"""S2 기준 사진 계약 (LLD §5.7·§5.8, D-0042, D-0043).

`hero-candidate-v1`은 기준 사진을 만든 시도에만 붙는다(`generate`). `picked`는 G1 얼굴을
그대로 기준 이미지로 쓰므로 기준 사진 기록을 만들지 않는다. `hero-comparison-v1`은 쓰지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from acf.common.schema import register
from acf.contracts.common import Strict
from acf.contracts.reference import RankingScope

BasePhoto = Literal["generate", "picked"]


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
    # 옛 기록에는 없다. 없으면 generate다(D-0043 (6)).
    basePhoto: BasePhoto = "generate"


class IdentityCheck(Strict):
    """같은 사람인지 본 결과(D-0043 (4)). `picked`는 검사하지 않고 SKIPPED다."""

    rubric: str = "identity-v1"
    status: Literal["PASS", "SKIPPED"]
    attempts: int = Field(default=0, ge=0)
    report: str = ""


@register("appearance-spec-v1")
class AppearanceSpec(Strict):
    """S2가 자동으로 고정한 외모 명세. 이후 단계(S4 프레임, S5·S6 영상)의 얼굴 기준이다."""

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
    # D-0043 (6)·(7): 옛 기록에는 없다. referenceImage는 picked면 G1 얼굴 그대로다.
    basePhoto: BasePhoto | None = None
    identityCheck: IdentityCheck | None = None
